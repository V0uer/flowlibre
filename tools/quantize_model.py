"""Convierte el modelo de Whisper a int8 y lo deja en models/.

En disco el modelo turbo pesa 1.6 GB en fp16. En ejecucion ya se usa
int8_float16, o sea que se cuantiza al cargar de todos modos: guardarlo ya
cuantizado ahorra ~800 MB sin cambiar nada de la calidad.

Uso:  .venv/Scripts/python.exe tools/quantize_model.py
      .venv/Scripts/python.exe tools/quantize_model.py --forzar   (rehace la conversion)

Necesita `transformers` Y `torch`, que NO son dependencias de runtime (faster-whisper
no usa ninguna de las dos). OJO: `pip install torch` en Windows baja la rueda con CUDA,
~2.5 GB, mas de lo que esta herramienta pretende ahorrar. Usar la de CPU:

      .venv/Scripts/python.exe -m pip install transformers
      .venv/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu

Y desinstalarlas al terminar (junto con sus huerfanos: sympy, networkx, jinja2,
mpmath, MarkupSafe):

      .venv/Scripts/python.exe -m pip uninstall -y torch transformers sympy networkx jinja2 mpmath MarkupSafe
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESTINO = ROOT / "models" / "large-v3-turbo-int8"
ORIGEN = "openai/whisper-large-v3-turbo"


def _completo(destino: Path) -> bool:
    """Una conversion a medias deja la carpeta creada pero sin pesos.

    Importa porque la descarga son ~1.6 GB: si se corta a media, la carpeta
    existe, este script se saldria diciendo "ya existe", y la app cargaria una
    ruta valida sin modelo adentro.
    """
    return (destino / "model.bin").exists()


def main() -> None:
    forzar = "--forzar" in sys.argv[1:]
    if _completo(DESTINO) and not forzar:
        total = sum(f.stat().st_size for f in DESTINO.rglob("*") if f.is_file())
        print(f"Ya existe y esta completo: {DESTINO} ({total / 1e9:.2f} GB)")
        return
    if DESTINO.exists():
        print(f"Limpiando conversion incompleta o previa en {DESTINO}")
        shutil.rmtree(DESTINO)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    print(f"Convirtiendo {ORIGEN} a int8 -> {DESTINO}")
    subprocess.run(
        [sys.executable, "-m", "ctranslate2.converters.transformers",
         "--model", ORIGEN,
         "--output_dir", str(DESTINO),
         "--copy_files", "tokenizer.json", "preprocessor_config.json",
         "--quantization", "int8"],
        check=True,
    )
    total = sum(f.stat().st_size for f in DESTINO.rglob("*") if f.is_file())
    print(f"Listo: {total / 1e9:.2f} GB en {DESTINO}")


if __name__ == "__main__":
    main()
