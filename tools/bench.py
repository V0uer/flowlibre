"""Mide la latencia de punta a punta contra WAVs de referencia.

Uso:  .venv/Scripts/python.exe tools/bench.py [ruta.wav ...]

Sin argumentos usa tests/fixtures/voz_{6,21,60}s.wav. Imprime la mediana de
cada etapa para poder comparar antes y despues de un cambio.
"""

from __future__ import annotations

import statistics
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flowlibre.clean import get_cleaner          # noqa: E402
from flowlibre.config import Config              # noqa: E402
from flowlibre.transcribe import Transcriber     # noqa: E402


def load_wav(path: str) -> np.ndarray:
    with wave.open(str(path)) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError(f"{path}: se esperaba 16 kHz mono")
        raw = w.readframes(w.getnframes())
    return (np.frombuffer(raw, dtype="<i2") / 32768.0).astype("float32")


def bench_file(wav_path: str, reps: int = 3) -> dict:
    cfg = Config()
    tr = Transcriber(cfg.whisper_model, cfg.whisper_compute_type)
    cleaner = get_cleaner(cfg)
    audio = load_wav(wav_path)

    tr.transcribe(audio, "es")            # calentamiento: excluye la carga del modelo

    whisper_times, clean_times = [], []
    clean_failed = False
    for _ in range(reps):
        t = time.perf_counter()
        text, _ = tr.transcribe(audio, "es")
        whisper_times.append(time.perf_counter() - t)

        t = time.perf_counter()
        try:
            cleaner.clean(text, cfg.format_mode)
            clean_times.append(time.perf_counter() - t)
        except Exception:
            clean_failed = True

    w = statistics.median(whisper_times)
    c = statistics.median(clean_times) if clean_times and not clean_failed else None
    return {"whisper_s": w, "clean_s": c, "total_s": w + c if c is not None else w}


def main() -> None:
    paths = sys.argv[1:] or [
        str(ROOT / "tests" / "fixtures" / f"voz_{n}s.wav") for n in (6, 21, 60)
    ]
    any_clean_missing = False
    print(f"{'archivo':<20} {'whisper':>9} {'limpieza':>9} {'total':>9}")
    print("-" * 50)
    for p in paths:
        if not Path(p).exists():
            print(f"{Path(p).name:<20} {'(falta)':>9}")
            continue
        r = bench_file(p)
        clean_str = f"{r['clean_s']:8.2f}s" if r["clean_s"] is not None else f"{'n/d':>9}"
        if r["clean_s"] is None:
            any_clean_missing = True
        print(f"{Path(p).name:<20} {r['whisper_s']:8.2f}s {clean_str} {r['total_s']:8.2f}s")

    if any_clean_missing:
        print(
            "\nAviso: la etapa de limpieza no se pudo medir (falla la llamada a la API "
            "de Claude). Define ANTHROPIC_API_KEY para incluirla en el benchmark."
        )


if __name__ == "__main__":
    main()
