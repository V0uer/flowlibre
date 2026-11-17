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


# --- inject_text: secuencia completa (guardar -> escribir -> sondear -> pegar/teclear -> restaurar) ---
#
# `wait_for_clipboard` ya tiene su propia cobertura de timing arriba. Aqui se
# monkeypatchea directo para poder probar rapido y sin ambiguedad la logica de
# ramificacion de `inject_text`: cuando pega, cuando reintenta, cuando cae a
# teclear, y que el portapapeles del autor siempre quede como estaba.


def test_inject_text_happy_path_pastes_and_restores_original(monkeypatch):
    state = {"clipboard": "lo que el autor tenia copiado"}
    calls = []

    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: state["clipboard"])
    monkeypatch.setattr(inject, "_set_clipboard_text", lambda t: state.__setitem__("clipboard", t))
    monkeypatch.setattr(inject, "wait_for_clipboard", lambda expected, timeout_s=None: True)
    monkeypatch.setattr(inject.keyboard, "send", lambda combo: calls.append(("send", combo)))
    monkeypatch.setattr(inject.keyboard, "write", lambda t, delay=0: calls.append(("write", t)))
    monkeypatch.setattr(inject.time, "sleep", lambda s: None)

    inject.inject_text("hola mundo")

    assert calls == [("send", "ctrl+v")]
    assert state["clipboard"] == "lo que el autor tenia copiado"


def test_inject_text_retries_once_and_still_pastes(monkeypatch):
    resultados = iter([False, True])
    calls = []
    wait_calls = []
    state = {"clipboard": "lo que el autor tenia copiado"}

    def fake_wait(expected, timeout_s=None):
        wait_calls.append(timeout_s)
        return next(resultados)

    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: state["clipboard"])
    monkeypatch.setattr(
        inject,
        "_set_clipboard_text",
        lambda t: (calls.append(("set", t)), state.__setitem__("clipboard", t)),
    )
    monkeypatch.setattr(inject, "wait_for_clipboard", fake_wait)
    monkeypatch.setattr(inject.keyboard, "send", lambda combo: calls.append(("send", combo)))
    monkeypatch.setattr(inject.keyboard, "write", lambda t, delay=0: calls.append(("write", t)))
    monkeypatch.setattr(inject.time, "sleep", lambda s: None)

    inject.inject_text("hola mundo")

    # se reintenta _set_clipboard_text una vez antes de pegar (mas la restauracion
    # final del portapapeles original); nunca se teclea
    sets_del_texto = [c for c in calls if c == ("set", "hola mundo")]
    assert len(sets_del_texto) == 2
    assert ("send", "ctrl+v") in calls
    assert not any(c[0] == "write" for c in calls)
    assert state["clipboard"] == "lo que el autor tenia copiado"
    # el reintento usa un plazo corto (0.05), no el default de 0.15: si el
    # primer sondeo ya se agoto, el portapapeles esta contendido de verdad y
    # alargar el segundo no cambia el panorama.
    assert wait_calls == [None, 0.05]


def test_inject_text_falls_back_to_typing_when_clipboard_never_settles(monkeypatch):
    calls = []
    state = {"clipboard": "lo que el autor tenia copiado"}

    def fake_set(t):
        calls.append(("set", t))
        state["clipboard"] = t

    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: state["clipboard"])
    # wait_for_clipboard siempre da False (portapapeles contendido de verdad),
    # asi que a inject_text no le importa lo que fake_set en verdad escriba:
    # nunca lo va a dar por bueno. Lo que se prueba aqui es que, al final, el
    # codigo restaure el original -- por eso fake_set SI muta state, igual que
    # en los otros tests: si _restore_clipboard(original) se borrara del
    # codigo fuente, este test debe fallar.
    monkeypatch.setattr(inject, "_set_clipboard_text", fake_set)
    monkeypatch.setattr(inject, "wait_for_clipboard", lambda expected, timeout_s=None: False)
    monkeypatch.setattr(inject.keyboard, "send", lambda combo: calls.append(("send", combo)))
    monkeypatch.setattr(inject.keyboard, "write", lambda t, delay=0: calls.append(("write", t)))
    monkeypatch.setattr(inject.time, "sleep", lambda s: None)

    inject.inject_text("hola mundo")

    assert not any(c[0] == "send" for c in calls)
    assert ("write", "hola mundo") in calls
    # el texto dictado no debe quedar pegado en el portapapeles del autor
    assert state["clipboard"] == "lo que el autor tenia copiado"


