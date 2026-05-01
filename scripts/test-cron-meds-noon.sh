#!/usr/bin/env bash
# Manually fire the medication-noon cron now (debug/validation).
# Pass criteria: an iMessage arrives reading the noon meds reminder.
# Run three times consecutively for stability validation.

set -euo pipefail

JOB_ID="f7d6780a-79d4-43ea-983e-45198fa68f58"
JOB_NAME="medication-noon"

echo "→ firing cron: $JOB_NAME ($JOB_ID)"
openclaw cron run --timeout 90000 --expect-final "$JOB_ID"

echo ""
echo "→ trace this run:"
echo "   scripts/trace-cron.sh $JOB_NAME"
echo ""
echo "→ Pass criteria: iMessage arrives reading a noon meds reminder."
