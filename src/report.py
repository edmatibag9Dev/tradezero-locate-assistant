"""Locate-cost report built from the append-only quote log (logs/quotes.jsonl).

Pure functions, stdlib only, no network: the report reads only what the app has
already logged, so it costs nothing to run and works offline. Used by the web
console (GET /api/report) and testable on its own (tests/test_report.py).

Definitions (all from the log's own fields; nothing is estimated):
- requests      every locate request outcome (all results except sell-backs)
- priced        requests where TradeZero returned a per-share rate
- spend         sum of `total` on ACCEPTED rows — real dollars paid for borrows
- avg_rate      spend / accepted shares (share-weighted $/share actually paid)
- rejected_value  sum of `total` on AUTO_REJECT rows — quote value the rule
                  declined (what accepting those quotes would have cost)
- sellbacks     SELLBACK_SENT rows and shares; the refund amount is NOT in the
                log (TradeZero's sell response carries no credit figure), so
                no credit dollars are reported
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

SELLBACK = {"SELLBACK_SENT", "SELLBACK_FAILED"}
BROKER_REJECTED = {"Rejected", "NO_QUOTE"}


def load_rows(path: Path) -> list[dict]:
    """Read the JSONL log; skip blank or malformed lines (log is append-only)."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _day(row: dict) -> str:
    return str(row.get("ts", ""))[:10]  # YYYY-MM-DD local date at log time


def filter_rows(rows: list[dict], days: int | None, mode: str,
                today: dt.date | None = None) -> list[dict]:
    """days=None → all time; days=1 → today only. mode: 'real' | 'mock' | 'all'.

    Rows logged before the `mode` field existed only appear under mode='all'.
    """
    today = today or dt.date.today()
    start = None if days is None else (today - dt.timedelta(days=days - 1)).isoformat()
    out = []
    for r in rows:
        if mode != "all" and r.get("mode") != mode:
            continue
        d = _day(r)
        if start is not None and (not d or d < start):
            continue
        out.append(r)
    return out


def build_report(rows: list[dict]) -> dict:
    """Aggregate already-filtered rows into totals + a per-symbol breakdown."""
    t = {"requests": 0, "priced": 0, "accepted": 0, "accepted_shares": 0,
         "spend": 0.0, "auto_rejected": 0, "rejected_value": 0.0, "passed": 0,
         "expired": 0, "broker_rejected": 0, "accept_failed": 0,
         "sellbacks": 0, "sellback_shares": 0, "sellback_failed": 0}
    syms: dict[str, dict] = {}

    for r in rows:
        res = r.get("result", "")
        sym = (r.get("symbol") or "?").upper()
        qty = int(r.get("qty") or 0)
        rate = r.get("rate")
        total = float(r.get("total") or 0)

        if res in SELLBACK:
            if res == "SELLBACK_SENT":
                t["sellbacks"] += 1
                t["sellback_shares"] += qty
            else:
                t["sellback_failed"] += 1
            continue

        s = syms.setdefault(sym, {"symbol": sym, "requests": 0, "accepted": 0,
                                  "shares": 0, "spend": 0.0, "min_rate": None,
                                  "max_rate": None, "last": ""})
        t["requests"] += 1
        s["requests"] += 1
        s["last"] = max(s["last"], str(r.get("ts", "")))
        if rate is not None:
            t["priced"] += 1
            rate = float(rate)
            s["min_rate"] = rate if s["min_rate"] is None else min(s["min_rate"], rate)
            s["max_rate"] = rate if s["max_rate"] is None else max(s["max_rate"], rate)

        if res == "ACCEPTED":
            t["accepted"] += 1
            t["accepted_shares"] += qty
            t["spend"] += total
            s["accepted"] += 1
            s["shares"] += qty
            s["spend"] += total
        elif res == "AUTO_REJECT":
            t["auto_rejected"] += 1
            t["rejected_value"] += total
        elif res == "PASSED":
            t["passed"] += 1
        elif res == "EXPIRED_UNANSWERED":
            t["expired"] += 1
        elif res in BROKER_REJECTED:
            t["broker_rejected"] += 1
        elif res == "ACCEPT_FAILED":
            t["accept_failed"] += 1

    t["spend"] = round(t["spend"], 2)
    t["rejected_value"] = round(t["rejected_value"], 2)
    t["avg_rate"] = (round(t["spend"] / t["accepted_shares"], 4)
                     if t["accepted_shares"] else None)
    t["accept_rate"] = (round(t["accepted"] / t["priced"], 3)
                        if t["priced"] else None)

    by_symbol = []
    for s in syms.values():
        s["spend"] = round(s["spend"], 2)
        s["avg_rate"] = round(s["spend"] / s["shares"], 4) if s["shares"] else None
        by_symbol.append(s)
    by_symbol.sort(key=lambda s: (-s["spend"], -s["requests"], s["symbol"]))

    days = sorted({_day(r) for r in rows if _day(r)})
    return {"totals": t, "by_symbol": by_symbol,
            "first_day": days[0] if days else None,
            "last_day": days[-1] if days else None}


def report(path: Path, days: int | None, mode: str,
           today: dt.date | None = None) -> dict:
    rows = filter_rows(load_rows(path), days, mode, today)
    out = build_report(rows)
    out.update({"days": days, "mode": mode})
    return out
