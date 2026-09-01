"""¿Hay una NVIDIA en esta máquina? De eso depende qué modelo usa la app.

Esto corre en el **primer arranque de una instalación limpia**, cuando todavía
no hay CUDA ni modelos descargados. Por eso no puede preguntarle a torch ni a
ctranslate2: hay que preguntarle al sistema.

Regla de oro: nunca tumbar ni colgar el arranque. Si la detección falla por lo
que sea, se asume que no hay NVIDIA — la app funciona más lento pero funciona,
que es infinitamente mejor que no abrir.
"""

from __future__ import annotations

import subprocess

TIMEOUT_S = 4

# Sin consola negra parpadeando al arrancar (la app vive en la bandeja).
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_PS_ADAPTADORES = [
    "powershell", "-NoProfile", "-NonInteractive", "-Command",
    "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
]


def _corre(cmd: list[str]) -> str:
    salida = subprocess.run(
        cmd, capture_output=True, text=True, timeout=TIMEOUT_S,
        creationflags=_SIN_VENTANA,
    )
    return salida.stdout or ""


def detectar_nvidia() -> bool:
    """True si hay una GPU NVIDIA utilizable en la máquina."""
    try:
        if "nvidia" in _corre(["nvidia-smi", "-L"]).lower():
            return True
    except Exception:
        pass        # sin driver NVIDIA, nvidia-smi ni siquiera existe
    try:
        # Respaldo: puede haber tarjeta NVIDIA con el driver a medio instalar,
        # o nvidia-smi fuera del PATH. El sistema sí sabe qué adaptadores hay.
        return "nvidia" in _corre(_PS_ADAPTADORES).lower()
    except Exception:
        return False


def perfil_recomendado() -> dict:
    """Configuración de Whisper adecuada a esta máquina.

    Con NVIDIA, el turbo cuantizado que ya se validó aquí. Sin ella, `small` en
    CPU: es lo que hace la diferencia entre una app usable y una que tarda medio
    minuto por dictado en una laptop cualquiera.
    """
    if detectar_nvidia():
        return {
            "whisper_model": "models/large-v3-turbo-int8",
            "whisper_compute_type": "int8_float16",
            "acelerada": True,
        }
    return {"whisper_model": "small", "whisper_compute_type": "int8", "acelerada": False}
