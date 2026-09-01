"""Orquestador: hotkey → grabar → transcribir → limpiar → inyectar → historial."""

from __future__ import annotations

import threading
import winsound

from .audio import Recorder
from .clean import CleanerError, get_cleaner
from .commands import CommandProcessor
from .config import Config
from .history import append_entry
from .hotkey import HotkeyManager, _dbg
from .inject import delete_chars, inject_text, send_enter
from .overlay import Overlay
from .transcribe import Transcriber


def _beep(freq: int, ms: int = 110) -> None:
    threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()


class FlowLibreApp:
    def __init__(self) -> None:
        self.config = Config()
        self.recorder = self._make_recorder()
        self.transcriber = Transcriber(
            self.config.whisper_model, self.config.whisper_compute_type,
            self.config.whisper_beam_size,
        )
        self.commands = CommandProcessor()
        self.overlay = Overlay(
            lambda: self.recorder.level,
            on_cancel=self._click_cancel,
            on_confirm=self._click_confirm,
        )
        self.hotkeys: HotkeyManager | None = None
        self.music_hotkeys: HotkeyManager | None = None
        self.cleaner = None      # motor de limpieza activo, cacheado (ver _get_cleaner)
        self._dashboard = None
        self.enabled = True
        self._active_prefix = ""     # prefijo del dictado en curso ("" = dictado normal)
        self._stream_stt = None      # StreamingTranscriber del dictado en curso
        self.last_injected = ""
        self.status = "listo"           # leído por el tray para el tooltip/ícono
        self.on_status_change = None    # callback que instala el tray
        self._busy = threading.Lock()

    def _make_recorder(self) -> Recorder:
        """Un solo lugar donde se cablea el troceo: si aqui se cae el on_chunk,
        la app sigue funcionando pero pierde toda la mejora de latencia sin
        avisar. Por eso lo construyen por igual __init__ y reload_config()."""
        return Recorder(
            self.config.microphone,
            on_chunk=self._on_chunk if self.config.streaming_stt else None,
        )

    # --- ciclo de vida ---

    def start(self) -> None:
        self.hotkeys = HotkeyManager(
            self.config.hotkey, self.config.hotkey_mode,
            on_start=self.start_recording, on_stop=self.stop_recording,
            on_cancel=self.cancel_recording,
        )
        self.hotkeys.register()
        self._register_music_hotkey()
        # Precalentar Whisper en background para que el primer dictado sea rápido.
        threading.Thread(target=self.transcriber.load, daemon=True).start()
        # Avisar temprano si el motor activo no está listo (no bloquea).
        threading.Thread(target=self._check_engine, daemon=True).start()

    def _register_music_hotkey(self) -> None:
        """2º atajo opcional: dicta en crudo y antepone music_prefix (ej. "m!p ").
        Usa el mismo hotkey_mode que el atajo principal."""
        if not self.config.music_hotkey:
            self.music_hotkeys = None
            return
        prefix = self.config.music_prefix
        self.music_hotkeys = HotkeyManager(
            self.config.music_hotkey, self.config.hotkey_mode,
            on_start=lambda: self.start_recording(prefix),
            on_stop=self.stop_recording,
            on_cancel=self.cancel_recording,
        )
        self.music_hotkeys.register()

    def _get_cleaner(self):
        """Motor de limpieza activo, cacheado entre dictados.

        get_cleaner() construye un objeto nuevo en cada llamada; cachearlo aquí
        es lo que hace que el cliente HTTP (y su conexión TLS) sobreviva entre
        dictados, en vez de descartarse en la línea siguiente a como se crea.

        Se reconstruye si cambió el motor activo, porque el menú de la bandeja
        escribe config.engine directo (Config.set) sin pasar por
        reload_config(): sin este chequeo, cambiar de motor desde la bandeja
        no surtiría efecto hasta reiniciar la app.
        """
        if self.cleaner is None or self.cleaner.name != self.config.engine:
            self._close_cleaner()
            self.cleaner = get_cleaner(self.config)
        return self.cleaner

    def _close_cleaner(self) -> None:
        """Libera el cleaner cacheado (cierra su cliente HTTP si tiene uno)."""
        if self.cleaner is not None:
            self.cleaner.close()

    def _check_engine(self) -> None:
        cleaner = self._get_cleaner()
        problem = cleaner.check_ready()
        if problem:
            print(f"[FlowLibre] Aviso del motor de limpieza:\n{problem}")
        # No precalienta TLS (httpx no conecta hasta el primer request real):
        # esto sirve para detectar temprano que falta httpx, que falta la key,
        # o que la config está incompleta, sin esperar al primer dictado.
        if hasattr(cleaner, "_get_client"):
            try:
                cleaner._get_client()
            except Exception as e:
                print(f"[FlowLibre] No se pudo precalentar el Motor B: {type(e).__name__}: {e}")

    def reload_config(self) -> None:
        self.config.reload()
        self.commands.reload()
        self._close_cleaner()
        self.cleaner = None       # se reconstruye al cambiar de motor/modelo/timeout
        if self.hotkeys:
            self.hotkeys.unregister()
        self.recorder = self._make_recorder()
        if (self.transcriber.model_name != self.config.whisper_model
                or self.transcriber.compute_type != self.config.whisper_compute_type
                or self.transcriber.beam_size != self.config.whisper_beam_size):
            self.transcriber = Transcriber(
                self.config.whisper_model, self.config.whisper_compute_type,
                self.config.whisper_beam_size,
            )
        self.hotkeys = HotkeyManager(
            self.config.hotkey, self.config.hotkey_mode,
            on_start=self.start_recording, on_stop=self.stop_recording,
            on_cancel=self.cancel_recording,
        )
        self.hotkeys.register()
        if self.music_hotkeys:
            self.music_hotkeys.unregister()
        self._register_music_hotkey()

    def shutdown(self) -> None:
        if self.hotkeys:
            self.hotkeys.unregister()
        if self.music_hotkeys:
            self.music_hotkeys.unregister()
        self._close_cleaner()

    def open_dashboard(self) -> None:
        """Abre (o trae al frente) el panel. Corre en el hilo de tkinter."""
        def _open() -> None:
            from .dashboard import Dashboard
            if self._dashboard is None or not self._dashboard.alive():
                self._dashboard = Dashboard(self.overlay.root, self)
            self._dashboard.show()
        self.overlay.submit(_open)

    def _set_status(self, status: str) -> None:
        self.status = status
        if self.on_status_change:
            self.on_status_change(status)

    # --- pipeline de dictado ---

    def start_recording(self, prefix: str = "") -> None:
        if not self.enabled or self.recorder.recording:
            _dbg(f"start_recording ignorado (enabled={self.enabled}, recording={self.recorder.recording})")
            return
        self._active_prefix = prefix
        try:
            if self.config.streaming_stt:
                from .stream_stt import StreamingTranscriber
                lang = None if self.config.language == "auto" else self.config.language
                self._stream_stt = StreamingTranscriber(self.transcriber, lang)
            self.recorder.start()
            self._set_status("grabando")
            _dbg("grabando (mic abierto)")
            self.overlay.show_recording()
        except Exception as e:
            _dbg(f"ERROR al abrir el micrófono: {e}")
            print(f"[FlowLibre] Error al abrir el micrófono: {e}")
            _beep(220, 300)

    def _on_chunk(self, chunk) -> None:
        """Cada trozo cerrado se manda a transcribir sin esperar a que el
        usuario suelte la tecla."""
        if self._stream_stt is not None:
            self._stream_stt.submit(chunk)

    def stop_recording(self) -> None:
        if not self.recorder.recording:
            return
        audio = self.recorder.stop()          # emite el trozo final via on_chunk
        prefix = self._active_prefix
        stt = self._stream_stt
        self._stream_stt = None
        self._set_status("procesando")
        _dbg(f"procesando: {len(audio)} muestras ({len(audio)/16000:.1f}s) prefijo={prefix!r}")
        self.overlay.show_processing()
        threading.Thread(
            target=self._process, args=(audio, prefix, stt), daemon=True
        ).start()

    def _click_cancel(self) -> None:
        """Clic en la X del overlay: descartar el dictado."""
        _dbg("clic en X: cancelar")
        if self.hotkeys:
            self.hotkeys.reset()
        self.cancel_recording()

    def _click_confirm(self) -> None:
        """Clic en la ✓ del overlay: terminar el dictado (como soltar el atajo)."""
        _dbg("clic en ✓: confirmar")
        if self.hotkeys:
            self.hotkeys.reset()
        self.stop_recording()

    def cancel_recording(self) -> None:
        """Descarta la grabación en curso sin transcribir (toque único suelto)."""
        if not self.recorder.recording:
            return
        # Soltar el transcriptor ANTES de parar: recorder.stop() emite el trozo
        # final por on_chunk, y mandarlo a la GPU en un dictado cancelado es
        # trabajo tirado sobre el recurso que ya estaba en disputa.
        stt = self._stream_stt
        self._stream_stt = None
        if stt is not None:
            stt.cancel()
        self.recorder.stop()
        self.overlay.hide()
        self._set_status("listo")

    def _process(self, audio, prefix: str = "", stt=None) -> None:
        with self._busy:
            try:
                lang_cfg = None if self.config.language == "auto" else self.config.language
                text, language = "", ""
                if stt is not None:
                    try:
                        text, language = stt.result()
                    except Exception as e:
                        # El streaming fallo, pero el audio completo sigue en
                        # memoria: retranscribir cuesta segundos, no hacerlo
                        # cuesta el dictado entero.
                        _dbg(f"streaming fallo ({type(e).__name__}: {e}); uso el audio completo")
                        print(f"[FlowLibre] Transcripción por trozos falló ({e}); "
                              f"reintento con el audio completo.")
                    if not text and len(audio):
                        _dbg("streaming devolvió vacío; retranscribo el audio completo")
                        text, language = self.transcriber.transcribe(audio, lang_cfg)
                elif len(audio):
                    text, language = self.transcriber.transcribe(audio, lang_cfg)
                _dbg(f"whisper devolvió {len(text)} chars: {text[:80]!r}")
                if text:
                    self._pipeline(text, language, len(audio) / 16000, prefix)
            except Exception as e:
                _dbg(f"ERROR en pipeline: {type(e).__name__}: {e}")
                print(f"[FlowLibre] Error en el pipeline: {e}")
                _beep(220, 300)
            finally:
                self.overlay.hide()
                self._set_status("listo")

    def _pipeline(self, text: str, language: str, audio_duration_s: float,
                  prefix: str = "") -> None:
        raw_text = text

        # Modo con prefijo (ej. "m!p " de Discord): texto crudo, sin comandos de
        # voz ni limpieza IA; solo se antepone el prefijo tal cual.
        if prefix:
            text = prefix + raw_text
            _dbg(f"inyectando {len(text)} chars (modo prefijo {prefix!r})")
            inject_text(text, self.config.inject_method)
            if self.config.music_send_enter:
                send_enter()
            self.last_injected = text
            append_entry(raw_text, text, "crudo", language, f"prefijo {prefix.strip()}",
                         duration_s=audio_duration_s)
            return

        # Comando standalone ("borra eso", "en mayúsculas")
        action = self.commands.match_standalone(raw_text)
        if action == "delete_last":
            if self.last_injected:
                delete_chars(len(self.last_injected))
                self.last_injected = ""
            return
        if action == "uppercase_last":
            if self.last_injected:
                delete_chars(len(self.last_injected))
                upper = self.last_injected.upper()
                inject_text(upper, self.config.inject_method)
                self.last_injected = upper
            return

        # Limpieza con IA (o crudo)
        mode = self.config.format_mode
        engine_used = "crudo"
        if mode == "crudo":
            clean_text = raw_text
        else:
            cleaner = self._get_cleaner()
            engine_used = cleaner.name
            try:
                clean_text = cleaner.clean(raw_text, mode)
            except CleanerError as e:
                fallback_done = False
                if cleaner.name == "claude" and self.config.claude_fallback_to_ollama:
                    from .clean_ollama import OllamaCleaner
                    try:
                        clean_text = OllamaCleaner(self.config).clean(raw_text, mode)
                        engine_used = "ollama (fallback)"
                        fallback_done = True
                    except CleanerError:
                        pass
                if not fallback_done:
                    print(f"[FlowLibre] Motor de limpieza falló, inyectando texto crudo:\n{e}")
                    clean_text = raw_text
                    engine_used = f"{cleaner.name} (falló → crudo)"
                    _beep(330, 200)

        # Comandos inline ("nueva línea", "punto y aparte")
        clean_text = self.commands.apply_inline(clean_text)

        _dbg(f"inyectando {len(clean_text)} chars (motor {engine_used})")
        inject_text(clean_text, self.config.inject_method)
        self.last_injected = clean_text
        append_entry(raw_text, clean_text, mode, language, engine_used,
                     duration_s=audio_duration_s)
