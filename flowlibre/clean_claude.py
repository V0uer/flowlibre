"""Motor B — API de Claude (opcional, apagado por defecto).

- SDK oficial `anthropic`, modelo por defecto claude-haiku-4-5.
- Prompt caching: el system prompt (reglas + diccionario) lleva
  cache_control ephemeral; el texto a limpiar va después, sin cachear.
- La API key se lee SOLO de ANTHROPIC_API_KEY. Nunca de config ni código.
"""

from __future__ import annotations

import os

from .clean import Cleaner, CleanerError, strip_llm_wrapping
from .config import load_dictionary
from .prompts import FEW_SHOTS, build_system_prompt

NO_KEY_HELP = (
    "El Motor B (Claude) está activo pero falta la variable de entorno ANTHROPIC_API_KEY.\n"
    "1) Crea una API key en https://console.anthropic.com (Settings → API Keys)\n"
    "2) Carga saldo en Billing\n"
    "3) En PowerShell:  setx ANTHROPIC_API_KEY \"tu-key\"  y reinicia FlowLibre.\n"
    "Mientras tanto, cambia a Motor A (Ollama) desde el menú de la bandeja."
)


class ClaudeCleaner(Cleaner):
    name = "claude"

    def __init__(self, config) -> None:
        self.config = config
        self._client = None

    def check_ready(self) -> str | None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return NO_KEY_HELP
        return None

    def _get_client(self):
        if self._client is None:
            import anthropic  # import perezoso: solo si el Motor B se usa
            self._client = anthropic.Anthropic()
        return self._client

    def clean(self, raw_text: str, format_mode: str) -> str:
        problem = self.check_ready()
        if problem:
            raise CleanerError(problem)

        import anthropic

        system_text = build_system_prompt(format_mode, load_dictionary())
        # Few-shots como turnos reales; el último lleva cache_control para que
        # todo el prefijo estable (system + ejemplos) quede cacheado. El texto
        # a limpiar va DESPUÉS del último breakpoint.
        messages = []
        for i, (shot_in, shot_out) in enumerate(FEW_SHOTS):
            messages.append({"role": "user", "content": shot_in})
            assistant_content = [{"type": "text", "text": shot_out}]
            if i == len(FEW_SHOTS) - 1:
                assistant_content[0]["cache_control"] = {"type": "ephemeral"}
            messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": raw_text})

        try:
            response = self._get_client().messages.create(
                model=self.config.claude_model,
                max_tokens=2048,
                system=[{
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=messages,
            )
        except anthropic.AuthenticationError as e:
            raise CleanerError(
                "API key de Anthropic inválida o revocada. Revisa ANTHROPIC_API_KEY."
            ) from e
        except anthropic.RateLimitError as e:
            raise CleanerError(
                "Rate limit de la API de Claude alcanzado. Espera un momento o cambia a Motor A."
            ) from e
        except anthropic.PermissionDeniedError as e:
            # 403 cubre billing_error (sin saldo) y permission_error
            raise CleanerError(
                "La API de Claude rechazó la petición (¿sin saldo?). "
                "Revisa Billing en console.anthropic.com o cambia a Motor A."
            ) from e
        except anthropic.APIStatusError as e:
            raise CleanerError(f"Error de la API de Claude ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise CleanerError(
                "Sin conexión a la API de Claude. Verifica tu red o usa Motor A (offline)."
            ) from e

        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text.strip():
            raise CleanerError("La API de Claude devolvió una respuesta vacía.")
        return strip_llm_wrapping(text)
