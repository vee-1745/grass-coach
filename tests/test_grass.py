import json
import sys
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grass import ledger, weather
from grass.cli import DEMO_DIR, DEMO_NOW, main, make_plan
from grass.config import Config
from grass.ics import busy_from_ics
from grass.quest import generate, validate, allowed_numbers
from grass.score import score_at
from grass.window import best_windows

FC = weather.parse(json.loads((DEMO_DIR / "nagpur.json").read_text()))
BUSY = busy_from_ics(DEMO_DIR / "busy.ics", FC.utc_offset)


class FakeOllama(BaseHTTPRequestHandler):
    """Pretends to be Ollama. `replies` is a list of message.content strings, served in order."""

    replies: list[str] = []
    seen: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append(body)
        content = type(self).replies.pop(0)
        out = json.dumps({"message": {"role": "assistant", "content": content}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def serve(replies):
    FakeOllama.replies = list(replies)
    FakeOllama.seen = []
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


class Scoring(unittest.TestCase):
    def test_evening_beats_hot_afternoon_and_night(self):
        evening = score_at(FC, datetime(2026, 10, 10, 17, 15))[0]
        afternoon = score_at(FC, datetime(2026, 10, 10, 14, 0))[0]
        night = score_at(FC, datetime(2026, 10, 10, 23, 0))[0]
        self.assertGreater(evening, afternoon)
        self.assertGreater(evening, night)

    def test_thunderstorm_is_a_hard_no(self):
        h = FC.hours[datetime(2026, 10, 10, 17)]
        h.code = 95
        try:
            self.assertLess(score_at(FC, datetime(2026, 10, 10, 17, 15))[0], 10)
        finally:
            h.code = 1


class Windows(unittest.TestCase):
    def test_respects_calendar_and_lead_time(self):
        wins = best_windows(FC, DEMO_NOW, 30, BUSY)
        self.assertTrue(wins)
        for w in wins:
            self.assertGreaterEqual(w.start, DEMO_NOW + timedelta(minutes=10))
            for b0, b1 in BUSY:
                self.assertTrue(w.end <= b0 or w.start >= b1, f"{w.start} overlaps {b0}-{b1}")

    def test_golden_hour_wins_the_demo_day(self):
        top = best_windows(FC, DEMO_NOW, 30, BUSY)[0]
        self.assertIn("golden hour", top.tags)

    def test_alternatives_are_spread_out(self):
        wins = best_windows(FC, DEMO_NOW, 30, BUSY, k=3)
        for a, b in zip(wins, wins[1:]):
            self.assertGreaterEqual(abs((b.start - a.start).total_seconds()), 90 * 60)

    def test_fully_booked_returns_nothing(self):
        wall = [(DEMO_NOW - timedelta(hours=1), DEMO_NOW + timedelta(hours=30))]
        self.assertEqual(best_windows(FC, DEMO_NOW, 30, wall), [])


class Calendar(unittest.TestCase):
    def test_parser_edge_cases(self):
        ics = (
            "BEGIN:VEVENT\nDTSTART:20261010T100000Z\nDTEND:20261010T110000Z\nEND:VEVENT\n"
            "BEGIN:VEVENT\nDTSTART;VALUE=DATE:20261010\nEND:VEVENT\n"
            "BEGIN:VEVENT\nTRANSP:TRANSPARENT\nDTSTART:20261010T120000\nDTEND:20261010T130000\nEND:VEVENT\n"
            "BEGIN:VEVENT\nSUMMARY:folded\n  line\nDTSTART;TZID=Asia/Kolkata:20261010T140000\nEND:VEVENT\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".ics", delete=False) as f:
            f.write(ics)
        busy = busy_from_ics(f.name, 19800)
        self.assertEqual(len(busy), 2)  # all-day + transparent skipped
        self.assertEqual(busy[0], (datetime(2026, 10, 10, 14), datetime(2026, 10, 10, 15)))  # no DTEND -> 1h
        self.assertEqual(busy[1][0], datetime(2026, 10, 10, 15, 30))  # 10:00Z -> 15:30 IST


class Ledger(unittest.TestCase):
    def test_streaks_and_levels(self):
        with tempfile.TemporaryDirectory() as d:
            for day in (7, 8, 9, 10):
                ledger.add(d, "walk", 20, datetime(2026, 10, day, 18, 0))
            ledger.add(d, "old", 30, datetime(2026, 10, 1, 18, 0))
            s = ledger.stats(ledger.entries(d), date(2026, 10, 10))
            self.assertEqual((s["streak"], s["best_streak"], s["outings"], s["minutes"]), (4, 4, 5, 110))
            self.assertEqual(s["level"], "Sprout")
            # streak survives until the end of the next day, then breaks
            self.assertEqual(ledger.stats(ledger.entries(d), date(2026, 10, 11))["streak"], 4)
            self.assertEqual(ledger.stats(ledger.entries(d), date(2026, 10, 12))["streak"], 0)

    def test_corrupt_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            ledger.add(d, "ok", 10)
            with open(Path(d) / "ledger.jsonl", "a") as f:
                f.write("{not json\n")
            self.assertEqual(len(ledger.entries(d)), 1)


GOOD = {"title": "Golden Hour Heist", "pitch": "Sun sets at 5:43 PM and it's 29°C. Perfect.",
        "rule": "Phone stays zipped away.", "bring": ["water"], "sign_off": "Go. Now."}


class LLMLayer(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan(Config(), demo=True)

    def run_with(self, replies):
        srv, url = serve(replies)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        cfg = Config(endpoint=url, model="gemma3:4b", timeout=5)
        return generate(cfg, self.plan.facts, self.plan.window, self.plan.kind)

    def test_happy_path_uses_the_model_and_sends_a_schema(self):
        q, note = self.run_with([json.dumps(GOOD)])
        self.assertEqual((q.source, note), ("gemma3:4b", None))
        sent = FakeOllama.seen[0]
        self.assertIn("properties", sent["format"])
        self.assertEqual(sent["model"], "gemma3:4b")

    def test_hallucinated_number_is_rejected_then_retry_succeeds(self):
        bad = dict(GOOD, pitch="It's a lovely 42°C out there.")
        q, note = self.run_with([json.dumps(bad), json.dumps(GOOD)])
        self.assertEqual(q.source, "gemma3:4b")
        self.assertIn("number 42", FakeOllama.seen[1]["messages"][1]["content"])

    def test_two_bad_answers_fall_back_to_rules(self):
        q, note = self.run_with(["not json at all", json.dumps(dict(GOOD, title=""))])
        self.assertEqual(q.source, "rules")
        self.assertIn("rule-based", note)

    def test_no_server_falls_back_without_retrying(self):
        cfg = Config(endpoint="http://127.0.0.1:9", timeout=2)
        q, note = generate(cfg, self.plan.facts, self.plan.window, self.plan.kind)
        self.assertEqual(q.source, "rules")
        self.assertIn("no model server", note)

    def test_validate_allows_clock_forms_from_facts(self):
        allowed = allowed_numbers(self.plan.facts, self.plan.window)
        ok = dict(GOOD, pitch="Leave at 17:00, back by 5:30.")
        self.assertEqual(validate(ok, allowed), [])


class EndToEnd(unittest.TestCase):
    def test_demo_cli_runs_offline(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--demo", "--no-llm", "--voice", "pirate"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("GRASS COACH", out)
        self.assertIn("Ahoy", out)
        self.assertIn("close the laptop", out)

    def test_no_usable_window_gives_a_doorstep_quest(self):
        # 23:30 on the last forecast day: nothing left in the horizon, so we still answer.
        plan = make_plan(Config(), demo=True, now_override="2026-10-11T23:30")
        self.assertTrue(plan.doorstep)
        self.assertEqual(plan.kind, "doorstep")
        self.assertIn("5 minutes", __import__("grass.render", fromlist=["x"]).render_card(
            plan, __import__("grass.quest", fromlist=["x"]).fallback_quest(plan.facts, "ranger", plan.kind), None))

    def test_offline_without_cache_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(weather.NoForecast):
                weather.load(1.0, 2.0, Path(d) / "x.json", offline=True)

    def test_cache_roundtrip_marks_stale(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text((DEMO_DIR / "nagpur.json").read_text())
            fc = weather.load(1.0, 2.0, p, offline=True)
            self.assertTrue(fc.stale)


if __name__ == "__main__":
    unittest.main()
