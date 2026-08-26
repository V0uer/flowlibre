"""Mide la latencia de punta a punta contra WAVs de referencia.

Uso:  .venv/Scripts/python.exe tools/bench.py [ruta.wav ...]

Sin argumentos usa tests/fixtures/voz_{6,21,60}s.wav. Imprime la mediana de
cada etapa para poder comparar antes y despues de un cambio.
"""

from __future__ import annotations

import os
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

    # "No se pudo medir" (falta la API key, así que ni lo intentamos: fallaría
    # siempre y no es un dato del sistema) es distinto de "se intentó y falló"
    # (la key está puesta pero clean() truena: rate limit, red, bug real). Lo
    # primero no debe imprimir un error; lo segundo no debe imprimirse como si
    # fuera lo primero, o quien mida busca el problema en el lugar equivocado.
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    skip_clean = cfg.engine == "claude" and not has_key

    whisper_times, clean_times = [], []
    clean_error = None
    for _ in range(reps):
        t = time.perf_counter()
        text, _ = tr.transcribe(audio, "es")
        whisper_times.append(time.perf_counter() - t)

        if skip_clean:
            continue

        t = time.perf_counter()
        try:
            cleaner.clean(text, cfg.format_mode)
            clean_times.append(time.perf_counter() - t)
        except Exception as e:
            # Una repetición que falla no debe tirar las que sí funcionaron:
            # la mediana se calcula solo con éxitos, y solo es None si NINGUNA
            # repetición pudo medirse. Guardamos tipo + mensaje truncado (nunca
            # la excepción cruda) porque esta salida se guarda en
            # docs/superpowers/baseline-*.txt, que sí se versiona en git, y
            # str(e) podría en teoría llevar datos sensibles de la petición.
            clean_error = (type(e).__name__, str(e)[:200])

    w = statistics.median(whisper_times)
    c = statistics.median(clean_times) if clean_times else None
    result = {"whisper_s": w, "clean_s": c, "total_s": w + c if c is not None else w}
    if skip_clean:
        result["clean_skip_reason"] = "sin ANTHROPIC_API_KEY"
    elif clean_error is not None:
        result["clean_error"] = clean_error
    return result


def main() -> None:
    paths = sys.argv[1:] or [
        str(ROOT / "tests" / "fixtures" / f"voz_{n}s.wav") for n in (6, 21, 60)
    ]
    missing_key = False
    real_errors = []  # [(nombre_archivo, tipo_excepcion, mensaje_truncado), ...]
    print(f"{'archivo':<20} {'whisper':>9} {'limpieza':>9} {'total':>9}")
    print("-" * 50)
    for p in paths:
        if not Path(p).exists():
            print(f"{Path(p).name:<20} {'(falta)':>9}")
            continue
        r = bench_file(p)
        clean_str = f"{r['clean_s']:8.2f}s" if r["clean_s"] is not None else f"{'n/d':>9}"
        print(f"{Path(p).name:<20} {r['whisper_s']:8.2f}s {clean_str} {r['total_s']:8.2f}s")

        if "clean_skip_reason" in r:
            missing_key = True
        if "clean_error" in r:
            etype, emsg = r["clean_error"]
            real_errors.append((Path(p).name, etype, emsg))

    if missing_key:
        print(
            "\nAviso: la etapa de limpieza no se pudo medir porque falta "
            "ANTHROPIC_API_KEY. Definela para incluirla en el benchmark."
        )
    if real_errors:
        print(
            "\nAviso: la limpieza fallo en al menos una repeticion PESE A TENER "
            "ANTHROPIC_API_KEY presente (no es un problema de la key):"
        )
        for name, etype, emsg in real_errors:
            print(f"  {name}: {etype}: {emsg}")


if __name__ == "__main__":
    main()
