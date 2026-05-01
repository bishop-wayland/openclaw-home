#!/usr/bin/env bash
# Manually fire the winddown-9pm cron now (debug/validation).
# Pass criteria: an iMessage arrives with a wind-down check-in.
# Run three times consecutively for stability validation.

set -euo pipefail

JOB_ID="ffa870ad-88ea-4847-a6b1-e3fc3dae642e"
JOB_NAME="winddown-9pm"

echo "→ firing cron: $JOB_NAME ($JOB_ID)"
openclaw cron run --timeout 90000 --expect-final "$JOB_ID"

echo ""
echo "→ trace this run:"
echo "   scripts/trace-cron.sh $JOB_NAME"
echo ""
echo "→ Pass criteria: iMessage arrives with an evening wind-down check-in."
