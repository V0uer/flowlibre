"""Empaqueta lo pesado y deja sus hashes escritos en flowlibre/descargas.py.

    .venv/Scripts/python.exe tools/publicar_artefactos.py

Produce dos .zip en packaging/salida/ que se suben a mano como assets del
release, y **reescribe los sha256 en descargas.py**. Ese ultimo paso no es
opcional: descargar_artefacto() se niega a bajar 1.4 GB que no puede verificar,
asi que un release publicado sin correr esto deja la app sin poder acelerarse y
con un mensaje que dice exactamente que falto.

Que empaqueta, y por que estos dos:

- **CUDA** — las DLLs de cuBLAS/cuDNN que salen de los paquetes pip nvidia-*.
  1.94 GB instalados; comprimidos caben en el limite de 2 GB por asset de
  GitHub. Son las que el instalador excluye a proposito.
- **El modelo int8** — es un artefacto nuestro: lo produce tools/, no existe en
  Hugging Face. Pesa 0.82 GB contra 1.6 GB del fp16, con el mismo texto y la
  misma velocidad. Los modelos estandar (small, large-v3-turbo) NO van aqui: ya
  estan en Hugging Face y faster-whisper los baja solo.
"""

from __future__ import annotations

import hashlib
import re
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "packaging" / "salida"
sys.path.insert(0, str(RAIZ))

from flowlibre import __version__      # noqa: E402


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _zip(destino: Path, pares: list[tuple[Path, str]]) -> Path:
    """Comprime (ruta_real, nombre_dentro_del_zip). ZIP_DEFLATED, no STORED:
    las DLLs comprimen bien y cada 100 MB de menos son 100 MB que no se le bajan
    a cada usuario con NVIDIA."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for real, dentro in pares:
            z.write(real, dentro)
    return destino


def empaquetar_cuda() -> Path | None:
    """Todas las DLLs de los paquetes nvidia-* del venv, aplanadas en bin/.

    Aplanadas a proposito: flowlibre/descargas.cuda_dir() apunta a
    %APPDATA%/FlowLibre/cuda/bin y registra ESA carpeta en el buscador de DLLs.
    Conservar el arbol de nvidia/<paquete>/bin obligaria a registrar N rutas y
    a adivinar cuales.
    """
    pares: list[tuple[Path, str]] = []
    for sp in sys.path:
        nvidia = Path(sp) / "nvidia"
        if not nvidia.is_dir():
            continue
        for sub in nvidia.iterdir():
            for dll in (sub / "bin").glob("*.dll"):
                pares.append((dll, f"bin/{dll.name}"))
    if not pares:
        print("  ! No hay paquetes nvidia-* en este venv. Nada que empaquetar.")
        return None
    print(f"  {len(pares)} DLLs")
    return _zip(SALIDA / f"flowlibre-cuda-{__version__}.zip", pares)


def empaquetar_modelo() -> Path | None:
    modelo = RAIZ / "models" / "large-v3-turbo-int8"
    if not modelo.is_dir():
        print(f"  ! No existe {modelo}. Corre el conversor primero.")
        return None
    pares = [(f, str(f.relative_to(modelo))) for f in modelo.rglob("*") if f.is_file()]
    print(f"  {len(pares)} archivos")
    return _zip(SALIDA / "large-v3-turbo-int8.zip", pares)


def escribir_hash(nombre_constante: str, valor: str) -> None:
    """Reemplaza el sha256 de una constante de descargas.py, en el lugar."""
    p = RAIZ / "flowlibre" / "descargas.py"
    texto = p.read_text(encoding="utf-8")
    patron = re.compile(
        rf"({nombre_constante}\s*=\s*Artefacto\((?:[^()]|\([^()]*\))*?sha256=)\"[^\"]*\"",
        re.S,
    )
    nuevo, n = patron.subn(rf'\g<1>"{valor}"', texto)
    if n != 1:
        raise SystemExit(f"No se pudo escribir el hash de {nombre_constante} "
                         f"(coincidencias: {n}). Revisa descargas.py a mano.")
    p.write_text(nuevo, encoding="utf-8")


def main() -> None:
    print(f"FlowLibre {__version__} — empaquetando artefactos del release\n")
    for etiqueta, constante, fn in (
        ("CUDA", "CUDA", empaquetar_cuda),
        ("modelo int8", "MODELO_INT8", empaquetar_modelo),
    ):
        print(f"{etiqueta}:")
        ruta = fn()
        if ruta is None:
            continue
        h = sha256(ruta)
        escribir_hash(constante, h)
        mb = ruta.stat().st_size / (1 << 20)
        print(f"  {ruta.name}  {mb:.0f} MB\n  sha256 {h}\n")

    print("Listo. Falta:")
    print("  1. Subir los .zip de packaging/salida/ como assets del release.")
    print("  2. Commitear descargas.py con los hashes nuevos.")
    print("  Sin el paso 2 la app se niega a bajarlos, y lo dice en el mensaje.")


if __name__ == "__main__":
    main()
