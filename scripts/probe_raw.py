"""Probe the raw Responses API usage block for cache settings (no pydantic-ai in the way)."""
import os, json, uuid
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
ROOT = Path(__file__).resolve().parent.parent
for d in (ROOT, *list(ROOT.parents)[:3]): load_dotenv(d / ".env")
key = os.environ["PORTKEY_API_KEY"]
c = OpenAI(base_url="https://api.portkey.ai/v1", api_key=key, default_headers={"x-portkey-api-key": key})
hb = (ROOT / "data/shop_handbook.md").read_text()
tag = uuid.uuid4().hex[:8]
def run(label, opts, nonce=""):
    r = c.responses.create(model="gpt-6-luna", input=[{"role": "user", "content": [{"type": "input_text", "text": nonce + hb}, {"type": "input_text", "text": "Reply with OK only."}]}],
                           **({"prompt_cache_options": opts} if opts else {}), max_output_tokens=200, reasoning={"effort": "none"} )
    print(label, json.dumps(r.usage.model_dump()))
run("explicit_nobp_A", {"mode": "explicit"}, f"[{tag}A] ")
run("explicit_nobp_A_again", {"mode": "explicit"}, f"[{tag}A] ")
run("implicit_B", None, f"[{tag}B] ")
run("implicit_B_again", None, f"[{tag}B] ")
