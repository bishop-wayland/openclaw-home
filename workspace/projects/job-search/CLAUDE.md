# Project: job-search skill

**Status:** Shipped (Phase 1 + 2) — in production at weekly cadence. Active follow-up: launchd schedule install on the Mini.

Bishop's weekly job-posting digest. Built end-to-end across two sessions as the first methodology test for new-skill creation — the validation that proved the playbook works on a fresh skill.

---

## Where the skill lives

`~/.openclaw/workspace/skills/job-search/` — see `SKILL.md` for full file map.

---

## Phases shipped

| Phase | Date | Outcome |
|---|---|---|
| 1 | 2026-05-02 | 22 Layer 1 ATS fetchers (Greenhouse / Lever / Ashby) + Python pre-filter + Claude judgment + SQLite dedup + HTML email via `gog`. Three-fires PASSED. |
| 2 | 2026-05-03 | Layer 2 `web_search_20250305` for ~17 bespoke companies. Single-call design with `max_searches=10` budget. Merged into Phase 1 schema. Three-fires PASSED. Real email delivered with 13 results including 2 from web_search. |

---

## Cost envelope (don't re-litigate)

- Per run: ~$0.55-0.70 (L1 ~$0.20 + L2 ~$0.40 with max_searches=10)
- Weekly cadence: ~$2.50-3/month — within target
- Tunable: `--layer2-max-searches` reduces L2 cost ~$0.04/search saved + ~$0.30 token savings if Claude prunes context

---

## Architectural decisions (don't re-litigate)

- **launchd, not openclaw cron.** Runtime makes web/API calls; openclaw's cron path has announce/deliver invariants that don't fit a tool-using worker. `scripts/install.sh` installs the launchd plist.
- **`gog` keyring backend = `file`.** Required because launchd / non-interactive subprocesses can't access macOS Keychain. Password lives in 1Password as `op://Bishop/GogKeyringPassword/credential`, injected via `GOG_KEYRING_PASSWORD` env var.
- **VFX / animation studios excluded entirely** — Pixar/WDAS/DreamWorks/Netflix Animation/Sony Pictures Imageworks/Weta/DNEG/Framestore/MPC. Dave will not relocate for production work; ILM kept for StageCraft/R&D.
- **Pre-filter narrows ~3079 → ~470 candidates** via title regex. Claude does the location filter and final relevance.
- **JSON output via `_extract_json` helper.** Claude reliably narrates analysis before emitting fenced JSON. The helper finds either ```json``` blocks or outermost {…}. Don't fight Claude's preamble — it's useful as commentary.
- **`skipped_companies` is a feature, not a bug.** Claude's reasoning ("Boston Dynamics found great match but Waltham-only") is high-signal market intel and surfaces in the email footer.
- **URL discipline** — system prompt requires direct apply / posting URLs only. Careers-homepage-only → rejected. Trades quantity for quality.
- **Layer 2 failures don't fail the run.** Exception logged + `(Layer 2 batch)` entry to `skipped_companies`; pipeline continues with Layer 1.
- **`--skip-layer2` flag** for cheap smoke tests ($0.20 vs $0.65).

---

## Auth dependencies

- `~/.openclaw/scripts/op-anthropic-key.sh` → Anthropic API key
- `~/.openclaw/scripts/op-gog-keyring-password.sh` → `gog` file-backend keyring password

---

## Open follow-ups

1. **Install launchd schedule on the Mini** — `scripts/install.sh install` (Sun 7am PT). Was not yet installed on the VM at break time. **Migration touchpoint.**
2. **After 4-6 weekly runs**, tune `criteria.md` and `--layer2-max-searches` based on what landed vs what was missed. The iterative tuning loop is the product, not just the search.
3. **Cosmetic:** `test.py` harness summary lines for layer2 stats / total_cost don't always surface in subprocess output capture (buffering quirk). Assertions correctly PASS — only the supplemental print is affected.

---

## References

- `workspace/skills/job-search/SKILL.md` — invocation patterns + file map
- `workspace/skills/job-search/criteria.md` — judgment rules (edited 2026-05-02 to soften "research scientist", emphasize 3D graphics / animation / characters)
- `workspace/skills/job-search/companies.json` — Layer 1 + Layer 2 company list
- `workspace/skills/job-search/scripts/search.py` — main orchestrator
- Spec / methodology source: [skill-builder project](../skill-builder/CLAUDE.md)
