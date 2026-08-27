"""Captura de micrófono con sounddevice. 16 kHz mono (formato nativo de Whisper)."""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000

from .chunker import Chunker  # noqa: E402 - chunker importa SAMPLE_RATE de este módulo


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

    def __init__(self, microphone=None, on_chunk=None) -> None:
        self.device = resolve_device(microphone)
        self.on_chunk = on_chunk
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._chunker: Chunker | None = Chunker() if on_chunk else None
        self._lock = threading.Lock()
        self.recording = False
        self.level = 0.0  # RMS del último bloque (0..~1), para el overlay

    def _ingest(self, indata: np.ndarray) -> None:
        """Procesa un bloque del micrófono. Separado del callback de sounddevice
        para poder probarlo sin abrir un stream real."""
        self.level = float(np.sqrt((indata ** 2).mean()))
        with self._lock:
            self._chunks.append(indata.copy())
        if self._chunker is not None:
            trozo = self._chunker.feed(indata.flatten())
            if trozo is not None and self.on_chunk:
                self.on_chunk(trozo)

    def start(self) -> None:
        if self.recording:
            return
        self._chunks = []
        self.level = 0.0
        self._chunker = Chunker() if self.on_chunk else None

        def callback(indata, frames, time_info, status):
            self._ingest(indata)

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

        # ORDEN CRITICO: cerrar el stream ANTES de vaciar el troceador. Mientras el
        # stream siga vivo, el callback de PortAudio sigue llamando a _ingest desde
        # SU PROPIO hilo; un bloque que entre a media de flush() se pierde en
        # silencio y se come la ultima palabra del dictado.
        # Guarda en vez de assert: stop() puede llamarse sin un stream abierto
        # (dos veces seguidas, o desde una prueba). Un assert aqui tumba la app.
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if self._chunker is not None:
            final = self._chunker.flush()
            if final.size and self.on_chunk:
                self.on_chunk(final)
            self._chunker = None

        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            audio = np.concatenate(self._chunks, axis=0).flatten()
            self._chunks = []
        return audio
