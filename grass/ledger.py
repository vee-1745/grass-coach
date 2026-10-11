"""The Touch-Grass Ledger: a local JSONL file of outings, with streaks and levels."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

LEVELS = [(0, "Seedling"), (60, "Sprout"), (300, "Sapling"), (900, "Oak"), (2400, "Ancient Banyan")]


def _path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "ledger.jsonl"


def add(data_dir: str | Path, note: str, minutes: int, when: datetime | None = None) -> dict:
    when = when or datetime.now()
    entry = {"date": when.date().isoformat(), "ts": when.isoformat(timespec="seconds"), "minutes": minutes, "note": note}
    p = _path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def entries(data_dir: str | Path) -> list[dict]:
    p = _path(data_dir)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a corrupt line should never lock you out of your own log
    return out


def stats(items: list[dict], today: date) -> dict:
    days = sorted({date.fromisoformat(e["date"]) for e in items})
    total = sum(int(e.get("minutes", 0)) for e in items)

    streak = 0
    cursor = today if today in days else today - timedelta(days=1)
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)

    best = run = 0
    prev = None
    for d in days:
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d

    level = max((m, n) for m, n in LEVELS if total >= m)[1]
    nxt = next(((m - total, n) for m, n in LEVELS if m > total), None)
    return {
        "outings": len(items),
        "minutes": total,
        "streak": streak,
        "best_streak": best,
        "level": level,
        "next_level": nxt,
        "touched_today": today in days,
    }
