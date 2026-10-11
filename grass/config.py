from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path


@dataclass
class Config:
    # Where you are. Change these (or pass --lat/--lon/--place).
    lat: float = 21.1458
    lon: float = 79.0882
    place: str = "Nagpur"

    # The open-weight model. Any model your local server can serve works.
    model: str = "gemma3:4b"
    backend: str = "ollama"  # "ollama" or "openai" (llama.cpp server, LM Studio, vLLM...)
    endpoint: str = "http://localhost:11434"
    timeout: int = 90

    voice: str = "ranger"
    duration: int = 30  # minutes outside
    ics: str | None = None  # path to a local .ics calendar export
    data_dir: str = str(Path.home() / ".grass")
    use_llm: bool = True
    offline: bool = False  # never touch the network for weather; use the cache


_NAMES = {f.name for f in fields(Config)}


def load_config(explicit: str | None = None, **overrides) -> Config:
    cfg = Config()
    candidates = [Path(explicit)] if explicit else [Path("grass.toml"), Path(cfg.data_dir) / "grass.toml"]
    for p in candidates:
        if p.exists():
            data = tomllib.loads(p.read_text(encoding="utf-8"))
            cfg = replace(cfg, **{k: v for k, v in data.items() if k in _NAMES})
            break
    return replace(cfg, **{k: v for k, v in overrides.items() if v is not None and k in _NAMES})
