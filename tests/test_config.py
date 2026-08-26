from flowlibre.config import DEFAULTS


def test_default_model_is_turbo():
    assert DEFAULTS["whisper_model"] == "large-v3-turbo"


def test_beam_size_default_is_one():
    assert DEFAULTS["whisper_beam_size"] == 1
