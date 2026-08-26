from flowlibre.clean_claude import classify_error, estimate_max_tokens


def test_short_text_gets_small_budget():
    # ~50 caracteres no necesitan 2048 tokens de salida
    assert estimate_max_tokens("Hola, como estas el dia de hoy amigo.") < 200


def test_budget_scales_with_input():
    corto = estimate_max_tokens("a" * 100)
    largo = estimate_max_tokens("a" * 2000)
    assert largo > corto


def test_budget_has_a_floor():
    # Un dictado de una palabra no debe quedarse sin presupuesto
    assert estimate_max_tokens("Hola") >= 64


def test_budget_has_a_ceiling():
    # Un dictado enorme no debe pedir un presupuesto ilimitado
    assert estimate_max_tokens("a" * 100_000) <= 4096


def test_401_habla_de_la_api_key():
    msg = classify_error(401, {"error": {"message": "invalid x-api-key"}})
    assert "API key" in msg


def test_429_habla_de_rate_limit():
    assert "Rate limit" in classify_error(429, {})


def test_403_sugiere_revisar_saldo():
    assert "saldo" in classify_error(403, {})


def test_otros_codigos_incluyen_el_status():
    assert "500" in classify_error(500, {"error": {"message": "boom"}})
