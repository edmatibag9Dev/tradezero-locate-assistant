# AGENTS.md — guide for AI agents working in this repo
> Standard: REPO-STANDARD 2026-10-09 · Commits, README and staging: CONTRIBUTING.md

This file is the canonical entry point for any AI agent (Claude Code, Cowork, Codex, etc.)
asked to **use, reference, extend, or rebuild** this project. Read it before acting.

## What this repo is

A voice-controlled short-locate assistant for TradeZero day traders. It quotes stock locates by
voice ("locate 500 F R S X"), enforces a per-share cost rule (auto-reject expensive borrows, ask
for approval on the rest), and shows the day's locate history in a local web console. Order
execution stays manual in the broker platform — this tool touches locates only.

Design in one line: **speech (sox + whisper.cpp, all on-device) → command parser → TradeZero
locates REST API → rule gate → spoken/web read-back, with every quote logged to JSONL.**

## File map

| Path | Committed? | Purpose |
|---|---|---|
| `AGENTS.md` | yes | This guide. |
| `README.md` | yes | Human quickstart (9-section standard). |
| `llms.txt` | yes | Machine-readable index. |
| `CONTRIBUTING.md` | yes | Commit + README rules. |
| `BUILD-PLAN.md` | yes | Decisions, core constraints, findings (incl. dead ends). |
| `SPEC-locate-workflow.md` | yes | TradeZero locate API contract + log schema + rule bands. |
| `CHANGELOG.md` | yes | Keep-a-Changelog history. |
| `setup.sh` | yes | One-time install: brew deps, Whisper model, local config. |
| `install-autostart.sh` | yes | launchd LaunchAgent installer (start at login, restart on crash). |
| `config.example.json` | yes | Config template (rules, polling, mode). |
| `.env.example` | yes | API key env-var template. |
| `watchlist.txt` | yes | Tickers prioritized by voice recognition; edit daily. |
| `src/tz_api.py` | yes | TradeZero REST client — locate endpoints only, stdlib urllib. |
| `src/mock_api.py` | yes | Same interface, no network; fixed rule-band symbols for practice. |
| `src/rules.py` | yes | The approval rule engine (auto-reject / warn / ask). |
| `src/voice.py` | yes | Mic record (sox), transcription (whisper-cli), command parser. |
| `src/app.py` | yes | Terminal UI — typed or `--voice` push-to-talk loop. |
| `src/server.py` | yes | Localhost web console (stdlib http.server) + JSON API. |
| `src/report.py` | yes | Locate-cost report — pure aggregation of `logs/quotes.jsonl` (no network). |
| `src/check_keys.py` | yes | Read-only key/config validator (two harmless GETs). |
| `web/index.html` | yes | Single-page console UI (self-contained; Google Fonts only). |
| `tests/test_rules.py` | yes | Rule-band boundary tests. |
| `tests/test_report.py` | yes | Locate-cost report aggregation + filter tests. |
| `tests/test_voice.py` | yes | Parser tests + TTS→Whisper→parse end-to-end audio tests. |
| `samples/quotes.sample.jsonl` | yes | Reference log so the repo previews without real data. |
| `config.json` | **no (gitignored)** | Holds the owner's real account ID. |
| `.env` | **no (gitignored)** | Real API keys. |
| `logs/` | **no (gitignored)** | Real locate/quote history (personal trading data). |
| `models/` | **no (gitignored)** | Whisper binary model (~141 MB) — `setup.sh` downloads it. |
| `CONFIG.local.md` | **no (gitignored)** | Mapping of placeholders → the owner's real values. |

## The data contract (`logs/quotes.jsonl`)

One JSON object per line, appended for **every** quote outcome (accepted, passed, auto-rejected,
broker-rejected, expired, sell-back). The web console's history table and daily summary read this.

```json
{"symbol": "WARN", "qty": 200, "rate": 0.12, "total": 24.0,
 "quoteReqID": "Q-WARN-EF56AB78", "result": "ACCEPTED",
 "ts": "2026-08-10T09:45:43-0700", "mode": "real"}
```

Rules an agent must preserve:
- `rate` is **per share** (TradeZero convention); `total = rate × qty`, precomputed at log time.
- `result` vocabulary: `ACCEPTED`, `PASSED`, `AUTO_REJECT`, `Rejected` (broker),
  `EXPIRED_UNANSWERED`, `NO_QUOTE`, `ACCEPT_FAILED`, `SELLBACK_SENT`, `SELLBACK_FAILED`.
- `ts` is local time with offset; the console filters "today" by string prefix `YYYY-MM-DD`.
- Append-only; never rewrite or dedupe historical lines.
- API keys and account IDs must never appear in log lines.

## How it works

