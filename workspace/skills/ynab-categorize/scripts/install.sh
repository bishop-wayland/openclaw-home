#!/bin/bash
# Install the ynab-categorize skill.
# Idempotent. Registers cron in preview mode (--no-apply), appends SETUP.md to AGENTS.md, runs preview fire.

set -e

SKILL_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
CRON_CONFIG="$HOME/.openclaw/cron/jobs.json"
AGENTS_MD="$HOME/.openclaw/workspace/AGENTS.md"
SETUP_MD="$SKILL_DIR/SETUP.md"

echo "Installing ynab-categorize skill..."

# Ensure cron config exists
if [ ! -f "$CRON_CONFIG" ]; then
    mkdir -p "$(dirname "$CRON_CONFIG")"
    echo '{"version": 1, "jobs": []}' > "$CRON_CONFIG"
fi

# Use Python to add/replace the cron entry safely.
# Schema follows paddle-board-alert pattern: agentTurn payload with `message` prompting Haiku
# to invoke the script via the exec tool.
SKILL_DIR_VAR="$SKILL_DIR"
python3 << EOF
import json
from pathlib import Path

cron_config_path = Path.home() / ".openclaw" / "cron" / "jobs.json"
skill_dir = "$SKILL_DIR_VAR"

with open(cron_config_path, "r") as f:
    config = json.load(f)

agent_message = (
    "Weekly YNAB transaction categorizer for Dave on Sunday at 9 AM PT.\n\n"
    "Call the exec tool exactly once with this command:\n\n"
    f"python3 {skill_dir}/scripts/propose.py --no-apply\n\n"
    "That is your only job. Do not narrate. Do not summarize. Do not call any other tools. "
    "The Python script handles fetching uncategorized transactions, classification, "
    "and delivery (email + iMessage). After exec returns, reply with the single word OK. "
    "Nothing else."
)

new_entry = {
    "name": "ynab-categorize",
    "enabled": True,
    "schedule": {
        "kind": "cron",
        "expr": "0 9 * * 0",
        "tz": "America/Los_Angeles"
    },
    "sessionTarget": "isolated",
    "wakeMode": "now",
    "payload": {
        "kind": "agentTurn",
        "message": agent_message,
        "model": "anthropic/claude-haiku-4-5",
        "timeoutSeconds": 1200,
        "lightContext": True,
        "tools": ["exec"]
    },
    "failureAlert": {
        "after": 1,
        "channel": "bluebubbles",
        "to": "+16508239528",
        "cooldownMs": 3600000
    }
}

# Replace existing entry if present, otherwise append
config["jobs"] = [j for j in config["jobs"] if j.get("name") != "ynab-categorize"]
config["jobs"].append(new_entry)

with open(cron_config_path, "w") as f:
    json.dump(config, f, indent=2)

print(f"Cron entry registered: Sundays 9 AM PT, preview mode (--no-apply), 1200s timeout")
EOF

# Append SETUP.md to AGENTS.md if not already there
if [ -f "$SETUP_MD" ] && [ -s "$SETUP_MD" ]; then
    if ! grep -q "YNAB Approval Routing" "$AGENTS_MD" 2>/dev/null; then
        echo "" >> "$AGENTS_MD"
        cat "$SETUP_MD" >> "$AGENTS_MD"
        echo "Appended SETUP.md to AGENTS.md"
    else
        echo "SETUP.md already in AGENTS.md (skipped append)"
    fi
fi

# Run preview fire — production-equivalent run with delivery enabled, only YNAB writes gated.
# No --dry-send: we want the email + iMessage to actually land so Dave can review.
echo ""
echo "Running preview fire (--no-apply only, full delivery)..."
cd "$SKILL_DIR"
python3 scripts/propose.py --no-apply > /tmp/ynab-preview.log 2>&1 &
PREVIEW_PID=$!
echo "Preview fire PID: $PREVIEW_PID (running in background, no timeout)"
echo "Watch progress: tail -f $SKILL_DIR/logs/run-*.jsonl"
echo ""
echo "Next steps:"
echo "  1. Wait for preview fire to deliver (5-10 min on first run with backlog)"
echo "  2. Check email at otte.dave@gmail.com and iMessage for the digest"
echo "  3. Reply 'go' when ready to enable live mode (real YNAB writes)"
echo "  4. Bishop will run: bash $SKILL_DIR/scripts/enable-live.sh"
echo ""
echo "Install complete."
