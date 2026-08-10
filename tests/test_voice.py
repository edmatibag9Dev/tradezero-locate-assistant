"""Voice-layer tests.

Part 1: parser unit tests (pure text, fast).
Part 2: end-to-end synthetic audio — macOS `say` speaks each command into a
wav, whisper.cpp transcribes it, the parser maps it. Tests the whole chain
except the physical microphone. Run: python3 tests/test_voice.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import voice

WATCHLIST = ["IQST", "FRSX", "HSCS", "TWAV", "FOXS", "ROLR", "BOLD", "ATLN"]

failures = 0


def check(name: str, got: dict, want: dict) -> None:
    global failures
    ok = all(got.get(k) == v for k, v in want.items())
    print(f"{'PASS' if ok else 'FAIL'}  {name:<46} -> {got}")
    if not ok:
        failures += 1


# ---- Part 1: parser unit tests -------------------------------------------

print("— parser unit tests —")
cases = [
    ("locate 500 FRSX", {"cmd": "locate", "qty": 500, "symbol": "FRSX"}),
    ("Locate 500 shares of FRSX.", {"cmd": "locate", "qty": 500, "symbol": "FRSX"}),
    ("locate five hundred shares of FRSX", {"cmd": "locate", "qty": 500, "symbol": "FRSX"}),
    ("Quote 1,000 IQST", {"cmd": "locate", "qty": 1000, "symbol": "IQST"}),
    ("locate two hundred fifty shares of BOLD", {"cmd": "locate", "qty": 250, "symbol": "BOLD"}),
    ("locate a thousand HSCS", {"cmd": "locate", "qty": 1000, "symbol": "HSCS"}),
    ("Locate 300 shares of F R S X", {"cmd": "locate", "qty": 300, "symbol": "FRSX"}),
    ("locate 200 FRSK", {"cmd": "locate", "qty": 200, "symbol": "FRSX"}),  # fuzzy
    ("Accept.", {"cmd": "accept"}),
    ("yes", {"cmd": "accept"}),
    ("Pass", {"cmd": "pass"}),
    ("no thanks", {"cmd": "pass"}),
    ("Inventory", {"cmd": "inventory"}),
    ("what are my holdings", {"cmd": "inventory"}),
    ("sell back 100 FRSX", {"cmd": "sellback", "qty": 100, "symbol": "FRSX"}),
    ("quit", {"cmd": "quit"}),
    ("locate FRSX", {"cmd": "unknown"}),          # no quantity
    ("locate 500", {"cmd": "unknown"}),           # no ticker
    ("what a nice day", {"cmd": "unknown"}),
]
for text, want in cases:
    check(text, voice.parse_command(text, WATCHLIST), want)

# ---- Part 2: end-to-end synthetic audio ----------------------------------

print("\n— synthetic audio end-to-end (say -> whisper -> parse) —")
audio_cases = [
    ("locate five hundred shares of F R S X",
     {"cmd": "locate", "qty": 500, "symbol": "FRSX"}),
    ("quote three hundred shares of I Q S T",
     {"cmd": "locate", "qty": 300, "symbol": "IQST"}),
    ("accept", {"cmd": "accept"}),
    ("pass", {"cmd": "pass"}),
    ("inventory", {"cmd": "inventory"}),
]
with tempfile.TemporaryDirectory() as td:
    for i, (utterance, want) in enumerate(audio_cases):
        aiff = f"{td}/u{i}.aiff"
        wav = f"{td}/u{i}.wav"
        subprocess.run(["say", "-o", aiff, utterance], check=True)
        subprocess.run(["sox", aiff, "-r", "16000", "-c", "1", wav], check=True)
        text = voice.transcribe(wav)
        got = voice.parse_command(text, WATCHLIST)
        check(f'"{utterance}" (heard: {text!r})', got, want)

total = len(cases) + len(audio_cases)
print(f"\n{total - failures}/{total} passed")
sys.exit(1 if failures else 0)