1. **Input** (native Mac): push-to-talk records mic via sox `rec` until ~1.4 s silence;
   `whisper-cli` (base.en, on-device) transcribes; `voice.parse_command` maps to
   locate/accept/pass/inventory/sellback, merging spelled tickers ("F R S X"→"FRSX"),
   parsing number words, fuzzy-matching `watchlist.txt`.
2. **Quote**: POST `/v1/api/accounts/locates/quote` (share count rounded up to a 100-multiple),
   then poll `/locates/history` (2 s + up to 4×2 s) until status 65 Offered or terminal.
3. **Rule gate** (`rules.py`): rate ≥ auto_reject threshold → cancel immediately, log, speak;
   otherwise speak price + total (with warning ≥ warn threshold) and open the accept window.
4. **Accept/pass**: user must answer within TradeZero's **30-second** offer window; accept =
   POST `/locates/accept` (all-or-nothing), pass = DELETE cancel. Outcome spoken + logged.
5. **Console** (`server.py`, localhost by default; `--lan` binds all interfaces for
   trusted-network access from other devices): browser triggers the same flows over a JSON
   API; mic and Whisper stay server-side. UI polls state (1 s) and history (5 s).

## How to extend

- **Change rule thresholds:** edit `rules` in `config.json` — no code changes.
- **New voice command:** add intent detection in `voice.parse_command`, then handle the new
  `cmd` in `app.py` main loop AND `server.py` `flow_listen` — keep both in sync.
- **New API endpoint:** add a method to `src/tz_api.py` (and mirror it in `mock_api.py` so
  mock mode keeps working; tests rely on the mock).
- **Cost report:** metrics live in `src/report.py` (`build_report`); add a field there,
  cover it in `tests/test_report.py`, then render it in the `#report` card of
  `web/index.html`. The report is read-only over the log — never call the API from it.
- **UI changes:** `web/index.html` is self-contained (inline CSS/JS, brand tokens in `:root`).
- **Sell-back sweep** (shipped 1.3.0): `flow_sweep()` in `server.py` / `do_sweep()` in
  `app.py` — extend there for scheduling or filters (e.g. keep symbols still on watch).

## Privacy — hard rules

- Never commit `.env` (API keys), `config.json` (real account ID), `logs/` (real trading
  activity), or `CONFIG.local.md`. These are gitignored — do not "helpfully" force-add them.
- Public repo: docs use placeholders (`SET_ME`, `TZ…` examples); real values live only in the
  gitignored files above.
- Never print or log API keys; `tz_api.py` reads them from env only.
- Voice audio is processed on-device and the scratch wav lives in `/tmp` — never persist it.

> ⛔ **Money rule:** accepting a locate spends real dollars on a live account. Never auto-accept
> anywhere in this codebase. Auto-reject is safe to automate; accept always requires an explicit
> human "accept" (spoken, hotkey, or click). Preserve this invariant in any change.

> ℹ️ **Paper accounts reject all locate quotes by design** — testing the priced-quote flow
> requires live keys. Quote+pass is free; only accept spends money. Mock mode
> (`--mock`) simulates the full flow with fixed rule-band symbols: CHEP $0.004, MIDD $0.05,
> WARN $0.12, EXPN $0.35.

## Verification gates

Run before declaring a change done:

1. `python3 tests/test_rules.py` — 9/9 (rule bands, including the $0.20 boundary);
   `python3 tests/test_report.py` — 26/26 (cost-report totals, filters, malformed lines).
2. `python3 tests/test_voice.py` — 27/27 (parser + synthetic TTS→Whisper→parse audio;
   needs `say`, `sox`, `whisper-cli`, and the model present).
3. Mock CLI round trip: `printf 'locate 500 EXPN\nquit\n' | python3 src/app.py --mock`
   → EXPN auto-rejects.
4. Mock server round trip: start `python3 src/server.py --mock --port 8765`, then
   `curl -X POST localhost:8765/api/command -d '{"text":"locate 500 WARN"}'` → `"offered"`,
   `curl -X POST localhost:8765/api/accept -d '{}'` → `"accepted"`, and
   `/api/history` shows both rows.
5. Scrub grep (public repo): `git grep -I -nE "(TZ_API|SECRET|account_id)" -- ':!*.example*' ':!AGENTS.md'`
   must show no real values; `git status --short` must not list `.env`, `config.json`, `logs/`, `models/`.
6. Staged named paths only, and `git diff --cached --name-status --diff-filter=D` prints nothing — staging rules: [CONTRIBUTING.md → What to Stage](CONTRIBUTING.md#what-to-stage--never-commit-blindly).
7. `python3 ~/.claude/skills/repo-standard/scripts/repo-check.py .` reports no FAIL lines.
