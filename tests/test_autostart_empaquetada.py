"""El comando que se registra en el arranque de Windows.

Un comando mal formado aquí no da error en ningún lado: la app simplemente no
arranca con Windows y nadie sabe por qué hasta que lo nota semanas después.
"""

import flowlibre.autostart as autostart


def test_desde_el_codigo_usa_pythonw_y_el_launcher():
    cmd = autostart._command()
    assert "pythonw" in cmd.lower()
    assert "flowlibre.pyw" in cmd


def test_instalada_registra_el_ejecutable(monkeypatch, tmp_path):
    exe = tmp_path / "Programas" / "FlowLibre" / "FlowLibre.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable", str(exe))

    cmd = autostart._command()

    assert cmd == f'"{exe}"'
    assert "pythonw" not in cmd.lower()
    assert ".pyw" not in cmd


def test_la_ruta_va_entre_comillas(monkeypatch, tmp_path):
    """`C:\Program Files\...` sin comillas se parte en el espacio y el registro
    Run intenta ejecutar `C:\Program`."""
    exe = tmp_path / "con espacios" / "FlowLibre.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable", str(exe))

    cmd = autostart._command()

    assert cmd.startswith('"') and cmd.endswith('"')
    assert cmd.count('"') == 2
