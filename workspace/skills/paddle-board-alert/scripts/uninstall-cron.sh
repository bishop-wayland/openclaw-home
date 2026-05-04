#!/bin/bash
# Remove the paddle-board-alert cron entry from ~/.openclaw/cron/jobs.json.
# Writes a timestamped backup before mutation.
set -euo pipefail

JOBS="$HOME/.openclaw/cron/jobs.json"
NAME="paddle-board-alert"

if [[ ! -f "$JOBS" ]]; then
  echo "ERROR: $JOBS does not exist." >&2
  exit 1
fi

BACKUP="${JOBS}.bak.$(date -u +%Y%m%dT%H%M%SZ).pre-paddle-uninstall"
cp -p "$JOBS" "$BACKUP"
echo "Backed up jobs.json → $BACKUP"

python3 - "$JOBS" "$NAME" <<'PY'
import json, sys
jobs_path, name = sys.argv[1], sys.argv[2]
with open(jobs_path) as f:
    cfg = json.load(f)
before = len(cfg.get("jobs", []))
cfg["jobs"] = [j for j in cfg.get("jobs", []) if j.get("name") != name]
after = len(cfg["jobs"])
with open(jobs_path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
print(f"  removed {before - after} job(s) named {name!r}; {after} job(s) remain")
PY

echo "Done."
