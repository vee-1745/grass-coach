---
title: Grass Coach: a local Gemma agent that gets you off the screen in 10 seconds
published: true
tags: devchallenge, hf26challenge
---
 
*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 1: Touch Grass](https://dev.to/challenges/hacktoberfest-week1-2026-10-05)*
 
## What I Built
 
Grass Coach is a tiny agent whose only job is to make the screen the shortest part of your day.
 
Most "go outside" apps have the same flaw: they're another app that wants your attention. So I built the opposite. You run one command, spend about ten seconds reading one card, and leave. The card tells you:
 
- **When** to go: the best free window in the next 24 hours, scored from forecast, air quality, UV, wind and daylight, routed around your calendar, with a bonus for golden hour and sunrise.
- **Why** that window: written by a local open-weight model, in a voice you pick (park ranger, anime training-arc sensei, worried grandma, pirate, or deadpan British naturalist).
- **A rule** to play by, which turns a walk into a side-quest: "Count flower colours; stop at 7." / "No headphones. Name 3 distinct sounds before you turn back." / "Photograph nothing. Memorise one thing and describe it to someone later."
- A **Touch-Grass Ledger** (`grass done`, `grass stats`) with streaks and levels, from Seedling up to Ancient Banyan.

If the weather is bad or your calendar is a wall, it doesn't pretend. It prescribes a five-minute "doorstep reset" at an open window instead.
 
It's for anyone who knows they should go outside and keeps not doing it. Me included.
 
## Demo

This is a real run on my laptop at 4:35 AM in Nagpur, Gemma 3 4B via Ollama, live Open-Meteo data:

```text
🌿 GRASS COACH · Mon 12 Oct · Nagpur
──────────────────────────────────────────────────────────
  CHASE THE DAWN IN NAGPUR!
  The sunrise is painting the sky with beautiful hues, and
  it's the perfect time to witness it before the day gets
  busy. We've got a lovely 30 minutes to enjoy!
 
  WHEN   6:00 AM – 6:30 AM  (today, in 89 min)  🌅 sunrise
  SCORE  67/100 ███████░░░ good
  SKY    27°C feels-like · rain 0% · UV 0 · wind 5 km/h
  AIR    AQI 105 (unhealthy for sensitive groups)
  RULE   Let's count seven different flower colors – a
         delightful little challenge!
  BRING  A light jacket, A water bottle, A small notebook
  ALSO   today 8:00 AM (52/100)
  ALSO   today 4:30 PM (29/100, golden hour)
 
  — Get out there and soak it up, friend!
──────────────────────────────────────────────────────────
Screen time for this card: ~10 seconds. Now close the laptop. 🚪
[model: gemma3:4b · forecast: live (Open-Meteo) · calendar: no calendar loaded]
```
 
Anyone can try it with no internet and no model:
 
```bash
git clone https://github.com/vee-1745/grass-coach
cd grass-coach
python -m grass --demo --no-llm
```
 
## Code
 
{% github vee-1745/grass-coach %}
 
Python 3.11+, standard library only. No pip install, no API key, no account.
 
## How I Built It
 
**Open pieces:** Gemma (via Ollama) as the default writer, [Open-Meteo](https://open-meteo.com) for open weather and air-quality data, and an OpenAI-compatible adapter so `llama.cpp`, LM Studio or vLLM work too. Swapping the model is one line in `grass.toml`.
 
The interesting part isn't the model. It's what I *don't* let the model do.
 
**1. Code owns the facts, the model owns the flavour.** Small models are bad at arithmetic and good at tone. So the Grass Score (0-100), the window times and the quest rule are all computed in plain Python. The model receives them as JSON and writes only a title, a pitch, a re-worded rule, a packing list and a sign-off. (You can see the exact facts it gets with `grass --json`.)
 
**2. Schema-constrained output.** The request carries a JSON schema (Ollama's `format` field, or `response_format` on OpenAI-compatible servers), so even a 4B model returns the right shape. Every live Gemma run I did returned a valid card.
 
**3. A number guard.** Every number the model writes is checked against the facts it was given. If the model says "it's a lovely 42°C", that's rejected, the model is told exactly why, and it gets one retry. This targets the failure small models actually have: confident, plausible, wrong numbers. It's covered by unit tests that script a fake Ollama server returning hallucinated numbers, malformed JSON and no response at all.
 
**4. It always answers.** If the model server isn't running or fails twice, a rule-based writer produces the card. If there's no signal, the last good forecast is cached and reused, labelled as stale. I tested those paths in unit tests; I haven't yet tried it on a trail with no signal.
 
**5. The calendar stays on your machine.** A tiny `.ics` reader finds your busy slots locally. Nothing about your schedule is sent anywhere.
 
There's also `grass compare --models gemma3:4b,qwen3:4b,llama3.2:3b`, which runs the same facts through several local models side by side. That only works because the model is a config line, not an API contract.
 
### What the first real run taught me
 
I wrote the code against a fake model server, so the real Gemma run was the actual test. It worked first time, and it also showed me where a 4B model is weak:
 
- **It ignored the voice.** My default voice is "park ranger", but Gemma wrote a generic cheerful "Get out there, friend!". Ironically, the dumb rule-based fallback ("Ranger's orders: ... Leave only footprints.") has more character than the model does.
- **It ignored common sense.** It told me to pack "a light jacket" (and on another run "a warm scarf") at 27°C. My number guard checks numbers, not sense. Next step: constrain the packing list by temperature.
- **It didn't mention the air.** AQI was 105 and the card shows it, but the model's pitch never says so. The score and data are honest; the prose isn't always.
- **The facts never wavered; the prose did.** Same inputs, three runs, three different texts. But the time, score and rule were identical every time, which is the whole point of the design.
- **One thing I'd fix:** the "ALSO" list happily showed a 29/100 option. It should hide weak alternatives.

## Why Does Open Innovation Matter?
 
- **It can work where the grass is.** A trail with no signal is exactly where a closed API stops. Local weights plus a cached forecast are designed to keep working there.
- **Your calendar and location stay yours.** An agent that knows when you're free and where you live is the kind of data you don't want on someone else's server. With a local model, the prompt never leaves the laptop.
- **I could change how it behaves.** Constraining output with a schema, adding a verification layer around the model, swapping models and comparing them on identical input are all things I could do in an afternoon because the model is mine to run.
- **It costs nothing to run.** No key, no quota, no bill. A tool meant to be used every day can't have a per-call cost.

## My Outing
 
The card above came out at 4:35 AM and pointed me at a 6:00 AM sunrise window.
 
I headed out into the cool Nagpur dawn around 6:00 AM for a 30-minute sunrise walk, bringing along a light jacket, my water bottle, and a small notebook to log what I found. I took the challenge seriously (I got to a nice morning walk anyways) and kept my eyes peeled, successfully spotting seven distinct flower colors: bright marigold orange, deep bougainvillea magenta, soft yellow, pure white, crimson red, lavender purple, and tiny wild blue petals nestled along a garden hedge. The AQI sitting at 105 gave the sky a slightly hazy quality, so I adjusted by keeping my pace relaxed and steady rather than turning it into a brisk workout. Stepping away from the laptop after just ten seconds of screen time was a complete breath of fresh air; swapping my usual morning routine (watching reels and youtube on laptop/tab) of mindless scrolling for real sunlight and quiet streets left me feeling remarkably calm, grounded, and present. And also, flowers helped me talk to my crush.

## Prize Categories

- **Gemma**: runs Gemma locally by default (`gemma3:4b` through Ollama), with schema-constrained output and a verification layer around it.

<!-- Thanks for participating! --> 