# `ynab-categorize` Skill Spec

**Spec version:** 1
**Authored:** 2026-05-04 by Dave + Claude (planning session)
**Author notes:** Dave has been hand-categorizing YNAB transactions weekly, with an evolving collection of working scripts (`ynab-autocategorize.py`, `ynab_classifier.py`, `build-merchant-lookup.py`, `merchant-lookup.json`, etc. — all in `~/.openclaw/workspace/`). The job is to absorb that work into a proper skill that runs automatically on Sundays, auto-applies known categorizations, and asks Dave to approve only the truly-new merchants. The methodology pivot in this spec vs. the existing scripts: drop the regex rules layer (it produces false-positive categorizations like "Hola House → Healthcare via 'House' pattern" when the merchant is actually a yoga studio); instead, every unknown merchant goes through web-search-then-LLM with the search context as the LLM's evidence. The lookup table (`merchant-lookup.json`) is the single source of truth — curated by Dave's approvals, not re-derived from YNAB.

## 1. Elevator pitch

Weekly automated YNAB transaction categorizer. Sunday morning cron pulls uncategorized transactions, auto-categorizes those whose payee matches an entry in `merchant-lookup.json` (the curated truth-table of merchant→category), and for new/unknown merchants does a DuckDuckGo web search + Claude Haiku categorization → puts those into a "pending approval" queue. Dave gets an email digest with full details and an iMessage with the high-level summary, the new-merchant proposals, and any LLM-surfaced anomalies. Dave replies "approve" (or "approve, but change X to Y") via iMessage; Bishop sees the reply and appends to the lookup. The newly-approved merchants then auto-apply on the next Sunday's run.

## 2. Trigger

- **Mode:** cron (primary) + on-demand
- **Schedule:** `0 9 * * 0 America/Los_Angeles` (Sundays at 9 AM PT)
- **Hook source:** N/A — no Gmail/file-watcher trigger
- **On-demand invocation:** `python3 ~/.openclaw/workspace/skills/ynab-categorize/scripts/propose.py [--dry-send] [--no-apply]`
- **Approval reply trigger:** Bishop's iMessage main session detects approval-shaped replies (regex matches on "approve" / "change <payee> to <category>") referencing the latest pending run-id, calls `scripts/apply-additions.py --run-id <id> --message "<reply text>"`. See Section 13 for routing detail.

## 3. Composes with

| Capability needed | Existing skill / tool to reuse | Reason |
|---|---|---|
| YNAB API auth | `~/.openclaw/scripts/op-ynab-key.sh` | Already returns canonical openclaw secrets-exec envelope; tested via `ynab-test.sh` |
| Anthropic API auth | `~/.openclaw/scripts/op-anthropic-key.sh` | Same envelope shape; used by job-search and ynab_classifier |
| Outbound iMessage | `openclaw message send --channel bluebubbles --target 'iMessage;-;otte.dave@gmail.com'` | Same route validated by hello-skill, paddle-board-alert, refurb-alert |
| Outbound email | `gog` (Gmail OAuth) | Same auth path job-search uses; existing token at `~/.openclaw/workspace/state/gog-token.json` |
| Per-hop JSONL logging | `paddle-board-alert/scripts/logger.py` (or `job-search/scripts/logger.py`) | Same convention used by every other skill |
| Three-fires harness | `paddle-board-alert/scripts/test.py` shape | Adapt — three dry + one real fire |

