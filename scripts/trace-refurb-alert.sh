#!/usr/bin/env bash
# Forensic trace for the refurb-alert circuit.
# Usage: scripts/trace-refurb-alert.sh [<msg_id>]

set -euo pipefail
MSG_ID="${1:-}"

GATEWAY_LOG=/Users/bishop/.openclaw/logs/gateway.log
SESSIONS_DIR=/Users/bishop/.openclaw/agents/main/sessions

echo "════════ HOP 1: webhook received ════════"
if [ -n "$MSG_ID" ]; then
  grep -F "$MSG_ID" "$GATEWAY_LOG" | tail -10 || echo "(no entries for $MSG_ID)"
else
  grep -E "gmail-alert-refurb|hook:refurb-alert" "$GATEWAY_LOG" | tail -5
fi

echo ""
echo "════════ HOP 2: hook dispatched ════════"
grep -E "gmail-alert-refurb|Refurb Mac mini" "$GATEWAY_LOG" | tail -5 || true

echo ""
echo "════════ HOP 3: transform invoked + BB call ════════"
# Transforms log via console.log to gateway.log (NOT gateway.err.log).
# Look for the transform's tagged log lines in the most recent fire.
grep "refurb-alert-transform" "$GATEWAY_LOG" | tail -8 || echo "(no transform log entries — transform may not have fired)"

echo ""
echo "════════ HOP 4: BB response status ════════"
grep "refurb-alert-transform.*status=" "$GATEWAY_LOG" | tail -3 || true

echo ""
echo "════════ summary ════════"
echo "PASS: HOP 3 shows POST + body + response status=200 + 'delivered tempGuid=...'"
echo "FAIL: BB returned 500 → likely identity collision on phone-keyed thread (resolved by"
echo "      using email-keyed chatGuid, which the transform does)."
echo "FAIL: HOP 3 empty → transform not loading (check hooks.transformsDir + module exists)."
