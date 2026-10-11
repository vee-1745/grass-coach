from __future__ import annotations

import textwrap

from .quest import day_label, fmt_t
from .score import verdict

W = 58
ICON = {"golden hour": "🌇", "sunrise": "🌅", "after dark": "🌙"}


def _row(label: str, text: str) -> str:
    return textwrap.fill(text, W, initial_indent=f"  {label:<6} ", subsequent_indent=" " * 9)


def render_card(plan, quest, note: str | None) -> str:
    w, now, facts = plan.window, plan.now, plan.facts
    h = w.hour
    out = [f"🌿 GRASS COACH · {now:%a %d %b} · {plan.cfg.place}", "─" * W, f"  {quest.title.upper()}"]
    out.append(textwrap.fill(quest.pitch, W, initial_indent="  ", subsequent_indent="  "))
    out.append("")

    if plan.doorstep:
        out.append(_row("WHEN", "right now, for 5 minutes (no walking required)"))
    else:
        tags = " ".join(f"{ICON.get(t, '')} {t}".strip() for t in w.tags)
        when = f"{fmt_t(w.start)} – {fmt_t(w.end)}  ({day_label(w.start, now)}, in {facts['starts_in_minutes']} min)"
        out.append(_row("WHEN", f"{when}  {tags}".strip()))

    filled = round(w.score / 10)
    out.append(_row("SCORE", f"{w.score}/100 {'█' * filled}{'░' * (10 - filled)} {verdict(w.score)}"))
    aqi = "unknown" if h.aqi is None else f"{round(h.aqi)} ({facts['air_quality']})"
    out.append(_row("SKY", f"{round(h.feels)}°C feels-like · rain {round(h.rain)}% · UV {round(h.uv)} · wind {round(h.wind)} km/h"))
    out.append(_row("AIR", f"AQI {aqi}"))
    out.append(_row("RULE", quest.rule))
    if quest.bring:
        out.append(_row("BRING", ", ".join(quest.bring)))
    for alt in plan.alternatives[:2]:
        tags = f", {alt.tags[0]}" if alt.tags else ""
        out.append(_row("ALSO", f"{day_label(alt.start, now)} {fmt_t(alt.start)} ({alt.score}/100{tags})"))
    out.append("")
    out.append(f"  — {quest.sign_off}")
    out.append("─" * W)

    out.append("Screen time for this card: ~10 seconds. Now close the laptop. 🚪")
    st = plan.streak
    if st:
        out.append(f"Streak: {st} day{'s' if st != 1 else ''}. Don't break it.")
    out.append('When you\'re back: grass done "what you did" -m 25')

    engine = f"model: {quest.source}" if quest.source != "rules" else "model: none (rule-based)"
    if plan.demo:
        data = "forecast: bundled demo data"
    elif plan.fc.stale:
        data = f"forecast: OFFLINE cache, {plan.fc.age_minutes() // 60}h old"
    else:
        data = "forecast: live (Open-Meteo)"
    cal = facts["calendar"]
    out.append(f"[{engine} · {data} · calendar: {cal}]")
    if note:
        out.append(f"[note: {note}]")
    return "\n".join(out)
