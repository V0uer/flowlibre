"""La descarga de 1.4 GB es el punto donde la gente abandona la instalacion.

Tres cosas tienen que ser ciertas y las tres se prueban contra un servidor real
levantado aqui mismo (no un mock de requests): que reanude donde se quedo, que
verifique el hash, y que **nunca** deje un binario corrupto en disco. Un .zip de
CUDA a medias que se da por bueno produce una app que abre y no transcribe, que
es exactamente el fallo mas caro que ya nos costo la tarea 5 (ver C41).
"""

from __future__ import annotations

import hashlib
import http.server
import threading

import pytest

from flowlibre import descargas


CUERPO = bytes(range(256)) * 400          # 102_400 bytes, no comprimible
SHA_OK = hashlib.sha256(CUERPO).hexdigest()


class _Handler(http.server.BaseHTTPRequestHandler):
    """Sirve CUERPO con soporte de Range, y puede cortar a media respuesta."""

    corte = None          # si es un int, manda solo esos bytes y cierra
    acepta_range = True
    peticiones: list = []

    def log_message(self, *a):        # silencio en la salida de pytest
        pass

    def do_GET(self):
        inicio = 0
        rango = self.headers.get("Range")
        type(self).peticiones.append(rango)
        if rango and self.acepta_range:
            inicio = int(rango.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {inicio}-{len(CUERPO)-1}/{len(CUERPO)}")
        else:
            self.send_response(200)
        cuerpo = CUERPO[inicio:]
        # Un corte real anuncia el tamano completo y luego muere a media
        # respuesta. Truncar tambien el Content-Length seria un corte "honesto",
        # que es justo el caso que NO estamos probando.
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        if self.corte is not None:
            self.wfile.write(cuerpo[: self.corte])
            self.close_connection = True
            return
        self.wfile.write(cuerpo)


@pytest.fixture
def servidor():
    _Handler.corte = None
    _Handler.acepta_range = True
    _Handler.peticiones = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/paquete.bin"
    srv.shutdown()


def test_descarga_completa_y_verifica_hash(servidor, tmp_path):
    destino = tmp_path / "paquete.bin"
    descargas.descargar(servidor, destino, sha256=SHA_OK)
    assert destino.read_bytes() == CUERPO


def test_reporta_progreso_hasta_el_total(servidor, tmp_path):
    vistos = []
    descargas.descargar(servidor, tmp_path / "p.bin", sha256=SHA_OK,
                        on_progress=lambda hecho, total: vistos.append((hecho, total)))
    assert vistos, "no reporto progreso ni una vez"
    assert vistos[-1] == (len(CUERPO), len(CUERPO))


def test_reanuda_donde_se_quedo_sin_volver_a_bajar_todo(servidor, tmp_path):
    destino = tmp_path / "paquete.bin"
    _Handler.corte = 40_000
    with pytest.raises(descargas.DescargaIncompleta):
        descargas.descargar(servidor, destino, sha256=SHA_OK, trozo=4096)
    parcial = destino.with_name(destino.name + ".parcial")
    guardado = parcial.stat().st_size
    assert 0 < guardado <= 40_000, "no conservo lo ya bajado"

    _Handler.corte = None
    descargas.descargar(servidor, destino, sha256=SHA_OK, trozo=4096)
    assert destino.read_bytes() == CUERPO
    assert _Handler.peticiones[-1] == f"bytes={guardado}-", "reanudo desde cero"


def test_hash_que_no_cuadra_borra_el_archivo(servidor, tmp_path):
    destino = tmp_path / "paquete.bin"
    with pytest.raises(descargas.HashInvalido):
        descargas.descargar(servidor, destino, sha256="00" * 32)
    assert not destino.exists(), "dejo un binario corrupto pasando por bueno"
    assert not destino.with_name(destino.name + ".parcial").exists()


def test_servidor_sin_range_reempieza_en_vez_de_concatenar_basura(servidor, tmp_path):
    """Un mirror que ignora Range devuelve 200 con el archivo entero. Pegarlo
    detras de lo ya bajado produce un archivo mas largo que el original y con el
    hash roto: hay que descartar lo parcial y empezar de nuevo."""
    destino = tmp_path / "paquete.bin"
    _Handler.corte = 40_000
    with pytest.raises(descargas.DescargaIncompleta):
        descargas.descargar(servidor, destino, sha256=SHA_OK, trozo=4096)

    _Handler.corte = None
    _Handler.acepta_range = False
    descargas.descargar(servidor, destino, sha256=SHA_OK)
    assert destino.read_bytes() == CUERPO


def test_no_vuelve_a_bajar_lo_que_ya_esta_bien(servidor, tmp_path):
    destino = tmp_path / "paquete.bin"
    destino.write_bytes(CUERPO)
    descargas.descargar(servidor, destino, sha256=SHA_OK)
    assert _Handler.peticiones == [], "volvio a bajar un archivo que ya estaba completo"


# --- instalacion del paquete de CUDA ----------------------------------------


@pytest.fixture
def datos(tmp_path, monkeypatch):
    """Directorio de datos falso: la suite nunca toca %APPDATA% real."""
    monkeypatch.setattr(descargas.paths, "data_dir", lambda: tmp_path)
    return tmp_path


def test_carpeta_de_cuda_vacia_no_cuenta_como_instalado(datos):
    """Una descarga o un descomprimido interrumpidos dejan la carpeta creada y
    vacia. Darla por buena manda a la app a cargar DLLs que no existen."""
    descargas.cuda_dir().mkdir(parents=True)
    assert descargas.cuda_instalado() is False


def test_cuda_instalado_cuando_hay_dlls(datos):
    d = descargas.cuda_dir()
    d.mkdir(parents=True)
    (d / "cublas64_12.dll").write_bytes(b"no soy una dll pero parezco")
    assert descargas.cuda_instalado() is True


def test_instalar_cuda_descomprime_y_tira_el_zip(datos, monkeypatch):
    import zipfile as _zip

    def falso_descargar(art, on_progress=None):
        destino = datos / art.destino_rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        with _zip.ZipFile(destino, "w") as z:
            z.writestr("bin/cublas64_12.dll", "contenido")
        return destino

    monkeypatch.setattr(descargas, "descargar_artefacto", falso_descargar)
    descargas.instalar_cuda()
    assert (descargas.cuda_dir() / "cublas64_12.dll").exists()
    assert not (datos / descargas.CUDA.destino_rel).exists(), "dejo 1.4 GB de zip inutil"


def test_no_baja_1_4_gb_sin_hash_publicado(datos):
    """La conducta, no el valor de la constante.

    Antes esto miraba descargas.CUDA, y el dia que se publico el release con su
    hash el test empezo a fallar por la razon equivocada: intentaba bajarse
    1.3 GB de verdad. Lo que se prueba es que un artefacto SIN hash se niegue.
    """
    sin_publicar = descargas.Artefacto(
        nombre="artefacto de prueba", archivo="x.zip", sha256="",
        destino_rel="x.zip",
    )
    with pytest.raises(descargas.DescargaError, match="hash publicado"):
        descargas.descargar_artefacto(sin_publicar)


def test_los_artefactos_publicados_traen_un_sha256_valido():
    """Un hash a medias (o de largo equivocado) nunca va a cuadrar, y el sintoma
    es una descarga de 1.3 GB que se borra sola al terminar, cada vez."""
    for art in (descargas.CUDA, descargas.MODELO_INT8):
        assert len(art.sha256) == 64, f"{art.nombre}: hash de largo raro"
        int(art.sha256, 16)      # revienta si no es hexadecimal
