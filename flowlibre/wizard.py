"""Los cuatro pasos del primer arranque.

La app instalada llega a una maquina que no tiene Python, ni CUDA, ni modelo, ni
API key, y cuyo dueno no leyo ningun README. El criterio 4 del spec pide que del
link a la primera frase dictada pasen menos de cinco minutos; este archivo es
casi todo ese presupuesto.

Cuatro pasos, y ninguno puede ser obligatorio salvo el ultimo:

1. **Bienvenida** — que atajo usar. Es lo unico que hay que saber para dictar.
2. **API key** — con boton de saltar bien visible. Sin key la app funciona en
   modo crudo: transcribe y escribe, solo que no limpia el texto. Decirlo
   explicito, porque "necesita una API key" hace que la mitad de la gente cierre
   el instalador.
3. **Microfono** — con el medidor en vivo del overlay. Elegir microfono a ciegas
   de una lista de nombres cripticos es la forma mas comun de acabar con una app
   de dictado que "no funciona".
4. **Modelo** — descarga con barra de progreso, y solo lo que esta maquina puede
   usar de verdad (ver plan_de_modelo).

**La API key se guarda como variable de entorno de usuario, nunca en
config.yaml**: ese archivo es justo el que la gente copia y pega cuando reporta
un problema.
"""

from __future__ import annotations

import collections
import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk

from . import descargas, gpu, paths

# Sin consola negra parpadeando (la app vive en la bandeja).
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

BG = "#f4f2ee"
CARD_BG = "#ffffff"
TEXT = "#1a1a1a"
MUTED = "#8a8a88"
ACCENT_BG = "#1a1a1a"
ACCENT_FG = "#ffffff"
FONT = "Segoe UI"

W, H = 560, 430


def necesita_wizard() -> bool:
    """True si esta maquina nunca ha corrido FlowLibre."""
    return not (paths.data_dir() / "config.yaml").exists()


def preparar_datos() -> bool:
    """Siembra los datos del usuario y dice si hay que correr el wizard.

    **El orden no es negociable.** `sembrar()` copia el config.yaml que trae la
    instalacion al directorio de datos; preguntar despues devolveria siempre
    "no hace falta" y el wizard no correria en ninguna maquina, jamas. El bug no
    tendria sintoma: la app abre perfecta y nadie ve nunca la bienvenida.
    """
    hace_falta = necesita_wizard()
    sembrados = paths.sembrar()
    if sembrados:
        # Se imprime aqui y no en main() porque este es el unico lugar que sabe
        # que se copio. Es la evidencia de que la migracion a %APPDATA% ocurrio.
        print(f"Datos iniciales copiados a {paths.data_dir()}: {', '.join(sembrados)}")
    return hace_falta


def guardar_api_key(valor: str) -> None:
    """Persiste la key como variable de entorno de usuario, no en config.yaml."""
    valor = (valor or "").strip()
    if not valor:
        return          # saltar el paso no debe dejar la variable puesta en blanco
    os.environ["ANTHROPIC_API_KEY"] = valor      # sirve ya, sin reiniciar
    try:
        subprocess.run(["setx", "ANTHROPIC_API_KEY", valor],
                       capture_output=True, creationflags=_SIN_VENTANA, timeout=10)
    except Exception as e:
        print(f"[FlowLibre] No se pudo persistir la API key: {e}")


def plan_de_modelo() -> dict:
    """Que hay que bajar en ESTA maquina, y que no.

    Sin NVIDIA no se bajan 1.4 GB de CUDA que no se van a poder usar: `small`
    corre en CPU y faster-whisper lo trae de Hugging Face solo. Con NVIDIA si
    valen la pena el paquete de aceleracion y el turbo cuantizado a int8, que
    pesa 0.82 GB contra 1.6 GB del fp16 con el mismo texto y la misma velocidad.
    """
    perfil = gpu.perfil_recomendado()
    perfil["descarga"] = [descargas.CUDA, descargas.MODELO_INT8] if perfil["acelerada"] else None
    return perfil


# --- interfaz ---------------------------------------------------------------


