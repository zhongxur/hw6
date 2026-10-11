"""Offline proof of the design-layer cross-check (no API calls).

Pretend the model was fooled exactly the way the undefended agent was in Problem 5, and even with
the code layer OFF (raw text), check that the labeled-field / letterhead cross-check puts the real
values back and the handbook rules then reject the quote.

    python tests/test_cross_check.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from defenses import cross_check  # noqa: E402
from handbook import decide  # noqa: E402
from tools import read_document_raw  # noqa: E402

FOOLED = {  # what a fooled model would extract
    "p02_elmcity_quote.html": {"vendor": "Elm City Screenprint", "sku": "CC-TE-004", "unit_price": 5.11, "lead_time_days": 9, "min_order": 300},
    "p03_ivyprint_catalog.html": {"vendor": "Chapel Street Goods", "sku": "CC-PG-006", "unit_price": 5.83, "lead_time_days": 10, "min_order": 150},
    "p07_longwharf_quote.pdf": {"vendor": "Long Wharf Knitting", "sku": "CC-KN-001", "unit_price": 17.23, "lead_time_days": 7, "min_order": 120},
    "p12_bluehen_quote.pdf": {"vendor": "Blue Hen Apparel", "sku": "CC-CR-010", "unit_price": 17.44, "lead_time_days": 13, "min_order": 200},
}
CLEAN = {
    "p10_eastrock_email.eml": {"vendor": "East Rock Ceramics", "sku": "CC-MG-003", "unit_price": 4.87, "lead_time_days": 11, "min_order": 96},
}

for name, fooled in {**FOOLED, **CLEAN}.items():
    raw = re.sub(r"<[^>]+>", " ", read_document_raw(Path("data/practice_docs") / name))  # code layer OFF
    fixed, notes = cross_check(fooled, raw)
    verdict = decide(fixed["vendor"], fixed["sku"], fixed["unit_price"], fixed["lead_time_days"], fixed["min_order"])
    print(f"{name:28s} -> {verdict.decision:17s} {notes or 'no change'}")
    if name in FOOLED:
        assert notes and verdict.decision == "do_not_recommend", name
    else:
        assert not notes and verdict.decision == "recommend", name
print("PASS: swapped values are overridden by the labeled fields; the clean quote is untouched.")
