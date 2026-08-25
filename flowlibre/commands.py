"""Comandos de voz definidos en commands.json.

Dos clases de comandos:
- "insert": si la frase aparece dentro del dictado, se reemplaza por texto
  (ej. "nueva línea" → salto de línea).
- "delete_last" / "uppercase_last": solo aplican si el dictado COMPLETO es el
  comando; operan sobre el último texto inyectado.
"""

from __future__ import annotations

import json
import re
import unicodedata

from .config import COMMANDS_PATH


def _normalize(text: str) -> str:
    """minúsculas, sin acentos ni puntuación — para comparar frases habladas."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class CommandProcessor:
    def __init__(self) -> None:
        self.commands: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        self.commands = {}
        if not COMMANDS_PATH.exists():
            return
        raw = json.loads(COMMANDS_PATH.read_text(encoding="utf-8"))
        for phrase, spec in raw.items():
            if phrase.startswith("_") or not isinstance(spec, dict):
                continue
            self.commands[_normalize(phrase)] = spec

    def match_standalone(self, text: str) -> str | None:
        """Si TODO el dictado es un comando de acción, devuelve la acción."""
        spec = self.commands.get(_normalize(text))
        if spec and spec.get("action") in ("delete_last", "uppercase_last"):
            return spec["action"]
        return None

    def apply_inline(self, text: str) -> str:
        """Reemplaza frases 'insert' dentro del texto (tolerante a puntuación)."""
        for phrase_norm, spec in self.commands.items():
            if spec.get("action") != "insert":
                continue
            # Construye un regex flexible: palabras del comando separadas por
            # espacios, ignorando acentos ya que comparamos contra texto real.
            words = phrase_norm.split()
            pattern = r"[,.\s]*\b" + r"\s+".join(_word_pattern(w) for w in words) + r"\b[,.\s]*"
            text = re.sub(pattern, spec["text"], text, flags=re.IGNORECASE)
        return text


def _word_pattern(word: str) -> str:
    """Regex que acepta la palabra con o sin acentos (linea ↔ línea)."""
    accent_map = {"a": "[aá]", "e": "[eé]", "i": "[ií]", "o": "[oó]", "u": "[uúü]", "n": "[nñ]"}
    return "".join(accent_map.get(c, re.escape(c)) for c in word)
