# Spec Template

Copy this template, fill it out, and save to `~/.openclaw/specs/<skill-name>.md`. The completed spec is the contract between Dave + Claude (planning) and the skills-agent (execution).

A spec is **complete** when:
- Every architectural commitment is locked (no `<TBD>` in those sections)
- Every initial parameter has a default *and* a one-line rationale
- The tuning surface is enumerated
- Success criteria are concrete enough to verify

If any section is `<TBD>`, the agent will stop-and-ask before proceeding. That's intended — better to clarify upfront than rebuild.

A complete worked example is in `examples/job-search-spec.md`.

---

## How to use this template

1. Copy this file to `~/.openclaw/specs/<skill-name>.md`.
2. Fill out each section. Replace `<placeholder>` values with concrete answers.
3. Delete sections that genuinely don't apply (mark them `N/A — <reason>` rather than removing, so the agent can verify the section was considered).
4. When ready to dispatch: iMessage Bishop the path. Bishop reads, dispatches the skills-agent, agent reads + builds.

---

# `<skill-name>` Skill Spec

**Spec version:** 1
**Authored:** `<YYYY-MM-DD>` by Dave + Claude (planning session)
**Author notes:** `<one paragraph: why this skill, what problem it solves, how it fits into Dave's workflow>`

## 1. Elevator pitch

`<2-3 sentences. What does the skill do? When does it fire? What does Dave see?>`

Example (job-search): *"Weekly automated job-posting digest emailed to Dave. Pulls open postings from a curated company list (Layer 1 deterministic ATS APIs + Layer 2 Claude web_search), filters via plain-English criteria, dedups against past sightings, and delivers an HTML email grouped by tier."*

## 2. Trigger

How and when does this skill fire?

- **Mode:** `<cron | launchd | hook | on-demand | both>`
- **Schedule:** `<cron expression or launchd plist time, in local time>`
- **Hook source:** `<gmail filter / file watcher / etc., if applicable>`
- **On-demand invocation:** `<how Dave triggers it conversationally — "Bishop, run the X now">`

## 3. Composes with

List existing openclaw/Bishop skills this skill should reuse. The agent will check this section first under the **compose-first rule**.

| Capability needed | Existing skill to reuse | Reason |
|---|---|---|
| `<e.g., outbound iMessage>` | `<alert-circuit>` | `<canonical pattern for cron-fired iMessage>` |
| `<e.g., gmail send>` | `<gog>` | `<existing auth + scope already wired>` |
| `<e.g., 1Password secret fetch>` | `<op-*-key.sh pattern>` | `<envelope shape is reused>` |

If a capability has no existing fit, list it under "Build new" with one-line justification.

**Build new:**
- `<capability>` — `<why no existing skill fits>`

## 4. Pipeline

List the hops the skill executes, in order. Each hop is a single responsibility. Per `METHODOLOGY.md`, every hop emits its own JSONL log line.

| # | Hop | Input | Output | Notes |
|---|---|---|---|---|
| 1 | `<config_load>` | `<config files>` | `<parsed config>` | `<errors halt>` |
| 2 | `<fetch>` | `<API endpoint>` | `<raw JSON>` | `<retry policy if any>` |
| 3 | `<filter>` | `<raw>` | `<candidates>` | `<which fields drive the filter>` |
| 4 | `<judge>` | `<candidates>` | `<scored results>` | `<API used, cost note>` |
| 5 | `<dedup>` | `<scored>` | `<new only>` | `<state store path>` |
| 6 | `<format>` | `<new>` | `<delivery payload>` | `<format type>` |
| 7 | `<deliver>` | `<payload>` | `<confirmation>` | `<channel + dry-run flag>` |
| 8 | `<mark_seen>` | `<delivered>` | `<state updated>` | `<skip on dry-send>` |

For small skills (paddle-board, etc.), 3-4 hops is normal. For complex pipelines (job-search), 8-12 hops.

## 5. Architectural commitments (LOCKED)

Decisions in this section are *not parameters*. Changing them post-build cascades through code. The agent must obey these.

- **Data source / external API:** `<NOAA NDBC, OpenWeatherMap, Anthropic API, Greenhouse jobs API, etc.>`
- **Output channel:** `<iMessage via alert-circuit | HTML email via gog | file write | terminal output>`
- **Storage backend:** `<SQLite at state/<name>.db | flat file | none>`
- **Output schema:** `<inline JSON Schema OR pointer to schema.json file>`
- **Auth dependencies:** `<list of op-*.sh scripts the skill requires; or "none">`
- **Cost model:** `<free | per-call paid | metered tier>` and `<which APIs cost what>`
- **Failure semantics:** `<halt-on-error | best-effort | enrichment-optional>` per hop
- **Unit conventions:** `<mph | knots | m/s; USD | EUR; UTC | local time>` — pick once, use everywhere

