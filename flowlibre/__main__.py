"""Entry point: python -m flowlibre"""

from __future__ import annotations

from . import wizard
from .app import FlowLibreApp
from .tray import Tray


def main() -> None:
    print("FlowLibre iniciando…")
    # Instalada, los datos del usuario viven en %APPDATA% y la primera vez están
    # vacíos: se siembran desde la copia que trae la instalación. Corriendo desde
    # el código esto no hace nada (origen y destino son la misma carpeta).
    # OJO con el orden: preparar_datos() pregunta ANTES de sembrar. Al reves,
    # el config.yaml recien sembrado haria creer que la maquina ya estaba
    # configurada y el wizard no correria nunca (ver wizard.preparar_datos).
    primera_vez = wizard.preparar_datos()
    app = FlowLibreApp()
    app.start()
    if primera_vez:
        app.abrir_wizard()
    print(f"Listo. Atajo: {app.config.hotkey} ({app.config.hotkey_mode}). "
          f"Motor: {app.config.engine}. Ícono en la bandeja del sistema.")
    Tray(app).run()


if __name__ == "__main__":
    main()
