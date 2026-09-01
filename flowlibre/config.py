"""Carga y validación de config.yaml, con defaults seguros."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

# Raíz del proyecto: la carpeta que contiene el paquete flowlibre/
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DICTIONARY_PATH = ROOT / "dictionary.txt"
COMMANDS_PATH = ROOT / "commands.json"
HISTORY_PATH = ROOT / "history.jsonl"

DEFAULTS = {
    "hotkey": "ctrl+alt+space",
    "hotkey_mode": "push_to_talk",   # push_to_talk | toggle | hibrido
    "music_hotkey": "f7+f8",         # 2º atajo: dicta un nombre y antepone music_prefix
    "music_prefix": "m!p ",          # prefijo que se pone antes del texto (comando de Discord)
    "music_send_enter": True,        # tras escribir el comando, manda Enter (envía el mensaje)
    "engine": "ollama",              # ollama (Motor A) | claude (Motor B)
    "format_mode": "mensaje",        # mensaje | email | notas | crudo
    "language": "auto",              # auto | es | en
    "microphone": None,
    "whisper_model": "large-v3-turbo",
    "whisper_beam_size": 1,
    "whisper_compute_type": "int8_float16",
    "streaming_stt": True,           # transcribe por trozos mientras hablas
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5:14b-instruct",
    "ollama_keep_alive": "5m",
    "claude_model": "claude-haiku-4-5",
    "claude_timeout_s": 4.0,
    "claude_fallback_to_ollama": True,
    "inject_method": "clipboard",    # clipboard | typing
}

VALID = {
    "hotkey_mode": {"push_to_talk", "toggle", "hibrido"},
    "engine": {"ollama", "claude"},
    "format_mode": {"mensaje", "email", "notas", "crudo"},
    "inject_method": {"clipboard", "typing"},
    "music_send_enter": {True, False},
    "streaming_stt": {True, False},
}


class Config:
    """Configuración viva de la app. `reload()` relee el YAML del disco."""

    def __init__(self) -> None:
        self._data: dict = {}
        self.reload()

    def reload(self) -> None:
        data = copy.deepcopy(DEFAULTS)
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            if not isinstance(loaded, dict):
                raise ValueError("config.yaml no contiene un mapeo YAML válido.")
            data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        # Valores inválidos vuelven al default en vez de tumbar la app.
        for key, valid_values in VALID.items():
            if data[key] not in valid_values:
                data[key] = DEFAULTS[key]
        self._data = data

    def __getattr__(self, name: str):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name)

    def set(self, key: str, value) -> None:
        """Cambia un valor en memoria y lo persiste en config.yaml."""
        if key not in DEFAULTS:
            raise KeyError(key)
        self._data[key] = value
        self._persist(key, value)

    def _persist(self, key: str, value) -> None:
        """Reescribe solo la línea del key en config.yaml, conservando comentarios."""
        if not CONFIG_PATH.exists():
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._data, f, allow_unicode=True)
            return
        lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
        rendered = yaml.safe_dump({key: value}, allow_unicode=True, default_flow_style=False).strip()
        replaced = False
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(f"{key}:"):
                lines[i] = rendered + "\n"
                replaced = True
                break
        if not replaced:
            lines.append(rendered + "\n")
        CONFIG_PATH.write_text("".join(lines), encoding="utf-8")


def load_dictionary() -> list[str]:
    """Términos del diccionario personalizado (ignora comentarios y vacíos)."""
    if not DICTIONARY_PATH.exists():
        return []
    terms = []
    for line in DICTIONARY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms
