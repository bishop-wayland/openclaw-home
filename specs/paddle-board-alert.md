# `paddle-board-alert` Skill Spec

**Spec version:** 1
**Authored:** 2026-05-03 by Dave + Claude (planning session)
**Author notes:** Dave paddle-boards on Lake Washington from Waverly Park in Kirkland. He wants a daily morning go/no-go signal so he can plan the day around it without checking the forecast manually. The skill fires at 5 AM, checks the morning forecast, and only messages on go-days — silence is the no-go signal. This is also the first behavioral test of the skill-builder methodology + skills-agent dispatch path. Composes with `alert-circuit` for iMessage delivery; that composition is itself part of the test (does the agent reuse alert-circuit's cron flavor instead of reinventing the iMessage stack?).

## 1. Elevator pitch

Daily 5 AM check of the morning wind forecast at Waverly Park, Kirkland. If wind stays at or below 8 mph from 6:00 AM through 9:00 AM, Dave gets an iMessage saying it's a good paddle morning. On bad-wind days, silence — the absence of a message is the no-go signal.

## 2. Trigger

- **Mode:** openclaw cron
- **Schedule:** 5:00 AM local time (PT) daily
- **Hook source:** N/A
- **On-demand invocation:** *"Bishop, check the paddle forecast"* → Bishop runs `python3 ~/.openclaw/workspace/skills/paddle-board-alert/scripts/check.py` (or whatever the agent names it). Returns the go/no-go inline + would-have-sent message text.

## 3. Composes with

| Capability needed | Existing skill to reuse | Reason |
|---|---|---|
| Outbound iMessage to Dave's thread | `alert-circuit` (conceptually) + job-search-style BB-direct call (mechanically) | This skill needs `--tools exec` for the Python script, which suppresses alert-circuit's announce path. The Python script handles BB delivery directly — same pattern as job-search uses with launchd, adapted to openclaw cron. Read alert-circuit's SKILL.md for the chatGuid and tone conventions, then implement BB-direct delivery in Python. |
| 1Password secret fetch | N/A (no secrets needed — Open-Meteo requires no auth, BB creds in openclaw.json) | — |

**Build new:**
- Open-Meteo forecast fetch — simple HTTP GET, inline in the main script
- Threshold evaluation logic — domain-specific (windowed max-wind check)
- BB-direct delivery from Python — read the BB config from openclaw.json, POST to BB REST API. (Pattern is documented in Section 5; do not reinvent the chatGuid format or BB API shape.)

**Critical compose-first checkpoint:** when the agent reaches Step 3 of the methodology (scaffold), it MUST first read `~/.openclaw/workspace/skills/alert-circuit/SKILL.md` AND `EXAMPLES.md` AND `~/.openclaw/workspace/skills/job-search/scripts/deliver.py` (or equivalent) to understand the announce-vs-direct distinction. The architecture in Section 5 below explains why this skill diverges from alert-circuit's announce flavor. **The agent should NOT ask whether openclaw cron can run Python directly — it CAN'T, and the spec already specifies the work-around.**

## 4. Pipeline

| # | Hop | Input | Output | Notes |
|---|---|---|---|---|
| 1 | `load_config` | `config.json` | parsed config (location, threshold, window) | halts on missing/invalid |
| 2 | `fetch_forecast` | Open-Meteo URL with lat/long + variables | hourly forecast JSON for today | halt-on-error; no retry on first build (forecast is best-effort, silence on outage is acceptable) |
| 3 | `evaluate_window` | hourly forecast + threshold + window hours | `{decision: "go" \| "no-go", max_wind_in_window: float, hourly_breakdown: list}` | pure computation |
| 4 | `deliver_or_suppress` | decision + message template | iMessage delivered (on "go") or suppressed (on "no-go") | BB-direct delivery from Python (see Section 5 architecture). Suppression is just an early `done` event with `decision: "no-go"`. |

## 5. Architectural commitments (LOCKED)

- **Data source:** Open-Meteo Forecast API at `https://api.open-meteo.com/v1/forecast`. Free, no API key, no signup. Documented at https://open-meteo.com/en/docs.
  - Required query params: `latitude`, `longitude`, `hourly=wind_speed_10m`, `wind_speed_unit=mph`, `timezone=America/Los_Angeles`, `forecast_days=1`.
  - Response shape: `{hourly: {time: [...], wind_speed_10m: [...]}}` — arrays parallel-indexed.

- **Cron architecture (CRITICAL — pre-answered to prevent stop-and-ask):** OpenClaw cron has no native shell/Python exec payload kind — every cron job fires an `agentTurn` (a Haiku LLM session). To run the Python forecast check, the cron job MUST use this exact pattern:
  - **Cron entry shape:** `payload.kind: "agentTurn"`, `payload.tools: ["exec"]` (allowlist), `payload.message: "Run the paddle-board forecast check: python3 ~/.openclaw/workspace/skills/paddle-board-alert/scripts/check.py --real-send"`
  - **Haiku agent's job:** call the `exec` tool with the documented command. Nothing else. No interpreting, no prose, no announce/deliver.
  - **Python script's job:** owns the entire pipeline end-to-end — fetch Open-Meteo, evaluate the window, and on a "go" day, call BlueBubbles directly via HTTP POST to deliver the iMessage. Returns 0 on success.
  - **CRITICAL — do NOT use announce/deliver for iMessage:** alert-circuit's "no tool calls in cron path" invariant applies to the **announce/deliver flow** specifically. Tool calls (including `exec`) suppress the announce path. Skills using `--tools exec` to run scripts MUST handle delivery from inside the script (call BB directly), not by handing text back to the agent. This is the same end-to-end pattern as job-search uses with launchd, just adapted to openclaw cron.

- **BlueBubbles delivery from Python:** POST to the local BB REST API. The base URL + password are in `~/.openclaw/openclaw.json` under the BlueBubbles config key (the agent should read these at script startup). Use `chatGuid: "iMessage;-;otte.dave@gmail.com"` — phone-keyed sends collide with Bishop Identity Track (separate project). Do not put creds in the skill repo or in env files; read them from openclaw.json at runtime.

- **Output channel:** iMessage via direct BlueBubbles API call from the Python script. NOT via alert-circuit's announce path (announce is suppressed by the `exec` tool call). The skill still **composes with** alert-circuit conceptually — same output destination, same tone — but the delivery mechanism diverges from alert-circuit's announce-flavor cron pattern. Document this in SKILL.md so future maintainers don't think it's a methodology violation.

- **Storage backend:** none. Skill is stateless — each day's check is independent. No dedup, no run history beyond logs/.

- **Output schema:** N/A — internal evaluation produces a Python dict, no external schema needed since output is unstructured iMessage text.

- **Auth dependencies:** none for Open-Meteo. BlueBubbles credentials are read from existing `~/.openclaw/openclaw.json` (not a new 1Password item — these creds are already wired for Bishop's use).

- **Cost model:** $0 per run. Free API, free delivery via existing Bishop infrastructure.

- **Failure semantics:**
  - `load_config`: halt-on-error. No config = no skill.
  - `fetch_forecast`: halt-on-error, no retry. If Open-Meteo is down at 5 AM, that day's check is silently skipped (logs surface why; no iMessage sent). This is acceptable per "absence is the signal" UX.
  - `evaluate_window`: halt-on-error. Pure computation; should not fail unless data is malformed.
  - `deliver_or_suppress`: halt-on-error. If BB delivery fails on a "go" day, log surfaces it but Dave doesn't get the alert (acceptable — silence already meant "maybe no-go" in Dave's mental model).

- **Unit conventions:** mph for wind, local PT for the morning window + cron schedule, UTC for log timestamps, ISO-8601 for date strings.

## 6. Initial parameters (TUNABLE)

| Parameter | Default | Surface | Rationale |
|---|---|---|---|
| `location.name` | `"Waverly Park, Kirkland WA"` | `config.json` | display name in the iMessage; not used for forecast lookup |
| `location.latitude` | `47.6911` | `config.json` | Waverly Beach Park lat (approximate; Dave can refine) |
| `location.longitude` | `-122.2105` | `config.json` | Waverly Beach Park long (approximate; Dave can refine) |
| `threshold_mph` | `8.0` | `config.json` | Dave's go/no-go cutoff for paddle conditions |
| `window_start_hour` | `6` | `config.json` | morning paddle window starts 6 AM local |
| `window_end_hour` | `9` | `config.json` | morning paddle window ends 9 AM local (exclusive — checks hours 6, 7, 8) |
| `cron_fire_time` | `5:00 AM PT daily` | openclaw cron jobs.json | one hour before the window opens, so Dave can plan |
| `message_template` | `"☀️ Good paddle morning, Dave — wind staying under {threshold:.0f} mph through the 6–9 AM window at {location}. Max forecast: {max_wind:.1f} mph."` | `config.json` (or top of `check.py` constant) | Bishop's voice; bake in the actual numbers from the forecast |

## 7. Tuning surface

Where Dave will iterate post-build:

1. **`config.json`** — most-edited; threshold, location coordinates, window hours, message wording
2. **`~/.openclaw/cron/jobs.json`** — the cron entry for fire time (this is openclaw's central cron registry, not in the skill dir)
3. **Adding a `--always-fire` mode later** — currently suppress-on-bad; if Dave wants the verbose flavor, add it as a follow-up (out of v1 scope)

## 8. Success criteria

**Dry fires (×3) must pass when:**
- All 4 hops emit JSONL events in order
- No `event=error` lines
- `forecast_fetched` event present with `n_hours >= 24` and `units = "mph"`
- `evaluated` event present with a clear `decision: "go"` or `decision: "no-go"`
- On a "go" decision: `deliver_skipped` event present (dry mode skips iMessage)
- On a "no-go" decision: `suppressed` event present with reason
- `done` event present with `ok: true`

**Real fire must pass when:**
- The skill executes end-to-end without errors
- If the actual current forecast at run time would trigger "go": iMessage is delivered to Dave's phone with the correct text, max wind value, and location
- If the actual current forecast triggers "no-go": no iMessage sent, log shows `suppressed` with the reason

(NOTE: the real fire's outcome depends on real-time weather. The harness should NOT artificially force a "go" — it should run whatever the actual forecast says. If the day of the build happens to be a no-go day, the agent should iterate-test the "go" path by temporarily stubbing the forecast to a known-good value in a separate ad-hoc test, then revert. Document this iteration in the build summary if it happens.)

**Bishop validation must pass when:**
- Dave can read SKILL.md and answer: how to invoke now, how to tune, how to debug, where the cron entry lives
- Last log line of any run is `event=done, ok=true`
- Bishop's *"Bishop, check the paddle forecast"* invocation works on-demand and returns the would-have-sent message text

## 9. Cost ceiling

| | |
|---|---|
| Per-run target | $0.00 |
| Per-run hard cap | $0.01 (stop-and-ask if exceeded — should never happen) |
| Monthly projection (daily cadence × 30) | $0.00 |
| Free APIs | Open-Meteo Forecast API |
| Paid APIs | none |

## 10. Logging & forensics

JSONL log path: `~/.openclaw/workspace/skills/paddle-board-alert/logs/run-<iso>.jsonl`

Required event types:
- `triggered` — entry, with `dry_send` flag
- `config_loaded` — location, threshold, window hours
- `forecast_fetched` — `n_hours`, `units`, `forecast_for_date`
- `evaluated` — `max_wind_in_window`, `threshold`, `decision`, `hourly_breakdown` (e.g., `[{"hour": 6, "wind_mph": 4.2}, {"hour": 7, "wind_mph": 5.8}, {"hour": 8, "wind_mph": 7.1}]`)
- `delivered` (on "go" + real fire) — message text, delivery confirmation
- `deliver_skipped` (on "go" + dry fire) — would-have-sent text
- `suppressed` (on "no-go") — reason
- `error` (if any) — hop, message, traceback
- `done` — `ok` status, `decision`

## 11. Test harness expectations

- Three-fires (3 dry + 1 real)
- Dry mechanism: `--dry-send` flag — skips the actual iMessage send, emits `deliver_skipped` events, does NOT skip the forecast fetch (so dry runs validate the real upstream API)
- State reset: N/A (stateless)
- Real fire is final; if any dry fails, real does NOT run

The harness should print, after each fire:
- `decision = go | no-go`
- `max_wind_in_window = X.X mph`
- `threshold = 8.0 mph`
- `would_send = "<message text>"` (on "go" days, even in dry mode)

## 12. Known follow-ups / out of scope

- **Always-fire mode** — currently suppress-on-bad. v2 could add a verbose "no-go" message ("today's a no-go: 12 mph at 7 AM"). Dave decided suppress-on-bad keeps the iMessage thread clean.
- **Multi-day forecast** — only checks today. v2 could surface a 3-day "the next paddle window is Thursday morning" alert.
- **Wind direction filter** — paddle-boarders care about offshore vs. onshore wind. v2 could filter on direction.
- **Tide/wave checks for saltwater paddles** — N/A for Lake Washington but would matter if Dave paddled in Puget Sound. Out of scope for v1.
- **Gust handling** — currently only checks sustained wind (`wind_speed_10m`). Open-Meteo offers `wind_gusts_10m` too; v2 could add a gust threshold. v1 ignores gusts to keep evaluation simple.
- **Subjective conditions** — temperature, precipitation, sunrise time. Could enrich the iMessage but not part of go/no-go.

## 13. Dispatch instructions for the skills-agent

When this spec is handed to the skills-agent, the agent should:

1. Load `~/.openclaw/workspace/skills/skill-builder/SKILL.md` and the docs it points to.
2. Read this spec in full.
3. **Critical:** read `~/.openclaw/workspace/skills/alert-circuit/SKILL.md` and `EXAMPLES.md` before scaffolding. The cron-flavor iMessage pattern from alert-circuit MUST be reused; this is a compose-first test.
4. Execute the build per `METHODOLOGY.md` step sequence.
5. Stop-and-ask via `sessions_send` to Bishop on any architectural ambiguity not resolved here. Likely candidates:
   - The exact alert-circuit invocation pattern (cron job entry shape, message handoff)
   - Any Open-Meteo response field that doesn't match the documented shape (rare but possible)
6. Write a build summary to `/tmp/skill-build-paddle-board-alert-<YYYYMMDD>-<HHMM>/summary.md` per the methodology.
7. Notify Bishop via `sessions_send` when done or stuck.

**Build identity:** `skill-build-paddle-board-alert-<YYYYMMDD>-<HHMM>`

**Skill destination:** `~/.openclaw/workspace/skills/paddle-board-alert/`

---

## Author's notes

- The compose-first test is the most important thing this build validates. If the agent reads alert-circuit and reuses its pattern: methodology works. If the agent ignores alert-circuit and scaffolds iMessage from scratch: methodology has a gap that needs fixing in the skill-builder docs.
- Open-Meteo was chosen over OpenWeatherMap and NOAA NDBC because:
  - **OpenWeatherMap:** requires API key + signup; Dave doesn't have an account; auth setup is friction the methodology shouldn't require.
  - **NOAA NDBC:** authoritative but coastal-buoy-focused; sparse coverage for Lake Washington. Wrong tool for inland lake forecasts.
  - **Open-Meteo:** free, no auth, excellent Pacific Northwest coverage, simple JSON, returns wind in mph directly when asked. Right fit.
  - **NWS API:** also viable (free, no key) but requires a two-step lookup (gridpoint → forecast). Open-Meteo is one-step. Simpler.
- The Waverly Park coordinates (47.6911, -122.2105) are an estimate; Dave should refine after first build by checking against a map or by paddling and pinging GPS.
- Suppress-on-bad is a UX decision Dave explicitly chose. Note in SKILL.md so future-Dave (or future-Claude) doesn't second-guess it.
- The 5 AM fire time is one hour before the window opens. Tight enough to be relevant, late enough that the forecast is fresh.
- The alert-circuit cron flavor is canonical — the agent should literally add a cron entry to `~/.openclaw/cron/jobs.json` rather than installing a launchd plist. This is opposite of job-search (which uses launchd because it's a tool-using worker). Different rule, same methodology — see `DECISION_POINTS.md` "Cron mechanism" entry.
