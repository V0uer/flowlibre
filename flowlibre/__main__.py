"""Entry point: python -m flowlibre"""

from __future__ import annotations

from .app import FlowLibreApp
from .tray import Tray


def main() -> None:
    print("FlowLibre iniciando…")
    app = FlowLibreApp()
    app.start()
    print(f"Listo. Atajo: {app.config.hotkey} ({app.config.hotkey_mode}). "
          f"Motor: {app.config.engine}. Ícono en la bandeja del sistema.")
    Tray(app).run()


if __name__ == "__main__":
    main()
