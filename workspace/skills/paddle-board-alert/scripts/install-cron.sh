#!/bin/bash
# Add the paddle-board-alert openclaw cron entry to ~/.openclaw/cron/jobs.json.
#
# Idempotent: if a job named "paddle-board-alert" already exists, it's replaced.
# A timestamped backup of jobs.json is written before any change.
#
# To uninstall: run scripts/uninstall-cron.sh.
set -euo pipefail

JOBS="$HOME/.openclaw/cron/jobs.json"
SKILL_DIR="$HOME/.openclaw/workspace/skills/paddle-board-alert"
NAME="paddle-board-alert"

if [[ ! -f "$JOBS" ]]; then
  echo "ERROR: $JOBS does not exist. Is openclaw initialized?" >&2
  exit 1
fi

BACKUP="${JOBS}.bak.$(date -u +%Y%m%dT%H%M%SZ).pre-paddle-install"
cp -p "$JOBS" "$BACKUP"
echo "Backed up jobs.json → $BACKUP"

python3 - "$JOBS" "$NAME" "$SKILL_DIR" <<'PY'
import json
import sys
import time
import uuid

jobs_path, name, skill_dir = sys.argv[1], sys.argv[2], sys.argv[3]
with open(jobs_path) as f:
    cfg = json.load(f)

cfg.setdefault("version", 1)
cfg.setdefault("jobs", [])

cron_message = (
    f"Paddle-board forecast check for Dave at 5 AM PT.\n\n"
    f"Call the exec tool exactly once with this command:\n\n"
    f"python3 {skill_dir}/scripts/check.py --real-send\n\n"
    f"That is your only job. Do not narrate. Do not summarize. Do not call any "
    f"other tools. The Python script handles fetching the forecast, evaluating "
    f"the wind window, and (on a go-day) delivering the iMessage to Dave "
    f"via the imsg CLI. After exec returns, reply with the single word "
    f"OK. Nothing else."
)

new_job = {
    "id": str(uuid.uuid4()),
    "name": name,
    "enabled": True,
    "createdAtMs": int(time.time() * 1000),
    "schedule": {"kind": "cron", "expr": "0 5 * * *", "tz": "America/Los_Angeles"},
    "sessionTarget": "isolated",
    "wakeMode": "now",
    "payload": {
        "kind": "agentTurn",
        "message": cron_message,
        "model": "anthropic/claude-haiku-4-5",
        "timeoutSeconds": 90,
        "lightContext": True,
        "tools": ["exec"],
    },
    "failureAlert": {
        "after": 1,
        "channel": "bluebubbles",
        "to": "+16508239528",
        "cooldownMs": 3600000,
    },
    "state": {},
}

before = len(cfg["jobs"])
cfg["jobs"] = [j for j in cfg["jobs"] if j.get("name") != name]
removed = before - len(cfg["jobs"])
cfg["jobs"].append(new_job)

with open(jobs_path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")

print(f"  removed {removed} existing job(s) named {name!r}")
print(f"  added new job id={new_job['id']}")
print(f"  schedule: {new_job['schedule']['expr']} {new_job['schedule']['tz']}")
PY

echo "Done. To uninstall: $SKILL_DIR/scripts/uninstall-cron.sh"
echo "To verify openclaw picked it up: openclaw cron list 2>/dev/null || cat $JOBS | jq '.jobs[] | select(.name==\"$NAME\")'"
