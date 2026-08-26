# FlowLibre Fase 1 — Latencia y peso (Windows)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un dictado de dos minutos termine tan rápido como uno de veinte segundos, y que FlowLibre pase de 6.7 GB a ~2.4 GB en disco.

**Architecture:** El pipeline actual arranca entero cuando el usuario suelta la tecla. Esta fase lo parte en dos: el audio se trocea en pausas naturales y se transcribe *mientras* el usuario sigue hablando, de modo que al soltar solo queda pendiente el último trozo. Encima de eso van seis ajustes puntuales (modelo turbo, beam 1, timeout en la API, sin `sleep()` fijos) que bajan la mediana. El peso baja cambiando a un modelo cuantizado a int8 y sacando dependencias que nunca se usan.

**Tech Stack:** Python 3.14, faster-whisper 1.2.1 + CTranslate2 (CUDA), numpy, sounddevice, httpx, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-flowlibre-2.0-design.md`

## Global Constraints

- **Solo Windows.** El port a macOS es la Fase 3. No introducir abstracciones de plataforma aquí — eso es la Fase 2.
- **Python 3.14**, venv en `D:\FlowLibre\.venv`. La app se corre con `python -m flowlibre`.
- **Modelo:** `large-v3-turbo`, `beam_size=1`, `condition_on_previous_text=False`. Medido en el spike: 1.20 s vs 4.95 s de `medium`+beam 5 sobre 21 s de audio.
- **Troceo:** mínimo 8 s de audio por trozo, silencio de corte 400 ms, corte forzado a 25 s, traslape 0.5 s. El mínimo es 8 s porque el encoder de Whisper procesa siempre una ventana de 30 s: trozos más cortos desperdician cómputo sin ganar latencia.
- **La API key vive solo en `ANTHROPIC_API_KEY`.** Nunca en config, nunca en código, nunca en un test.
- **`raw/` de los KBs no aplica aquí.** Este repo es código.
- **Criterio de éxito de la fase:** p90 de punta a punta ≤ 2.5 s con la GPU ocupada, y latencia que no crece con la duración del dictado.

## Corrección de alcance respecto al spec

El spec asignó a la Fase 1 "las secciones 6 y 7". La sección 7 incluye **el paquete CUDA descargable**, que necesita el instalador y por lo tanto pertenece a la Fase 5.

**Esta fase toma:** la sección 6 completa, más los recortes de peso que no dependen del instalador (modelo int8, sacar el SDK de `anthropic`, borrar `medium`).
**Se mueve a la Fase 5:** la detección de NVIDIA y la descarga condicional del paquete CUDA.

Peso alcanzable en esta fase: **6.7 GB → ~3.5 GB**. Los ~2.4 GB del spec se alcanzan en la Fase 5, cuando CUDA salga del bundle.

## Estructura de archivos

| Archivo | Responsabilidad | Acción |
|---|---|---|
| `flowlibre/chunker.py` | Decidir dónde cortar el audio. Función pura sobre bloques de numpy, sin hilos ni micrófono. | **Crear** |
| `flowlibre/merge.py` | Unir textos de trozos consecutivos deduplicando el traslape. Función pura sobre strings. | **Crear** |
| `flowlibre/audio.py` | Captura del micrófono. Gana un modo que emite trozos a un callback. | Modificar |
| `flowlibre/transcribe.py` | Envoltura de faster-whisper. Gana transcripción incremental. | Modificar |
| `flowlibre/clean_claude.py` | Limpieza con la API. Gana timeout, reintento y `max_tokens` calculado. Pierde el SDK. | Modificar |
| `flowlibre/inject.py` | Pegado en el cursor. Pierde los `sleep()` fijos. | Modificar |
| `flowlibre/app.py` | Orquestador. Conecta el troceo con la transcripción incremental. | Modificar |
| `flowlibre/config.py` | Defaults nuevos para troceo y beam. | Modificar |
| `tools/quantize_model.py` | Convertir el modelo a int8 una sola vez. Herramienta, no runtime. | **Crear** |
| `tools/bench.py` | Medir latencia de punta a punta contra WAVs de referencia. | **Crear** |
| `tests/` | Suite de pytest. | **Crear** |

`chunker.py` y `merge.py` son archivos nuevos y separados a propósito: son la lógica riesgosa de esta fase y son funciones puras, así que se prueban sin micrófono, sin GPU y sin red.

---

## Task 1: Repositorio, pruebas y arnés de medición

Sin esto no hay forma de saber si el resto funcionó. Establece el punto de comparación **antes** de tocar nada.

**Files:**
- Create: `.gitignore`
- Create: `tests/__init__.py`
- Create: `tools/bench.py`
- Create: `tests/fixtures/README.md`

**Interfaces:**
- Consumes: nada.
- Produces: `tools/bench.py` expone `bench_file(wav_path: str, reps: int = 3) -> dict` que devuelve `{"whisper_s": float, "clean_s": float, "total_s": float}`, y corre como script con `python tools/bench.py`.

- [ ] **Step 1: Inicializar el repositorio**

`D:\FlowLibre` no es un repo git todavía. Desde `D:\FlowLibre`:

```bash
git init
git branch -M main
```

- [ ] **Step 2: Escribir `.gitignore`**

Crear `.gitignore` con exactamente esto:

```gitignore
.venv/
__pycache__/
*.pyc
debug.log
history.jsonl
models/
tests/fixtures/*.wav
```

`history.jsonl` se ignora porque contiene todo lo que el autor ha dictado. `models/` se ignora porque son gigabytes de pesos.

- [ ] **Step 3: Instalar pytest**

```bash
.venv/Scripts/python.exe -m pip install pytest
```

Agregar a `requirements.txt`, al final del archivo:

```
# --- Pruebas ---
pytest>=8.0
```

- [ ] **Step 4: Crear el paquete de pruebas**

Crear `tests/__init__.py` vacío (archivo de cero bytes).

Crear `tests/fixtures/README.md`:

```markdown
# Fixtures de audio

Los `.wav` de esta carpeta son grabaciones de voz real y **no se versionan**
(ver `.gitignore`). Para regenerarlos, grabar 60 segundos hablando normal a
16 kHz mono y guardarlos como `voz_60s.wav`, luego recortar con:

    ffmpeg -i voz_60s.wav -t 21 voz_21s.wav
    ffmpeg -i voz_60s.wav -t 6  voz_6s.wav

Los benchmarks de `tools/bench.py` los necesitan; los tests unitarios no.
```

- [ ] **Step 5: Escribir el arnés de medición**

Crear `tools/bench.py`:

```python
"""Mide la latencia de punta a punta contra WAVs de referencia.

Uso:  .venv/Scripts/python.exe tools/bench.py [ruta.wav ...]

Sin argumentos usa tests/fixtures/voz_{6,21,60}s.wav. Imprime la mediana de
cada etapa para poder comparar antes y despues de un cambio.
"""

from __future__ import annotations

import statistics
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flowlibre.clean import get_cleaner          # noqa: E402
from flowlibre.config import Config              # noqa: E402
from flowlibre.transcribe import Transcriber     # noqa: E402


def load_wav(path: str) -> np.ndarray:
    with wave.open(str(path)) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError(f"{path}: se esperaba 16 kHz mono")
        raw = w.readframes(w.getnframes())
    return (np.frombuffer(raw, dtype="<i2") / 32768.0).astype("float32")


def bench_file(wav_path: str, reps: int = 3) -> dict:
    cfg = Config()
    tr = Transcriber(cfg.whisper_model, cfg.whisper_compute_type)
    cleaner = get_cleaner(cfg)
    audio = load_wav(wav_path)

    tr.transcribe(audio, "es")            # calentamiento: excluye la carga del modelo

    whisper_times, clean_times = [], []
    for _ in range(reps):
        t = time.perf_counter()
        text, _ = tr.transcribe(audio, "es")
        whisper_times.append(time.perf_counter() - t)

        t = time.perf_counter()
        cleaner.clean(text, cfg.format_mode)
        clean_times.append(time.perf_counter() - t)

    w = statistics.median(whisper_times)
    c = statistics.median(clean_times)
    return {"whisper_s": w, "clean_s": c, "total_s": w + c}


def main() -> None:
    paths = sys.argv[1:] or [
        str(ROOT / "tests" / "fixtures" / f"voz_{n}s.wav") for n in (6, 21, 60)
    ]
    print(f"{'archivo':<20} {'whisper':>9} {'limpieza':>9} {'total':>9}")
    print("-" * 50)
    for p in paths:
        if not Path(p).exists():
            print(f"{Path(p).name:<20} {'(falta)':>9}")
            continue
        r = bench_file(p)
        print(f"{Path(p).name:<20} {r['whisper_s']:8.2f}s {r['clean_s']:8.2f}s {r['total_s']:8.2f}s")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Grabar los fixtures y capturar la línea base**

Colocar en `tests/fixtures/` una grabación propia de 60 s a 16 kHz mono llamada `voz_60s.wav`, y generar los recortes:

```bash
ffmpeg -i tests/fixtures/voz_60s.wav -t 21 tests/fixtures/voz_21s.wav
ffmpeg -i tests/fixtures/voz_60s.wav -t 6  tests/fixtures/voz_6s.wav
```

Correr el benchmark **antes de cambiar nada** y guardar la salida:

```bash
.venv/Scripts/python.exe tools/bench.py | tee docs/superpowers/baseline-2026-08-25.txt
```

Esta salida es el número contra el que se compara todo lo demás. Con la config actual (`medium`, beam 5) se espera alrededor de 5 s para el WAV de 21 s.

- [ ] **Step 7: Commit**

```bash
git add .gitignore requirements.txt tests tools docs
git commit -m "chore: inicializar repo, pytest y arnes de medicion de latencia"
```

---

## Task 2: Modelo turbo y beam configurable

El cambio de mejor relación beneficio/riesgo: 4x más rápido, medido.

**Files:**
- Modify: `flowlibre/config.py` (bloque `DEFAULTS`)
- Modify: `flowlibre/transcribe.py:66-82` (llamadas a `self._model.transcribe`)
- Modify: `config.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `Config` de la Task 1.
- Produces: `Config.whisper_beam_size: int` (default `1`) y `Config.whisper_model` con default `"large-v3-turbo"`. `Transcriber.transcribe()` conserva su firma `(audio: np.ndarray, language: str | None) -> tuple[str, str]`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_config.py`:

```python
from flowlibre.config import DEFAULTS


def test_default_model_is_turbo():
    assert DEFAULTS["whisper_model"] == "large-v3-turbo"


def test_beam_size_default_is_one():
    assert DEFAULTS["whisper_beam_size"] == 1
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: FAIL — `assert 'medium' == 'large-v3-turbo'` y `KeyError: 'whisper_beam_size'`

- [ ] **Step 3: Actualizar los defaults**

En `flowlibre/config.py`, dentro de `DEFAULTS`, reemplazar la línea `"whisper_model": "medium",` por:

```python
    "whisper_model": "large-v3-turbo",
    "whisper_beam_size": 1,
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Usar el beam configurable en la transcripción**

En `flowlibre/transcribe.py`, cambiar el constructor para aceptar el beam:

```python
    def __init__(self, model_name: str, compute_type: str, beam_size: int = 1) -> None:
        self.model_name = model_name
        self.compute_type = compute_type
        self.beam_size = beam_size
        self._model = None
```

En el mismo archivo, en `transcribe()`, reemplazar **ambas** llamadas a `self._model.transcribe(...)` (la del `try` y la del `except RuntimeError`) por esta forma:

```python
            segments, info = self._model.transcribe(
                audio,
                language=language,
                vad_filter=True,
                beam_size=self.beam_size,
                condition_on_previous_text=False,
            )
```

`condition_on_previous_text=False` importa doble: acelera, y evita que un trozo arrastre alucinaciones al siguiente cuando llegue el troceo de la Task 6.

- [ ] **Step 6: Pasar el beam desde la app**

En `flowlibre/app.py`, hay dos construcciones de `Transcriber` (una en `__init__`, otra en `reload_config`). Agregar el tercer argumento a ambas:

```python
        self.transcriber = Transcriber(
            self.config.whisper_model, self.config.whisper_compute_type,
            self.config.whisper_beam_size,
        )
```

En `reload_config`, la condición que decide si reconstruir el modelo también debe mirar el beam:

```python
        if (self.transcriber.model_name != self.config.whisper_model
                or self.transcriber.compute_type != self.config.whisper_compute_type
                or self.transcriber.beam_size != self.config.whisper_beam_size):
```

- [ ] **Step 7: Actualizar `config.yaml`**

Reemplazar el bloque de Whisper por:

```yaml
# --- Whisper (transcripción local en GPU) ---
# Modelos: "small" (~0.5GB VRAM) | "medium" (~1.5GB) | "large-v3-turbo" (recomendado:
# más preciso que medium y ~4x más rápido) | "large-v3" (~3.5GB)
whisper_model: "large-v3-turbo"
whisper_compute_type: "int8_float16"
# Búsqueda del decodificador. 1 = más rápido. Subir a 5 solo si la calidad no alcanza.
whisper_beam_size: 1
```

- [ ] **Step 8: Medir la mejora**

```bash
.venv/Scripts/python.exe tools/bench.py
```

Comparar contra la línea base **medida** en la Task 1
(`docs/superpowers/baseline-2026-08-25.txt`), columna `whisper`:

| archivo | línea base (medium, beam 5) | esperado (turbo, beam 1) |
|---|---:|---:|
| `voz_6s.wav` | 0.18 s | 0.10 s o menos |
| `voz_21s.wav` | 0.69 s | 0.35 s o menos |
| `voz_60s.wav` | 3.69 s | 1.50 s o menos |

**Los números absolutos dependen mucho de qué tan ocupada esté la GPU** — el autor juega en
esa máquina, y la misma medición varía hasta 7x según lo que haya corriendo. Antes de
medir, correr `nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader` y anotar el
valor en el reporte.

**El criterio que decide es la razón, no el valor absoluto:** `voz_60s.wav` debe mejorar
al menos **2x** contra la línea base. Si mejora menos, parar y revisar que el modelo turbo
se haya descargado de verdad (la primera corrida lo baja y tarda varios minutos) y que no
se haya caído a CPU — un mensaje `GPU no disponible` en la salida delata eso último.

- [ ] **Step 9: Commit**

```bash
git add flowlibre/config.py flowlibre/transcribe.py flowlibre/app.py config.yaml tests/test_config.py
git commit -m "perf: usar large-v3-turbo con beam 1 (4x mas rapido, medido)"
```

---

## Task 3: Limpieza con httpx — timeout, reintento y `max_tokens` real

Aquí vive la cola de 9 segundos: hoy la llamada a la API no tiene timeout, así que espera lo que la API tarde. En la misma pasada se cambia el SDK de `anthropic` por un POST directo, porque arrastra `pydantic`, `google` y `hf_xet` (~25 MB) para usar un solo endpoint.

**Esta tarea fusiona lo que el plan original tenía como Tasks 3 y 10.** Se juntaron porque ambas reescribían el mismo método `clean()`: hacerlo en dos pasadas significaba escribir el manejo de errores del SDK para borrarlo acto seguido.

**Files:**
- Modify: `flowlibre/clean_claude.py` (`_get_client` y `clean` completos)
- Modify: `flowlibre/config.py` (`DEFAULTS`)
- Modify: `flowlibre/app.py` (`_check_engine`)
- Modify: `config.yaml`
- Modify: `requirements.txt`
- Test: `tests/test_clean_claude.py`

**Interfaces:**
- Consumes: `Config` (Task 1), `Cleaner` / `CleanerError` / `strip_llm_wrapping` de `flowlibre/clean.py` (ya existen).
- Produces: `flowlibre.clean_claude.estimate_max_tokens(raw_text: str) -> int` y `flowlibre.clean_claude.classify_error(status: int, body: dict) -> str`. `ClaudeCleaner.clean(raw_text, format_mode) -> str` conserva su firma y sus mensajes de error visibles.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_clean_claude.py`:

```python
from flowlibre.clean_claude import classify_error, estimate_max_tokens


def test_short_text_gets_small_budget():
    # ~50 caracteres no necesitan 2048 tokens de salida
    assert estimate_max_tokens("Hola, como estas el dia de hoy amigo.") < 200


def test_budget_scales_with_input():
    corto = estimate_max_tokens("a" * 100)
    largo = estimate_max_tokens("a" * 2000)
    assert largo > corto


def test_budget_has_a_floor():
    # Un dictado de una palabra no debe quedarse sin presupuesto
    assert estimate_max_tokens("Hola") >= 64


def test_budget_has_a_ceiling():
    # Un dictado enorme no debe pedir un presupuesto ilimitado
    assert estimate_max_tokens("a" * 100_000) <= 4096


def test_401_habla_de_la_api_key():
    msg = classify_error(401, {"error": {"message": "invalid x-api-key"}})
    assert "API key" in msg


def test_429_habla_de_rate_limit():
    assert "Rate limit" in classify_error(429, {})


def test_403_sugiere_revisar_saldo():
    assert "saldo" in classify_error(403, {})


def test_otros_codigos_incluyen_el_status():
    assert "500" in classify_error(500, {"error": {"message": "boom"}})
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_clean_claude.py -v`
Expected: FAIL — `ImportError: cannot import name 'classify_error'`

- [ ] **Step 3: Implementar las dos funciones puras**

En `flowlibre/clean_claude.py`, agregar después de la constante `NO_KEY_HELP`:

```python
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
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_clean_claude.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Agregar el timeout a la configuración**

En `flowlibre/config.py`, dentro de `DEFAULTS`, después de `"claude_model"`:

```python
    "claude_timeout_s": 4.0,
```

En `config.yaml`, después de la línea de `claude_model`:

```yaml
# Segundos que se espera a la API antes de reintentar una vez y luego rendirse.
# Sin esto, un request colgado bloquea el dictado indefinidamente.
claude_timeout_s: 4.0
```

- [ ] **Step 6: Reemplazar el cliente del SDK por httpx**

En `flowlibre/clean_claude.py`, reemplazar el método `_get_client` completo por:

```python
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
```

- [ ] **Step 7: Reescribir la llamada a la API**

En `flowlibre/clean_claude.py`, en el método `clean`:

Borrar la línea `import anthropic` que está después del bloque `if problem: raise CleanerError(problem)`.

Reemplazar todo lo que va desde `try:` (el que contiene `response = self._get_client().messages.create(...)`) hasta el último `except anthropic.APIConnectionError as e: ... from e` inclusive, por:

```python
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
```

Dejar intactos el `if not text.strip(): raise CleanerError(...)` y el `return strip_llm_wrapping(text)` del final del método.

También actualizar el docstring del módulo, arriba del todo: donde dice
`- SDK oficial \`anthropic\`, modelo por defecto claude-haiku-4-5.` poner
`- POST directo a la API con httpx, modelo por defecto claude-haiku-4-5.`

- [ ] **Step 8: Precalentar la conexión al arrancar**

En `flowlibre/app.py`, en `_check_engine`, agregar al final del método:

```python
        # Abrir el cliente HTTP ahora, para no pagar el handshake TLS en el
        # primer dictado.
        cleaner = get_cleaner(self.config)
        if hasattr(cleaner, "_get_client"):
            try:
                cleaner._get_client()
            except Exception:
                pass
```

- [ ] **Step 9: Actualizar las dependencias**

En `requirements.txt`, reemplazar el bloque que dice
`# --- Motor B: API de Claude (opcional, apagado por defecto) ---` y su línea
`anthropic>=0.40` por:

```
# --- Motor B: API de Claude ---
# Se habla el endpoint directo con httpx: el SDK oficial arrastra pydantic,
# google y hf_xet (~25 MB) para un solo POST.
httpx>=0.27
```

Instalar httpx y desinstalar lo que sobra:

```bash
.venv/Scripts/python.exe -m pip install httpx
.venv/Scripts/python.exe -m pip uninstall -y anthropic
```

- [ ] **Step 10: Correr los tests y probar de verdad**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS (10 passed — 2 de config, 8 de este archivo)

Luego, con `ANTHROPIC_API_KEY` puesta en el entorno, verificar que la limpieza sigue
funcionando de punta a punta:

```bash
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); from flowlibre.config import Config; from flowlibre.clean_claude import ClaudeCleaner; print(ClaudeCleaner(Config()).clean('hola oye necesito que me mandes el reporte de agosto porfa', 'mensaje'))"
```

Expected: imprime el texto limpio y puntuado. Si imprime un `CleanerError`, revisar que
`ANTHROPIC_API_KEY` esté en el entorno de esa terminal.

- [ ] **Step 11: Commit**

```bash
git add flowlibre/clean_claude.py flowlibre/config.py flowlibre/app.py config.yaml requirements.txt tests/test_clean_claude.py
git commit -m "perf: httpx con timeout de 4s, un reintento y max_tokens calculado"
```

---

## Task 4: Inyección sin esperas fijas

200 ms fijos por dictado, esperando "por si acaso".

**Files:**
- Modify: `flowlibre/inject.py:44-70`
- Test: `tests/test_inject.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `flowlibre.inject.wait_for_clipboard(expected: str, timeout_s: float = 0.5) -> bool`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_inject.py`:

```python
import time

import flowlibre.inject as inject


def test_returns_true_as_soon_as_clipboard_matches(monkeypatch):
    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: "hola")
    t = time.perf_counter()
    assert inject.wait_for_clipboard("hola", timeout_s=1.0) is True
    # Debe volver de inmediato, no dormir el timeout completo
    assert time.perf_counter() - t < 0.1


def test_returns_false_after_timeout_when_never_matches(monkeypatch):
    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: "otra cosa")
    t = time.perf_counter()
    assert inject.wait_for_clipboard("hola", timeout_s=0.2) is False
    assert time.perf_counter() - t >= 0.2


def test_tolerates_clipboard_read_failures(monkeypatch):
    # _get_clipboard_text devuelve None cuando el portapapeles esta ocupado
    estados = iter([None, None, "hola"])
    monkeypatch.setattr(inject, "_get_clipboard_text", lambda: next(estados, "hola"))
    assert inject.wait_for_clipboard("hola", timeout_s=1.0) is True
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/test_inject.py -v`
Expected: FAIL — `AttributeError: module 'flowlibre.inject' has no attribute 'wait_for_clipboard'`

- [ ] **Step 3: Implementar la espera activa**

En `flowlibre/inject.py`, agregar después de `_set_clipboard_text`:

```python
def wait_for_clipboard(expected: str, timeout_s: float = 0.5) -> bool:
    """Espera a que el portapapeles contenga `expected`. True si llego a tiempo.

    Reemplaza los sleep() fijos: en la practica el portapapeles se asienta en
    pocos milisegundos, pero bajo carga puede tardar mas. Sondear cuesta lo que
    de verdad tarda, no siempre lo peor.
    """
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if _get_clipboard_text() == expected:
            return True
        time.sleep(0.005)
    return False
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/Scripts/python.exe -m pytest tests/test_inject.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Usar la espera en `inject_text`**

En `flowlibre/inject.py`, reemplazar el cuerpo de la rama "clipboard" de `inject_text` por:

```python
    # clipboard (default)
    original = _get_clipboard_text()
    _set_clipboard_text(text)
    wait_for_clipboard(text, timeout_s=0.5)   # antes: sleep(0.05) a ciegas
    keyboard.send("ctrl+v")
    # Dar a la app destino un margen corto para leer el portapapeles antes de
    # restaurarlo. Esto no se puede sondear: no hay forma de saber si ya leyo.
    time.sleep(0.05)
    if original is not None:
        try:
            _set_clipboard_text(original)
        except Exception:
            pass  # si falla la restauración, el texto dictado queda en el clipboard
```

Nota para quien implementa: el `sleep(0.05)` después del `Ctrl+V` **se queda**. No hay señal observable de que la app destino ya leyó el portapapeles, así que sondear no aplica. Lo que se elimina son los 150 ms del original y los 50 ms previos al pegado.

- [ ] **Step 6: Correr toda la suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS (13 passed)

- [ ] **Step 7: Commit**

```bash
git add flowlibre/inject.py tests/test_inject.py
git commit -m "perf: sondear el portapapeles en vez de esperar 200ms fijos"
```

---

## Task 5: El troceador (función pura)

La pieza riesgosa de la fase. Se aísla en su propio archivo, sin micrófono ni hilos, para poder probarla a fondo.

**Files:**
- Create: `flowlibre/chunker.py`
- Test: `tests/test_chunker.py`

**Interfaces:**
- Consumes: `flowlibre.audio.SAMPLE_RATE` (16000).
- Produces: `Chunker(min_s=8.0, silence_s=0.4, max_s=25.0, overlap_s=0.5, threshold=0.01)` con dos métodos:
  - `feed(block: np.ndarray) -> np.ndarray | None` — devuelve un trozo cerrado, o `None` si aún no toca cortar.
  - `flush() -> np.ndarray` — devuelve lo que quede pendiente (el trozo final).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_chunker.py`:

```python
import numpy as np
import pytest

from flowlibre.audio import SAMPLE_RATE
from flowlibre.chunker import Chunker


def habla(segundos: float) -> np.ndarray:
    """Audio fuerte (por encima del umbral de silencio)."""
    n = int(segundos * SAMPLE_RATE)
    return (np.random.default_rng(0).standard_normal(n) * 0.2).astype("float32")


def silencio(segundos: float) -> np.ndarray:
    n = int(segundos * SAMPLE_RATE)
    return np.zeros(n, dtype="float32")


def alimentar(ch: Chunker, audio: np.ndarray, bloque_s: float = 0.1):
    """Mete audio en bloques como lo haria el microfono. Devuelve los trozos emitidos."""
    salida = []
    paso = int(bloque_s * SAMPLE_RATE)
    for i in range(0, len(audio), paso):
        trozo = ch.feed(audio[i:i + paso])
        if trozo is not None:
            salida.append(trozo)
    return salida


def test_no_corta_antes_del_minimo():
    ch = Chunker()
    # 5s de habla y luego una pausa larga: aun no llega al minimo de 8s
    trozos = alimentar(ch, np.concatenate([habla(5), silencio(1.0)]))
    assert trozos == []


def test_corta_en_silencio_despues_del_minimo():
    ch = Chunker()
    trozos = alimentar(ch, np.concatenate([habla(9), silencio(0.6), habla(2)]))
    assert len(trozos) == 1
    # El trozo debe cubrir al menos los 9s de habla
    assert len(trozos[0]) >= 9 * SAMPLE_RATE


def test_no_corta_en_pausas_cortas():
    ch = Chunker()
    # Pausa de 150ms: por debajo del umbral de 400ms, es una pausa de respiracion
    trozos = alimentar(ch, np.concatenate([habla(9), silencio(0.15), habla(3)]))
    assert trozos == []


def test_corta_forzado_al_maximo_sin_silencio():
    ch = Chunker()
    # 30s continuos sin una sola pausa: debe cortar solo a los 25s
    trozos = alimentar(ch, habla(30))
    assert len(trozos) == 1
    assert len(trozos[0]) == pytest.approx(25 * SAMPLE_RATE, rel=0.05)


def test_los_trozos_se_traslapan():
    ch = Chunker(overlap_s=0.5)
    alimentar(ch, np.concatenate([habla(9), silencio(0.6)]))
    resto = ch.flush()
    # Tras cerrar un trozo, el siguiente arranca con 0.5s del anterior
    assert len(resto) >= 0.5 * SAMPLE_RATE


def test_flush_devuelve_lo_pendiente():
    ch = Chunker()
    alimentar(ch, habla(4))
    resto = ch.flush()
    assert len(resto) == pytest.approx(4 * SAMPLE_RATE, rel=0.05)


def test_flush_en_vacio_no_truena():
    assert len(Chunker().flush()) == 0
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_chunker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flowlibre.chunker'`

- [ ] **Step 3: Implementar el troceador**

Crear `flowlibre/chunker.py`:

```python
"""Decide donde cortar el audio para transcribirlo mientras el usuario habla.

La regla: cerrar un trozo en una pausa natural, pero solo si el trozo ya
justifica una pasada de Whisper. El encoder procesa siempre una ventana de 30s
rellene o no, asi que trozos de 3s cuestan lo mismo que trozos de 25s: cortar
muy seguido desperdicia GPU sin ganar latencia. De ahi el minimo de 8s.

Es una funcion pura sobre bloques de numpy: no sabe de microfonos ni de hilos.
"""

from __future__ import annotations

import numpy as np

from .audio import SAMPLE_RATE


class Chunker:
    def __init__(
        self,
        min_s: float = 8.0,
        silence_s: float = 0.4,
        max_s: float = 25.0,
        overlap_s: float = 0.5,
        threshold: float = 0.01,
    ) -> None:
        self.min_samples = int(min_s * SAMPLE_RATE)
        self.silence_samples = int(silence_s * SAMPLE_RATE)
        self.max_samples = int(max_s * SAMPLE_RATE)
        self.overlap_samples = int(overlap_s * SAMPLE_RATE)
        self.threshold = threshold
        self._buffer: list[np.ndarray] = []
        self._length = 0
        self._silence_run = 0

    def feed(self, block: np.ndarray) -> np.ndarray | None:
        """Acumula un bloque. Devuelve un trozo cerrado si toca cortar."""
        block = np.asarray(block, dtype="float32").flatten()
        if block.size == 0:
            return None

        self._buffer.append(block)
        self._length += block.size

        if float(np.sqrt((block ** 2).mean())) < self.threshold:
            self._silence_run += block.size
        else:
            self._silence_run = 0

        corte_natural = (
            self._length >= self.min_samples
            and self._silence_run >= self.silence_samples
        )
        corte_forzado = self._length >= self.max_samples
        if corte_natural or corte_forzado:
            return self._close(self.max_samples if corte_forzado else None)
        return None

    def _close(self, limite: int | None) -> np.ndarray:
        audio = np.concatenate(self._buffer)
        if limite is not None:
            audio, sobrante = audio[:limite], audio[limite:]
        else:
            sobrante = np.zeros(0, dtype="float32")

        # El siguiente trozo arranca con la cola de este, para que ninguna
        # palabra quede partida entre dos transcripciones.
        cola = audio[-self.overlap_samples:] if self.overlap_samples else np.zeros(0, dtype="float32")
        self._buffer = [cola, sobrante] if sobrante.size else [cola]
        self._length = int(sum(b.size for b in self._buffer))
        self._silence_run = 0
        return audio

    def flush(self) -> np.ndarray:
        """Devuelve lo que quede pendiente y vacia el estado."""
        audio = np.concatenate(self._buffer) if self._buffer else np.zeros(0, dtype="float32")
        self._buffer = []
        self._length = 0
        self._silence_run = 0
        return audio
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_chunker.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add flowlibre/chunker.py tests/test_chunker.py
git commit -m "feat: troceador de audio que corta en pausas naturales"
```

---

## Task 6: Unir trozos deduplicando el traslape

Los trozos se traslapan 0.5 s a propósito, así que el texto del traslape sale dos veces. Esto lo arregla.

**Files:**
- Create: `flowlibre/merge.py`
- Test: `tests/test_merge.py`

**Interfaces:**
- Consumes: nada.
- Produces: `flowlibre.merge.merge_overlap(prev: str, nxt: str, max_words: int = 15) -> str`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_merge.py`:

```python
from flowlibre.merge import merge_overlap


def test_une_sin_traslape():
    assert merge_overlap("hola que tal", "todo bien") == "hola que tal todo bien"


def test_elimina_el_traslape_repetido():
    prev = "necesito que me ayudes con el reporte"
    nxt = "con el reporte de agosto por favor"
    assert merge_overlap(prev, nxt) == "necesito que me ayudes con el reporte de agosto por favor"


def test_ignora_diferencias_de_puntuacion_y_mayusculas():
    prev = "vamos a revisar el Presupuesto,"
    nxt = "el presupuesto de este mes"
    assert merge_overlap(prev, nxt) == "vamos a revisar el Presupuesto, de este mes"


def test_prefiere_el_traslape_mas_largo():
    prev = "uno dos tres uno dos tres"
    nxt = "uno dos tres cuatro"
    assert merge_overlap(prev, nxt) == "uno dos tres uno dos tres cuatro"


def test_maneja_lados_vacios():
    assert merge_overlap("", "hola") == "hola"
    assert merge_overlap("hola", "") == "hola"
    assert merge_overlap("", "") == ""


def test_no_borra_repeticiones_legitimas_lejanas():
    # "de" aparece en ambos pero no es traslape: no debe comerse nada
    prev = "el reporte de agosto"
    nxt = "manda copia de eso"
    assert merge_overlap(prev, nxt) == "el reporte de agosto manda copia de eso"
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_merge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flowlibre.merge'`

- [ ] **Step 3: Implementar la unión**

Crear `flowlibre/merge.py`:

```python
"""Une textos de trozos consecutivos, quitando el traslape duplicado.

Los trozos de audio se traslapan medio segundo para que ninguna palabra quede
partida. El precio es que esas palabras se transcriben dos veces. Aqui se
busca el sufijo mas largo de un trozo que coincida con el prefijo del
siguiente, y se pega solo una vez.

La comparacion normaliza mayusculas y puntuacion porque Whisper puntua distinto
segun el contexto: el mismo audio puede salir "el presupuesto," en un trozo y
"El presupuesto" en el otro.
"""

from __future__ import annotations

import unicodedata

_PUNCT = {"Pc", "Pd", "Pe", "Pf", "Pi", "Po", "Ps"}


def _norm(word: str) -> str:
    """Palabra sin puntuacion ni mayusculas, para comparar."""
    return "".join(c for c in word.lower() if unicodedata.category(c) not in _PUNCT)


def merge_overlap(prev: str, nxt: str, max_words: int = 15) -> str:
    """Pega `nxt` despues de `prev` sin repetir el traslape."""
    if not prev.strip():
        return nxt.strip()
    if not nxt.strip():
        return prev.strip()

    prev_words = prev.split()
    next_words = nxt.split()
    limite = min(max_words, len(prev_words), len(next_words))

    # De mayor a menor: el traslape mas largo es el correcto. Buscar de menor a
    # mayor encontraria coincidencias de una palabra que son casualidad.
    for k in range(limite, 0, -1):
        cola = [_norm(w) for w in prev_words[-k:]]
        cabeza = [_norm(w) for w in next_words[:k]]
        if cola == cabeza:
            return " ".join(prev_words + next_words[k:])

    return " ".join(prev_words + next_words)
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_merge.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add flowlibre/merge.py tests/test_merge.py
git commit -m "feat: unir trozos consecutivos deduplicando el traslape"
```

---

## Task 7: Grabación con troceo

Conecta el troceador al micrófono, sin romper el modo actual.

**Files:**
- Modify: `flowlibre/audio.py` (clase `Recorder`)
- Test: `tests/test_recorder.py`

**Interfaces:**
- Consumes: `Chunker` de la Task 5.
- Produces: `Recorder(microphone=None, on_chunk: Callable[[np.ndarray], None] | None = None)`. Cuando `on_chunk` es `None`, `Recorder` se comporta **exactamente** como hoy. `stop()` sigue devolviendo el audio completo en ambos modos.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_recorder.py`:

```python
import numpy as np

from flowlibre.audio import SAMPLE_RATE, Recorder


def habla(segundos: float) -> np.ndarray:
    n = int(segundos * SAMPLE_RATE)
    return (np.random.default_rng(1).standard_normal((n, 1)) * 0.2).astype("float32")


def silencio(segundos: float) -> np.ndarray:
    return np.zeros((int(segundos * SAMPLE_RATE), 1), dtype="float32")


def test_sin_callback_no_emite_trozos():
    r = Recorder()
    r._chunks = []
    r.recording = True
    r._ingest(habla(20))          # sin on_chunk, solo acumula
    assert r.stop().size >= 20 * SAMPLE_RATE


def test_con_callback_emite_trozos_durante_la_grabacion():
    emitidos = []
    r = Recorder(on_chunk=emitidos.append)
    r._chunks = []
    r.recording = True
    for bloque in (habla(9), silencio(0.6), habla(2)):
        r._ingest(bloque)
    assert len(emitidos) == 1
    assert emitidos[0].size >= 9 * SAMPLE_RATE


def test_stop_devuelve_el_audio_completo_aunque_haya_troceado():
    emitidos = []
    r = Recorder(on_chunk=emitidos.append)
    r._chunks = []
    r.recording = True
    for bloque in (habla(9), silencio(0.6), habla(3)):
        r._ingest(bloque)
    completo = r.stop()
    # El audio entero sigue disponible: 9 + 0.6 + 3 segundos
    assert completo.size >= 12 * SAMPLE_RATE
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_recorder.py -v`
Expected: FAIL — `TypeError: Recorder.__init__() got an unexpected keyword argument 'on_chunk'`

- [ ] **Step 3: Extraer la ingesta de audio a un método**

En `flowlibre/audio.py`, cambiar el constructor de `Recorder`:

```python
    def __init__(self, microphone=None, on_chunk=None) -> None:
        self.device = resolve_device(microphone)
        self.on_chunk = on_chunk
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._chunker: Chunker | None = None
        self._lock = threading.Lock()
        self.recording = False
        self.level = 0.0  # RMS del último bloque (0..~1), para el overlay
```

Agregar el import al inicio del archivo:

```python
from .chunker import Chunker
```

Agregar el método `_ingest`, que es lo que el callback del stream va a llamar:

```python
    def _ingest(self, indata: np.ndarray) -> None:
        """Procesa un bloque del micrófono. Separado del callback de sounddevice
        para poder probarlo sin abrir un stream real."""
        self.level = float(np.sqrt((indata ** 2).mean()))
        with self._lock:
            self._chunks.append(indata.copy())
        if self._chunker is not None:
            trozo = self._chunker.feed(indata.flatten())
            if trozo is not None and self.on_chunk:
                self.on_chunk(trozo)
```

- [ ] **Step 4: Usar `_ingest` desde el stream y crear el troceador en `start`**

En `flowlibre/audio.py`, en `start()`, reemplazar la definición del callback y agregar la creación del troceador:

```python
    def start(self) -> None:
        if self.recording:
            return
        self._chunks = []
        self.level = 0.0
        self._chunker = Chunker() if self.on_chunk else None

        def callback(indata, frames, time_info, status):
            self._ingest(indata)

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=callback,
        )
        self._stream.start()
        self.recording = True
```

- [ ] **Step 5: Emitir el trozo final en `stop` y quitar el `assert` del stream**

En `flowlibre/audio.py`, reemplazar el cuerpo de `stop()` desde `self.recording = False`
hasta `self._stream = None` por:

```python
        self.recording = False
        self.level = 0.0

        if self._chunker is not None:
            final = self._chunker.flush()
            if final.size and self.on_chunk:
                self.on_chunk(final)
            self._chunker = None

        # Guarda en vez de assert: stop() puede llamarse sin un stream abierto
        # (dos veces seguidas, o desde una prueba). Un assert aqui tumba la app.
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
```

El resto de `stop()` (el bloque `with self._lock:` que concatena y devuelve el audio)
queda igual.

**Por qué el cambio del `assert`:** los tests de esta tarea llaman a `stop()` sin haber
abierto un stream real. Con el `assert` original reventarían con `AssertionError` aunque
el troceo estuviera perfecto.

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_recorder.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Correr toda la suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS (29 passed)

- [ ] **Step 8: Commit**

```bash
git add flowlibre/audio.py tests/test_recorder.py
git commit -m "feat: Recorder puede emitir trozos durante la grabacion"
```

---

## Task 8: Transcripción incremental

Junta las tres piezas anteriores: los trozos se transcriben conforme llegan y el texto se va uniendo.

**Files:**
- Create: `flowlibre/stream_stt.py`
- Test: `tests/test_stream_stt.py`

**Interfaces:**
- Consumes: `Transcriber` (Task 2), `merge_overlap` (Task 6).
- Produces: `StreamingTranscriber(transcriber, language)` con:
  - `submit(chunk: np.ndarray) -> None` — encola un trozo (no bloquea).
  - `result(timeout_s: float = 30.0) -> tuple[str, str]` — espera a que se vacíe la cola y devuelve `(texto, idioma)`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_stream_stt.py`:

```python
import time

import numpy as np

from flowlibre.stream_stt import StreamingTranscriber


class TranscriberFalso:
    """Devuelve textos predefinidos, uno por llamada, y simula tardanza."""

    def __init__(self, textos, demora=0.0):
        self.textos = list(textos)
        self.demora = demora
        self.llamadas = 0

    def transcribe(self, audio, language):
        if self.demora:
            time.sleep(self.demora)
        texto = self.textos[self.llamadas] if self.llamadas < len(self.textos) else ""
        self.llamadas += 1
        return texto, "es"


def audio(segundos=1.0):
    return np.zeros(int(segundos * 16000), dtype="float32")


def test_une_los_trozos_en_orden():
    st = StreamingTranscriber(TranscriberFalso(["hola que tal", "todo bien gracias"]), "es")
    st.submit(audio())
    st.submit(audio())
    texto, idioma = st.result()
    assert texto == "hola que tal todo bien gracias"
    assert idioma == "es"


def test_deduplica_el_traslape_entre_trozos():
    st = StreamingTranscriber(
        TranscriberFalso(["necesito el reporte de agosto", "de agosto por favor"]), "es"
    )
    st.submit(audio())
    st.submit(audio())
    texto, _ = st.result()
    assert texto == "necesito el reporte de agosto por favor"


def test_transcribe_mientras_llegan_mas_trozos():
    falso = TranscriberFalso(["uno", "dos", "tres"], demora=0.05)
    st = StreamingTranscriber(falso, "es")
    st.submit(audio())
    time.sleep(0.15)                  # da tiempo a que procese el primero
    assert falso.llamadas >= 1        # ya trabajo sin esperar a los demas
    st.submit(audio())
    st.submit(audio())
    assert st.result() == ("uno dos tres", "es")


def test_sin_trozos_devuelve_vacio():
    assert StreamingTranscriber(TranscriberFalso([]), "es").result() == ("", "")


def test_ignora_trozos_que_salen_vacios():
    st = StreamingTranscriber(TranscriberFalso(["hola", "", "mundo"]), "es")
    for _ in range(3):
        st.submit(audio())
    texto, _ = st.result()
    assert texto == "hola mundo"
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stream_stt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flowlibre.stream_stt'`

- [ ] **Step 3: Implementar el transcriptor incremental**

Crear `flowlibre/stream_stt.py`:

```python
"""Transcribe trozos de audio conforme llegan, en un hilo aparte.

El punto de todo esto: cuando el usuario suelta la tecla, los trozos anteriores
ya estan transcritos y solo queda el ultimo. Por eso la latencia deja de
depender de cuanto hablo.

Un solo hilo consumidor, no un pool: los trozos deben transcribirse en orden
para que el traslape se pueda deduplicar contra el trozo anterior.
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
        self._text = ""
        self._detected = ""
        self._error: BaseException | None = None
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, chunk: np.ndarray) -> None:
        """Encola un trozo. No bloquea."""
        self._queue.put(chunk)

    def _run(self) -> None:
        try:
            while True:
                item = self._queue.get()
                if item is _FIN:
                    return
                texto, idioma = self._transcriber.transcribe(item, self._language)
                if idioma and not self._detected:
                    self._detected = idioma
                if texto.strip():
                    self._text = merge_overlap(self._text, texto)
        except BaseException as e:       # se re-lanza en result()
            self._error = e
        finally:
            self._done.set()

    def result(self, timeout_s: float = 30.0) -> tuple[str, str]:
        """Espera a que se procese todo lo encolado y devuelve (texto, idioma)."""
        self._queue.put(_FIN)
        self._thread.join(timeout=timeout_s)
        if self._error is not None:
            raise self._error
        return self._text, self._detected
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stream_stt.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add flowlibre/stream_stt.py tests/test_stream_stt.py
git commit -m "feat: transcripcion incremental de trozos en hilo aparte"
```

---

## Task 9: Conectar el troceo al pipeline

El cambio que hace que todo lo anterior sirva de algo en la app real.

**Files:**
- Modify: `flowlibre/app.py` (`__init__`, `reload_config`, `start_recording`, `stop_recording`, `_process`, `_pipeline`)
- Modify: `flowlibre/config.py` (`DEFAULTS`)
- Modify: `config.yaml`
- Test: `tests/test_app_pipeline.py`

**Interfaces:**
- Consumes: `Recorder(on_chunk=...)` (Task 7), `StreamingTranscriber` (Task 8).
- Produces: `Config.streaming_stt: bool` (default `True`). `FlowLibreApp._pipeline(text, language, audio_duration_s, prefix)` cambia de firma: ahora recibe el texto ya transcrito, no el audio.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_app_pipeline.py`:

```python
from flowlibre.config import DEFAULTS


def test_streaming_activado_por_defecto():
    assert DEFAULTS["streaming_stt"] is True


def test_pipeline_recibe_texto_no_audio():
    """El pipeline ya no transcribe: recibe el texto listo.

    Se verifica por firma para no necesitar GPU ni microfono en la suite.
    """
    import inspect

    from flowlibre.app import FlowLibreApp

    params = list(inspect.signature(FlowLibreApp._pipeline).parameters)
    assert params == ["self", "text", "language", "audio_duration_s", "prefix"]
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app_pipeline.py -v`
Expected: FAIL — `KeyError: 'streaming_stt'`

- [ ] **Step 3: Agregar el interruptor de configuración**

En `flowlibre/config.py`, dentro de `DEFAULTS`, después de `"whisper_beam_size"`:

```python
    "streaming_stt": True,
```

En `config.yaml`, después del bloque de Whisper:

```yaml
# Transcribir por trozos MIENTRAS hablas, en vez de esperar a que sueltes la
# tecla. Hace que la espera no crezca con la duración del dictado.
# Ponlo en false para volver al comportamiento anterior.
streaming_stt: true
```

- [ ] **Step 4: Conectar el troceo en la app**

En `flowlibre/app.py`, en `__init__`, reemplazar la creación del `Recorder` por:

```python
        self.recorder = Recorder(
            self.config.microphone,
            on_chunk=self._on_chunk if self.config.streaming_stt else None,
        )
```

y agregar, junto a los demás atributos de estado:

```python
        self._stream_stt = None        # StreamingTranscriber del dictado en curso
```

En `reload_config`, reemplazar la línea `self.recorder = Recorder(self.config.microphone)` por la misma forma con `on_chunk` de arriba.

Agregar el método que recibe los trozos:

```python
    def _on_chunk(self, chunk) -> None:
        """Cada trozo cerrado se manda a transcribir sin esperar a que el
        usuario suelte la tecla."""
        if self._stream_stt is not None:
            self._stream_stt.submit(chunk)
```

- [ ] **Step 5: Abrir el transcriptor incremental al empezar a grabar**

En `flowlibre/app.py`, en `start_recording`, dentro del `try`, **antes** de `self.recorder.start()`:

```python
            if self.config.streaming_stt:
                from .stream_stt import StreamingTranscriber
                lang = None if self.config.language == "auto" else self.config.language
                self._stream_stt = StreamingTranscriber(self.transcriber, lang)
```

En `cancel_recording`, después de `self.recorder.stop()`, descartar el transcriptor en curso:

```python
        self._stream_stt = None
```

- [ ] **Step 6: Cobrar el resultado al soltar**

En `flowlibre/app.py`, reemplazar `stop_recording` por:

```python
    def stop_recording(self) -> None:
        if not self.recorder.recording:
            return
        audio = self.recorder.stop()          # emite el trozo final via on_chunk
        prefix = self._active_prefix
        stt = self._stream_stt
        self._stream_stt = None
        self._set_status("procesando")
        _dbg(f"procesando: {len(audio)} muestras ({len(audio)/16000:.1f}s) prefijo={prefix!r}")
        self.overlay.show_processing()
        threading.Thread(
            target=self._process, args=(audio, prefix, stt), daemon=True
        ).start()
```

Reemplazar `_process` por:

```python
    def _process(self, audio, prefix: str = "", stt=None) -> None:
        with self._busy:
            try:
                lang_cfg = None if self.config.language == "auto" else self.config.language
                if stt is not None:
                    text, language = stt.result()
                else:
                    text, language = self.transcriber.transcribe(audio, lang_cfg)
                _dbg(f"whisper devolvió {len(text)} chars: {text[:80]!r}")
                if text:
                    self._pipeline(text, language, len(audio) / 16000, prefix)
            except Exception as e:
                _dbg(f"ERROR en pipeline: {type(e).__name__}: {e}")
                print(f"[FlowLibre] Error en el pipeline: {e}")
                _beep(220, 300)
            finally:
                self.overlay.hide()
                self._set_status("listo")
```

- [ ] **Step 7: Ajustar `_pipeline` a la nueva firma**

En `flowlibre/app.py`, cambiar la firma de `_pipeline` y **borrar** sus primeras cinco líneas (las que hacían `lang_cfg`, `transcribe`, el `_dbg` y el `if not raw_text: return`), que ahora viven en `_process`:

```python
    def _pipeline(self, text: str, language: str, audio_duration_s: float, prefix: str = "") -> None:
        raw_text = text
```

En el resto del cuerpo, reemplazar las dos apariciones de `duration_s=len(audio) / 16000` por `duration_s=audio_duration_s`. No hay otros usos de `audio` en el método.

- [ ] **Step 8: Correr los tests y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS (36 passed)

- [ ] **Step 9: Probar la app de verdad**

```bash
D:/FlowLibre/FlowLibre.bat
```

Dictar tres veces y confirmar en `debug.log`:
1. Un dictado corto (~5 s) — debe salir texto correcto.
2. Un dictado largo (~60 s) — el tiempo entre `procesando:` e `inyectando` debe ser **menos de 1.5 s**, contra los ~6 s de antes.
3. Un dictado con pausas largas a media frase — verificar que **no se repiten ni se comen palabras** en las uniones. Este es el riesgo principal del troceo.

Si aparecen palabras repetidas, subir `overlap_s` en `Chunker`; si se comen palabras, bajarlo.

- [ ] **Step 10: Commit**

```bash
git add flowlibre/app.py flowlibre/config.py config.yaml tests/test_app_pipeline.py
git commit -m "perf: transcribir por trozos mientras se habla"
```

---

## Task 10: FUSIONADA EN LA TASK 3 — no se despacha

El plan original separaba "timeout y max_tokens" (Task 3) de "quitar el SDK de
anthropic" (Task 10). El escaneo previo encontro que ambas reescribian el mismo
metodo `clean()`: la Task 3 habria escrito manejo de errores del SDK para que la
Task 10 lo borrara de inmediato. Se fusionaron en la Task 3.

Ver el ruling C2 en `.superpowers/sdd/2026-08-25-fase-1-latencia-y-peso/progress.md`.

---

## Task 11: Modelo cuantizado a int8

El recorte de peso más grande de esta fase: 1.6 GB a ~800 MB.

**Files:**
- Create: `tools/quantize_model.py`
- Modify: `config.yaml`
- Modify: `.gitignore` (ya incluye `models/` desde la Task 1)

**Interfaces:**
- Consumes: nada del runtime.
- Produces: el directorio `models/large-v3-turbo-int8/`, que `config.yaml` referencia por ruta.

- [ ] **Step 1: Escribir la herramienta de conversión**

Crear `tools/quantize_model.py`:

```python
"""Convierte el modelo de Whisper a int8 y lo deja en models/.

En disco el modelo turbo pesa 1.6 GB en fp16. En ejecucion ya se usa
int8_float16, o sea que se cuantiza al cargar de todos modos: guardarlo ya
cuantizado ahorra ~800 MB sin cambiar nada de la calidad.

Uso:  .venv/Scripts/python.exe tools/quantize_model.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESTINO = ROOT / "models" / "large-v3-turbo-int8"
ORIGEN = "openai/whisper-large-v3-turbo"


def main() -> None:
    if DESTINO.exists():
        print(f"Ya existe: {DESTINO}")
        return
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    print(f"Convirtiendo {ORIGEN} a int8 -> {DESTINO}")
    subprocess.run(
        [sys.executable, "-m", "ctranslate2.converters.transformers",
         "--model", ORIGEN,
         "--output_dir", str(DESTINO),
         "--copy_files", "tokenizer.json", "preprocessor_config.json",
         "--quantization", "int8"],
        check=True,
    )
    total = sum(f.stat().st_size for f in DESTINO.rglob("*") if f.is_file())
    print(f"Listo: {total / 1e9:.2f} GB en {DESTINO}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Instalar la dependencia de conversión y correrla**

El convertidor necesita `transformers`, que **no** es dependencia de runtime (no va en `requirements.txt`):

```bash
.venv/Scripts/python.exe -m pip install transformers
.venv/Scripts/python.exe tools/quantize_model.py
```

Expected: imprime "Listo: ~0.8 GB".

- [ ] **Step 3: Apuntar la config al modelo local**

En `config.yaml`, cambiar la línea del modelo:

```yaml
# Ruta local al modelo cuantizado (generado con tools/quantize_model.py).
# También acepta un nombre de modelo ("large-v3-turbo", "medium", "small"),
# que se descarga de Hugging Face al primer uso.
whisper_model: "models/large-v3-turbo-int8"
```

En `flowlibre/transcribe.py`, en `load()`, resolver la ruta relativa contra la raíz del proyecto antes de construir el modelo:

```python
    def load(self) -> None:
        """Carga el modelo (descarga la primera vez). Idempotente."""
        if self._model is not None:
            return
        _add_nvidia_dll_dirs()
        from faster_whisper import WhisperModel

        from .config import ROOT
        # Una ruta relativa apunta a un modelo local; un nombre suelto se baja de HF.
        candidato = ROOT / self.model_name
        origen = str(candidato) if candidato.is_dir() else self.model_name
        self._origen = origen        # lo necesita el reintento en CPU de transcribe()

        try:
            self._model = WhisperModel(
                origen, device="cuda", compute_type=self.compute_type
            )
        except Exception as e:
            # Sin GPU/CUDA utilizable: caer a CPU en vez de crashear.
            print(f"[FlowLibre] GPU no disponible ({e}); usando CPU (más lento).")
            self._model = WhisperModel(origen, device="cpu", compute_type="int8")
```

Inicializar el atributo en el constructor de `Transcriber`, junto a `self._model = None`:

```python
        self._origen = model_name
```

Y en `transcribe()`, dentro del `except RuntimeError` que reintenta en CPU, reemplazar
`WhisperModel(self.model_name, device="cpu", compute_type="int8")` por:

```python
            self._model = WhisperModel(self._origen, device="cpu", compute_type="int8")
```

Sin esto, el reintento en CPU buscaría en Hugging Face un modelo llamado
`models/large-v3-turbo-int8` y fallaría.

- [ ] **Step 4: Verificar que la app sigue transcribiendo**

```bash
.venv/Scripts/python.exe tools/bench.py
```

Expected: los mismos tiempos de la Task 2 (±15%). Si el modelo no carga, revisar que `models/large-v3-turbo-int8/model.bin` exista.

- [ ] **Step 5: Borrar los modelos viejos de la caché**

Solo después de confirmar que el int8 funciona:

```bash
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-medium
rm -rf ~/.cache/huggingface/hub/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo
```

Expected: ~3.1 GB liberados.

- [ ] **Step 6: Commit**

```bash
git add tools/quantize_model.py flowlibre/transcribe.py config.yaml
git commit -m "perf: modelo turbo cuantizado a int8 (-800 MB en disco)"
```

---

## Task 12: Validación contra los criterios de éxito

Ningún cambio de código. Verifica que la fase cumplió lo que prometió y deja constancia.

**Files:**
- Create: `docs/superpowers/resultados-fase-1.md`

- [ ] **Step 1: Medir con la GPU en reposo**

Cerrar juegos y Wallpaper Engine. Confirmar con `nvidia-smi` que la utilización esté por debajo de 20%.

```bash
.venv/Scripts/python.exe tools/bench.py
```

Anotar los tres números.

- [ ] **Step 2: Medir con la GPU ocupada**

Abrir un juego (Aim Lab sirve) y dejarlo corriendo. Confirmar con `nvidia-smi` que la utilización esté arriba de 80%.

```bash
.venv/Scripts/python.exe tools/bench.py
```

Anotar los tres números. **Este es el criterio que importa:** el total del WAV de 60 s debe quedar en 2.5 s o menos.

- [ ] **Step 3: Verificar que la latencia no crece con la duración**

De la corrida con GPU ocupada, comparar el total del WAV de 6 s contra el de 60 s. La diferencia debe ser **menor a 1 segundo**. Si el de 60 s es notoriamente más lento, el troceo no está funcionando: revisar en `debug.log` que aparezcan varias transcripciones parciales por dictado.

- [ ] **Step 4: Medir el peso**

```bash
du -sh /d/FlowLibre /d/FlowLibre/.venv /d/FlowLibre/models ~/.cache/huggingface
```

Expected: total alrededor de 3.5 GB, contra los 6.7 GB de partida.

- [ ] **Step 5: Escribir los resultados**

Crear `docs/superpowers/resultados-fase-1.md` con una tabla de antes y después para cada criterio de la sección 14 del spec, marcando cada uno como cumplido o no. Para los que no se cumplieron, anotar el número real y qué haría falta.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/resultados-fase-1.md
git commit -m "docs: resultados medidos de la fase 1"
```

---

## Notas de auto-revisión

Se revisó este plan contra el spec. Tres cosas que vale la pena tener presentes al ejecutar:

1. **La Task 9 es la única con riesgo real de regresión.** Cambia la firma de `_pipeline` y el flujo de `stop_recording`. Los modos de prefijo (Discord) y los comandos de voz ("borra eso") pasan por ahí y hay que probarlos a mano; los tests no los cubren porque necesitan micrófono y teclado reales.
2. **`streaming_stt: true` es un interruptor de escape.** Si el troceo da problemas en uso real, ponerlo en `false` devuelve el comportamiento anterior sin revertir código.
3. **La sección 7 del spec queda parcialmente cubierta**, por la corrección de alcance de arriba. La detección de NVIDIA y la descarga condicional de CUDA se planean en la Fase 5.
