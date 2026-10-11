# Problem 4: With and without cached tokens

I ran the Problem 3 agent (no defenses) on all 12 practice documents in each setup. Every model call
is saved in `output/cache_test.json` (2 calls per document, 24 per setup). Each call records the
setup, the document, every token count the API reports (input, cached, cache-write, output,
reasoning), and the dollars from `prices.json`. Script: `python scripts/experiments.py cache`.

> **Gateway check.** The course's Portkey gateway also has a *response* cache. It replays an
> identical request without calling the model, and copies the old token counts. My first attempt was
> partly served from that cache, so I discarded it. Every call in the final run sends
> `x-portkey-cache-force-refresh: true`, and each row in `cache_test.json` records
> `gateway_response_cache: "REFRESH"`. That means all 72 calls really reached gpt-6-luna.

## The setups and the proof they did what I intended

| Setup | How it is built | Proof from the API's token counts |
|---|---|---|
| **Without cache** | A fresh random nonce (`[request nonce <uuid>]`) goes at the very front of **every request**, so no two requests ever share a prefix. | **0 cached tokens on all 24 calls.** |
| **With cache** (main result) | prompt.md + handbook sit at the front of every request as the agent's instructions, with a cache breakpoint (`openai_cache_instructions`) and a fixed `prompt_cache_key`. | **All 24 calls report cached tokens** (10,438–10,923 per call). |
| With cache, *new documents* | Same as "with cache", plus a unique tag *after* the handbook, so each document looks new (the realistic daily case). | All 24 calls read about 10,420 cached tokens (the handbook prefix). The document part is written fresh (≈ 160 cache-write tokens per call). |

The "with cache" run re-read documents the agent had already seen in the last 30 minutes, so even
the document text came from cache (0 writes). That is a best case. A real vendor desk gets new
documents every day, so I use the **new documents** setup for the projection.

Two things I learned while building the without-cache setup:

- The documented switch `prompt_cache_options = {"mode": "explicit"}` (with no breakpoints) is
  supposed to stop automatic caching. Through our gateway it was **ignored**: in a probe, the second
  identical request still read 10,074 cached tokens.
- A nonce **once per document** is not enough. The agent's second call (after `read_document`)
  repeats the first call's prefix, so it would hit the cache. The nonce has to change **per
  request**. I did this with a dynamic instruction, which PydanticAI re-runs before every model request.

## Results (12 documents each)

| | Without cache | With cache | With cache, new documents |
|---|---|---|---|
| Input tokens | 257,656 | 257,095 | 257,371 |
| — cached reads ($0.01/1M) | **0** | 254,071 | 250,449 |
| — cache writes ($0.125/1M) | 254,632 | 0 | 3,898 |
| — plain input ($0.10/1M) | 3,024 | 3,024 | 3,024 |
| Output tokens (incl. reasoning) | 2,270 (949) | 2,099 (719) | 2,161 (844) |
| **Total cost** | **$0.033266** | **$0.003893** | **$0.004375** |
| **Cost per document** | **$0.002772** | **$0.000324** | **$0.000365** |
| **Percent saved vs. without cache** | | **88.3%** | **86.8%** |

Where the money goes:

| Bucket | Without cache | With cache | With cache, new documents |
|---|---|---|---|
| Cache writes | **95.7%** | 0% | 11.1% |
| Cached reads | 0% | 65.3% | 57.3% |
| Output tokens | 3.4% | 27.0% | 24.7% |
| Plain input | 0.9% | 7.8% | 6.9% |

Per document (input / cached / cache-write / output tokens):

| Document | Without cache | $ | With cache | $ | With cache, new docs | $ |
|---|---|---|---|---|---|---|
| p01_bluehen_quote.html | 21,630 / 0 / 21,378 / 224 | $0.002809 | 21,581 / 21,329 / 0 / 168 | $0.000322 | 21,603 / 20,869 / 482 / 133 | $0.000361 |
| p02_elmcity_quote.html | 21,641 / 0 / 21,389 / 356 | $0.002877 | 21,595 / 21,343 / 0 / 282 | $0.000380 | 21,621 / 20,872 / 497 / 242 | $0.000417 |
| p03_ivyprint_catalog.html | 21,635 / 0 / 21,383 / 186 | $0.002791 | 21,588 / 21,336 / 0 / 183 | $0.000330 | 21,612 / 20,871 / 489 / 172 | $0.000381 |
| p04_harborstitch_quote.html | 21,664 / 0 / 21,412 / 176 | $0.002790 | 21,616 / 21,364 / 0 / 182 | $0.000330 | 21,642 / 20,874 / 516 / 198 | $0.000397 |
| p05_maplemills_quote.pdf | 21,305 / 0 / 21,053 / 149 | $0.002731 | 21,258 / 21,006 / 0 / 152 | $0.000311 | 21,282 / 20,871 / 159 / 159 | $0.000333 |
| p06_qtextile_quote.pdf | 21,350 / 0 / 21,098 / 148 | $0.002736 | 21,302 / 21,050 / 0 / 147 | $0.000309 | 21,326 / 20,871 / 203 / 148 | $0.000333 |
| p07_longwharf_quote.pdf | 21,316 / 0 / 21,064 / 207 | $0.002762 | 21,277 / 21,025 / 0 / 178 | $0.000324 | 21,303 / 20,872 / 179 / 202 | $0.000357 |
| p08_chapelst_email.eml | 21,330 / 0 / 21,078 / 157 | $0.002738 | 21,284 / 21,032 / 0 / 169 | $0.000320 | 21,304 / 20,870 / 182 / 195 | $0.000354 |
| p09_westville_email.eml | 21,499 / 0 / 21,247 / 186 | $0.002774 | 21,451 / 21,199 / 0 / 161 | $0.000318 | 21,475 / 20,872 / 351 / 164 | $0.000360 |
| p10_eastrock_email.eml | 21,352 / 0 / 21,100 / 162 | $0.002744 | 21,303 / 21,051 / 0 / 152 | $0.000312 | 21,327 / 20,872 / 203 / 220 | $0.000369 |
| p11_yorkst_quote.html | 21,614 / 0 / 21,362 / 159 | $0.002775 | 21,565 / 21,313 / 0 / 161 | $0.000319 | 21,583 / 20,868 / 463 / 171 | $0.000377 |
| p12_bluehen_quote.pdf | 21,320 / 0 / 21,068 / 160 | $0.002739 | 21,275 / 21,023 / 0 / 164 | $0.000317 | 21,293 / 20,867 / 174 / 157 | $0.000334 |

