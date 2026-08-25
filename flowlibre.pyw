# Launcher sin consola (usado por el auto-inicio de Windows).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flowlibre.__main__ import main

main()
