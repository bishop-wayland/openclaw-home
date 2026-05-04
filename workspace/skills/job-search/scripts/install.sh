#!/usr/bin/env bash
# Install / uninstall the job-search launchd schedule.
#
#   scripts/install.sh install     — load the plist (Sun 7am PT)
#   scripts/install.sh uninstall   — unload the plist
#   scripts/install.sh status      — show current load state + last run
#   scripts/install.sh now         — fire one run immediately (real send)
#   scripts/install.sh dry         — fire one run immediately (dry-send)

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_NAME="com.bishop.job-search"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

case "${1:-}" in
  install)
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_NAME}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>python3</string>
    <string>${SKILL_DIR}/scripts/search.py</string>
    <string>--layer2-max-searches</string>
    <string>12</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>0</integer>
    <key>Hour</key><integer>7</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${SKILL_DIR}/logs/launchd.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>${SKILL_DIR}/logs/launchd.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
EOF
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"
    echo "✓ Installed: $PLIST_PATH"
    echo "  Schedule: Sun 7:00 AM PT (system local time)"
    launchctl list | grep -F "$PLIST_NAME" || true
    ;;
  uninstall)
    if [ -f "$PLIST_PATH" ]; then
      launchctl unload "$PLIST_PATH" 2>/dev/null || true
      rm -f "$PLIST_PATH"
      echo "✓ Uninstalled $PLIST_PATH"
    else
      echo "(not installed)"
    fi
    ;;
  status)
    launchctl list | grep -F "$PLIST_NAME" || echo "(not loaded)"
    if [ -f "$PLIST_PATH" ]; then
      echo "Plist exists at: $PLIST_PATH"
    fi
    last_log=$(ls -t "$SKILL_DIR/logs/run-"*.jsonl 2>/dev/null | head -1 || true)
    if [ -n "$last_log" ]; then
      echo "Last run log: $last_log"
      tail -1 "$last_log" | python3 -m json.tool 2>/dev/null || tail -1 "$last_log"
    else
      echo "No runs yet."
    fi
    ;;
  now)
    exec /usr/bin/env python3 "$SKILL_DIR/scripts/search.py"
    ;;
  dry)
    exec /usr/bin/env python3 "$SKILL_DIR/scripts/search.py" --dry-send
    ;;
  *)
    echo "Usage: $0 {install|uninstall|status|now|dry}"
    exit 1
    ;;
esac
