# Decision Points

Catalog of the decisions a skill build typically encounters, tagged with the **default pattern** the methodology applies (param / architectural / spec-locked / methodology-default). The skills-agent walks this catalog during Step 2 of the build (decision-point sweep).

Patterns:
- **`param`** — tunable knob with safe default; agent picks it without asking.
- **`architectural`** — locks code/prompts/schema; must be in spec or stop-and-ask.
- **`spec-locked`** — Dave's value preference, not technical; must be in spec.
- **`methodology-default`** — the methodology dictates the answer; no decision needed (e.g., JSONL logging).

For each category: when it applies, why the pattern, default if param, what triggers stop-and-ask, and worked examples.

---

## Triggers & scheduling

### Schedule / cron timing
- **Pattern:** `param` (the time) + `architectural` (the mechanism)
- **When it applies:** Any skill that fires on a schedule.
- **Why:** *When* a cron fires is a knob (Dave will move it around). *How* it fires (launchd vs openclaw cron vs hook) is locked by skill semantics.
- **Default if param:** match user intent — early morning for digests (5-7 AM PT), Sunday 7 AM for weekly summaries, top-of-hour for hourly checks.
- **Stop-and-ask trigger:** if the spec doesn't say *which mechanism* (launchd vs openclaw cron). Use the rule below.
- **Job-search example:** Sun 7 AM PT (param: launchd plist time) via launchd (architectural, because it makes web/API calls).
- **Paddle-board example:** 5 AM daily (param) via openclaw cron (architectural — fits the announce/deliver pattern that openclaw cron is designed for).

### Cron mechanism (launchd vs openclaw cron vs hook)
- **Pattern:** `architectural`
- **When it applies:** All scheduled skills.
- **Rule for picking:**
  - **launchd** when the skill makes outbound web/API calls and runs as a tool-using worker (job-search). Easier to debug, doesn't conflict with openclaw's cron invariants.
  - **openclaw cron** when the skill is announce/deliver — fire a Haiku, format a message, deliver via Bishop's iMessage path. Use the `alert-circuit` cron flavor.
  - **hook** when the skill is event-driven (gmail filter match, file watcher). See `alert-circuit/EXAMPLES.md` for hook-flavor.
- **Stop-and-ask trigger:** if the skill has both tool-use *and* announce-style behavior; pick the dominant role.

---

## External APIs & data sources

### Data source / API selection
- **Pattern:** `architectural`
- **When it applies:** Any skill that fetches external data.
- **Why:** API choice locks data shape, auth model, rate limits, failure modes — touching prompts, parsers, error handling.
- **Stop-and-ask trigger:** spec doesn't name the API.
- **Job-search example:** Greenhouse/Lever/Ashby for Layer 1 (locked), Anthropic web_search for Layer 2 (locked). Switching ATSes would mean rewriting `fetch_*` functions and renormalizing the data.
- **Paddle-board example:** NOAA, OpenWeatherMap, Tomorrow.io, etc. — must be locked in spec.

### API key / auth source
- **Pattern:** `architectural` (the mechanism) + `spec-locked` (the credential)
- **When it applies:** Any skill needing creds.
- **Rule:** Always use the `op-<service>-key.sh` envelope pattern in `~/.openclaw/scripts/`. Creds live in 1Password, not in the skill repo, env files, or the keychain.
- **Stop-and-ask trigger:** if the cred isn't yet in 1Password under a known path.
- **Job-search example:** `op-anthropic-key.sh` (existed) + `op-gog-keyring-password.sh` (created during build).
- **Paddle-board example:** if API requires a key, agent stops-and-asks for the 1Password path before fetching.

### Rate limits / retry / backoff strategy
- **Pattern:** `architectural` (strategy) + `param` (values)
- **When it applies:** Any external API with limits.
- **Default if param:** linear backoff, 3 retries, 5s base — for free-tier APIs. Skip retry entirely for paid APIs (let it fail clean — retries cost money).
- **Stop-and-ask trigger:** API has a non-obvious rate limit (e.g., per-IP per-day, sliding window) that requires special handling.

---

## Output & delivery

