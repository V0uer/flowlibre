"""Dónde viven los datos del usuario según cómo corra la app.

Corriendo desde el código (como hoy, en D:\FlowLibre) todo se queda donde está.
Corriendo instalada, los datos se van a %APPDATA%: la carpeta del programa es de
solo lectura, y aunque no lo fuera, la primera actualización que reemplace esa
carpeta se llevaría el historial de dictados.
"""

from pathlib import Path

import flowlibre.paths as paths


def _empaquetada(monkeypatch, appdata: Path):
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(appdata))


def test_en_desarrollo_los_datos_siguen_junto_al_codigo():
    assert paths.data_dir() == paths.ROOT


def test_instalada_los_datos_se_van_a_appdata(monkeypatch, tmp_path):
    _empaquetada(monkeypatch, tmp_path)
    assert paths.data_dir() == tmp_path / "FlowLibre"
    assert paths.data_dir().is_dir()          # la crea, no falla


def test_sin_appdata_cae_a_la_carpeta_del_usuario(monkeypatch, tmp_path):
    """En una sesión rara sin APPDATA, mejor el perfil del usuario que reventar."""
    _empaquetada(monkeypatch, tmp_path)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(paths.Path, "home", staticmethod(lambda: tmp_path / "casa"))
    assert paths.data_dir() == tmp_path / "casa" / ".flowlibre"


def test_los_recursos_de_solo_lectura_salen_del_bundle(monkeypatch, tmp_path):
    _empaquetada(monkeypatch, tmp_path)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    assert paths.resource_dir() == tmp_path / "bundle"


def test_sin_meipass_los_recursos_estan_junto_al_ejecutable(monkeypatch, tmp_path):
    _empaquetada(monkeypatch, tmp_path)
    monkeypatch.delattr(paths.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(tmp_path / "app" / "FlowLibre.exe"))
    assert paths.resource_dir() == tmp_path / "app"


# --- siembra y migración ---


def test_siembra_los_archivos_que_faltan(tmp_path):
    origen, destino = tmp_path / "prog", tmp_path / "datos"
    origen.mkdir(); destino.mkdir()
    (origen / "config.yaml").write_text("engine: claude\n", encoding="utf-8")
    (origen / "commands.json").write_text("{}", encoding="utf-8")

    paths.sembrar(origen, destino)

    assert (destino / "config.yaml").read_text(encoding="utf-8") == "engine: claude\n"
    assert (destino / "commands.json").exists()


def test_la_siembra_nunca_pisa_lo_que_el_usuario_ya_tiene(tmp_path):
    """Se corre en cada arranque: si sobrescribiera, cada actualización borraría
    la configuración del autor."""
    origen, destino = tmp_path / "prog", tmp_path / "datos"
    origen.mkdir(); destino.mkdir()
    (origen / "config.yaml").write_text("engine: ollama\n", encoding="utf-8")
    (destino / "config.yaml").write_text("engine: claude\n", encoding="utf-8")

    paths.sembrar(origen, destino)

    assert (destino / "config.yaml").read_text(encoding="utf-8") == "engine: claude\n"


def test_migra_el_historial_sin_borrar_el_original(tmp_path):
    """176 dictados de historial: se copia, no se mueve. Si algo sale mal en la
    migración, el original sigue ahí."""
    origen, destino = tmp_path / "prog", tmp_path / "datos"
    origen.mkdir(); destino.mkdir()
    (origen / "history.jsonl").write_text('{"raw":"hola"}\n', encoding="utf-8")

    paths.sembrar(origen, destino)

    assert (destino / "history.jsonl").exists()
    assert (origen / "history.jsonl").exists()


def test_sembrar_no_hace_nada_si_origen_y_destino_son_el_mismo(tmp_path):
    """El caso de desarrollo: no debe copiarse encima de sí mismo."""
    (tmp_path / "config.yaml").write_text("x: 1\n", encoding="utf-8")
    paths.sembrar(tmp_path, tmp_path)
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == "x: 1\n"


def test_config_apunta_al_directorio_de_datos():
    from flowlibre import config
    assert config.CONFIG_PATH.parent == paths.data_dir()
    assert config.HISTORY_PATH.parent == paths.data_dir()
