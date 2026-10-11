"""Probe: is the Portkey gateway answering repeated identical requests from its own response cache?"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # loads .env
from openai import OpenAI
key = os.environ["PORTKEY_API_KEY"]
for extra in ({}, {"x-portkey-cache-force-refresh": "true"}):
    c = OpenAI(base_url=config.PORTKEY_BASE_URL, api_key=key, default_headers={"x-portkey-api-key": key, **extra})
    for i in range(2):
        r = c.responses.with_raw_response.create(model="gpt-6-luna", input="Pick a random integer between 1 and 1000000. Reply with the number only.")
        body = r.parse()
        print(extra or "default", i, {k: v for k, v in r.headers.items() if "cache" in k.lower() or k.lower().startswith("x-portkey")}, body.output_text, body.id)