### Output channel
- **Pattern:** `architectural`
- **When it applies:** Always.
- **Why:** Channel choice cascades into delivery code, formatting (HTML vs plain text vs iMessage chunking), and Bishop's role.
- **Stop-and-ask trigger:** spec is silent on channel. (Spec must say `email | iMessage | file | terminal | combination`.)
- **Job-search example:** HTML email via `gog`. iMessage was considered and rejected because the digest is too long for iMessage UX.
- **Paddle-board example:** iMessage via `alert-circuit`. Short, single-line, daily.

### Recipient / sender identity
- **Pattern:** `param` (with safe defaults)
- **When it applies:** Any delivery.
- **Default if param:** sender = Bishop's identity (`bishopunit937@gmail.com` for email; Bishop's iMessage chat for iMessage). Recipient = `otte.dave@gmail.com` for email; Dave's iMessage thread for iMessage.
- **Stop-and-ask trigger:** spec wants a non-Bishop sender, or a recipient other than Dave.
- **Job-search example:** sender `bishopunit937@gmail.com`, recipient `otte.dave@gmail.com`. Both constants in `deliver.py` — could be parameters but haven't needed to be yet.

### Suppress-on-empty vs always-fire
- **Pattern:** `architectural`
- **When it applies:** Alert / digest / notification skills.
- **Why:** Changes UX semantics. "Always fire" means Dave gets a daily message even if nothing matches ("today is NOT a paddle day"). "Suppress on empty" means silence is the no-go signal. Mixing them mid-build means rewriting delivery logic.
- **Stop-and-ask trigger:** spec doesn't pick.
- **Job-search example:** always-fire (digest is sent even with zero new postings; the empty digest itself is the "nothing this week" signal).
- **Paddle-board example:** Dave should pick. Default suggestion would be **suppress-on-bad** (only message when wind is good) so Dave's iMessage thread isn't noise on bad-wind days.

---

## Processing & state

### Storage backend
- **Pattern:** `architectural`
- **When it applies:** Skills that need state across runs (dedup, run history, cached results).
- **Default if architectural:** SQLite at `state/<name>.db` for dedup or any structured state. Flat file (JSON / JSONL) for simple pointers (last-run timestamp, single-value cursors). None if stateless.
- **Stop-and-ask trigger:** state requirement is unclear from the pipeline. (If pipeline has dedup, state is needed.)
- **Job-search example:** SQLite at `state/seen.db`, hash key = `sha256(normalized_title + company + location)`.
- **Paddle-board example:** none — stateless. Each day's check is independent.

### Dedup strategy (key derivation)
- **Pattern:** `architectural`
- **When it applies:** Any skill with potentially duplicate inputs across runs.
- **Why:** Key choice determines what counts as "same posting / same alert / same event." Wrong key leaks duplicates or collapses distinct items.
- **Stop-and-ask trigger:** spec doesn't define what makes two items "the same."
- **Job-search example:** key = `sha256(normalized_title + company + location)`. Explicitly NOT URL — Greenhouse/Lever recycle job IDs, aggregators generate one-off URLs.
- **Paddle-board example:** N/A (stateless).

### Output schema (for skills that emit structured data)
- **Pattern:** `architectural`
- **When it applies:** Any skill where Claude or another tool produces JSON consumed by downstream code.
- **Why:** Schema shape touches Claude's prompt, the parser, validation, and renderers. Adding a field cascades.
- **Stop-and-ask trigger:** spec gives no schema and the pipeline has a `judge` / `extract` / `classify` hop.
- **Job-search example:** `schema.json` with `results[].{tier, company, title, url, location, relevance_blurb}` + `skipped_companies[]` + `filtered_out_count`. Validated against Claude's output every run.

### Filter / criteria / threshold values
- **Pattern:** `param` (the values) + `architectural` (the filter mechanism)
- **When it applies:** Any skill with a "decide if this matches" hop.
- **Default if param:** lean conservative on first build (over-include, under-exclude). Dave will tune toward stricter as he sees what gets through.
- **Stop-and-ask trigger:** spec gives no starting values *and* the domain isn't obvious (e.g., wind threshold for paddle-boarding — agent should ask if spec is silent).
- **Job-search example:** `criteria.md` (plain English, edited freely) + `EXCLUDE_TITLE_PATTERNS` / `INCLUDE_TITLE_PATTERNS` regex lists in `search.py`.
- **Paddle-board example:** `wind_threshold_mph: 14` (param, in config). Probably want the rule "alert me when forecast wind for 6-10am stays under threshold."

---

## Cost & safety

