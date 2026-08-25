"""Captura de micrófono con sounddevice. 16 kHz mono (formato nativo de Whisper)."""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def resolve_device(microphone) -> int | None:
    """Convierte el valor de config (None, índice o parte del nombre) a índice."""
    if microphone is None:
        return None
    if isinstance(microphone, int):
        return microphone
    needle = str(microphone).lower()
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and needle in dev["name"].lower():
            return i
    return None  # no encontrado → default de Windows


class Recorder:
    """Graba audio entre start() y stop(). stop() devuelve el audio como float32."""

    def __init__(self, microphone=None) -> None:
        self.device = resolve_device(microphone)
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self.recording = False
        self.level = 0.0  # RMS del último bloque (0..~1), para el overlay

    def start(self) -> None:
        if self.recording:
            return
        self._chunks = []
        self.level = 0.0

        def callback(indata, frames, time_info, status):
            self.level = float(np.sqrt((indata ** 2).mean()))
            with self._lock:
                self._chunks.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=callback,
        )
        self._stream.start()
        self.recording = True

    def stop(self) -> np.ndarray:
        if not self.recording:
            return np.zeros(0, dtype=np.float32)
        self.recording = False
        self.level = 0.0
        assert self._stream is not None
        self._stream.stop()
        self._stream.close()
        self._stream = None
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            audio = np.concatenate(self._chunks, axis=0).flatten()
            self._chunks = []
        return audio
