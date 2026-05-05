# `ynab-categorize` Patch Spec — cost-tracking fix

**Spec version:** 1
**Mode:** patch
**Derive from:** null (not applicable in patch mode)
**Authored:** 2026-05-04 by Dave + Claude (planning session)
**Author notes:** First test of patch mode through Bishop. Fixes the `cost_total: 0.0` bug surfaced during YNAB preview validation (see commit `0393047`). This is also enforcement of METHODOLOGY's "Don't ship if cost tracking returns zero on a real run" rule (added in commit `9243abf`). Small, well-scoped, ideal first patch for validating the iteration loop.

## 1. Elevator pitch

Wire up the cost accumulator in `propose.py`. `classify.py` correctly computes `cost_usd` per call (input/output token counts × Haiku 4.5 rates), but `propose.py` never accumulates the per-call cost into `total_cost`. The `logger.emit("cost_total", cost_usd=total_cost)` line at `propose.py:409` always logs 0.0 despite real LLM spend. Fix: accumulate `result.get("cost_usd", 0.0)` into `total_cost` after each `classify_transaction` call in the Hop 6 classify loop. Add a harness assertion that real-fire `cost_total > 0`.

## 4. Pipeline (only affected hops)

| Hop | Change |
|---|---|
| 6 (classify) | Accumulate `result.get("cost_usd", 0.0)` into `total_cost` after each `classify.classify_transaction(...)` call in the per-txn loop. The accumulator initialization at `propose.py:280` is correct; the missing `+=` is in the loop body around line 286-310. |
| 13 (done / cost_total emit) | No code change — the emit at `propose.py:409` is already correct. The fix in Hop 6 makes the value non-zero. |

All other hops: unchanged.

## 8. Success criteria

**Patch verification (re-fired preview after worker handoff):**
- JSONL log's `cost_total` event has `cost_usd > 0` (expect ~$0.01–0.05 for a typical run on backlog).
- The sum of `cost_usd` across all `classify_llm_call` events equals `cost_total`. (Spot-check, not byte-exact — floating point.)

**Harness regression check:**
- All 3 dry fires + 1 real fire still PASS.
- New assertion in `test.py`: parse the real-fire log, assert `cost_total > 0`. Assertion failure message: "cost accumulator disconnected — total_cost emit is $0.00 despite N classify_llm_call events with non-zero cost_usd."

**Bishop-relayed report (post-announce):**
- One-line summary: "patch applied; preview fire ran; `cost_total` now $X.XX (was $0.00)."

## 11. Test harness expectations

- 3 dry + 1 real, unchanged structure.
- New assertion: real-fire `cost_total > 0`. Encode as a JSONL post-parse check in `test.py`'s real-fire branch. Reuse the existing log-parse helpers if any exist; otherwise add a simple `[e for e in events if e["event"] == "cost_total"][0]["cost_usd"] > 0` style check.

## 13. Dispatch instructions for the skills-agent

- **Target skill:** `~/.openclaw/workspace/skills/ynab-categorize/`
- **Patch identity:** `skill-patch-ynab-categorize-cost-tracking-<YYYYMMDD>-<HHMM>` (Bishop generates at dispatch time).
- **Files likely affected (hint, not constraint):** `scripts/propose.py` (the accumulator wiring), `scripts/test.py` (the new assertion). No other files should change. If the worker finds it needs to touch other files, that's a stop-and-ask.
- **State preservation: YES.** Do NOT touch `state/merchant-lookup.json` or any `state/pending-*.json` files. The `cp -r` handoff to Bishop's workspace must leave state files byte-identical to the originals (worker treats them as read-only inputs throughout).
- **Install preservation: YES.** Do NOT re-run `install.sh`. Do NOT modify `~/.openclaw/cron/jobs.json`. Do NOT re-append SETUP.md to Bishop's AGENTS.md. The cron entry, routing, and live-state are preserved across the patch.
- **Live-state preservation: YES.** The cron entry is currently in preview mode (`--no-apply` baked in). Don't flip it. If Dave was already in live mode, also don't flip; patch just lands and the existing gate state is untouched.
- **Re-fire requirement (Bishop's job, not worker's):** Bishop runs ONE preview fire post-announce per the patch-mode protocol: `python3 ~/.openclaw/workspace/skills/ynab-categorize/scripts/propose.py --no-apply`. Verify `cost_total > 0` in the resulting log; report the actual cost figure to Dave.

