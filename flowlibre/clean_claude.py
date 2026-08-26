"""Motor B — API de Claude (opcional, apagado por defecto).

- POST directo a la API con httpx, modelo por defecto claude-haiku-4-5.
- Prompt caching: el system prompt (reglas + diccionario) lleva
  cache_control ephemeral; el texto a limpiar va después, sin cachear.
- La API key se lee SOLO de ANTHROPIC_API_KEY. Nunca de config ni código.
"""

from __future__ import annotations

import math
import os
import time

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
    err = body.get("error") if isinstance(body, dict) else None
    detalle = err.get("message", "") if isinstance(err, dict) else ""
    return f"Error de la API de Claude ({status}): {detalle}"


def _parse_retry_after(value: str | None) -> float | None:
    """Segundos que pide el header `retry-after`, o None si no aplica.

    Solo se aceptan números finitos no-negativos. El header HTTP también
    admite una fecha (p.ej. "Wed, 21 Oct 2026 07:28:00 GMT"), que no
    soportamos: `float()` la rechaza y se devuelve None. Un valor negativo,
    NaN o infinito también se descarta en vez de pasarlo a `time.sleep`,
    que revienta con `ValueError` fuera de `CleanerError` (la misma clase de
    fuga que un cuerpo no-JSON: se pierde el dictado entero).
    """
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


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
            )
        return self._client

    def close(self) -> None:
        """Cierra el cliente HTTP y libera la conexión TLS abierta."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _timeout_for(self, max_tokens: int):
        """Plazos de red para una generacion de `max_tokens` tokens.

        Sin streaming, el cuerpo no empieza a llegar hasta que el modelo termino,
        asi que el plazo de LECTURA tiene que cubrir la generacion completa. Haiku
        ronda los 60 tokens/s; el margen fijo absorbe la cola de la API.
        `claude_timeout_s` pasa a gobernar solo la conexion, que es lo que de
        verdad se cuelga cuando no hay red.

        Supuesto critico: este plazo solo se queda corto si el throughput real
        de Haiku cae por debajo de ~37 tokens/s con la salida pegada al
        presupuesto (`max_tokens`). Si eso pasa, es la unica falla de este
        modulo que ocurre DESPUES de que la generacion ya se cobro y SIN
        reintento (ver ReadTimeout en clean()) — vale la pena revisar este
        numero si Haiku cambia de rendimiento.
        """
        import httpx
        base = self.config.claude_timeout_s
        return httpx.Timeout(
            connect=base,
            read=max(base, max_tokens / 60.0 + 5.0),
            write=base,
            pool=base,
        )

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

        max_tokens = estimate_max_tokens(raw_text)
        payload = {
            "model": self.config.claude_model,
            "max_tokens": max_tokens,
            "system": [{
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }],
            "messages": messages,
        }
        timeout = self._timeout_for(max_tokens)

        r = None
        last_error = None
        for intento in range(2):     # un reintento: la mayoria de las colas largas son transitorias
            try:
                r = self._get_client().post(self.API_URL, json=payload, timeout=timeout)
            except httpx.ReadTimeout as e:
                # La generacion ya ocurrio (y ya se cobro): reintentarla pagaria
                # dos veces por lo mismo, asi que no hay segundo intento.
                raise CleanerError(
                    "La API de Claude tardó demasiado en responder. Si te pasa "
                    "seguido con dictados largos, sube claude_timeout_s en config.yaml."
                ) from e
            except httpx.RequestError as e:
                # Conexion caida, DNS, TLS, decodificacion, redirects: son
                # transitorios, valen un reintento.
                last_error = e
                if intento == 0:
                    continue
                raise CleanerError(
                    "La API de Claude no respondió a tiempo. Verifica tu red o usa "
                    "Motor A (offline)."
                ) from last_error

            if r.status_code == 200:
                break

            try:
                body = r.json()
            except ValueError:
                body = {}
            if not isinstance(body, dict):
                body = {}

            if r.status_code == 429 and intento == 0:
                # Reintentar un rate limit de inmediato casi siempre devuelve
                # otro 429. Se respeta retry-after si es corto; si es largo, o
                # si no viene, no vale la pena seguir esperando el dictado.
                wait = _parse_retry_after(r.headers.get("retry-after"))
                if wait is not None and wait > 2:
                    raise CleanerError(classify_error(r.status_code, body))
                time.sleep(wait if wait is not None else 0.5)
                continue
            # 5xx son transitorios: valen un reintento con un backoff fijo.
            if r.status_code in (500, 502, 503, 529) and intento == 0:
                time.sleep(0.5)
                continue
            raise CleanerError(classify_error(r.status_code, body))

        # Llegar aquí implica r.status_code == 200: cada otra rama del bucle
        # termina en `raise`.
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}

        if data.get("stop_reason") == "max_tokens":
            raise CleanerError(
                "La limpieza salió incompleta (dictado demasiado largo). "
                "Se escribe la transcripción sin limpiar."
            )

        text = next(
            (b["text"] for b in data.get("content", []) if b.get("type") == "text"), ""
        )
        if not text.strip():
            raise CleanerError("La API de Claude devolvió una respuesta vacía.")
        return strip_llm_wrapping(text)
