# `hello-skill` Skill Spec

**Spec version:** 1
**Authored:** 2026-05-04 by Dave + Claude (planning session)
**Author notes:** Smoke test for the refactored skills-agent dispatch pipeline (post-coding-agent-pattern refactor). The skill itself is intentionally trivial — its job is to validate the dispatch + worker + notification end-to-end, not to deliver real value. After the smoke test passes, this skill can be deleted (or kept as a "say hi" toy).

## 1. Elevator pitch

A one-shot CLI that sends Dave a short iMessage greeting. Tunable greeting tone (formal / casual / dry-humor) and target route. Used as the dispatch-pipeline smoke test on 2026-05-04; thereafter, optionally retained for ad-hoc "ping me" use.

## 2. Trigger

- **Mode:** on-demand
- **Schedule:** N/A — no cron / no launchd
- **Hook source:** N/A
- **On-demand invocation:** `python3 ~/.openclaw/workspace/skills/hello-skill/scripts/hello.py` (or with `--dry-send` to compose without delivering)

## 3. Composes with

| Capability needed | Existing skill to reuse | Reason |
|---|---|---|
| Outbound iMessage | `openclaw message send --channel bluebubbles --target 'iMessage;-;otte.dave@gmail.com'` | The route validated by refurb-alert + gh-notify transforms; email-keyed handle avoids the Bishop-Apple-ID identity collision. |
| Per-run JSONL logging | `alert-circuit` and `job-search` skills' logging convention | Same `logs/run-<iso>.jsonl` pattern used by every other skill — agent already understands it. |

**Build new:**
- Greeting composer (3 short tone variants, one-liner each) — too small to be its own skill, lives inline in `scripts/hello.py`.

## 4. Pipeline

| # | Hop | Input | Output | Notes |
|---|---|---|---|---|
| 1 | `config_load` | `config.json` | parsed config dict | Halt with clear error if file missing or required keys absent |
| 2 | `compose_greeting` | tone + template from config | greeting text string | Pure-function; no side effects |
| 3 | `deliver` | greeting + route from config | confirmation (or `delivery_skipped` event in dry mode) | Calls `openclaw message send` via subprocess; halt on non-zero exit; skipped under `--dry-send` |
| 4 | `done` | — | exit 0 | Final JSONL line |

## 5. Architectural commitments (LOCKED)

