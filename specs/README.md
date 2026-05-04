# Skill Specs

This directory holds the *spec docs* that get handed to the skills-agent for autonomous skill builds.

## Naming convention

`<kebab-case-skill-name>.md` — matches the skill's eventual directory name in `~/.openclaw/workspace/skills/<skill-name>/`.

Examples:
- `paddle-board-alert.md`
- `morning-git-digest.md`
- `ynab-autocategorize.md`

## Lifecycle

1. **Author** — Dave + Claude produce a spec at the laptop using `~/.openclaw/workspace/skills/skill-builder/SPEC_TEMPLATE.md`. Output saved here.
2. **Dispatch** — Dave iMessages Bishop the path. Bishop reads spec, composes task, calls `sessions_spawn` (see `~/.openclaw/agents/skills-agent/DISPATCH.md`).
3. **Build** — skills-agent reads spec, loads skill-builder skill, follows methodology, writes summary to `/tmp/skill-build-<id>/summary.md`.
4. **Tune** — Dave iterates on the built skill via files in `~/.openclaw/workspace/skills/<skill-name>/`. The spec stays here as the historical record of v1 intent.

## What lives here vs. elsewhere

- **`~/.openclaw/specs/<name>.md`** — the spec (historical, immutable after build)
- **`~/.openclaw/workspace/skills/<name>/`** — the built skill (the running artifact)
- **`~/.openclaw/workspace/skills/skill-builder/`** — the methodology (the recipe)
- **`~/.openclaw/agents/skills-agent/`** — the agent shell (system prompt + dispatch reference)
- **`/tmp/skill-build-<id>/`** — per-build summaries / questions / failure analyses (ephemeral)

## Modifying a spec post-build

Don't edit a spec after the build to "fix" it. The spec is the historical contract. If you want to change the skill, edit the skill's files directly (criteria.md, config.json, etc.) — that's the tuning loop.

If you want to *rebuild from a revised spec*, save it as `<name>-v2.md` and dispatch a new build with that. The old skill dir gets archived or wiped per your call.

## Empty by design

This directory starts empty. The first spec to land here should be `paddle-board-alert.md`, the live test of the methodology.
