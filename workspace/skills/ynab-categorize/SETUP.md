## YNAB Approval Routing

When the `ynab-categorize` skill fires on Sunday mornings, it sends Dave:
1. An email digest with auto-categorized, pending-approval, and manual-review sections
2. An iMessage with a summary and approval prompts for new merchants

If Dave replies via iMessage with an approval-shaped message, you (Bishop) should detect it and trigger the approval handler.

### Detect

Dave's iMessage reply matches if it contains the word `approve` (case-insensitive) AND references a YNAB run-id. The run-id is embedded in both the email and iMessage you sent.

Examples:
- "approve"
- "approve, but change Zona Rosa to Gifts"
- "approve all except Hola House"

### On Match

1. Find the most recent pending file: `ls -t ~/.openclaw/workspace/skills/ynab-categorize/state/pending-*.json | head -1`
2. Extract the run-id from the filename (format: `pending-<run-id>.json`)
3. Call: `python3 ~/.openclaw/workspace/skills/ynab-categorize/scripts/apply-additions.py --run-id <run-id> --message "<Dave's reply text>"`

The script will:
- Parse Dave's reply (handles "approve", "change X to Y", "approve all except Y")
- Append new merchants to `~/.openclaw/workspace/skills/ynab-categorize/state/merchant-lookup.json`
- Send Dave a confirmation iMessage with the diff
- Exit cleanly (always succeeds; failures surface to Dave for manual correction)

### On No-Match

Treat the reply as normal conversation. Respond as appropriate.

### Important Notes

- **Safe regardless of live/preview state:** The approval routing only writes to `merchant-lookup.json` (the curated truth table), never to YNAB. It's harmless to approve pending merchants even if the cron is in preview mode (--no-apply).
- **Don't auto-retry:** If `apply-additions.py` fails (e.g., malformed reply, file not found), surface the error to Dave and ask what he wants. Don't silently re-run.
- **Approval text is Dave's:** The exact wording of "change X to Y" is Dave's choice. The parser is lenient and handles common phrasings.
