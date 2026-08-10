"""Mock TradeZero client — same interface as TradeZeroClient, no network.

Lets the whole quote -> rule -> approve/reject -> inventory loop run before
API keys exist. Prices are seeded from the symbol name so runs are repeatable:
try QQQQ-ish cheap names and 'EXPN' style symbols to hit different rule bands.

A few fixed symbols for testing the rule bands:
  CHEP  -> $0.004/share  (sub-penny: ASK)
  MIDD  -> $0.05/share   (ASK)
  WARN  -> $0.12/share   (ASK + warning)
  EXPN  -> $0.35/share   (AUTO_REJECT)
Anything else gets a pseudo-random rate under $0.30.
"""

from __future__ import annotations

import hashlib
import time

from tz_api import OFFERED

FIXED = {"CHEP": 0.004, "MIDD": 0.05, "WARN": 0.12, "EXPN": 0.35}


class MockTradeZeroClient:
    def __init__(self, base_url: str = "", account_id: str = "MOCK123"):
        self.account_id = account_id
        self._quotes: dict[str, dict] = {}
        self._inventory: dict[str, dict] = {}

    def _rate_for(self, symbol: str) -> float:
        if symbol in FIXED:
            return FIXED[symbol]
        h = int(hashlib.sha256(symbol.encode()).hexdigest(), 16)
        return round((h % 3000) / 10000, 4)  # $0.0000 - $0.2999

    def quote_locate(self, symbol: str, quantity: int, quote_req_id: str) -> dict:
        self._quotes[quote_req_id] = {
            "quoteReqID": quote_req_id,
            "symbol": symbol.upper(),
            "locateStatus": OFFERED,
            "locatePrice": self._rate_for(symbol.upper()),
            "locateShares": quantity,
            "offeredAt": time.time(),
        }
        return {"locateQuoteSent": "true"}

    def poll_quote(self, quote_req_id: str, polling_cfg: dict) -> dict | None:
        time.sleep(0.3)  # simulate a fast turnaround
        return self._quotes.get(quote_req_id)

    def accept_locate(self, quote_req_id: str) -> dict:
        q = self._quotes[quote_req_id]
        if time.time() - q["offeredAt"] > 30:
            return {"locateAcceptSent": "false", "text": "quote expired"}
        sym = q["symbol"]
        inv = self._inventory.setdefault(
            sym, {"symbol": sym, "located": 0, "available": 0, "spent": 0.0})
        inv["located"] += q["locateShares"]
        inv["available"] += q["locateShares"]
        inv["spent"] = round(inv["spent"] + q["locatePrice"] * q["locateShares"], 2)
        return {"locateAcceptSent": "true"}

    def cancel_locate(self, quote_req_id: str) -> dict:
        self._quotes.pop(quote_req_id, None)
        return {"locateCancelSent": "true"}

    def inventory(self) -> list[dict]:
        return list(self._inventory.values())

    def sell_back(self, symbol: str, quantity: int, quote_req_id: str,
                  locate_type: str = "Locate") -> dict:
        inv = self._inventory.get(symbol.upper())
        if inv and inv["available"] >= quantity:
            inv["available"] -= quantity
            inv["located"] -= quantity
            return {"locateSellSent": "true"}
        return {"locateSellSent": "false", "text": "insufficient available shares"}
