# 🌿 Grass Coach

A tiny agent that runs on a **local open-weight model** and has exactly one job: get you off the screen.

It reads the forecast, air quality, sunset time and your free calendar slots, finds the single best
window to go outside, and hands you a **side-quest card** with a little rule to play by.
You spend ~10 seconds on the screen. Then you leave.

```
🌿 GRASS COACH · Sat 10 Oct · Nagpur
──────────────────────────────────────────────────────────
  CHASE THE GOLDEN HOUR
  Ranger's orders: The sun sets at 5:43 PM, so 5:00 PM is
  when the light turns soft and everything looks like a
  film. It's 29°C and the air is moderate (AQI 58).

  WHEN   5:00 PM – 5:30 PM  (today, in 80 min)  🌇 golden hour
  SCORE  83/100 ████████░░ prime
  RULE   Photograph nothing. Memorise one thing and
         describe it to someone later.
  ...
Screen time for this card: ~10 seconds. Now close the laptop. 🚪
```

## Try it in 10 seconds (no internet, no model)

```bash
python -m grass --demo --no-llm          # bundled forecast + calendar, rule-based writer
python -m grass --demo --voice pirate --no-llm
```

Python 3.11+, standard library only.

## Run it for real

```bash
# 1. a local open-weight model (Gemma shown; any works)
ollama pull gemma3:4b

# 2. your location (and optionally a calendar export)
cp grass.example.toml grass.toml   # edit lat / lon / place / ics

# 3. go
python -m grass
python -m grass --voice sensei
python -m grass --duration 45
```

Back from your outing:

```bash
python -m grass done "walked around the lake, no headphones" -m 25
python -m grass stats               # streak + level (Seedling → Ancient Banyan)
```

Compare models on the *same facts*:

```bash
python -m grass compare --models gemma3:4b,qwen3:4b,llama3.2:3b
```

## How it works

| Piece | What | Open? |
|---|---|---|
| Weather, UV, sunrise/sunset, AQI | [Open-Meteo](https://open-meteo.com) (no key); last good forecast cached for no-signal use | open data |
| Grass Score (0-100) | plain code: apparent temp, rain, AQI, wind, UV, daylight | n/a |
| Best window | 15-minute slots, scored, routed around your `.ics`, +golden-hour/sunrise bonus | n/a |
| Quest writer | a local model (Ollama, or any OpenAI-compatible server such as `llama.cpp`) | open weights |
| Fallback writer | rule-based templates | n/a |

**Design rule: code owns the facts, the model owns the flavour.** Times, scores and the quest rule are
computed deterministically. The model gets them as JSON and writes a title, pitch, rewritten rule,
packing list and sign-off, via **schema-constrained output**. Every number it mentions is checked
against the facts it was given; a hallucinated "42°C" is rejected and retried once, and if the model
is missing or keeps failing, the rule-based writer answers instead. It always answers.

Voices: `ranger`, `sensei` (anime training arc), `grandma`, `pirate`, `deadpan`.

## Privacy

Your location goes to Open-Meteo for the forecast (and only when online). Your calendar is parsed locally
from a file and never sent anywhere. The model runs on your machine; no prompts leave it.
Use `--offline` to skip the network entirely and use the cached forecast.

## Limits (honest ones)

- Recurring calendar events are not expanded; export a fresh date range instead.
- The score is a heuristic I tuned by hand, not science.
- Window search covers the next 24 hours.
- Tested with a scripted fake Ollama server and bundled demo data; see `tests/`. Run `python -m unittest discover -s tests`.

## License

MIT