def test_inject_text_without_original_clipboard_skips_restore(monkeypatch):
    calls = []
    state = {"clipboard": None}

    def fake_set(t):
        calls.append(("set", t))
        state["clipboard"] = t

    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: state["clipboard"])
    monkeypatch.setattr(inject, "_set_clipboard_text", fake_set)
    monkeypatch.setattr(inject, "wait_for_clipboard", lambda expected, timeout_s=None: True)
    monkeypatch.setattr(inject.keyboard, "send", lambda combo: calls.append(("send", combo)))
    monkeypatch.setattr(inject.keyboard, "write", lambda t, delay=0: calls.append(("write", t)))
    monkeypatch.setattr(inject.time, "sleep", lambda s: None)

    inject.inject_text("hola mundo")

    # no habia portapapeles original -> una sola llamada a _set_clipboard_text
    # (la que pega el texto dictado), ninguna de restauracion
    assert [c for c in calls if c[0] == "set"] == [("set", "hola mundo")]


# --- La tecla Windows del atajo todavia abajo al momento de pegar ---
#
# El atajo por defecto es "windows+ctrl". Si el texto llega antes de que el
# autor suelte Windows, el Ctrl+V sintetico se combina con esa tecla fisica:
# Windows recibe Win+Ctrl+V, abre el selector de salida de sonido y el texto
# no se pega. Antes de mandar cualquier tecla hay que esperar a que se suelte.


def _parchar_teclas(monkeypatch, calls):
    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: None)
    monkeypatch.setattr(inject, "_set_clipboard_text", lambda t: None)
    monkeypatch.setattr(inject, "wait_for_clipboard", lambda expected, timeout_s=None: True)
    monkeypatch.setattr(inject.keyboard, "send", lambda combo: calls.append(("send", combo)))
    monkeypatch.setattr(inject.keyboard, "write", lambda t, delay=0: calls.append(("write", t)))
    monkeypatch.setattr(inject.time, "sleep", lambda s: None)


def test_inject_text_espera_a_que_se_suelte_windows_antes_de_pegar(monkeypatch):
    calls = []
    estados = iter([True, True, False])

    def fake_presionada():
        valor = next(estados, False)
        calls.append(("windows abajo", valor))
        return valor

    _parchar_teclas(monkeypatch, calls)
    monkeypatch.setattr(inject, "_tecla_windows_presionada", fake_presionada)

    inject.inject_text("hola mundo")

    assert ("send", "ctrl+v") in calls
    pegado = calls.index(("send", "ctrl+v"))
    soltada = calls.index(("windows abajo", False))
    assert soltada < pegado
    # no se consulto ni una vez mas despues de pegar: la espera va antes
    assert not any(c[0] == "windows abajo" for c in calls[pegado:])


def test_inject_text_no_se_cuelga_si_windows_nunca_se_suelta(monkeypatch):
    calls = []
    _parchar_teclas(monkeypatch, calls)
    monkeypatch.setattr(inject, "_tecla_windows_presionada", lambda: True)
    monkeypatch.setattr(inject, "ESPERA_MAX_TECLA_WINDOWS_S", 0.05)

    t = time.perf_counter()
    inject.inject_text("hola mundo")

    # se rinde al plazo y pega de todos modos: perder el dictado es peor
    assert time.perf_counter() - t < 1.0
    assert ("send", "ctrl+v") in calls


def test_el_modo_typing_tambien_espera_a_windows(monkeypatch):
    calls = []
    estados = iter([True, False])

    def fake_presionada():
        valor = next(estados, False)
        calls.append(("windows abajo", valor))
        return valor

    _parchar_teclas(monkeypatch, calls)
    monkeypatch.setattr(inject, "_tecla_windows_presionada", fake_presionada)

    inject.inject_text("hola", method="typing")

    assert calls.index(("windows abajo", False)) < calls.index(("write", "hola"))


def test_delete_chars_espera_a_windows(monkeypatch):
    calls = []
    estados = iter([True, False])

    def fake_presionada():
        valor = next(estados, False)
        calls.append(("windows abajo", valor))
        return valor

    _parchar_teclas(monkeypatch, calls)
    monkeypatch.setattr(inject, "_tecla_windows_presionada", fake_presionada)

    inject.delete_chars(2)

    assert calls.index(("windows abajo", False)) < calls.index(("send", "backspace"))
