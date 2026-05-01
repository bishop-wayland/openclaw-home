#!/usr/bin/env bash
# Pull the per-hop forensic trace for an email-circuit run.
# Usage: scripts/trace-email-circuit.sh [<msg_id>]
#   With <msg_id>: trace the specific run.
#   Without: trace the most recent gmail hook run.

set -euo pipefail
MSG_ID="${1:-}"

GATEWAY_LOG=/Users/bishop/.openclaw/logs/gateway.log
SESSIONS_DIR=/Users/bishop/.openclaw/agents/main/sessions
INBOX_QUEUE=/Users/bishop/.openclaw/workspace/memory/inbox-queue.md

echo "════════ HOP 1: webhook received (gateway log) ════════"
if [ -n "$MSG_ID" ]; then
  grep -F "$MSG_ID" "$GATEWAY_LOG" | tail -10 || echo "(no entries for msg_id=$MSG_ID)"
else
  grep -E "hooks/gmail|hook:gmail" "$GATEWAY_LOG" | tail -5
fi

echo ""
echo "════════ HOP 2: hook mapping selected + agent dispatched ════════"
grep -E "hook.dispatch|mapping.*Gmail|hook:gmail.*started" "$GATEWAY_LOG" | tail -5 || true

echo ""
echo "════════ HOP 3: agent decision (which branch + tool calls) ════════"
# Find most recent hook session jsonl
LATEST_HOOK_SESSION=$(ls -t $SESSIONS_DIR/*.jsonl 2>/dev/null | xargs grep -l "hook:gmail" 2>/dev/null | head -1 || true)
if [ -n "$LATEST_HOOK_SESSION" ]; then
  echo "session: $LATEST_HOOK_SESSION"
  grep -oE '"role":"assistant"[^}]*"text":"[^"]*"|"name":"[a-z_]+","arguments"' "$LATEST_HOOK_SESSION" | head -10
else
  echo "(no recent hook session found)"
fi

echo ""
echo "════════ HOP 4: channel delivery (chat.send to BlueBubbles) ════════"
grep -E "chat\.send|bluebubbles.*send|deliver" "$GATEWAY_LOG" | tail -5 || true

echo ""
echo "════════ inbox-queue.md (if log branch fired) ════════"
tail -3 "$INBOX_QUEUE" 2>/dev/null || echo "(no inbox-queue.md)"

echo ""
echo "════════ summary ════════"
echo "ALERT BRANCH succeeded if: HOP 3 shows assistant emitted the 🚨 line and HOP 4 shows a chat.send."
echo "LOG BRANCH succeeded if:   HOP 3 shows a write tool call and inbox-queue.md got a new line."
