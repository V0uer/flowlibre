import time

import numpy as np

from flowlibre.stream_stt import StreamingTranscriber


class TranscriberFalso:
    """Devuelve textos predefinidos, uno por llamada, y simula tardanza."""

    def __init__(self, textos, demora=0.0):
        self.textos = list(textos)
        self.demora = demora
        self.llamadas = 0

    def transcribe(self, audio, language):
        if self.demora:
            time.sleep(self.demora)
        texto = self.textos[self.llamadas] if self.llamadas < len(self.textos) else ""
        self.llamadas += 1
        if isinstance(texto, BaseException):
            raise texto
        return texto, "es"


def audio(segundos=1.0):
    return np.zeros(int(segundos * 16000), dtype="float32")


def test_une_los_trozos_en_orden():
    st = StreamingTranscriber(TranscriberFalso(["hola que tal", "todo bien gracias"]), "es")
    st.submit(audio())
    st.submit(audio())
    texto, idioma = st.result()
    assert texto == "hola que tal todo bien gracias"
    assert idioma == "es"


def test_deduplica_el_traslape_entre_trozos():
    st = StreamingTranscriber(
        TranscriberFalso(["necesito el reporte de agosto", "de agosto por favor"]), "es"
    )
    st.submit(audio())
    st.submit(audio())
    texto, _ = st.result()
    assert texto == "necesito el reporte de agosto por favor"


def test_transcribe_mientras_llegan_mas_trozos():
    falso = TranscriberFalso(["uno", "dos", "tres"], demora=0.05)
    st = StreamingTranscriber(falso, "es")
    st.submit(audio())
    time.sleep(0.15)                  # da tiempo a que procese el primero
    assert falso.llamadas >= 1        # ya trabajo sin esperar a los demas
    st.submit(audio())
    st.submit(audio())
    assert st.result() == ("uno dos tres", "es")


def test_sin_trozos_devuelve_vacio():
    assert StreamingTranscriber(TranscriberFalso([]), "es").result() == ("", "")


def test_ignora_trozos_que_salen_vacios():
    st = StreamingTranscriber(TranscriberFalso(["hola", "", "mundo"]), "es")
    for _ in range(3):
        st.submit(audio())
    texto, _ = st.result()
    assert texto == "hola mundo"


# --- Rulings C30/C31: un trozo malo no puede costar el dictado entero ---


def test_un_trozo_que_falla_no_tumba_el_resto():
    falso = TranscriberFalso(["uno", RuntimeError("trozo malo"), "tres"])
    st = StreamingTranscriber(falso, "es")
    for _ in range(3):
        st.submit(audio())
    texto, idioma = st.result()
    assert texto == "uno tres"        # se pierde el trozo, no el dictado
    assert idioma == "es"
    assert falso.llamadas == 3        # siguio consumiendo despues del error


def test_si_todo_falla_y_no_hay_texto_relanza_el_error():
    st = StreamingTranscriber(
        TranscriberFalso([RuntimeError("modelo caido"), RuntimeError("modelo caido")]), "es"
    )
    st.submit(audio())
    st.submit(audio())
    try:
        st.result()
    except RuntimeError as e:
        assert "modelo caido" in str(e)
    else:
        raise AssertionError("con cero texto y solo errores, result() debe relanzar")


def test_timeout_devuelve_lo_que_haya_sin_colgarse():
    st = StreamingTranscriber(TranscriberFalso(["uno", "dos"], demora=5.0), "es")
    st.submit(audio())
    st.submit(audio())
    inicio = time.monotonic()
    texto, _ = st.result(timeout_s=0.1)
    assert time.monotonic() - inicio < 2.0    # no espero a los 10 s de trabajo
    assert isinstance(texto, str)
