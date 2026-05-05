# `ynab-categorize` Patch Spec — amount-based categorization

**Spec version:** 1
**Mode:** patch
**Derive from:** null (not applicable in patch mode)
**Authored:** 2026-05-04 by Dave + Claude (planning session)
**Author notes:** Adds two related capabilities. (1) Classification fallback: when payee lookup fails, check whether the transaction amount matches a known amount-rule before falling through to the LLM call. Use case: recurring fixed-dollar transactions whose payee text varies (spousal-support check, fixed-rate subscription, monthly rent — same amount every cycle but the bank's payee text shifts). (2) iMessage syntax for adding rules: Dave can send "remember $-2500.00 = Spousal Support" and Bishop appends it to `state/amount-lookup.json` via a new `apply-amount-rule.py` script. Parallel to the existing merchant-approval routing.

## 1. Elevator pitch

**Two new capabilities, one patch:**

(1) **Classifier fallback.** Insert an "amount-rule check" between Step 1 (payee lookup) and Step 2 (web+LLM) in `classify.py`'s `classify_transaction`. If the transaction amount (in dollars) matches an entry in `state/amount-lookup.json` (within configurable tolerance, default 0.0 = exact), return as `auto_apply` with the rule's category. Otherwise fall through to the existing LLM path. New event `classify_amount_hit` joins `classify_lookup_hit` and `classify_llm_call`/`classify_error` as the per-txn classification outcomes.

(2) **iMessage rule entry.** New script `apply-amount-rule.py` parses an iMessage like "remember $-2500.00 = Spousal Support" (also accepts `means`, `as`, `→`, `->` as the separator) into a `{amount, category, note}` rule and appends to `state/amount-lookup.json`. Validates the amount is parseable and the category matches an existing YNAB category. Bishop's AGENTS.md gains a new "Amount-Rule Entry" routing section (delivered via `AGENTS-ADDENDUM.md` for Bishop to apply post-announce — patch mode doesn't re-run install.sh).

## 4. Pipeline (only affected hops)

