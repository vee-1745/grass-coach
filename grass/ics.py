"""Tiny local .ics reader. Your calendar never leaves your machine.

Handles: line folding, UTC ("Z") times, floating/TZID times (treated as local),
TRANSPARENT events (ignored), all-day events (ignored). Recurrence rules are
not expanded; export a fresh range from your calendar app instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path


def _unfold(text: str) -> list[str]:
    out: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _parse_dt(value: str, utc_offset: int) -> datetime | None:
    value = value.strip()
    if len(value) < 15:  # DATE only (all-day)
        return None
    dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        dt += timedelta(seconds=utc_offset)
    return dt


def busy_from_ics(path: str | Path, utc_offset: int = 0) -> list[tuple[datetime, datetime]]:
    lines = _unfold(Path(path).read_text(encoding="utf-8", errors="replace"))
    busy: list[tuple[datetime, datetime]] = []
    cur: dict[str, str] | None = None
    for ln in lines:
        if ln == "BEGIN:VEVENT":
            cur = {}
        elif ln == "END:VEVENT":
            if cur is not None and cur.get("TRANSP", "").upper() != "TRANSPARENT":
                try:
                    start = _parse_dt(cur["DTSTART"], utc_offset) if "DTSTART" in cur else None
                    end = _parse_dt(cur["DTEND"], utc_offset) if "DTEND" in cur else None
                except ValueError:
                    start = end = None
                if start is not None:
                    busy.append((start, end if end and end > start else start + timedelta(hours=1)))
            cur = None
        elif cur is not None and ":" in ln:
            key, _, val = ln.partition(":")
            cur[key.split(";")[0].upper()] = val
    return sorted(busy)