## 6. Initial parameters (TUNABLE)

Every value Dave might tune in conversation later. Each gets a safe default + one-line rationale. The agent surfaces these as files / flags / config keys.

| Parameter | Default | Surface | Rationale |
|---|---|---|---|
| `<wind_threshold_mph>` | `<14>` | `<config.json>` | `<conservative; paddle-boarders generally avoid >15mph>` |
| `<location_lat_lng>` | `<47.6754, -122.2087>` | `<config.json>` | `<Kirkland WA — Dave's home>` |
| `<check_hours>` | `<6-10am local>` | `<config.json>` | `<morning paddle window>` |
| `<cron_fire_time>` | `<5am local daily>` | `<launchd plist>` | `<early enough to plan the day around>` |
| `<api_call_budget>` | `<$0.05/run>` | `<--budget flag>` | `<keeps monthly under $2>` |

## 7. Tuning surface

Concrete list of files / flags Dave will iterate on after the build. Helps the agent know what to surface and prioritize as friendly to edit.

- `<config.json>` — most-edited; threshold and location
- `<criteria.md>` (if applicable) — plain-English judgment rules
- `<companies.json>` (if applicable) — data lists Dave curates
- `<--<flag-name>>` (if applicable) — runtime overrides for one-off tuning

## 8. Success criteria

Concrete checks for "v1 works." The three-fires harness (3 dry + 1 real) is the default; spell out what each fire must verify.

**Dry fires (×3) must pass when:**
- All required hops emit JSONL events in order
- No `event=error` lines
- Dry-side-effect events present (`*_skipped` events for delivery and state mutation)
- No empty results unless explicitly expected (e.g., dedup matched everything)

**Real fire must pass when:**
- The externally-visible side effect occurs and is verifiable
  - `<e.g., email arrives at otte.dave@gmail.com with non-zero results>`
  - `<e.g., iMessage delivered to Dave's number with the alert text>`
  - `<e.g., file at /tmp/<x>.json updated with new content>`
- State store is updated (dedup hash inserted, mark_seen committed, etc.)
- Run cost is under the per-run budget

**Bishop validation must pass when:**
- Dave can read SKILL.md and know how to invoke / tune the skill
- Bishop can answer "what did this skill produce this morning?" by reading logs

## 9. Cost ceiling

| | |
|---|---|
| Per-run target | `<$X.XX>` |
| Per-run hard cap (stop-and-ask if exceeded) | `<$Y.YY>` |
| Monthly projection at expected cadence | `<$Z.ZZ>` |
| Free-tier APIs (no $) | `<list>` |
| Paid APIs | `<list with per-call cost>` |

If estimated monthly cost exceeds Dave's stated cap (default: $5/month per skill unless otherwise specified), the agent stops-and-asks before scaffolding.

## 10. Logging & forensics

What the agent must JSONL-log per hop. The log path convention is `~/.openclaw/workspace/skills/<name>/logs/run-<iso>.jsonl`.

Required event types:
- `triggered` — entry, with run mode flags
- `<hop_name>` — one per hop, with key counters (n_fetched, n_kept, n_skipped, etc.)
- `error` (if any) — hop, message, traceback, http code if applicable
- `done` — exit status

Plus skill-specific events:
- `<event_name>` — `<what it captures>`

## 11. Test harness expectations

- Default: three-fires (3 dry + 1 real). Override only with reason.
- Dry mechanism: `<--dry-send | --no-deliver | --simulate-fetch>` — pick one CLI flag, document what it skips
- State reset: harness resets dedup state before run #1 so each fire is comparable
- Real fire is final; if any dry fails, real does NOT run
- **Real fire MUST exercise the deliver hops.** If this spec lists external side effects in §5 (email, iMessage, Slack post, etc.), the real fire actually invokes them. A harness that only dry-runs is a methodology violation — see METHODOLOGY.md §"Three-fires harness is non-negotiable".
- **Real-fire deliveries MUST be marked `TEST FIRE`.** Any externally-visible delivery from the harness gets a `[TEST FIRE]` prefix in the subject/body and a `(skill harness, ignore)` tail. Production runs do not have this marker.

## 12. Known follow-ups / out of scope

What's deliberately not in v1 scope but worth flagging for future work:

- `<feature>` — `<why deferred — cost, complexity, depends on Bishop Identity Track, etc.>`
- `<integration>` — `<not yet because [reason]>`

## 13. Dispatch instructions for the skills-agent

