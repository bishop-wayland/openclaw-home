#!/usr/bin/env bash
# Test-fire the refurb Mac mini alert circuit.
# Run three times consecutively and confirm an iMessage arrives each time before declaring stable.

set -euo pipefail

GATEWAY_HOST="http://127.0.0.1:18789"
HOOK_PATH="/hooks/gmail-alert-refurb"
HOOK_TOKEN=$(python3 -c 'import json;print(json.load(open("/Users/bishop/.openclaw/openclaw.json"))["hooks"]["token"])')

MSG_ID="test-refurb-$(date +%s)"

PAYLOAD=$(python3 -c "
import json
print(json.dumps({
  'messages': [{
    'id': '$MSG_ID',
    'from': 'Refurb Tracker <info@refurb-tracker.com>',
    'subject': '1 new refurbished product on the Apple Store US',
    'body': 'Refurbished Mac mini Apple M4 Chip — \$509.00 (test fire)',
    'snippet': '1 new refurbished product on the Apple Store US'
  }]
}))
")

echo "→ firing hook: $HOOK_PATH msg_id=$MSG_ID"

curl -sS -X POST "${GATEWAY_HOST}${HOOK_PATH}" \
  -H "Content-Type: application/json" \
  -H "x-openclaw-token: ${HOOK_TOKEN}" \
  -d "$PAYLOAD" \
  | python3 -m json.tool 2>/dev/null || true

echo ""
echo "→ Wait ~10 sec, then trace:"
echo "  scripts/trace-refurb-alert.sh $MSG_ID"
echo ""
echo "→ Pass criteria: iMessage arrives reading:"
echo "  🚨 Mac mini alert: 1 new refurbished product on the Apple Store US → https://www.apple.com/shop/refurbished/mac/mac-mini"
