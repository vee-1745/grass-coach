"""Generate the bundled demo forecast (a plausible post-monsoon Nagpur weekend).

Synthetic on purpose: it lets anyone try Grass Coach with zero internet.
Run: python scripts/make_demo_fixture.py
"""

import json
import math
from pathlib import Path

out = Path(__file__).resolve().parent.parent / "grass" / "demo" / "nagpur.json"
days = ["2026-10-10", "2026-10-11"]
time, temp, feels, rain, wind, uv, cloud, code, aqi = ([] for _ in range(9))

for day_i, day in enumerate(days):
    for h in range(24):
        time.append(f"{day}T{h:02d}:00")
        t = 22 + 7 * max(0, math.sin(math.pi * (h - 7) / 14)) - (1.5 if h < 6 or h > 22 else 0)
        temp.append(round(t - day_i * 0.8, 1))
        feels.append(round(t - day_i * 0.8 + 1.5, 1))
        rain.append(45 if 13 <= h <= 15 and day_i == 0 else (20 if day_i else 10))
        wind.append(8 + (h % 5))
        uv.append(round(max(0, 8 * math.sin(math.pi * (h - 6) / 12)) * (0.6 if day_i == 0 else 1), 1) if 6 <= h <= 18 else 0)
        cloud.append(60 if 12 <= h <= 16 else (25 if h < 20 else 10))
        code.append(80 if (day_i == 0 and h == 14) else (3 if 12 <= h <= 16 else (1 if 6 <= h <= 19 else 0)))
        aqi.append(85 if 10 <= h <= 15 else (58 if 16 <= h <= 19 else 70))

raw = {
    "fetched_at": "2026-10-10T10:00:00",
    "forecast": {
        "utc_offset_seconds": 19800,
        "hourly": {
            "time": time,
            "temperature_2m": temp,
            "apparent_temperature": feels,
            "precipitation_probability": rain,
            "wind_speed_10m": wind,
            "uv_index": uv,
            "cloud_cover": cloud,
            "weather_code": code,
        },
        "daily": {
            "time": days,
            "sunrise": ["2026-10-10T06:10", "2026-10-11T06:10"],
            "sunset": ["2026-10-10T17:43", "2026-10-11T17:42"],
        },
    },
    "air": {"hourly": {"time": time, "us_aqi": aqi}},
}
out.write_text(json.dumps(raw))
print("wrote", out)
