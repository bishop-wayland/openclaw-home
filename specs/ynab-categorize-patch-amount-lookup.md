# `ynab-categorize` Patch Spec — amount-based categorization

**Spec version:** 1
**Mode:** patch
**Derive from:** null (not applicable in patch mode)
**Authored:** 2026-05-04 by Dave + Claude (planning session)
**Author notes:** Adds a fallback layer to classify.py: when payee lookup fails, check whether the transaction amount matches a known amount-rule before falling through to the LLM call. Use case: recurring fixed-dollar transactions whose payee text varies (e.g., spousal-support check — same amount every month, but the bank's payee text shifts run-to-run). Dave maintains the rule list manually in `state/amount-lookup.json`. v1 ships the file empty; Dave adds rules locally as they come up.

## 1. Elevator pitch

Insert an "amount-rule check" between Step 1 (payee lookup) and Step 2 (web+LLM) in `classify.py`'s `classify_transaction`. If the transaction amount (in dollars) matches an entry in `state/amount-lookup.json` (within configurable tolerance, default 0.0 = exact), return as `auto_apply` with the rule's category. Otherwise fall through to the existing LLM path. New event `classify_amount_hit` joins `classify_lookup_hit` and `classify_llm_call`/`classify_error` as the per-txn classification outcomes.

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
- **Approval flow:** unchanged. Amount-rules are NOT introduced via Dave's iMessage approval reply. Dave edits the JSON manually. (v2 may add iMessage syntax like "remember $-2500.00 = Spousal Support" but that's deferred.)

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
- Dave adds one rule to `state/amount-lookup.json` for a known recurring amount, manually fires `python3 propose.py --no-apply`, confirms a `classify_amount_hit` event in the JSONL for the matching transaction.
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
| `scripts/amount_lookup.py` | **CREATE** | New module: `load_amount_rules(path)` + `match_amount(amount, rules, tolerance)`. Mirror `merchant_lookup.py`'s shape. ~30 LOC. |
| `scripts/classify.py` | EDIT | `classify_transaction` gains the Step 1.5 amount-rule branch between existing payee-lookup and LLM-call branches. Add `amount_rules` kwarg. ~15 LOC inserted. |
| `scripts/propose.py` | EDIT | Hop 5: load amount-rules; emit `load_amount_lookup`. Hop 6 loop: pass `amount_rules` to classify_transaction; emit `classify_amount_hit` when result evidence indicates amount match. ~10 LOC modified. |
| `state/amount-lookup.json` | **CREATE** | Empty seed file: `{"version": 1, "rules": []}`. |
| `scripts/test.py` | EDIT | Add the `load_amount_lookup` assertion in the harness's per-fire validation. Keep existing `cost_total > 0` assertion intact. ~5 LOC. |
| `SKILL.md` | EDIT | Tuning surface section gains the new state file. ~3 lines added. |
| `config.json` | EDIT | Add `amount_match_tolerance: 0.0` and `amount_lookup_overrides_payee: false` to the existing config dict. |

**If the worker finds it needs to touch any file not on this list, that's a stop-and-ask** — write a question file, halt, let Bishop iMessage Dave for confirmation. Don't silently expand scope. (Lesson from the cost-tracking patch: the spec missed that `classify.py` also needed editing; the worker silently added it. Better path: stop, surface the finding, get a one-line "yes proceed" from Dave, then continue.)

### Dataflow trace (mandatory before applying edits)

Before writing any code, the worker reads:
1. `scripts/classify.py:classify_transaction` (currently lines ~190-285) to confirm the existing two-branch structure (payee-lookup, LLM-call) and the dict shape returned in each case.
2. `scripts/propose.py` Hop 5 (currently `load_lookup` around line ~268) and Hop 6 per-txn loop (around line ~282) to confirm where the new event/parameter wiring goes.
3. `scripts/merchant_lookup.py` to confirm the module pattern being mirrored.

The worker then writes a one-paragraph "Trace summary" at the top of `PATCH-SUMMARY.md` documenting what it understood about the call shapes, BEFORE applying edits. If the trace surfaces ambiguity (e.g., classify_transaction's signature is unexpected, the merchant_lookup pattern isn't what the spec assumed, the existing return dicts don't match the documented shape), STOP-and-ask. Don't pattern-match-and-go.

### Patch invariants

- **State preservation: YES.** Don't touch `state/merchant-lookup.json` or `state/pending-*.json`. The new `state/amount-lookup.json` is a fresh creation; you write it ONCE with the empty seed and don't re-touch it.
- **Install preservation: YES.** Don't re-run `install.sh`. Don't modify `~/.openclaw/cron/jobs.json`. Don't re-append SETUP.md to Bishop's AGENTS.md.
- **Live-state preservation: YES.** Whatever mode the cron is currently in (preview or live), leave it alone.
- **Cost-tracking preservation: YES.** The prior patch wired cost accumulation through `classify.py` and `propose.py`. The new amount-rule branch returns `cost_usd: 0.0` (no LLM call → no cost), but the prior accumulator must still work for LLM-classified transactions in the same run.

### Re-fire requirement (Bishop's job, not worker's)

Bishop runs ONE preview fire post-announce per patch-mode protocol: `python3 ~/.openclaw/workspace/skills/ynab-categorize/scripts/propose.py --no-apply`. Verify:
- `load_amount_lookup` event present
- `cost_total > 0`
- No `classify_amount_hit` events (rules list is empty for v1 ship)
- Run completes successfully end-to-end

Bishop relays to Dave: "Amount-lookup feature shipped. Rules file is empty (you seed it). Cron is unchanged. Reply with the recurring amounts you want to seed (or edit `state/amount-lookup.json` directly)."

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
- v1 ships empty so the patch can land without forcing rule decisions. Dave seeds the file in conversation after the patch validates.
- This patch is also a methodology test: it touches more files (7) than the cost-tracking patch (3). Tests whether the dataflow-trace requirement and the explicit Files-affected list catch the kind of scope-creep that bit the prior patch.
- Ordering note: amount-lookup runs AFTER payee-lookup. So if the merchant-lookup contains a generic entry like "Wells Fargo" → "Banking Fees", and the spousal-support check shows up under "Wells Fargo," it'll be auto-categorized as "Banking Fees" — wrong. Dave should keep merchant-lookup tight (no over-broad payee keys) so amount-lookup can correctly catch the fallback cases. v2 with `amount_lookup_overrides_payee: true` would fix this if it becomes a problem.
