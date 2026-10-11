from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from . import ledger, weather
from .config import Config, load_config
from .ics import busy_from_ics
from .quest import VOICES, build_facts, choose_kind, generate
from .render import render_card
from .score import score_at
from .window import Window, best_windows

DEMO_DIR = Path(__file__).parent / "demo"
DEMO_NOW = datetime(2026, 10, 10, 15, 40)


@dataclass
class Plan:
    cfg: Config
    fc: weather.Forecast
    now: datetime
    window: Window
    alternatives: list[Window]
    kind: str
    facts: dict
    doorstep: bool
    streak: int
    demo: bool = False


def make_plan(cfg: Config, demo: bool = False, now_override: str | None = None) -> Plan:
    if demo:
        fc = weather.parse(json.loads((DEMO_DIR / "nagpur.json").read_text()))
        now = DEMO_NOW
        cfg = replace(cfg, place="Nagpur", ics=str(DEMO_DIR / "busy.ics"))
    else:
        cache = Path(cfg.data_dir) / "cache" / f"forecast_{cfg.lat:.2f}_{cfg.lon:.2f}.json"
        fc = weather.load(cfg.lat, cfg.lon, cache, cfg.offline)
        now = fc.now_local()
    if now_override:
        now = datetime.fromisoformat(now_override)

    busy = busy_from_ics(cfg.ics, fc.utc_offset) if cfg.ics else []
    wins = best_windows(fc, now, cfg.duration, busy)
    doorstep = not wins or wins[0].score < 25
    if doorstep:
        hour = fc.at(now) or min(fc.hours.values(), key=lambda h: abs(h.t - now))
        s = score_at(fc, now)
        window = Window(now, now + timedelta(minutes=5), int(s[0]) if s else 0, hour)
        alts = wins[:2]
    else:
        window, alts = wins[0], wins[1:]

    streak = 0 if demo else ledger.stats(ledger.entries(cfg.data_dir), now.date())["streak"]
    kind = choose_kind(window, doorstep)
    facts = build_facts(cfg, fc, now, window, kind, len(busy), streak)
    return Plan(cfg, fc, now, window, alts, kind, facts, doorstep, streak, demo)


# ---- commands -------------------------------------------------------------


def cmd_now(cfg: Config, args) -> int:
    plan = make_plan(cfg, getattr(args, "demo", False), getattr(args, "now", None))
    quest, note = generate(plan.cfg, plan.facts, plan.window, plan.kind)
    if getattr(args, "json", False):
        print(json.dumps({"facts": plan.facts, "quest": quest.__dict__, "note": note}, indent=2, ensure_ascii=False))
    else:
        print(render_card(plan, quest, note))
    return 0


def cmd_compare(cfg: Config, args) -> int:
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    plan = make_plan(cfg, getattr(args, "demo", False), getattr(args, "now", None))
    print(f"Same facts, {len(models)} open models. Voice: {cfg.voice}. Window: {plan.facts['go_at']} ({plan.kind})\n")
    for m in models:
        mcfg = replace(plan.cfg, model=m, use_llm=True)
        t0 = time.time()
        try:
            q, _ = generate(mcfg, plan.facts, plan.window, plan.kind, allow_fallback=False)
            print(f"── {m}  ({time.time() - t0:.1f}s)\n   {q.title}\n   {q.pitch}\n   RULE: {q.rule}\n   — {q.sign_off}\n")
        except Exception as e:  # keep comparing even if one model is missing
            print(f"── {m}  FAILED: {e}\n")
    return 0


def cmd_done(cfg: Config, args) -> int:
    note = " ".join(args.note).strip() or "touched grass"
    minutes = args.minutes if args.minutes is not None else cfg.duration
    ledger.add(cfg.data_dir, note, minutes)
    s = ledger.stats(ledger.entries(cfg.data_dir), date.today())
    print(f"🌱 Logged: {note} ({minutes} min). Streak: {s['streak']} day(s). Level: {s['level']}.")
    return 0


def cmd_stats(cfg: Config, args) -> int:
    items = ledger.entries(cfg.data_dir)
    s = ledger.stats(items, date.today())
    print(f"🌳 Level: {s['level']}")
    print(f"   {s['outings']} outings · {s['minutes']} minutes outside")
    print(f"   Streak: {s['streak']} day(s) (best {s['best_streak']})")
    if s["next_level"]:
        print(f"   {s['next_level'][0]} more minutes to {s['next_level'][1]}")
    for e in items[-5:]:
        print(f"   · {e['date']}  {e['minutes']:>3} min  {e['note']}")
    return 0


def cmd_voices(cfg: Config, args) -> int:
    for name, v in VOICES.items():
        print(f"{name:<8} {v['style']}")
    return 0


# ---- argument parsing -----------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    S = argparse.SUPPRESS
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=S, help="path to a grass.toml")
    common.add_argument("--lat", type=float, default=S)
    common.add_argument("--lon", type=float, default=S)
    common.add_argument("--place", default=S, help="display name for your location")
    common.add_argument("--model", default=S, help="any model your local server has (default gemma3:4b)")
    common.add_argument("--backend", choices=["ollama", "openai"], default=S)
    common.add_argument("--endpoint", default=S, help="model server URL (default http://localhost:11434)")
    common.add_argument("--voice", choices=sorted(VOICES), default=S)
    common.add_argument("--duration", type=int, default=S, help="minutes outside (default 30)")
    common.add_argument("--ics", default=S, help="local .ics calendar export to route around")
    common.add_argument("--no-llm", action="store_true", default=S, help="rule-based mode, no model")
    common.add_argument("--offline", action="store_true", default=S, help="use the cached forecast only")
    common.add_argument("--demo", action="store_true", default=S, help="bundled demo forecast + calendar, no internet needed")
    common.add_argument("--now", default=S, help="pretend it's this local time (ISO), for testing")
    common.add_argument("--json", action="store_true", default=S, help="machine-readable output")

    p = argparse.ArgumentParser(
        prog="grass", parents=[common],
        description="Grass Coach: a local open-weight agent that tells you when and why to go outside.",
    )
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("now", parents=[common], help="get your quest (default)")
    d = sub.add_parser("done", parents=[common], help="log an outing")
    d.add_argument("note", nargs="*")
    d.add_argument("-m", "--minutes", type=int)
    sub.add_parser("stats", parents=[common], help="streak, level, recent outings")
    c = sub.add_parser("compare", parents=[common], help="same facts through several local models")
    c.add_argument("--models", required=True, help="comma-separated, e.g. gemma3:4b,qwen3:4b,llama3.2:3b")
    sub.add_parser("voices", parents=[common], help="list voices")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    overrides = {k: getattr(args, k) for k in ("lat", "lon", "place", "model", "backend", "endpoint", "voice", "duration", "ics", "offline") if hasattr(args, k)}
    if hasattr(args, "no_llm"):
        overrides["use_llm"] = False
    cfg = load_config(getattr(args, "config", None), **overrides)
    cmd = args.cmd or "now"
    try:
        return {"now": cmd_now, "done": cmd_done, "stats": cmd_stats, "compare": cmd_compare, "voices": cmd_voices}[cmd](cfg, args)
    except weather.NoForecast as e:
        print(f"grass: {e}")
        return 2
