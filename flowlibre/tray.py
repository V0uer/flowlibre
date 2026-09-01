"""Ícono en la bandeja del sistema con pystray.

Menú: activar/desactivar, modo de formato, motor A/B, abrir config,
ver historial, iniciar con Windows, salir. El ícono cambia de color al grabar.
"""

from __future__ import annotations

import os

import pystray
from PIL import Image, ImageDraw

from . import autostart
from .config import CONFIG_PATH, HISTORY_PATH
from .iconos import ICONOS_DIR

COLORS = {
    "listo": (70, 130, 240),       # azul
    "grabando": (230, 60, 60),     # rojo
    "procesando": (240, 180, 40),  # ámbar
    "apagado": (120, 120, 120),    # gris
}

FORMAT_MODES = ["mensaje", "email", "notas", "crudo"]
ENGINES = [("ollama", "Motor A — Ollama (local)"), ("claude", "Motor B — Claude (API)")]


def _icono_dibujado(color: tuple[int, int, int]) -> Image.Image:
    """Respaldo: el micrófono a mano de siempre, por si faltan los assets.

    Quedarse sin ícono de bandeja no es un problema estético: la bandeja es la
    única forma de abrir el panel y de salir de la app.
    """
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 56, 56], fill=color + (255,))
    # silueta simple de micrófono
    d.rounded_rectangle([27, 18, 37, 38], radius=5, fill=(255, 255, 255, 255))
    d.line([32, 40, 32, 47], fill=(255, 255, 255, 255), width=3)
    d.line([25, 47, 39, 47], fill=(255, 255, 255, 255), width=3)
    return img


def _make_icon(estado: str) -> Image.Image:
    """La marca de FlowLibre del color del estado (ver tools/make_icons.py)."""
    png = ICONOS_DIR / f"tray-{estado}.png"
    try:
        with Image.open(png) as img:
            return img.convert("RGBA")
    except OSError:
        return _icono_dibujado(COLORS.get(estado, COLORS["listo"]))


class Tray:
    def __init__(self, app) -> None:
        self.app = app
        self.icon = pystray.Icon(
            "FlowLibre", _make_icon("listo"), "FlowLibre — listo",
            menu=self._build_menu(),
        )
        app.on_status_change = self._on_status

    # --- estado visual ---

    def _on_status(self, status: str) -> None:
        if not self.app.enabled:
            status = "apagado"
        self.icon.icon = _make_icon(status)
        self.icon.title = f"FlowLibre — {status}"

    # --- menú ---

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                "Abrir FlowLibre", lambda: self.app.open_dashboard(),
                default=True,  # doble clic al ícono abre el panel
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Activado", self._toggle_enabled,
                checked=lambda item: self.app.enabled,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Modo de formato", pystray.Menu(*[
                pystray.MenuItem(
                    mode, self._make_mode_setter(mode),
                    checked=self._make_mode_checker(mode), radio=True,
                ) for mode in FORMAT_MODES
            ])),
            pystray.MenuItem("Motor de limpieza", pystray.Menu(*[
                pystray.MenuItem(
                    label, self._make_engine_setter(engine),
                    checked=self._make_engine_checker(engine), radio=True,
                ) for engine, label in ENGINES
            ])),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Abrir config.yaml", lambda: os.startfile(CONFIG_PATH)),
            pystray.MenuItem("Ver historial", self._open_history),
            pystray.MenuItem("Recargar configuración", lambda: self.app.reload_config()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Iniciar con Windows", self._toggle_autostart,
                checked=lambda item: autostart.is_enabled(),
            ),
            pystray.MenuItem(
                "Buscar actualizaciones al arrancar", self._toggle_auto_update,
                checked=lambda item: self.app.config.auto_update,
            ),
            # visible=... hace que el aviso solo aparezca cuando hay algo que
            # ofrecer. Un menú con "Actualizar a None" es peor que ninguno.
            pystray.MenuItem(
                self._texto_actualizacion, self._instalar_actualizacion,
                visible=lambda item: self.app.actualizacion is not None,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self._quit),
        )

    def _toggle_enabled(self) -> None:
        self.app.enabled = not self.app.enabled
        self._on_status(self.app.status)

    def _make_mode_setter(self, mode):
        return lambda: self.app.config.set("format_mode", mode)

    def _make_mode_checker(self, mode):
        return lambda item: self.app.config.format_mode == mode

    def _make_engine_setter(self, engine):
        return lambda: self.app.config.set("engine", engine)

    def _make_engine_checker(self, engine):
        return lambda item: self.app.config.engine == engine

    def _open_history(self) -> None:
        if not HISTORY_PATH.exists():
            HISTORY_PATH.touch()
        os.startfile(HISTORY_PATH)

    def _toggle_autostart(self) -> None:
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()

    def _texto_actualizacion(self, item=None) -> str:
        nov = self.app.actualizacion
        if nov is None:
            return "Actualizar"
        if self.app.actualizacion_lista:
            return f"Instalar la versión {nov.version} y reiniciar"
        return f"Descargando la versión {nov.version}…"

    def _instalar_actualizacion(self) -> None:
        """Solo hace algo cuando el instalador ya está en disco."""
        from . import actualizacion

        ruta = self.app.actualizacion_lista
        if not ruta:
            return
        self.app.shutdown()
        self.icon.stop()
        actualizacion.aplicar(ruta)

    def _toggle_auto_update(self) -> None:
        self.app.config.set("auto_update", not self.app.config.auto_update)

    def _quit(self) -> None:
        self.app.shutdown()
        self.icon.stop()

    def run(self) -> None:
        """Bloquea el hilo principal con el loop del tray."""
        self.icon.run()