| Hop | Change |
|---|---|
| 5 (load_lookup) | Also load `state/amount-lookup.json` via the new `amount_lookup.load_amount_rules()` helper. New JSONL event: `load_amount_lookup` with `{path, entry_count, version}`. If the file is missing, log the event with `entry_count: 0` and proceed (don't halt — empty rules is a valid steady state). If the file exists but JSON is malformed, halt with `error` event (preserve loud failure on schema corruption). |
| 6 (classify) | `classify_transaction` gains a Step 1.5 between the existing payee-lookup branch and the LLM call. Pass `amount_rules` as a new keyword arg from propose.py. On amount match: emit `classify_amount_hit` event (`{txn_id, payee, amount, matched_category, rule_note}`) and return the auto_apply dict. On no amount match: fall through to existing LLM path unchanged. |

All other hops: unchanged. Apply hop, deliver hops, persist hops are untouched.

## 5. Architectural commitments (LOCKED)

- **Storage backend for amount rules:** flat JSON file at `state/amount-lookup.json`. Same shape pattern as `state/merchant-lookup.json`. No SQLite, no DB.
- **Match semantics for v1:** exact amount match (tolerance 0.0). Dollar comparison after dividing YNAB millicent value by 1000.0.
- **Order of precedence:** payee-lookup wins over amount-lookup. Amount-lookup is a fallback when payee match fails. (Rationale: payee match is Dave's curated truth; amount match is a heuristic. v2 may invert if the conflict comes up in practice; not v1.)
- **Module organization:** new module `scripts/amount_lookup.py` with `load_amount_rules(path)` and `match_amount(amount, rules, tolerance)`. Mirror `scripts/merchant_lookup.py`'s shape. Don't merge into merchant_lookup.py — different schema, different match logic, separate concerns.
- **Approval flow extension:** parallel to merchant-approval, NOT integrated. Existing "approve" routing (for new merchants in the run-scoped pending file) is unchanged. NEW routing for amount rules: Dave's iMessage matches the regex `(?i)\bremember\b\s+\$?(-?\d+(?:\.\d+)?)\s*(?:=|→|->|means|as)\s+(.+?)$` (also accepts `always` as a synonym for `remember`). The match isn't run-scoped (no run_id needed) — amount rules are global. Bishop calls `scripts/apply-amount-rule.py --message "<reply text>"`.
- **Conflict policy on existing amount:** if the parsed amount already exists in `amount-lookup.json` with a DIFFERENT category, the script REJECTS with an iMessage telling Dave the existing mapping and instructing him to edit the JSON directly to replace. v1 doesn't auto-overwrite — keeps Dave in control. (v2 could add "replace $X.XX with <new>" syntax for explicit override.)
- **Conflict policy on existing amount + same category:** silent no-op + idempotent confirmation iMessage ("$X.XX → <category> already in rules, no change").
- **Validation requirements:** `apply-amount-rule.py` validates (a) amount is a parseable number; (b) category text exactly matches an entry from YNAB's category list (fetched via the same `op-ynab-key.sh` + GET pattern used in `propose.py:fetch_categories`). On either validation failure, send Dave an iMessage explaining what failed and how to retry.

## 6. Initial parameters (TUNABLE)

| Parameter | Default | Surface | Rationale |
|---|---|---|---|
| `amount_match_tolerance` | `0.0` | `config.json` | Exact match for v1; Dave said "always the same value." Future fuzzy match (e.g., $0.01 rounding) is a config knob away. |
| `amount_lookup_overrides_payee` | `false` | `config.json` | v1: payee wins. Knob exists so v2 can flip without code change if Dave runs into the conflict. |

Both knobs ship in config.json with the listed defaults. The amount-lookup branch reads them when classifying.

## 5b. New file

**`state/amount-lookup.json`** — ship empty:

```json
{
  "version": 1,
  "rules": []
}
```

Schema:
- `version` (int, required): currently `1`. Bumped if schema evolves.
- `rules` (list, required): list of rule objects:
  - `amount` (number, required): exact dollar amount; negative for outflows. Compared against `txn.get("amount") / 1000.0`. Example for a $2,500 outflow: `-2500.00`.
  - `category` (string, required): must match one of YNAB's category names. Not validated at lookup time (matches merchant-lookup behavior); a typo here means the auto_apply path tries to PATCH with an unknown category and fails into manual_review_needed. Dave audits the JSON.
  - `note` (string, optional): human-readable description for Dave's reference (e.g., "Monthly spousal support, ex-spouse").

## 7. Tuning surface

Updated `SKILL.md` "Files and tuning points" section adds:

- **state/amount-lookup.json** — recurring fixed-amount rules (e.g., "every $-2500.00 outflow → Spousal Support"). Edit the `rules` list directly; restart not needed (file reread on each cron fire).

## 8. Success criteria

**Patch verification (Bishop's post-announce preview fire):**
- New `load_amount_lookup` event in JSONL with `entry_count >= 0` and `version: 1`.
- `cost_total` event still emits `> 0` (cost-tracking patch from commit `1253892`-area still works — regression check).
- All existing event types still present in the right counts (no event-type regressions).

**Harness regression:**
- All 3 dry + 1 real PASS, including the new `load_amount_lookup` assertion.
- The `cost_total > 0` assertion (added in the prior patch) still passes — DON'T regress it.

**Functional verification (after dispatch, while the file is empty):**
- No `classify_amount_hit` events expected in the preview run (rules list is empty).
- Behavior identical to pre-patch when amount-lookup is empty (proves the new branch is correctly fall-through).

**Future verification (Dave's manual test, after this patch ships):**
- Dave adds one rule to `state/amount-lookup.json` for a known recurring amount (either via the new iMessage syntax — "remember $-2500.00 = Spousal Support" — or by editing the JSON directly), manually fires `python3 propose.py --no-apply`, confirms a `classify_amount_hit` event in the JSONL for the matching transaction.
- For the iMessage path: Dave replies "remember $-2500.00 = 💰 Spousal Support" → Bishop matches the regex → calls `apply-amount-rule.py --message "remember $-2500.00 = 💰 Spousal Support"` → script validates + appends to amount-lookup.json + sends confirmation iMessage. Dave audits the resulting JSON.
- This is NOT part of the harness — happens after Dave reviews the patch and seeds the rules.

## 11. Test harness expectations

- 3 dry + 1 real, unchanged structure.
- New assertion: `load_amount_lookup` event must exist in every fire (entry_count is informational, not asserted — empty is valid).
- Existing `cost_total > 0` assertion: KEEP. The new patch must not regress it.
- The harness does NOT assert `classify_amount_hit` fires — depends on real-data overlap with Dave's (currently empty) rule list. Add only if/when Dave seeds a test rule that's guaranteed to match a real txn.

## 13. Dispatch instructions for the skills-agent

- **Target skill:** `~/.openclaw/workspace/skills/ynab-categorize/`
- **Patch identity:** `skill-patch-ynab-categorize-amount-lookup-<YYYYMMDD>-<HHMM>` (Bishop generates).

### Files affected (explicit list — verify scope before applying)

| File | Action | Why |
|---|---|---|
| `scripts/amount_lookup.py` | **CREATE** | New module: `load_amount_rules(path)` + `match_amount(amount, rules, tolerance)` + `add_amount_rule(rules, amount, category, note)` (returns updated rules list, raises on conflict). Mirror `merchant_lookup.py`'s shape. ~50 LOC. |
| `scripts/apply-amount-rule.py` | **CREATE** | New entry-point script. Parses an iMessage via regex, validates amount + category against YNAB, appends to `state/amount-lookup.json`, sends a confirmation iMessage via the existing `deliver.send_imessage` helper. Modeled on `apply-additions.py`'s structure (auth, parse, validate, mutate state, deliver confirmation). ~120 LOC. |
| `scripts/classify.py` | EDIT | `classify_transaction` gains the Step 1.5 amount-rule branch between existing payee-lookup and LLM-call branches. Add `amount_rules` kwarg. ~15 LOC inserted. |
| `scripts/propose.py` | EDIT | Hop 5: load amount-rules; emit `load_amount_lookup`. Hop 6 loop: pass `amount_rules` to classify_transaction; emit `classify_amount_hit` when result evidence indicates amount match. ~10 LOC modified. |
| `state/amount-lookup.json` | **CREATE** | Empty seed file: `{"version": 1, "rules": []}`. |
| `scripts/test.py` | EDIT | Add the `load_amount_lookup` assertion in the harness's per-fire validation. Keep existing `cost_total > 0` assertion intact. ~5 LOC. |
| `SETUP.md` | EDIT | Add a second routing section for "Amount-Rule Entry" alongside the existing "YNAB Approval Routing" section. The full SETUP.md now documents BOTH Bishop-side behaviors (forensic record). |
| `AGENTS-ADDENDUM.md` | **CREATE** (skill root) | One-shot file for Bishop to append to his AGENTS.md post-announce. Contains JUST the new "Amount-Rule Entry" routing section (NOT the existing merchant approval section, which Bishop already has). Bishop appends with idempotency check (grep for "Amount-Rule Entry" header), then deletes the addendum file. |
| `SKILL.md` | EDIT | Tuning surface section gains the new state file + the new iMessage syntax. ~5 lines added. |
| `config.json` | EDIT | Add `amount_match_tolerance: 0.0` and `amount_lookup_overrides_payee: false` to the existing config dict. |

**If the worker finds it needs to touch any file not on this list, that's a stop-and-ask** — write a question file, halt, let Bishop iMessage Dave for confirmation. Don't silently expand scope. (Lesson from the cost-tracking patch: the spec missed that `classify.py` also needed editing; the worker silently added it. Better path: stop, surface the finding, get a one-line "yes proceed" from Dave, then continue.)

### Dataflow trace (mandatory before applying edits)

Before writing any code, the worker reads:
1. `scripts/classify.py:classify_transaction` (currently lines ~190-285) to confirm the existing two-branch structure (payee-lookup, LLM-call) and the dict shape returned in each case.
2. `scripts/propose.py` Hop 5 (currently `load_lookup` around line ~268) and Hop 6 per-txn loop (around line ~282) to confirm where the new event/parameter wiring goes.
3. `scripts/merchant_lookup.py` to confirm the module pattern `amount_lookup.py` mirrors.
4. `scripts/apply-additions.py` to confirm the entry-point script pattern `apply-amount-rule.py` mirrors (auth → parse message → validate → mutate state → deliver confirmation iMessage). Reuse helpers (`deliver.send_imessage`, the YNAB GET wrapper for category fetch).
5. The existing `SETUP.md` to understand the routing-section format that the new Amount-Rule section will mirror.

The worker then writes a one-paragraph "Trace summary" at the top of `PATCH-SUMMARY.md` documenting what it understood about the call shapes, BEFORE applying edits. Specifically: (a) confirm `classify_transaction`'s current return dict keys; (b) confirm `apply-additions.py`'s argv shape and confirmation-iMessage flow; (c) confirm the existing SETUP.md section header style. If any of these don't match the documented assumptions, STOP-and-ask. Don't pattern-match-and-go.

### Patch invariants

- **State preservation: YES.** Don't touch `state/merchant-lookup.json` or `state/pending-*.json`. The new `state/amount-lookup.json` is a fresh creation; you write it ONCE with the empty seed and don't re-touch it.
- **Install preservation: YES.** Don't re-run `install.sh`. Don't modify `~/.openclaw/cron/jobs.json`. Don't re-append SETUP.md to Bishop's AGENTS.md.
- **Live-state preservation: YES.** Whatever mode the cron is currently in (preview or live), leave it alone.
- **Cost-tracking preservation: YES.** The prior patch wired cost accumulation through `classify.py` and `propose.py`. The new amount-rule branch returns `cost_usd: 0.0` (no LLM call → no cost), but the prior accumulator must still work for LLM-classified transactions in the same run.

### Bishop post-announce — extra step for this patch

This patch introduces NEW Bishop-side routing (the "Amount-Rule Entry" section). Standard patch-mode protocol says "AGENTS.md routing is preserved" — that holds for ROUTING THAT ALREADY EXISTS, but new routing introduced by a patch needs to be applied.

Bishop's post-announce sequence for this patch:

1. Verify `PATCH-SUMMARY.md` exists and indicates SUCCESS (standard).
2. Verify state files intact (standard — merchant-lookup.json byte-identical, all pending-*.json untouched).
3. **Check for `AGENTS-ADDENDUM.md`** at `~/.openclaw/workspace/skills/ynab-categorize/AGENTS-ADDENDUM.md`. If present:
   - Grep your own AGENTS.md for the addendum's section header (e.g., `## Amount-Rule Entry`).
   - If NOT already present, append the addendum's content to your AGENTS.md, preserving spacing.
   - If already present, no-op (idempotent).
   - Delete the addendum file (`rm`) after applying so it's not re-applied on subsequent patches.
4. Trigger ONE preview fire (standard): `python3 propose.py --no-apply`.
5. Verify `load_amount_lookup` event in log, `cost_total > 0`, no errors. The rules list is empty for v1 ship, so no `classify_amount_hit` events expected.
6. Relay to Dave: "Amount-lookup feature shipped. Rules file is empty — seed by replying 'remember $-2500.00 = Spousal Support' (or edit `state/amount-lookup.json` directly). Cron unchanged. Reply 'go' to enable live writes if you haven't already."

This `AGENTS-ADDENDUM.md` pattern becomes the convention for any future patch that needs to add Bishop-side routing without re-running install.sh.

### What Bishop pre-stages (before spawning)

| Source | Worker-side path | Reason |
|---|---|---|
| `~/.openclaw/workspace/skills/skill-builder/*` | `./skill-builder/` | Methodology pack — worker reads METHODOLOGY's "Modes: build vs patch" section first. |
| `~/.openclaw/specs/ynab-categorize-patch-amount-lookup.md` | `./spec.md` | This patch-spec. |
| `~/.openclaw/workspace/skills/ynab-categorize/` (entire skill) | `./skills/ynab-categorize/` | Target skill, with state files intact (worker treats as read-only inputs). |

### Forbidden

- Modifying `state/merchant-lookup.json` or `state/pending-*.json`.
- Re-running `install.sh`, `enable-live.sh`, or `disable-live.sh`.
- Modifying `~/.openclaw/cron/jobs.json` or Bishop's `~/.openclaw/workspace/AGENTS.md`.
- Touching files outside the explicit Files-affected list without surfacing as stop-and-ask.
- `ANNOUNCE_SKIP`, `NO_REPLY`, or `no_reply` as final assistant text.
- Skipping the dataflow trace.

### Build identity

`skill-patch-ynab-categorize-amount-lookup-<YYYYMMDD>-<HHMM>`

### Skill destination (post-handoff, in-place overwrite)

`~/.openclaw/workspace/skills/ynab-categorize/`

---

## Author's notes

- The classic use case is the Spousal Support check: $-2500.00 every month. Bank's payee field shifts ("Wells Fargo Online Transfer", "ACH Withdrawal", etc.), so payee-lookup misses. Amount alone is a reliable signal.
- Other amounts Dave will likely seed: rent or mortgage if recurring at fixed amount, gym membership, any fixed-price subscription whose payee text isn't stable.
- v1 ships rules file empty so the patch can land without forcing rule decisions. Dave seeds via iMessage syntax in conversation after the patch validates.
- This patch is a methodology test on multiple axes: it touches more files (10) than the cost-tracking patch (3); it adds new Bishop-side routing (testing the `AGENTS-ADDENDUM.md` convention); it tests the dataflow-trace requirement and the explicit Files-affected list (lessons from the prior patch's scope-creep).
- Ordering note: amount-lookup runs AFTER payee-lookup. So if the merchant-lookup contains a generic entry like "Wells Fargo" → "Banking Fees", and the spousal-support check shows up under "Wells Fargo," it'll be auto-categorized as "Banking Fees" — wrong. Dave should keep merchant-lookup tight (no over-broad payee keys) so amount-lookup can correctly catch the fallback cases. v2 with `amount_lookup_overrides_payee: true` would fix this if it becomes a problem.
- Conflict policy on the iMessage path is conservative: existing-amount + different-category → REJECT with explanation, don't auto-overwrite. Reasoning: amount rules are high-trust (bypass LLM judgment entirely); silent overwrite by a fat-finger iMessage could miscategorize a recurring transaction for months before Dave noticed. The reject-and-explain path keeps Dave in control. v2 may add explicit "replace $X.XX with <new>" syntax.
- The category text in the iMessage MUST exactly match a YNAB category name. The script fetches the current YNAB category list via the same auth pattern propose.py uses (`op-ynab-key.sh` + GET `/budgets/{id}/categories`) — no cached category list, no fuzzy matching. If Dave types "Spousal Support" but YNAB has it as "💰 Spousal Support" (with emoji), the script rejects and tells him the closest matches.
