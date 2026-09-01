"""cancel(): soltar un dictado a medias sin dejar el hilo colgado ni gastar GPU."""

import time

import numpy as np

from flowlibre.stream_stt import StreamingTranscriber


class _Lento:
    def __init__(self):
        self.llamadas = 0

    def transcribe(self, audio, language):
        self.llamadas += 1
        time.sleep(0.05)
        return "texto", "es"


def _audio():
    return np.zeros(16000, dtype="float32")


def test_cancel_termina_el_hilo():
    st = StreamingTranscriber(_Lento(), "es")
    st.submit(_audio())
    st.cancel()
    st._thread.join(timeout=2.0)
    assert not st._thread.is_alive()


def test_cancel_no_transcribe_lo_que_quedaba_en_la_cola():
    lento = _Lento()
    st = StreamingTranscriber(lento, "es")
    for _ in range(20):
        st.submit(_audio())
    st.cancel()
    st._thread.join(timeout=2.0)
    assert not st._thread.is_alive()
    assert lento.llamadas <= 2      # a lo mucho el que ya estaba en vuelo
