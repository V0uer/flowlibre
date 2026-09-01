"""El troceo conectado a la app real: firma del pipeline, respaldo cuando el
streaming no entrega nada, y que cancelar no deje trabajo de GPU en vuelo."""

import inspect
import threading
import types

import numpy as np

from flowlibre.app import FlowLibreApp
from flowlibre.config import DEFAULTS, VALID


def test_streaming_activado_por_defecto():
    assert DEFAULTS["streaming_stt"] is True


def test_streaming_stt_valida_booleanos():
    """Un `streaming_stt: "no"` en el YAML es truthy: sin validar, apagarlo mal
    lo dejaria prendido en silencio."""
    assert VALID["streaming_stt"] == {True, False}


def test_pipeline_recibe_texto_no_audio():
    """El pipeline ya no transcribe: recibe el texto listo.

    Se verifica por firma para no necesitar GPU ni microfono en la suite.
    """
    params = list(inspect.signature(FlowLibreApp._pipeline).parameters)
    assert params == ["self", "text", "language", "audio_duration_s", "prefix"]


# --- respaldo cuando el streaming no entrega texto ---


class _TranscriberFalso:
    def __init__(self, texto="del audio completo"):
        self.texto = texto
        self.llamadas = 0

    def transcribe(self, audio, language):
        self.llamadas += 1
        return self.texto, "es"


class _SttFalso:
    def __init__(self, resultado=None, error=None):
        self.resultado = resultado
        self.error = error

    def result(self):
        if self.error:
            raise self.error
        return self.resultado


def _app_de_proceso(transcriber):
    ns = types.SimpleNamespace()
    ns._busy = threading.Lock()
    ns.config = types.SimpleNamespace(language="es")
    ns.transcriber = transcriber
    ns.overlay = types.SimpleNamespace(hide=lambda: None)
    ns._set_status = lambda status: None
    ns.pipeline_calls = []
    ns._pipeline = lambda *a, **k: ns.pipeline_calls.append((a, k))
    ns._process = types.MethodType(FlowLibreApp._process, ns)
    return ns


def test_usa_el_texto_del_streaming_sin_retranscribir():
    app = _app_de_proceso(_TranscriberFalso())
    app._process(np.zeros(16000, dtype="float32"), "", _SttFalso(("hola mundo", "es")))
    assert app.transcriber.llamadas == 0
    assert app.pipeline_calls[0][0][0] == "hola mundo"


def test_si_el_streaming_sale_vacio_transcribe_el_audio_completo():
    """El audio entero sigue en memoria: perder el dictado seria gratis y evitable."""
    app = _app_de_proceso(_TranscriberFalso("rescatado del audio"))
    app._process(np.zeros(16000, dtype="float32"), "", _SttFalso(("", "")))
    assert app.transcriber.llamadas == 1
    assert app.pipeline_calls[0][0][0] == "rescatado del audio"


def test_si_el_streaming_truena_transcribe_el_audio_completo():
    app = _app_de_proceso(_TranscriberFalso("rescatado del audio"))
    app._process(np.zeros(16000, dtype="float32"), "",
                 _SttFalso(error=RuntimeError("modelo caido")))
    assert app.transcriber.llamadas == 1
    assert app.pipeline_calls[0][0][0] == "rescatado del audio"


def test_no_retranscribe_si_no_hay_audio_que_rescatar():
    app = _app_de_proceso(_TranscriberFalso())
    app._process(np.zeros(0, dtype="float32"), "", _SttFalso(("", "")))
    assert app.transcriber.llamadas == 0
    assert app.pipeline_calls == []


# --- cancelar no puede dejar trabajo de GPU en vuelo ---


class _RecorderFalso:
    def __init__(self, on_chunk=None):
        self.recording = True
        self.on_chunk = on_chunk

    def stop(self):
        self.recording = False
        if self.on_chunk:                      # el trozo final del flush
            self.on_chunk(np.zeros(16000, dtype="float32"))
        return np.zeros(16000, dtype="float32")


def _app_de_cancelacion():
    ns = types.SimpleNamespace()
    ns.overlay = types.SimpleNamespace(hide=lambda: None)
    ns._set_status = lambda status: None
    ns._stream_stt = None
    ns._on_chunk = types.MethodType(FlowLibreApp._on_chunk, ns)
    ns.recorder = _RecorderFalso(on_chunk=ns._on_chunk)
    ns.cancel_recording = types.MethodType(FlowLibreApp.cancel_recording, ns)
    return ns


def test_cancelar_no_manda_el_trozo_final_a_transcribir():
    """Cancelar es 'no quiero esto': mandar el flush a la GPU es trabajo tirado
    justo cuando la contencion de GPU es el problema que estamos resolviendo."""
    app = _app_de_cancelacion()
    enviados = []
    app._stream_stt = types.SimpleNamespace(
        submit=enviados.append, cancel=lambda: None
    )
    app.cancel_recording()
    assert enviados == []
    assert app._stream_stt is None


def test_cancelar_cierra_el_hilo_del_transcriptor():
    """Sin cancel(), el hilo consumidor se queda bloqueado en la cola para siempre:
    un hilo colgado por cada dictado cancelado."""
    app = _app_de_cancelacion()
    cerrados = []
    app._stream_stt = types.SimpleNamespace(
        submit=lambda c: None, cancel=lambda: cerrados.append(True)
    )
    app.cancel_recording()
    assert cerrados == [True]


# --- el cableado real recorder -> _on_chunk (si esto se cae, el troceo
#     deja de servir en silencio: la app sigue funcionando, solo lenta) ---


def _app_de_recorder(streaming):
    ns = types.SimpleNamespace()
    ns.config = types.SimpleNamespace(microphone=None, streaming_stt=streaming)
    ns._stream_stt = None
    ns._on_chunk = types.MethodType(FlowLibreApp._on_chunk, ns)
    ns._make_recorder = types.MethodType(FlowLibreApp._make_recorder, ns)
    return ns


def test_el_recorder_recibe_on_chunk_con_streaming_prendido():
    app = _app_de_recorder(True)
    rec = app._make_recorder()
    enviados = []
    app._stream_stt = types.SimpleNamespace(submit=enviados.append)
    rec.on_chunk(np.zeros(8, dtype="float32"))
    assert len(enviados) == 1

def test_el_recorder_no_trocea_con_streaming_apagado():
    assert _app_de_recorder(False)._make_recorder().on_chunk is None
