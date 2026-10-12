# TradeZero Locate Assistant

Voice-controlled short-locate quoting, rule-gated approval, and a daily locate history console
for TradeZero day traders — locates only, order execution stays in your trading platform.

## Project Overview

This tool turns the locate workflow into a hands-free loop: press a key, say *"locate 500 shares
of F R S X"*, hear the price read back aloud, and say *"accept"* or *"pass"* — all inside the
quote window. A configurable cost rule protects you from expensive borrows automatically:
quotes at or above $0.20/share are rejected before you're even asked, and anything at or above
$0.10/share carries a spoken warning. Everything runs locally on your Mac; speech never leaves
the machine, and your API keys stay in a local env file. Technically it is a stdlib-only Python
app: on-device speech (sox + whisper.cpp) → command parser → TradeZero locates REST API → rule
gate → spoken/web read-back, with every quote logged to JSONL.

## Purpose

Short sellers on TradeZero often need to locate hard-to-borrow shares in a hurry: quotes expire
in 30 seconds, and clicking through the platform while watching the tape costs time and focus.
Built by and for members of a short selling trading group — fork it, tune the thresholds, and
make it yours.

## Features

- **Voice locate quotes** — push-to-talk; spelled tickers ("F R S X"), number words ("five
  hundred"), and a daily watchlist bias recognition toward the names you actually trade.
- **Rule-gated approval** — ≥ $0.20/share auto-rejects (configurable); $0.10–$0.199 asks with
  a warning; below that just asks. Nothing is ever accepted without your explicit word.
- **30-second countdown** — the accept window is visualized in the web console and enforced;
  expired quotes log as expired, never silently accepted.
- **Web console** (localhost) — mic button, hotkeys (`Space` talk, `A` accept, `P` pass,
  `I` inventory), pending-quote card, locate inventory, and a running **today's locates** table
  with per-day totals: quotes, accepts, dollars spent on borrows.
- **Locate cost report** — a console card that totals locate spend from the quote log:
  dollars spent, accepted count and accept rate, average $/share actually paid, auto-rejected
  count with the quote value declined, passed/expired counts, sell-backs, and a per-symbol
  table (requests, accepted, shares, spend, avg paid, quoted range). Period: Today / 7 days /
  30 days / All; mode: Real / Mock / All (defaults to Real, last 7 days). Reads only the
  local log — no API calls, no cost. Also available as JSON at `GET /api/report`.
- **Spoken read-back** — price per share and total cost announced via macOS speech.
- **Locate inventory + sell-back** — see held locates; sell unused shares back for credit.
- **End-of-day sweep** — one action refunds ALL unused locate shares: the console button
  ("Sell back all unused", hotkey `S`), voice (*"sell back everything"* / *"sweep"*), or the
  CLI `sweep` command. Per-symbol results reported; failures (e.g. Single Use tied to a
  short) named individually.
- **Mock mode** — practice the entire flow with zero risk and no API keys.
- **Terminal UI** — the same flows work in a plain CLI (`src/app.py`), typed or voice.

## File Descriptions

| File | Description |
|---|---|
| `setup.sh` | One-time install: brew deps (whisper-cpp, sox), Whisper model, local config |
| `src/server.py` | Web console server (localhost:8765) + JSON API |
| `web/index.html` | Single-page console UI (self-contained) |
| `src/app.py` | Terminal UI — typed commands or `--voice` push-to-talk |
| `src/tz_api.py` | TradeZero REST client (locate endpoints only, no dependencies) |
| `src/mock_api.py` | Offline mock client with fixed practice symbols |
| `src/rules.py` | Approval rule engine |
| `src/report.py` | Locate-cost report: aggregates `logs/quotes.jsonl` by period, mode and symbol |
| `src/voice.py` | Mic capture, on-device Whisper transcription, command parser |
| `src/check_keys.py` | Read-only validator for your API keys and config |
| `config.example.json` | Config template — copy to `config.json` (gitignored) |
| `.env.example` | API key template — copy to `.env` (gitignored) |
| `watchlist.txt` | Tickers the voice parser prioritizes; edit each morning |
| `tests/` | Rule-band tests, locate-cost report tests, synthetic TTS→Whisper→parse audio tests |
| `samples/quotes.sample.jsonl` | Example of the quote log format |
| `AGENTS.md` / `llms.txt` / `SPEC-locate-workflow.md` / `BUILD-PLAN.md` | Agent + contract docs |

## How to Use

0. **Prerequisites** — macOS with [Homebrew](https://brew.sh) and Python 3.9+ (the macOS
   built-in `python3` works). If
   `brew --version` fails, install Homebrew first (asks for your Mac password):
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
   then follow the installer's printed "Next steps" to add `brew` to your PATH
   (on Apple Silicon: `eval "$(/opt/homebrew/bin/brew shellenv)"`).
1. **Install**: `./setup.sh` — installs whisper-cpp and sox via Homebrew, downloads the
   ~141 MB Whisper model, and creates your local `config.json` and `.env`.
2. **Practice free** — `python3 src/server.py --mock` → open http://127.0.0.1:8765. Try the mock
   symbols: `CHEP` (0.4¢ → asks), `WARN` (12¢ → asks with warning), `EXPN` (35¢ → auto-rejects).
   Press `Space`, speak, then say "accept" or "pass" when the mic reopens. First mic use triggers
   a macOS Microphone permission prompt for your terminal app — click Allow.
3. **Get API keys** — log in at https://portal.tradezero.com/login → Enable API Trading → sign
   agreements → API Key Management → Generate. **The secret is shown exactly once.** Live
   accounts need the API Trading add-on (ProBundle/FreeBundle).
4. **Configure** — put keys in `.env`, your account ID in `config.json`, set `"mode": "real"`.
   Validate with `python3 src/check_keys.py` (read-only, spends nothing).
5. **Trade day** — edit `watchlist.txt` with the day's candidates, start the server, and quote
   by voice, hotkey, or the typed command box (`locate 500 FRSX`). Unused shares:
   *"sell back 100 FRSX"*.
6. **Second screen / another Mac** (optional) — start with `--lan`
   (`python3 src/server.py --lan`) and open `http://<trading-mac-name>.local:8765` from any
   device on your network (find the name under System Settings → General → Sharing). Approve
   the macOS firewall prompt on first run. **The mic and spoken read-back stay on the server
   Mac** — remote devices are remote controls/monitors. ⚠ LAN mode means anyone on the
   network can reach the console, including accept — use only on a trusted home network
   (default remains localhost-only). Port busy? Add `--port 8766`.
7. **Auto-start at login** (optional, recommended for a dedicated trading Mac) —
   `./install-autostart.sh --lan` installs a launchd LaunchAgent: the console starts at
   login, restarts if it crashes, and survives closed terminals. Any server flags you pass
   are baked in. `--status` checks it, `--uninstall` removes it; output goes to
   `logs/console.log`. If the mic fails silently afterward, grant Microphone access to
   `python3`/`Python` in System Settings → Privacy & Security.

### Update / refresh

- **Daily:** refresh `watchlist.txt` with the day's gap-up candidates before the open.
- **History:** `logs/quotes.jsonl` accumulates every outcome; the console's table shows today,
  and the **Locate cost report** card summarizes any period (append-only JSONL, easy to analyze).
  JSON: `curl 'http://127.0.0.1:8765/api/report?days=30&mode=real'` (`days` = number or `all`;
  `mode` = `real`, `mock` or `all`).
- **Thresholds:** edit `rules` in `config.json`; changes apply on next server start.
- **Model upgrade:** drop a different ggml model into `models/` and update the path in
  `src/voice.py` if you want higher accuracy (small.en) at some speed cost.
- **Verify any change:** run the gates in `AGENTS.md` (rule tests, voice tests, mock round trips).

## Data Sources

- **TradeZero Developer API** — https://developer.tradezero.com (locates, accounts, orders,
  WebSocket streams). Base URL `https://webapi.tradezero.com` for both paper and live; your key
  pair selects the environment. Locate prices are quoted **per share**, quantities in multiples
  of 100, offers expire in **30 seconds**, rate limit 10 req/s on order endpoints.
