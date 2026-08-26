import time

import flowlibre.inject as inject


def test_returns_true_as_soon_as_clipboard_matches(monkeypatch):
    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: "hola")
    t = time.perf_counter()
    assert inject.wait_for_clipboard("hola", timeout_s=1.0) is True
    # Debe volver de inmediato, no dormir el timeout completo
    assert time.perf_counter() - t < 0.1


def test_returns_false_after_timeout_when_never_matches(monkeypatch):
    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: "otra cosa")
    t = time.perf_counter()
    assert inject.wait_for_clipboard("hola", timeout_s=0.2) is False
    assert time.perf_counter() - t >= 0.2


def test_tolerates_clipboard_read_failures(monkeypatch):
    # _get_clipboard_text devuelve None cuando el portapapeles esta ocupado
    estados = iter([None, None, "hola"])
    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: next(estados, "hola"))
    assert inject.wait_for_clipboard("hola", timeout_s=1.0) is True
