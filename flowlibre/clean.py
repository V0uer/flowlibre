"""Interfaz común de los motores de limpieza y selección A/B en runtime."""

from __future__ import annotations

from abc import ABC, abstractmethod


class CleanerError(Exception):
    """Fallo del motor de limpieza, con mensaje apto para mostrar al usuario."""


class Cleaner(ABC):
    """Contrato común: recibe texto crudo, devuelve texto limpio."""

    name: str = "?"

    @abstractmethod
    def clean(self, raw_text: str, format_mode: str) -> str:
        """Limpia el texto. Lanza CleanerError si el motor no puede operar."""

    @abstractmethod
    def check_ready(self) -> str | None:
        """None si el motor está listo; si no, instrucciones para el usuario."""


def get_cleaner(config) -> Cleaner:
    """Devuelve el motor activo según config (se decide en cada dictado)."""
    if config.engine == "claude":
        from .clean_claude import ClaudeCleaner
        return ClaudeCleaner(config)
    from .clean_ollama import OllamaCleaner
    return OllamaCleaner(config)


def strip_llm_wrapping(text: str) -> str:
    """Defensa extra post-modelo: quita comillas envolventes y prefijos tipo
    'Aquí está:' que un modelo desobediente pudiera agregar."""
    cleaned = text.strip()
    prefixes = (
        "aquí está:", "aqui esta:", "texto corregido:", "texto limpio:",
        "corregido:", "here is the corrected text:", "corrected text:",
    )
    lowered = cleaned.lower()
    for p in prefixes:
        if lowered.startswith(p):
            cleaned = cleaned[len(p):].strip()
            break
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"“”'«»":
        cleaned = cleaned[1:-1].strip()
    return cleaned
