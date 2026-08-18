# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); dates are America/Los_Angeles.
Real quote logs (`logs/`), keys (`.env`), personal config (`config.json`), and the Whisper
model binary (`models/`) are gitignored and never committed.

## [1.3.1] — 2026-08-14

### Fixed
- Voice capture failed instantly ("mic_error") under launchd autostart: launchd jobs get a
  minimal PATH without /opt/homebrew/bin, so `rec` and `whisper-cli` were never found.
  voice.py now resolves both to absolute paths (shutil.which + Homebrew fallbacks), and the
  LaunchAgent plist sets an explicit PATH. Verified by transcribing under a stripped PATH.

## [1.3.0] — 2026-08-10

### Added
- End-of-day sell-back sweep: refunds all unused locate shares in one action — console
  button + `S` hotkey (with confirm), voice ("sell back everything" / "sweep"), CLI `sweep`
  command, and `POST /api/sweep`. Per-symbol results with named failures; each sell-back
  logged to the quote history. Voice tests now 27/27.

## [1.2.0] — 2026-08-10

### Added
- `install-autostart.sh`: launchd LaunchAgent installer — console starts at login,
  auto-restarts on crash (KeepAlive verified), survives closed terminals; `--status` and
  `--uninstall` included; server flags (e.g. `--lan`) baked into the job; logs to
  `logs/console.log`.

### Fixed
- Python 3.9 compatibility (`from __future__ import annotations` across `src/`) — the
  macOS built-in python3 now works; README prerequisite corrected to 3.9+.

## [1.1.0] — 2026-08-10

### Added
- `--lan` flag for the web console: binds all interfaces so other devices on a trusted
  network (e.g. a laptop next to the trading Mac) can reach the console; startup banner
  prints the LAN URL and a security warning. Default remains localhost-only.
- README "second screen / another Mac" instructions, including the firewall prompt and the
  fact that mic + spoken read-back stay on the server Mac.

## [1.0.0] — 2026-08-10

### Added
- TradeZero locates REST client (`src/tz_api.py`): quote, poll-by-history, accept, cancel,
  inventory, sell-back — stdlib only, keys from env.
- Approval rule engine (`src/rules.py`): auto-reject ≥ $0.20/share, warn ≥ $0.10, ask below;
  thresholds config-driven; 9 boundary tests.
- Voice layer (`src/voice.py`): sox push-to-talk capture, on-device whisper.cpp transcription,
  command parser with number words, spelled-ticker merging, and watchlist fuzzy matching;
  24 tests including synthetic TTS→Whisper→parse audio.
- Terminal UI (`src/app.py`): typed or `--voice` mode, spoken read-back, 30-second accept
  countdown, `--mock` practice mode with fixed rule-band symbols.
- Web console (`src/server.py` + `web/index.html`): localhost single-page UI with mic button,
  hotkeys (Space/A/P/I), pending-quote card with countdown bar, locate inventory, today's
  locate history table with daily spend summary; brand-styled, light/dark.
- Mock client (`src/mock_api.py`) for zero-risk practice without keys.
- Key validator (`src/check_keys.py`): read-only auth + config check.
- `setup.sh`: brew deps, Whisper model download, local config creation.
- Repo docs: AGENTS.md, llms.txt, SPEC-locate-workflow.md, BUILD-PLAN.md, 9-section README,
  sample quote log.

### Known limitations
- Paper accounts reject all locate quotes by design (validated live-only workflow; see
  BUILD-PLAN findings). Push-to-talk needs tab/terminal focus. macOS only.