### Per-run cost ceiling
- **Pattern:** `param` (the value) + `architectural` (the enforcement)
- **When it applies:** Any skill with paid API calls.
- **Default if param:** "no paid calls" if the skill can do its job with free APIs. Otherwise pick a per-run cap that keeps monthly under $5.
- **Stop-and-ask trigger:** estimated monthly cost > $5 OR spec sets a cost ceiling that the agent's pipeline design would exceed.
- **Job-search example:** ~$0.55-0.70/run, $2.50-3/month. Layer 2 max_uses=12 caps the worst case.
- **Paddle-board example:** target $0 — free weather APIs available (NOAA NDBC, OpenWeatherMap free tier). If the spec wants paid → stop-and-ask.

### Failure semantics per hop
- **Pattern:** `architectural`
- **When it applies:** Any multi-hop pipeline.
- **Why:** "Halt on error" vs "best-effort, continue" vs "enrichment-optional" changes how the agent codes each hop. Job-search's Layer 2 is enrichment-optional (failure → log, continue with L1). Layer 1 fetch is best-effort (per-company errors → `skipped_companies`, continue). Claude judgment is halt-on-error (no point continuing if the judge crashed).
- **Stop-and-ask trigger:** spec doesn't classify each hop.
- **Default if pattern is unclear:** halt-on-error for any hop the pipeline genuinely depends on; best-effort for fan-out hops where partial results are valuable; enrichment-optional for "nice-to-have" augmentations.

### Concurrency / re-entrance
- **Pattern:** `architectural` (almost always: "single-run, no concurrency")
- **When it applies:** Scheduled skills + on-demand skills that share state.
- **Default:** single-run. Use a lock file (`state/<name>.lock`) if concurrency is genuinely possible.
- **Stop-and-ask trigger:** spec implies long-running operations that might overlap (e.g., cron fires while a manual run is still going).

---

## Conventions

### Unit conventions (mph/knots/USD/UTC)
- **Pattern:** `architectural`
- **Why:** Pick once, use everywhere. Mid-build unit drift is a stealth bug source.
- **Default if architectural:** US-locale defaults (mph, USD, local time aka PT). UTC for log timestamps. ISO-8601 dates everywhere.
- **Stop-and-ask trigger:** spec mixes units (e.g., "wind in mph but cost in EUR").
- **Paddle-board example:** mph for wind, local PT for time windows, UTC for log timestamps.

### File / directory naming
- **Pattern:** `methodology-default`
- **Convention:**
  - Skill dir: `~/.openclaw/workspace/skills/<kebab-case-name>/`
  - Logs: `logs/run-<YYYYMMDDTHHMMSSZ>.jsonl`
  - State: `state/<purpose>.db` (SQLite) or `state/<purpose>.json`
  - Auxiliary scripts: `scripts/<verb-noun>.py`
  - launchd plist: `com.bishop.<kebab-name>.plist`
- **Stop-and-ask trigger:** none — methodology-default.

---

## Methodology defaults (no decision needed)

These are decided by the methodology, not the spec. Listed here so the agent knows not to deliberate.

| Item | Default |
|---|---|
| Logging format | JSONL, one event per hop, line-buffered |
| Log location | `logs/run-<iso>.jsonl` in skill dir |
| Test harness | three-fires (3 dry + 1 real) via `scripts/test.py` |
| Dry-run flag | `--dry-send` (or skill-specific: `--no-deliver`, `--simulate-fetch`) |
| State mutation on dry runs | skipped (rehearsals don't commit state) |
| Auth secret access | `op-<service>-*.sh` envelope, JSON `{"values": {"value": "..."}}` |
| Build identity | `skill-build-<name>-<YYYYMMDD>-<HHMM>` |
| Build summary location | `/tmp/skill-build-<id>/summary.md` |
| Done notification | `sessions_send` to Bishop's main session |

---

## How to use this catalog during a build

The skills-agent walks this catalog top to bottom. For each entry that applies to the skill:

1. Check the spec for the answer.
2. If spec covers it → record the decision in `/tmp/skill-build-<id>/decisions.md`.
3. If spec is silent and pattern is `param` → pick safe default per this catalog, record rationale.
4. If spec is silent and pattern is `architectural` or `spec-locked` → **stop-and-ask** before scaffolding.

Never "skip an entry because it'll probably be obvious from context." The agent's discipline is: *"every entry that applies, every build, every time."* This is what makes autonomous builds safe.
