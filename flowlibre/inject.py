"""Inyección de texto en el cursor activo.

- Método "clipboard" (default): guarda el portapapeles, pega con Ctrl+V y lo
  restaura. Soporta acentos y emoji vía CF_UNICODETEXT.
- Método "typing": teclea carácter por carácter (para apps que bloquean pegar).
"""

from __future__ import annotations

import time

import keyboard
import win32clipboard
import win32con


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


def inject_text(text: str, method: str = "clipboard") -> None:
    if not text:
        return
    if method == "typing":
        keyboard.write(text, delay=0.005)
        return

    # clipboard (default)
    original = _get_clipboard_text()
    _set_clipboard_text(text)
    time.sleep(0.05)          # dar tiempo a que el clipboard se asiente
    keyboard.send("ctrl+v")
    time.sleep(0.15)          # dejar que la app destino lea el clipboard
    if original is not None:
        try:
            _set_clipboard_text(original)
        except Exception:
            pass  # si falla la restauración, el texto dictado queda en el clipboard


def send_enter() -> None:
    """Envía Enter (para autoenviar el comando en modo música/prefijo)."""
    time.sleep(0.05)   # asegurar que el texto ya se pegó antes de enviar
    keyboard.send("enter")


def delete_chars(count: int) -> None:
    """Envía `count` retrocesos (para el comando de voz 'borra eso')."""
    for _ in range(count):
        keyboard.send("backspace")
        time.sleep(0.002)
