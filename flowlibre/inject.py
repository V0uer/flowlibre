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
        if not wait_for_clipboard(text):
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
    for _ in range(count):
        keyboard.send("backspace")
        time.sleep(0.002)
