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

    def __init__(self, model_name: str, compute_type: str, beam_size: int = 1) -> None:
        self.model_name = model_name
        self.compute_type = compute_type
        self.beam_size = beam_size
        self._model = None
        self._origen = model_name    # ruta/nombre con el que se cargo (ver _resolve_origen)

    def _resolve_origen(self) -> str:
        """Una ruta apunta a un modelo local; un nombre suelto se baja de Hugging Face.

        `models/` esta en .gitignore, asi que en un clon nuevo la carpeta del modelo
        cuantizado NO existe. Sin el aviso, Hugging Face responde con un
        "repository not found" sobre `models/large-v3-turbo-int8` que no le dice a
        nadie que lo que falta es correr el conversor.
        """
        from pathlib import Path

        from .config import ROOT

        candidato = Path(self.model_name)
        if not candidato.is_absolute():
            candidato = ROOT / self.model_name
        if candidato.is_dir():
            return str(candidato)
        if "/" in self.model_name or "\\" in self.model_name:
            print(f"[FlowLibre] No encuentro el modelo local en {candidato}. "
                  f"Genéralo con: .venv/Scripts/python.exe tools/quantize_model.py")
        return self.model_name

    def load(self) -> None:
        """Carga el modelo (descarga la primera vez). Idempotente."""
        if self._model is not None:
            return
        _add_nvidia_dll_dirs()
        from faster_whisper import WhisperModel

        origen = self._resolve_origen()
        self._origen = origen        # lo necesita el reintento en CPU de transcribe()

        try:
            self._model = WhisperModel(
                origen, device="cuda", compute_type=self.compute_type
            )
        except Exception as e:
            # Sin GPU/CUDA utilizable: caer a CPU en vez de crashear.
            print(f"[FlowLibre] GPU no disponible ({e}); usando CPU (más lento).")
            self._model = WhisperModel(origen, device="cpu", compute_type="int8")

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
                beam_size=self.beam_size,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
        except RuntimeError as e:
            # Las DLLs de CUDA se cargan en la PRIMERA inferencia, no al construir
            # el modelo; si fallan aquí, reintentar una vez en CPU.
            print(f"[FlowLibre] GPU falló en inferencia ({e}); reintentando en CPU.")
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self._origen, device="cpu", compute_type="int8")
            segments, info = self._model.transcribe(
                audio,
                language=language,
                vad_filter=True,
                beam_size=self.beam_size,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
        return text, info.language or ""
