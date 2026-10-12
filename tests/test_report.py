"""Tests for the locate-cost report (src/report.py). Stdlib only; no network.

Run: python3 tests/test_report.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import report  # noqa: E402

TODAY = dt.date(2026, 10, 12)
ROWS = [
    # old row without a mode field (pre-mode logs) — only counted under mode=all
    {"symbol": "EXPN", "qty": 500, "rate": 0.35, "total": 175.0,
     "result": "AUTO_REJECT", "ts": "2026-08-10T09:45:42-0700"},
    {"symbol": "I", "qty": 100, "rate": 0.154, "total": 15.4, "result": "PASSED",
     "ts": "2026-10-12T06:47:10-0700", "mode": "mock"},
    {"symbol": "MVIS", "qty": 100, "rate": 0.0045, "total": 0.45,
     "result": "EXPIRED_UNANSWERED", "ts": "2026-10-12T09:07:54-0700", "mode": "real"},
    {"symbol": "WFF", "qty": 100, "rate": 0.45, "total": 45.0, "result": "AUTO_REJECT",
     "ts": "2026-10-12T09:18:04-0700", "mode": "real"},
    {"symbol": "ELOG", "qty": 100, "rate": 0.009, "total": 0.9, "result": "PASSED",
     "ts": "2026-10-12T09:19:19-0700", "mode": "real"},
    {"symbol": "ELOG", "qty": 200, "rate": 0.012, "total": 2.4, "result": "ACCEPTED",
     "ts": "2026-10-12T09:25:00-0700", "mode": "real"},
    {"symbol": "ELOG", "qty": 100, "result": "SELLBACK_SENT",
     "ts": "2026-10-12T15:30:00-0700", "mode": "real"},
    {"symbol": "KOSS", "qty": 100, "result": "Rejected", "detail": "System error",
     "ts": "2026-10-06T11:04:30-0700", "mode": "real"},
    {"symbol": "ABCD", "qty": 300, "rate": 0.05, "total": 15.0, "result": "ACCEPTED",
     "ts": "2026-09-01T10:00:00-0700", "mode": "real"},
]

passed = failed = 0


def check(name: str, got, want) -> None:
    global passed, failed
    ok = got == want
    passed += ok
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r}" + ("" if ok else f", want {want!r}"))


def run() -> None:
    # today, real only
    r = report.build_report(report.filter_rows(ROWS, 1, "real", TODAY))
    t = r["totals"]
    check("today real: requests (sell-back excluded)", t["requests"], 4)
    check("today real: priced", t["priced"], 4)
    check("today real: accepted", t["accepted"], 1)
    check("today real: spend", t["spend"], 2.4)
    check("today real: avg paid/share", t["avg_rate"], 0.012)
    check("today real: accept rate", t["accept_rate"], 0.25)
    check("today real: auto-rejected count", t["auto_rejected"], 1)
    check("today real: rejected value", t["rejected_value"], 45.0)
    check("today real: passed / expired", (t["passed"], t["expired"]), (1, 1))
    check("today real: sell-backs", (t["sellbacks"], t["sellback_shares"]), (1, 100))
    top = r["by_symbol"][0]
    check("today real: top symbol by spend", top["symbol"], "ELOG")
    check("today real: ELOG quoted range", (top["min_rate"], top["max_rate"]), (0.009, 0.012))
    check("today real: ELOG requests", top["requests"], 2)

    # 7 days real picks up KOSS broker rejection (unpriced), not the Sep 1 accept
    t7 = report.build_report(report.filter_rows(ROWS, 7, "real", TODAY))["totals"]
    check("7d real: broker rejected", t7["broker_rejected"], 1)
    check("7d real: priced excludes unpriced reject", t7["priced"], 4)
    check("7d real: spend unchanged", t7["spend"], 2.4)

    # all time real includes Sep 1 accept
    ta = report.build_report(report.filter_rows(ROWS, None, "real", TODAY))["totals"]
    check("all real: spend", ta["spend"], 17.4)
    check("all real: avg paid/share (share-weighted)", ta["avg_rate"], 0.0348)

    # mode filters
    tm = report.build_report(report.filter_rows(ROWS, None, "mock", TODAY))["totals"]
    check("all mock: requests", tm["requests"], 1)
    tall = report.build_report(report.filter_rows(ROWS, None, "all", TODAY))["totals"]
    check("all modes: includes pre-mode row", tall["auto_rejected"], 2)

    # empty
    te = report.build_report([])
    check("empty: no avg rate", te["totals"]["avg_rate"], None)
    check("empty: no accept rate", te["totals"]["accept_rate"], None)
    check("empty: no days", (te["first_day"], te["last_day"]), (None, None))

    # load_rows skips malformed / blank lines
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "q.jsonl"
        p.write_text(json.dumps(ROWS[2]) + "\n\nnot json\n" + json.dumps(ROWS[3]) + "\n")
        check("load_rows skips bad lines", len(report.load_rows(p)), 2)
        full = report.report(p, 1, "real", TODAY)
        check("report(): echoes filters", (full["days"], full["mode"]), (1, "real"))
        check("load_rows missing file", report.load_rows(Path(d) / "nope.jsonl"), [])

    print(f"\n{passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    run()
