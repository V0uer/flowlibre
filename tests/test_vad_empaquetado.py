"""El bundle tiene que llevarse el modelo de VAD de faster-whisper.

`faster_whisper/vad.py` carga `assets/silero_vad_v6.onnx` desde dentro de su
propio paquete. PyInstaller solo arrastra modulos de Python: ese .onnx no lo ve
nadie salvo que el spec lo pida. Sin el, el instalador compila sin un error, la
app abre, la bandeja responde, el microfono graba — y al transcribir muere en un
hilo de fondo con NO_SUCHFILE que con console=False no imprime nada. Asi salio
el instalador de la v2.0.0.

Los tests no construyen el bundle: miran que el spec lo pida y que lo que pide
siga siendo el archivo que la libreria busca.
"""

from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

RAIZ = Path(__file__).resolve().parent.parent
SPECS = [RAIZ / "packaging" / "flowlibre.spec",
         RAIZ / "packaging" / "flowlibre-debug.spec"]


def _nombre_del_modelo_que_carga_la_libreria() -> str:
    """El nombre sale de vad.py, no de una constante nuestra: si faster-whisper
    renombra el modelo en una actualizacion, es este test el que tiene que
    romperse y no el usuario al dictar."""
    from faster_whisper import vad

    fuente = Path(vad.__file__).read_text(encoding="utf-8")
    encontrados = [t for t in fuente.replace('"', "'").split("'")
                   if t.endswith(".onnx")]
    assert len(encontrados) == 1, f"vad.py carga {encontrados}, no un solo .onnx"
    return encontrados[0]


def _lineas_de_codigo(spec: Path) -> list[str]:
    """Sin comentarios. Un `# datos += collect_data_files(...)` satisface una
    busqueda de subcadena y deja pasar exactamente el bug que este archivo
    vigila: comprobado comentando la linea y viendo los tres tests en verde."""
    lineas = []
    for cruda in spec.read_text(encoding="utf-8").splitlines():
        codigo = cruda.split("#", 1)[0].strip()
        if codigo:
            lineas.append(codigo)
    return lineas


def test_ambos_specs_recogen_los_datos_de_faster_whisper():
    for spec in SPECS:
        codigo = _lineas_de_codigo(spec)
        assert any('collect_data_files("faster_whisper")' in l for l in codigo), (
            f"{spec.name} volvio a quedarse sin el modelo de VAD")
        assert any(l.startswith("from PyInstaller.utils.hooks import")
                   and "collect_data_files" in l for l in codigo), (
            f"{spec.name} usa collect_data_files sin importarlo")


def test_lo_que_recoge_el_spec_incluye_el_modelo_que_vad_py_abre():
    modelo = _nombre_del_modelo_que_carga_la_libreria()
    origenes = [os.path.basename(origen)
                for origen, _ in collect_data_files("faster_whisper")]
    assert modelo in origenes, (
        f"collect_data_files no trae {modelo}; trae {sorted(set(origenes))}")


def test_el_modelo_llega_a_la_ruta_donde_la_libreria_lo_busca():
    """faster-whisper lo abre como `<paquete>/assets/<modelo>`. Si el spec lo
    dejara en la raiz del bundle, el archivo estaria y la app seguiria sin
    transcribir."""
    modelo = _nombre_del_modelo_que_carga_la_libreria()
    destinos = {Path(destino).as_posix()
                for origen, destino in collect_data_files("faster_whisper")
                if os.path.basename(origen) == modelo}
    assert destinos == {"faster_whisper/assets"}, (
        f"{modelo} aterriza en {destinos}, no en faster_whisper/assets")
