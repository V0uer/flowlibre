from flowlibre.clean_claude import (
    ClaudeCleaner,
    _parse_retry_after,
    classify_error,
    estimate_max_tokens,
)


class _FakeConfig:
    """Config mínima para instanciar ClaudeCleaner sin tocar red ni disco."""
    def __init__(self, claude_timeout_s=4.0):
        self.claude_timeout_s = claude_timeout_s


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


def test_classify_error_no_revienta_con_cuerpo_vacio():
    # Un 502 de un proxy puede llegar sin cuerpo JSON parseable; classify_error
    # ya recibe el body como {} en ese caso (ver manejo defensivo en clean()).
    assert "502" in classify_error(502, {})


def test_classify_error_no_revienta_si_error_no_es_dict():
    # Algunos proxies devuelven {"error": "texto plano"} en vez del objeto
    # {"error": {"message": ...}} que espera la API de Anthropic.
    msg = classify_error(502, {"error": "texto plano"})
    assert "502" in msg


def test_timeout_read_escala_con_max_tokens():
    cleaner = ClaudeCleaner(_FakeConfig(claude_timeout_s=4.0))
    corto = cleaner._timeout_for(64)
    largo = cleaner._timeout_for(4096)
    assert largo.read > corto.read


def test_timeout_read_nunca_baja_del_piso():
    # Con pocos tokens, el plazo de lectura no debe caer por debajo de
    # claude_timeout_s (la conexion ya tarda eso como minimo).
    cleaner = ClaudeCleaner(_FakeConfig(claude_timeout_s=4.0))
    t = cleaner._timeout_for(1)
    assert t.read >= 4.0


def test_timeout_connect_usa_claude_timeout_s():
    cleaner = ClaudeCleaner(_FakeConfig(claude_timeout_s=7.5))
    t = cleaner._timeout_for(2000)
    assert t.connect == 7.5


def test_retry_after_negativo_se_descarta():
    # Un retry-after de -1 no debe llegar a time.sleep(-1), que revienta con
    # ValueError fuera de CleanerError (misma clase de fuga que C-1).
    assert _parse_retry_after("-1") is None


def test_retry_after_nan_se_descarta():
    assert _parse_retry_after("nan") is None


def test_retry_after_numero_valido_se_respeta():
    assert _parse_retry_after("60") == 60.0
    assert _parse_retry_after("1") == 1.0


def test_retry_after_ausente_es_none():
    assert _parse_retry_after(None) is None


def test_retry_after_fecha_http_se_descarta():
    # El header tambien admite una fecha HTTP en vez de segundos; no la
    # soportamos, pero tampoco debe reventar.
    assert _parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
