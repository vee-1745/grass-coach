"""Turn (window + weather) into a side-quest.

Design rule: code decides the facts (time, score, rule); the model only writes the
flavour. Every number the model mentions is checked against the facts it was given,
and if the model is missing, slow or hallucinating, a rule-based writer takes over.
So the app always answers, even on a trail with no signal and no model.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from .llm import LLMError, LLMUnreachable, chat_json
from .score import aqi_word, verdict
from .window import Window

KINDS = {
    "golden_hour": "Chase the golden hour: soft low light and long shadows.",
    "sunrise": "Catch the sunrise before the day gets loud.",
    "petrichor": "A rain-adjacent walk: the smell of wet earth is the prize.",
    "night_walk": "A night walk: cooler air, quiet streets, look up.",
    "cool_shade": "A warm day: go at the coolest free slot, stay shady, carry water.",
    "wander": "An aimless wander that follows one small rule.",
    "doorstep": "No good outdoor window available. The smallest possible dose of outside.",
}

# Tiny constraint games: they make a walk feel like a quest instead of a chore.
RULES = [
    "Turn left at every junction until you've spotted 5 different shades of green.",
    "Take a route you've never taken, even if it's a bit longer.",
    "No headphones. Name 3 distinct sounds before you turn back.",
    "Photograph nothing. Memorise one thing and describe it to someone later.",
    "Find something older than you (a tree, a wall, a temple stone) and say hi.",
    "Walk until you hear a bird you can't name, then watch it for 60 seconds.",
    "Follow the longest shadow you see for the first 5 minutes.",
    "Phone in your bag, on silent, zipped. Only touch it if you're lost.",
    "Count flower colours; stop at 7.",
    "Pick up 3 pieces of litter (if it's safe) and bin them. Leave the place better.",
]
DOORSTEP_RULES = [
    "Look at the farthest thing you can see for 60 seconds, then at the nearest living thing.",
    "Open a window, close your eyes, and count 5 distinct sounds.",
    "Stand barefoot on the floor by the door and take 10 slow breaths of outside air.",
]

VOICES = {
    "ranger": {
        "style": "a warm, slightly corny national-park ranger",
        "open": "Ranger's orders:",
        "close": "Leave only footprints.",
    },
    "sensei": {
        "style": "an over-dramatic anime training-arc mentor",
        "open": "Your training arc begins now.",
        "close": "Believe in your legs!",
    },
    "grandma": {
        "style": "a loving grandmother who thinks you've been indoors far too long",
        "open": "Sweetheart, listen.",
        "close": "And wear proper shoes.",
    },
    "pirate": {
        "style": "a pirate captain who treats the outdoors as buried treasure",
        "open": "Ahoy, landlubber.",
        "close": "X marks the spot, and the spot is outdoors.",
    },
    "deadpan": {
        "style": "a dry, deadpan British naturalist",
        "open": "I suppose you could go outside.",
        "close": "Do try to contain your excitement.",
    },
}

FALLBACK = {
    "golden_hour": (
        "Chase the Golden Hour",
        "The sun sets at {sunset}, so {go_at} is when the light turns soft and everything looks like a film. "
        "It's {feels}°C and the air is {aqi_word} (AQI {aqi}).",
        ["water", "sunglasses", "comfortable shoes"],
    ),
    "sunrise": (
        "Beat the Sunrise",
        "Sunrise is at {sunrise}. At {go_at} the world is quiet, {feels}°C, and the air is {aqi_word} (AQI {aqi}).",
        ["water", "light layer", "comfortable shoes"],
    ),
    "petrichor": (
        "The Wet-Earth Walk",
        "There's a {rain}% chance of rain around {go_at}, which puts that smell of wet earth on the table. "
        "It's {feels}°C, so a light layer is plenty.",
        ["umbrella", "shoes that can splash", "water"],
    ),
    "night_walk": (
        "The Night Shift Walk",
        "After dark at {go_at} it's {feels}°C with {cloud}% cloud, so look up as well as ahead. Stick to lit routes.",
        ["phone torch", "water", "reflective layer"],
    ),
    "cool_shade": (
        "Go Late, Stay Shady",
        "It's a warm one ({feels}°C feels-like). {go_at} is your coolest free slot, so keep to the shade and carry water.",
        ["lots of water", "cap", "light cotton layer"],
    ),
    "wander": (
        "The Aimless Twenty",
        "{go_at} to {until} is free and conditions are {verdict}: {feels}°C, {rain}% rain chance, air {aqi_word}.",
        ["water", "comfortable shoes"],
    ),
    "doorstep": (
        "The Doorstep Reset",
        "No good free window in the next day, and right now scores {score}/100 ({feels}°C feels-like, AQI {aqi}). "
        "Smallest dose instead: five minutes at an open door or window.",
        [],
    ),
}

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "pitch": {"type": "string"},
        "rule": {"type": "string"},
        "bring": {"type": "array", "items": {"type": "string"}},
        "sign_off": {"type": "string"},
    },
    "required": ["title", "pitch", "rule", "bring", "sign_off"],
}

_CAPS = {"title": 60, "pitch": 280, "rule": 220, "sign_off": 70}


@dataclass
class Quest:
    title: str
    pitch: str
    rule: str
    bring: list[str]
    sign_off: str
    source: str  # model name, or "rules"


def fmt_t(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def day_label(dt: datetime, now: datetime) -> str:
    delta = (dt.date() - now.date()).days
    return "today" if delta == 0 else "tomorrow" if delta == 1 else dt.strftime("%A")


def choose_kind(window: Window, doorstep: bool) -> str:
    h = window.hour
    if doorstep:
        return "doorstep"
    if "golden hour" in window.tags:
        return "golden_hour"
    if "sunrise" in window.tags:
        return "sunrise"
    if "after dark" in window.tags:
        return "night_walk"
    if (h.code in (51, 53, 55, 61, 80) or h.rain >= 40) and h.code < 95:
        return "petrichor"
    if h.feels >= 31:
        return "cool_shade"
    return "wander"


def pick_rule(kind: str, today: date) -> str:
    pool = DOORSTEP_RULES if kind == "doorstep" else RULES
    return pool[(today.toordinal() + sum(map(ord, kind))) % len(pool)]


def build_facts(cfg, fc, now: datetime, window: Window, kind: str, busy_count: int, streak: int) -> dict:
    h = window.hour
    sun = fc.sun.get(window.start.date()) or next(iter(fc.sun.values()))
    return {
        "place": cfg.place,
        "now": fmt_t(now),
        "quest_kind": kind,
        "quest_goal": KINDS[kind],
        "go_day": day_label(window.start, now),
        "go_at": fmt_t(window.start),
        "until": fmt_t(window.end),
        "starts_in_minutes": max(0, int((window.start - now).total_seconds() // 60)),
        "duration_minutes": int((window.end - window.start).total_seconds() // 60),
        "window_notes": window.tags,
        "grass_score": window.score,
        "verdict": verdict(window.score),
        "feels_like_c": round(h.feels),
        "rain_chance_pct": round(h.rain),
        "wind_kmh": round(h.wind),
        "uv_index": round(h.uv),
        "cloud_pct": round(h.cloud),
        "air_quality_us_aqi": None if h.aqi is None else round(h.aqi),
        "air_quality": aqi_word(h.aqi),
        "sunrise": fmt_t(sun[0]),
        "sunset": fmt_t(sun[1]),
        "calendar": f"routed around {busy_count} busy slots" if busy_count else "no calendar loaded",
        "streak_days": streak,
        "rule": pick_rule(kind, now.date()),
    }


def allowed_numbers(facts: dict, window: Window) -> set[int]:
    nums = {int(n) for n in re.findall(r"\d+", json.dumps(facts))}
    for t in (window.start, window.end):  # 24h and 12h clock forms are both fair game
        nums |= {t.hour, t.hour % 12 or 12, t.minute}
    return nums


def validate(data: dict, allowed: set[int]) -> list[str]:
    errs: list[str] = []
    texts: list[str] = []
    for key, cap in _CAPS.items():
        v = data.get(key)
        if not isinstance(v, str) or not v.strip():
            errs.append(f"'{key}' missing")
        elif len(v) > cap:
            errs.append(f"'{key}' too long")
        else:
            texts.append(v)
    bring = data.get("bring")
    if not isinstance(bring, list) or len(bring) > 3 or not all(isinstance(b, str) and len(b) <= 30 for b in bring):
        errs.append("'bring' must be up to 3 short strings")
    else:
        texts += bring
    for text in texts:
        for m in re.findall(r"\d+(?:\.\d+)?", text):
            f = float(m)
            if int(f) not in allowed and round(f) not in allowed:
                errs.append(f"number {m} is not in the facts")
    return errs


def system_prompt(voice: str) -> str:
    v = VOICES[voice]["style"]
    return (
        "You are Grass Coach, a tiny agent whose only job is to get someone off their screen and outside. "
        f"Speak as {v}. Use ONLY the facts you are given: never invent numbers, places, animals or weather. "
        "Be short, specific and a little fun. Reply with JSON only."
    )


def user_prompt(facts: dict, problems: list[str] | None = None) -> str:
    text = (
        f"FACTS:\n{json.dumps(facts, indent=1)}\n\n"
        "Write a side-quest card:\n"
        "- title: max 6 words, playful\n"
        "- pitch: 1-2 sentences on why this window is good; mention at most 2 facts\n"
        "- rule: restate the quest rule in your voice, same meaning, 1 sentence\n"
        "- bring: up to 3 short items suited to the weather\n"
        "- sign_off: max 8 words"
    )
    if problems:
        text += f"\n\nYour previous answer was rejected: {'; '.join(problems)}. Fix it using only the facts."
    return text


def fallback_quest(facts: dict, voice: str, kind: str) -> Quest:
    title, pitch, bring = FALLBACK[kind]
    ctx = {
        "go_at": facts["go_at"],
        "until": facts["until"],
        "sunset": facts["sunset"],
        "sunrise": facts["sunrise"],
        "feels": facts["feels_like_c"],
        "rain": facts["rain_chance_pct"],
        "cloud": facts["cloud_pct"],
        "aqi": facts["air_quality_us_aqi"] if facts["air_quality_us_aqi"] is not None else "unknown",
        "aqi_word": facts["air_quality"],
        "verdict": facts["verdict"],
        "score": facts["grass_score"],
    }
    v = VOICES[voice]
    return Quest(title, f"{v['open']} {pitch.format(**ctx)}", facts["rule"], list(bring), v["close"], "rules")


def generate(cfg, facts: dict, window: Window, kind: str, allow_fallback: bool = True) -> tuple[Quest, str | None]:
    """Return (quest, note). `note` explains why we fell back, when we did."""
    reason = "LLM disabled (--no-llm)"
    if cfg.use_llm:
        allowed = allowed_numbers(facts, window)
        problems: list[str] | None = None
        for _ in range(2):
            try:
                data = chat_json(cfg, system_prompt(cfg.voice), user_prompt(facts, problems), SCHEMA)
            except LLMUnreachable as e:
                reason = str(e)
                break
            except LLMError as e:
                reason = str(e)
                problems = [reason]
                continue
            problems = validate(data, allowed)
            if not problems:
                return Quest(
                    data["title"].strip(), data["pitch"].strip(), data["rule"].strip(),
                    [b.strip() for b in data["bring"]], data["sign_off"].strip(), cfg.model,
                ), None
            reason = "model output rejected: " + "; ".join(problems)
    if not allow_fallback:
        raise LLMError(reason)
    return fallback_quest(facts, cfg.voice, kind), f"rule-based mode ({reason})"
