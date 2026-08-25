"""Atajo global configurable, en modos push-to-talk, toggle e híbrido."""

from __future__ import annotations

import datetime
import threading
import time
from pathlib import Path

import keyboard

# Log de diagnóstico (activado mientras depuramos el hotkey).
DEBUG_LOG = Path(__file__).resolve().parent.parent / "debug.log"


def _dbg(msg: str) -> None:
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%H:%M:%S.%f} {msg}\n")
    except OSError:
        pass

# Modo híbrido: un toque más corto que esto cuenta como "tap" (no push-to-talk),
# y un segundo tap dentro de la misma ventana fija el micrófono.
TAP_SECONDS = 0.4

# keyboard.add_hotkey no dispara combos formados SOLO por modificadores
# (ej. "windows+ctrl"); esos se detectan a mano con hooks por tecla.
MODIFIER_KEYS = {
    "ctrl", "left ctrl", "right ctrl",
    "alt", "left alt", "right alt", "alt gr",
    "shift", "left shift", "right shift",
    "windows", "left windows", "right windows", "win", "cmd",
}


class HotkeyManager:
    """Llama on_start / on_stop / on_cancel según el modo del atajo.

    push_to_talk: on_start al presionar el combo, on_stop al soltar la tecla final.
    toggle: cada activación del combo alterna entre grabar y detener.
    hibrido: mantener presionado = push-to-talk; doble toque rápido = el micro
             queda fijo grabando; un toque más lo detiene. Un toque suelto único
             se cancela (on_cancel) para no procesar audio fantasma.
    """

    def __init__(self, hotkey: str, mode: str, on_start, on_stop, on_cancel=None) -> None:
        self.hotkey = hotkey
        self.mode = mode
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_cancel = on_cancel or on_stop
        self._active = False
        self._hook_ids: list = []
        # Estado del modo híbrido: "idle" | "held" | "waiting" | "locked"
        self._state = "idle"
        self._press_time = 0.0
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def register(self) -> None:
        keys = [k.strip() for k in self.hotkey.split("+")]
        if all(k in MODIFIER_KEYS for k in keys):
            self._register_modifier_combo(keys)
            return
        if self.mode == "toggle":
            self._hook_ids.append(keyboard.add_hotkey(self.hotkey, self._toggle))
            return
        press = self._hybrid_press if self.mode == "hibrido" else self._ptt_press
        release = self._hybrid_release if self.mode == "hibrido" else self._ptt_release
        self._hook_ids.append(
            keyboard.add_hotkey(self.hotkey, press, trigger_on_release=False)
        )
        # La tecla "principal" es la última del combo; su release detiene.
        main_key = keys[-1]
        self._hook_ids.append(keyboard.on_release_key(main_key, release))

    def _register_modifier_combo(self, keys: list[str]) -> None:
        """Detección manual: presionado cuando TODAS las teclas del combo están
        abajo; soltado cuando cualquiera se suelta."""
        self._combo_down = False
        _dbg(f"registrando combo manual: {keys} (modo {self.mode})")

        def on_press(event) -> None:
            states = {k: keyboard.is_pressed(k) for k in keys}
            _dbg(f"press '{event.name}' sc={event.scan_code} estados={states}")
            if not self._combo_down and all(states.values()):
                self._combo_down = True
                _dbg("=> COMBO PRESS")
                self._combo_press()

        def on_release(event) -> None:
            _dbg(f"release '{event.name}' sc={event.scan_code} combo_down={self._combo_down}")
            if self._combo_down:
                self._combo_down = False
                _dbg("=> COMBO RELEASE")
                self._combo_release()

        for k in keys:
            self._hook_ids.append(keyboard.on_press_key(k, on_press))
            self._hook_ids.append(keyboard.on_release_key(k, on_release))
        _dbg(f"hooks instalados: {len(self._hook_ids)}")

    def _combo_press(self) -> None:
        if self.mode == "toggle":
            self._toggle()
        elif self.mode == "hibrido":
            self._hybrid_press()
        else:
            self._ptt_press()

    def _combo_release(self) -> None:
        if self.mode == "hibrido":
            self._hybrid_release(None)
        elif self.mode != "toggle":
            self._ptt_release(None)

    def reset(self) -> None:
        """Vuelve al estado inactivo (cuando el dictado se termina por otra vía,
        ej. clic en los botones del overlay)."""
        with self._lock:
            self._cancel_timer()
            self._state = "idle"
            self._active = False

    def unregister(self) -> None:
        self._cancel_timer()
        for hid in self._hook_ids:
            try:
                keyboard.remove_hotkey(hid)
            except (KeyError, ValueError):
                try:
                    keyboard.unhook(hid)
                except Exception:
                    pass
        self._hook_ids = []

    # --- modo toggle ---

    def _toggle(self) -> None:
        if self._active:
            self._active = False
            self.on_stop()
        else:
            self._active = True
            self.on_start()

    # --- modo push_to_talk ---

    def _ptt_press(self) -> None:
        if not self._active:
            self._active = True
            self.on_start()

    def _ptt_release(self, event) -> None:
        if self._active:
            self._active = False
            self.on_stop()

    # --- modo híbrido ---

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _hybrid_press(self) -> None:
        with self._lock:
            if self._state == "locked":
                # Tercer toque: terminar el dictado fijo.
                self._state = "idle"
                self.on_stop()
            elif self._state == "waiting":
                # Segundo toque dentro de la ventana: fijar el micrófono.
                self._cancel_timer()
                self._state = "locked"
            elif self._state == "idle":
                self._state = "held"
                self._press_time = time.monotonic()
                self.on_start()
            # "held": repeticiones de tecla mantenida se ignoran.

    def _hybrid_release(self, event) -> None:
        with self._lock:
            if self._state != "held":
                return
            if time.monotonic() - self._press_time >= TAP_SECONDS:
                # Se mantuvo presionado: push-to-talk clásico.
                self._state = "idle"
                self.on_stop()
            else:
                # Toque rápido: esperar un posible segundo toque.
                self._state = "waiting"
                self._timer = threading.Timer(TAP_SECONDS, self._hybrid_timeout)
                self._timer.daemon = True
                self._timer.start()

    def _hybrid_timeout(self) -> None:
        with self._lock:
            if self._state == "waiting":
                # Toque único suelto: descartar la mini-grabación sin procesarla.
                self._state = "idle"
                self.on_cancel()