**Build new:**
- `classify.py` module — orchestrates lookup → web search → LLM call. Adapts `ynab_classifier.py` (Stages 1, 4, 5) but drops Stages 2 (regex rules) and 3 (recurring detection — folded into LLM context).
- `merchant_lookup.py` module — load/append/save the truth table.
- `digest.py` module — assemble email body and iMessage summary.
- `apply-additions.py` — separate entry point for Bishop to call on Dave's approval reply.
- `init-lookup.py` — one-shot seeder script (essentially `build-merchant-lookup.py` polished into the skill's shape, runs at install time only).

## 4. Pipeline

Each hop emits a JSONL event in `logs/run-<iso>.jsonl`. Halt-on-error policy at each hop unless noted.

| # | Hop | Input | Output | Notes |
|---|---|---|---|---|
| 1 | `triggered` | argv flags (`--dry-send`, `--no-apply`) | run_id, mode flags | Entry log line |
| 2 | `auth` | `op-ynab-key.sh` envelope, `op-anthropic-key.sh` envelope | `ynab_token`, `anthropic_key` | Halt on missing credentials |
| 3 | `fetch_categories` | `GET /budgets/{id}/categories` | `categories_by_name`, `category_names_list` | The names list becomes the LLM's valid-options whitelist |
| 4 | `fetch_uncategorized` | `GET /budgets/{id}/transactions?since_date=…` filter `category_id is None` | `uncategorized_txns[]` | Pull last 90 days only (don't reprocess ancient backlog every Sunday) |
| 5 | `load_lookup` | `state/merchant-lookup.json` | `lookup` dict | If missing, halt with clear "run init-lookup.py" error |
| 6 | `classify` | each `txn` | per-txn `{kind: "auto_apply" \| "pending_approval", category, confidence, evidence}` | See classification logic below |
| 7 | `apply_known` | `auto_apply` txns | YNAB PATCH per txn | Failure handling: structural-transfer rejection (YNAB returns 400 + "transfer cannot be categorized" or similar) → silently route to `manual_review_needed`. Skip in `--no-apply` mode. |
| 8 | `compose_digest` | classification results, apply results | email body (HTML), pending list, manual-review list | Format per Section "Digest shapes" below |
| 9 | `compose_imessage` | classification summary, pending list, anomalies | iMessage text (≤ 800 chars typically) | Includes "Of note" LLM narrator turn (one extra Haiku call) if `things_of_note_enabled` |
| 10 | `deliver_email` | digest body | gog send result | Skipped in `--dry-send`; emit `delivery_skipped` event |
| 11 | `deliver_imessage` | iMessage text | BB send result | Skipped in `--dry-send`; emit `delivery_skipped` event |
| 12 | `persist_pending` | pending-approval list, run_id | `state/pending-<run-id>.json` | So `apply-additions.py` can find it on Dave's reply |
| 13 | `done` | — | exit 0 | Final JSONL line |

### Classification logic (Hop 6 detail)

For each uncategorized transaction:

1. **Lookup hit** — payee in `merchant-lookup.json` (exact match, OR partial-key match where key is ≥ 5 chars and substring of payee, case-insensitive). → `auto_apply` with confidence 0.99 / 0.85 respectively.
2. **No lookup hit** — clean payee name (strip common prefixes like `SP `, `TST*`, `PAYPAL `; trim transaction codes; trim everything after `@`) → DuckDuckGo Instant Answer API query → assemble LLM prompt with `{cleaned_payee, raw_payee, amount, date, account, memo, recent-history-of-this-payee, web_search_results, valid_categories}` → Haiku call → parse `{category, confidence, reasoning}` from response. → `pending_approval` with whatever confidence the LLM returns.

If LLM call fails (auth error, timeout, etc.) → mark as `manual_review_needed`, no proposed category. Don't halt the run; log the error and move to next transaction.

### Digest shapes

**Email digest** (HTML, sent via gog):

```
Subject: YNAB digest — week of <YYYY-MM-DD>

YNAB CATEGORIZER — RUN <run_id>

Summary:
  Auto-categorized:        12 transactions ($438.12)
  Pending your approval:    3 new merchants (5 transactions, $234.50)
  Manual review needed:     1 transaction
  Total processed:         16 transactions

────────────────────────────────────────────────
AUTO-CATEGORIZED (already applied to YNAB):

  2026-04-29  PCC - KIRKLAND     $73.21   →  🛒 🥑 Groceries
  2026-04-30  HBO Max            $25.35   →  📺 Subscriptions
  …

────────────────────────────────────────────────
PENDING APPROVAL (NEW merchants — not yet applied):

  Zona Rosa — proposed: 🎁 Gifts (LLM, conf 0.78)
    Web context: "Boutique gift shop in downtown Kirkland, WA."
    Affected transactions:
      2026-04-22  $176.82
    Why: Web evidence + retail-shop amount range.

  Hola House — proposed: 🏥 Healthcare (LLM, conf 0.82)
    Web context: "Massage and yoga studio, Kirkland."
    Affected transactions:
      2026-04-28  $130.00
    Why: Massage therapy categorically falls under healthcare in your category list.

  …

────────────────────────────────────────────────
MANUAL REVIEW NEEDED:

  2026-04-30  Transfer : Savings → Checking   $500.00   (structural transfer; YNAB doesn't allow categorization)

────────────────────────────────────────────────
TO APPROVE PENDING MERCHANTS: reply to the iMessage thread with "approve"
or "approve, but change Zona Rosa to Recreational Equipment".

run_id: <run_id>
```

**iMessage** (≤ 800 chars typically):

```
🦞 YNAB digest, week of 2026-05-04 — full details in email.

Auto-categorized: 12 ($438.12).
Pending approval: 3 new merchants.

  1. Zona Rosa → 🎁 Gifts (boutique gift shop, Kirkland)
  2. Hola House → 🏥 Healthcare (massage + yoga studio)
  3. Hinge.co → 📺 Subscriptions (dating app, monthly billing)

Of note: Buttera Motors $730 is 3× your typical auto spend.

Reply "approve" to lock all three in, or override:
"approve, but change Hola House to Gym Classes"

run_id: <run_id>
```

## 5. Architectural commitments (LOCKED)

- **Pipeline shape:** 2 layers — `lookup` → `web + LLM`. No regex rules layer. No recurring-detection stage; recurring signal is folded into LLM context as a single field.
- **Source of truth:** `merchant-lookup.json` is the curated table. Curated only via approval flow, never re-derived from YNAB.
- **Initialization:** one-shot `scripts/init-lookup.py` seeds the table from YNAB history at install time. Already effectively done — the existing `~/.openclaw/workspace/merchant-lookup.json` (343 entries) ships with the skill as the seed file.
- **YNAB write semantics:** auto-apply happens for `auto_apply` transactions ONLY. `pending_approval` transactions stay uncategorized in YNAB until next Sunday's run picks them up via lookup hit.
- **Approval target:** approvals modify `merchant-lookup.json` only. YNAB is never touched in the approval flow.
- **Approval scope:** new merchants only (additions to lookup). v1 has no in-band mechanism to override existing lookup entries; Dave edits `merchant-lookup.json` directly when needed.
- **Output channels:** email via `gog`, iMessage via `bluebubbles`. Both fire every run.
- **LLM:** `claude-haiku-4-5` for both classification and "things of note" narrator. Anthropic API direct, not via openclaw's inference layer.
- **Web search:** DuckDuckGo Instant Answer API. Free. 5-second timeout per query. Failure does not halt classification — pass empty search context to LLM.
- **Auth:** `op-ynab-key.sh` for YNAB token; `op-anthropic-key.sh` for Anthropic key. Both already exist.
- **Cost model:** $0 for YNAB and DuckDuckGo. ~$0.005/run for LLM (5-10 new-merchant calls + 1 narrator turn at Haiku rates). Hard cap `$5/run` as runaway guard.
- **Failure semantics per hop:** `auth` halt; `fetch_*` halt; `load_lookup` halt with init message; `classify` non-halt (per-txn errors → manual_review_needed); `apply_known` non-halt (per-txn errors → manual_review_needed; structural-transfer errors silently routed without surfacing); `deliver_*` halt with explicit error event.
- **Storage:** `state/merchant-lookup.json` (curated), `state/pending-<run-id>.json` (per-run approval queue, kept until corresponding `apply-additions.py` runs OR for 30 days then auto-pruned), `logs/run-<iso>.jsonl` (per-run forensic log).
- **Unit conventions:** YNAB amounts are milli-units (×1000); display as USD-2-decimal. Dates in transactions stay as YNAB's `YYYY-MM-DD` strings. All run timestamps in ISO-8601 UTC.

## 6. Initial parameters (TUNABLE)

| Parameter | Default | Surface | Rationale |
|---|---|---|---|
| `budget_id` | `2f6bc004-22ff-4e29-be77-a8907cb1c537` (David's Budget) | `config.json` | Parameterized so kids' budget can be added later (or substituted entirely) |
| `budget_label` | `"David's Budget"` | `config.json` | Used in email subject + iMessage |
| `cron_schedule` | `"0 9 * * 0"` | `cron/jobs.json` entry | Sundays 9 AM PT; Dave's chosen weekly review cadence |
| `cron_tz` | `"America/Los_Angeles"` | same | Dave's TZ |
| `lookback_days` | `90` | `config.json` | How far back to pull uncategorized txns; trim ancient backlog |
| `llm_model` | `"claude-haiku-4-5"` | `config.json` | Cheap, plenty good for this task |
| `llm_classify_max_tokens` | `200` | `config.json` | Output is short structured response |
| `llm_narrator_enabled` | `true` | `config.json` | "Of note:" anomaly line in iMessage; tiny Haiku call. Toggle off to silence |
| `llm_narrator_max_tokens` | `150` | `config.json` | One or two short bullets |
| `max_budget_usd` | `5.0` | `config.json` | Hard runaway guard; expected actual is ~$0.005 |
| `email_recipient` | `"otte.dave@gmail.com"` | `config.json` | Email for the digest |
| `email_from_label` | `"Bishop YNAB"` | `config.json` | Sender display |
| `imessage_channel` | `"bluebubbles"` | `config.json` | Per architecture, BB is preferred over native imessage |
| `imessage_target` | `"iMessage;-;otte.dave@gmail.com"` | `config.json` | Email-keyed handle avoids identity collision |
| `web_search_provider` | `"duckduckgo"` | `config.json` | Free, no auth |
| `web_search_timeout_seconds` | `5` | `config.json` | Don't block the run for slow searches |
| `partial_match_min_key_length` | `5` | `config.json` | Lookup partial-match minimum substring length |
| `pending_approval_ttl_days` | `30` | `config.json` | Auto-prune `pending-<run-id>.json` files older than this |
| `--dry-send` flag | absent | argv | Skip both deliver hops |
| `--no-apply` flag | absent | argv | Skip YNAB PATCH hop (used by harness real fire) |

## 7. Tuning surface

- `~/.openclaw/workspace/skills/ynab-categorize/config.json` — most-edited; budget, schedule, channels, thresholds, narrator toggle
- `~/.openclaw/workspace/skills/ynab-categorize/state/merchant-lookup.json` — the curated truth table; Dave edits manually when fixing existing entries
- `~/.openclaw/workspace/skills/ynab-categorize/scripts/classify.py` — only edit to change classification logic (e.g., add a new hop, change LLM prompt)
- `~/.openclaw/cron/jobs.json` — schedule (only via `openclaw cron edit`, not direct edit)
- `--dry-send` / `--no-apply` flags — runtime overrides for one-off testing

## 8. Success criteria

**Dry fires (×3) must pass when:**
- All required hops emit JSONL events in order: `triggered → auth → fetch_categories → fetch_uncategorized → load_lookup → classify → apply_known → compose_digest → compose_imessage → deliver_email_skipped → deliver_imessage_skipped → persist_pending → done`
- No `event=error` lines (transient classify-side errors are OK as long as they're tagged with `kind=manual_review_needed` not `event=error`)
- Classification runs successfully against real YNAB data; counts of `auto_apply` + `pending_approval` + `manual_review_needed` sum to total uncategorized
- LLM classification returns a category from the live category-names list pulled in `fetch_categories` (validates the LLM honors the live whitelist)
- `state/pending-<run-id>.json` written and parseable by `apply-additions.py --run-id <id> --message "approve"` (a no-op apply during dry — verify the parsing path)

**Real fire must pass when:**
- Same event sequence as dry, EXCEPT `deliver_email_skipped` is replaced with `deliver_email_sent` (gog returns `204 No Content` or success result), and `deliver_imessage_skipped` with `delivery_imessage_sent` (BB returns success + Message ID)
- `apply_known` hop is skipped (real fire uses `--no-apply` per spec — no YNAB writes during harness)
- Email arrives at `otte.dave@gmail.com` with the digest body
- iMessage delivered to BB target with the summary text
- Run cost: under $0.10 (well below the $5 cap); record actual cost in summary log

**Bishop validation must pass when:**
- Reading `SKILL.md` tells Dave how to invoke (`python3 propose.py`), tune (`config.json`), and monitor (logs)
- Bishop can answer "what did the YNAB skill do this morning?" by reading the latest `logs/run-*.jsonl` and the latest `state/pending-*.json`
- Bishop's AGENTS.md gains a "YNAB Approval Routing" subsection telling him how to detect approval-shaped Dave replies and call `apply-additions.py` (this is the single edit to Bishop's config the build is allowed to make — see Section 13 dispatch instructions)

## 9. Cost ceiling

| | |
|---|---|
| Per-run target | $0.005 (5-10 LLM classification calls + 1 narrator call at Haiku rates) |
| Per-run hard cap | $5.00 (config-tunable; runaway guard, not expected actual) |
| Monthly projection | ~$0.02 at weekly cadence |
| Free APIs | YNAB API, DuckDuckGo Instant Answer, Gmail (gog), BlueBubbles |
| Paid APIs | Anthropic (Haiku) — ~$0.0002 per LLM call |

If estimated monthly cost exceeds $1, log a warning event in `done`. The hard cap is enforced via per-run cost accumulator that halts the run if exceeded mid-pipeline.

## 10. Logging & forensics

Log path: `~/.openclaw/workspace/skills/ynab-categorize/logs/run-<iso>.jsonl`

Required event types:

- `triggered` — `{run_id, dry_send, no_apply, argv}`
- `auth` — `{ynab_token_obtained: bool, anthropic_key_obtained: bool}` (no actual secret values)
- `fetch_categories` — `{category_count, category_names: [...]}`
- `fetch_uncategorized` — `{since_date, count, txn_ids: [...]}`
- `load_lookup` — `{path, entry_count}`
- `classify_lookup_hit` — `{txn_id, payee, category, match_type: "exact"|"partial", key}` — one per auto-apply
- `classify_web_search` — `{txn_id, payee, cleaned_payee, query, search_succeeded: bool, snippet_chars}` — one per web call
- `classify_llm_call` — `{txn_id, payee, model, input_tokens, output_tokens, cost_usd, proposed_category, confidence, reasoning_short}` — one per LLM call
- `classify_summary` — `{auto_apply: N, pending_approval: M, manual_review_needed: K, total: T}` — one per run
- `apply_known_attempt` — `{txn_id, payee, category, category_id}` — one per attempted PATCH
- `apply_known_success` — `{txn_id}` — one per successful PATCH
- `apply_known_structural_skip` — `{txn_id, payee, ynab_error_message}` — one per silent transfer skip; routed to manual_review_needed
- `apply_known_error` — `{txn_id, error}` — one per non-structural failure; also routed to manual_review_needed
- `compose_digest` — `{email_chars, html_chars}`
- `compose_imessage` — `{message_chars, narrator_text}` — narrator empty string if disabled or returned nothing
- `narrator_call` — `{model, input_tokens, output_tokens, cost_usd}` — only if `llm_narrator_enabled`
- `deliver_email_sent` / `deliver_email_skipped` — `{recipient, subject, response_status?}`
- `deliver_imessage_sent` / `deliver_imessage_skipped` — `{channel, target, bb_message_id?}`
- `persist_pending` — `{path, pending_count}`
- `cost_total` — `{cost_usd}` — one per run
- `error` — `{hop, message, traceback}` — only for non-recoverable errors that halt the run
- `done` — `{exit_status, run_id}`

## 11. Test harness expectations

`scripts/test.py` runs 3 dry + 1 real fire in sequence.

- **Dry mechanism:** `--dry-send --no-apply` flags. Skips both delivery hops AND the YNAB PATCH hop. Classification still runs (real YNAB read, real web searches, real LLM calls — minor cost incurred per dry fire).
- **Real fire:** `--no-apply` only. Delivers email + iMessage with real content; does NOT write to YNAB. The real-fire side effect is that Dave receives one email and one iMessage from the harness run. (The harness deliberately does not test the apply-known path; that gets tested separately via on-demand `propose.py` runs after Dave reviews the harness output.)
- **State reset:** harness uses a temp lookup file (`state/lookup-test.json`) seeded from the production lookup, so no test runs corrupt the curated table. `state/pending-test-*.json` files written by the harness are auto-deleted on success.
- **Real fire is final;** if any dry fire fails, real does NOT run. Test summary log at `logs/test-<iso>.jsonl`.

After harness PASS, Dave manually runs `python3 propose.py` once (no flags) to validate the apply-known path against real YNAB. That's outside the harness so the agent doesn't write to YNAB during build verification.

## 12. Known follow-ups / out of scope

**v2 candidates (deferred):**

- **Amazon disaggregation.** v1 ships with Amazon staying in the broad `📦 Household Supplies (Amazon)` bucket. v2 should tackle this — Dave's planning to pull a year of Amazon order history (CSV export from Amazon account page) and use that as ground truth to either (a) apply a historical-ratio distribution per Amazon transaction, or (b) train a simple model on `(amount, day-of-week, time, recent-purchase-history)` features, or (c) feed the order detail directly into the LLM as evidence. Decision deferred to v2 spec.
- **In-band override of existing lookup entries.** v1 only handles new-merchant approvals. If Dave wants to change "Wibbley's Burgers" from Dining→Snacks, he edits `merchant-lookup.json` manually. v2 could add iMessage syntax like "remap Wibbley's Burgers to Snacks" that the approval router handles.
- **Multi-budget support.** v1 hardcodes one budget via config (default David's). v2 could iterate over a list of budgets, separate digest per budget.
- **Lookup fuzzy match beyond simple substring.** Current partial-match rule: key (≥ 5 chars) is substring of payee. Could be smarter (Levenshtein distance, normalize whitespace/punctuation).
- **Show transaction-level overrides in approval reply.** v1 approval applies to all transactions of a newly-approved merchant. v2 could allow "approve Zona Rosa, but the 2026-04-22 one specifically should be Gifts and the 2026-04-25 one should be Dining" — overrides per transaction, not per merchant.

**Out of scope for v1 (won't be built):**

- Replacing manual YNAB editing of bad lookup entries with a UI.
- Auto-detecting recurring transactions and pre-populating a "Subscriptions" cluster (LLM is good enough at this with the recent-history field).
- Web search providers other than DuckDuckGo Instant Answer.
- LLM models other than Haiku (cost stays trivially low; smarter models offer marginal classification gain at 10-20× the cost).

## 13. Dispatch instructions for the skills-agent

This skill is built by the registered OpenClaw `skills-agent` sub-agent (per `agents.list[].id: "skills-agent"`). Bishop spawns it via `sessions_spawn(agentId: "skills-agent", task: ...)`. The worker runs in its own workspace at `~/.openclaw/workspace-skills-agent/` with `tools.fs.workspaceOnly: true` enforcing path containment.

### What Bishop pre-stages (before spawning)

Bishop copies these into the worker's workspace at dispatch time. Worker sees them at `./<filename>` relative to its workspace root.

| Source | Worker-side path | Reason |
|---|---|---|
| `~/.openclaw/workspace/skills/skill-builder/*` | `./skill-builder/` | Methodology pack — worker reads SKILL.md, METHODOLOGY.md, DECISION_POINTS.md as Step 1 |
| `~/.openclaw/specs/ynab-categorize.md` | `./spec.md` | This spec |
| `~/.openclaw/workspace/merchant-lookup.json` | `./merchant-lookup.json` | The 343-entry seed table per §3 "Composes with" — worker uses this as `./state/merchant-lookup.json` in the skill it builds |
| `~/.openclaw/workspace/skills/job-search/scripts/{logger.py, deliver.py, test.py}` | `./compose-refs/job-search/scripts/{...}` | Reference patterns the worker reads for compose-first reuse |
| `~/.openclaw/workspace/skills/paddle-board-alert/scripts/deliver.py` | `./compose-refs/paddle-board-alert/scripts/deliver.py` | BB iMessage send pattern reference |
| `~/.openclaw/workspace/ynab_classifier.py` and `~/.openclaw/workspace/ynab-autocategorize.py` | `./compose-refs/ynab_classifier.py` and `./compose-refs/ynab-autocategorize.py` | Adaptation sources per "Composition reuse priority" below |
| `~/.openclaw/workspace/build-merchant-lookup.py` | `./compose-refs/build-merchant-lookup.py` | Becomes `scripts/init-lookup.py` with light polish |

### What the worker does

1. Read `./skill-builder/SKILL.md` and the docs it points to (METHODOLOGY.md, DECISION_POINTS.md).
2. Read `./spec.md` (this spec) in full.
3. Execute the build per `METHODOLOGY.md` step sequence, scaffolding into `./skills/ynab-categorize/`.
4. Pull the seed lookup table into the new skill: `cp ./merchant-lookup.json ./skills/ynab-categorize/state/merchant-lookup.json`. **Do NOT run init-lookup.py during the build** — the seed copy is the initialization. The init script ships in the skill but is invoked by Dave manually if he ever wants to wipe and rebuild.
5. **Do NOT install the cron schedule.** Write `scripts/install-cron.sh` as a one-shot installer (mirror `paddle-board-alert/scripts/install-cron.sh` shape). Dave will run it manually after reviewing the build.
6. Run the three-fires harness per METHODOLOGY §"Three-fires harness". Real-fire deliveries (email digest + iMessage summary) MUST be marked `[TEST FIRE]` in subject/body with a `(skill harness, ignore)` tail per METHODOLOGY Fix B.
7. **Output handoff:** copy the completed skill from your workspace to Bishop's:
   ```bash
   cp -r ./skills/ynab-categorize/ /Users/bishop/.openclaw/workspace/skills/ynab-categorize/
   ```
8. Write `./skills/ynab-categorize/BUILD-SUMMARY.md` (also handed off via the cp above) per METHODOLOGY Step 8.
9. **Write `./skills/ynab-categorize/SETUP.md`** containing the YNAB Approval Routing snippet (see below). This is the manual post-build step Dave applies to Bishop's `~/.openclaw/workspace/AGENTS.md` after reviewing the build.
10. Emit a substantive final assistant text — the OpenClaw runtime announce auto-delivers it to Bishop's session. Reference the SETUP.md path so Bishop can relay it to Dave. **Do NOT call `openclaw message send`** — runtime handles delivery; the `message` tool is denied for this agent anyway.

### Forbidden

- `ANNOUNCE_SKIP`, `NO_REPLY`, or `no_reply` as final assistant text — these tokens suppress the announce.
- Any modification to Bishop's `~/.openclaw/workspace/AGENTS.md`, `cron/jobs.json`, or top-level openclaw config. The YNAB Approval Routing section is delivered via `SETUP.md` for Dave to apply manually.
- Running a real fire before three consecutive clean dry fires.

### `SETUP.md` content (worker writes this verbatim)

```markdown
# Post-build setup for ynab-categorize

After Dave reviews the build and is ready to enable approval routing, add the following section to `~/.openclaw/workspace/AGENTS.md`, after the existing "Skills-Agent Dispatch" / "Active Dispatches" sections.

---

## YNAB Approval Routing

Sundays after 9 AM PT, the `ynab-categorize` skill fires its weekly cron and sends Dave both an email digest and an iMessage with new-merchant approval prompts. When Dave replies via iMessage, you (Bishop) detect the approval-shaped reply and trigger the apply-additions step.

**Detect:** Dave's iMessage reply matches if it contains `approve` (case-insensitive) AND references a YNAB run-id (the `run_id` is in the iMessage you sent — pull from `~/.openclaw/workspace/skills/ynab-categorize/state/pending-*.json` to find the most recent unapplied run).

**On match:**
1. Find the pending file: `ls -t ~/.openclaw/workspace/skills/ynab-categorize/state/pending-*.json | head -1`. Read its `run_id`.
2. Call: `python3 ~/.openclaw/workspace/skills/ynab-categorize/scripts/apply-additions.py --run-id <run_id> --message "<Dave's reply text>"`
3. The script parses the reply (handles "approve", "approve, but change X to Y", "approve all except Y"), appends to `state/merchant-lookup.json`, and emits a confirmation iMessage with the diff.
4. Relay the script's output to Dave (or let the script's own iMessage stand if it's clear).

**On no-match:** treat the reply as conversational; respond normally.

**Don't:** auto-retry on failure (e.g., script error, malformed reply). Surface the error to Dave and ask what he wants.

---

After adding the section, restart the gateway: `openclaw gateway restart`. Then the next Sunday cron fire will deliver the digest with approval prompts, and Dave's iMessage replies will route through this section.
```

### Composition reuse priority

The worker should read these (in `./compose-refs/`) before scaffolding any module:

1. `./compose-refs/job-search/scripts/logger.py` and `test.py` — logging convention + harness shape
2. `./compose-refs/job-search/scripts/deliver.py` — gog email send pattern
3. `./compose-refs/paddle-board-alert/scripts/deliver.py` — BB iMessage send pattern (structurally simpler than alert-circuit's announce path)
4. `./compose-refs/ynab_classifier.py` (Stages 1, 4, 5 — copy-and-adapt the lookup, web enrichment, and LLM logic; **drop** Stages 2 and 3)
5. `./compose-refs/ynab-autocategorize.py` — auth pattern, YNAB GET/PATCH client, the `categories_by_name` build (keep these; **drop** the RULES list and SKIP_PATTERNS list per Section 5)
6. `./compose-refs/build-merchant-lookup.py` — becomes `scripts/init-lookup.py` with light polish

The worker should NOT copy `ynab-autocategorize.py`'s RULES list or SKIP_PATTERNS list — those are explicitly removed from the architecture per Section 5.

### Build identity

`skill-build-ynab-categorize-<YYYYMMDD>-<HHMM>` (Bishop generates at dispatch time).

### Skill destination (post-handoff)

`~/.openclaw/workspace/skills/ynab-categorize/`

### Source location during build

`~/.openclaw/workspace-skills-agent/skills/ynab-categorize/` — this is where the worker scaffolds before the exec-copy handoff.

---

## Author's notes

- Dave has been hand-curating `merchant-lookup.json` for several weeks via his earlier scripts. The 343 entries it currently contains are GOOD — they reflect Dave's actual categorization preferences. Treat the seed file as authoritative ground truth for the initial state.
- The two existing scripts (`ynab-autocategorize.py` and `ynab_classifier.py`) represent two different design philosophies. The skill takes the better parts of each: from `ynab-autocategorize.py` keep the auth + YNAB client + categories-by-name build + dry-run/apply pattern; from `ynab_classifier.py` keep the lookup logic (Stage 1) + payee cleaning + web enrichment (Stage 4) + LLM arbitration (Stage 5). The regex rules from `ynab-autocategorize.py` and the recurring-detection from `ynab_classifier.py` are explicitly dropped.
- This is the first skill to compose with `gog` for outbound email. The agent should read `job-search/scripts/deliver.py` carefully — that's the validated reference for sending HTML email via gog with proper auth fetching.
- After dispatch, the worker reports back to Bishop via the OpenClaw runtime announce mechanism (push-based, runtime-derived Status). Bishop relays the announce body to Dave in his own voice. Dave should expect during the build: (a) one `[TEST FIRE]` iMessage from the harness real fire (sample digest content, sample run_id), (b) one `[TEST FIRE]` email from the harness real fire (same), (c) one Bishop iMessage relaying the build's completion summary. Total: 2 messages from the skill (harness real fire) + 1 from Bishop (announce relay). Production cron runs from the installed skill are separate and unmarked.
- The build cost (worker tokens) should be ~$1-3 — comparable to job-search Phase 1+2 build. The skill itself runs at ~$0.005/run in production.
