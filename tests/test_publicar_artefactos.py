"""El paso que se olvida: escribir los hashes de vuelta en descargas.py.

Si la expresion regular deja de coincidir (porque alguien reordena los campos
del Artefacto, por ejemplo), el script publica los .zip y no avisa que no
escribio nada. El release queda con artefactos que la app se niega a bajar.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _cargar():
    spec = importlib.util.spec_from_file_location(
        "publicar_artefactos", RAIZ / "tools" / "publicar_artefactos.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_escribe_el_hash_de_cada_artefacto(tmp_path, monkeypatch):
    mod = _cargar()
    copia = tmp_path / "flowlibre"
    copia.mkdir()
    original = (RAIZ / "flowlibre" / "descargas.py").read_text(encoding="utf-8")
    (copia / "descargas.py").write_text(original, encoding="utf-8")
    monkeypatch.setattr(mod, "RAIZ", tmp_path)

    mod.escribir_hash("CUDA", "aa" * 32)
    mod.escribir_hash("MODELO_INT8", "bb" * 32)

    texto = (copia / "descargas.py").read_text(encoding="utf-8")
    assert f'sha256="{"aa" * 32}"' in texto
    assert f'sha256="{"bb" * 32}"' in texto


def test_falla_ruidosamente_si_ya_no_coincide(tmp_path, monkeypatch):
    mod = _cargar()
    copia = tmp_path / "flowlibre"
    copia.mkdir()
    (copia / "descargas.py").write_text("# aqui ya no hay Artefactos\n", encoding="utf-8")
    monkeypatch.setattr(mod, "RAIZ", tmp_path)
    with pytest.raises(SystemExit):
        mod.escribir_hash("CUDA", "cc" * 32)
