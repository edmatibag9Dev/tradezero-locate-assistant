"""TradeZero Developer API client — locates only.

Auth: TZ-API-KEY-ID / TZ-API-SECRET-KEY headers, read from environment.
Base URL is the same for paper and live; the key pair selects the environment.

Endpoints used (per developer.tradezero.com docs, Aug 2026):
  POST   /v1/api/accounts/locates/quote
  GET    /v1/api/accounts/{accountId}/locates/history      (poll for quote status)
  POST   /v1/api/accounts/locates/accept
  DELETE /v1/api/accounts/locates/cancel/accounts/{accountId}/quoteReqID/{quoteReqID}
  GET    /v1/api/accounts/{accountId}/locates/inventory
  POST   /v1/api/accounts/locates/sell
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error

# locateStatus codes
STATUS = {
    48: "New",
    50: "Filled",
    52: "Canceled",
    54: "Pending",
    56: "Rejected",
    65: "Offered",
    67: "Expired",
    81: "Quoting",
}
OFFERED = 65
FILLED = 50
TERMINAL = {50, 52, 56, 67}


class TradeZeroError(Exception):
    pass


class TradeZeroClient:
    def __init__(self, base_url: str, account_id: str):
        self.base_url = base_url.rstrip("/")
        self.account_id = account_id
        key_id = os.environ.get("TZ_API_KEY_ID")
        secret = os.environ.get("TZ_API_SECRET_KEY")
        if not key_id or not secret:
            raise TradeZeroError(
                "Set TZ_API_KEY_ID and TZ_API_SECRET_KEY environment variables "
                "(see .env.example). Use PAPER keys until the app is trusted."
            )
        self._headers = {
            "TZ-API-KEY-ID": key_id,
            "TZ-API-SECRET-KEY": secret,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode()
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise TradeZeroError(f"{method} {path} -> HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise TradeZeroError(f"{method} {path} -> network error: {e.reason}") from e

    # --- locates -----------------------------------------------------------

    def quote_locate(self, symbol: str, quantity: int, quote_req_id: str) -> dict:
        return self._request("POST", "/v1/api/accounts/locates/quote", {
            "account": self.account_id,
            "symbol": symbol.upper(),
            "quantity": quantity,
            "quoteReqID": quote_req_id,
        })

    def locate_history(self) -> list[dict]:
        out = self._request("GET", f"/v1/api/accounts/{self.account_id}/locates/history")
        return out.get("locateHistory", [])

    def poll_quote(self, quote_req_id: str, polling_cfg: dict) -> dict | None:
        """Poll history until the quote row reaches Offered or a terminal state.

        Reg SHO threshold symbols may answer under '<quoteReqID>.SU' (Single Use);
        we match either row and return the priced one when both exist.
        """
        time.sleep(polling_cfg["initial_wait_s"])
        for _ in range(polling_cfg["max_attempts"]):
            rows = [r for r in self.locate_history()
                    if r.get("quoteReqID") in (quote_req_id, f"{quote_req_id}.SU")]
            offered = [r for r in rows if r.get("locateStatus") == OFFERED]
            if offered:
                return offered[0]
            terminal = [r for r in rows if r.get("locateStatus") in TERMINAL]
            if terminal:
                return terminal[0]
            time.sleep(polling_cfg["interval_s"])
        return None

    def accept_locate(self, quote_req_id: str) -> dict:
        return self._request("POST", "/v1/api/accounts/locates/accept", {
            "accountId": self.account_id,
            "quoteReqID": quote_req_id,
        })

    def cancel_locate(self, quote_req_id: str) -> dict:
        path = (f"/v1/api/accounts/locates/cancel/accounts/"
                f"{self.account_id}/quoteReqID/{quote_req_id}")
        return self._request("DELETE", path)

    def inventory(self) -> list[dict]:
        out = self._request("GET", f"/v1/api/accounts/{self.account_id}/locates/inventory")
        return out.get("locateInventory", out.get("inventory", [])) if isinstance(out, dict) else out

    def sell_back(self, symbol: str, quantity: int, quote_req_id: str,
                  locate_type: str = "Locate") -> dict:
        return self._request("POST", "/v1/api/accounts/locates/sell", {
            "account": self.account_id,
            "symbol": symbol.upper(),
            "quantity": quantity,
            "locateType": locate_type,
            "quoteReqID": quote_req_id,
        })
