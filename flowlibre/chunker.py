"""Decide donde cortar el audio para transcribirlo mientras el usuario habla.

La regla: cerrar un trozo en una pausa natural, pero solo si el trozo ya
justifica una pasada de Whisper. El encoder procesa siempre una ventana de 30s
rellene o no, asi que trozos de 3s cuestan lo mismo que trozos de 25s: cortar
muy seguido desperdicia GPU sin ganar latencia. De ahi el minimo de 8s.

Es una funcion pura sobre bloques de numpy: no sabe de microfonos ni de hilos.
"""

from __future__ import annotations

import numpy as np

from .audio import SAMPLE_RATE


class Chunker:
    def __init__(
        self,
        min_s: float = 8.0,
        silence_s: float = 0.4,
        max_s: float = 25.0,
        overlap_s: float = 0.5,
        threshold: float = 0.01,
    ) -> None:
        self.min_samples = int(min_s * SAMPLE_RATE)
        self.silence_samples = int(silence_s * SAMPLE_RATE)
        self.max_samples = int(max_s * SAMPLE_RATE)
        self.overlap_samples = int(overlap_s * SAMPLE_RATE)
        self.threshold = threshold
        self._buffer: list[np.ndarray] = []
        self._length = 0
        self._silence_run = 0

    def feed(self, block: np.ndarray) -> np.ndarray | None:
        """Acumula un bloque. Devuelve un trozo cerrado si toca cortar."""
        block = np.asarray(block, dtype="float32").flatten()
        if block.size == 0:
            return None

        self._buffer.append(block)
        self._length += block.size

        if float(np.sqrt((block ** 2).mean())) < self.threshold:
            self._silence_run += block.size
        else:
            self._silence_run = 0

        corte_natural = (
            self._length >= self.min_samples
            and self._silence_run >= self.silence_samples
        )
        corte_forzado = self._length >= self.max_samples
        if corte_natural or corte_forzado:
            return self._close(self.max_samples if corte_forzado else None)
        return None

    def _close(self, limite: int | None) -> np.ndarray:
        audio = np.concatenate(self._buffer)
        if limite is not None:
            audio, sobrante = audio[:limite], audio[limite:]
        else:
            sobrante = np.zeros(0, dtype="float32")

        # El siguiente trozo arranca con la cola de este, para que ninguna
        # palabra quede partida entre dos transcripciones.
        cola = audio[-self.overlap_samples:] if self.overlap_samples else np.zeros(0, dtype="float32")
        self._buffer = [cola, sobrante] if sobrante.size else [cola]
        self._length = int(sum(b.size for b in self._buffer))
        self._silence_run = 0
        return audio

    def flush(self) -> np.ndarray:
        """Devuelve lo que quede pendiente y vacia el estado."""
        audio = np.concatenate(self._buffer) if self._buffer else np.zeros(0, dtype="float32")
        self._buffer = []
        self._length = 0
        self._silence_run = 0
        return audio
