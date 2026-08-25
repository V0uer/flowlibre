"""Panel de FlowLibre (estilo Wispr Flow): Home con estadísticas + historial,
y Ajustes para configurar atajo, micrófono, motor y formato.

Corre como Toplevel en el hilo de tkinter del overlay (ver Overlay.submit).
Cerrar la ventana solo la oculta; se reusa la instancia.
"""

from __future__ import annotations

import json
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import ttk

from .config import HISTORY_PATH

BG = "#f4f2ee"          # crema de fondo
SIDEBAR_BG = "#eceae4"
CARD_BG = "#ffffff"
TEXT = "#1a1a1a"
MUTED = "#8a8a88"
ROW_LINE = "#eeece7"
ACCENT_BG = "#1a1a1a"   # botones oscuros
ACCENT_FG = "#ffffff"

FONT = "Segoe UI"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

HOTKEY_MODES = ["hibrido", "push_to_talk", "toggle"]
ENGINES = ["claude", "ollama"]
FORMAT_MODES = ["mensaje", "email", "notas", "crudo"]
INJECT_METHODS = ["clipboard", "typing"]
YES_NO = ["sí", "no"]
DEFAULT_MIC = "(micrófono predeterminado)"


def _load_history() -> list[dict]:
    entries = []
    if HISTORY_PATH.exists():
        for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
    return entries


def _stats(entries: list[dict]) -> tuple[int, int, int]:
    """(palabras totales, wpm promedio, racha de días)."""
    total_words = sum(len(e.get("clean", "").split()) for e in entries)

    words_timed = 0
    minutes = 0.0
    days: set[date] = set()
    for e in entries:
        try:
            d = datetime.fromisoformat(e["timestamp"]).date()
            days.add(d)
        except (KeyError, ValueError):
            continue
        dur = e.get("duration_s")
        if dur and dur >= 2:
            words_timed += len(e.get("clean", "").split())
            minutes += dur / 60
    wpm = round(words_timed / minutes) if minutes > 0 else 0

    streak = 0
    cursor = date.today()
    if cursor not in days:
        cursor -= timedelta(days=1)  # el día apenas empieza: contar desde ayer
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return total_words, wpm, streak


def _fmt_total(n: int) -> str:
    return f"{n / 1000:.1f}K" if n >= 1000 else str(n)


def _day_label(d: date) -> str:
    today = date.today()
    if d == today:
        return "HOY"
    if d == today - timedelta(days=1):
        return "AYER"
    return f"{d.day} de {MESES[d.month - 1]}" + ("" if d.year == today.year else f" de {d.year}")


