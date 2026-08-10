# BUILD-PLAN — TradeZero Locate Assistant

*Owner: Ed · Drafted: 2026-08-10 · Status: v1 shipped (mock + paper validated; live pending)*

## Decisions locked

| Decision | Choice | Why |
|---|---|---|
| Scope | Locates only — no order endpoints | Owner executes shorts manually in ZeroPro; locates are account-level so API-accepted locates are usable for manual shorts; lowest-risk slice of the API |
| Approval rule | ≥ $0.20/sh auto-reject · $0.10–$0.199 warn+ask · < $0.10 ask | Auto-reject only ever saves money so it's safe to automate; accept always needs a human word; $0.10 warning encodes the "10¢+ borrow is a signal" rule |
| Sub-penny quotes | Ask (not auto-accept) | Auto-accept would let the app spend money alone; a 0.9¢ locate on 10k shares is still $90 |
| Speech stack | sox `rec` + whisper.cpp (base.en) on-device | `hear` formula gone from Homebrew; openai-whisper needs torch (Python 3.14 wheels uncertain); whisper.cpp is a clean brew install; nothing leaves the Mac |
| Ticker recognition | Spell-out + watchlist fuzzy match | Whisper merges "F R S X"→"FRSX" natively; watchlist bias fixes the rest; free-form ticker pronunciation is unreliable by design |
| Web architecture | Server-side mic; browser triggers via JSON API | Reuses the already-tested CLI pipeline byte-for-byte; no getUserMedia permissions or browser audio-encoding differences; any browser works |
| HTTP stack | Python stdlib only (urllib, http.server) | Trading-group members can run it with zero pip installs |
| Quote handling | Poll `/locates/history` 2 s + 4×2 s | Documented recommendation; quote status is not pushed |
| Config | JSON file + .env, both gitignored; committed examples | Shareable repo with zero personal data in the tree |

## Core constraint / insight

**TradeZero locate offers expire in 30 seconds, and accepting spends real money.** The whole
design flows from this: speed matters (voice beats clicking), but the accept step must never be
automated. The rule engine splits the decision space so automation only ever *saves* money
(auto-reject) and a human word is required to *spend* it. Locate prices are per share; locate
quantities are 100-share blocks; accepts are all-or-nothing — but shorts against inventory can
be any size, and standard locates can be sold back for credit.

## Findings (including dead ends)

- **Paper accounts cannot test the locate flow.** Every quote is rejected asynchronously
  ("System error"), ETB checks always return true, inventory is always empty. Documented as
  live-only. Paper is still useful: it validates auth, request formatting, polling, and
  rejection handling. The zero-cost live test is quote → pass.
- **AAPL rejection "2 Easy to borrow"** is the pre-trade signal that no locate is needed —
  worth surfacing as a friendly "just short it" message (future polish).
- **No market data in the TradeZero API** — no quotes, candles, or VWAP. Any strategy logic
  (e.g. auto-quoting the day's gainers) needs an external data source.
- **`hear` (macOS speech CLI) is no longer in Homebrew core** — its GitHub install needs sudo.
  whisper.cpp turned out better anyway: deterministic, offline, and its base.en model nails
  spelled tickers and number words on synthetic tests (24/24).
- **Whisper transcription quirk**: merges spelled letters and normalizes numbers itself
  ("five hundred" → "500"), which simplified the parser considerably.
- **Quote status is 0-priced until Offered (65)** — reading `locatePrice` before status 65
  would announce "$0.00"; the poller waits for 65 or terminal.
- **Reg SHO threshold symbols** can answer under `<quoteReqID>.SU` (Single Use pool) — the
  poller matches both; Single Use inventory can't be sold back after funding a short.
- **Deliberate mishearing test**: "FRSK" fuzzy-matched to watchlist FRSX at cutoff 0.75 —
  the watchlist is the load-bearing part of ticker accuracy.

## Roadmap

1. Live-key smoke test: quote → pass (zero cost), then one micro-accept (~$1) to prove accept.
2. End-of-day sell-back sweep (inventory → refundable → `/locates/sell`), console button.
3. Global OS-level push-to-talk hotkey (works while the platform has focus).
4. "Easy to borrow" friendly read-back; auto-load watchlist from a gainers scanner.
5. Locate-cost analytics over the accumulated JSONL (cost per symbol, hit rate, spend per week).
