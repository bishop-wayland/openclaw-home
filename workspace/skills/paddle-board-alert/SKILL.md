---
name: paddle-board-alert
description: Daily 5 AM check of the morning wind forecast at Waverly Park, Kirkland. If wind stays at or below the configured threshold (default 8 mph) across the 6-9 AM window, Dave gets an iMessage. On bad-wind days, silence — absence of the message IS the no-go signal. Suppress-on-bad is intentional; do not "fix" it to always-fire without asking Dave first. Composes conceptually with alert-circuit (same chatGuid + tone) but mechanically uses the openclaw-cron + exec-tool + BB-direct flavor (announce path is suppressed by the exec tool call). Use when Dave says "check the paddle forecast", "is it a paddle morning?", "what's the wind look like?", or asks anything about tuning the threshold/window/location.
---

# Paddle-Board Alert

Bishop's morning go/no-go signal for Dave's Lake Washington paddle days.

## What this skill does

At 5 AM PT every day, openclaw cron fires an `agentTurn` (Haiku) with `tools: ["exec"]`. Haiku's only job is to call the exec tool with:

```
python3 ~/.openclaw/workspace/skills/paddle-board-alert/scripts/check.py --real-send
```

The Python pipeline:

1. **load_config** — reads `config.json` (location, threshold, window).
2. **fetch_forecast** — Open-Meteo `/v1/forecast` (free, no auth) → 24 hours of `wind_speed_10m` for today, in mph, local PT time.
3. **evaluate_window** — pulls hours [`window_start`, `window_end`) from the forecast, finds max wind. Decision = `go` if max ≤ threshold else `no-go`.
4. **deliver_or_suppress** — on `go` + `--real-send`: POSTs an iMessage directly to BlueBubbles (`/api/v1/message/text`, chatGuid `iMessage;-;otte.dave@gmail.com`). On `no-go`: silence (logs `suppressed`).

Stateless. No dedup. Each day's check is independent.

## Why this skill diverges from alert-circuit's announce flavor

The alert-circuit invariant *"no tool calls in the cron-style agent path"* applies to the announce/deliver flow specifically. This skill needs `tools: ["exec"]` to run the Python forecast pipeline — which by design suppresses the announce path. Skills that use `--tools exec` MUST handle delivery from inside the script; that's exactly the pattern job-search uses with launchd, and what `scripts/deliver.py` here implements (BB-direct POST). It's the same end-to-end shape, adapted to the openclaw cron entrypoint rather than launchd.

The chatGuid (`iMessage;-;otte.dave@gmail.com`, email-keyed, never phone-keyed) and the message-tone conventions ARE the alert-circuit reuse.

## When Dave invokes Bishop

- **"Check the paddle forecast" / "is it a paddle morning?" / "what's the wind look like?"** — Bishop runs `python3 ~/.openclaw/workspace/skills/paddle-board-alert/scripts/check.py` (no `--real-send` flag → dry mode, no iMessage). Returns the decision, max wind in window, and (on go-days) the would-have-sent text. Cost: $0, sub-2-second response.
- **"Send me the paddle alert if it's a go-day"** — `python3 .../check.py --real-send`. Same pipeline, actually delivers iMessage on go-days, silent on no-go.
- **"Tune the threshold to 10"** — edit `config.json` → `threshold_mph`. Next cron pick-up uses the new value (no restart needed; config is read on every invocation).
- **"Move the window to 7-10 AM"** — edit `config.json` → `window_start_hour: 7`, `window_end_hour: 10`.
- **"Change the location to <X>"** — edit `config.json` → `location.{name, latitude, longitude}`. Latitude/longitude can be looked up on Google Maps; the `name` is just for the message.
- **"Why didn't I get a paddle alert today?"** — `tail -1 ~/.openclaw/workspace/skills/paddle-board-alert/logs/run-*.jsonl | jq` shows the most recent decision. If `decision: "no-go"`, that's why (and the `evaluated.max_wind_in_window` shows how close it got). If there's an `event: error` line, the upstream API was down or some other hop failed.
- **"Move the cron fire time to 4:30 AM"** — edit the entry in `~/.openclaw/cron/jobs.json` (skill is registered as `paddle-board-alert`); change the cron expression. Or use `openclaw cron edit`.

## File map

| File | Purpose |
|---|---|
| `SKILL.md` | this file |
| `config.json` | tunable knobs (location, threshold, window, message template) |
| `scripts/check.py` | main pipeline orchestrator (4 hops) |
| `scripts/deliver.py` | BB-direct iMessage send (reads creds from `~/.openclaw/openclaw.json`) |
| `scripts/logger.py` | per-hop JSONL logger (line-buffered) |
| `scripts/test.py` | three-fires verification harness |
| `scripts/install-cron.sh` | adds the openclaw cron entry to `~/.openclaw/cron/jobs.json` |
| `scripts/uninstall-cron.sh` | removes the cron entry |
| `logs/run-*.jsonl` | per-run forensic trace |

## Composes with

- **alert-circuit** (conceptually) — chatGuid convention, message tone, three-fires-before-stable testing discipline.
- **job-search** (mechanically) — `logger.py` shape, three-fires harness shape, BB-direct delivery pattern (just adapted from launchd to openclaw cron).
- **openclaw cron** — the trigger registry. Entry lives in `~/.openclaw/cron/jobs.json`.
- **BlueBubbles** — iMessage delivery. Server URL + password live in `~/.openclaw/openclaw.json` → `channels.bluebubbles`.

## Cost

- **Per run:** $0.00 (Open-Meteo is free, no API key; BB delivery is free; Haiku turn is the only paid call and it's just "call exec with this exact command" — sub-cent token cost).
- **Monthly (daily cadence × 30):** ~$0.01 in token cost from the trivial Haiku turns. Effectively free.

## Tuning surface (where Dave will iterate)

1. **`config.json`** (most-edited) — threshold, location, window hours, message wording.
2. **`~/.openclaw/cron/jobs.json`** — fire time (default `0 5 * * *` PT).
3. **`scripts/check.py`** — only edit if changing pipeline shape (adding gust threshold, multi-day forecast, wind-direction filter, etc. — all listed as v2 follow-ups).

## Testing

The three-fires harness is the contract:

```
python3 ~/.openclaw/workspace/skills/paddle-board-alert/scripts/test.py
```

Runs 3 dry fires (real Open-Meteo fetch, no iMessage send) followed by 1 real fire. If any dry fails, the real fire does NOT run. The real fire's outcome depends on the actual current forecast — silence on no-go is still PASS; iMessage delivery is required on go.

After a real go-day fire, verify the iMessage actually landed on Dave's iPhone before declaring the build stable.

## Known follow-ups (out of v1 scope)

- Always-fire mode (verbose "no-go" message). Suppress-on-bad is the v1 default.
- Multi-day forecast ("the next paddle window is Thursday morning").
- Wind-direction filter (offshore vs. onshore).
- Gust handling (Open-Meteo has `wind_gusts_10m`; v1 only checks sustained wind).
- Subjective conditions (temp, precipitation, sunrise time).
