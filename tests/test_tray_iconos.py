"""La bandeja usa la marca generada, y no se cae si los assets no estan.

El respaldo importa de verdad: `assets/` puede faltar en un bundle mal armado o
en un clon a medias, y quedarse sin icono de bandeja significa quedarse **sin
ninguna forma de abrir el panel o salir de la app**.
"""

import flowlibre.tray as tray


def test_hay_un_icono_por_cada_estado():
    for estado in ("listo", "grabando", "procesando", "apagado"):
        img = tray._make_icon(estado)
        assert img.size[0] >= 16
        assert img.mode == "RGBA"


def test_los_estados_se_ven_distintos():
    """Si todos salieran iguales, el icono dejaria de comunicar el estado y nadie
    lo notaria: la app seguiria 'funcionando'."""
    vistos = {estado: tray._make_icon(estado).tobytes()
              for estado in ("listo", "grabando", "procesando", "apagado")}
    assert len(set(vistos.values())) == 4


def test_usa_el_png_generado_cuando_existe(monkeypatch):
    llamado = {"n": 0}
    original = tray._icono_dibujado

    def espia(color):
        llamado["n"] += 1
        return original(color)

    monkeypatch.setattr(tray, "_icono_dibujado", espia)
    tray._make_icon("listo")
    assert llamado["n"] == 0, "habiendo PNG, no deberia dibujar el respaldo"


def test_cae_al_dibujado_si_falta_el_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(tray, "ICONOS_DIR", tmp_path / "no-existe")
    img = tray._make_icon("grabando")
    assert img.size[0] >= 16     # sigue habiendo icono, no una excepcion
