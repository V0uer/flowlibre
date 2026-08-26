"""Decide donde cortar el audio para transcribirlo mientras el usuario habla.

La regla: cerrar un trozo en una pausa natural, pero solo si el trozo ya
justifica una pasada de Whisper. El encoder procesa siempre una ventana de 30s
rellene o no, asi que trozos de 3s cuestan lo mismo que trozos de 25s: cortar
muy seguido desperdicia GPU sin ganar latencia. De ahi el minimo de 8s.

Es una funcion pura sobre bloques de numpy: no sabe de microfonos ni de GPU.
Si sabe de hilos, y a proposito: `feed()` lo llama el callback de audio
(un hilo del driver) y `flush()` lo llama el hilo que detecta que el usuario
soltó la tecla de dictado. Ambos pueden coincidir en el tiempo, asi que las
mutaciones de estado compartido estan protegidas con un lock. Es parte del
contrato de esta clase, no un detalle de implementacion.
"""

from __future__ import annotations

import threading

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
        # threshold es un piso ABSOLUTO de RMS sobre audio float32 en [-1, 1],
        # no relativo al piso de ruido del dispositivo. Con ganancia de
        # microfono baja, todo cae por debajo y nunca se detecta silencio;
        # con un piso de ruido alto (p. ej. un mixer que rutea musica o el
        # audio del sistema, como "Wave Link MicrophoneFX"), nunca baja de
        # threshold y el troceador queda forzado a cortar solo por maximo.
        # stats() expone cuantos cortes fueron naturales vs. forzados para
        # que capas mas arriba detecten ese caso.
        self.min_samples = int(min_s * SAMPLE_RATE)
        self.silence_samples = int(silence_s * SAMPLE_RATE)
        self.max_samples = int(max_s * SAMPLE_RATE)
        self.threshold = threshold

        # Relacion entre min_s, silence_s y overlap_s: el buffer de un trozo
        # nuevo NACE con la cola de traslape del trozo anterior ya adentro,
        # asi que lo que de verdad hace falta acumular para llegar a
        # min_samples es "min_samples - overlap_samples" de audio nuevo. Si
        # overlap_samples crece hasta acercarse a "min_samples - silence_samples",
        # el buffer cumple el minimo desde que nace y corta en cuanto aparece
        # la primera pausa de silence_s, sin importar que tan poco audio
        # nuevo haya — el troceador degenera en cortar cada silence_s. Por
        # eso se clampea con un margen (un silence_samples extra de colchon).
        overlap_samples = int(overlap_s * SAMPLE_RATE)
        limite = max(self.min_samples - 2 * self.silence_samples, 0)
        if overlap_samples > limite:
            print(
                f"Chunker: overlap_s={overlap_s}s ({overlap_samples} muestras) "
                f"degeneraria el corte natural; recortado a "
                f"{limite / SAMPLE_RATE:.3f}s ({limite} muestras).",
            )
            overlap_samples = limite
        self.overlap_samples = overlap_samples

        self._lock = threading.Lock()
        self._buffer: list[np.ndarray] = []
        self._length = 0
        self._silence_run = 0
        self._voiced = 0
        self._cortes_naturales = 0
        self._cortes_forzados = 0

    def feed(self, block: np.ndarray) -> np.ndarray | None:
        """Acumula un bloque. Devuelve un trozo cerrado si toca cortar."""
        block = np.asarray(block, dtype="float32").flatten()
        if block.size == 0:
            return None

        # Un hipo del driver de audio (buffer sin inicializar, XRUN) no debe
        # poder tumbar un dictado entero: NaN/Inf se sanean antes de que
        # nada los lea. Sin esto, NaN < threshold es False, el bloque se
        # clasifica como "voz" y nunca se detecta la pausa que cerraria el
        # trozo; ademas los NaN llegarian crudos a ctranslate2.
        if not np.isfinite(block).all():
            block = np.nan_to_num(block, nan=0.0, posinf=0.0, neginf=0.0)

        es_voz = float(np.sqrt((block ** 2).mean())) >= self.threshold

        with self._lock:
            self._buffer.append(block)
            self._length += block.size

            if es_voz:
                self._silence_run = 0
                self._voiced += block.size
            else:
                self._silence_run += block.size

            corte_natural = (
                self._length >= self.min_samples
                and self._silence_run >= self.silence_samples
                and self._voiced > 0
            )
            if corte_natural:
                self._cortes_naturales += 1
                return self._close(None)

            if self._length >= self.max_samples:
                if self._voiced > 0:
                    self._cortes_forzados += 1
                    return self._close(self.max_samples)
                # Maximo alcanzado sin una sola muestra de voz: es puro
                # silencio (o ruido bajo threshold). No hay nada que
                # transcribir — descartar el buffer en vez de emitir un
                # trozo mudo que, si algun dia el VAD de mas arriba no lo
                # filtra, Whisper alucinaria sobre el.
                self._discard()
                return None

        return None

    def _close(self, limite: int | None) -> np.ndarray:
        """Cierra el trozo actual. Debe llamarse con self._lock tomado."""
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
        # La cola es audio que ya salio transcrito dentro de "audio"; el
        # contador de voz arranca en 0 para el trozo que sigue, asi que un
        # flush() inmediato (sin que llegue voz nueva) no repite esa cola.
        self._voiced = 0
        return audio

    def _discard(self) -> None:
        """Tira el buffer mudo al llegar al maximo. Requiere self._lock tomado."""
        audio = np.concatenate(self._buffer)
        cola = audio[-self.overlap_samples:] if self.overlap_samples else np.zeros(0, dtype="float32")
        self._buffer = [cola] if cola.size else []
        self._length = int(cola.size)
        self._silence_run = 0
        self._voiced = 0

    def flush(self) -> np.ndarray:
        """Devuelve lo que quede pendiente y vacia el estado."""
        with self._lock:
            if self._voiced == 0:
                audio = np.zeros(0, dtype="float32")
            else:
                audio = np.concatenate(self._buffer) if self._buffer else np.zeros(0, dtype="float32")
            self._buffer = []
            self._length = 0
            self._silence_run = 0
            self._voiced = 0
            return audio

    def stats(self) -> dict[str, int]:
        """Cuenta de cortes naturales vs. forzados, para diagnosticar un
        threshold que no le sirve a un microfono dado (ver nota en threshold)."""
        with self._lock:
            return {
                "naturales": self._cortes_naturales,
                "forzados": self._cortes_forzados,
            }
