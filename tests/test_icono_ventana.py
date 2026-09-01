"""El icono de las ventanas de la app (panel y barra de tareas).

Se prueba la resolucion del archivo, no tkinter: abrir una ventana real en la
suite requiere un escritorio y cuelga en cualquier corrida sin sesion grafica.
"""

from pathlib import Path

from flowlibre.iconos import ICONOS_DIR, ruta_icono_ventana


def test_encuentra_el_png_grande():
    ruta = ruta_icono_ventana()
    assert ruta is not None
    assert Path(ruta).exists()
    assert Path(ruta).suffix == ".png"


def test_devuelve_none_si_no_hay_assets(monkeypatch, tmp_path):
    """Sin assets la app debe abrir igual, solo que con el icono de Tk."""
    import flowlibre.iconos as ic
    monkeypatch.setattr(ic, "ICONOS_DIR", tmp_path)
    assert ic.ruta_icono_ventana() is None


def test_el_ico_de_windows_trae_los_seis_tamanos():
    """Windows elige el tamano segun donde lo pinte; si solo hubiera 256, el
    escritorio se veria bien y la barra de tareas borrosa."""
    from PIL import Image
    with Image.open(ICONOS_DIR / "FlowLibre.ico") as ico:
        assert {s[0] for s in ico.info["sizes"]} == {16, 32, 48, 64, 128, 256}
