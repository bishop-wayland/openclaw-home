#!/bin/bash
# Enable live mode: allow real YNAB writes.
# Removes the --no-apply flag from the cron entry's agentTurn message.

set -e

CRON_CONFIG="$HOME/.openclaw/cron/jobs.json"

echo "Enabling live mode for ynab-categorize..."

python3 << 'EOF'
import json
import sys
from pathlib import Path

cron_config_path = Path.home() / ".openclaw" / "cron" / "jobs.json"

with open(cron_config_path, "r") as f:
    config = json.load(f)

found = False
for entry in config["jobs"]:
    if entry.get("name") == "ynab-categorize":
        message = entry.get("payload", {}).get("message", "")
        if "--no-apply" not in message:
            print("Already in live mode (no --no-apply present). No change.")
            sys.exit(0)
        new_message = message.replace(" --no-apply", "")
        entry["payload"]["message"] = new_message
        found = True
        break

if not found:
    print("ERROR: ynab-categorize entry not found in cron jobs.")
    sys.exit(1)

with open(cron_config_path, "w") as f:
    json.dump(config, f, indent=2)

print("Live mode enabled. Next Sunday's cron commits real YNAB writes.")
EOF
