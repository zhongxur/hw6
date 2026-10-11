# Problem 2 — Sizing up the handbook

## Token count: **10,058 tokens**

`data/shop_handbook.md` is 28,903 characters and 6,127 words. It's mostly the 160-row product
catalogue (section 9) and the 40-row purchase order table (section 10).

I counted it two ways ([scripts/count_tokens.py](../scripts/count_tokens.py), raw numbers in
`output/handbook_token_count.json`):

| Method | Tokens |
|---|---|
| Local tokenizer: `tiktoken` `o200k_base` encoding (the GPT-4o / GPT-5 family encoding) | 10,058 |
| What the API actually bills: `gpt-6-luna` input tokens for *handbook + "Say OK."* (10,067) minus *"Say OK."* alone (9) | 10,058 |

Both methods give the same number, so the estimate below uses **10,058 tokens**.

## Prices (`data/prices.json`, gpt-6-luna, per 1M tokens)

| Plain input | Cached input (read) | Cache write | Output |
|---|---|---|---|
| $0.10 | $0.01 | $0.125 | $0.50 |

## What the handbook alone costs

**Without cached tokens** (every call pays the plain input rate):

- One call: 10,058 × $0.10 / 1,000,000 = **$0.0010058** (about a tenth of a cent)
- 1,000 calls: 1,000 × $0.0010058 = **$1.0058**

**With cached tokens** (the handbook is read from cache at $0.01/1M):

- One call, once the cache is warm: 10,058 × $0.01 / 1,000,000 = **$0.00010058**
- 1,000 calls: the first call has to *write* the cache, and the other 999 read it:
  - first call (cache write): 10,058 × $0.125 / 1,000,000 = $0.00125725
  - 999 cached calls: 999 × $0.00010058 = $0.10047942
  - **total ≈ $0.1017**, which is **about 90% cheaper** than $1.0058

Notes:

- A cache write costs 25% *more* than plain input ($0.125 vs $0.10). Caching only pays off if the
  prefix is reused at least once before it expires.
- The handbook goes out on **every model call**, not once per document. My agent makes 2 calls per
  document: one to ask for `read_document`, and one to answer after reading it. So the handbook's
  cost per *document* is about 2× the per-call numbers above:
  - without cache: about $0.0020 per document, or $2.01 per 1,000 documents
  - with cache: about $0.0002 per document, or $0.20 per 1,000 documents
- These numbers cover the handbook only. My prompt, the tool definitions, the document text, and the
  output tokens (5× the input price) come on top of this. Problem 4 measures the full bill.
