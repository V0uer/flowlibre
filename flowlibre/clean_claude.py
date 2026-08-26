"""Motor B — API de Claude (opcional, apagado por defecto).

- POST directo a la API con httpx, modelo por defecto claude-haiku-4-5.
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


# La limpieza reescribe el texto, no lo expande: la salida pesa aproximadamente
# lo mismo que la entrada. Se pide 1.6x para dar aire a la puntuacion y acentos.
# Pedir 2048 fijos hacia esperar tokens que nunca se iban a usar.
def estimate_max_tokens(raw_text: str) -> int:
    """Presupuesto de tokens de salida para limpiar `raw_text`."""
    approx_tokens = len(raw_text) / 3.5      # español: ~3.5 caracteres por token
    return max(64, min(4096, int(approx_tokens * 1.6) + 32))


def classify_error(status: int, body: dict) -> str:
    """Mensaje en español para un status HTTP de la API."""
    if status == 401:
        return "API key de Anthropic inválida o revocada. Revisa ANTHROPIC_API_KEY."
    if status == 429:
        return "Rate limit de la API de Claude alcanzado. Espera un momento o cambia a Motor A."
    if status == 403:
        return ("La API de Claude rechazó la petición (¿sin saldo?). "
                "Revisa Billing en console.anthropic.com o cambia a Motor A.")
    detalle = body.get("error", {}).get("message", "")
    return f"Error de la API de Claude ({status}): {detalle}"


class ClaudeCleaner(Cleaner):
    name = "claude"

    def __init__(self, config) -> None:
        self.config = config
        self._client = None

    def check_ready(self) -> str | None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return NO_KEY_HELP
        return None

    API_URL = "https://api.anthropic.com/v1/messages"

    def _get_client(self):
        """Cliente HTTP reutilizado: conserva la conexion TLS entre dictados."""
        if self._client is None:
            import httpx
            self._client = httpx.Client(
                headers={
                    "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                timeout=self.config.claude_timeout_s,
            )
        return self._client

    def clean(self, raw_text: str, format_mode: str) -> str:
        problem = self.check_ready()
        if problem:
            raise CleanerError(problem)

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

        import httpx

        payload = {
            "model": self.config.claude_model,
            "max_tokens": estimate_max_tokens(raw_text),
            "system": [{
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }],
            "messages": messages,
        }

        r = None
        last_error = None
        for intento in range(2):     # un reintento: la mayoria de las colas largas son transitorias
            try:
                r = self._get_client().post(self.API_URL, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                if intento == 0:
                    continue
                raise CleanerError(
                    "La API de Claude no respondió a tiempo. Verifica tu red o usa "
                    "Motor A (offline)."
                ) from last_error
            if r.status_code == 200:
                break
            # 429 y 5xx son transitorios: valen un reintento. El resto, no.
            if r.status_code in (429, 500, 502, 503, 529) and intento == 0:
                continue
            raise CleanerError(classify_error(r.status_code, r.json()))

        if r is None or r.status_code != 200:
            raise CleanerError(
                "La API de Claude no respondió a tiempo. Verifica tu red o usa "
                "Motor A (offline)."
            )

        text = next(
            (b["text"] for b in r.json().get("content", []) if b.get("type") == "text"), ""
        )
        if not text.strip():
            raise CleanerError("La API de Claude devolvió una respuesta vacía.")
        return strip_llm_wrapping(text)