### What Bishop pre-stages (before spawning)

| Source | Worker-side path | Reason |
|---|---|---|
| `~/.openclaw/workspace/skills/skill-builder/*` | `./skill-builder/` | Methodology pack — worker reads METHODOLOGY's "Modes: build vs patch" section first. |
| `~/.openclaw/specs/ynab-categorize-patch-cost-tracking.md` | `./spec.md` | This patch-spec. |
| `~/.openclaw/workspace/skills/ynab-categorize/` (entire skill, recursively) | `./skills/ynab-categorize/` | The target skill. State files come along but are read-only to the worker. |

### What the worker does

1. Read `./skill-builder/SKILL.md` and METHODOLOGY's "Modes: build vs patch" section.
2. Read `./spec.md` (this patch-spec) in full.
3. Read the existing skill at `./skills/ynab-categorize/`. Specifically: `propose.py` (the per-txn classify loop around lines 282-310, and the `total_cost` emit at line 409), `classify.py` (confirm `cost_usd` is in the returned dict), and `test.py` (find where real-fire log parsing happens, or add it if absent).
4. Apply the surgical edit to `propose.py`: accumulate `result.get("cost_usd", 0.0)` into `total_cost` inside the per-txn loop.
5. Add the harness assertion to `test.py`.
6. Run the three-fires harness. All 3 dry + 1 real must PASS, including the new cost assertion.
7. Write `./skills/ynab-categorize/PATCH-SUMMARY.md` per skills-agent's done-reporting (patch mode) contract.
8. Output handoff via `exec`:
   ```bash
   cp -r ./skills/ynab-categorize/ /Users/bishop/.openclaw/workspace/skills/ynab-categorize/
   ```
   This is destructive on the target. State files in your staged copy MUST be byte-identical to the originals (you don't touch them).
9. Emit final assistant text — substantive patch report. Reference the cost figure from your real-fire run.

### Forbidden

- Modifying `state/merchant-lookup.json` or `state/pending-*.json`.
- Re-running `install.sh`, `enable-live.sh`, or `disable-live.sh`.
- Modifying `~/.openclaw/cron/jobs.json` or Bishop's `~/.openclaw/workspace/AGENTS.md`.
- Touching files in the skill outside `propose.py` and `test.py` without surfacing as a stop-and-ask.
- `ANNOUNCE_SKIP`, `NO_REPLY`, or `no_reply` as final assistant text.

### Build identity

`skill-patch-ynab-categorize-cost-tracking-<YYYYMMDD>-<HHMM>`

### Skill destination (post-handoff, in-place overwrite)

`~/.openclaw/workspace/skills/ynab-categorize/`

### Source location during patch

`~/.openclaw/workspace-skills-agent/skills/ynab-categorize/`

---

## Author's notes

- `classify.py`'s per-call cost calc uses Haiku 4.5 pricing: input $0.80 / 1M tokens, output $2.0 / 1M tokens (`classify.py:142`). That's the correct model + pricing per the build spec §9.
- This patch validates two things at once: (a) the patch mode workflow end-to-end through Bishop, and (b) the new methodology rule about cost-tracking enforcement. Two birds.
- Expected wall time: 3-5 min for the worker (small surgical edit + harness re-run), plus 4-5 min for Bishop's preview fire on the 176-txn backlog. Total: ~10 min from dispatch to Dave seeing the diff report.
