#!/bin/bash
# Disable live mode: prevent YNAB writes.
# Adds the --no-apply flag back to the cron entry's agentTurn message.

set -e

CRON_CONFIG="$HOME/.openclaw/cron/jobs.json"

echo "Disabling live mode for ynab-categorize..."

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
        if "--no-apply" in message:
            print("Already in preview mode (--no-apply present). No change.")
            sys.exit(0)
        # Append --no-apply to the propose.py invocation line
        new_message = message.replace(
            "scripts/propose.py",
            "scripts/propose.py --no-apply"
        )
        if new_message == message:
            print("ERROR: could not locate propose.py invocation in cron message.")
            sys.exit(1)
        entry["payload"]["message"] = new_message
        found = True
        break

if not found:
    print("ERROR: ynab-categorize entry not found in cron jobs.")
    sys.exit(1)

with open(cron_config_path, "w") as f:
    json.dump(config, f, indent=2)

print("Live mode disabled. Next cron fire runs in preview mode (--no-apply).")
EOF
