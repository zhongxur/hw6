"""Paths, the gpt-6-luna model via Portkey, and dollar pricing from data/prices.json."""

from __future__ import annotations

import json
import os
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import httpx2 as httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
PROMPTS = ROOT / "prompts"
HANDBOOK_PATH = DATA / "shop_handbook.md"
PRICES_PATH = DATA / "prices.json"

# project folder first, then parents (the course keeps one shared ~/MBA/.env)
for _d in (ROOT, *list(ROOT.parents)[:3]):
    load_dotenv(_d / ".env")

MODEL_NAME = "gpt-6-luna"  # the only model allowed in this homework
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").strip()


# x-portkey-cache-status of each model response in the current run (a ContextVar so parallel runs
# don't mix their lists); agent.run_desk sets a fresh list per run
GATEWAY_CACHE_STATUS: ContextVar[list[str] | None] = ContextVar("gateway_cache_status", default=None)


async def _record_gateway_cache(response: httpx.Response) -> None:
    statuses = GATEWAY_CACHE_STATUS.get()
    if statuses is not None:
        statuses.append(response.headers.get("x-portkey-cache-status", "none"))


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Copy .env.example to .env and add your key.")
    return AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key=key,
        # the course gateway also has a RESPONSE cache that replays identical requests; force-refresh
        # makes every experiment call reach the model (the gateway status is logged per call)
        default_headers={"x-portkey-api-key": key, "x-portkey-cache-force-refresh": "true"},
        timeout=120,
        http_client=httpx.AsyncClient(timeout=120, event_hooks={"response": [_record_gateway_cache]}),
    )


def build_model() -> OpenAIResponsesModel:
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=_client()))


@lru_cache(maxsize=1)
def prices() -> dict:
    return json.loads(PRICES_PATH.read_text())[MODEL_NAME]


def cost_usd(input_tokens: int, cached_tokens: int, cache_write_tokens: int, output_tokens: int) -> dict:
    """Dollars per billing bucket.

    The API's input_tokens INCLUDES cached (read) and cache-write tokens, so the plain-rate input is
    input - cached - cache_write. Output tokens include reasoning tokens.
    """
    p = prices()
    uncached = max(input_tokens - cached_tokens - cache_write_tokens, 0)
    parts = {
        "uncached_input_usd": uncached * p["input_per_1m"] / 1e6,
        "cached_input_usd": cached_tokens * p["cached_input_per_1m"] / 1e6,
        "cache_write_usd": cache_write_tokens * p["cache_write_per_1m"] / 1e6,
        "output_usd": output_tokens * p["output_per_1m"] / 1e6,
    }
    parts["total_usd"] = sum(parts.values())
    return {k: round(v, 8) for k, v in parts.items()}


def append_json_list(path: Path, entries: list[dict] | dict) -> None:
    """Append to a JSON list file (created if missing). These logs are never wiped between runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() and path.read_text().strip() else []
    data.extend(entries if isinstance(entries, list) else [entries])
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
