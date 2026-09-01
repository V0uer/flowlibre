"""El wizard solo tiene una oportunidad: el primer arranque de una instalacion.

Aqui se prueba la logica, no los pixeles. Lo que se puede romper en silencio es
el **orden** (ver test_el_orden_importa) y el destino de la API key: si acaba en
config.yaml, se filtra el dia que alguien mande su config para reportar un
problema.
"""

from __future__ import annotations

import pytest

from flowlibre import paths, wizard


@pytest.fixture
def instalada(tmp_path, monkeypatch):
    """Simula una instalacion limpia: recursos por un lado, datos vacios por otro."""
    recursos = tmp_path / "programa"
    datos = tmp_path / "datos"
    recursos.mkdir()
    datos.mkdir()
    (recursos / "config.yaml").write_text("hotkey: ctrl+alt+space\n", encoding="utf-8")
    monkeypatch.setattr(paths, "resource_dir", lambda: recursos)
    monkeypatch.setattr(paths, "data_dir", lambda: datos)
    monkeypatch.setattr(wizard.paths, "data_dir", lambda: datos)
    return recursos, datos


def test_hace_falta_cuando_no_hay_config(instalada):
    assert wizard.necesita_wizard() is True


def test_no_hace_falta_si_ya_hay_config(instalada):
    _, datos = instalada
    (datos / "config.yaml").write_text("hotkey: f9\n", encoding="utf-8")
    assert wizard.necesita_wizard() is False


def test_el_orden_importa_sembrar_antes_de_preguntar_lo_apagaria(instalada):
    """sembrar() copia el config.yaml de la instalacion a los datos del usuario.
    Si se pregunta DESPUES, la respuesta es siempre 'no hace falta' y el wizard
    no se ejecuta nunca en ninguna maquina. El bug no da sintoma: la app abre
    perfecta y el usuario simplemente nunca ve la bienvenida."""
    _, datos = instalada
    hace_falta = wizard.preparar_datos()
    assert hace_falta is True, "se sembro antes de preguntar"
    assert (datos / "config.yaml").exists(), "no sembro"


def test_segunda_vez_ya_no_hace_falta(instalada):
    wizard.preparar_datos()
    assert wizard.preparar_datos() is False


# --- API key ----------------------------------------------------------------


def test_la_api_key_va_a_variable_de_entorno_no_a_config(instalada, monkeypatch):
    _, datos = instalada
    llamadas = []
    monkeypatch.setattr(wizard.subprocess, "run", lambda *a, **k: llamadas.append(a))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    wizard.guardar_api_key("  sk-ant-secreta  ")

    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-secreta", "no sirve en esta sesion"
    assert llamadas, "no la persistio para los proximos arranques"
    assert "setx" in llamadas[0][0][0]
    cfg = (datos / "config.yaml")
    assert not cfg.exists() or "sk-ant" not in cfg.read_text(encoding="utf-8"), \
        "la key acabo en un archivo que la gente comparte al reportar problemas"


def test_key_vacia_no_persiste_nada(instalada, monkeypatch):
    llamadas = []
    monkeypatch.setattr(wizard.subprocess, "run", lambda *a, **k: llamadas.append(a))
    wizard.guardar_api_key("   ")
    assert llamadas == [], "guardo una key vacia y dejo la variable puesta en blanco"


# --- perfil de la maquina ---------------------------------------------------


def test_el_paso_del_modelo_pide_lo_que_la_maquina_puede_usar(monkeypatch):
    monkeypatch.setattr(wizard.gpu, "detectar_nvidia", lambda: True)
    plan = wizard.plan_de_modelo()
    assert plan["acelerada"] is True
    assert plan["descarga"] is not None, "con NVIDIA hay que bajar CUDA y el int8"

    monkeypatch.setattr(wizard.gpu, "detectar_nvidia", lambda: False)
    plan = wizard.plan_de_modelo()
    assert plan["acelerada"] is False
    assert plan["descarga"] is None, "sin NVIDIA no tiene caso bajar 1.4 GB"
    assert plan["whisper_model"] == "small"
