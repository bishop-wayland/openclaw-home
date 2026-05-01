#!/usr/bin/env bash
# Fire the Gmail hook deliberately with a fake refurb-tracker email payload.
# Use this to test the email-alert circuit end-to-end without waiting for a real email.
#
# Usage:
#   scripts/test-email-circuit.sh           # fires a refurb-tracker forwarded email (alert branch)
#   scripts/test-email-circuit.sh queue     # fires a non-alert email (log branch → inbox-queue.md)
#
# After firing, inspect the trace with: scripts/trace-email-circuit.sh

set -euo pipefail

BRANCH="${1:-alert}"

GATEWAY_HOST="http://127.0.0.1:18789"
HOOK_PATH="/hooks/gmail"
HOOK_TOKEN=$(python3 -c 'import json;print(json.load(open("/Users/bishop/.openclaw/openclaw.json"))["hooks"]["token"])')

MSG_ID="test-$(date +%s)"

if [ "$BRANCH" = "alert" ]; then
  FROM='Dave Otte <otte.dave@gmail.com>'
  SUBJECT='Fwd: 1 new refurbished product on the Apple Store US'
  BODY=$'---------- Forwarded message ---------\nFrom: Refurb Tracker <info@refurb-tracker.com>\nDate: '"$(date)"$'\nSubject: 1 new refurbished product on the Apple Store US\nTo: <otte.dave@gmail.com>\n\nRefurbished Mac mini Apple M4 Chip — $509.00 (test fire)'
else
  FROM='Some Newsletter <hello@example.com>'
  SUBJECT='Weekly digest (test fire, queue branch)'
  BODY='Lorem ipsum non-urgent newsletter content for the queue branch test.'
fi

PAYLOAD=$(python3 -c "
import json,sys
print(json.dumps({
  'messages': [{
    'id': '$MSG_ID',
    'from': '$FROM',
    'subject': '$SUBJECT',
    'body': '''$BODY''',
    'snippet': '$SUBJECT'
  }]
}))
")

echo "→ firing hook: branch=$BRANCH msg_id=$MSG_ID"
echo "→ payload: $PAYLOAD" | head -c 200; echo "..."

curl -sS -X POST "${GATEWAY_HOST}${HOOK_PATH}" \
  -H "Content-Type: application/json" \
  -H "x-openclaw-token: ${HOOK_TOKEN}" \
  -d "$PAYLOAD" \
  | python3 -m json.tool 2>/dev/null || true

echo "→ done. To trace the run:"
echo "  scripts/trace-email-circuit.sh $MSG_ID"
