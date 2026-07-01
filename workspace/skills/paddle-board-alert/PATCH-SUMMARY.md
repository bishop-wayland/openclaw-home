# PATCH-SUMMARY.md — skill-patch-paddle-board-alert-20260630-2035

**Patch identity:** `skill-patch-paddle-board-alert-20260630-2035`
**Applied:** 2026-06-30 (harness run: 2026-07-01T03:39Z)
**Mode:** patch

---

## What changed and why

### 1. `scripts/deliver.py` — reviewed; no changes needed

The unsanctioned prior attempt had already correctly converted delivery from BlueBubbles HTTP POST to `imsg send --to "+16508239528" --text "<message>"` CLI subprocess. The conversion handles `FileNotFoundError` (imsg not installed) and `subprocess.TimeoutExpired` as distinct cases, and returns the `(ok: bool, detail: dict)` shape `check.py`'s `deliver_or_suppress` expects. Treated as an unverified draft per spec; verified correct on review.

### 2. `scripts/check.py` — two stale BB references fixed

- `f"BB delivery failed: {detail}"` → `f"imsg delivery failed: {detail}"`
- `bb_response_status=detail.get("status")` → `send_status=detail.get("status")`

Real-fire log confirms `send_status: 0` is emitted correctly.

### 3. `SKILL.md` — all BlueBubbles mechanism references updated

Six targeted edits across:
- **Frontmatter description** — "BB-direct flavor" → "imsg-CLI flavor"; dropped "same chatGuid" from alert-circuit compose note (chatGuid was BB-specific).
- **Step 4 description** — removed BlueBubbles HTTP POST / chatGuid details; replaced with `imsg send --to "+16508239528"` CLI description.
- **"Why this skill diverges" section** — "BB-direct POST" → "imsg-CLI send"; replaced the chatGuid invariant paragraph (see note below).
- **File map** — `deliver.py` row updated to describe imsg CLI.
- **"Composes with" section** — removed BlueBubbles entry; added imsg entry; removed chatGuid mention from alert-circuit entry.
- **Cost section** — "BB delivery is free" → "imsg delivery is free".

Historical/explanatory references to "BlueBubbles" were retained where they provide context (e.g., "replaced BlueBubbles 2026-06-30", "the old email-keyed chatGuid invariant was BlueBubbles-era").

### 4. `scripts/install-cron.sh` — cron_message prose updated

The Haiku-facing message text said "delivering the iMessage to Dave directly via BlueBubbles." Updated to "via the imsg CLI."

**Note:** `install-cron.sh` still contains `"channel": "bluebubbles"` in the `failureAlert` block. This is the jobs.json failure-notification channel (fires if the cron turn errors). BlueBubbles deprecation means this alert won't reach Dave if the cron fails. This is a follow-up item — not in scope for this patch, but flagged for a future pass (likely update to `"channel": "imsg"` with the correct field shape).

---

## Architectural invariant reversal

**Old invariant (BlueBubbles-era):** Never use phone-keyed sends; always use email-keyed chatGuid (`iMessage;-;otte.dave@gmail.com`). Rationale: Bishop's Apple ID had Dave's phone number on it, creating Apple ID collision risk.

**New state:** Phone-keyed sends (`+16508239528`) are correct and safe. Bishop has migrated to his own Apple ID (`+1-425-436-8004`), eliminating the collision risk. `imsg` sends by phone number, not chatGuid. This reversal is noted explicitly in SKILL.md's "Why this skill diverges" section.

---

## Three-fires harness results

**Run:** 2026-07-01T03:39Z  
**Result:** PASS — 3 dry + 1 real, all clean

**Real fire outcome:** GO-DAY — delivery actually exercised.  
- Max wind in 6–9 AM window: **6.0 mph** (threshold: 8.0 mph)  
- iMessage sent: `"☀️ Good paddle morning, Dave — wind staying under 8 mph through the 6–9 AM window at Waverly Park, Kirkland WA. Max forecast: 6.0 mph."`  
- `send_status: 0` confirmed in log.

Bishop should verify the iMessage landed on Dave's phone (independent confirmation that imsg CLI is wired correctly in the Mac Mini environment).

---

## [TEST FIRE] prefix gap

The harness's real fire sends the production message with no `[TEST FIRE]` marker — the harness passes `--real-send` directly to `check.py` which uses the unmodified `message_template` from `config.json`. Adding a prefix would require threading a `--message-prefix` flag through `check.py` and `test.py` (more than a one-line addition). Per spec §11, this is noted as a gap and not blocking this patch. Follow-up: add `--test-fire` flag to `check.py` in a future patch.

---

## State files

This skill is stateless — no `state/` directory exists, no dedup store, no SQLite db. Confirmed still true: no state files were created by this patch. Each daily check remains fully independent.

---

## Files changed

| File | Change |
|---|---|
| `scripts/check.py` | Fixed BB error message + log field name |
| `SKILL.md` | Removed all BB mechanism references (6 edits) |
| `scripts/install-cron.sh` | Fixed BB mention in cron_message prose |
| `scripts/deliver.py` | No changes (reviewed; already correct) |
| `PATCH-SUMMARY.md` | Created (this file) |
