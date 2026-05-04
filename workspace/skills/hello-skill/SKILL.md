---
name: hello-skill
description: Trivial smoke-test skill — sends Dave a one-line iMessage greeting via `openclaw message send` (BlueBubbles channel). Built on 2026-05-04 to validate the post-refactor skills-agent dispatch pipeline. On-demand only (no cron / no hook). Tunable greeting tone (formal / casual / dry-humor) and route. Use when Dave says "say hi", "ping me", "run the hello skill", or wants to verify the dispatch infrastructure is working end-to-end.
---

# Hello Skill

A deliberately trivial smoke-test skill: composes a short greeting and (optionally) delivers it to Dave via iMessage. Built as the validation fire for the skills-agent dispatch pipeline; retain as a "ping me" toy or delete after smoke-testing.

## What this skill does

```
python3 ~/.openclaw/workspace/skills/hello-skill/scripts/hello.py            # real send
python3 ~/.openclaw/workspace/skills/hello-skill/scripts/hello.py --dry-send  # compose only
```

Pipeline (4 hops):

1. **config_load** — reads `config.json` (tone, template, route, tone clauses). Halts on missing file or missing required keys.
2. **compose_greeting** — fills `greeting_template` with the chosen `tone_clause`, current local `{hhmm}`, and local `{tz}`.
3. **deliver** — `subprocess.run(["openclaw", "message", "send", ...])`. Skipped under `--dry-send` (emits `delivery_skipped` event instead).
4. **done** — emits `done` event with `exit_status`.

Stateless. No dedup. Each fire is independent.

## When Dave invokes Bishop

- **"Say hi" / "ping me" / "run the hello skill"** — Bishop runs `python3 ~/.openclaw/workspace/skills/hello-skill/scripts/hello.py`. Sub-second, $0, lands an iMessage.
- **"Test it without sending"** — `python3 .../hello.py --dry-send`. Shows the would-be greeting in the log without delivering.
- **"Change the tone to formal"** — edit `config.json` → `tone`: `"formal"`. (Also accepts `"casual"` and `"dry-humor"`.)
- **"Reword the greeting"** — edit `config.json` → `greeting_template`. Available substitutions: `{tone_clause}`, `{hhmm}`, `{tz}`.
- **"Add a new tone"** — edit `config.json` → add an entry to `tone_clauses` (e.g. `"haiku": "..."`), then set `tone` to that key.
- **"Send it to a different recipient"** — edit `config.json` → `target_recipient` (chat GUID, e.g. `iMessage;-;<email>` or `iMessage;-;<phone>`).
- **"Why didn't I get the hello?"** — `tail -1 ~/.openclaw/workspace/skills/hello-skill/logs/run-*.jsonl | jq` shows the last fire. If `event: error` is present, that hop's `traceback` field has the cause.

## File map

| File | Purpose |
|---|---|
| `SKILL.md` | this file |
| `config.json` | tone, template, route, tone clauses |
| `scripts/hello.py` | main pipeline (4 hops) |
| `scripts/logger.py` | per-hop JSONL logger (line-buffered, copied from paddle-board-alert) |
| `scripts/test.py` | three-fires verification harness |
| `logs/run-*.jsonl` | per-run forensic trace |
| `logs/test-*.jsonl` | per-harness-invocation summary |

## Composes with

- **`openclaw message send --channel bluebubbles`** — the validated outbound iMessage path; same chat GUID convention as `paddle-board-alert` and `alert-circuit` (email-keyed `iMessage;-;otte.dave@gmail.com`, never phone-keyed).
- **`paddle-board-alert/scripts/logger.py`** — JSONL logger shape, copied verbatim.
- **`paddle-board-alert/scripts/test.py`** — three-fires harness shape, adapted.

## Cost

- **Per run:** $0.00. No paid APIs. BlueBubbles is local; the Mac app does the actual send. CLI subprocess overhead only.
- **Monthly:** $0.00. Skill is on-demand and trivial.

The build itself (the worker that scaffolded this skill) was a one-time ~$1-2 token cost, not a recurring run cost.

## Tuning surface (where Dave will iterate)

1. **`config.json`** — tone, greeting wording, recipient, tone clauses. The only file you'll normally edit.
2. **`scripts/hello.py`** — only edit if you want to add a hop (e.g., randomize tone, vary by time of day).

## Testing

```
python3 ~/.openclaw/workspace/skills/hello-skill/scripts/test.py
```

Runs 3 dry fires (compose only, no iMessage) followed by 1 real fire (sends iMessage). If any dry fails, the real does NOT run. The real fire's outcome is verified by `delivery_sent.bb_exit_code == 0`; eyeball the iPhone to confirm the message landed.

`--no-real` flag skips the real fire entirely (3 dry only, useful for quick re-checks after editing config).

## Known follow-ups

- This skill is intentionally trivial. After validating the dispatch pipeline, it can be deleted, or kept as a "ping me / say hi" toy. No production system depends on it.
