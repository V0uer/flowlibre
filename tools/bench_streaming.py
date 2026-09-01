"""Mide lo que el usuario de verdad espera: del momento en que suelta la tecla
al texto listo, con el troceo activo.

Por que no basta tools/bench.py: ese llama a Transcriber.transcribe() con el
audio completo, o sea el camino VIEJO. El troceo no aparece por ningun lado,
asi que un WAV de 60 s siempre saldra mas lento ahi aunque la app real ya no
funcione asi.

Aqui se emula el microfono en tiempo real (bloques de 0.1 s con su espera) para
que los trozos se transcriban MIENTRAS "se habla", que es justo de donde sale la
mejora. Por eso un WAV de 60 s tarda 60 s en medirse: no hay forma de medir esto
mas rapido sin mentir.

Uso:  .venv/Scripts/python.exe tools/bench_streaming.py [ruta.wav ...]
"""

from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flowlibre.audio import Recorder                      # noqa: E402
from flowlibre.config import Config                       # noqa: E402
from flowlibre.stream_stt import StreamingTranscriber     # noqa: E402
from flowlibre.transcribe import Transcriber              # noqa: E402

BLOQUE = 1600        # 0.1 s a 16 kHz, como los bloques que entrega sounddevice


def load_wav(path: str) -> np.ndarray:
    with wave.open(str(path)) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError(f"{path}: se esperaba 16 kHz mono")
        raw = w.readframes(w.getnframes())
    return (np.frombuffer(raw, dtype="<i2") / 32768.0).astype("float32")


def mide_streaming(tr: Transcriber, audio: np.ndarray) -> tuple[float, int, str]:
    """Devuelve (espera_al_soltar_s, trozos_transcritos, texto)."""
    contador = {"n": 0}
    transcriber_contado = _Contado(tr, contador)
    st = StreamingTranscriber(transcriber_contado, "es")
    rec = Recorder(None, on_chunk=st.submit)
    rec.recording = True                       # sin abrir PortAudio de verdad

    for i in range(0, len(audio), BLOQUE):
        inicio = time.perf_counter()
        rec._ingest(audio[i:i + BLOQUE].reshape(-1, 1))
        resto = 0.1 - (time.perf_counter() - inicio)
        if resto > 0:
            time.sleep(resto)                  # emula el paso del tiempo real

    t = time.perf_counter()                    # <- aqui el usuario suelta la tecla
    rec.stop()
    texto, _ = st.result(timeout_s=120.0)
    return time.perf_counter() - t, contador["n"], texto


class _Contado:
    """Envuelve al Transcriber solo para contar cuantos trozos se transcribieron."""

    def __init__(self, tr, contador):
        self._tr = tr
        self._c = contador

    def transcribe(self, audio, language):
        self._c["n"] += 1
        return self._tr.transcribe(audio, language)


def main() -> None:
    wavs = sys.argv[1:] or [str(ROOT / "tests" / "fixtures" / f"voz_{s}s.wav")
                            for s in (6, 21, 60)]
    cfg = Config()
    tr = Transcriber(cfg.whisper_model, cfg.whisper_compute_type, cfg.whisper_beam_size)
    print(f"modelo={cfg.whisper_model} compute={cfg.whisper_compute_type} "
          f"beam={cfg.whisper_beam_size}\n")
    tr.transcribe(np.zeros(16000, dtype="float32"), "es")     # calentamiento

    print(f"{'archivo':<16}{'audio':>8}{'completo':>11}{'troceado':>11}{'trozos':>8}")
    print("-" * 54)
    for wav in wavs:
        audio = load_wav(wav)
        dur = len(audio) / 16000

        t = time.perf_counter()
        tr.transcribe(audio, "es")                            # el camino viejo
        completo = time.perf_counter() - t

        espera, trozos, _ = mide_streaming(tr, audio)
        print(f"{Path(wav).name:<16}{dur:7.1f}s{completo:10.2f}s{espera:10.2f}s{trozos:8d}")


if __name__ == "__main__":
    main()
