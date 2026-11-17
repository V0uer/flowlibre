"""Inyección de texto en el cursor activo.

- Método "clipboard" (default): guarda el portapapeles, pega con Ctrl+V y lo
  restaura. Soporta acentos y emoji vía CF_UNICODETEXT.
- Método "typing": teclea carácter por carácter (para apps que bloquean pegar).
"""

from __future__ import annotations

import ctypes
import time

import keyboard
import win32clipboard
import win32con

_VK_LWIN = 0x5B
_VK_RWIN = 0x5C

# Cuanto se espera, como mucho, a que el autor suelte la tecla Windows antes de
# pegar. Pasado el plazo se pega igual: perder el dictado es peor que el
# selector de sonido que Windows abre con Win+Ctrl+V.
ESPERA_MAX_TECLA_WINDOWS_S = 2.0


def _tecla_windows_presionada() -> bool:
    """Estado FISICO de las dos teclas Windows, no el que lleva `keyboard`."""
    user32 = ctypes.windll.user32
    return bool(user32.GetAsyncKeyState(_VK_LWIN) & 0x8000
                or user32.GetAsyncKeyState(_VK_RWIN) & 0x8000)


def esperar_tecla_windows_suelta() -> None:
    """Bloquea hasta que no haya ninguna tecla Windows abajo (o venza el plazo).

    El atajo por defecto es "windows+ctrl". Con dictados cortos el texto llega
    en milisegundos, a veces antes de que el autor suelte Windows; entonces la
    tecla sintetica se combina con la fisica. Un Ctrl+V se vuelve Win+Ctrl+V
    (selector de salida de sonido, y no pega nada), y una letra tecleada se
    vuelve un atajo de Windows. Por eso se espera antes de CUALQUIER tecla.
    """
    deadline = time.perf_counter() + ESPERA_MAX_TECLA_WINDOWS_S
    while _tecla_windows_presionada():
        if time.perf_counter() >= deadline:
            return
        time.sleep(0.01)


def _get_clipboard_text() -> str | None:
    """Texto actual del portapapeles, o None si está vacío / no es texto."""
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return None
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return None


def _set_clipboard_text(text: str) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def wait_for_clipboard(expected: str, timeout_s: float = 0.15) -> bool:
    """Espera a que el portapapeles contenga `expected`. True si llego a tiempo.

    Reemplaza los sleep() fijos: en la practica el portapapeles se asienta en
    pocos milisegundos, pero bajo carga puede tardar mas. Sondear cuesta lo que
    de verdad tarda, no siempre lo peor.

    timeout_s=0.15 para que el peor caso (timeout + el sleep post-Ctrl+V) no
    supere los 200ms que tardaba el codigo anterior con sus dos sleep() fijos.
    """
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if _get_clipboard_text() == expected:
            return True
        time.sleep(0.01)
    return False


def _restore_clipboard(original: str | None) -> None:
    if original is not None:
        try:
            _set_clipboard_text(original)
        except Exception:
            pass  # si falla la restauración, el texto dictado queda en el clipboard


def inject_text(text: str, method: str = "clipboard") -> None:
    if not text:
        return
    esperar_tecla_windows_suelta()
    if method == "typing":
        keyboard.write(text, delay=0.005)
        return

    # clipboard (default)
    original = _get_clipboard_text()
    _set_clipboard_text(text)
    if not wait_for_clipboard(text):
        # El portapapeles no cuadro: otra app lo tiene tomado. Un Ctrl+V aqui
        # pegaria lo que esa app haya escrito, no lo que el autor dicto.
        _set_clipboard_text(text)
        # Si el primer sondeo (150ms) ya se agoto, el portapapeles esta
        # genuinamente contendido: o se libera pronto o hay que rendirse y
        # teclear. Alargar este segundo sondeo a 150ms tambien no cambia el
        # panorama, solo suma otros 150ms al peor caso. Por eso usa un plazo
        # corto: no lo subas para "darle mas chance".
        if not wait_for_clipboard(text, timeout_s=0.05):
            # Se tecla el texto en vez de pegarlo: mas lento, pero el dictado
            # aterriza siempre y no se toca el portapapeles del usuario.
            keyboard.write(text, delay=0.005)
            _restore_clipboard(original)
            return
    keyboard.send("ctrl+v")
    # Dar a la app destino un margen corto para leer el portapapeles antes de
    # restaurarlo. Esto no se puede sondear: no hay forma de saber si ya leyo.
    time.sleep(0.05)
    _restore_clipboard(original)


def send_enter() -> None:
    """Envía Enter (para autoenviar el comando en modo música/prefijo)."""
    time.sleep(0.05)   # asegurar que el texto ya se pegó antes de enviar
    keyboard.send("enter")


def delete_chars(count: int) -> None:
    """Envía `count` retrocesos (para el comando de voz 'borra eso')."""
    esperar_tecla_windows_suelta()
    for _ in range(count):
        keyboard.send("backspace")
        time.sleep(0.002)
