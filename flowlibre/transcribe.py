"""Transcripción local con faster-whisper en GPU (CUDA).

Las DLLs de cuBLAS/cuDNN vienen de los paquetes pip nvidia-*; se agregan al
buscador de DLLs de Windows antes de cargar el modelo (sin CUDA Toolkit global).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE


def _add_nvidia_dll_dirs() -> None:
    """Registra los directorios bin/ de los paquetes pip de NVIDIA (Windows).

    ctranslate2 carga cuBLAS/cuDNN con LoadLibrary plano, que ignora
    os.add_dll_directory — por eso también se antepone cada bin/ al PATH.
    """
    if sys.platform != "win32":
        return
    for sp in sys.path:
        nvidia_dir = Path(sp) / "nvidia"
        if not nvidia_dir.is_dir():
            continue
        for sub in nvidia_dir.iterdir():
            bin_dir = sub / "bin"
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


class Transcriber:
    """Envuelve faster-whisper con carga perezosa del modelo."""

    def __init__(self, model_name: str, compute_type: str) -> None:
        self.model_name = model_name
        self.compute_type = compute_type
        self._model = None

    def load(self) -> None:
        """Carga el modelo (descarga la primera vez). Idempotente."""
        if self._model is not None:
            return
        _add_nvidia_dll_dirs()
        from faster_whisper import WhisperModel

        try:
            self._model = WhisperModel(
                self.model_name, device="cuda", compute_type=self.compute_type
            )
        except Exception as e:
            # Sin GPU/CUDA utilizable: caer a CPU en vez de crashear.
            print(f"[FlowLibre] GPU no disponible ({e}); usando CPU (más lento).")
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray, language: str | None) -> tuple[str, str]:
        """Devuelve (texto, idioma_detectado). language=None → auto-detección."""
        if audio.size < SAMPLE_RATE // 4:  # < 0.25s: ruido, ignorar
            return "", ""
        self.load()
        try:
            segments, info = self._model.transcribe(
                audio,
                language=language,
                vad_filter=True,
                beam_size=5,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
        except RuntimeError as e:
            # Las DLLs de CUDA se cargan en la PRIMERA inferencia, no al construir
            # el modelo; si fallan aquí, reintentar una vez en CPU.
            print(f"[FlowLibre] GPU falló en inferencia ({e}); reintentando en CPU.")
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            segments, info = self._model.transcribe(
                audio, language=language, vad_filter=True, beam_size=5,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
        return text, info.language or ""
