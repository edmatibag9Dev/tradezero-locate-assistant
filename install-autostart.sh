#!/bin/bash
# Install a macOS launchd LaunchAgent that keeps the locate console running:
# starts at login, restarts if it crashes, survives closed terminal windows.
#
# Usage:
#   ./install-autostart.sh [server flags...]   # e.g.  ./install-autostart.sh --lan
#   ./install-autostart.sh --status            # is the job loaded / running?
#   ./install-autostart.sh --uninstall         # stop the server and remove the job
#
# Server output goes to logs/console.log (+ .err). Flags you pass (e.g. --lan,
# --mock, --port 8766) are baked into the job; re-run the installer to change them.
set -e
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
LABEL="com.tradezero.locate-console"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON3="$(command -v python3)"
UID_NUM="$(id -u)"

case "${1:-}" in
  --uninstall)
    launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed $LABEL — server stopped, LaunchAgent deleted."
    exit 0;;
  --status)
    if launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1; then
      launchctl print "gui/$UID_NUM/$LABEL" | grep -E "state|pid|last exit" | head -5
      echo "Loaded. Logs: $PROJECT_DIR/logs/console.log"
    else
      echo "$LABEL is not loaded."
    fi
    exit 0;;
esac

mkdir -p logs "$HOME/Library/LaunchAgents"

ARGS_XML=""
for a in "$@"; do
  ARGS_XML="$ARGS_XML
    <string>$a</string>"
done

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON3</string>
    <string>$PROJECT_DIR/src/server.py</string>$ARGS_XML
  </array>
  <key>WorkingDirectory</key>
  <string>$PROJECT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$PROJECT_DIR/logs/console.log</string>
  <key>StandardErrorPath</key>
  <string>$PROJECT_DIR/logs/console.err</string>
</dict>
</plist>
PLIST

plutil -lint "$PLIST" >/dev/null

launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST"

echo "Installed $LABEL (flags: ${*:-none})."
echo "  status:    ./install-autostart.sh --status"
echo "  logs:      tail -f logs/console.log"
echo "  remove:    ./install-autostart.sh --uninstall"
echo ""
echo "NOTE: first voice use under autostart may re-prompt for Microphone access"
echo "(grant it to 'python3' / 'Python' in System Settings > Privacy & Security"
echo "> Microphone if the mic ever fails silently)."
echo ""
echo "If the server keeps exiting (real mode without keys), check logs/console.err —"
echo "launchd restarts it every ~10s until the config is fixed."