- **Data source / external API:** none (no fetch hop; greeting is composed locally from config)
- **Output channel:** iMessage via `openclaw message send --channel bluebubbles`
- **Storage backend:** N/A — stateless skill, no dedup needed (it's a one-shot ping)
- **Output schema:** N/A — output is a single iMessage text message, no structured payload
- **Auth dependencies:** none (BlueBubbles is already configured for Bishop's host)
- **Cost model:** free (no paid API calls; BB Mac app does the actual send)
- **Failure semantics:** halt-on-error per hop. If `openclaw message send` exits non-zero, log `error` event and exit 1.
- **Unit conventions:** N/A (no units in this skill)

## 6. Initial parameters (TUNABLE)

| Parameter | Default | Surface | Rationale |
|---|---|---|---|
| `tone` | `dry-humor` | `config.json` | Matches Dave's preferred conversational register per `user_dave.md`; `formal` and `casual` are alternates. |
| `greeting_template` | `"Hello, Dave. {tone_clause} Skill-builder smoke test passed at {hhmm} {tz}."` | `config.json` | Template-string format with `{tone_clause}` and `{hhmm}` / `{tz}` substitutions; lets Dave reword without code edits. |
| `target_channel` | `bluebubbles` | `config.json` | The proven channel; native `imessage` is experimental. |
| `target_recipient` | `iMessage;-;otte.dave@gmail.com` | `config.json` | Email-keyed handle; avoids identity collision until Bishop Identity Track ships. |
| `tone_clauses` | `{"formal": "Greetings.", "casual": "Hey there.", "dry-humor": "Reporting for duty in the most low-stakes possible way."}` | `config.json` | One short clause per tone; selected by `tone` value. |
| `cli_dry_send_flag` | `--dry-send` | `scripts/hello.py` argv | Standard convention used by other skills. |

## 7. Tuning surface

- `~/.openclaw/workspace/skills/hello-skill/config.json` — tone, template, route, tone clauses
- `~/.openclaw/workspace/skills/hello-skill/scripts/hello.py` — only edit if Dave wants to add a hop or change CLI behavior
- `--dry-send` flag — runtime override for "compose but don't deliver"

## 8. Success criteria

**Dry fires (×3) must pass when:**
- `triggered`, `config_load`, `compose_greeting`, `delivery_skipped`, `done` events appear in order in `logs/run-<iso>.jsonl`
- No `error` events
- The composed greeting is a non-empty string with the expected substitutions
- Exit code 0
- No actual iMessage is sent (verified by absence of `delivery_sent` event)

**Real fire must pass when:**
- The same events appear except `delivery_skipped` is replaced by `delivery_sent` with the BlueBubbles response captured
- An iMessage is delivered to `iMessage;-;otte.dave@gmail.com` containing the composed greeting
- `openclaw message send` exits 0 (subprocess captured)
- Exit code 0
- Run cost: $0 (no paid API calls)

**Bishop validation must pass when:**
- Reading SKILL.md tells Dave how to invoke + tune
- Bishop can answer "did the smoke test work?" by tailing the latest log

## 9. Cost ceiling

| | |
|---|---|
| Per-run target | $0.00 |
| Per-run hard cap | $0.00 (no paid APIs called by the skill itself) |
| Monthly projection | $0.00 |
| Free-tier APIs | BlueBubbles local REST (no $) |
| Paid APIs | none |

The *build itself* (the worker spawned to scaffold this skill) costs ~$1-2 in worker tokens. That's a one-time cost, not a recurring run cost.

## 10. Logging & forensics

Log path: `~/.openclaw/workspace/skills/hello-skill/logs/run-<iso>.jsonl`

Required event types:
- `triggered` — entry; fields: `dry_send` (bool), `argv`
- `config_load` — fields: `path`, `tone`, `target_channel`, `target_recipient`
- `compose_greeting` — fields: `tone_clause`, `final_text` (truncated to 200 chars)
- `delivery_skipped` (dry only) — fields: `would_send`
- `delivery_sent` (real only) — fields: `bb_exit_code`, `bb_stdout` (truncated)
- `error` — fields: `hop`, `message`, `traceback`
- `done` — fields: `exit_status`

## 11. Test harness expectations

- `scripts/test.py` runs 3 dry + 1 real fire in sequence
- Dry mechanism: `--dry-send` CLI flag; `delivery_skipped` event replaces `delivery_sent`; no `openclaw message send` subprocess call
- State reset: N/A (stateless skill — no dedup state to reset between runs)
- Real fire is final; if any dry fails, real does NOT run
- Test harness emits its own `logs/test-<iso>.jsonl` with per-fire status

## 12. Known follow-ups / out of scope

- N/A — this skill is intentionally minimal. Anything beyond "send a hello" belongs in a different skill.

## 13. Dispatch instructions for the skills-agent

When this spec is handed to the skills-agent, the worker should:

1. Load `~/.openclaw/workspace/skills/skill-builder/SKILL.md` and the docs it points to.
2. Read this spec in full.
3. Execute the build per `METHODOLOGY.md` step sequence.
4. Stop-and-ask is NOT expected for this build — every architectural decision is locked above. If the worker hits an ambiguity anyway, follow the stop-and-ask protocol in SYSTEM_PROMPT.md (write question file + iMessage Dave directly).
5. Write a build summary to `/tmp/skill-build-<id>/summary.md` per methodology Step 8.
6. Notify Dave directly via `openclaw message send` when done. Bishop is bookkeeper, not relay.

**Build identity:** `skill-build-hello-skill-<YYYYMMDD>-<HHMM>`

**Skill destination:** `~/.openclaw/workspace/skills/hello-skill/`

---

## Author's notes

- This is the first dispatch under the post-refactor pipeline (coding-agent pattern via `bash background:true claude --print`).
- The skill is deliberately trivial so any failure points to the dispatch infrastructure, not the methodology.
- Dave will receive **two iMessages** as part of the smoke test: (a) the real-fire greeting from the skill itself, and (b) the worker's completion notification. Both are expected.
- After this spec validates the pipeline, the skill can be retained as a toy or deleted. No production system depends on it.
