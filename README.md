# FlowLibre 🎙️

Dictado por voz para Windows 11 con limpieza por IA, **100% local y gratis por defecto**. Presiona un atajo, habla en cualquier aplicación, y el texto — sin muletillas, con puntuación y gramática correcta — se escribe donde esté tu cursor.

- Transcripción: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) en tu GPU (CUDA).
- Limpieza: **Motor A** = Ollama local (default, offline, gratis) o **Motor B** = API de Claude (opcional, de pago).

---

## 1. Requisitos

- Windows 11, GPU NVIDIA (probado con RTX 3080 Ti, 12 GB VRAM).
- [Python 3.11+](https://www.python.org/downloads/) (marca "Add to PATH" al instalar).
- [Ollama](https://ollama.com/download) para el Motor A.

## 2. Instalación

```powershell
cd D:\FlowLibre
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> Las DLLs de CUDA (cuBLAS/cuDNN) se instalan vía pip — no necesitas instalar el CUDA Toolkit.

### Motor A — Ollama (default)

```powershell
ollama pull qwen2.5:14b-instruct
```

Asegúrate de que Ollama esté corriendo (ícono en la bandeja). Eso es todo: el flujo por defecto es 100% offline.

### Motor B — Claude (opcional)

1. Crea una API key en [console.anthropic.com](https://console.anthropic.com) (Settings → API Keys) y carga saldo en Billing.
2. Guarda la key como variable de entorno (nunca va en `config.yaml`):
   ```powershell
   setx ANTHROPIC_API_KEY "sk-ant-..."
   ```
3. Reinicia la terminal/FlowLibre y activa el Motor B desde el menú de la bandeja (o `engine: "claude"` en `config.yaml`).

## 3. Correr

```powershell
cd D:\FlowLibre
.venv\Scripts\activate
python -m flowlibre
```

Aparece un ícono azul de micrófono en la bandeja del sistema.

**Nota:** la primera vez, faster-whisper descarga el modelo `medium` (~1.5 GB). El primer dictado tras arrancar tarda unos segundos mientras carga en GPU.

## 4. Uso

| Acción | Cómo |
|---|---|
| Dictar (push-to-talk) | Mantén **Win+Ctrl**, habla, suelta |
| Micro fijo (manos libres) | Doble toque rápido a **Win+Ctrl**; un toque más termina |
| Cambiar modo de atajo | `hotkey_mode: "hibrido" / "push_to_talk" / "toggle"` en config.yaml |
| Cambiar modo de formato | Menú de bandeja → Modo de formato (mensaje/email/notas/crudo) |
| Cambiar motor A/B | Menú de bandeja → Motor de limpieza |
| Comandos de voz | Di "nueva línea", "punto y aparte"; o dicta SOLO "borra eso" / "en mayúsculas" |
| Diccionario | Agrega nombres propios a `dictionary.txt` (uno por línea) |
| Historial | Menú de bandeja → Ver historial (`history.jsonl`) |
| Iniciar con Windows | Menú de bandeja → Iniciar con Windows |

Feedback sonoro: beep agudo = grabando, beep medio = procesando, beep grave = error.

## 5. Configuración (`config.yaml`)

Los parámetros clave (edita y usa "Recargar configuración" en el tray):

| Parámetro | Default | Notas |
|---|---|---|
| `hotkey` | `windows+ctrl` | Atajo global |
| `hotkey_mode` | `hibrido` | `push_to_talk` / `toggle` / `hibrido` (mantener = PTT, doble toque = fijo) |
| `engine` | `ollama` | `ollama` (A) / `claude` (B) |
| `whisper_model` | `medium` | `small` / `medium` / `large-v3` |
| `ollama_keep_alive` | `"5m"` | **`"0"` descarga el modelo tras cada uso y libera ~9 GB de VRAM** (útil para jugar), a cambio de ~2-3 s de recarga en el siguiente dictado. Verifícalo con `nvidia-smi`. |
| `claude_model` | `claude-haiku-4-5` | o `claude-sonnet-5` |
| `claude_fallback_to_ollama` | `true` | Si el Motor B falla (sin red/saldo), cae al A |
| `inject_method` | `clipboard` | `typing` si una app bloquea el pegado |

### VRAM (12 GB)

Whisper `medium` (~1.5 GB) + qwen2.5:14b (~9 GB) conviven bien. Si usas `large-v3` (~3.5 GB) considera un modelo de Ollama más chico o `ollama_keep_alive: "0"`.

### Prompt caching del Motor B

El system prompt (reglas + diccionario) se marca con `cache_control` para abaratar llamadas repetidas. Ojo: la API solo cachea prefijos de ≥ ~4096 tokens en Haiku — con un diccionario chico el prompt es menor y el caching simplemente no se activa (sin error). Con diccionarios grandes verás `cache_read_input_tokens > 0` a partir de la 2ª llamada.

## 6. Solución de problemas

- **"Ollama no responde"** → abre Ollama y corre `ollama pull qwen2.5:14b-instruct`.
- **No transcribe / usa CPU** → revisa que los paquetes `nvidia-cublas-cu12` y `nvidia-cudnn-cu12` se instalaron; actualiza el driver NVIDIA.
- **El atajo no funciona en apps elevadas (admin)** → corre FlowLibre como administrador.
- **No pega en cierta app** → cambia `inject_method: "typing"`.