class Dashboard:
    def __init__(self, root: tk.Tk, app) -> None:
        self.app = app
        self.win = tk.Toplevel(root)
        self.win.title("FlowLibre")
        self.win.geometry("880x600")
        self.win.minsize(700, 480)
        self.win.configure(bg=BG)
        self.win.protocol("WM_DELETE_WINDOW", self.win.withdraw)

        self._build_sidebar()
        self.content = tk.Frame(self.win, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)
        self.home = tk.Frame(self.content, bg=BG)
        self.settings = tk.Frame(self.content, bg=BG)
        self._build_home()
        self._build_settings()
        self._show_tab("home")

    def alive(self) -> bool:
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def show(self) -> None:
        self.refresh()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    # --- sidebar ---

    def _build_sidebar(self) -> None:
        bar = tk.Frame(self.win, bg=SIDEBAR_BG, width=180)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)
        tk.Label(
            bar, text="🎙  FlowLibre", font=(FONT, 13, "bold"),
            bg=SIDEBAR_BG, fg=TEXT, anchor="w",
        ).pack(fill="x", padx=18, pady=(22, 18))
        self._nav_buttons = {}
        for key, label in [("home", "Home"), ("settings", "Ajustes")]:
            btn = tk.Label(
                bar, text=label, font=(FONT, 11), anchor="w",
                bg=SIDEBAR_BG, fg=TEXT, padx=18, pady=7, cursor="hand2",
            )
            btn.pack(fill="x", padx=8)
            btn.bind("<Button-1>", lambda _e, k=key: self._show_tab(k))
            self._nav_buttons[key] = btn

    def _show_tab(self, key: str) -> None:
        for k, btn in self._nav_buttons.items():
            btn.configure(bg=CARD_BG if k == key else SIDEBAR_BG)
        self.home.pack_forget()
        self.settings.pack_forget()
        (self.home if key == "home" else self.settings).pack(fill="both", expand=True)

    # --- Home ---

    def _build_home(self) -> None:
        head = tk.Frame(self.home, bg=BG)
        head.pack(fill="x", padx=28, pady=(24, 12))
        tk.Label(
            head, text="Bienvenido de vuelta, el autor", font=(FONT, 16, "bold"),
            bg=BG, fg=TEXT,
        ).pack(side="left")

        self.stats_card = tk.Frame(self.home, bg=CARD_BG, padx=22, pady=14)
        self.stats_card.pack(fill="x", padx=28)
        self._stat_labels = {}
        for key in ("words", "wpm", "streak"):
            row = tk.Frame(self.stats_card, bg=CARD_BG)
            row.pack(side="left", padx=(0, 40))
            big = tk.Label(row, text="—", font=(FONT, 20, "bold"), bg=CARD_BG, fg=TEXT)
            big.pack(anchor="w")
            small = tk.Label(row, text="", font=(FONT, 9), bg=CARD_BG, fg=MUTED)
            small.pack(anchor="w")
            self._stat_labels[key] = (big, small)
        self._stat_labels["words"][1].configure(text="palabras totales")
        self._stat_labels["wpm"][1].configure(text="palabras por minuto")
        self._stat_labels["streak"][1].configure(text="días de racha")

        # Historial con scroll
        wrap = tk.Frame(self.home, bg=BG)
        wrap.pack(fill="both", expand=True, padx=28, pady=(16, 20))
        self.hist_canvas = tk.Canvas(wrap, bg=CARD_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.hist_canvas.yview)
        self.hist_frame = tk.Frame(self.hist_canvas, bg=CARD_BG)
        self.hist_frame.bind(
            "<Configure>",
            lambda _e: self.hist_canvas.configure(scrollregion=self.hist_canvas.bbox("all")),
        )
        self._hist_window = self.hist_canvas.create_window(
            (0, 0), window=self.hist_frame, anchor="nw"
        )
        self.hist_canvas.bind(
            "<Configure>",
            lambda e: self.hist_canvas.itemconfigure(self._hist_window, width=e.width),
        )
        self.hist_canvas.configure(yscrollcommand=scroll.set)
        self.hist_canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.hist_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.hist_canvas.yview_scroll(-1 * (e.delta // 120), "units"),
        )

    def refresh(self) -> None:
        entries = _load_history()
        total, wpm, streak = _stats(entries)
        self._stat_labels["words"][0].configure(text=_fmt_total(total))
        self._stat_labels["wpm"][0].configure(text=str(wpm))
        self._stat_labels["streak"][0].configure(text=str(streak))
        self._fill_history(entries)
        self._load_settings_values()

    def _fill_history(self, entries: list[dict]) -> None:
        for child in self.hist_frame.winfo_children():
            child.destroy()
        if not entries:
            tk.Label(
                self.hist_frame, text="Aún no hay dictados. Mantén Win+Ctrl y habla.",
                font=(FONT, 10), bg=CARD_BG, fg=MUTED, pady=30,
            ).pack()
            return

        last_day = None
        for e in reversed(entries[-200:]):  # más recientes primero
            try:
                ts = datetime.fromisoformat(e["timestamp"])
            except (KeyError, ValueError):
                continue
            text = e.get("clean", "").strip()
            if not text:
                continue
            if ts.date() != last_day:
                last_day = ts.date()
                tk.Label(
                    self.hist_frame, text=_day_label(last_day), font=(FONT, 8, "bold"),
                    bg=CARD_BG, fg=MUTED, anchor="w", padx=18, pady=6,
                ).pack(fill="x", pady=(8, 0))
            row = tk.Frame(self.hist_frame, bg=CARD_BG, cursor="hand2")
            row.pack(fill="x")
            tk.Frame(row, bg=ROW_LINE, height=1).pack(fill="x")
            inner = tk.Frame(row, bg=CARD_BG, padx=18, pady=8)
            inner.pack(fill="x")
            tk.Label(
                inner, text=ts.strftime("%H:%M"), font=(FONT, 9),
                bg=CARD_BG, fg=MUTED, width=6, anchor="nw",
            ).pack(side="left")
            lbl = tk.Label(
                inner, text=text, font=(FONT, 10), bg=CARD_BG, fg=TEXT,
                anchor="w", justify="left", wraplength=520,
            )
            lbl.pack(side="left", fill="x", expand=True)
            for widget in (row, inner, lbl):
                widget.bind("<Button-1>", lambda _e, t=text: self._copy(t))

    def _copy(self, text: str) -> None:
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        old = self.win.title()
        self.win.title("FlowLibre — copiado ✓")
        self.win.after(1200, lambda: self.win.title(old))

    # --- Ajustes ---

    def _build_settings(self) -> None:
        tk.Label(
            self.settings, text="Ajustes", font=(FONT, 16, "bold"), bg=BG, fg=TEXT,
        ).pack(anchor="w", padx=28, pady=(24, 12))
        card = tk.Frame(self.settings, bg=CARD_BG, padx=24, pady=18)
        card.pack(fill="x", padx=28)

        self._vars: dict[str, tk.StringVar] = {}

        def field(row: int, label: str, key: str, values: list[str] | None, hint: str = ""):
            tk.Label(card, text=label, font=(FONT, 10), bg=CARD_BG, fg=TEXT).grid(
                row=row, column=0, sticky="w", pady=6
            )
            var = tk.StringVar()
            self._vars[key] = var
            if values is None:
                w = ttk.Entry(card, textvariable=var, width=34, font=(FONT, 10))
            else:
                w = ttk.Combobox(
                    card, textvariable=var, values=values, width=32,
                    state="readonly", font=(FONT, 10),
                )
            w.grid(row=row, column=1, sticky="w", padx=(16, 0), pady=6)
            if hint:
                tk.Label(card, text=hint, font=(FONT, 8), bg=CARD_BG, fg=MUTED).grid(
                    row=row, column=2, sticky="w", padx=(12, 0)
                )

        field(0, "Atajo", "hotkey", None, 'ej. "windows+ctrl", "f8"')
        field(1, "Modo del atajo", "hotkey_mode", HOTKEY_MODES,
              "hibrido: mantener o doble toque")
        field(2, "Atajo música (m!p)", "music_hotkey", None, 'ej. "f7+f8"; vacío = off')
        field(3, "Enter automático (m!p)", "music_send_enter", YES_NO,
              "envía el comando solo")
        field(4, "Micrófono", "microphone", self._mic_options())
        field(5, "Motor de limpieza", "engine", ENGINES, "claude = API, ollama = local")
        field(6, "Modo de formato", "format_mode", FORMAT_MODES)
        field(7, "Modelo de Claude", "claude_model", None)
        field(8, "Inyección de texto", "inject_method", INJECT_METHODS,
              "typing si una app bloquea el pegado")

        self._save_note = tk.Label(self.settings, text="", font=(FONT, 9), bg=BG, fg=MUTED)
        btn = tk.Label(
            self.settings, text="Guardar y aplicar", font=(FONT, 10, "bold"),
            bg=ACCENT_BG, fg=ACCENT_FG, padx=18, pady=8, cursor="hand2",
        )
        btn.pack(anchor="w", padx=28, pady=(16, 4))
        btn.bind("<Button-1>", lambda _e: self._save_settings())
        self._save_note.pack(anchor="w", padx=28)

    def _mic_options(self) -> list[str]:
        options = [DEFAULT_MIC]
        try:
            import sounddevice as sd

            seen = set()
            for dev in sd.query_devices():
                name = dev["name"].strip()
                if dev["max_input_channels"] > 0 and name not in seen:
                    seen.add(name)
                    options.append(name)
        except Exception:
            pass
        return options

    def _load_settings_values(self) -> None:
        cfg = self.app.config
        for key in ("hotkey", "hotkey_mode", "music_hotkey", "engine",
                    "format_mode", "claude_model", "inject_method"):
            self._vars[key].set(str(getattr(cfg, key)))
        self._vars["music_send_enter"].set("sí" if cfg.music_send_enter else "no")
        mic = cfg.microphone
        self._vars["microphone"].set(DEFAULT_MIC if mic in (None, "") else str(mic))

    def _save_settings(self) -> None:
        cfg = self.app.config
        for key, var in self._vars.items():
            value = var.get().strip()
            if key == "microphone":
                value = None if value == DEFAULT_MIC else value
            elif key == "music_send_enter":
                value = (value == "sí")
            if getattr(cfg, key) != value:
                cfg.set(key, value)
        self.app.reload_config()
        self._save_note.configure(text="Guardado y aplicado ✓")
        self.win.after(2500, lambda: self._save_note.configure(text=""))
