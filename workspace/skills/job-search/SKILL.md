---
name: job-search
description: Weekly automated job-posting digest emailed to Dave at otte.dave@gmail.com. Pulls open postings from a curated company list (Layer 1 deterministic ATS APIs + Layer 2 Claude web_search), filters via plain-English criteria, dedups against past sightings, and delivers an HTML email grouped by tier. Use when Dave says "show me the job digest", "tune my job search", "add company X to the watch list", "drop firmware filter", or asks anything about open postings he's tracking. Runs autonomously every Sunday 7 AM PT via launchd.
---

# Job Search

Bishop's weekly job-market scan. Surfaces open postings matching Dave's criteria so he can see how the market is evolving without active effort.

## What this skill does

Once a week (Sun 7 AM PT, via launchd), `scripts/search.py` runs the full pipeline:

1. **Layer 1 fetch** — pulls JSON from Greenhouse / Lever / Ashby APIs for ~22 companies in `companies.json[layer1]`. Free, deterministic.
2. **Pre-filter** — Python regex drops obvious non-matches (intern, junior, contract, firmware, kernel, recruiter). Narrows ~3000 raw postings to ~470 senior-level candidates.
3. **Layer 1 Claude judgment** — single Anthropic API call with `criteria.md` as system prompt, candidates as user data, `schema.json` as required output shape. Returns ~10-20 relevance-scored matches.
4. **Layer 2 web_search** — single Anthropic API call with the `web_search_20250305` tool, capped at `--layer2-max-searches` (default 10). Searches the ~17 bespoke-ATS companies in `companies.json[layer2]` (Apple, NVIDIA, Microsoft, Bungie/Blizzard/Respawn, Snap, Niantic, etc.) by tier priority. Returns matched postings + reasoned `skipped_companies` notes (which are themselves market signal — "Boston Dynamics found Staff SWE Simulation but Waltham-onsite only").
5. **Merge** — Layer 1 + Layer 2 results combined into one judgment.
6. **Dedup** — `state/seen.db` (SQLite) tracks `sha256(normalized_title + company + location)`. Drops anything seen before.
7. **Format** — `format.py` builds tier-grouped HTML email with apply links + relevance blurbs + cost footer.
8. **Deliver** — `gog gmail send` from `yutani.w.bishop@gmail.com` to `otte.dave@gmail.com`.
9. **Per-hop logging** — `logs/run-<iso>.jsonl` records every hop. If something breaks at 7 AM Sunday, `tail logs/run-*.jsonl | jq` shows which hop failed in 30 seconds.

Layer 2 is enrichment — if it fails (HTTP error, parse error), the run continues with Layer 1 only and notes the failure in `skipped_companies`. Use `--skip-layer2` for a cheaper Phase-1-only run.

## When Dave invokes Bishop

- **"Show me this week's digest" / "what came in this morning?"** — read the most recent `logs/run-*.jsonl`, summarize the results count, list top hits if Dave asks. Email already in his inbox.
- **"Run the job search now"** — `python3 ~/.openclaw/workspace/skills/job-search/scripts/search.py`. Fires the full pipeline immediately, sends a real email. Costs ~$0.55-0.70 (L1 + L2).
- **"Run a cheap one (no web_search)"** — `python3 ~/.openclaw/workspace/skills/job-search/scripts/search.py --skip-layer2`. Phase 1 only. Costs ~$0.20.
- **"Tune the search" / "drop X" / "add Y to T3"** — edit `criteria.md` or `companies.md` directly. For new companies: also re-run `scripts/discover-ats.py` and update `companies.json`. Next Sunday's run picks up the change.
- **"Why didn't I get a digest?" / "what broke?"** — `ls -t logs/ | head` then `cat` the latest. Each hop logged. Failure has a clear `event: error` line.
- **"How much is this costing?"** — `claude_responded` log line has L1 cost; `layer2_responded` has L2 token + web_search cost. Sum with `jq`.

## File map

| File | Purpose |
|---|---|
| `SKILL.md` | this file |
| `criteria.md` | plain-English judgment rules — edit when tuning |
| `companies.md` | human-curated company list (source of truth for tiers + URLs) |
| `companies.json` | machine-readable ATS slug map for Layer 1; search_hints for Layer 2 |
| `schema.json` | strict JSON schema Claude's output is validated against |
| `scripts/search.py` | main orchestrator (fetch → pre-filter → Claude → dedup → format → deliver) |
| `scripts/dedup.py` | SQLite-backed seen-postings store |
| `scripts/format.py` | JSON results → HTML email body |
| `scripts/deliver.py` | thin wrapper around `gog gmail send` |
| `scripts/logger.py` | per-hop JSONL logger |
| `scripts/test.py` | three-fires verification harness |
| `scripts/discover-ats.py` | maintenance: probe ATSes for new companies |
| `scripts/install.sh` | install / uninstall the launchd plist |
| `state/seen.db` | SQLite dedup store |
| `logs/run-*.jsonl` | per-run forensic trace |
| `com.bishop.job-search.plist` | launchd schedule (Sun 7 AM PT) |

## Composes with

- **gog** (bundled openclaw skill) — outbound email via `gog gmail send`. Auth lives at the Bishop level (`yutani.w.bishop@gmail.com`, gmail scope confirmed).
- **1password** (bundled) — Anthropic API key fetched via `~/.openclaw/scripts/op-anthropic-key.sh`.
- **launchd** — system scheduler. Not openclaw cron (this skill's runtime makes web/API calls; launchd is simpler to debug than openclaw's cron path here).

## Cost expectations (Phase 1 + Phase 2)

- Per run: ~$0.55-0.70 (Phase 1 ~$0.20 + Phase 2 ~$0.40 with `max_searches=10`)
- Monthly (weekly cadence): ~$2.50-3.00
- Layer 1 ATS fetches are free
- Layer 2 web_search: $0.01 per use × up to 10 uses = $0.10/run hard cap on tool fees, plus ~$0.30 in token cost
- Tune `--layer2-max-searches` lower for cost reduction (e.g. 5 → ~$0.30 total/run)

## Iteration philosophy

Tuning is a conversation, not a redeploy. When the digest surfaces a bad match, Dave says why; Bishop edits `criteria.md` or `companies.md` accordingly. The week-over-week loop is the product. Don't over-engineer the criteria up front — ship, tune, repeat.
