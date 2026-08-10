"""TradeZero locate assistant — CLI loop (voice layer comes next).

Commands:
  locate <shares> <SYMBOL>   quote a locate, apply rules, approve/reject
  inv                        current locate inventory
  sellback <shares> <SYMBOL> credit back unused located shares
  quit

Run:  python3 src/app.py            (mode comes from config.json; "mock" needs no keys)
      python3 src/app.py --live-config   force real client (still paper if paper keys)
"""

import json
import math
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import rules
import voice
from tz_api import TradeZeroClient, TradeZeroError, STATUS, OFFERED

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text())


def load_env() -> None:
    """Load key=value lines from the project .env into the environment."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    import os
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_env()

ACCEPT_WINDOW_S = 30
VOICE_MODE = "--voice" in sys.argv
SCRATCH_WAV = "/tmp/tz-locate-voice.wav"


def listen() -> str:
    """Record one utterance and return its transcription ('' on failure)."""
    print("   🎤 listening ...")
    if not voice.record(SCRATCH_WAV):
        print("   (mic capture failed — is microphone access granted?)")
        return ""
    text = voice.transcribe(SCRATCH_WAV)
    if text:
        print(f"   heard: {text}")
    return text


def say(text: str) -> None:
    """Speak via macOS TTS (and always print)."""
    print(f">> {text}")
    if CONFIG.get("speak"):
        subprocess.Popen(["say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def log_quote(record: dict) -> None:
    path = ROOT / CONFIG["log_file"]
    path.parent.mkdir(exist_ok=True)
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def fmt_rate(rate: float) -> str:
    cents = rate * 100
    return f"{cents:.2f} cents a share" if cents < 1 else f"{cents:.0f} cents a share"


def do_locate(client, shares: int, symbol: str) -> None:
    symbol = symbol.upper()
    qty = max(100, math.ceil(shares / 100) * 100)
    if qty != shares:
        print(f"   (locates are 100-share blocks: quoting {qty}, you asked for {shares})")

    quote_req_id = f"Q-{symbol}-{uuid.uuid4().hex[:8].upper()}"
    client.quote_locate(symbol, qty, quote_req_id)
    print(f"   quoting {qty} {symbol} ...")

    row = client.poll_quote(quote_req_id, CONFIG["polling"])
    if row is None:
        say(f"No quote came back for {symbol}. Try again.")
        log_quote({"symbol": symbol, "qty": qty, "result": "NO_QUOTE"})
        return
    status = row.get("locateStatus")
    if status != OFFERED:
        say(f"{symbol} locate {STATUS.get(status, status)}. {row.get('text', '')}".strip())
        log_quote({"symbol": symbol, "qty": qty, "result": STATUS.get(status, str(status))})
        return

    rate = float(row["locatePrice"])
    total = rate * int(row["locateShares"])
    verdict = rules.evaluate(rate, CONFIG["rules"])
    base = {"symbol": symbol, "qty": qty, "rate": rate, "total": round(total, 2),
            "quoteReqID": quote_req_id}

    if verdict["action"] == rules.AUTO_REJECT:
        client.cancel_locate(quote_req_id)
        limit_c = CONFIG["rules"]["auto_reject_at_per_share"] * 100
        say(f"Rejected. {symbol} quoted at {fmt_rate(rate)} — over your {limit_c:.0f} cent limit.")
        log_quote({**base, "result": "AUTO_REJECT"})
        return

    warn = "Warning — " if verdict["warn"] else ""
    say(f"{warn}{symbol}, {qty} shares at {fmt_rate(rate)} — {fmt_money(total)} total. Accept?")
    offered_at = time.monotonic()

    while True:
        remaining = ACCEPT_WINDOW_S - (time.monotonic() - offered_at)
        if remaining <= 0:
            say(f"Quote expired for {symbol}.")
            log_quote({**base, "result": "EXPIRED_UNANSWERED"})
            return
        if VOICE_MODE:
            # Say-then-listen: mic opens right after the question is spoken.
            heard = listen()
            answer = voice.parse_command(heard).get("cmd", "") if heard else ""
            if answer not in ("accept", "pass"):
                print(f"   ({remaining:.0f}s left — say 'accept' or 'pass')")
        else:
            answer = input(f"   accept / pass ({remaining:.0f}s left): ").strip().lower()
        if answer in ("accept", "a", "yes", "y"):
            out = client.accept_locate(quote_req_id)
            if str(out.get("locateAcceptSent", "")).lower() == "true":
                say(f"Accepted — {qty} {symbol} for {fmt_money(total)}.")
                log_quote({**base, "result": "ACCEPTED"})
            else:
                say(f"Accept failed for {symbol}: {out.get('text', 'unknown error')}")
                log_quote({**base, "result": "ACCEPT_FAILED", "detail": out})
            return
        if answer in ("pass", "p", "no", "n", "reject"):
            client.cancel_locate(quote_req_id)
            say(f"Passed on {symbol}.")
            log_quote({**base, "result": "PASSED"})
            return
        print("   say 'accept' or 'pass'")


def do_inventory(client) -> None:
    inv = client.inventory()
    if not inv:
        say("No locates in inventory.")
        return
    parts = []
    for row in inv:
        sym = row.get("symbol", "?")
        avail = row.get("available", row.get("locateShares", "?"))
        parts.append(f"{sym}: {avail} available")
        print(f"   {json.dumps(row)}")
    say("Holding " + "; ".join(parts))


def do_sellback(client, shares: int, symbol: str) -> None:
    req_id = f"S-{symbol.upper()}-{uuid.uuid4().hex[:8].upper()}"
    out = client.sell_back(symbol, shares, req_id)
    ok = str(out.get("locateSellSent", "")).lower() == "true"
    say(f"Sell-back {'sent' if ok else 'failed'} for {shares} {symbol.upper()}."
        + ("" if ok else f" {out.get('text', '')}"))
    log_quote({"symbol": symbol.upper(), "qty": shares,
               "result": "SELLBACK_SENT" if ok else "SELLBACK_FAILED"})


def main() -> None:
    mode = CONFIG["mode"]
    if "--mock" in sys.argv:
        mode = "mock"
    if mode == "mock":
        from mock_api import MockTradeZeroClient
        client = MockTradeZeroClient()
        print("MOCK MODE — no keys needed, no network calls. Rule bands: "
              "CHEP=$0.004  MIDD=$0.05  WARN=$0.12  EXPN=$0.35")
    else:
        try:
            client = TradeZeroClient(CONFIG["base_url"], CONFIG["account_id"])
        except TradeZeroError as e:
            print(f"error: {e}")
            sys.exit(1)

    r = CONFIG["rules"]
    print(f"Rules: auto-reject >= ${r['auto_reject_at_per_share']:.2f}/sh, "
          f"warn >= ${r['warn_at_per_share']:.2f}/sh, ask below.\n")

    if VOICE_MODE:
        wl = voice.load_watchlist()
        print(f"VOICE MODE — press Enter to talk. Watchlist: {', '.join(wl) or '(empty)'}")
        print('Say: "locate 500 FRSX" · "inventory" · "sell back 100 FRSX" · "quit"\n')

    while True:
        try:
            if VOICE_MODE:
                input("locate> [Enter to talk] ")
                heard = listen()
                if not heard:
                    continue
                parsed = voice.parse_command(heard)
            else:
                line = input("locate> ").strip()
                if not line:
                    continue
                parts = line.split()
                cmd = parts[0].lower()
                if cmd == "locate" and len(parts) == 3:
                    parsed = {"cmd": "locate", "qty": int(parts[1]), "symbol": parts[2]}
                elif cmd in ("inv", "inventory"):
                    parsed = {"cmd": "inventory"}
                elif cmd == "sellback" and len(parts) == 3:
                    parsed = {"cmd": "sellback", "qty": int(parts[1]), "symbol": parts[2]}
                elif cmd in ("quit", "exit", "q"):
                    parsed = {"cmd": "quit"}
                else:
                    parsed = {"cmd": "unknown", "text": line}
        except (EOFError, KeyboardInterrupt):
            print()
            break
        except ValueError:
            print("   shares must be a number, e.g. locate 500 ABCD")
            continue

        try:
            cmd = parsed["cmd"]
            if cmd == "locate":
                # Voice confirmation of what was heard happens via the quote
                # read-back itself — the accept step is the safety gate.
                do_locate(client, parsed["qty"], parsed["symbol"])
            elif cmd == "inventory":
                do_inventory(client)
            elif cmd == "sellback":
                do_sellback(client, parsed["qty"], parsed["symbol"])
            elif cmd == "quit":
                break
            elif cmd in ("accept", "pass"):
                print("   no quote is waiting — ask for a locate first")
            else:
                hint = parsed.get("hint", "")
                if VOICE_MODE:
                    say(f"Didn't catch that{': ' + hint if hint else ''}. Try again.")
                else:
                    print("   commands: locate <shares> <SYMBOL> | inv | "
                          "sellback <shares> <SYMBOL> | quit")
        except TradeZeroError as e:
            say(f"API error: {e}")


if __name__ == "__main__":
    main()
