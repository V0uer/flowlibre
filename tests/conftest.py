"""La suite no debe escribir en el debug.log de la app.

_dbg() escribe siempre en D:\FlowLibre\debug.log, que es el log real que el autor
lee para diagnosticar dictados. Correr los tests metia ahi lineas de mentira
("modelo caido", "rescatado del audio") entre los dictados de verdad, y ese log
es la unica evidencia que tenemos de como se comporta la app en uso real.
"""

import pytest

from flowlibre import hotkey


@pytest.fixture(autouse=True)
def _debug_log_aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(hotkey, "DEBUG_LOG", tmp_path / "debug.log")
