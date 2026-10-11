"""Talk to a *local* open-weight model. Two wire formats cover almost everything:

- "ollama": Ollama's native /api/chat (schema-constrained output via `format`)
- "openai": any OpenAI-compatible server: llama.cpp `llama-server`, LM Studio, vLLM...

Swapping models is one config line. Nothing here ever leaves localhost unless you point it elsewhere.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

# Never route a local model call through a system proxy.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class LLMError(RuntimeError):
    """The model answered, but the answer was unusable."""


class LLMUnreachable(LLMError):
    """No model server / model not found. Retrying will not help."""


def chat_json(cfg, system: str, user: str, schema: dict) -> dict:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if cfg.backend == "openai":
        url = cfg.endpoint.rstrip("/") + "/v1/chat/completions"
        body = {
            "model": cfg.model,
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 400,
            "response_format": {"type": "json_schema", "json_schema": {"name": "quest", "schema": schema, "strict": True}},
        }
    else:
        url = cfg.endpoint.rstrip("/") + "/api/chat"
        body = {
            "model": cfg.model,
            "messages": messages,
            "stream": False,
            "think": False,  # skip reasoning traces; we want a 60-token card, not an essay
            "format": schema,
            "options": {"temperature": 0.8, "num_predict": 400},
        }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with _OPENER.open(req, timeout=cfg.timeout) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read()[:200].decode("utf-8", "replace")
        raise LLMUnreachable(f"model server said HTTP {e.code} for '{cfg.model}': {detail}") from e
    except (OSError, ValueError) as e:
        raise LLMUnreachable(f"no model server at {cfg.endpoint} ({type(e).__name__})") from e

    try:
        content = resp["choices"][0]["message"]["content"] if cfg.backend == "openai" else resp["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError("unexpected response shape from model server") from e
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
    try:
        data = json.loads(content)
    except ValueError as e:
        raise LLMError("model returned invalid JSON") from e
    if not isinstance(data, dict):
        raise LLMError("model returned JSON that is not an object")
    return data
