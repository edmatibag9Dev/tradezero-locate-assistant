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
import re
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
         "sellbacks": 0, "sellback_shares": 0, "sellback_failed": 0,
         "canceled": 0, "from_platform": 0}
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

        if r.get("source") == "platform":
            t["from_platform"] += 1
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
        elif res == "CANCELED":
            t["canceled"] += 1

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
           today: dt.date | None = None,
           extra_rows: list[dict] | None = None) -> dict:
    """extra_rows: account rows (today's platform history + saved platform
    log). Only settled outcomes count; in-flight rows are dropped."""
    extra = [r for r in (extra_rows or [])
             if r.get("result") not in ("OFFERED", "PENDING")]
    rows = filter_rows(merge_rows(load_rows(path), extra), days, mode, today)
    out = build_report(rows)
    out.update({"days": days, "mode": mode})
    return out


# --- TradeZero account data (read-only API rows) ------------------------------
# The quote log only knows what this app did. Locates taken in ZeroPro (or any
# other front end) live on the account, so two account sources fill the gap:
#   - GET /locates/history  → today's locate rows, account-wide (all statuses)
#   - GET /cash-transactions → posted locate fees/credits and borrow charges

# TradeZero locateStatus → the quote-log result vocabulary (plus 3 platform-only
# states that never appear in the app's own log).
PLATFORM_RESULT = {50: "ACCEPTED", 52: "CANCELED", 56: "Rejected",
                   67: "EXPIRED_UNANSWERED", 65: "OFFERED", 54: "PENDING",
                   81: "PENDING", 48: "PENDING"}


def _local_ts(iso: str) -> str:
    """'2026-10-30T15:41:02.123Z' (UTC) → '2026-10-30T08:41:02-0700' (local)."""
    if not iso:
        return ""
    s = iso.strip().replace("Z", "+00:00")
    # Python 3.9's fromisoformat only takes 3- or 6-digit fractions; TradeZero
    # sends 2, 3 or 7. Normalise the fraction to exactly 6 digits.
    m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(.*)$", s)
    if m:
        frac = ((m.group(2) or "") + "000000")[:6]
        s = f"{m.group(1)}.{frac}{m.group(3)}"
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return iso
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def normalize_saved(rows: list[dict]) -> list[dict]:
    """Repair platform rows saved by v1.5.0–1.5.1 (raw UTC 'Z' timestamps,
    broker text that could carry the account ID) at read time."""
    out = []
    for r in rows:
        r = dict(r)
        ts = str(r.get("ts", ""))
        if ts.endswith("Z") or ts.endswith("+00:00"):
            r["ts"] = _local_ts(ts)
        if r.get("detail"):
            r["detail"] = scrub(str(r["detail"]), None)
        out.append(r)
    return out


def base_req_id(qid: str) -> str:
    """Reg SHO threshold names answer under '<id>.SU' — same request."""
    return qid[:-3] if qid.endswith(".SU") else qid


def scrub(text: str, account_id: str | None) -> str:
    """Drop the account ID from broker text ("…pending for account <id> and…")."""
    if account_id:
        text = text.replace(account_id, "…")
    return re.sub(r"\baccount \S+", "account …", text)


def platform_rows(history: list[dict], mode: str) -> list[dict]:
    """Map TradeZero /locates/history rows to quote-log-style rows.

    Filled rows with negative shares are sell-backs (credits). Rows still in
    flight (Offered/Pending/Quoting) are kept so the table shows them, but the
    report ignores them because no money has moved.
    """
    out = []
    for h in history:
        status = h.get("locateStatus")
        shares = int(h.get("locateShares") or h.get("filledShares") or 0)
        rate = h.get("locatePrice")
        rate = float(rate) if rate not in (None, "") and float(rate) > 0 else None
        if shares < 0 and status == 50:
            result = "SELLBACK_SENT"            # processed: credit issued
        elif shares < 0 and status == 56:
            result = "SELLBACK_FAILED"          # e.g. "16 Insufficient shares."
        elif shares < 0 and status == 52:
            result = "CANCELED"
        else:
            result = PLATFORM_RESULT.get(status, str(status))
        qty = abs(shares)
        row = {"symbol": (h.get("symbol") or "").upper(), "qty": qty,
               "rate": rate, "quoteReqID": h.get("quoteReqID", ""),
               "result": result, "ts": _local_ts(h.get("createdDate", "")),
               "mode": mode, "source": "platform"}
        if rate is not None and result != "SELLBACK_SENT":
            row["total"] = round(rate * qty, 2)
        if h.get("text"):
            row["detail"] = scrub(str(h["text"]).strip(), h.get("accountId"))
        out.append(row)
    return out


def merge_rows(log_rows: list[dict], extra: list[dict]) -> list[dict]:
    """Add account rows the app didn't log itself. The app's own row wins for
    any quoteReqID it already logged (it carries the rule outcome: AUTO_REJECT
    vs PASSED). Rows without a quoteReqID are always kept."""
    SELL = ("SELLBACK_SENT", "SELLBACK_FAILED")
    settled_sell = {base_req_id(r.get("quoteReqID", "")): r for r in extra
                    if r.get("quoteReqID") and r.get("result") in SELL + ("CANCELED",)
                    and r.get("source") == "platform"}
    merged, seen = [], set()
    for r in log_rows:
        qid = base_req_id(r.get("quoteReqID", ""))
        if qid and r.get("result") in SELL and qid in settled_sell:
            acct = settled_sell[qid]
            r = {**r, "result": acct["result"], "settled_by": "account"}
            if acct.get("detail"):
                r["detail"] = acct["detail"]
        if qid:
            seen.add(qid)
        merged.append(r)
    for r in extra:
        qid = base_req_id(r.get("quoteReqID", ""))
        if qid and qid in seen:
            continue
        if qid:
            seen.add(qid)
        merged.append(r)
    return merged


LOCATE_FEES = "Locate Fees"
BORROW = "Locate & Borrow Charge"


def cash_summary(cash_rows: list[dict]) -> dict:
    """Posted locate money from the account's cash ledger (real dollars).

    fees     = Locate Fees withdrawals (locates bought)
    credits  = Locate Fees deposits ("Locate credit…" — sell-backs refunded)
    borrow   = Locate & Borrow Charge withdrawals (overnight carry)
    net      = fees + borrow − credits
    """
    fees = credits = borrow = 0.0
    n_fee = n_credit = n_borrow = 0
    days = set()
    for r in cash_rows:
        kind = str(r.get("cashType", "")).strip()
        dep = float(r.get("deposit") or 0)
        wd = float(r.get("withdraw") or 0)
        if kind == LOCATE_FEES:
            fees += wd
            credits += dep
            n_fee += wd > 0
            n_credit += dep > 0
        elif kind == BORROW:
            borrow += wd - dep
            n_borrow += 1
        else:
            continue
        d = str(r.get("entryDate", ""))[:10]
        if d:
            days.add(d)
    return {"fees": round(fees, 2), "credits": round(credits, 2),
            "borrow": round(borrow, 2), "net": round(fees + borrow - credits, 2),
            "fee_entries": n_fee, "credit_entries": n_credit,
            "borrow_entries": n_borrow,
            "first_day": min(days) if days else None,
            "last_day": max(days) if days else None}


def window(days: int | None, today: dt.date | None = None) -> tuple[str, int]:
    """(start_date, number_of_days) for the cash ledger; 'all' = 365 days."""
    today = today or dt.date.today()
    n = 365 if days is None else max(1, min(days, 365))
    return (today - dt.timedelta(days=n - 1)).isoformat(), n
