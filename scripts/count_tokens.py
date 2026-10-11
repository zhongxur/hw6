"""Problem 2: count the handbook's tokens two ways (local tokenizer + what the API bills)."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tiktoken  # noqa: E402
from pydantic_ai import Agent  # noqa: E402

from config import HANDBOOK_PATH, build_model, prices  # noqa: E402

text = HANDBOOK_PATH.read_text(encoding="utf-8")
local = len(tiktoken.get_encoding("o200k_base").encode(text))


async def api_count() -> tuple[int, int]:
    agent = Agent(build_model())
    base = (await agent.run("Say OK.")).usage.input_tokens  # framing + the tiny question
    full = (await agent.run([text, "Say OK."])).usage.input_tokens  # same + the handbook
    return base, full


base, full = asyncio.run(api_count())
out = {
    "characters": len(text),
    "words": len(text.split()),
    "tiktoken_o200k_base": local,
    "api_input_tokens_without_handbook": base,
    "api_input_tokens_with_handbook": full,
    "api_handbook_tokens": full - base,
    "prices_per_1m": prices(),
}
print(json.dumps(out, indent=2))
