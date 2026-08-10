"""Validate TradeZero API keys — read-only smoke test.

Reads keys from the project .env file (or existing environment variables),
then makes two harmless GET calls: locate inventory and locate history.
No quotes are requested, nothing is accepted, no money is spent.

Run:  python3 src/check_keys.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_env()
    config = json.loads((ROOT / "config.json").read_text())

    problems = []
    if os.environ.get("TZ_API_KEY_ID", "").startswith(("your-", "")) and \
            not os.environ.get("TZ_API_KEY_ID"):
        problems.append("TZ_API_KEY_ID is missing — fill it in .env")
    elif "your-" in os.environ.get("TZ_API_KEY_ID", ""):
        problems.append("TZ_API_KEY_ID still has the placeholder value — fill it in .env")
    if not os.environ.get("TZ_API_SECRET_KEY") or \
            "your-" in os.environ.get("TZ_API_SECRET_KEY", ""):
        problems.append("TZ_API_SECRET_KEY is missing or placeholder — fill it in .env")
    if config.get("account_id") in ("", "SET_ME"):
        problems.append('account_id in config.json is still "SET_ME" — '
                        "put your paper account ID there")
    if problems:
        print("Not ready yet:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    from tz_api import TradeZeroClient, TradeZeroError

    client = TradeZeroClient(config["base_url"], config["account_id"])
    print(f"Testing keys against {config['base_url']} "
          f"(account {config['account_id']}) ...")

    try:
        inv = client.inventory()
        print(f"  inventory: OK — {len(inv)} locate position(s)")
        hist = client.locate_history()
        print(f"  history:   OK — {len(hist)} locate record(s)")
    except TradeZeroError as e:
        print(f"  FAILED: {e}")
        print("\nCommon causes: wrong/regenerated secret, API Trading not "
              "enabled yet, or wrong account ID.")
        sys.exit(1)

    print("\nKeys are valid. Next: set \"mode\": \"real\" in config.json "
          "and run python3 src/app.py for a live paper locate.")


if __name__ == "__main__":
    main()
