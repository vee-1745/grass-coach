"""The Grass Score: a plain, explainable 0-100 number. No LLM maths, ever.

Small models are bad at arithmetic and great at flavour, so the numbers are
computed here and the model only gets to talk about them.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .weather import Forecast, Hour

TEMP = [(-5, 0.0), (12, 1.0), (27, 1.0), (40, 0.0)]  # apparent temp, °C
AQI = [(0, 1.0), (50, 1.0), (100, 0.65), (150, 0.3), (200, 0.08), (300, 0.0)]
WIND = [(0, 1.0), (20, 1.0), (60, 0.0)]  # km/h
UV = [(0, 1.0), (5, 1.0), (11, 0.4)]


def interp(x: float, pts: list[tuple[float, float]]) -> float:
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def factors(h: Hour, at: datetime, sunrise: datetime, sunset: datetime) -> dict[str, float]:
    daylight = sunrise - timedelta(minutes=30) <= at <= sunset + timedelta(minutes=40)
    rain = 1 - 0.85 * h.rain / 100
    if h.code >= 95:  # thunderstorm: just no
        rain = min(rain, 0.05)
    return {
        "temp": interp(h.feels, TEMP),
        "rain": rain,
        "air": interp(h.aqi, AQI) if h.aqi is not None else 0.9,
        "wind": interp(h.wind, WIND),
        "uv": interp(h.uv, UV) if sunrise <= at <= sunset else 1.0,
        "light": 1.0 if daylight else 0.35,
    }


def score_at(fc: Forecast, at: datetime):
    """Return (score 0-100, factors, hour) or None when the forecast has no data for `at`."""
    h = fc.at(at)
    sun = fc.sun.get(at.date())
    if h is None or sun is None:
        return None
    f = factors(h, at, *sun)
    prod = 1.0
    for v in f.values():
        prod *= v
    return round(100 * prod, 1), f, h


def verdict(score: float) -> str:
    if score >= 75:
        return "prime"
    if score >= 55:
        return "good"
    if score >= 35:
        return "okay"
    if score >= 20:
        return "meh"
    return "stay in"


def aqi_word(aqi: float | None) -> str:
    if aqi is None:
        return "unknown"
    for limit, word in [(50, "good"), (100, "moderate"), (150, "unhealthy for sensitive groups"), (200, "unhealthy")]:
        if aqi <= limit:
            return word
    return "very unhealthy"
