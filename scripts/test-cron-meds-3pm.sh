#!/usr/bin/env bash
# Manually fire the medication-3pm cron now (debug/validation).
# Pass criteria: an iMessage arrives reading the 3pm meds reminder.
# Run three times consecutively for stability validation.

set -euo pipefail

JOB_ID="8850f8d3-c009-4260-b91f-6f41a4849c2a"
JOB_NAME="medication-3pm"

echo "→ firing cron: $JOB_NAME ($JOB_ID)"
openclaw cron run --timeout 90000 --expect-final "$JOB_ID"

echo ""
echo "→ trace this run:"
echo "   scripts/trace-cron.sh $JOB_NAME"
echo ""
echo "→ Pass criteria: iMessage arrives reading a 3pm meds reminder."
