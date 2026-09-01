"""Guarda del aislamiento: si el fixture de conftest se cae, esto lo grita."""

from pathlib import Path

from flowlibre import hotkey


def test_los_tests_no_escriben_en_el_debug_log_real():
    real = Path(hotkey.__file__).resolve().parent.parent / "debug.log"
    assert hotkey.DEBUG_LOG != real


def test_dbg_escribe_en_el_log_aislado():
    hotkey._dbg("prueba")
    assert "prueba" in hotkey.DEBUG_LOG.read_text(encoding="utf-8")
