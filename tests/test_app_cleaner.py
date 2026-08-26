"""Regresión: el menú de la bandeja cambia config.engine sin pasar por
reload_config() (ver flowlibre/tray.py: _make_engine_setter usa
Config.set(), que solo reescribe el YAML). _get_cleaner() debe notar el
cambio de motor por sí solo, o el dictado se queda pegado al motor viejo
hasta reiniciar la app."""

import types

from flowlibre.app import FlowLibreApp


class _FakeConfig:
    def __init__(self, engine):
        self.engine = engine


def _make_fake_app(engine):
    """Objeto mínimo con la forma que _get_cleaner()/_close_cleaner() esperan
    de self, sin construir FlowLibreApp completo (que abre audio/GUI/hotkeys)."""
    ns = types.SimpleNamespace()
    ns.config = _FakeConfig(engine)
    ns.cleaner = None
    ns._get_cleaner = types.MethodType(FlowLibreApp._get_cleaner, ns)
    ns._close_cleaner = types.MethodType(FlowLibreApp._close_cleaner, ns)
    return ns


def test_get_cleaner_se_reconstruye_al_cambiar_engine_sin_reload_config():
    fake = _make_fake_app("ollama")
    first = fake._get_cleaner()
    assert first.name == "ollama"

    # Simula lo que hace el menú de la bandeja: mutar config.engine directo.
    fake.config.engine = "claude"
    second = fake._get_cleaner()

    assert second.name == "claude"
    assert second is not first


def test_get_cleaner_reutiliza_el_mismo_objeto_si_no_cambia_el_motor():
    fake = _make_fake_app("ollama")
    first = fake._get_cleaner()
    second = fake._get_cleaner()
    assert first is second
