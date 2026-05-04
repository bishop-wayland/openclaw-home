---
name: ynab-categorize
version: "1.0"
description: Weekly automated YNAB transaction categorizer. Pulls uncategorized transactions, auto-applies known merchants from lookup table, and surfaces new merchants for Dave's approval via email digest + iMessage.
triggers:
  - cron: "0 9 * * 0 America/Los_Angeles" (Sundays 9 AM PT)
  - manual: python3 scripts/propose.py [--dry-send] [--no-apply]
outputs:
  - email: HTML digest with auto-applied, pending approval, and manual review sections
  - iMessage: Summary with new-merchant approval prompts
dependencies:
  - YNAB API token (via 1Password)
  - Anthropic API key (via 1Password)
  - gog (Gmail OAuth for email delivery)
  - BlueBubbles (iMessage delivery)
composes_with:
  - job-search (JSONL logger, test harness pattern)
  - paddle-board-alert (BlueBubbles iMessage delivery)
  - gog (Gmail OAuth email delivery)
lifecycle:
  - Cron fires on schedule (default Sunday 9 AM PT)
  - Pulls uncategorized transactions from YNAB (last 90 days)
  - Classifies each:
    1. Lookup hit → auto_apply (confident, no approval needed)
    2. Web search + LLM → pending_approval (new merchant, needs Dave's OK)
    3. LLM failure → manual_review_needed (timeout, parse error, etc.)
  - Auto-applies confirmed merchants to YNAB (in live mode)
  - Sends email digest + iMessage with approval prompts
  - On Dave's iMessage reply containing "approve", calls apply-additions.py to lock in new merchants
state:
  - merchant-lookup.json: curated truth table of merchant → category mappings (343+ entries)
  - pending-<run-id>.json: per-run approval queue (auto-pruned after 30 days)
---

# ynab-categorize

Weekly automated transaction categorizer for Dave's YNAB budget. Reduces manual categorization work to just approving new merchants.

## When Dave invokes Bishop

**Check the status:** "How many transactions did YNAB categorize last Sunday?"
→ Bishop reads `logs/run-*.jsonl` and the latest `state/pending-*.json` to answer.

**Run now:** "Categorize the budget right now."
→ Bishop runs `python3 ~/.openclaw/workspace/skills/ynab-categorize/scripts/propose.py`

**Tune the schedule:** "Move the weekly run to Thursday at 8 AM."
→ Dave edits `~/.openclaw/cron/jobs.json`, changes the schedule, and Bishop reloads cron.

**Tune the lookup:** "Remove 'Wibbley's Burgers' from Dining; make it Snacks."
→ Dave edits `~/.openclaw/workspace/skills/ynab-categorize/state/merchant-lookup.json` directly.

**Toggle the narrator:** "Stop sending the 'Of note' anomalies in the iMessage."
→ Dave edits `config.json`, sets `llm_narrator_enabled: false`.

**Approve pending merchants:** (automatic)
→ Dave replies to the iMessage with "approve" or "approve, but change X to Y"
→ Bishop detects the reply and runs `apply-additions.py`
→ New merchants are locked into the lookup

## Files and tuning points

- **config.json** — budget ID, schedule, LLM model, email/iMessage targets, thresholds
- **state/merchant-lookup.json** — the curated truth table (343+ entries); Dave edits manually to override
- **scripts/propose.py** — main pipeline; edit only to change classification logic
- **scripts/classify.py** — web search + LLM arbitration; where the magic happens

## Cost

- **Per-run:** ~$0.005 (5-10 LLM classification calls at Haiku rates)
- **Monthly:** ~$0.02 (weekly cadence)
- **Hard cap:** $5.00/run (config-tunable runaway guard)
- **Free APIs:** YNAB, DuckDuckGo, Gmail, BlueBubbles

## Install

```bash
bash ~/.openclaw/workspace/skills/ynab-categorize/scripts/install.sh
```

This registers the cron in **preview mode** (--no-apply, no YNAB writes) and runs one preview fire. After Dave reviews the output and replies "go", Bishop runs:

```bash
bash ~/.openclaw/workspace/skills/ynab-categorize/scripts/enable-live.sh
```

Then the next Sunday cron fire will commit real YNAB writes.

## Rollback

If something goes wrong:

```bash
bash ~/.openclaw/workspace/skills/ynab-categorize/scripts/disable-live.sh
```

This re-adds the `--no-apply` flag, reverting to preview mode. Next fire is safe.
