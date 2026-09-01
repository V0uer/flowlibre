# -*- mode: python ; coding: utf-8 -*-
"""Bundle de FlowLibre para Windows, SIN CUDA.

    .venv/Scripts/python.exe -m PyInstaller packaging/flowlibre.spec --noconfirm

El punto de este archivo son las **exclusiones**. Las libs de NVIDIA pesan
1.94 GB de los ~2.4 GB del venv: meterlas en el instalador es justo lo que la
seccion 7 del spec quiere evitar. El paquete de aceleracion se descarga despues,
y solo en maquinas que tengan una NVIDIA (ver flowlibre/gpu.py).

Modo onedir y no onefile: onefile descomprime todo a un temporal en cada
arranque, lo que en una app que vive en la bandeja y arranca con Windows se
siente como un segundo perdido cada vez, y ademas rompe la actualizacion
parcial.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

# La version vive en flowlibre/__init__.py y en ningun otro lado. Se deja aqui en
# disco para que el .iss la lea: Inno Setup no puede importar Python, y repetir
# el numero a mano ya nos tenia con el instalador en 2.0.0 y el paquete en 1.0.0
# — una app recien instalada que se cree vieja y se ofrece actualizar en bucle.
_ns = {}
exec((ROOT / "flowlibre" / "__init__.py").read_text(encoding="utf-8"), _ns)
VERSION = _ns["__version__"]
(Path(SPECPATH) / "VERSION").write_text(VERSION, encoding="utf-8")

datos = [
    (str(ROOT / "assets" / "icons"), "assets/icons"),
    (str(ROOT / "config.yaml"), "."),
    (str(ROOT / "commands.json"), "."),
    (str(ROOT / "dictionary.txt"), "."),
]

# Lo que NO va en el instalador base.
# OJO con `av` (PyAV, 67 MB): el spec lo daba por excluible porque FlowLibre le
# pasa el microfono a Whisper como array de numpy y nunca decodifica archivos.
# Es cierto sobre el USO y falso sobre el IMPORT: `faster_whisper/audio.py` hace
# `import av` al cargar el paquete. Excluirlo compila sin un error y produce una
# app que abre, se ve bien y **no transcribe nada** — muere en un hilo de fondo
# con ModuleNotFoundError. Verificado el 2026-08-31 con un build de consola.
# Si algun dia hay que recuperar esos 67 MB, el camino es un stub de `av`, con
# el riesgo de que cualquier version futura de faster-whisper lo rompa.
excluidos = [
    "torch", "transformers", "sympy", "networkx",   # herramientas de conversion
    "matplotlib", "pandas", "scipy", "IPython", "pytest", "setuptools", "pip",
]

a = Analysis(
    [str(ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datos,
    hiddenimports=["pystray._win32", "PIL._tkinter_finder", "flowlibre",
                   "flowlibre.app", "flowlibre.tray", "flowlibre.dashboard"],
    excludes=excluidos,
    noarchive=False,
)

# Las DLLs de CUDA/cuDNN entran como binarios arrastrados por ctranslate2, asi
# que no basta con `excludes` (que solo filtra modulos de Python): hay que
# sacarlas de la lista de binarios a mano. Son ~1.9 GB.
def _es_cuda(destino: str) -> bool:
    d = destino.lower()
    return (d.startswith("nvidia") or "cudnn" in d or "cublas" in d
            or "cudart" in d or "cufft" in d or "curand" in d)

a.binaries = [b for b in a.binaries if not _es_cuda(b[0])]
a.datas = [d for d in a.datas if not _es_cuda(d[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FlowLibre",
    console=False,                 # vive en la bandeja, sin consola negra
    icon=str(ROOT / "assets" / "icons" / "FlowLibre.ico"),
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="FlowLibre",
)
