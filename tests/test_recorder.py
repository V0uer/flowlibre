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


class _FakeStream:
    """Stream falso que registra el orden de start/stop/close, sin abrir
    hardware. Se instala en lugar de sd.InputStream vía monkeypatch."""

    def __init__(self, eventos, **kwargs):
        self._eventos = eventos
        self.callback = kwargs["callback"]

    def start(self):
        self._eventos.append("stream.start")

    def stop(self):
        self._eventos.append("stream.stop")

    def close(self):
        self._eventos.append("stream.close")


def test_stop_cierra_el_stream_antes_de_vaciar_el_chunker(monkeypatch):
    """El orden que protege la ultima palabra del dictado: si esto se invierte,
    un bloque que llegue a medio flush() se pierde en silencio."""
    eventos = []

    monkeypatch.setattr(
        "flowlibre.audio.sd.InputStream",
        lambda **kwargs: _FakeStream(eventos, **kwargs),
    )

    class FakeChunker:
        def __init__(self, *a, **k):
            pass

        def feed(self, block):
            return None

        def flush(self):
            eventos.append("chunker.flush")
            return np.zeros(0, dtype="float32")

    monkeypatch.setattr("flowlibre.chunker.Chunker", FakeChunker)

    r = Recorder(on_chunk=lambda chunk: None)
    r.start()
    r.stop()

    assert eventos.index("stream.stop") < eventos.index("chunker.flush")
    assert eventos.index("stream.close") < eventos.index("chunker.flush")


def test_start_conecta_el_callback_del_stream_a_ingest_con_chunker_nuevo(monkeypatch):
    """Si alguien borra la creacion del Chunker dentro de start(), o desconecta
    el callback de _ingest, este test debe fallar."""
    eventos = []

    monkeypatch.setattr(
        "flowlibre.audio.sd.InputStream",
        lambda **kwargs: _FakeStream(eventos, **kwargs),
    )

    r = Recorder(on_chunk=lambda chunk: None)
    chunker_de_init = r._chunker

    ingest_calls = []
    monkeypatch.setattr(r, "_ingest", lambda indata: ingest_calls.append(indata))

    r.start()

    assert r._chunker is not None
    assert r._chunker is not chunker_de_init  # start() debe crear uno nuevo

    bloque = habla(1)
    r._stream.callback(bloque, None, None, None)
    assert len(ingest_calls) == 1
    assert ingest_calls[0] is bloque


def test_excepcion_en_on_chunk_no_rompe_la_ingesta():
    """Si on_chunk truena (bug del consumidor), _ingest no debe propagar la
    excepcion: eso correria dentro del callback de PortAudio y abortaria el
    stream en silencio. La grabacion debe poder seguir alimentandose."""

    def on_chunk_que_truena(chunk):
        raise RuntimeError("boom")

    r = Recorder(on_chunk=on_chunk_que_truena)
    r._chunks = []
    r.recording = True

    r._ingest(habla(9))
    r._ingest(silencio(0.6))  # fuerza un corte natural -> on_chunk truena aqui

    # seguir alimentando audio despues de la excepcion no debe fallar
    r._ingest(habla(2))

    with r._lock:
        audio_acumulado = sum(c.size for c in r._chunks)
    assert audio_acumulado >= 11 * SAMPLE_RATE