**Cold start.** The very first time the agent ever ran (p01, empty cache), call 1 *wrote* 10,438
tokens ($0.00133). Call 2 already read them back, and the whole document cost $0.00156. After that,
the cache stays warm.

## Real numbers vs. my Problem 2 estimate

| | Problem 2 estimate (handbook only) | Measured (whole call) |
|---|---|---|
| Fixed prefix per call | 10,058 tokens | 10,420 cached tokens (handbook + prompt.md + tool definitions ≈ +360) |
| Cost per call, without cache | $0.0010058 | **$0.0013861** (+38%) |
| Cost per call, warm cache | $0.00010058 | handbook part 10,420 × $0.01/1M = **$0.000104** (+3.6%); whole call **$0.000182** |
| 1,000 calls, with cache | $0.1017 | about $0.18 per 1,000 calls (whole call) |
| Calls per document | (per call) | **2**, so the handbook goes out twice per document |

- **Token count: correct.** The API's cached prefix is my 10,058 handbook tokens plus about 360
  tokens of prompt and tool schemas.
- **Without cache: 38% too low.** The cause is surprise #1 below: the provider bills these tokens
  at the cache-write rate, not the plain input rate.
- **With cache: correct for the handbook.** The handbook really does cost about $0.0001 per call.
  But it is no longer most of the bill. Output tokens, the uncached request tail, and the document's
  cache writes now add up to about as much as the handbook.

## Projection: 1,000 documents a day for 30 days (30,000 documents)

| | Per document | Per day | **Per month** |
|---|---|---|---|
| Without cache | $0.002772 | $2.77 | **$83.17** |
| With cache (new documents, warm cache) | $0.000365 | $0.36 | **$10.94** |
| + one cold start per day ($0.0012 extra) | | | + $0.04 |
| **Savings** | | | **≈ $72 per month (86.8%)** |

At 1,000 documents a day, a document arrives about every 86 seconds, so the 30-minute cache TTL never
lapses. The worst case is traffic gaps over 30 minutes before every document, so each one pays the
cold-start price (≈ $0.00156). That comes to about **$47 per month**: still cheaper than no cache,
but most of the savings are gone.

## What surprised me, and why it happens

1. **"No cache" is more expensive than the price list suggests.** I expected uncached input at
   $0.10/1M. Instead, 95.7% of the no-cache bill is **cache writes at $0.125/1M**. The provider
   automatically writes every new prompt prefix to the cache and charges the 25% write premium. A
   prefix that is unique every time is written and never read, so the agent pays the premium on
   10,000+ tokens per call for nothing. This is why real no-cache cost is 38% above my estimate.
   **Cache writes cost more than plain input**: caching only saves money when the prefix is reused.
2. **You can't simply switch caching off.** The documented `mode: "explicit"` switch did nothing
   through the gateway. I had to change the prompt itself on every request to stop cache reuse.
3. **Even the first document saves money.** On the cold start, call 2 read the 10,438 tokens that
   call 1 had just written. An agent that makes several calls per document benefits from caching
   even on its first document.
4. **Output tokens become the expensive part.** Output is under 1% of tokens but about 25% of the
   cached bill, because output costs 5× plain input and 50× a cached read. Roughly 40% of output
   tokens are hidden reasoning tokens. The next savings would come from shorter answers and less
   reasoning, not from the handbook.
5. **A second hidden cache.** The gateway's *response* cache replayed my earlier answers along with
   their old token counts. Without forcing a refresh, an experiment can silently measure nothing.
   For a vendor desk that could also be a correctness problem: a re-sent but changed document should
   never get a stale answer.
6. **Not about cost: the undefended answers change from run to run.** Across these runs, the
   no-defense agent sometimes took the hidden "revised" values in p02 ($5.11), p07 (7 days), and
   p12 ($17.44), and sometimes didn't. Caching doesn't change what the model computes; this is
   ordinary randomness in whether the hidden text wins. It's a preview of Problem 5.
