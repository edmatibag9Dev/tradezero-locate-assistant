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

    # --- account (platform) rows -------------------------------------------
    hist = [
        {"symbol": "oneg", "quoteReqID": "ZP-1", "locateShares": 100, "locateStatus": 50,
         "locatePrice": 0.02, "createdDate": "2026-10-30T14:05:00.1234567Z", "text": ""},
        {"symbol": "TNMG", "quoteReqID": "ZP-2.SU", "locateShares": 100, "locateStatus": 50,
         "locatePrice": 0.03, "createdDate": "2026-10-30T14:06:00Z"},
        {"symbol": "ONEG", "quoteReqID": "ZP-3", "locateShares": -100, "locateStatus": 50,
         "locatePrice": 0, "createdDate": "2026-10-30T20:00:00Z"},
        {"symbol": "XYZ", "quoteReqID": "Q-XYZ-1", "locateShares": 100, "locateStatus": 52,
         "locatePrice": 0.25, "createdDate": "2026-10-30T15:00:00Z"},
        {"symbol": "ABC", "quoteReqID": "ZP-4", "locateShares": 100, "locateStatus": 65,
         "locatePrice": 0.01, "createdDate": "2026-10-30T15:01:00Z"},
    ]
    pr = report.platform_rows(hist, "real")
    check("platform: filled -> ACCEPTED, symbol upper-cased",
          (pr[0]["result"], pr[0]["symbol"], pr[0]["total"]), ("ACCEPTED", "ONEG", 2.0))
    check("platform: 7-digit UTC fraction parses to local date", pr[0]["ts"][:4], "2026")
    check("platform: negative filled -> SELLBACK_SENT, no total",
          (pr[2]["result"], pr[2]["qty"], "total" in pr[2]), ("SELLBACK_SENT", 100, False))
    check("platform: tagged source", {r["source"] for r in pr}, {"platform"})
    log = [{"symbol": "XYZ", "qty": 100, "rate": 0.25, "total": 25.0, "quoteReqID": "Q-XYZ-1",
            "result": "AUTO_REJECT", "ts": "2026-10-30T08:00:00-0700", "mode": "real"}]
    m = report.merge_rows(log, pr)
    check("merge: app's own row wins (AUTO_REJECT kept, CANCELED dropped)",
          [r["result"] for r in m if r["symbol"] == "XYZ"], ["AUTO_REJECT"])
    check("merge: .SU id de-duplicates", len(report.merge_rows(pr[:2], [dict(pr[1], quoteReqID="ZP-2")])), 2)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "q.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in log) + "\n")
        rt = report.report(p, None, "real", TODAY, extra_rows=pr)["totals"]
        check("report+account: accepted incl. ZeroPro locates", rt["accepted"], 2)
        check("report+account: spend incl. ZeroPro locates", rt["spend"], 5.0)
        check("report+account: in-flight OFFERED row ignored", rt["requests"], 3)
        check("report+account: from_platform count", rt["from_platform"], 2)
        check("report+account: sell-back counted", rt["sellbacks"], 1)

    # --- 2026-10-30 live findings ------------------------------------------
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import tz_api
    check("sellback_ok: documented field", tz_api.sellback_ok({"locateSellbackSent": "true"}), True)
    check("sellback_ok: legacy field", tz_api.sellback_ok({"locateSellSent": "true"}), True)
    check("sellback_ok: false / missing", (tz_api.sellback_ok({"locateSellbackSent": "false"}),
                                          tz_api.sellback_ok({})), (False, False))
    for raw in ("2026-10-30T14:50:34.27Z", "2026-10-30T12:26:02.817Z",
                "2026-10-30T12:26:19.0234567Z", "2026-10-30T12:26:19Z"):
        got = report._local_ts(raw)
        check(f"ts converted to local offset: {raw}", (got[-5] in "+-", got.endswith("Z")), (True, False))
    utc = dt.datetime(2026, 10, 30, 14, 50, 34, tzinfo=dt.timezone.utc)
    check("ts keeps the instant", report._local_ts("2026-10-30T14:50:34.27Z"),
          utc.astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"))
    sells = report.platform_rows([
        {"symbol": "ONEG", "quoteReqID": "S-ONEG-1", "locateShares": -100, "locateStatus": 50,
         "locatePrice": 0, "createdDate": "2026-10-30T18:57:00Z"},
        {"symbol": "TNMG", "quoteReqID": "S-TNMG-1", "locateShares": -100, "locateStatus": 56,
         "locatePrice": 0, "createdDate": "2026-10-30T18:57:00Z", "text": "16 Insufficient shares."},
        {"symbol": "XX", "quoteReqID": "S-XX-1", "locateShares": -100, "locateStatus": 48,
         "locatePrice": 0, "createdDate": "2026-10-30T18:57:00Z"},
        {"symbol": "TNMG", "quoteReqID": "Q9", "locateShares": 0, "locateStatus": 56,
         "accountId": "ACCT123", "createdDate": "2026-10-30T12:26:19Z",
         "text": "Accept is already pending for account ACCT123 and symbol TNMG."},
    ], "real")
    check("sell rows: filled / rejected / queued",
          [r["result"] for r in sells[:3]], ["SELLBACK_SENT", "SELLBACK_FAILED", "SELLBACK_PENDING"])
    check("account ID scrubbed from broker text", "ACCT123" in sells[3]["detail"], False)
    check("scrub without known ID", report.scrub("pending for account 9XY99 and", None),
          "pending for account … and")
    applog = [{"symbol": "ONEG", "qty": 100, "quoteReqID": "S-ONEG-1", "result": "SELLBACK_FAILED",
               "ts": "2026-10-30T11:56:56-0700", "mode": "real"},
              {"symbol": "TNMG", "qty": 100, "quoteReqID": "S-TNMG-1", "result": "SELLBACK_SENT",
               "ts": "2026-10-30T11:56:56-0700", "mode": "real"}]
    mm = report.merge_rows(applog, sells)
    check("merge: account outcome overrides app sell-back status",
          [(r["symbol"], r["result"]) for r in mm if r["quoteReqID"].startswith("S-O") or r["quoteReqID"].startswith("S-T")],
          [("ONEG", "SELLBACK_SENT"), ("TNMG", "SELLBACK_FAILED")])
    check("merge: no duplicate sell rows", sum(r["quoteReqID"].startswith("S-") for r in mm), 3)
    saved = report.normalize_saved([{"symbol": "TNMG", "ts": "2026-10-30T12:26:19.023Z",
                                     "detail": "pending for account 9XY99 and symbol", "source": "platform"}])
    check("normalize_saved: ts + scrub", (saved[0]["ts"].endswith("Z"), "9XY99" in saved[0]["detail"]),
          (False, False))

    # --- sell-back lifecycle: sent -> pending (48 New) -> processed (50) ---------
    def sell(qid, sym, status, ts="2026-10-30T18:57:00Z"):
        return report.platform_rows([{"symbol": sym, "quoteReqID": qid, "locateShares": -100,
                                      "locateStatus": status, "locatePrice": 0,
                                      "createdDate": ts}], "real")[0]
    app = [{"symbol": "ONEG", "qty": 100, "quoteReqID": "S-A", "result": "SELLBACK_FAILED",
            "ts": "2026-10-30T11:56:56-0700", "mode": "real"},      # logged by the 1.5.1 bug
           {"symbol": "TNMG", "qty": 100, "quoteReqID": "S-B", "result": "SELLBACK_SENT",
            "ts": "2026-10-30T11:56:56-0700", "mode": "real"},      # ack only
           {"symbol": "ZZZ", "qty": 100, "quoteReqID": "S-C", "result": "SELLBACK_FAILED",
            "ts": "2026-10-30T11:56:56-0700", "mode": "real"}]      # never reached TradeZero
    res = {r["quoteReqID"]: r["result"] for r in report.merge_rows(app, [sell("S-A", "ONEG", 48)])}
    check("app 'failed' but account queued -> pending", res["S-A"], "SELLBACK_PENDING")
    check("app ack, no account row yet -> pending", res["S-B"], "SELLBACK_PENDING")
    check("app failed, no account row -> stays failed", res["S-C"], "SELLBACK_FAILED")
    res2 = {r["quoteReqID"]: r["result"] for r in
            report.merge_rows(app, [sell("S-A", "ONEG", 48), sell("S-A", "ONEG", 50),
                                    sell("S-B", "TNMG", 50), sell("S-B", "TNMG", 48)])}
    check("saved pending + later filled -> processed", res2["S-A"], "SELLBACK_SENT")
    check("filled is not undone by a stale pending row", res2["S-B"], "SELLBACK_SENT")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "q.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in app) + "\n")
        rt = report.report(p, None, "real", TODAY, extra_rows=[sell("S-A", "ONEG", 48)])["totals"]
        check("report: nothing counted as sold back while pending", rt["sellbacks"], 0)
        check("report: pending sell-backs and shares",
              (rt["sellback_pending"], rt["sellback_pending_shares"]), (2, 200))
        rt2 = report.report(p, None, "real", TODAY,
                            extra_rows=[sell("S-A", "ONEG", 50), sell("S-B", "TNMG", 50)])["totals"]
        check("report: processed sell-backs", (rt2["sellbacks"], rt2["sellback_shares"],
                                               rt2["sellback_pending"]), (2, 200, 0))

    cash = [
        {"cashType": "Locate Fees", "deposit": 0, "withdraw": 2.0, "entryDate": "2026-10-29T00:00:00"},
        {"cashType": "Locate Fees", "deposit": 3.0, "withdraw": 0, "entryDate": "2026-10-28T00:00:00"},
        {"cashType": "Locate Fees", "deposit": 0, "withdraw": 5.5, "entryDate": "2026-10-30T00:00:00"},
        {"cashType": "Locate & Borrow Charge", "deposit": 0, "withdraw": 0.4, "entryDate": "2026-10-30T00:00:00"},
        {"cashType": "Software & Data", "deposit": 0, "withdraw": 15.0, "entryDate": "2026-10-30T00:00:00"},
    ]
    cs = report.cash_summary(cash)
    check("cash: fees / credits / borrow", (cs["fees"], cs["credits"], cs["borrow"]), (7.5, 3.0, 0.4))
    check("cash: net = fees + borrow - credits", cs["net"], 4.9)
    check("cash: other cash types ignored", cs["fee_entries"] + cs["credit_entries"], 3)
    check("cash: empty ledger", report.cash_summary([])["net"], 0.0)
    check("window: 7 days", report.window(7, TODAY), ("2026-10-06", 7))
    check("window: all = 365", report.window(None, TODAY)[1], 365)

    print(f"\n{passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    run()
