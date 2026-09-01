"""Lo pesado no viaja en el instalador: se baja la primera vez que hace falta.

El instalador pesa 70.9 MB porque **no** trae las DLLs de CUDA (1.94 GB) ni el
modelo. Esta es la otra mitad de esa decision: bajarlos despues, solo en las
maquinas que los necesiten, y bajarlos bien.

**Bien** aqui significa tres cosas concretas, y ninguna es opcional:

1. **Reanudar.** Una descarga de 1.4 GB que se corta al 90% y empieza de cero es
   la forma mas rapida de que alguien desinstale la app.
2. **Verificar el hash.** Sin esto, un .zip truncado se descomprime a medias y la
   app abre, se ve perfecta y no transcribe. Ese fallo exacto ya nos costo la
   tarea 5 (C41): sin consola, el ModuleNotFoundError muere en un hilo de fondo
   que nadie ve.
3. **Nunca dejar un binario corrupto.** Si el hash no cuadra, se borra. Un archivo
   malo que se queda en disco se da por bueno en el siguiente arranque y el fallo
   se vuelve permanente e indiagnosticable.

**De donde sale cada cosa** (decision del autor, 2026-09-01): el paquete de CUDA y
el modelo cuantizado int8 van en GitHub Releases — son artefactos nuestros, no
existen en ningun otro lado. Los modelos estandar de Whisper se siguen bajando de
Hugging Face, como hoy, porque ya estan ahi y no tiene sentido pagarles ancho de
banda al repo.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from . import paths

# Un solo lugar con el slug del repo: lo leen las descargas y el auto-update.
GITHUB_REPO = os.environ.get("FLOWLIBRE_REPO", "V0uer/flowlibre")

TROZO = 1 << 20          # 1 MB: suficiente para que el progreso se sienta vivo
TIMEOUT_S = (10, 60)     # (conectar, leer) — el segundo es generoso a proposito


class DescargaError(Exception):
    """Algo salio mal bajando un artefacto."""


class DescargaIncompleta(DescargaError):
    """La conexion se corto antes de tiempo. Lo parcial se conserva."""


class HashInvalido(DescargaError):
    """Lo que llego no es lo que se esperaba. El archivo ya se borro."""


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(TROZO), b""):
            h.update(bloque)
    return h.hexdigest()


def descargar(
    url: str,
    destino: Path,
    *,
    sha256: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    session: requests.Session | None = None,
    trozo: int = TROZO,
) -> Path:
    """Baja `url` a `destino`, reanudando si hay un `.parcial` de un intento previo.

    `on_progress(bajado, total)` se llama con bytes absolutos, no incrementos: el
    que dibuja la barra no tiene que llevar la cuenta. `total` es 0 si el
    servidor no dice cuanto pesa.
    """
    destino = Path(destino)
    if destino.exists() and (sha256 is None or _sha256(destino) == sha256):
        # Ya esta y esta bien. El caso comun del segundo arranque.
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    ya = parcial.stat().st_size if parcial.exists() else 0

    http = session or requests
    headers = {"Range": f"bytes={ya}-"} if ya else {}
    resp = http.get(url, headers=headers, stream=True, timeout=TIMEOUT_S)
    resp.raise_for_status()

    # Un mirror que ignora Range responde 200 con el archivo entero. Pegar eso
    # detras de lo ya bajado produce un archivo mas largo y con el hash roto:
    # se descarta lo parcial en vez de concatenar basura.
    reanudando = ya > 0 and resp.status_code == 206
    if not reanudando:
        ya = 0

    total = int(resp.headers.get("Content-Length") or 0) + ya
    hecho = ya
    cortada = False
    with open(parcial, "ab" if reanudando else "wb") as f:
        try:
            for bloque in resp.iter_content(trozo):
                if not bloque:
                    continue
                f.write(bloque)
                hecho += len(bloque)
                if on_progress:
                    on_progress(hecho, total)
        except requests.RequestException:
            # La conexion se murio a media descarga. No es un error que haya que
            # propagar crudo: lo que ya se escribio en el .parcial es valido y es
            # exactamente lo que hace posible reanudar.
            cortada = True

    if cortada or (total and hecho < total):
        # Se conserva el .parcial a proposito.
        raise DescargaIncompleta(f"se bajaron {hecho} de {total} bytes")

    if sha256 is not None and _sha256(parcial) != sha256:
        parcial.unlink(missing_ok=True)
        destino.unlink(missing_ok=True)
        raise HashInvalido(f"el hash de {destino.name} no cuadra; se borro el archivo")

    os.replace(parcial, destino)
    return destino


# --- Artefactos que no caben en el instalador -------------------------------


@dataclass(frozen=True)
class Artefacto:
    """Algo pesado que vive en GitHub Releases y se baja bajo demanda."""

    nombre: str          # lo que ve el usuario en la barra de progreso
    archivo: str         # nombre del asset en el release
    sha256: str          # 64 hex; vacio = todavia sin publicar (ver publicar_artefactos)
    destino_rel: str     # a donde va, relativo al directorio de datos
    tag: str = "v2.0.0"

    @property
    def url(self) -> str:
        return f"https://github.com/{GITHUB_REPO}/releases/download/{self.tag}/{self.archivo}"


# Los hashes se rellenan al publicar el release (tools/publicar_artefactos.py).
# Vacio significa "todavia no publicado": descargar_artefacto lo dice claro en
# vez de bajarse 1.4 GB sin poder verificarlos.
CUDA = Artefacto(
    nombre="paquete de aceleracion NVIDIA",
    archivo="flowlibre-cuda-2.0.0.zip",
    sha256="bd9c0f6010c9db1bc8c8f5ea5afc8b06bb55977a3b87d61ad65aa8b58aa256cf",
    destino_rel="cuda/flowlibre-cuda.zip",
)

MODELO_INT8 = Artefacto(
    nombre="modelo de transcripcion (int8)",
    archivo="large-v3-turbo-int8.zip",
    sha256="76c637f846fc0128dfffc6978d1aeeff401944437a4446c4dc13ee0a39728574",
    destino_rel="models/large-v3-turbo-int8.zip",
)


def descargar_artefacto(art: Artefacto, on_progress=None) -> Path:
    """Baja un artefacto al directorio de datos del usuario."""
    if not art.sha256:
        raise DescargaError(
            f"{art.nombre}: no hay hash publicado todavia. Corre "
            f"tools/publicar_artefactos.py al crear el release."
        )
    return descargar(art.url, paths.data_dir() / art.destino_rel,
                     sha256=art.sha256, on_progress=on_progress)


def cuda_dir() -> Path:
    """Donde quedan las DLLs de CUDA una vez descomprimidas."""
    return paths.data_dir() / "cuda" / "bin"


def cuda_instalado() -> bool:
    """True si hay DLLs de CUDA utilizables en el directorio de datos.

    Se pregunta por un .dll de verdad y no por la carpeta: una descarga a medias
    o un descomprimido interrumpido dejan la carpeta creada y vacia, y darla por
    buena manda a la app a cargar CUDA que no existe.
    """
    d = cuda_dir()
    return d.is_dir() and any(d.glob("*.dll"))


def instalar_cuda(on_progress=None) -> Path:
    """Baja y descomprime el paquete de CUDA. Idempotente."""
    if cuda_instalado():
        return cuda_dir()
    zip_path = descargar_artefacto(CUDA, on_progress=on_progress)
    destino = paths.data_dir() / "cuda"
    # A una carpeta temporal y luego un rename: si el descomprimido se corta a
    # la mitad, cuda_instalado() no puede ver una instalacion a medias.
    tmp = destino.with_name("cuda.descomprimiendo")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp)
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    os.replace(tmp, destino)
    zip_path.unlink(missing_ok=True)     # 1.4 GB que ya no sirven de nada
    return cuda_dir()
