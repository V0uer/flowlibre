"""Chequeo de version nueva contra GitHub Releases.

Este codigo corre en **cada arranque de cada usuario**, antes de que nadie haya
dictado nada. La regla que manda sobre cualquier otra: **no puede impedir que la
app abra**. Sin internet, con GitHub caido, con una respuesta que no es JSON o
con un tag que alguien escribio a mano mal — la respuesta es siempre la misma,
"no hay actualizacion", y la app sigue su camino.

Se descarga en segundo plano y **se aplica al siguiente reinicio**, nunca a
media sesion: FlowLibre vive en la bandeja con un atajo global registrado, y
reemplazarse a si misma mientras alguien dicta es la peor forma posible de
enterarse de que habia una version nueva.

El repo es publico (decision del autor, 2026-09-01), asi que la API de releases
se consulta sin token y el instalador se baja con un link directo.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import requests

from . import paths
from . import __version__
from .descargas import GITHUB_REPO, descargar

API_ULTIMO = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
TIMEOUT_S = 6           # corto a proposito: esto no puede demorar un arranque


@dataclass(frozen=True)
class Novedad:
    version: str
    instalador: str      # URL del .exe
    notas_url: str
    tamano: int = 0


def _a_numeros(texto: str) -> tuple[int, ...] | None:
    """'v2.10.0' -> (2, 10, 0). Cualquier otra cosa -> None.

    Comparar versiones como texto dice que '2.10.0' < '2.9.0', que es al reves
    de la verdad. Y el tag trae 'v' delante mientras __version__ no: comparados
    crudos nunca son iguales, y la app se ofreceria actualizar a la version que
    ya tiene, en cada arranque, para siempre.
    """
    partes = str(texto).lstrip("vV").split(".")
    if len(partes) != 3:
        return None
    try:
        return tuple(int(p) for p in partes)
    except ValueError:
        return None


def buscar_actualizacion() -> Novedad | None:
    """La version publicada, si es mas nueva que esta. Nunca lanza."""
    try:
        resp = requests.get(API_ULTIMO, timeout=TIMEOUT_S,
                            headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        datos = resp.json()
        if not isinstance(datos, dict):
            return None

        publicada = _a_numeros(datos.get("tag_name", ""))
        actual = _a_numeros(__version__)
        if publicada is None or actual is None or publicada <= actual:
            return None

        instalador = next(
            (a for a in datos.get("assets", []) or []
             if str(a.get("name", "")).lower().endswith(".exe")),
            None,
        )
        if not instalador:
            # Un release sin instalador no sirve de nada al usuario final.
            return None

        return Novedad(
            version=".".join(str(n) for n in publicada),
            instalador=instalador["browser_download_url"],
            notas_url=datos.get("html_url", ""),
            tamano=int(instalador.get("size") or 0),
        )
    except Exception:
        # Deliberadamente ancho. Cualquier fallo aqui significa "hoy no", nunca
        # "la app no abre".
        return None


def chequear_si_toca(config) -> Novedad | None:
    """Respeta el interruptor de Ajustes antes de tocar la red."""
    if not getattr(config, "auto_update", True):
        return None
    return buscar_actualizacion()


def carpeta_descargas() -> Path:
    return paths.data_dir() / "actualizaciones"


def descargar_en_segundo_plano(novedad: Novedad, al_terminar=None) -> threading.Thread:
    """Baja el instalador sin bloquear nada. `al_terminar(ruta | None)`.

    Sin hash: GitHub no publica uno por asset. Lo que si se verifica es el
    tamano que la API declara, que caza el caso real (descarga truncada) sin
    inventar una garantia criptografica que no tenemos.
    """
    destino = carpeta_descargas() / f"FlowLibre-Setup-{novedad.version}.exe"

    def trabajo() -> None:
        ruta = None
        try:
            ruta = descargar(novedad.instalador, destino)
            if novedad.tamano and ruta.stat().st_size != novedad.tamano:
                ruta.unlink(missing_ok=True)
                ruta = None
        except Exception as e:
            print(f"[FlowLibre] No se pudo bajar la actualizacion: {e}")
            ruta = None
        if al_terminar:
            al_terminar(ruta)

    h = threading.Thread(target=trabajo, daemon=True)
    h.start()
    return h


def aplicar(instalador: Path) -> None:
    """Lanza el instalador en silencio y cierra la app.

    Solo se llama cuando el usuario lo pide desde la bandeja. `/SILENT` con
    `/CLOSEAPPLICATIONS`: Inno Setup no puede sobreescribir el .exe mientras
    corre, y sin esto la actualizacion falla a la mitad dejando una instalacion
    incompleta.
    """
    import subprocess
    import sys

    subprocess.Popen([str(instalador), "/SILENT", "/CLOSEAPPLICATIONS",
                      "/RESTARTAPPLICATIONS"], close_fds=True)
    sys.exit(0)
