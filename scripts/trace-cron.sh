#!/usr/bin/env bash
# Forensic per-hop trace for the most recent run of any cron job.
# Surfaces each hop with timing and outcome interpretation, so a cron
# alert is debuggable in <60 sec without reading raw JSON.
#
# Usage: scripts/trace-cron.sh <job-name>
#   e.g. scripts/trace-cron.sh medication-noon

set -euo pipefail

JOB_NAME="${1:-}"
if [ -z "$JOB_NAME" ]; then
  echo "usage: $0 <job-name>" >&2
  echo "available jobs:" >&2
  python3 -c "
import json
for j in json.load(open('/Users/bishop/.openclaw/cron/jobs.json'))['jobs']:
  print(f\"  {j['name']}  (enabled={j['enabled']})\")
" >&2
  exit 1
fi

JOB_ID=$(python3 -c "
import json, sys
jobs = json.load(open('/Users/bishop/.openclaw/cron/jobs.json'))['jobs']
match = [j['id'] for j in jobs if j['name'] == '$JOB_NAME']
if not match:
    print('no cron job named $JOB_NAME', file=sys.stderr); sys.exit(1)
print(match[0])
")

RUNS_FILE="/Users/bishop/.openclaw/cron/runs/$JOB_ID.jsonl"
GATEWAY_ERR_LOG="/Users/bishop/.openclaw/logs/gateway.err.log"

if [ ! -s "$RUNS_FILE" ]; then
  echo "(no run history at $RUNS_FILE)"
  exit 0
fi

python3 - "$JOB_NAME" "$JOB_ID" "$RUNS_FILE" "$GATEWAY_ERR_LOG" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone

job_name, job_id, runs_file, err_log = sys.argv[1:5]

with open(runs_file) as f:
    last = f.readlines()[-1].strip()
run = json.loads(last)

def ts(ms):
    if ms is None: return "(none)"
    return datetime.fromtimestamp(ms/1000, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

def ms(v):
    if v is None: return "?"
    return f"{v/1000:.1f}s" if v >= 1000 else f"{v}ms"

run_at      = run.get("runAtMs")
end_ts      = run.get("ts")
duration    = run.get("durationMs", 0)
status      = run.get("status", "?")
error       = run.get("error")
summary     = run.get("summary") or "(empty — agent produced no reply)"
delivered   = run.get("delivered")
deliv_stat  = run.get("deliveryStatus", "?")
delivery    = run.get("delivery") or {}
intended    = delivery.get("intended") or {}
resolved    = delivery.get("resolved") or {}
fallback    = delivery.get("fallbackUsed")
session_id  = run.get("sessionId", "?")
model       = run.get("model", "?")
out_tokens  = (run.get("usage") or {}).get("output_tokens", "?")

bar = "═" * 64
print(bar)
print(f" cron: {job_name}  ({job_id})")
print(bar)

print("\n──── HOP 1: cron fired ────")
print(f"  fired at       : {ts(run_at)}")
print(f"  ended at       : {ts(end_ts)}")
print(f"  total duration : {ms(duration)}")

print("\n──── HOP 2: agent dispatched ────")
print(f"  model          : {model}")
print(f"  session id     : {session_id}")
print(f"  output tokens  : {out_tokens}")

print("\n──── HOP 3: agent reply ────")
print(f"  text           : {summary}")

print("\n──── HOP 4: BB delivery attempted ────")
print(f"  channel        : {resolved.get('channel') or intended.get('channel') or '?'}")
print(f"  to             : {resolved.get('to')      or intended.get('to')      or '?'}")
print(f"  source         : {resolved.get('source')  or intended.get('source')  or '?'}")
if fallback is not None:
    print(f"  fallback used  : {fallback}")

print("\n──── HOP 5: BB delivery result ────")
print(f"  delivered      : {delivered}")
print(f"  status         : {deliv_stat}")
if error:
    print(f"  error          : {error}")

print("\n──── outcome ────")
if status == "ok" and delivered:
    print("  ✓ PASS — agent ran, BB delivered, ack received.")
elif status == "ok" and delivered is False:
    print("  ⚠  PASS-WITH-WORKAROUND — bestEffort:true swallowed a BB error.")
    print("     iMessage probably arrived (BB sends despite slow ack), but the")
    print("     delivery layer didn't confirm in time. If Dave didn't actually")
    print("     receive the message, this is a true silent failure.")
    print("     Root cause hypothesis: identity collision (Bishop's Apple ID")
    print("     has Dave's phone). Expected to resolve once Bishop has his own")
    print("     phone number — see Bishop Identity Track.")
elif status == "error":
    print(f"  ✗ FAIL — cron run errored: {error or '(see error field)'}")
    print("     Likely causes:")
    print("       AbortError during delivery → BB API hang (apple-script method)")
    print("       timeout                    → agent exceeded payload.timeoutSeconds")
    print("       other                      → see error message above")
else:
    print(f"  ? status={status} — unexpected, inspect raw run jsonl directly")

# Gateway log peek within run window — best-effort, may have nothing.
if run_at and os.path.exists(err_log):
    print("\n──── gateway.err.log (run window) ────")
    start = datetime.fromtimestamp((run_at-2000)/1000, tz=timezone.utc).astimezone()
    end_dt = datetime.fromtimestamp((end_ts+2000)/1000, tz=timezone.utc).astimezone()
    # Build minute-prefixes spanning window
    prefixes = set()
    cur = start.replace(second=0, microsecond=0)
    while cur <= end_dt:
        prefixes.add(cur.strftime("%Y-%m-%dT%H:%M:"))
        cur = cur.replace(minute=cur.minute+1) if cur.minute < 59 else cur.replace(hour=cur.hour+1, minute=0)
    found = []
    try:
        with open(err_log, errors="ignore") as f:
            for line in f:
                if any(p in line for p in prefixes):
                    found.append(line.rstrip())
                    if len(found) >= 15: break
    except Exception:
        pass
    if found:
        for ln in found:
            print(f"  {ln}")
    else:
        print("  (no entries in window — BB call detail isn't logged for cron path)")
PYEOF
