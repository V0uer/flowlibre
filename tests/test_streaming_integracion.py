"""Cadena completa sin microfono ni GPU: Recorder -> Chunker -> StreamingTranscriber.

Las demas pruebas cubren cada pieza por separado con dobles. Esta es la unica
que verifica que las tres encajan: que el audio que entra por el callback sale
troceado, se transcribe en orden, y se une sin repetir el traslape.
"""

import numpy as np

from flowlibre.audio import Recorder
from flowlibre.stream_stt import StreamingTranscriber


class _TranscriberFalso:
    """Numera los trozos que le llegan, para poder verificar el orden."""

    def __init__(self):
        self.trozos = []

    def transcribe(self, audio, language):
        self.trozos.append(len(audio))
        return f"trozo {len(self.trozos)}", "es"


def _bloque(rms, muestras=1600):
    rng = np.random.default_rng(len(str(rms)) + muestras)
    return (rng.normal(0, rms, (muestras, 1))).astype("float32")


def _silencio(muestras=1600):
    return np.zeros((muestras, 1), dtype="float32")


def test_la_cadena_completa_produce_texto_unido_y_en_orden():
    falso = _TranscriberFalso()
    st = StreamingTranscriber(falso, "es")
    rec = Recorder(None, on_chunk=st.submit)
    rec.recording = True                      # sin abrir PortAudio de verdad

    def hablar(segundos):
        for _ in range(int(segundos * 10)):   # bloques de 0.1 s
            rec._ingest(_bloque(0.1))

    def callar(segundos):
        for _ in range(int(segundos * 10)):
            rec._ingest(_silencio())

    hablar(9)                                 # pasa el minimo de 8 s
    callar(0.6)                               # pausa natural -> corte
    hablar(9)
    audio = rec.stop()                        # emite el trozo final

    texto, idioma = st.result(timeout_s=10.0)

    assert len(falso.trozos) >= 2, "el troceo no corto: se transcribio todo de golpe"
    assert idioma == "es"
    esperado = " ".join(f"trozo {i + 1}" for i in range(len(falso.trozos)))
    assert texto == esperado
    assert len(audio) == int(18.6 * 16000)    # el audio completo sigue disponible
