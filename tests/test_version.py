"""La version vive en un solo lugar, y tres cosas la leen.

El chequeo de actualizacion compara __version__ contra el tag del ultimo
release. Si el instalador dice 2.0.0 y el paquete dice 1.0.0, la app recien
instalada se cree vieja y se ofrece actualizar a la version que YA tiene, en
bucle, en cada arranque. Nadie lo nota al construir: los dos numeros viven en
archivos distintos y ninguna prueba los junta. Esta si.
"""

from __future__ import annotations

import re
from pathlib import Path

import flowlibre

RAIZ = Path(__file__).resolve().parent.parent


def test_el_instalador_no_repite_el_numero_a_mano():
    """El .iss debe LEER la version, no llevar su propia copia."""
    iss = (RAIZ / "packaging" / "flowlibre.iss").read_text(encoding="utf-8", errors="ignore")
    assert not re.search(r'#define\s+Version\s+"\d', iss),         "el .iss volvio a tener el numero escrito a mano"
    assert "FileRead" in iss and "VERSION" in iss


def test_el_archivo_que_lee_el_instalador_cuadra_con_el_paquete():
    version_txt = RAIZ / "packaging" / "VERSION"
    if not version_txt.exists():
        return      # se genera al construir; en un clon limpio todavia no existe
    assert version_txt.read_text(encoding="utf-8").strip() == flowlibre.__version__


def test_la_version_es_semantica():
    assert re.fullmatch(r"\d+\.\d+\.\d+", flowlibre.__version__)
