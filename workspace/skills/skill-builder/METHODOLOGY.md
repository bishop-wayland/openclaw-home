# Methodology

The pattern for building an openclaw/Bishop skill end-to-end. Distilled from the `job-search` build (2026-05-02 → 2026-05-03), which validated each step and surfaced the failure modes this doc warns against.

This methodology is opinionated. The opinions are load-bearing — deviating from them is a stop-and-ask moment, not a quiet override.

---

## The four principles

### 1. Parameterize-by-default

Every decision point starts as a **tunable parameter** with a safe, opinionated default. Only commit to an **architectural choice** when the decision would cascade into prompt rewrites, schema changes, or storage migrations.

**Why:** Dave's tuning loop *is* the product. The first build is "safe defaults, end-to-end working." The next four conversations are "drop firmware filter, add Roblox to T2, bump max_searches to 15." If the first build hardcodes those values, every tuning conversation becomes a code edit.

**Practical test:** for any value the agent is about to write into code, ask: "would Dave plausibly want to tune this in conversation later?" If yes → put it in a config file or CLI flag, not a constant.

**Examples from job-search:**
- `--layer2-max-searches` (param) — Dave bumped 10 → 12 in conversation, no code edit.
- `companies.json` (param) — adding Roblox to T2 is an edit to a JSON file.
- `criteria.md` (param) — soften "research scientist" rule by editing the markdown.
- The JSON-extraction parser tolerating prose preamble (architectural) — affects how Claude's output is parsed; not a knob.
- The output schema (architectural) — adding a field cascades through Claude prompt + format.py + schema validation.