When this spec is handed to the skills-agent (a registered OpenClaw sub-agent at `agents.list[].id: "skills-agent"`), the worker should:

1. Load `./skill-builder/SKILL.md` and the docs it points to. (Bishop pre-stages the methodology pack into the skills-agent workspace at dispatch.)
2. Read `./spec.md` in full. (Bishop pre-stages the per-build spec there.)
3. Execute the build per `METHODOLOGY.md` step sequence, scaffolding into `./skills/<skill-name>/`.
4. Stop-and-ask on any architectural ambiguity not resolved here: write `./skills/<skill-name>/QUESTION.md`, then emit a final assistant text describing the question. The OpenClaw runtime announce delivers your final text to Bishop's session; Dave answers via iMessage; Bishop dispatches a fresh worker with the answer in the new task.
5. Write the build summary to `./skills/<skill-name>/BUILD-SUMMARY.md` per methodology Step 8.
6. Write the install scripts and SETUP.md per the **Install phase** subsection below.
7. **Output handoff:** copy the completed skill from your workspace to Bishop's via `exec`:
   ```bash
   cp -r ./skills/<skill-name>/ /Users/bishop/.openclaw/workspace/skills/<skill-name>/
   ```
8. Emit a final assistant text — substantive build report. The runtime announce auto-posts it to Bishop's session. **Never end with `ANNOUNCE_SKIP`, `NO_REPLY`, or `no_reply`** — those tokens suppress the announce.

**Build identity:** `skill-build-<skill-name>-<YYYYMMDD>-<HHMM>`

**Skill destination (after handoff):** `~/.openclaw/workspace/skills/<skill-name>/`

**Source location during build:** `~/.openclaw/workspace-skills-agent/skills/<skill-name>/`

### Install phase (the worker writes; Bishop runs)

Per METHODOLOGY Step 7, the build flows automatically into install with a write-disabled preview. Specify here:

- **Has external writes beyond Dave's inbox:** `<YES | NO>` (YNAB PATCH, third-party API state, shared file writes outside the skill = YES. iMessage / email to Dave only = NO.)
- **Write-gate mechanism:** `<--no-apply CLI flag | config.json apply_writes:false | env var SKILL_LIVE=0>` — pick one, document the default-gated state. Prefer a mechanism visible at the cron-entry level so Dave can audit "is this skill live?" from `cron/jobs.json` alone.
- **Schedule registration target:** `<~/.openclaw/cron/jobs.json | launchd plist at ~/Library/LaunchAgents/com.bishop.<name>.plist | hook config>`

The worker writes:

| File | Purpose |
|---|---|
| `scripts/install.sh` | Registers schedule with write-gate ON, appends `SETUP.md` to Bishop's AGENTS.md (if non-empty), runs one immediate preview fire. Idempotent. |
| `scripts/enable-live.sh` | Flips the gate from preview to live. **Omit if "Has external writes" is NO.** |
| `scripts/disable-live.sh` | Inverse of enable-live. **Omit if "Has external writes" is NO.** |
| `SETUP.md` | Bishop-side routing snippet (approval-reply detection, etc.). Empty/skipped if the skill needs no Bishop behavior beyond firing the cron. |

After the worker emits the announce with SUCCESS, **Bishop** (per Bishop's AGENTS.md "Post-build install protocol"):
1. Runs `bash ~/.openclaw/workspace/skills/<name>/scripts/install.sh`
2. Reads the preview fire's log to confirm clean run
3. Reports to Dave with the preview output and the "Reply 'go'" prompt

When Dave replies "go" → Bishop runs `enable-live.sh`. Done.

For skills with no external writes: `install.sh` installs directly to live, no `enable-live.sh` / `disable-live.sh` needed.

**Worker forbidden actions** (still):
- Don't *run* `install.sh` from the worker. `tools.fs.workspaceOnly` blocks the cron/AGENTS.md edits anyway.
- Don't pre-flip the live gate. The default-gated state is load-bearing.

---

## Author's notes (optional)

Anything Dave + Claude want the agent to know that didn't fit elsewhere:

- `<context, gotchas, prior conversations, related work>`

---

## Appendix: Sections to delete if not applicable

For very small skills, some sections may genuinely not apply. Mark them `N/A — <reason>` rather than removing entirely; this signals the section was considered, not skipped.

Common N/A patterns:
- "Storage backend: N/A — stateless skill, no dedup needed"
- "Composes with: N/A — entirely standalone, no existing skill fits any capability"
- "Initial parameters: N/A — no tunable values; all behavior is locked"

If three or more sections are N/A, reconsider whether this is a full skill or just a one-off script.
