"""El chequeo de actualizacion es codigo que corre en CADA arranque de CADA
usuario y que no puede, bajo ninguna circunstancia, impedir que la app abra.

Por eso casi todos estos tests son sobre lo que pasa cuando algo sale mal:
GitHub caido, respuesta basura, sin internet, un tag que no parece version. La
respuesta correcta siempre es la misma: no hay actualizacion, y la app sigue.
"""

from __future__ import annotations

import pytest

from flowlibre import actualizacion


def _release(tag, assets=("FlowLibre-Setup-9.9.9.exe",)):
    return {"tag_name": tag, "html_url": "https://x/y",
            "assets": [{"name": n, "browser_download_url": f"https://x/{n}",
                        "size": 123} for n in assets]}


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_hay_version_nueva(monkeypatch):
    monkeypatch.setattr(actualizacion, "__version__", "2.0.0")
    monkeypatch.setattr(actualizacion.requests, "get", lambda *a, **k: _Resp(_release("v2.1.0")))
    novedad = actualizacion.buscar_actualizacion()
    assert novedad is not None
    assert novedad.version == "2.1.0"


def test_la_misma_version_no_es_novedad(monkeypatch):
    """El bug clasico: el tag trae 'v' y __version__ no. Comparados como texto,
    'v2.0.0' != '2.0.0' y la app se ofrece actualizar a la version que ya tiene,
    en cada arranque, para siempre."""
    monkeypatch.setattr(actualizacion, "__version__", "2.0.0")
    monkeypatch.setattr(actualizacion.requests, "get", lambda *a, **k: _Resp(_release("v2.0.0")))
    assert actualizacion.buscar_actualizacion() is None


def test_no_ofrece_bajar_de_version(monkeypatch):
    monkeypatch.setattr(actualizacion, "__version__", "2.3.0")
    monkeypatch.setattr(actualizacion.requests, "get", lambda *a, **k: _Resp(_release("v2.1.0")))
    assert actualizacion.buscar_actualizacion() is None


def test_compara_por_numero_no_por_texto(monkeypatch):
    """Como texto, '2.10.0' < '2.9.0'. Como version, es al reves."""
    monkeypatch.setattr(actualizacion, "__version__", "2.9.0")
    monkeypatch.setattr(actualizacion.requests, "get", lambda *a, **k: _Resp(_release("v2.10.0")))
    novedad = actualizacion.buscar_actualizacion()
    assert novedad is not None and novedad.version == "2.10.0"


@pytest.mark.parametrize("desastre", [
    lambda *a, **k: (_ for _ in ()).throw(ConnectionError("sin internet")),
    lambda *a, **k: _Resp({}, 500),
    lambda *a, **k: _Resp({"tag_name": "ultima"}),          # tag que no es version
    lambda *a, **k: _Resp({"tag_name": "v2.1.0"}),          # release sin assets
    lambda *a, **k: _Resp("no soy un dict"),
])
def test_nada_de_esto_puede_tumbar_el_arranque(monkeypatch, desastre):
    monkeypatch.setattr(actualizacion, "__version__", "2.0.0")
    monkeypatch.setattr(actualizacion.requests, "get", desastre)
    assert actualizacion.buscar_actualizacion() is None


def test_el_interruptor_apagado_ni_siquiera_llama_a_github(monkeypatch):
    llamadas = []
    monkeypatch.setattr(actualizacion.requests, "get", lambda *a, **k: llamadas.append(a))

    class Cfg:
        auto_update = False

    assert actualizacion.chequear_si_toca(Cfg()) is None
    assert llamadas == [], "chequeo la red con el auto-update apagado"


def test_elige_el_instalador_no_cualquier_asset(monkeypatch):
    monkeypatch.setattr(actualizacion, "__version__", "2.0.0")
    rel = _release("v2.1.0", assets=("codigo.zip", "FlowLibre-Setup-2.1.0.exe", "notas.txt"))
    monkeypatch.setattr(actualizacion.requests, "get", lambda *a, **k: _Resp(rel))
    novedad = actualizacion.buscar_actualizacion()
    assert novedad.instalador.endswith("FlowLibre-Setup-2.1.0.exe")