**Default discipline:** "safe and opinionated" beats "neutral." `max_searches=10` is conservative (cheap, bounded). `criteria.md` is opinionated (excludes VFX studios because Dave won't relocate). The agent must explain *why* each default is what it is in the spec — so Dave's tuning is informed, not blind.

### 2. Compose-first

Before scaffolding, the agent searches `~/.openclaw/workspace/skills/` for patterns that already solve part of the problem. **Reuse first, build new only when no fit exists.**

**Why:** Reinventing iMessage delivery, cron scheduling, JSONL logging, or 1Password auth is busywork that ships bugs. The canonical skills (`alert-circuit`, `gog`) exist *because* their patterns work. The agent should treat them as libraries.

**Practical workflow:**
1. List the capabilities the new skill needs (fetch / process / decide / log / deliver / schedule).
2. For each capability, grep existing skills' SKILL.md for the pattern. Note matches.
3. In the new skill's SKILL.md, list `Composes with: …` explicitly.
4. If no fit exists for a capability, only *then* build it — and consider whether the new pattern itself should be promoted to a reusable skill someday.

**Examples from job-search:**
- Composed with `gog` (gmail send via existing skill).
- Composed with `1password` pattern (op-anthropic-key.sh, op-gog-keyring-password.sh — reused the existing `op-*-key.sh` envelope shape).
- Did *not* compose with `alert-circuit` (job-search's email delivery is bulk HTML, not the iMessage cron pattern alert-circuit specializes in).

**For paddle-board alert:** must compose with `alert-circuit`. Agent that scaffolds its own iMessage stack instead of using alert-circuit's pattern is a methodology failure.

### 3. Stop-and-ask, don't silently guess

For any architectural decision not committed in the spec, the agent **halts** and asks via the failure path. Silent guesses on architectural choices are forbidden.

**Why:** Architectural drift discovered after a build is expensive to undo (it cascades through code, prompts, schema, tests). Architectural drift discovered before is a 30-second iMessage exchange.

**Stop-and-ask path (v1):**
1. Agent writes `/tmp/skill-build-<id>/question-<n>.md` with: the question, what would unblock it, what defaults the agent would otherwise use.
2. Agent calls `sessions_send` to Bishop's main session: `"skill-build-<id> stuck. Question at <path>."`
3. Bishop iMessages Dave with the question summary.
4. Dave replies via iMessage.
5. Bishop dispatches a *resume* session: same spec + the question + Dave's answer file. Agent picks up from where it stopped.

(Phase B will introduce mid-session injection so the agent doesn't have to fully restart, but v1 stops cleanly.)

**Parameter decisions DON'T trigger stop-and-ask** — the agent picks a safe default, exposes the param, and notes the choice in the build summary. Dave tunes later.

### 4. Three-fires harness is non-negotiable

Every skill ships with `scripts/test.py` that runs **3 dry + 1 real** fires before the build is called done. Dry fires use `--dry-send` (or equivalent) to skip the externally-visible side effect; the real fire actually does it.

**Why:** Integration bugs are the bugs that bite at 7 AM Sunday. Unit tests miss them. The harness simulates production: real APIs, real auth, real logging — only the side effect is dry-runnable.

**Harness contract:**
- Each fire writes a per-run JSONL log.
- The harness parses the log and asserts: required hops fired, no `event=error` lines, dry fires have `*_skipped` events, real fires have actual delivery confirmation.
- Harness exits 0 only when ALL fires pass cleanly.
- Real fire is FAR LAST — if any dry fails, the real never runs.

**Real fire MUST exercise the deliver hops.** If the spec specifies external side effects (email, iMessage, Slack post, file write to a shared location, etc.), the real fire must actually invoke those hops — not skip them with `--dry-send`. A harness that passes only dry fires is a harness that doesn't prove the production path. *(Caught during the 2026-05-04 dispatch refactor: the prior hello-skill harness was running `--dry-send --no-apply` for the "real" fire, which meant the harness reported PASS without ever delivering anything.)*

**Real-fire deliveries MUST be marked `TEST FIRE`.** Any externally-visible delivery from the harness — iMessage body, email subject, Slack post, anything Dave or another human will see — must include a `TEST FIRE` prefix or marker so the recipient can distinguish harness output from production output. Production cron runs do not have this marker; only harness real fires do. Pattern: prefix the message subject/body with `[TEST FIRE]` and add a short tail like `(skill harness, ignore)`. Locks the message into "this is a test" framing without obscuring what it does.

**Bugs the harness caught during job-search:**
- Null byte in source (the script wouldn't import; first dry fire surfaced it instantly).
- JSON-from-prose preamble (Claude narrated before emitting JSON; harness saw the parse error and dumped the raw response).
- Keyring password wiring (gog couldn't read the file backend; harness's real fire failed cleanly with a clear error).
- Validator drift (schema check rejected Claude's actual output shape; one fix and re-fire).

Each was diagnosed in seconds because the JSONL trace pointed straight at the failing hop.

---

## Build sequence (the happy path)

Each step has a contract: the agent should only advance when the previous step's contract is met.

### Step 0 — Read the spec

Read `~/.openclaw/specs/<skill-name>.md` end to end. Confirm the spec is complete per `SPEC_TEMPLATE.md`. If any architectural commitment is missing, **stop-and-ask** before doing anything else.

If the spec file doesn't exist at the expected path, halt immediately and ping Bishop: "no spec at `<path>` — was the dispatch path correct? Spec is mandatory; the methodology cannot proceed without one." Don't try to infer a spec from the task description alone — the spec is the contract, and silently inferring it defeats the methodology.

**Contract:** spec is complete and unambiguous. Agent can answer "what does success look like?" from the spec alone.

### Step 1 — Compose-first survey

List existing skills (`ls ~/.openclaw/workspace/skills/`). Read their SKILL.md frontmatter descriptions. For each capability the new skill needs, identify whether to reuse or build.

**Contract:** "Composes with" section of the planned SKILL.md is decided. List of "build new" capabilities is enumerated.

### Step 2 — Decision-point sweep

Walk through `DECISION_POINTS.md`. For each category that applies:
- Spec committed → record the choice
- Spec didn't commit, but pattern is "param" → pick safe default, note rationale
- Spec didn't commit, pattern is "architectural" → **stop-and-ask**

**Contract:** every decision is either "spec-locked" or "param with default + rationale" — no silent guesses.

### Step 3 — Scaffold

Create the standard directory structure:

```
~/.openclaw/workspace/skills/<skill-name>/
├── SKILL.md                 # frontmatter + invocation patterns
├── (criteria.md / config.md / similar)   # the human-tunable knobs
├── (companies.json / schema.json / data files as needed)
├── scripts/
│   ├── <main>.py            # main pipeline orchestrator
│   ├── logger.py            # per-hop JSONL logger (copy from job-search if reusable)
│   ├── deliver.py           # delivery (or import from a composed skill)
│   ├── test.py              # three-fires harness
│   └── install.sh           # cron / launchd / hook installer
├── state/                   # SQLite db, dedup store, etc. (only if needed)
├── logs/                    # JSONL run logs land here
└── (com.bishop.<name>.plist / cron entry / hook config as appropriate)
```

Files that don't apply for a small skill should be omitted — but JSONL logger + test.py + main pipeline + SKILL.md are the floor.

**Contract:** scaffold compiles (Python parses, JSON validates). Empty stubs are fine; structure is what matters.

### Step 4 — Build hop-by-hop

The main pipeline is a series of hops. Each hop:
- Has a single responsibility
- Reads its inputs from the previous hop or from a config/state file
- Writes a JSONL log line on entry and on completion (or error)
- Errors halt the pipeline with `event=error, hop=<name>` + traceback

Build hops in order. Don't move to hop N+1 until hop N has its own JSONL line emitting.

**Contract:** a single dry fire produces one JSONL log line per hop, in order, with no errors.

### Step 5 — Three-fires harness

Write `scripts/test.py` per the harness contract above. Verify:
- 3 dry fires PASS (all required hops fire, no errors, dry-send events present)
- 1 real fire PASSES (delivery confirmed, state updated)
- Harness exits 0

If any fire fails, fix and re-run from scratch (reset dedup state, etc.). Don't ship until all 4 are clean.

**Iteration during build is expected.** First-fire failures are common and how the harness earns its keep. Job-search caught a null-byte-in-source, a JSON-from-prose-preamble parse fail, a keyring auth wiring issue, and a schema validation drift — each in a different fire. Fix forward, re-run. The methodology requires *three consecutive* clean dry runs before the real fire, not "three runs total" — flakes count.

**Contract:** harness exits 0 with three CONSECUTIVE clean dry fires + one real. Logs are clean. Real fire's side effect is verifiable (email arrives, file is written, iMessage delivered, etc.).

### Step 6 — Bishop validation

Add a "When Dave invokes Bishop" section to SKILL.md describing how Dave will use the skill conversationally with Bishop. (Examples: *"Show me this week's digest"*, *"Run it now"*, *"Tune the threshold to 15"*.)

If the skill is meant to be triggered by Dave (not just by cron), validate one round-trip: Dave-style request → Bishop loads SKILL.md → executes the right action.

**Contract:** Bishop can answer "how do I use this skill?" by reading SKILL.md alone.

### Step 7 — Install (with write-disabled preview)

The build is automated end-to-end through install. The worker writes the install scripts; Bishop runs them after the announce; Dave's "go" flips a single gate from preview to live. **There is no manual hand-install step.**

**The principle: install ships in preview mode, lives behind one gate.** Skills whose production runs perform external writes beyond Dave's inbox (YNAB PATCH, third-party API state changes, shared file writes outside the skill, irreversible network calls) install with their write hops *gated off* by default. The cron is registered, Bishop's routing is wired, and an immediate preview fire runs on install — but nothing commits externally. Dave sees the same email/iMessage he'd see in production minus the writes. He replies "go" → Bishop flips one gate → next fire is fully live.

**Why this shape:** the build's three-fires harness validates the skill works *in worker context*. The post-install preview fire validates the *production code path* (cron → agent → script → delivery) end-to-end against real upstream data. Catching wiring bugs there is much cheaper than at 9 AM Sunday. Manual hand-install is friction without value — by the time Dave is reading SETUP.md, he's already reviewed BUILD-SUMMARY.md and seen the harness real-fire output.

**Skills with no risky external writes** (e.g., a paddle-board alert that only sends an iMessage — the iMessage *is* the desired side effect, harness real-fire already exercised it) skip the preview/live distinction and install directly to live.

**The write-gate mechanism is per-skill** — pick a CLI flag (`--no-apply`), config key (`apply_writes: false`), or env var. The pipeline defaults to gated. Live mode means the gate is removed (cron entry edited to drop the flag, config key flipped, etc.). Pick the simplest one that makes the gate visible at the cron-entry level so Dave can audit "is this skill live?" by reading `cron/jobs.json` alone.

**The install ships three scripts** (one for non-write skills):
- `scripts/install.sh` — registers the schedule (cron / launchd / hook) with the write-gate ON, appends SETUP.md to Bishop's AGENTS.md (if SETUP.md is non-empty), then runs one immediate preview fire. Idempotent — safe to re-run.
- `scripts/enable-live.sh` — flips the gate from preview to live. (Omit for skills with no write-gate.)
- `scripts/disable-live.sh` — flips the gate back. Always include as the inverse of enable-live.

**Schedule selection (unchanged):**
- Recurring tool-using runtime → **launchd** (e.g., job-search). NOT openclaw cron — openclaw's cron path has invariants for the announce/deliver pattern that don't fit a tool-using worker.
- Recurring announce-pattern alert → **openclaw cron** in `~/.openclaw/cron/jobs.json` (e.g., medication reminders). See `alert-circuit` for the canonical pattern.
- Hook-driven (gmail, etc.) → openclaw hooks. See `alert-circuit/EXAMPLES.md`.

**Worker's role:** writes `install.sh`, `enable-live.sh`, `disable-live.sh`, and `SETUP.md` into the skill directory. **Does not run them** — `tools.fs.workspaceOnly: true` prevents the worker from reaching `~/.openclaw/cron/jobs.json` or Bishop's AGENTS.md anyway. Worker exits cleanly with the announce.

**Bishop's role (post-announce, automatic):**
1. Run `bash ~/.openclaw/workspace/skills/<name>/scripts/install.sh`. The script handles schedule registration, AGENTS.md append, and the preview fire.
2. Read the preview fire's log (`logs/run-*.jsonl` newest) to confirm it ran clean.
3. Report to Dave: "Skill built and installed in preview mode. Preview fire just ran — check your email/iMessage. Reply 'go' when ready to enable live mode." (Or, for non-write skills: "Skill built and installed live. First scheduled fire is `<datetime>`.")

**Dave's role:** review the preview email/iMessage. If it looks right, reply "go." Bishop runs `enable-live.sh`. Done.

**Contract:**
- Schedule is loaded; next firing time is in the build summary.
- For write-gated skills: preview fire's external output equals production output minus the write hops; one gate-flip script enables live; one inverse script rolls back.
- For non-write skills: install is direct-to-live; no gate scripts needed.

---

### Why "preview" is not "mock"

The preview fire is **not** a mocked run. It hits real upstream APIs, makes real LLM calls, sends real email/iMessage to Dave. The only thing it doesn't do is the *external write* (YNAB PATCH, etc.). Spec authors should call this out as "preview, write-disabled" — calling it "mock" oversells the safety; the only safety boundary is the write-gate. Everything reachable to a live run *is* reachable to the preview except the gated hop.

### Step 8 — Report back

Write `/tmp/skill-build-<id>/summary.md`:

```markdown
# Build summary: <skill-name>

**Status:** SUCCESS | STUCK (see questions/) | FAILED (see error.md)
**Skill location:** ~/.openclaw/workspace/skills/<skill-name>/
**Test harness:** PASS (3 dry + 1 real) | failures listed below
**Real fire side effect:** <what happened — email sent, iMessage delivered, etc.>

## Decisions made
- Architectural: <list>
- Parameters with defaults: <table>

## Tuning surface (where Dave will iterate)
- <file/flag> — <what to tune>

## Composes with
- <list>

## Cost
- Per-run: $X
- Monthly: $Y

## Known follow-ups
- <list>

## Files to read for context
- SKILL.md
- <main>.py — entry point
- logs/run-*.jsonl — forensic trace
```

Then call `sessions_send` to Bishop's main session: `"skill-build-<id> done. Summary at /tmp/skill-build-<id>/summary.md"`.

Bishop reads the summary and iMessages Dave the result.

**Contract:** Dave can decide whether to use the skill by reading the summary alone.

---

## What NOT to do

These are the failure modes that bit during the job-search build, encoded as rules.

### Don't skip JSONL logging "just for now"

The trace logs are why bugs were diagnosable in seconds. Without per-hop JSONL events, a 7 AM Sunday failure is opaque. The 5 lines of logger.py boilerplate pay for themselves in the first incident.

### Don't skip the harness

Even for a small skill. Three-fires is the contract. A "trivial" skill that ships without a harness will silently break the first time the upstream API changes.

### Don't bake constants where parameters belong

If the agent is about to write `THRESHOLD = 14.0`, ask: "would Dave plausibly want to tune this?" If yes, the value goes into a config file or CLI flag with a documented default.

### Don't reinvent patterns that exist in other skills

If the new skill needs iMessage delivery, use `alert-circuit`'s pattern. If it needs gmail send, use `gog`. If it needs 1Password auth, use the `op-*-key.sh` envelope shape. The cost of "I'll just write my own" is paid by every future maintenance pass.

### Don't silently guess on architectural decisions

Stop-and-ask is cheap. Architectural drift is expensive. When in doubt, write a question file and ping Bishop. Dave will answer in 30 seconds.

### Don't fight Claude's prose preamble — extract from it

When using Claude for judgment hops, Claude reliably narrates analysis before emitting JSON. Use the `_extract_json` helper pattern (find `\`\`\`json` block OR outermost `{...}`) and keep the prose as commentary in `notes-*.md`. The narration is useful, not noise.

### Don't use macOS Keychain for non-interactive auth

launchd / cron / subprocess shells can't access the macOS Keychain. Use `gnupg`/`gog`'s file-backend keyring (encrypted, password-protected) with the password fetched from 1Password and injected via env var. Pattern: `op-gog-keyring-password.sh`.

### Don't dry-run state mutations

`mark_seen`, dedup commits, and similar must be skipped on dry fires. Dry runs are rehearsals; they don't commit state. Otherwise the harness's three-fires lose their meaning.

### Don't ship without checking cost

Skills that call paid APIs (Claude, web_search, weather APIs with free-tier limits) need a per-run cost estimate AND a monthly projection in the SKILL.md. If the projection is over the spec's cost ceiling, that's a stop-and-ask: re-architect (cap usage, switch APIs, drop frequency) or get Dave's approval to exceed.

---

## Stop-and-ask checklist

Before halting, the agent's question file must contain:

1. **The decision being asked about.** ("Which weather API to use for paddle-board alert?")
2. **What the spec said.** (Quote the relevant section, or note "spec was silent.")
3. **What unblocks proceeding.** ("Pick one of: NOAA NDBC, OpenWeatherMap, Tomorrow.io.")
4. **What the agent would otherwise default to.** ("If forced to default: NOAA NDBC because it's free and authoritative for US coastal locations, but the buoy data is sparse for inland lakes.")
5. **Cost or blast-radius implications.** ("OpenWeatherMap free tier is 1k calls/day; Tomorrow.io is 500/day. NOAA is unlimited but coverage is patchy.")

A well-formed question file lets Dave answer in one sentence.

---

## Origin

This methodology was extracted from the `job-search` build the day after it shipped. The build itself was the validation; this doc is the codification. Subsequent skill builds are the ongoing validation — failures here update the doc.
