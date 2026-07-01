# `job-search` Skill Spec

**Spec version:** 1
**Authored:** 2026-05-02 by Dave + Claude (planning session) — *reverse-engineered 2026-05-03 as a worked example for the skill-builder methodology*
**Author notes:** Dave is exploring the job market without active urgency (earliest realistic move date Q1 2027). The goal is a *passive but serious* signal — surface postings matching his 3D-graphics / animation / characters / TA-and-EM background so the shape of the market stays visible, not so he can apply this week. Tuning is the product: each weekly digest is a chance to refine criteria, drop noisy companies, add new ones. Two-layer design (deterministic ATS + web_search) is intentional: cheap broad coverage + bespoke careers-page coverage for FAANG/big-tech that don't expose ATS APIs.

## 1. Elevator pitch

Weekly automated job-posting digest emailed to Dave at otte.dave@gmail.com. Pulls open postings from a curated company list (Layer 1 deterministic ATS APIs + Layer 2 Claude web_search), filters via plain-English criteria, dedups against past sightings, and delivers an HTML email grouped by tier. Runs autonomously every Sunday 7 AM PT.

## 2. Trigger

- **Mode:** launchd (scheduled), with on-demand support
- **Schedule:** Sunday 7:00 AM local time (PT)
- **Hook source:** N/A
- **On-demand invocation:** *"Bishop, run the job search now"* → Dave-or-Bishop runs `python3 ~/.openclaw/workspace/skills/job-search/scripts/search.py` (or `--skip-layer2` for cheap variant)

## 3. Composes with

| Capability needed | Existing skill to reuse | Reason |
|---|---|---|
| Outbound HTML email | `gog` | bundled openclaw skill, already has Bishop's gmail scope wired |
| 1Password secret fetch | `op-*-key.sh` envelope pattern | reuse the `{"values": {"value": "..."}}` JSON shape |

**Build new:**
- ATS fetch (Greenhouse / Lever / Ashby) — no existing skill covers this; HTTP+JSON is simple enough to inline
- Pre-filter regex — domain-specific to job titles, not generalizable
- Claude judgment loop — uses Anthropic API directly, doesn't fit any existing skill pattern
- Per-hop JSONL logger — generic, but copy-into-skill (could be promoted to a shared lib later)
- Three-fires harness — generic, copy-into-skill (could be promoted)

## 4. Pipeline

| # | Hop | Input | Output | Notes |
|---|---|---|---|---|
| 1 | `load_config` | `companies.json`, `criteria.md`, `schema.json` | parsed config | halts on missing/invalid |
| 2 | `layer1_fetch` | Greenhouse/Lever/Ashby URLs from `companies.json[layer1]` | raw JSON arrays | per-company errors → `skipped_companies`, continue |
| 3 | `normalize` | raw arrays | common posting shape `{title, location, url, department, company, tier}` | inline within layer1_fetch |
| 4 | `prefilter` | normalized list | candidates passing title regex | EXCLUDE_TITLE_PATTERNS + INCLUDE_TITLE_PATTERNS |
| 5 | `claude_judge` (Layer 1) | candidates + criteria.md + schema.json | judgment dict | single Anthropic API call, sonnet, ~$0.20 |
| 6 | `claude_layer2_search` | `companies.json[layer2]` + criteria.md + schema.json | judgment dict | single Anthropic API call w/ web_search tool, max_uses=10-12, ~$0.40 |
| 7 | `merge` | L1 + L2 judgments | combined judgment | concat results, concat skipped, sum filtered_out_count |
| 8 | `validate` | combined judgment | errors[] | check against schema.json; halt if invalid |
| 9 | `dedup` | combined results | new only + already-seen split | SQLite at `state/seen.db` |
| 10 | `format` | new results + run meta | (subject, html_body) | tier-grouped HTML, footer with run cost + L2 stats |
| 11 | `deliver` | (subject, html) | gmail send confirmation | `gog gmail send` via `yutani.w.bishop@gmail.com` → `otte.dave@gmail.com`; skipped on `--dry-send` |
| 12 | `mark_seen` | new results | inserted count | SQLite insert; skipped on `--dry-send` |

## 5. Architectural commitments (LOCKED)

