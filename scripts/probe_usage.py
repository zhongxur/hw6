"""One-off probe: what usage fields does gpt-6-luna via Portkey return, and does caching work?"""
import asyncio, os, json, uuid
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, CachePoint
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

ROOT = Path(__file__).resolve().parent.parent
for d in (ROOT, *list(ROOT.parents)[:3]):
    load_dotenv(d / ".env")
key = os.environ["PORTKEY_API_KEY"]
client = AsyncOpenAI(base_url="https://api.portkey.ai/v1", api_key=key, default_headers={"x-portkey-api-key": key})
model = OpenAIResponsesModel("gpt-6-luna", provider=OpenAIProvider(openai_client=client))
hb = (ROOT / "data/shop_handbook.md").read_text()

async def main():
    agent = Agent(model)
    tag = uuid.uuid4().hex[:6]
    for label, prompt, settings in [
        ("tiny", ["Say OK."], None),
        ("hb_only_1", [hb, "Say OK."], None),
        ("explicit_cp_1", [hb, CachePoint(), f"Say OK. {tag}"], OpenAIResponsesModelSettings(openai_prompt_cache_key="hw6probe"+tag, openai_prompt_cache_options={"mode": "explicit"})),
        ("explicit_cp_2", [hb, CachePoint(), f"Say OK again. {tag}"], OpenAIResponsesModelSettings(openai_prompt_cache_key="hw6probe"+tag, openai_prompt_cache_options={"mode": "explicit"})),
        ("explicit_nocp_1", [hb, f"Say OK. x{tag}"], OpenAIResponsesModelSettings(openai_prompt_cache_options={"mode": "explicit"})),
        ("explicit_nocp_2", [hb, f"Say OK. y{tag}"], OpenAIResponsesModelSettings(openai_prompt_cache_options={"mode": "explicit"})),
    ]:
        r = await agent.run(prompt, model_settings=settings)
        u = r.usage
        print(label, json.dumps({"input": u.input_tokens, "cache_read": u.cache_read_tokens, "cache_write": u.cache_write_tokens, "output": u.output_tokens, "details": u.details}))
asyncio.run(main())
