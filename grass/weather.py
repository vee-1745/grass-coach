"""Open-Meteo weather + air quality (free, keyless, open data) with an offline cache.

Trail with no signal? The last good forecast is reused and flagged as stale.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

HOURLY = "temperature_2m,apparent_temperature,precipitation_probability,wind_speed_10m,uv_index,cloud_cover,weather_code"


class NoForecast(RuntimeError):
    pass


@dataclass
class Hour:
    t: datetime
    temp: float
    feels: float
    rain: float  # precipitation probability, %
    wind: float  # km/h
    uv: float
    cloud: float  # %
    code: int  # WMO weather code
    aqi: float | None  # US AQI


@dataclass
class Forecast:
    hours: dict[datetime, Hour]
    sun: dict[date, tuple[datetime, datetime]]
    utc_offset: int
    fetched_at: datetime  # naive UTC
    stale: bool = False

    def now_local(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=self.utc_offset)

    def at(self, t: datetime) -> Hour | None:
        return self.hours.get(t.replace(minute=0, second=0, microsecond=0))

    def age_minutes(self) -> int:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return max(0, int((now - self.fetched_at).total_seconds() // 60))


def _n(v, default):
    return default if v is None else v


def parse(raw: dict) -> Forecast:
    f = raw["forecast"]
    h = f["hourly"]
    aqi_by_time: dict[str, float | None] = {}
    if raw.get("air"):
        ah = raw["air"]["hourly"]
        aqi_by_time = dict(zip(ah["time"], ah["us_aqi"]))
    hours: dict[datetime, Hour] = {}
    for i, ts in enumerate(h["time"]):
        t = datetime.fromisoformat(ts)
        hours[t] = Hour(
            t=t,
            temp=_n(h["temperature_2m"][i], 20.0),
            feels=_n(h["apparent_temperature"][i], 20.0),
            rain=_n(h["precipitation_probability"][i], 0.0),
            wind=_n(h["wind_speed_10m"][i], 0.0),
            uv=_n(h["uv_index"][i], 0.0),
            cloud=_n(h["cloud_cover"][i], 0.0),
            code=int(_n(h["weather_code"][i], 0)),
            aqi=aqi_by_time.get(ts),
        )
    d = f["daily"]
    sun = {
        date.fromisoformat(day): (datetime.fromisoformat(sr), datetime.fromisoformat(ss))
        for day, sr, ss in zip(d["time"], d["sunrise"], d["sunset"])
    }
    fetched = datetime.fromisoformat(raw.get("fetched_at", "2000-01-01T00:00:00"))
    return Forecast(hours, sun, int(f.get("utc_offset_seconds", 0)), fetched)


def _get(url: str, params: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "grass-coach/0.1"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def download(lat: float, lon: float, timeout: int = 8) -> dict:
    base = {"latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2}
    forecast = _get(FORECAST_URL, {**base, "hourly": HOURLY, "daily": "sunrise,sunset"}, timeout)
    try:
        air = _get(AIR_URL, {**base, "hourly": "us_aqi"}, timeout)
    except (OSError, ValueError):
        air = None  # air quality is a bonus; never block on it
    return {
        "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"),
        "forecast": forecast,
        "air": air,
    }


def load(lat: float, lon: float, cache_path: str | Path, offline: bool = False) -> Forecast:
    cache = Path(cache_path)
    if not offline:
        try:
            raw = download(lat, lon)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(raw), encoding="utf-8")
            return parse(raw)
        except (OSError, ValueError, KeyError):
            pass  # no signal: fall through to the cache
    if cache.exists():
        fc = parse(json.loads(cache.read_text(encoding="utf-8")))
        fc.stale = True
        return fc
    raise NoForecast("No signal and no cached forecast yet. Run once with internet, or try --demo.")
