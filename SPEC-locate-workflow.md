# SPEC — TradeZero Locate Workflow & Log Contract

The stable contracts this project depends on: the TradeZero locate API surface (as documented at
developer.tradezero.com, Aug 2026), the approval-rule bands, and the append-only quote log.

## Inputs

| Input | Source | Notes |
|---|---|---|
| `TZ_API_KEY_ID` / `TZ_API_SECRET_KEY` | `.env` (gitignored) | Sent as headers on every request; key pair selects paper vs live |
| `account_id` | `config.json` (gitignored) | TradeZero account (e.g. `TZP…` paper / live ID) |
| `rules.*` | `config.json` | Per-share thresholds, dollars |
| `watchlist.txt` | repo root | Voice-recognition ticker bias; one symbol per line |
| Voice / typed command | mic or console | `locate <qty> <SYMBOL>`, `accept`, `pass`, `inventory`, `sell back <qty> <SYMBOL>` |

## TradeZero API surface used (base `https://webapi.tradezero.com`)

| Call | Purpose |
|---|---|
| `POST /v1/api/accounts/locates/quote` | Request quote: `{account, symbol, quantity, quoteReqID}` — quantity multiple of 100; `quoteReqID` client-generated unique |
| `GET /v1/api/accounts/{accountId}/locates/history` | Poll for quote status; match `quoteReqID` and `<quoteReqID>.SU` |
| `POST /v1/api/accounts/locates/accept` | `{accountId, quoteReqID}` — all-or-nothing, within 30 s of Offered |
| `DELETE /v1/api/accounts/locates/cancel/accounts/{accountId}/quoteReqID/{quoteReqID}` | Decline/cleanup |
| `GET /v1/api/accounts/{accountId}/locates/inventory` | Held locates, `available` share counts |
| `POST /v1/api/accounts/locates/sell` | Credit back unused shares: `{account, symbol, quantity, locateType, quoteReqID}` |

**Status codes:** 48 New · 50 Filled · 52 Canceled · 54 Pending · 56 Rejected · 65 Offered
(30-second accept window) · 67 Expired · 81 Quoting. `locatePrice` is **per share** and is `0`
until status 65.

## Rule bands (config-driven; defaults shown)

| Per-share rate | Action |
|---|---|
| ≥ `auto_reject_at_per_share` ($0.20) | Cancel quote immediately; speak + log `AUTO_REJECT`; no accept window |
| ≥ `warn_at_per_share` ($0.10), < auto-reject | Speak price with **warning**, ask |
| < warn (incl. sub-penny) | Speak price, ask |

**Invariant: no code path may accept a locate without an explicit human answer** (spoken
"accept", hotkey `A`, or button). Timeout = expired, never accepted.

## Output contract — `logs/quotes.jsonl` (append-only)

```json
{"symbol": "WARN", "qty": 200, "rate": 0.12, "total": 24.0,
 "quoteReqID": "Q-WARN-EF56AB78", "result": "ACCEPTED",
 "ts": "2026-08-10T09:45:43-0700", "mode": "real"}
```

Invariants:
- One line per outcome; never rewrite, reorder, or dedupe.
- `result` ∈ ACCEPTED · PASSED · AUTO_REJECT · Rejected · EXPIRED_UNANSWERED · NO_QUOTE ·
  ACCEPT_FAILED · SELLBACK_SENT · SELLBACK_FAILED.
- `rate` per share; `total` precomputed; broker rejections may omit `rate`/`total`.
- `ts` local time with UTC offset, prefix-filterable by `YYYY-MM-DD`; `mode` ∈ mock · real.
- No secrets, keys, or account IDs in any line.

## Console JSON API (`src/server.py` — localhost by default, `--lan` binds all interfaces)

| Endpoint | Returns |
|---|---|
| `GET /api/state` | `{mode, rules, pending: {symbol, qty, rate, total, warn, expires_in} \| null, busy}` |
| `POST /api/listen {context}` | Records mic, transcribes, acts; `context: "command" \| "answer"` |
| `POST /api/command {text}` | Same flows from typed text |
| `POST /api/accept` / `POST /api/pass` | Resolve the pending quote |
| `GET /api/history` | `{history: [today's log lines, newest first]}` |
| `GET /api/inventory` | `{inventory: [...]}` |

Consumers (the web UI, or anything a group member builds) may rely on these shapes.
