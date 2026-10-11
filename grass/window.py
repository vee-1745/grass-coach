"""Find the best free window to go outside: weather score x your calendar x golden hour."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .score import score_at
from .weather import Forecast, Hour

SLOT = timedelta(minutes=15)


@dataclass
class Window:
    start: datetime
    end: datetime
    score: int
    hour: Hour
    tags: list[str] = field(default_factory=list)


def _ceil15(t: datetime) -> datetime:
    t = t.replace(second=0, microsecond=0)
    extra = (-t.minute) % 15
    return t + timedelta(minutes=extra)


def _bonus(fc: Forecast, mid: datetime) -> tuple[float, list[str]]:
    sun = fc.sun.get(mid.date())
    if not sun:
        return 0.0, []
    rise, sset = sun
    if sset - timedelta(minutes=80) <= mid <= sset + timedelta(minutes=5):
        return 10.0, ["golden hour"]
    if rise - timedelta(minutes=10) <= mid <= rise + timedelta(minutes=70):
        return 6.0, ["sunrise"]
    if mid > sset + timedelta(minutes=40) or mid < rise - timedelta(minutes=30):
        return 0.0, ["after dark"]
    return 0.0, []


def best_windows(
    fc: Forecast,
    now: datetime,
    duration: int = 30,
    busy: list[tuple[datetime, datetime]] | tuple = (),
    k: int = 3,
    horizon_h: int = 24,
    lead_min: int = 10,
) -> list[Window]:
    n = max(1, duration // 15)
    t = _ceil15(now + timedelta(minutes=lead_min))
    limit = now + timedelta(hours=horizon_h)
    slots = []
    while t + SLOT <= limit:
        s = score_at(fc, t)
        free = not any(t < b_end and t + SLOT > b_start for b_start, b_end in busy)
        slots.append((t, s, free))
        t += SLOT

    cands: list[tuple[float, Window]] = []
    for i in range(len(slots) - n + 1):
        run = slots[i : i + n]
        if not all(free and s is not None for _, s, free in run):
            continue
        mean = sum(s[0] for _, s, _ in run) / n
        start = run[0][0]
        end = start + SLOT * n
        mid = start + (end - start) / 2
        bonus, tags = _bonus(fc, mid)
        adj = min(100.0, mean + bonus)
        rank = adj - 0.6 * (start - now).total_seconds() / 3600  # mild "sooner is better" bias
        hour = fc.at(mid)
        if hour is None:
            continue
        cands.append((rank, Window(start, end, int(round(adj)), hour, tags)))

    cands.sort(key=lambda c: c[0], reverse=True)
    picked: list[Window] = []
    gap = timedelta(minutes=90)  # alternatives should be genuinely different options
    for _, w in cands:
        if all(w.end + gap <= p.start or w.start >= p.end + gap for p in picked):
            picked.append(w)
            if len(picked) == k:
                break
    return picked
