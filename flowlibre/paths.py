"""Dónde vive cada cosa según cómo esté corriendo la app.

Hay dos mundos y no se pueden confundir:

- **Desde el código** (lo de hoy, `D:\\FlowLibre`): todo junto, como siempre.
- **Instalada**: el programa vive en una carpeta que es de solo lectura para el
  usuario, y que la próxima actualización va a reemplazar entera. Los datos del
  usuario —configuración, historial, diccionario, comandos— **no pueden estar
  ahí**: se van a `%APPDATA%\\FlowLibre`, que sobrevive a las actualizaciones.

El historial de dictados es lo más valioso que guarda la app y lo único
imposible de reconstruir. Por eso `sembrar()` copia y nunca mueve, y nunca
sobrescribe algo que ya exista.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Lo que se lleva de la instalación a los datos del usuario en el primer arranque.
SEMILLAS = ("config.yaml", "dictionary.txt", "commands.json", "history.jsonl")


def esta_empaquetada() -> bool:
    """True cuando corre como .exe de PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    """Carpeta escribible con los datos del usuario. La crea si hace falta."""
    if not esta_empaquetada():
        return ROOT
    appdata = os.environ.get("APPDATA")
    destino = Path(appdata) / "FlowLibre" if appdata else Path.home() / ".flowlibre"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def resource_dir() -> Path:
    """Carpeta de solo lectura con lo que viene dentro del paquete.

    PyInstaller en modo onefile descomprime en `sys._MEIPASS`; en onedir los
    archivos quedan junto al ejecutable.
    """
    if not esta_empaquetada():
        return ROOT
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else Path(sys.executable).resolve().parent


def sembrar(origen: Path | None = None, destino: Path | None = None) -> list[str]:
    """Copia al directorio de datos lo que falte. Devuelve qué copió.

    Se llama en cada arranque, así que la regla de oro es **no pisar nada**: si
    el archivo ya existe del lado del usuario, se respeta tal cual. Copiar y no
    mover deja el original como respaldo si la migración sale mal.
    """
    origen = origen if origen is not None else resource_dir()
    destino = destino if destino is not None else data_dir()
    if origen == destino:
        return []
    copiados = []
    for nombre in SEMILLAS:
        src, dst = origen / nombre, destino / nombre
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            copiados.append(nombre)
    return copiados
