"""Dónde viven los íconos de la app y cuál usa cada superficie.

Un solo lugar que sepa resolver las rutas: la bandeja, las ventanas y el
instalador los buscan distinto, y sin esto cada uno se inventa su ruta.
Los archivos los genera `tools/make_icons.py`.
"""

from __future__ import annotations

from pathlib import Path

ICONOS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


def ruta_icono_ventana(lado: int = 256) -> str | None:
    """PNG para `iconphoto` de tkinter (panel y barra de tareas).

    Devuelve None si falta: la app tiene que abrir igual, con el ícono de Tk,
    en vez de tronar al arrancar por un archivo decorativo.
    """
    png = ICONOS_DIR / f"FlowLibre-{lado}.png"
    return str(png) if png.exists() else None
