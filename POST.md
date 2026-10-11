---
title: Grass Coach: a local Gemma agent that gets you off the screen in 10 seconds
published: false
tags: devchallenge, hf26challenge
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 1: Touch Grass](https://dev.to/challenges/hacktoberfest-week1-2026-10-05)*

## What I Built

Grass Coach is a tiny agent whose only job is to make the screen the shortest part of your day.

Every apps-that-want-you-outside idea I've seen has the same flaw: it's another app that wants your attention. So I built the opposite. You run one command, spend about ten seconds reading one card, and leave. The card says:

- **When** to go (the best free window in the next 24 hours, scored from forecast, air quality, UV, wind, daylight, and routed around your calendar, with a bonus for golden hour and sunrise),
- **Why** that window (written by a local open-weight model, in the voice you pick: park ranger, anime training-arc sensei, worried grandma, pirate, or deadpan British naturalist),
- **A rule** to play by, which turns a walk into a side-quest ("No headphones. Name 3 distinct sounds before you turn back." / "Photograph nothing. Memorise one thing and describe it to someone later."),
- and a **Touch-Grass Ledger** (`grass done`, `grass stats`) with streaks and levels, from Seedling up to Ancient Banyan.

If the weather is bad or your calendar is a wall, it doesn't lie to you. It prescribes a five-minute "doorstep reset" at an open window instead of pretending a monsoon is a nice day.

It's for anyone who knows they should go outside and keeps not doing it. Me included.

## Demo

<!-- TODO: paste a short screen recording (terminal card, then you closing the laptop) or a GIF -->

Try it with no internet and no model:

```bash
git clone https://github.com/vee-1745/grass-coach.git
cd grass-coach
python -m grass --demo --no-llm
```

## Code

{% github vee-1745/grass-coach %}

Python 3.11+, standard library only. No pip install, no API key, no account.

## How I Built It

**Open pieces:** Gemma (via Ollama) as the default writer, [Open-Meteo](https://open-meteo.com) for open weather and air-quality data, and an OpenAI-compatible adapter so `llama.cpp`, LM Studio or vLLM work too. Swapping the model is one line in `grass.toml`.

The interesting part isn't the model, it's what I *don't* let the model do.

**1. Code owns the facts, the model owns the flavour.** Small models are bad at arithmetic and great at tone. So the Grass Score (0-100), the window times and the quest rule are all computed in plain Python. The model receives them as JSON and writes only a title, a pitch, a re-worded rule, a packing list and a sign-off.

**2. Schema-constrained output.** The request carries a JSON schema (Ollama's `format` field, or `response_format` on OpenAI-compatible servers), so even a 3-4B model returns the right shape.

**3. A number guard.** Every number the model writes is checked against the facts it was given. If Gemma says "it's a lovely 42°C", that's rejected, the model is told exactly why, and it gets one retry. This catches the failure small models actually have: confident, plausible, wrong numbers.

**4. It always answers.** If the model server isn't running, or the model fails twice, a rule-based writer produces the card. If there's no signal, the last good forecast is cached and reused, clearly labelled as stale. The tool never says "service unavailable"; that would be a silly thing to hear from something that's supposed to get you to a trail.

**5. Calendar stays on your machine.** A tiny `.ics` reader finds your busy slots locally. Nothing about your schedule is sent anywhere.

I also added `grass compare --models gemma3:4b,qwen3:4b,llama3.2:3b`, which runs the same facts through several local models side by side, which is only possible because the model is a config line rather than an API contract.

Tests: 18 unit tests including a fake Ollama server that serves scripted replies (good, hallucinated, malformed, unreachable) to prove the guard, retry and fallback behave.

## Why Does Open Innovation Matter?

- **It works where the grass is.** The trail with no signal is exactly where a closed API stops working. Local weights plus a cached forecast keep working there. <!-- TODO: only keep this line if you actually tested it offline -->
- **Your calendar and location stay yours.** An agent that knows when you're free and where you live is exactly the kind of data you don't want on someone else's server. With a local model, the prompt never leaves the laptop.
- **I could change how it behaves.** Swapping models, comparing them on identical input, and constraining the output with a schema are all things I did in an afternoon *because* the model is mine to run. I found out which model followed the number rules best by measuring it, not by reading a vendor's changelog.
- **It costs nothing to run.** No key, no quota, no bill. A tool whose goal is "do this every day" can't have a per-call cost.

## My Outing

<!-- TODO: THIS IS THE BONUS-POINTS SECTION. Fill in honestly after you go outside. Suggestions:
- What did the card say? (paste it)
- Where did you go, for how long, and did you follow the rule?
- What did the model get right or wrong? Did the number guard ever fire? (run with --json to see)
- Which model/voice did you end up liking?
- A photo from the outing (or deliberately none, if the rule said "photograph nothing") -->

## My Agent Session

<!-- Optional: save this build session with DevRelay and embed it with the agent_session tag, or link it. -->

## Prize Categories

- **Gemma**: runs Gemma locally by default (`gemma3:4b` through Ollama), with schema-constrained output and a verification layer around it.
<!-- Add "Entire" only if you embed/share the agent session. Remove any category you don't genuinely use. -->

<!-- Thanks for participating! -->
