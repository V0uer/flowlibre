"""Historial de dictados en history.jsonl (una línea JSON por dictado)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .config import HISTORY_PATH


def append_entry(
    raw: str, clean: str, mode: str, language: str, engine: str,
    duration_s: float | None = None,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "raw": raw,
        "clean": clean,
        "mode": mode,
        "language": language,
        "engine": engine,
    }
    if duration_s and duration_s > 0:
        entry["duration_s"] = round(duration_s, 1)
        words = len(clean.split())
        entry["wpm"] = round(words / (duration_s / 60), 1)
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
