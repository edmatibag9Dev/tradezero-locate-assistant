# CLAUDE.md — TradeZero Locate Assistant

@AGENTS.md

## Session start (Claude Code)

1. Read `PROJECT-NOTE.md` if present — local status and open items (gitignored, lives only
   on the machine that runs the console).
2. `git status` and `git log --oneline -5`; this repo's `main` on GitHub is the source of truth.
3. Check which machine you are on. The **running copy is on the Mac Studio** at
   `~/tradezero-locate-assistant` (launchd job `com.tradezero.locate-console`, `--lan`,
   live account). It must stay in the home folder: launchd failed from `~/Documents`
   (exit 78, macOS privacy protection).

## Money and safety (in addition to AGENTS.md)

- The console is on a **live** TradeZero account. Never run accept, sell-back or sweep
  against it to test. Use `--mock` on another port (`--port 8766`) for any test.
- Read-only calls (`locates/history`, `locates/inventory`, `cash-transactions`) are fine.
- Never print, log or commit `.env`, `config.json`, `logs/`, or the account ID.

## Deploy a change on the Mac Studio

```bash
cd ~/tradezero-locate-assistant && git pull
launchctl kickstart -k gui/$(id -u)/com.tradezero.locate-console
./install-autostart.sh --status          # expect: state = running
```

Run the verification gates in AGENTS.md first — on **Python 3.9** (`/usr/bin/python3`),
which is what the launchd job uses.

## Outputs for Ed

Review documents go out as `.docx` plus a `.md` copy (the `.md` is for repos and agents).
State what was verified versus assumed; never present a guess as a fact.