- **Data sources:** Greenhouse public boards API, Lever public postings API, Ashby public job-board API (Layer 1, free); Anthropic API with `web_search_20250305` tool (Layer 2, paid).
- **Output channel:** HTML email via `gog gmail send`. No iMessage delivery — digest is too long for iMessage UX.
- **Storage backend:** SQLite at `state/seen.db`. Schema: `seen_postings(hash PRIMARY KEY, company, title, location, url, first_seen_iso)`.
- **Output schema:** `schema.json` — strict, no `additionalProperties`, top-level keys `results / skipped_companies / filtered_out_count`.
- **Auth dependencies:**
  - `~/.openclaw/scripts/op-anthropic-key.sh` (existing) → Anthropic API key
  - `~/.openclaw/scripts/op-gog-keyring-password.sh` (must create during build) → gog file-backend keyring password (because launchd subprocesses can't access macOS Keychain)
- **Cost model:** L1 fetches free; L1 Claude judgment paid (sonnet, ~$0.20/run); L2 Claude+web_search paid (~$0.40/run with max_uses=10).
- **Failure semantics:**
  - L1 fetch — best-effort (per-company error → `skipped_companies`, continue)
  - L1 judgment — halt-on-error (judge is the pipeline's brain; can't continue without it)
  - L2 search — enrichment-optional (failure → log + `skipped_companies` note, continue with L1 only)
  - validate — halt-on-error (don't deliver malformed output)
  - dedup — halt-on-error (state corruption is unrecoverable)
  - deliver — halt-on-error (no point marking seen if delivery failed)
- **Unit conventions:** UTC for log timestamps, local PT for cron schedule, USD for cost, ISO-8601 for all dates.

## 6. Initial parameters (TUNABLE)

| Parameter | Default | Surface | Rationale |
|---|---|---|---|
| Cron fire time | Sun 7 AM PT | launchd plist | weekly digest, early Sunday so Dave sees it with his coffee |
| Layer 2 max searches | 10 (later 12) | `--layer2-max-searches` flag | cap cost; 10-12 fits 17 companies with tier-priority allocation |
| Pre-filter exclude patterns | comprehensive list (intern/junior/contract/firmware/sales/etc.) | `EXCLUDE_TITLE_PATTERNS` in search.py | conservative — drop obvious non-matches before paying Claude to read them |
| Pre-filter include patterns | senior+ with domain anchor (TA, EM in graphics/3D/ML, etc.) | `INCLUDE_TITLE_PATTERNS` in search.py | conservative — keep anything plausibly matching |
| Layer 1 company list | 22 companies across T1-T4 | `companies.json[layer1]` | Dave's curated list, mirrors `companies.md` |
| Layer 2 company list | 17 companies, bespoke ATSes | `companies.json[layer2]` | FAANG + game studios + frontier AI / robotics |
| Tier definitions | T1 Games / T2 Big Tech / T3 AI labs+robotics / T4 mid-size | `companies.md` (human-readable) + `companies.json[].tier` | Dave's mental model |
| Criteria (judgment rules) | plain English, ~80 lines | `criteria.md` | iteratively tuned; soft on graphics/3D/animation, hard on firmware/contract/relocation |
| Recipient email | otte.dave@gmail.com | `deliver.py` constant | Dave's primary inbox |
| Sender identity | yutani.w.bishop@gmail.com | `deliver.py` constant | Bishop's gmail account |

## 7. Tuning surface

Where Dave will iterate post-build, in expected frequency order:

1. **`criteria.md`** — most-edited; soften / strengthen specific rules ("drop research-scientist filter", "lean harder into 3D")
2. **`companies.md` + `companies.json`** — add/drop companies, move tiers
3. **`--layer2-max-searches`** — adjust based on weekly cost actuals
4. **`EXCLUDE_TITLE_PATTERNS` / `INCLUDE_TITLE_PATTERNS`** — add domain-specific exclusions when noisy titles slip through

## 8. Success criteria

**Dry fires (×3) must pass when:**
- All 12 hops emit JSONL events in order
- No `event=error` lines
- `deliver_skipped` and `marked_seen_skipped` events present
- Layer 2 events present (or `layer2_skipped` if `--skip-layer2`)
- Pre-filter narrows ~3000 raw → ~470 candidates (within tolerance)
- Claude returns valid JSON parseable by `_extract_json`

**Real fire must pass when:**
- Email arrives at `otte.dave@gmail.com` from `yutani.w.bishop@gmail.com`
- Subject is `Job digest — <day> <date> — N new postings`
- Body is HTML, tier-grouped, with apply links + relevance blurbs
- `state/seen.db` has rows for the delivered postings
- Run cost (input tokens × $3/M + cache × $0.30/M + output × $15/M + L2 searches × $0.01) is under $1.00

**Bishop validation must pass when:**
- Dave can read SKILL.md and answer: how to invoke now, how to tune, how to debug
- Last log line of any run is `event=done, ok=true`

## 9. Cost ceiling

| | |
|---|---|
| Per-run target | $0.55-0.70 |
| Per-run hard cap | $1.00 (stop-and-ask if exceeded) |
| Monthly projection (weekly) | $2.50-3.00 |
| Free APIs | Greenhouse, Lever, Ashby |
| Paid APIs | Anthropic Sonnet ($3/$15 per M tokens), Anthropic web_search ($0.01/use) |

## 10. Logging & forensics

Required JSONL events (per `logger.py` writing to `logs/run-<iso>.jsonl`):

- `triggered` — entry, with `phase`, `dry_send`, `skip_layer2`, `layer2_max_searches`
- `config_loaded` — counts of L1/L2 companies
- `layer1_fetch` (×N) — per-company fetch result (count or error)
- `layer1_complete` — total raw count, fetch failures count
- `prefiltered` — kept, dropped
- `claude_invoked` — model, candidate count
- `claude_responded` — token counts, cost, prose notes length
- `layer2_invoked` (or `layer2_skipped`)
- `layer2_responded` — token counts, web_searches count, cost, L2 results count
- `validated` — results count, skipped count, filtered_out_count
- `deduped` — new, already_seen
- `artifacts_saved` — judgment.json + notes.md filenames
- `email_formatted` — subject, body bytes
- `gmail_sent` (or `deliver_skipped` on dry runs)
- `marked_seen` (or `marked_seen_skipped` on dry runs)
- `error` (if any) — hop, message, traceback, http if applicable
- `done` — ok status, results_emailed count

Forensic artifacts saved per run:
- `judgment-<id>.json` — final merged judgment
- `notes-<id>.md` — Claude's prose preamble (sectioned by L1 / L2)

## 11. Test harness expectations

- Three-fires (3 dry + 1 real)
- Dry mechanism: `--dry-send` flag — skips `deliver` and `mark_seen` hops
- Cheaper variant: `--skip-layer2` — Phase 1 only, ~$0.20 instead of $0.65
- State reset: `test.py` removes `state/seen.db` before run #1
- Real fire is final; if any dry fails, real does NOT run

## 12. Known follow-ups / out of scope

- **Job description deep-read** — currently judgment is title+location only. Could fetch the full posting body and judge on description; cost ~3-5x. Deferred until tuning shows title-only is too thin.
- **Bishop notification on Sunday** — Dave currently sees the digest as email. Could iMessage Bishop a "new digest landed, N postings" alert. Deferred — email is sufficient.
- **Cross-week trend reporting** — "new T1 postings this month vs last month." Requires aggregation queries on `seen.db`. Deferred until 4-6 weeks of data exist.
- **Pixar / WDAS / DreamWorks / Sony Imageworks** — explicitly out of scope. Dave will not relocate for production work. ILM kept for StageCraft / R&D only.

## 13. Dispatch instructions for the skills-agent

When this spec is handed to the skills-agent, the agent should:

1. Load `~/.openclaw/workspace/skills/skill-builder/SKILL.md` and the docs it points to.
2. Read this spec in full.
3. Execute the build per `METHODOLOGY.md` step sequence.
4. Stop-and-ask via `sessions_send` to Bishop on any architectural ambiguity not resolved here.
5. Write a build summary to `/tmp/skill-build-<id>/summary.md` per the methodology.
6. Notify Bishop via `sessions_send` when done or stuck.

**Build identity:** `skill-build-job-search-<YYYYMMDD>-<HHMM>`

**Skill destination:** `~/.openclaw/workspace/skills/job-search/`

---

## Author's notes

- The `_extract_json` helper that tolerates Claude's prose preamble is a *design choice* worth highlighting up front — without it, the first dry fire fails on Claude's narration before the JSON. Don't fight the preamble; extract from it.
- The `gog` file-backend keyring password requirement was discovered during build, not predicted. The agent will likely hit this same friction on any skill that uses `gog` from launchd / cron / non-TTY contexts. Consider promoting the `op-gog-keyring-password.sh` script to a known dependency for any skill that composes with `gog`.
- Three-fires PASSED on both Phase 1 (2026-05-02) and Phase 1+2 (2026-05-03). Real fires delivered substantive digests both times. The methodology validated end-to-end.
- This spec is the *reverse-engineering* of what got built. If Dave had handed this to the skills-agent before any code existed, the methodology says it should have produced something materially identical. That hypothesis isn't testable on job-search itself (already built), but is the design target for the next skill (paddle-board alert) which serves as the live test.

---

## Verification: did this spec produce what we built?

Cross-checking the spec against the actual `~/.openclaw/workspace/skills/job-search/` directory:

| Spec element | Actual artifact | Match? |
|---|---|---|
| 12-hop pipeline | `search.py` `run()` function | ✓ |
| Layer 1 ATS fetchers | `fetch_greenhouse`, `fetch_lever`, `fetch_ashby` | ✓ |
| Pre-filter regex pair | `EXCLUDE_TITLE_PATTERNS` + `INCLUDE_TITLE_PATTERNS` | ✓ |
| Claude judgment | `claude_judge` | ✓ |
| Layer 2 web_search | `claude_layer2_search` | ✓ |
| Merge | `merge_judgments` | ✓ |
| Schema validation | `validate_judgment` | ✓ |
| SQLite dedup | `dedup.py` | ✓ |
| HTML format | `format.py` | ✓ |
| gog deliver | `deliver.py` | ✓ |
| Three-fires harness | `test.py` | ✓ |
| launchd schedule | `install.sh` install command | ✓ |
| JSONL logger | `logger.py` | ✓ |
| Auth dependencies | `op-anthropic-key.sh` + `op-gog-keyring-password.sh` | ✓ |

**Conclusion:** the spec captures what was built. Structure validation passes. The remaining test is *behavior* validation — dispatching the agent against a new spec (paddle-board alert) and seeing if the methodology actually produces the right thing.
