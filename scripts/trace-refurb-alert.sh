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
echo "════════ HOP 3: agent reply (should be the alert text) ════════"
LATEST_SESSION=$(ls -t $SESSIONS_DIR/*.jsonl 2>/dev/null | xargs grep -l "refurb-alert" 2>/dev/null | head -1 || true)
if [ -n "$LATEST_SESSION" ]; then
  echo "session: $LATEST_SESSION"
  grep -oE '"role":"assistant"[^}]*"text":"[^"]*"' "$LATEST_SESSION" | tail -3
  echo ""
  echo "tool calls (should be ZERO for clean delivery):"
  grep -oE '"name":"[a-z_]+","arguments"' "$LATEST_SESSION" | tail -5 || echo "(none)"
else
  echo "(no recent session found for refurb-alert)"
fi

echo ""
echo "════════ HOP 4: BlueBubbles delivery ════════"
grep -E "chat\.send" "$GATEWAY_LOG" | tail -3 || true

echo ""
echo "════════ summary ════════"
echo "PASS: HOP 3 shows ONLY the alert text (no narration, zero tool calls) AND HOP 4 shows a chat.send."
echo "If agent narrated or called tools: messageTemplate is being read as instructions — verify it's pure data."
echo "If chat.send missing: tool call suppression. Check for any tool calls in HOP 3."
