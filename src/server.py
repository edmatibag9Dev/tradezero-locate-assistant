"""Local web console for the TradeZero locate assistant.

Serves a single-page UI (web/index.html) plus a JSON API. Mic capture and
Whisper transcription happen server-side (same tested pipeline as the CLI);
the browser triggers listening and renders state. Localhost only.

Run:  python3 src/server.py [--mock] [--port 8765]
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import report
import rules
import voice
from tz_api import TradeZeroClient, TradeZeroError, STATUS, OFFERED

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text())
ACCEPT_WINDOW_S = 30

# --- shared state ---------------------------------------------------------

LOCK = threading.Lock()
PENDING: dict | None = None   # the currently offered quote awaiting accept/pass
BUSY = threading.Lock()       # serializes mic + quote flows


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    import os
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def say(text: str) -> None:
    if CONFIG.get("speak"):
        subprocess.Popen(["say", text], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


def log_quote(record: dict) -> None:
    path = ROOT / CONFIG["log_file"]
    path.parent.mkdir(exist_ok=True)
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    record["mode"] = MODE
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def fmt_rate(rate: float) -> str:
    cents = rate * 100
    return f"{cents:.2f} cents a share" if cents < 1 else f"{cents:.0f} cents a share"


# --- flows ----------------------------------------------------------------

def flow_locate(qty: int, symbol: str) -> dict:
    global PENDING
    symbol = symbol.upper()
    import math
    rounded = max(100, math.ceil(qty / 100) * 100)
    quote_req_id = f"Q-{symbol}-{uuid.uuid4().hex[:8].upper()}"
    CLIENT.quote_locate(symbol, rounded, quote_req_id)
    row = CLIENT.poll_quote(quote_req_id, CONFIG["polling"])

    if row is None:
        say(f"No quote came back for {symbol}.")
        log_quote({"symbol": symbol, "qty": rounded, "result": "NO_QUOTE"})
        return {"status": "no_quote", "symbol": symbol}
    st = row.get("locateStatus")
    if st != OFFERED:
        detail = str(row.get("text", "")).strip()
        say(f"{symbol} locate {STATUS.get(st, st)}. {detail}")
        log_quote({"symbol": symbol, "qty": rounded,
                   "result": STATUS.get(st, str(st)), "detail": detail})
        return {"status": "rejected_by_broker", "symbol": symbol,
                "broker_status": STATUS.get(st, str(st)), "detail": detail}

    rate = float(row["locatePrice"])
    total = round(rate * int(row["locateShares"]), 2)
    verdict = rules.evaluate(rate, CONFIG["rules"])
    base = {"symbol": symbol, "qty": rounded, "rate": rate, "total": total,
            "quoteReqID": quote_req_id}

    if verdict["action"] == rules.AUTO_REJECT:
        CLIENT.cancel_locate(quote_req_id)
        limit_c = CONFIG["rules"]["auto_reject_at_per_share"] * 100
        say(f"Rejected. {symbol} quoted at {fmt_rate(rate)} — "
            f"over your {limit_c:.0f} cent limit.")
        log_quote({**base, "result": "AUTO_REJECT"})
        return {"status": "auto_rejected", **base}

    with LOCK:
        PENDING = {**base, "warn": verdict["warn"],
                   "expires_at": time.time() + ACCEPT_WINDOW_S}
    warn = "Warning — " if verdict["warn"] else ""
    say(f"{warn}{symbol}, {rounded} shares at {fmt_rate(rate)} — "
        f"{total:.2f} dollars total. Accept?")
    return {"status": "offered", **base, "warn": verdict["warn"],
            "expires_in": ACCEPT_WINDOW_S}


def flow_answer(accept: bool) -> dict:
    global PENDING
    with LOCK:
        p = PENDING
        if p is None:
            return {"status": "no_pending"}
        if time.time() > p["expires_at"]:
            PENDING = None
            log_quote({**_strip(p), "result": "EXPIRED_UNANSWERED"})
            say(f"Quote expired for {p['symbol']}.")
            return {"status": "expired", "symbol": p["symbol"]}
        PENDING = None
    if accept:
        out = CLIENT.accept_locate(p["quoteReqID"])
        ok = str(out.get("locateAcceptSent", "")).lower() == "true"
        result = "ACCEPTED" if ok else "ACCEPT_FAILED"
        log_quote({**_strip(p), "result": result})
        say(f"Accepted — {p['qty']} {p['symbol']} for {p['total']:.2f} dollars."
            if ok else f"Accept failed for {p['symbol']}.")
        return {"status": result.lower(), **_strip(p)}
    CLIENT.cancel_locate(p["quoteReqID"])
    log_quote({**_strip(p), "result": "PASSED"})
    say(f"Passed on {p['symbol']}.")
    return {"status": "passed", **_strip(p)}


def _strip(p: dict) -> dict:
    return {k: v for k, v in p.items() if k not in ("expires_at", "warn")}


def flow_listen(context: str) -> dict:
    """Record one utterance and act on it. context: 'command' | 'answer'."""
    wav = "/tmp/tz-locate-web.wav"
    if not voice.record(wav):
        return {"status": "mic_error"}
    text = voice.transcribe(wav)
    if not text:
        return {"status": "heard_nothing"}
    parsed = voice.parse_command(text)
    out = {"heard": text, "parsed": parsed}

    if context == "answer" or PENDING is not None:
        if parsed["cmd"] == "accept":
            return {**out, **flow_answer(True)}
        if parsed["cmd"] == "pass":
            return {**out, **flow_answer(False)}
        if PENDING is not None:
            return {**out, "status": "say_accept_or_pass"}
    if parsed["cmd"] == "locate":
        return {**out, **flow_locate(parsed["qty"], parsed["symbol"])}
    if parsed["cmd"] == "sellback":
        req = f"S-{parsed['symbol']}-{uuid.uuid4().hex[:8].upper()}"
        r = CLIENT.sell_back(parsed["symbol"], parsed["qty"], req)
        ok = str(r.get("locateSellSent", "")).lower() == "true"
        log_quote({"symbol": parsed["symbol"], "qty": parsed["qty"],
                   "result": "SELLBACK_SENT" if ok else "SELLBACK_FAILED"})
        say(f"Sell back {'sent' if ok else 'failed'} for {parsed['symbol']}.")
        return {**out, "status": "sellback_sent" if ok else "sellback_failed"}
    if parsed["cmd"] == "sweep":
        return {**out, **flow_sweep()}
    if parsed["cmd"] == "inventory":
        return {**out, "status": "inventory", "inventory": CLIENT.inventory()}
    return {**out, "status": "not_understood"}


def flow_sweep() -> dict:
    """Sell back every unused locate share. Refund-only; failures reported
    per symbol (e.g. Single Use inventory tied to a short can't be refunded)."""
    try:
        inv = CLIENT.inventory()
    except TradeZeroError as e:
        return {"status": "api_error", "error": str(e)}
    results, swept_shares, failed = [], 0, []
    for row in inv:
        symbol = row.get("symbol")
        avail = int(row.get("available", row.get("locateShares", 0)) or 0)
        if not symbol or avail <= 0:
            continue
        req = f"S-{symbol}-{uuid.uuid4().hex[:8].upper()}"
        try:
            r = CLIENT.sell_back(symbol, avail, req)
            ok = str(r.get("locateSellSent", "")).lower() == "true"
        except TradeZeroError as e:
            ok, r = False, {"text": str(e)}
        log_quote({"symbol": symbol, "qty": avail,
                   "result": "SELLBACK_SENT" if ok else "SELLBACK_FAILED"})
        results.append({"symbol": symbol, "qty": avail, "ok": ok,
                        "detail": str(r.get("text", "")).strip()})
        if ok:
            swept_shares += avail
        else:
            failed.append(symbol)
    if not results:
        say("Nothing to sweep — no unused locate shares.")
        return {"status": "nothing_to_sweep", "results": []}
    msg = f"Sweep sent — {swept_shares} shares across " \
          f"{sum(1 for x in results if x['ok'])} symbols."
    if failed:
        msg += f" Failed: {', '.join(failed)}."
    say(msg)
    return {"status": "swept", "swept_shares": swept_shares, "results": results}


def today_history() -> list[dict]:
    path = ROOT / CONFIG["log_file"]
    if not path.exists():
        return []
    today = time.strftime("%Y-%m-%d")
    rows = []
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("ts", "").startswith(today):
            rows.append(r)
    return rows[::-1]


# --- HTTP -----------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (ROOT / "web" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/state":
            with LOCK:
                p = PENDING
                pending = None
                if p:
                    remaining = max(0, p["expires_at"] - time.time())
                    pending = {**_strip(p), "warn": p["warn"],
                               "expires_in": round(remaining, 1)}
            self._json({"mode": MODE, "rules": CONFIG["rules"],
                        "pending": pending, "busy": BUSY.locked()})
        elif self.path == "/api/history":
            self._json({"history": today_history()})
        elif self.path.startswith("/api/report"):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            raw_days = (q.get("days") or ["7"])[0]
            mode = (q.get("mode") or ["real"])[0]
            if mode not in ("real", "mock", "all"):
                return self._json({"error": "mode must be real, mock or all"}, 400)
            try:
                days = None if raw_days == "all" else max(1, int(raw_days))
            except ValueError:
                return self._json({"error": "days must be a number or 'all'"}, 400)
            self._json(report.report(ROOT / CONFIG["log_file"], days, mode))
        elif self.path == "/api/inventory":
            try:
                self._json({"inventory": CLIENT.inventory()})
            except TradeZeroError as e:
                self._json({"error": str(e)}, 502)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n) or b"{}") if n else {}
        try:
            if self.path == "/api/listen":
                if not BUSY.acquire(blocking=False):
                    return self._json({"status": "busy"}, 409)
                try:
                    self._json(flow_listen(payload.get("context", "command")))
                finally:
                    BUSY.release()
            elif self.path == "/api/command":
                parsed = voice.parse_command(payload.get("text", ""))
                if parsed["cmd"] == "locate":
                    self._json(flow_locate(parsed["qty"], parsed["symbol"]))
                elif parsed["cmd"] == "accept":
                    self._json(flow_answer(True))
                elif parsed["cmd"] == "pass":
                    self._json(flow_answer(False))
                elif parsed["cmd"] == "sweep":
                    self._json(flow_sweep())
                elif parsed["cmd"] == "sellback":
                    req = f"S-{parsed['symbol']}-{uuid.uuid4().hex[:8].upper()}"
                    r = CLIENT.sell_back(parsed["symbol"], parsed["qty"], req)
                    ok = str(r.get("locateSellSent", "")).lower() == "true"
                    log_quote({"symbol": parsed["symbol"], "qty": parsed["qty"],
                               "result": "SELLBACK_SENT" if ok else "SELLBACK_FAILED"})
                    self._json({"status": "sellback_sent" if ok else "sellback_failed"})
                else:
                    self._json({"status": "not_understood", "parsed": parsed})
            elif self.path == "/api/accept":
                self._json(flow_answer(True))
            elif self.path == "/api/pass":
                self._json(flow_answer(False))
            elif self.path == "/api/sweep":
                self._json(flow_sweep())
            else:
                self._json({"error": "not found"}, 404)
        except TradeZeroError as e:
            self._json({"status": "api_error", "error": str(e)}, 502)


def lan_ip() -> str:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))  # no packets sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()


def main() -> None:
    global CLIENT, MODE
    load_env()
    MODE = "mock" if "--mock" in sys.argv else CONFIG["mode"]
    port = 8765
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    if MODE == "mock":
        from mock_api import MockTradeZeroClient
        CLIENT = MockTradeZeroClient()
    else:
        CLIENT = TradeZeroClient(CONFIG["base_url"], CONFIG["account_id"])

    host = "127.0.0.1"
    if "--lan" in sys.argv:
        host = "0.0.0.0"
        print(f"Locate console ({MODE} mode) on ALL interfaces:")
        print(f"  this Mac:      http://127.0.0.1:{port}")
        print(f"  from your LAN: http://{lan_ip()}:{port}")
        print("  ⚠ LAN mode: anyone on this network can reach the console —")
        print("    accept/pass included. Use only on a trusted home network.")
    else:
        print(f"Locate console ({MODE} mode): http://127.0.0.1:{port}")
        print("  (this Mac only — start with --lan to allow other devices)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
