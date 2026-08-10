"""Voice layer: push-to-talk mic capture, local Whisper transcription,
and command parsing with watchlist-constrained ticker matching.

Everything runs on-device: sox `rec` captures the mic, whisper.cpp
transcribes, nothing leaves the Mac.

First mic use triggers a macOS permission prompt for the terminal app —
click Allow, then re-try the command.
"""

from __future__ import annotations

import difflib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "ggml-base.en.bin"
WATCHLIST_FILE = ROOT / "watchlist.txt"

# Words that are never tickers even though they show up in caps/short form.
STOPWORDS = {"OF", "THE", "A", "AN", "ON", "FOR", "TO", "AT", "IN", "SHARES",
             "SHARE", "STOCK", "LOCATE", "QUOTE", "GET", "ME", "PLEASE",
             "SELL", "BACK", "AND", "IT", "IS"}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000, "a": 1,
}


def record(wav_path: str, max_seconds: int = 8) -> bool:
    """Record mic until ~1.4s of silence (or max_seconds). True on success."""
    cmd = [
        "rec", "-q", "-r", "16000", "-c", "1", wav_path,
        "trim", "0", str(max_seconds),
        "silence", "1", "0.1", "1.5%", "1", "1.4", "3%",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=max_seconds + 5)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def transcribe(wav_path: str) -> str:
    out = subprocess.run(
        ["whisper-cli", "-m", str(MODEL), "-f", wav_path, "--no-timestamps"],
        capture_output=True, text=True, timeout=30)
    return out.stdout.strip() if out.returncode == 0 else ""


def load_watchlist() -> list[str]:
    if not WATCHLIST_FILE.exists():
        return []
    return [w.strip().upper() for w in WATCHLIST_FILE.read_text().split()
            if w.strip() and not w.startswith("#")]


def parse_number(tokens: list[str]) -> tuple[int | None, int]:
    """Parse a leading quantity from tokens ('500' or 'five hundred').

    Returns (value, tokens_consumed) or (None, 0).
    """
    if not tokens:
        return None, 0
    t0 = tokens[0].replace(",", "")
    if t0.isdigit():
        return int(t0), 1
    total, current, used = 0, 0, 0
    for tok in tokens:
        w = tok.lower()
        if w not in NUMBER_WORDS:
            break
        val = NUMBER_WORDS[w]
        if val in (100, 1000):
            current = max(current, 1) * val
            if val == 1000:
                total += current
                current = 0
        else:
            current += val
        used += 1
    total += current
    return (total, used) if used and total > 0 else (None, 0)


def extract_ticker(tokens: list[str], watchlist: list[str]) -> str | None:
    """Find the most likely ticker among the remaining tokens.

    Whisper usually merges spelled letters ('F R S X' -> 'FRSX'), but we also
    re-join runs of single letters as a fallback. Watchlist gets fuzzy-match
    priority; otherwise any 1-5 letter non-stopword token qualifies.
    """
    cleaned = [re.sub(r"[^A-Za-z]", "", t).upper() for t in tokens]
    cleaned = [t for t in cleaned if t]

    # Re-join runs of single letters: ['F','R','S','X'] -> 'FRSX'
    joined: list[str] = []
    run = ""
    for t in cleaned:
        if len(t) == 1 and t not in ("A", "I"):
            run += t
        else:
            if len(run) >= 2:
                joined.append(run)
            run = ""
            joined.append(t)
    if len(run) >= 2:
        joined.append(run)

    candidates = [t for t in joined if 1 <= len(t) <= 5 and t not in STOPWORDS]
    if not candidates:
        return None
    if watchlist:
        for c in candidates:
            if c in watchlist:
                return c
        for c in candidates:
            close = difflib.get_close_matches(c, watchlist, n=1, cutoff=0.75)
            if close:
                return close[0]
    # Prefer the last candidate: 'locate 500 shares of XYZ' puts it last.
    return candidates[-1]


def parse_command(text: str, watchlist: list[str] | None = None) -> dict:
    """Map a transcription to an app command.

    Returns {'cmd': 'locate'|'accept'|'pass'|'inventory'|'sellback'|'quit'|'unknown', ...}
    """
    watchlist = watchlist if watchlist is not None else load_watchlist()
    raw = text.strip()
    low = re.sub(r"[^a-z0-9\s]", " ", raw.lower())
    words = low.split()
    if not words:
        return {"cmd": "unknown", "text": raw}

    if any(w in ("accept", "yes", "yep", "take") for w in words):
        return {"cmd": "accept"}
    if any(w in ("pass", "no", "nope", "reject", "skip", "cancel") for w in words):
        return {"cmd": "pass"}
    if any(w in ("inventory", "holdings", "holding") for w in words):
        return {"cmd": "inventory"}
    if any(w in ("quit", "exit", "goodbye") for w in words) or "shut down" in low:
        return {"cmd": "quit"}

    sellback = "sell" in words and ("back" in words or "sellback" in low)
    if "sweep" in words or (sellback and any(w in ("everything", "all", "unused") for w in words)):
        return {"cmd": "sweep"}
    locate = any(w in ("locate", "quote", "borrow") for w in words)
    if locate or sellback:
        # Find quantity anywhere after the verb, then a ticker.
        tokens = raw.split()
        qty = None
        for i in range(len(tokens)):
            qty, used = parse_number([t.replace(",", "") for t in tokens[i:]])
            if qty:
                rest = tokens[:i] + tokens[i + used:]
                break
        if not qty:
            return {"cmd": "unknown", "text": raw,
                    "hint": "no share quantity heard"}
        ticker = extract_ticker(rest, watchlist)
        if not ticker:
            return {"cmd": "unknown", "text": raw, "hint": "no ticker heard"}
        return {"cmd": "sellback" if sellback else "locate",
                "qty": qty, "symbol": ticker}

    return {"cmd": "unknown", "text": raw}