class Wizard(tk.Toplevel):
    """Corre como Toplevel en el hilo de tkinter del overlay (ver Overlay.submit).

    No se prueba con pytest: necesita display, microfono y una descarga de
    verdad. Lo que si se prueba es la logica de arriba, que es donde viven los
    fallos silenciosos.
    """

    def __init__(self, master, app, al_terminar=None) -> None:
        super().__init__(master)
        self.app = app
        self.al_terminar = al_terminar
        self.paso = 0
        self._mic_var = tk.StringVar()
        self._key_var = tk.StringVar()
        self._niveles = None
        self._barra = None
        self._estado = None

        self.title("Bienvenido a FlowLibre")
        self.configure(bg=BG)
        self.geometry(f"{W}x{H}")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._terminar)

        self.cuerpo = tk.Frame(self, bg=BG)
        self.cuerpo.pack(fill="both", expand=True, padx=28, pady=(28, 0))
        self.pie = tk.Frame(self, bg=BG)
        self.pie.pack(fill="x", padx=28, pady=18)

        self._render()

    # --- navegacion ---

    def _render(self) -> None:
        for w in list(self.cuerpo.winfo_children()) + list(self.pie.winfo_children()):
            w.destroy()
        [self._bienvenida, self._api_key, self._microfono, self._modelo][self.paso]()

    def _siguiente(self) -> None:
        if self.paso >= 3:
            self._terminar()
            return
        self.paso += 1
        self._render()

    def _titulo(self, texto: str, sub: str = "") -> None:
        tk.Label(self.cuerpo, text=texto, bg=BG, fg=TEXT,
                 font=(FONT, 20, "bold"), anchor="w").pack(fill="x")
        if sub:
            tk.Label(self.cuerpo, text=sub, bg=BG, fg=MUTED, font=(FONT, 10),
                     anchor="w", justify="left",
                     wraplength=W - 60).pack(fill="x", pady=(6, 18))

    def _botones(self, principal: str, on_principal=None,
                 secundario: str | None = None, on_sec=None) -> None:
        tk.Button(self.pie, text=principal, command=on_principal or self._siguiente,
                  bg=ACCENT_BG, fg=ACCENT_FG, font=(FONT, 10, "bold"), relief="flat",
                  padx=22, pady=8, cursor="hand2").pack(side="right")
        if secundario:
            tk.Button(self.pie, text=secundario, command=on_sec or self._siguiente,
                      bg=BG, fg=MUTED, font=(FONT, 10), relief="flat",
                      padx=12, cursor="hand2").pack(side="right", padx=(0, 10))
        tk.Label(self.pie, text=f"Paso {self.paso + 1} de 4", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="left")

    # --- paso 1: bienvenida ---

    def _bienvenida(self) -> None:
        atajo = self.app.config.hotkey
        self._titulo("FlowLibre",
                     "Dictado por voz que se escribe donde tengas el cursor.")
        tarjeta = tk.Frame(self.cuerpo, bg=CARD_BG)
        tarjeta.pack(fill="x", pady=4)
        tk.Label(tarjeta, text=f"Manten {atajo} y habla.", bg=CARD_BG, fg=TEXT,
                 font=(FONT, 15)).pack(pady=(24, 6))
        tk.Label(tarjeta, text="Al soltar, el texto aparece donde estaba el cursor.",
                 bg=CARD_BG, fg=MUTED, font=(FONT, 10)).pack(pady=(0, 24))
        self._botones("Empezar")

    # --- paso 2: API key ---

    def _api_key(self) -> None:
        self._titulo(
            "Limpieza del texto (opcional)",
            "Con una API key de Anthropic, FlowLibre limpia lo que dictas: quita "
            "muletillas, puntua y ordena.\n\nSin key la app funciona igual y escribe "
            "lo que dictas tal cual (modo crudo). La puedes poner despues en Ajustes.",
        )
        ttk.Entry(self.cuerpo, textvariable=self._key_var, show="•",
                  width=52).pack(anchor="w", ipady=4)
        tk.Label(self.cuerpo,
                 text="Se guarda como variable de entorno de tu usuario, no en los "
                      "archivos de configuracion.",
                 bg=BG, fg=MUTED, font=(FONT, 9), anchor="w",
                 wraplength=W - 60, justify="left").pack(fill="x", pady=(8, 0))
        self._botones("Continuar", secundario="Saltar por ahora", on_sec=self._saltar_key)

    def _saltar_key(self) -> None:
        self._key_var.set("")
        self._siguiente()

    # --- paso 3: microfono ---

    def _microfono(self) -> None:
        # El medidor es el mismo del overlay, no otro: una segunda implementacion
        # se desincroniza y acaba mostrando un nivel que no es el que la app oye.
        from .overlay import BARS, dibujar_onda, escala_nivel

        self._titulo("Microfono", "Habla un momento: las barras deben moverse.")
        nombres = self._listar_micros()
        combo = ttk.Combobox(self.cuerpo, textvariable=self._mic_var,
                             values=nombres, state="readonly", width=52)
        combo.pack(anchor="w")
        if nombres:
            combo.current(0)

        lienzo = tk.Canvas(self.cuerpo, width=W - 60, height=64, bg=CARD_BG,
                           highlightthickness=0)
        lienzo.pack(fill="x", pady=18)
        self._niveles = collections.deque([0.0] * BARS, maxlen=BARS)

        def latir() -> None:
            if not lienzo.winfo_exists():
                return
            try:
                self._niveles.append(escala_nivel(self.app.recorder.level))
            except Exception:
                self._niveles.append(0.0)
            lienzo.delete("all")
            dibujar_onda(lienzo, self._niveles, 24, W - 84, 32, 56, color=TEXT)
            lienzo.after(40, latir)

        latir()
        self._botones("Continuar")

    def _listar_micros(self) -> list[str]:
        try:
            import sounddevice as sd

            return [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]
        except Exception:
            return []       # sin lista, se queda el microfono predeterminado

    # --- paso 4: modelo ---

    def _modelo(self) -> None:
        plan = plan_de_modelo()
        self._plan = plan
        if plan["acelerada"]:
            sub = ("Detectamos una GPU NVIDIA. Falta bajar el paquete de aceleracion "
                   "y el modelo. Puedes seguir usando la PC mientras tanto, y si se "
                   "corta la descarga, retoma donde se quedo.")
        else:
            sub = ("Esta maquina no tiene GPU NVIDIA, asi que FlowLibre usara el "
                   "modelo ligero en CPU. Se baja solo la primera vez que dictes.")
        self._titulo("Ultimo paso", sub)

        self._barra = ttk.Progressbar(self.cuerpo, length=W - 60, mode="determinate")
        self._barra.pack(pady=(4, 6))
        self._estado = tk.Label(self.cuerpo, text="", bg=BG, fg=MUTED,
                                font=(FONT, 9), anchor="w")
        self._estado.pack(fill="x")

        if plan["acelerada"]:
            self._botones("Descargar", on_principal=self._descargar,
                          secundario="Despues", on_sec=self._terminar)
        else:
            self._botones("Terminar", on_principal=self._terminar)

    def _descargar(self) -> None:
        def progreso(hecho: int, total: int) -> None:
            pct = (hecho / total * 100) if total else 0
            mb = f"{hecho // (1 << 20)} de {total // (1 << 20)} MB"
            self.after(0, lambda: self._pinta_progreso(pct, mb))

        def trabajo() -> None:
            try:
                descargas.instalar_cuda(on_progress=progreso)
            except Exception as e:
                aviso = f"No se pudo descargar: {e}. Puedes reintentar desde Ajustes."
                self.after(0, lambda: self._pinta_progreso(0, aviso))
                return
            self.after(0, self._terminar)

        self._pinta_progreso(0, "Empezando...")
        threading.Thread(target=trabajo, daemon=True).start()

    def _pinta_progreso(self, pct: float, texto: str) -> None:
        if self._barra is not None and self._barra.winfo_exists():
            self._barra.config(value=pct)
            self._estado.config(text=texto)

    # --- salida ---

    def _terminar(self) -> None:
        guardar_api_key(self._key_var.get())
        plan = plan_de_modelo()
        try:
            self.app.config.set("whisper_model", plan["whisper_model"])
            self.app.config.set("whisper_compute_type", plan["whisper_compute_type"])
            if self._mic_var.get():
                self.app.config.set("microphone", self._mic_var.get())
            if not os.environ.get("ANTHROPIC_API_KEY"):
                # Sin key, el Motor B no puede limpiar. Dejar la app en crudo es
                # mejor que un error en cada dictado.
                self.app.config.set("format_mode", "crudo")
            self.app.reload_config()
        except Exception as e:
            print(f"[FlowLibre] El wizard no pudo guardar la configuracion: {e}")
        if self.al_terminar:
            self.al_terminar()
        self.destroy()
