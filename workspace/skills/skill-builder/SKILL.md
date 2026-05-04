---
name: skill-builder
description: The methodology for designing and building a new openclaw/Bishop skill end-to-end. Loaded by Dave + Claude during planning sessions, and by the skills-agent during autonomous builds. Use when (a) Dave says "let's plan a new skill", (b) you need to draft a SPEC_TEMPLATE.md for a new skill, (c) you've been dispatched as the skills-agent and need to know how to proceed, or (d) you need to remember the parameterize-by-default / compose-first / stop-and-ask principles that make autonomous builds safe.
---

# Skill Builder

The reusable knowledge pack for creating new openclaw/Bishop skills. Distilled from the end-to-end build of `job-search` (2026-05-02 → 2026-05-03), which validated the methodology across two phases (Layer 1 deterministic + Layer 2 web_search).

## When this skill is loaded

Three contexts load it:

1. **Dave + Claude planning at the laptop.** Goal: produce a complete `SPEC_TEMPLATE.md`-shaped doc for a new skill. Output goes to `~/.openclaw/specs/<skill-name>.md`.
2. **The skills-agent (`agents/skills-agent/`), dispatched by Bishop.** The agent loads this skill as its first action on any new build. Methodology in this skill is the agent's playbook.
3. **Bishop, ad-hoc.** If Dave asks Bishop directly "what would building a `foo` skill involve?" Bishop can load this for context. (Bishop should *not* execute builds himself — dispatch the agent.)

## What's in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | this file — entry point + when to load |
| `METHODOLOGY.md` | principles + happy-path build sequence + what-not-to-do |
| `SPEC_TEMPLATE.md` | the shape of a complete spec doc; copy-and-fill for each new skill |
| `DECISION_POINTS.md` | catalog of common decision categories tagged param-or-architectural |
| `examples/job-search-spec.md` | reverse-engineered worked example — the spec that *would have* produced what we built |

Read order: `SKILL.md` → `METHODOLOGY.md` → `DECISION_POINTS.md` → `SPEC_TEMPLATE.md` → `examples/job-search-spec.md` for grounding.

## Core principles (the four loadbearing rules)

These are stated in full in `METHODOLOGY.md`. Summary:

1. **Parameterize-by-default.** Every decision point starts as a tunable parameter (file, flag, config) with a safe opinionated default. Only commit to architectural choices when the decision would cascade into prompt/code rewrites.
2. **Compose-first.** Before scaffolding, search `~/.openclaw/workspace/skills/` for patterns that already solve part of the problem. Reuse first, build new only when no fit exists. (Job-search reuses `gog`. A paddle-board alert should reuse `alert-circuit`.)
3. **Stop-and-ask, don't silently guess.** For architectural decisions not committed in the spec, the agent halts and asks via the failure path (`sessions_send` to Bishop → iMessage Dave → resume). Silent guesses are forbidden.
4. **Three-fires harness is non-negotiable.** Every skill ships with `scripts/test.py` that runs 3 dry + 1 real fires before calling the build done. The harness is what catches integration bugs the unit tests miss.

## Skill invocation patterns

### Dave + Claude planning (laptop)

```
Dave: "let's plan the paddle-board alert skill"
Claude: [loads skill-builder] → [opens SPEC_TEMPLATE.md side-by-side] →
        walks through each section with Dave, asks the architectural questions,
        proposes parameter defaults, captures tuning surface
Output: ~/.openclaw/specs/paddle-board-alert.md
```

### Skills-agent autonomous build (dispatched by Bishop)

```
Bishop: sessions_spawn(runtime: "acp", task: "<system prompt> + <spec contents> + <return instructions>")
Agent: [loads skill-builder as first action] →
        [follows METHODOLOGY.md hop by hop] →
        [stops-and-asks at any architectural decision not in spec] →
        [runs three-fires harness] →
        [writes /tmp/build-summary-<id>.md] →
        [sessions_send Bishop "done, summary at <path>"]
Bishop: reads summary, iMessages Dave the result.
```

## What the skill is NOT

- Not a code generator. The methodology specifies the *pattern*; the agent (or Claude in conversation) writes actual code that fits the spec.
- Not a substitute for spec planning. The agent cannot build from a thin or ambiguous spec — it'll stop-and-ask, which surfaces the missing planning.
- Not Bishop's playbook for *delivering* alerts. That's `alert-circuit`. Skill-builder is about *building* skills, not running them.

## Composes with

- `agents/skills-agent/` — the deployable wrapper that loads this skill and executes a build autonomously.
- `~/.openclaw/specs/<name>.md` — the per-skill spec, conformant to `SPEC_TEMPLATE.md`.
- Existing skills (`alert-circuit`, `gog`, `job-search`) — sources of compose-first reuse patterns.

## Origin

Distilled 2026-05-03 from the job-search end-to-end build. The build itself was the methodology test; this skill is the post-hoc codification so the next build doesn't have to rediscover the patterns.

The first real test of *this skill* is the paddle-board alert build — see `~/.openclaw/specs/paddle-board-alert.md` (forthcoming) and the agent dispatch.
