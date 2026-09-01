"""Lo que se le manda a un desconocido no puede ser la config del autor.

El bundle siembra un config.yaml en %APPDATA% la primera vez. Si ese archivo es
el de desarrollo, cada instalacion nace con el atajo del autor, su microfono
Elgato y una ruta a `models/large-v3-turbo-int8` que en otra maquina no existe.
Eso ultimo no es cosmetico: faster-whisper trata la ruta como repo_id de Hugging
Face, recibe un 401 y el hilo de carga muere en silencio (console=False).

Este test lo caza sin construir el bundle.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLA = RAIZ / "packaging" / "config.plantilla.yaml"


def test_el_spec_empaqueta_la_plantilla_y_no_el_config_real():
    spec = (RAIZ / "packaging" / "flowlibre.spec").read_text(encoding="utf-8")
    assert "config.plantilla.yaml" in spec
    assert not re.search(r'ROOT\s*/\s*"config\.yaml"', spec), \
        "el bundle volvio a llevarse el config.yaml de desarrollo"


def test_la_plantilla_no_apunta_a_un_modelo_que_solo_existe_aqui():
    datos = yaml.safe_load(PLANTILLA.read_text(encoding="utf-8"))
    modelo = str(datos["whisper_model"])
    assert "/" not in modelo and "\\" not in modelo, \
        f"la plantilla manda a HF una ruta local: {modelo}"


def test_la_plantilla_no_lleva_datos_personales():
    datos = yaml.safe_load(PLANTILLA.read_text(encoding="utf-8"))
    assert datos["microphone"] is None, "va el microfono de alguien mas"
    texto = PLANTILLA.read_text(encoding="utf-8")
    assert "Elgato" not in texto and "Wave Link" not in texto


def test_la_plantilla_es_valida_para_la_app():
    """Todas sus claves tienen que existir en DEFAULTS: Config ignora en silencio
    las que no conoce, asi que una llave mal escrita aqui es una opcion que el
    usuario cree haber puesto y que nunca se aplica."""
    from flowlibre.config import DEFAULTS

    datos = yaml.safe_load(PLANTILLA.read_text(encoding="utf-8"))
    desconocidas = set(datos) - set(DEFAULTS)
    assert not desconocidas, f"claves que la app ignora: {desconocidas}"
