"""Motor A — Ollama local. Gratis, offline, corre en la GPU."""

from __future__ import annotations

import requests

from .clean import Cleaner, CleanerError, strip_llm_wrapping
from .config import load_dictionary
from .prompts import FEW_SHOTS, build_system_prompt

INSTALL_HELP = (
    "Ollama no responde en {url}.\n"
    "1) Instala Ollama desde https://ollama.com/download\n"
    "2) En una terminal: ollama pull {model}\n"
    "3) Asegúrate de que Ollama esté corriendo (ícono en la bandeja)."
)

MODEL_HELP = (
    "El modelo '{model}' no está descargado en Ollama.\n"
    "Ejecuta en una terminal:  ollama pull {model}"
)


class OllamaCleaner(Cleaner):
    name = "ollama"

    def __init__(self, config) -> None:
        self.config = config

    def check_ready(self) -> str | None:
        url = self.config.ollama_url
        model = self.config.ollama_model
        try:
            resp = requests.get(f"{url}/api/tags", timeout=3)
            resp.raise_for_status()
        except requests.RequestException:
            return INSTALL_HELP.format(url=url, model=model)
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        # Ollama registra "qwen2.5:14b-instruct" tal cual; acepta también
        # variantes con sufijo de tag (p.ej. "-q4_K_M").
        if not any(m == model or m.startswith(model) for m in models):
            return MODEL_HELP.format(model=model)
        return None

    def clean(self, raw_text: str, format_mode: str) -> str:
        problem = self.check_ready()
        if problem:
            raise CleanerError(problem)

        system = build_system_prompt(format_mode, load_dictionary())
        messages = [{"role": "system", "content": system}]
        for shot_in, shot_out in FEW_SHOTS:
            messages.append({"role": "user", "content": shot_in})
            messages.append({"role": "assistant", "content": shot_out})
        messages.append({"role": "user", "content": raw_text})

        try:
            resp = requests.post(
                f"{self.config.ollama_url}/api/chat",
                json={
                    "model": self.config.ollama_model,
                    "messages": messages,
                    "stream": False,
                    # keep_alive controla cuánto vive el modelo en VRAM.
                    # "0" lo descarga tras cada uso (libera la GPU).
                    "keep_alive": str(self.config.ollama_keep_alive),
                    "options": {"temperature": 0.1},
                },
                timeout=120,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise CleanerError(f"Error llamando a Ollama: {e}") from e

        content = resp.json().get("message", {}).get("content", "")
        if not content.strip():
            raise CleanerError("Ollama devolvió una respuesta vacía.")
        return strip_llm_wrapping(content)
