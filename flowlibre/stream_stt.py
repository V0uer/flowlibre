"""Transcribe trozos de audio conforme llegan, en un hilo aparte.

El punto de todo esto: cuando el usuario suelta la tecla, los trozos anteriores
ya estan transcritos y solo queda el ultimo. Por eso la latencia deja de
depender de cuanto hablo.

Un solo hilo consumidor, no un pool: los trozos deben transcribirse en orden
para que el traslape se pueda deduplicar contra el trozo anterior.

Un trozo que falla no cuesta el dictado
---------------------------------------
La transcripcion de un trozo puede reventar por causas locales a ese trozo (la
GPU se quedo sin memoria justo ahi, un reintento en CPU que tampoco cuajo). Si
el hilo muriera con la primera excepcion, el resto de la cola nunca se procesa
y el autor pierde TODO lo que dijo, no el pedazo que fallo. Por eso el try/except
va *dentro* del bucle: se anota el error, se imprime, y se sigue con el
siguiente trozo. La excepcion solo se re-lanza en result() cuando no quedo
ningun texto — ahi el fallo no es de un trozo sino de la maquinaria entera, y
devolver "" en silencio esconderia el problema.
"""

from __future__ import annotations

import queue
import threading

import numpy as np

from .merge import merge_overlap

_FIN = object()      # centinela que le dice al hilo que ya no vienen mas trozos


class StreamingTranscriber:
    def __init__(self, transcriber, language: str | None) -> None:
        self._transcriber = transcriber
        self._language = language
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._text = ""
        self._detected = ""
        self._error: BaseException | None = None
        self._fin_enviado = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, chunk: np.ndarray) -> None:
        """Encola un trozo. No bloquea."""
        self._queue.put(chunk)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _FIN:
                return
            try:
                texto, idioma = self._transcriber.transcribe(item, self._language)
            except BaseException as e:      # un trozo malo no tumba los demas
                print(f"[FlowLibre] trozo no transcrito ({e}); sigo con el resto.")
                with self._lock:
                    if self._error is None:
                        self._error = e
                continue
            with self._lock:
                if idioma and not self._detected:
                    self._detected = idioma
                if texto.strip():
                    self._text = merge_overlap(self._text, texto)

    def result(self, timeout_s: float = 30.0) -> tuple[str, str]:
        """Espera a que se procese todo lo encolado y devuelve (texto, idioma)."""
        if not self._fin_enviado:
            self._fin_enviado = True
            self._queue.put(_FIN)
        self._thread.join(timeout=timeout_s)
        if self._thread.is_alive():
            # Mejor entregar lo que ya hay que colgar la app o perderlo todo.
            print(f"[FlowLibre] la transcripcion excedio {timeout_s}s; entrego lo listo.")
        with self._lock:
            texto, idioma, error = self._text, self._detected, self._error
        if not texto and error is not None:
            raise error
        return texto, idioma
