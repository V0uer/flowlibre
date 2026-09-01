# Resultados — Fase 1: latencia y peso

Cierre del 2026-08-31. Rama `fase-1-latencia`. Suite: 102 tests en verde.

Punto de partida: `docs/superpowers/baseline-2026-08-25.txt` (modelo `medium`, beam 5,
sin troceo, SDK `anthropic`).

## 1. Latencia

Todo en segundos. "completo" = transcribir el audio entero al soltar la tecla (el camino
viejo). "troceado" = lo que el usuario de verdad espera: **del momento en que suelta la
tecla al texto listo**, con los trozos ya transcritos mientras hablaba. Medido con
`tools/bench_streaming.py`, que emula el micrófono en tiempo real.

### Whisper, con la GPU en reposo (utilización 13%)

| audio | baseline 2026-08-25 | completo (hoy) | **troceado (hoy)** |
|-------|--------------------:|---------------:|-------------------:|
| 6 s   | 0.18 | 0.32 | **0.15** |
| 21 s  | 0.69 | 0.29 | **0.12** |
| 60 s  | 3.69 | 0.78 | **0.15** |

### Whisper, con la GPU ocupada (60–80%, contención sintética)

| audio | completo | **troceado** |
|-------|---------:|-------------:|
| 6 s   | 0.52 | **0.35** |
| 21 s  | 0.51 | **0.28** |
| 60 s  | 1.68 | **0.25** |

La contención se generó con un segundo proceso transcribiendo en bucle, no con un juego.
Es contención real de GPU por otro proceso, pero un juego pelea por gráficos más que por
cómputo: **queda pendiente repetir la medición con un juego abierto** para cerrar el
criterio 1 con la carga exacta del spec.

### Dictado real (la única medición que no es sintética)

Del `debug.log`, dictado del autor del 2026-08-31 a las 19:22, **34.9 s de audio dictados
con pausas a propósito**:

- `procesando:` → `whisper devolvió`: **0.318 s** (109.8x tiempo real)
- `procesando:` → `inyectando` (incluye la limpieza con Claude): **1.86 s**
- Sin una sola línea de error, fallback ni "streaming falló".
- Texto crudo sin palabras repetidas ni comidas en ningún empalme de trozos.

Contra los 176 dictados medidos del historial: los de 25 s o más **antes** del cambio
(n=42) tenían mediana de **1.90 s** de Whisper. Los cuatro comparables más recientes:
1.46 s (26.6 s de audio), 1.63 s (31.9 s), 2.08 s (32.0 s) y 7.64 s (31.5 s, con la GPU
ocupada). El de ahora, **más largo que todos esos, tardó 0.318 s**.

## 2. Peso en disco

| | antes | ahora |
|---|---:|---:|
| modelo Whisper | 1.6 GB (fp16) | **0.82 GB** (int8) |
| `.venv` | 2.4 GB | 2.37 GB (1.94 GB son las libs de NVIDIA) |
| caché de Hugging Face | 3.1 GB | 1.51 GB |
| **total** | **6.7 GB** | **4.65 GB** |

Bajará a **3.14 GB** al borrar la caché del turbo fp16, que se dejó a propósito como red
de seguridad hasta que el int8 acumule dictados reales:

```bash
rm -rf ~/.cache/huggingface/hub/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo
```

El int8 se generó con `tools/quantize_model.py` y se verificó contra el fp16: **misma
velocidad** (0.14 / 0.28 / 0.76 s contra 0.14 / 0.28 / 0.79 s) y **el mismo texto**. Las
únicas diferencias en el WAV de 60 s son de estilo — el fp16 escribe "120 watts" y puntúa
más, el int8 escribe "120W" — y que al final, donde ambos alucinan un bucle sobre el
silencio, **el int8 alucina menos** (750 caracteres contra 873). Los dos son deterministas
entre corridas.

## 3. Criterios del spec (sección 14)

| # | Criterio | Estado |
|---|----------|--------|
| 1 | p90 de punta a punta ≤ 2.5 s con la GPU ocupada | **Cumplido, con un asterisco.** Whisper bajo contención: 0.25–0.35 s. Sumando la limpieza medida en uso real (1.54 s), el total queda en ~1.9 s. Falta repetirlo con un juego abierto. |
| 2 | La latencia no crece con la duración del dictado | **Cumplido.** Bajo contención: 0.35 s para 6 s de audio y **0.25 s para 60 s**. Diferencia de 0.10 s contra el objetivo de < 1 s. El camino viejo iba de 0.52 a 1.68 s. |
| 3 | Instalador ≤ 200 MB, instalación ≤ 2.5 GB | Fuera de la fase 1 (no hay instalador todavía). La instalación va en 3.14 GB tras borrar la caché fp16; de esos, **1.94 GB son las libs de CUDA**, que es donde hay que atacar en la fase del instalador. |
| 4 | Alguien sin conocimientos técnicos dicta en < 5 min | Fuera de la fase 1. |
| 5 | Corre en la Mac del autor | Fuera de la fase 1. |
| 6 | Nada de `win32/winsound/winreg` fuera de `platform/windows.py` | Fuera de la fase 1 (ese módulo aún no existe). |

## 4. Lo que de verdad movió la aguja

El hallazgo que reencuadró el problema: la app no era lenta por el modelo, sino por
**contención de GPU**. En 164 dictados reales, Whisper rendía 24.5x tiempo real en su
mejor 10% y 0.5x en el peor, con la misma configuración y la misma GPU; la variable era si
El autor estaba jugando. Por eso el troceo — repartir el trabajo mientras habla — importaba
más que cambiar de modelo: al soltar la tecla ya no queda un dictado entero por
transcribir, solo el último pedazo. Los números de arriba son exactamente eso: la columna
"troceado" es plana, la columna "completo" crece con la duración.
