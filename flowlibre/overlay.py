"""Overlay visual estilo Wispr Flow: pastilla flotante con la onda del audio.

Corre tkinter en su propio hilo (todas las llamadas tk viven ahí). La ventana
es sin bordes, siempre-encima y NO roba el foco (WS_EX_NOACTIVATE), para que
el texto se inyecte en la app donde estaba el cursor.
"""

from __future__ import annotations

import collections
import queue
import threading
import tkinter as tk

W, H = 104, 24
BARS = 11
BTN = 24                    # ancho reservado a cada botón (X / palomita)
MARGIN_BOTTOM = 60          # separación sobre el borde inferior de la pantalla
TRANSPARENT = "#010203"     # color clave que Windows vuelve transparente
PILL_BG = "#000000"         # negro puro, sin borde (como Wispr Flow)
WAVE_COLOR = "#d8d8dc"      # blanco grisáceo
LINE_DIM = "#55555a"        # línea base del estado "procesando"
LINE_BRIGHT = "#d8d8dc"     # destello que recorre la línea
X_BG = "#48484c"            # circulito gris de la X
X_COLOR = "#ffffff"         # cruz blanca delgada
CHECK_BG = "#ffffff"        # círculo blanco relleno
CHECK_COLOR = "#000000"     # palomita negra delgada


class Overlay:
    """Estados: hidden | recording (onda) | processing (puntos pulsando)."""

    def __init__(self, get_level, on_cancel=None, on_confirm=None) -> None:
        self.get_level = get_level  # callable → nivel del mic 0..1
        self.on_cancel = on_cancel    # clic en X: descartar dictado
        self.on_confirm = on_confirm  # clic en ✓: terminar dictado
        self._cmd: queue.Queue[str] = queue.Queue()
        self._levels = collections.deque([0.0] * BARS, maxlen=BARS)
        self._state = "hidden"
        self._tick = 0
        threading.Thread(target=self._run, daemon=True).start()

    # --- API (segura desde cualquier hilo) ---

    def show_recording(self) -> None:
        self._cmd.put("recording")

    def show_processing(self) -> None:
        self._cmd.put("processing")

    def hide(self) -> None:
        self._cmd.put("hidden")

    def submit(self, fn) -> None:
        """Ejecuta un callable en el hilo de tkinter (para ventanas hijas,
        ej. el panel/dashboard)."""
        self._cmd.put(fn)

    # --- hilo de tkinter ---

    def _run(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT)
        self.root.configure(bg=TRANSPARENT)
        self._reposition()
        self.canvas = tk.Canvas(
            self.root, width=W, height=H, bg=TRANSPARENT,
            highlightthickness=0, cursor="hand2",
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)
        self.root.update_idletasks()
        self._no_activate()
        self.root.withdraw()
        self._poll()
        self.root.mainloop()

    def _no_activate(self) -> None:
        """Evita que la ventana robe el foco al aparecer (crítico: el cursor
        debe seguir en la app donde se va a escribir)."""
        try:
            import win32con
            import win32gui

            hwnd = win32gui.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(
                hwnd, win32con.GWL_EXSTYLE,
                ex | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW,
            )
        except Exception:
            pass  # sin pywin32 el overlay funciona igual, solo puede robar foco

    def _on_click(self, event) -> None:
        if self._state != "recording":
            return
        if event.x <= BTN and self.on_cancel:
            self.on_cancel()
        elif event.x >= W - BTN and self.on_confirm:
            self.on_confirm()

    def _reposition(self) -> None:
        """Centra la pastilla abajo del monitor donde está la ventana ACTIVA
        (ahí es donde va a caer el texto), no del monitor principal."""
        try:
            import win32api
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
            monitor = win32api.MonitorFromWindow(hwnd, 2)  # DEFAULTTONEAREST
            left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
        except Exception:
            left = top = 0
            right = self.root.winfo_screenwidth()
            bottom = self.root.winfo_screenheight()
        x = left + (right - left - W) // 2
        y = bottom - H - MARGIN_BOTTOM
        self.root.geometry(f"{W}x{H}+{x}+{y}")

    def _poll(self) -> None:
        try:
            while True:
                new_state = self._cmd.get_nowait()
                if callable(new_state):
                    try:
                        new_state()
                    except Exception as e:
                        print(f"[FlowLibre] Error en tarea del hilo tk: {e}")
                    continue
                if new_state == "hidden":
                    self.root.withdraw()
                elif self._state == "hidden":
                    self._levels.extend([0.0] * BARS)
                    self._reposition()
                    self.root.deiconify()
                    self.root.attributes("-topmost", True)
                self._state = new_state
        except queue.Empty:
            pass
        if self._state != "hidden":
            self._draw()
        self._tick += 1
        self.root.after(40, self._poll)

    def _pill(self, x0: float, y0: float, x1: float, y1: float, color: str) -> None:
        """Pastilla redondeada (dos círculos + rectángulo) de un solo color."""
        d = y1 - y0  # diámetro de las puntas
        self.canvas.create_oval(x0, y0, x0 + d, y1, fill=color, outline="")
        self.canvas.create_oval(x1 - d, y0, x1, y1, fill=color, outline="")
        self.canvas.create_rectangle(x0 + d / 2, y0, x1 - d / 2, y1, fill=color, outline="")

    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        self._pill(0, 0, W, H, PILL_BG)

        mid = H / 2
        if self._state == "recording":
            # X a la izquierda: circulito gris con cruz blanca delgada
            r = 8
            cx = BTN / 2 + 3
            c.create_oval(cx - r, mid - r, cx + r, mid + r, fill=X_BG, outline="")
            a = 3.0
            c.create_line(cx - a, mid - a, cx + a, mid + a, fill=X_COLOR, width=1.5, capstyle="round")
            c.create_line(cx - a, mid + a, cx + a, mid - a, fill=X_COLOR, width=1.5, capstyle="round")
            # Palomita a la derecha: círculo blanco relleno, palomita negra delgada
            kx = W - BTN / 2 - 3
            c.create_oval(kx - r, mid - r, kx + r, mid + r, fill=CHECK_BG, outline="")
            c.create_line(
                kx - 3.5, mid + 0.5, kx - 1, mid + 3, kx + 4, mid - 2.5,
                fill=CHECK_COLOR, width=1.5, capstyle="round", joinstyle="round",
            )
            # Onda al centro
            try:
                level = float(self.get_level())
            except Exception:
                level = 0.0
            self._levels.append(min(1.0, level * 12))
            x0, x1 = BTN + 6, W - BTN - 6
            gap = (x1 - x0) / (BARS - 1)
            for i, lv in enumerate(self._levels):
                x = x0 + i * gap
                h = max(1.0, lv * (H - 12) / 2)
                c.create_line(
                    x, mid - h, x, mid + h,
                    fill=WAVE_COLOR, width=2, capstyle="round",
                )
        else:  # processing: línea con un destello que la recorre
            x0, x1 = 14, W - 14
            c.create_line(x0, mid, x1, mid, fill=LINE_DIM, width=2, capstyle="round")
            span = x1 - x0
            seg = 16
            pos = (self._tick * 3) % (span + seg) - seg
            sx = max(x0, x0 + pos)
            ex = min(x1, x0 + pos + seg)
            if ex > sx:
                c.create_line(sx, mid, ex, mid, fill=LINE_BRIGHT, width=2, capstyle="round")
