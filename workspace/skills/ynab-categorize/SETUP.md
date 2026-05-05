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

## Amount-Rule Entry

Dave can add fixed-amount categorization rules via iMessage. Use case: recurring
fixed-dollar transactions whose payee text varies (spousal-support check, fixed-rate
subscription, etc.) — same amount every cycle but the bank's payee text shifts.

### Detect

Dave's iMessage matches if it contains `remember` or `always` followed by a dollar
amount and a separator (`=`, `→`, `->`, `means`, or `as`).

Regex: `(?i)\b(?:remember|always)\b\s+\$?(-?\d+(?:\.\d+)?)\s*(?:=|→|->|means|as)\s+(.+?)$`

Examples:
- "remember $-2500.00 = 💰 Spousal Support"
- "remember $500 means 🛒 🥑 Groceries"
- "always $-100.00 → 📺 Subscriptions (Netflix, Strava, WSJ, etc.)"

### On Match

Call:
```
python3 ~/.openclaw/workspace/skills/ynab-categorize/scripts/apply-amount-rule.py --message "<Dave's text>"
```

The script will:
- Validate the amount is parseable
- Validate the category exactly matches a YNAB category name (fetches live from YNAB API)
- Append the rule to `state/amount-lookup.json`
- Send Dave a confirmation iMessage

### Conflict policy

- Same amount + same category already exists → silent no-op + confirmation iMessage
- Same amount + DIFFERENT category → REJECT with explanation; instruct Dave to edit
  `state/amount-lookup.json` directly to replace

### On No-Match

Treat the message as normal conversation. Respond as appropriate.

### Important Notes

- **No run-id needed:** Amount rules are global, not run-scoped.
- **Category must be exact:** The script fetches YNAB's live category list and rejects
  fuzzy matches. If Dave uses an emoji-prefixed category, he must include the emoji.
- **Don't auto-retry:** If the script fails, surface the error to Dave and ask what
  he wants. Don't silently re-run.
