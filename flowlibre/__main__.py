"""Entry point: python -m flowlibre"""

from __future__ import annotations

from . import paths
from .app import FlowLibreApp
from .tray import Tray


def main() -> None:
    print("FlowLibre iniciando…")
    # Instalada, los datos del usuario viven en %APPDATA% y la primera vez están
    # vacíos: se siembran desde la copia que trae la instalación. Corriendo desde
    # el código esto no hace nada (origen y destino son la misma carpeta).
    sembrados = paths.sembrar()
    if sembrados:
        print(f"Datos iniciales copiados a {paths.data_dir()}: {', '.join(sembrados)}")
    app = FlowLibreApp()
    app.start()
    print(f"Listo. Atajo: {app.config.hotkey} ({app.config.hotkey_mode}). "
          f"Motor: {app.config.engine}. Ícono en la bandeja del sistema.")
    Tray(app).run()


if __name__ == "__main__":
    main()
