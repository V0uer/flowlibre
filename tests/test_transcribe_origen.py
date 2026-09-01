"""Resolucion del modelo: ruta local (int8 generado en models/) vs nombre de HF."""

from flowlibre.config import ROOT
from flowlibre.transcribe import Transcriber


def test_una_ruta_relativa_existente_se_resuelve_contra_la_raiz(tmp_path, monkeypatch):
    (ROOT / "models" / "prueba-int8").mkdir(parents=True, exist_ok=True)
    try:
        t = Transcriber("models/prueba-int8", "int8_float16")
        assert t._resolve_origen() == str(ROOT / "models" / "prueba-int8")
    finally:
        (ROOT / "models" / "prueba-int8").rmdir()


def test_un_nombre_suelto_se_deja_para_hugging_face():
    assert Transcriber("large-v3-turbo", "int8_float16")._resolve_origen() == "large-v3-turbo"


def test_una_ruta_que_no_existe_avisa_con_el_comando_para_generarla(capsys):
    """models/ esta en .gitignore: en un clon nuevo la carpeta NO existe, y el
    error de Hugging Face ('repo models/... not found') no dice como arreglarlo."""
    t = Transcriber("models/no-existe-int8", "int8_float16")
    assert t._resolve_origen() == "models/no-existe-int8"
    salida = capsys.readouterr().out
    assert "quantize_model.py" in salida


def test_el_origen_arranca_con_el_nombre_del_modelo():
    """transcribe() reintenta en CPU con self._origen; si nace vacio, el reintento
    (que corre justo cuando la GPU ya fallo) truena con AttributeError."""
    assert Transcriber("large-v3-turbo", "int8_float16")._origen == "large-v3-turbo"


# --- instalada: el modelo puede estar en dos lugares ---


def test_instalada_gana_el_modelo_descargado_sobre_el_empaquetado(monkeypatch, tmp_path):
    """El modelo grande se descarga después de instalar (va a %APPDATA%), pero el
    bundle puede traer uno chico. Si ganara el empaquetado, la descarga de 800 MB
    no serviría de nada y nadie vería un error."""
    import flowlibre.paths as paths
    datos, bundle = tmp_path / "datos", tmp_path / "bundle"
    (datos / "models" / "turbo-int8").mkdir(parents=True)
    (bundle / "models" / "turbo-int8").mkdir(parents=True)
    monkeypatch.setattr(paths, "data_dir", lambda: datos)
    monkeypatch.setattr(paths, "resource_dir", lambda: bundle)

    t = Transcriber("models/turbo-int8", "int8_float16")
    assert t._resolve_origen() == str(datos / "models" / "turbo-int8")


def test_instalada_cae_al_modelo_empaquetado(monkeypatch, tmp_path):
    import flowlibre.paths as paths
    datos, bundle = tmp_path / "datos", tmp_path / "bundle"
    datos.mkdir()
    (bundle / "models" / "small-int8").mkdir(parents=True)
    monkeypatch.setattr(paths, "data_dir", lambda: datos)
    monkeypatch.setattr(paths, "resource_dir", lambda: bundle)

    t = Transcriber("models/small-int8", "int8_float16")
    assert t._resolve_origen() == str(bundle / "models" / "small-int8")
