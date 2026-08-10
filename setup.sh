#!/bin/bash
# One-time setup for the TradeZero Locate Assistant (macOS, Apple Silicon or Intel).
# Installs speech dependencies, downloads the Whisper model, creates local config.
set -e
cd "$(dirname "$0")"

echo "==> Checking Homebrew dependencies (whisper-cpp, sox)..."
command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh"; exit 1; }
brew list whisper-cpp &>/dev/null || brew install whisper-cpp
brew list sox &>/dev/null || brew install sox

echo "==> Downloading Whisper base.en model (~141 MB, one time)..."
mkdir -p models logs
if [ ! -f models/ggml-base.en.bin ]; then
  curl -L -o models/ggml-base.en.bin \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
fi

echo "==> Creating local config files (never committed)..."
[ -f config.json ] || cp config.example.json config.json
[ -f .env ] || cp .env.example .env
chmod 600 .env

echo "
Setup complete. Next steps:
  1. Try it with zero risk:      python3 src/server.py --mock   ->  http://127.0.0.1:8765
  2. Get TradeZero API keys:     portal.tradezero.com -> Enable API Trading -> API Key Management
  3. Put keys in .env, your account ID in config.json, set \"mode\": \"real\"
  4. Grant Microphone permission to your terminal app when macOS asks (first mic use)

NOTE: paper accounts REJECT all locate quotes by design — the priced-quote flow
needs a live account. Quoting + passing costs nothing; only 'accept' spends money."
