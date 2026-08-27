import numpy as np

from flowlibre.audio import SAMPLE_RATE, Recorder


def habla(segundos: float) -> np.ndarray:
    n = int(segundos * SAMPLE_RATE)
    return (np.random.default_rng(1).standard_normal((n, 1)) * 0.2).astype("float32")


def silencio(segundos: float) -> np.ndarray:
    return np.zeros((int(segundos * SAMPLE_RATE), 1), dtype="float32")


def test_sin_callback_no_emite_trozos():
    r = Recorder()
    r._chunks = []
    r.recording = True
    r._ingest(habla(20))          # sin on_chunk, solo acumula
    assert r.stop().size >= 20 * SAMPLE_RATE


def test_con_callback_emite_trozos_durante_la_grabacion():
    emitidos = []
    r = Recorder(on_chunk=emitidos.append)
    r._chunks = []
    r.recording = True
    for bloque in (habla(9), silencio(0.6), habla(2)):
        r._ingest(bloque)
    assert len(emitidos) == 1
    assert emitidos[0].size >= 9 * SAMPLE_RATE


def test_stop_devuelve_el_audio_completo_aunque_haya_troceado():
    emitidos = []
    r = Recorder(on_chunk=emitidos.append)
    r._chunks = []
    r.recording = True
    for bloque in (habla(9), silencio(0.6), habla(3)):
        r._ingest(bloque)
    completo = r.stop()
    # El audio entero sigue disponible: 9 + 0.6 + 3 segundos
    assert completo.size >= 12 * SAMPLE_RATE
