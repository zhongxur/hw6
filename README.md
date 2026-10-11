# HW6: Campus Customs Vendor Desk (Tokenomics + Prompt Injection)

A PydanticAI agent (gpt-6-luna via Portkey) that reads one vendor document (HTML, PDF, or `.eml`),
extracts vendor / SKU / unit price / lead time / minimum order, and recommends or rejects the quote
using the Campus Customs Shop Handbook. It caches the 10k-token handbook, and it is defended at the
code, design, and prompt layers against documents that hide instructions for the AI.

Results page: **`output/hw6_report.html`** (one self-contained file; open it by double-click).

## Run the agent

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env            # add your PORTKEY_API_KEY (a .env in a parent folder also works)

python agent.py --doc data/practice_docs/p01_bluehen_quote.html                 # final agent: all defenses, cached
python agent.py --doc data/practice_docs/p01_bluehen_quote.html --no-defenses   # the Problem 3 agent
python agent.py --doc data/exam_docs/e03_quote.html --defenses code,prompt      # any subset of code,design,prompt
python agent.py --doc data/practice_docs/p08_chapelst_email.eml --no-cache      # no prompt-cache reuse
```

Each run prints the answer, the token counts, and the cost, and appends to `output/usage_log.json`
and `output/audit_trail.json`. The trap tools (`send_email`, `approve_payment`) only write to
`output/trap_calls.json`, which is still `[]` after every run.

## Reproduce each problem

| Problem | Command | Output |
|---|---|---|
| 2 Handbook size | `python scripts/count_tokens.py` | `output/handbook_estimate.md`, `handbook_token_count.json` |
| 3 Agent | `python agent.py --doc ... --no-defenses` (p01, p08) | `output/harness.md`, `usage_log.json`, `audit_trail.json`, `p3_demo_runs.txt` |
| 4 Caching | `python scripts/experiments.py cache` | `output/cache_test.json`, `cache_test.md` |
| 5 Attacks | `python scripts/experiments.py attack` | `output/attack_results.json`, `attack_results.md`, `attack_screens/` |
| 6 Defenses | `python scripts/experiments.py defense` | `output/defense_results.json`, `defense_results.md`, Safety section in `harness.md` |
| 7 Red team | `python scripts/make_attacks.py` then `python scripts/experiments.py redteam` | `data/my_attacks/`, `output/red_team.md`, `red_team_results.json` |
| 8 Exam | `python scripts/experiments.py exam` | `output/exam_results.json` |
| 9 Report | `python scripts/build_report.py` | `output/hw6_report.html` |

Offline tests (no API cost): `python tests/test_trap_gate.py` (trap tools are held for human sign-off)
and `python tests/test_cross_check.py` (swapped numbers are overridden by the labeled fields).

## Layout

```
agent.py        entry point / CLI; run_desk() used by every experiment
tools.py        naive document reader + trap tools (log only)
models.py       VendorDecision, ExtractedQuote, DeskResult
defenses.py     code layer (clean_document) + design-layer checks (cross_check, scrub_output)
handbook.py     handbook section-4 rules in Python (tables parsed from data/shop_handbook.md)
config.py       gpt-6-luna via Portkey, prices, cost formula, append-only logs
prompts/prompt.md   agent instructions; its Safety section is the prompt-layer defense
scripts/        experiments, token count, attack builder, report builder, gateway/caching probes
tests/          offline proofs of the design layer
```

## Notes

- Only `gpt-6-luna` is used, everywhere.
- The course's Portkey gateway also has a **response** cache that replays identical requests. Every
  call sends `x-portkey-cache-force-refresh: true`, and logs the gateway status per call, so every
  experiment number comes from a real model call.
- `.env` is git-ignored; `.env.example` has placeholders only.