- **Whisper model** — `ggml-base.en.bin` from the official whisper.cpp repository on Hugging
  Face (downloaded by `setup.sh`; all transcription is on-device).
- Quote history is generated locally in `logs/quotes.jsonl` (gitignored; see `samples/`).

## Known Limitations

- **Paper accounts reject every locate quote by design** (TradeZero simulates no locate
  inventory) — paper validates keys and request formatting only.
- Locates must be quoted in **multiples of 100 shares**.
- Accepting is **all-or-nothing** per quote — no partial accepts.
- "Single Use" locates (Reg SHO threshold symbols) can't be sold back after funding a short.
- Extended-hours and market-hours behavior of the locate desk isn't documented by TradeZero.
- Push-to-talk requires the browser tab (or terminal) to have focus.
- The cost report shows **gross** spend: TradeZero's sell-back response carries no credit
  amount, so refunds from sell-backs are counted (shares) but not netted out (dollars).
- Log lines written before the `mode` field existed (very early builds) appear only under
  the report's **All** mode filter.
- macOS only (uses `say`, sox/coreaudio, Homebrew).

## Workarounds

- **Paper accounts:** test the priced flow on a live account with quote → **pass** (costs
  nothing); only *accept* spends money. Mock mode (`--mock`) simulates the full flow with fixed
  rule-band symbols.
- **100-share multiples:** the app rounds up and tells you.
- **All-or-nothing accept:** you can short less than you locate, and sell the rest back.
- **Single Use locates:** no workaround.
- **Undocumented session hours:** no workaround; expect quotes mainly during regular sessions.
- **Push-to-talk focus:** no workaround yet; a global OS-level hotkey is on the roadmap.
- **Gross report spend:** check sell-back credits in the TradeZero platform statement.
- **Pre-`mode` log lines:** select **All** in the report's mode filter to include them.
- **macOS only:** no workaround.

## Build Notes

- **Zero Python dependencies** — stdlib only (urllib, http.server, threading). The only system
  deps are `whisper-cpp` and `sox` via Homebrew.
- Speech is fully on-device: sox records until ~1.4 s of silence; whisper.cpp (base.en model)
  transcribes; a deterministic parser handles number words, spelled tickers, and fuzzy watchlist
  matching. No cloud STT, no audio retention (scratch wav in `/tmp`).
- The web console is one self-contained HTML file (inline CSS/JS; Google Fonts is the only
  external reference) served by a ~250-line stdlib HTTP server. The browser never touches the
  mic — it triggers server-side listening, so the tested pipeline is identical in CLI and web.
- Safety invariant: **accept is never automated.** Auto-reject only ever saves money; accept
  always requires an explicit human answer. See `AGENTS.md` for the full contract.
- Architecture and dead-ends (including the paper-locate discovery) in `BUILD-PLAN.md`.

---
*Not affiliated with TradeZero. Trading involves risk; locate fees are real money on live
accounts. This tool never places orders and never accepts a locate without your explicit
confirmation.*

*Last updated: 2026-10-12*
