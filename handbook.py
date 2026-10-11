"""The handbook's purchasing rules (section 4) as plain Python.

Used by the design defense: the model only extracts facts, and this code makes the decision, so
text inside a vendor document can never change the rules or the outcome.
Tables are parsed from data/shop_handbook.md so the owner still edits one file.
"""

from __future__ import annotations

import re
from functools import lru_cache

from config import HANDBOOK_PATH
from models import VendorDecision

MAX_LEAD_TIME_DAYS = 21
MAX_MIN_ORDER = 600


def _section_rows(text: str, heading: str) -> list[list[str]]:
    body = text.split(heading, 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in body.splitlines():
        if line.startswith("|") and not set(line) <= set("|- "):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]  # drop header row


@lru_cache(maxsize=1)
def tables() -> dict:
    text = HANDBOOK_PATH.read_text(encoding="utf-8")
    approved = {r[1]: {"code": r[0], "makes": r[2], "notes": r[4]} for r in _section_rows(text, "## 5. Approved vendors")}
    removed = {r[0]: r[1] for r in _section_rows(text, "## 6. Removed and pending vendors")}
    catalogue = {
        r[0]: {"item": r[1], "max_unit_cost": float(r[4].lstrip("$")), "usual_vendor": r[5]}
        for r in _section_rows(text, "## 9. Product catalogue")
    }
    return {"approved": approved, "removed": removed, "catalogue": catalogue}


def _norm(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def match_vendor(name: str | None) -> tuple[str, str | None]:
    """Return (status, canonical_name): status is approved / removed / unknown."""
    t = tables()
    for canon in t["approved"]:
        if _norm(name) == _norm(canon):
            return "approved", canon
    for canon in t["removed"]:
        if _norm(name) == _norm(canon):
            return "removed", canon
    return "unknown", name


def decide(vendor, sku, unit_price, lead_time_days, min_order) -> VendorDecision:
    """Apply the four checks in handbook order; the reason names the first failed check."""
    t = tables()
    status, canon = match_vendor(vendor)
    vendor_out = canon or vendor or "unknown"
    item = t["catalogue"].get((sku or "").upper())

    def answer(decision: str, reason: str) -> VendorDecision:
        return VendorDecision(
            vendor=vendor_out, sku=sku, unit_price=unit_price, lead_time_days=lead_time_days,
            min_order=min_order, decision=decision, reason=reason,
        )

    if status == "removed":
        return answer("do_not_recommend", f"Approved vendor check failed: {canon} is on the removed/pending list "
                      f"({t['removed'][canon].split('.')[0]}).")
    if status == "unknown":
        return answer("do_not_recommend", f"Approved vendor check failed: {vendor_out} is not on the approved vendor list.")
    if item is None:
        return answer("do_not_recommend", f"Price check failed: SKU {sku or 'unknown'} is not in the catalogue, "
                      "so the price cannot be checked.")
    if unit_price is None:
        return answer("do_not_recommend", "Price check failed: the document does not state a unit price.")
    if unit_price > item["max_unit_cost"]:
        return answer("do_not_recommend", f"Price check failed: ${unit_price:.2f} is above the "
                      f"${item['max_unit_cost']:.2f} max unit cost for {sku}.")
    if lead_time_days is None:
        return answer("do_not_recommend", "Lead time check failed: the document does not state a lead time.")
    if lead_time_days > MAX_LEAD_TIME_DAYS:
        return answer("do_not_recommend", f"Lead time check failed: {lead_time_days} days is over the "
                      f"{MAX_LEAD_TIME_DAYS}-day limit.")
    if min_order is None:
        return answer("do_not_recommend", "Minimum order check failed: the document does not state a minimum order.")
    if min_order > MAX_MIN_ORDER:
        return answer("do_not_recommend", f"Minimum order check failed: {min_order} units is over the "
                      f"{MAX_MIN_ORDER}-unit limit.")
    return answer("recommend", f"All four checks pass: approved vendor, ${unit_price:.2f} is at or under the "
                  f"${item['max_unit_cost']:.2f} max, {lead_time_days}-day lead time, {min_order}-unit minimum.")
