# Project: skill-builder & skills-agent

**Status:** Active. Methodology + dispatch path proven through Phase 6 (2026-05-04). Patch-mode dispatch not yet empirically validated end-to-end.

The architecture for scaling skill creation: Dave + Claude plan a spec at the laptop → Bishop dispatches a skills-agent (registered sub-agent) → agent autonomously builds the skill following a frozen methodology.

---

## Where the work lives

- `~/.openclaw/workspace/skills/skill-builder/` — the methodology pack (SKILL.md, METHODOLOGY.md, SPEC_TEMPLATE.md, DECISION_POINTS.md, examples/)
- `~/.openclaw/workspace-skills-agent/` — the registered sub-agent (its own workspace; `.gitignored`; recreate fresh on the Mini)
- `~/.openclaw/agents/skills-agent/` — agent shell config (SYSTEM_PROMPT.md, DISPATCH.md)
- `~/.openclaw/workspace/AGENTS.md` § Skills-Agent Dispatch — Bishop's dispatch protocol
- `~/.openclaw/workspace/.claude/` — PreToolUse hook structurally enforcing "no in-session edits to skill code"

---

## Phases shipped

| Phase | Date | Outcome |
|---|---|---|
| 1 — Methodology skill | 2026-05-03 | 4 principles + 8-step build sequence + spec template + decision-points catalog |
| 2 — Agent shell | 2026-05-03 | skills-agent registered; Bishop dispatch protocol added |
| 3 — Paddle-board validation | 2026-05-04 | First real skill built via dispatch; 3 rounds (rounds 1-2 failed structurally, round 3 succeeded) |
| 4 — Refactor (1) | 2026-05-04 | First tried `bash background:true claude --print` (coding-agent pattern) |
| 5 — Refactor (2) | 2026-05-04 | Re-refactored to native `sessions_spawn(agentId: skills-agent)` — coding-agent pattern was for *external* CLIs; ours is a registered sub-agent |
| 6 — Iteration mode + enforcement | 2026-05-04 | Build/patch modes with shared methodology; install-with-preview pattern; PreToolUse hook |

---

## Key decisions (don't re-litigate)

1. **Bishop never edits skill files in-process.** Even one-line "obviously correct" patches dispatch via skills-agent. Trust model is structural: Haiku for orchestration, stronger model for code. PreToolUse hook enforces this. (See `feedback_code_changes_via_skills_agent` reasoning.)
2. **Dave + Claude planning produces the SPEC and stops.** Don't dispatch from the laptop CLI. Bishop dispatches. Spec lives at `workspace/specs/<skill-name>.md`. (See `feedback_spec_planning_role` reasoning.)
3. **Compose-first applies to us too.** Before building any orchestration/dispatch infrastructure, survey bundled openclaw skills (`/opt/homebrew/lib/node_modules/openclaw/skills/`, `dist/extensions/*/skills/`). We hand-rolled patterns that already existed.
4. **Install-with-preview gate.** Every skill with external writes installs in preview mode (typically `--no-apply` flag in cron payload). Dave reviews preview output, says "go", Bishop runs `enable-live.sh`. (METHODOLOGY Step 7.)
5. **Build vs patch dispatch differ.** Build dispatch spawns a worker against an empty target dir; patch dispatch pre-stages the existing skill in the worker's workspace, runs against it in place, no install step. Patch invariants: state preservation, install preservation, live-state preservation, surgical scope.
6. **Architectural lessons embedded in the methodology** (commit `9243abf`): cron schema reference, `--dry-send` vs `--no-apply` semantics, install-script smoke test, cost-tracking assertion. These four came out of YNAB's build bugs.

---

## What's *not* yet validated

- **Patch-mode dispatch end-to-end.** Bishop violated the no-in-session-edits rule twice on 2026-05-04 before the PreToolUse hook shipped. Hook now forces dispatch. The next patch is the validation.
- **Build → preview → live → ongoing maintenance loop** in production. We've done build + preview + first iteration cycle, but the long-tail "skill needs maintenance 3 months in" path is unproven.

---

## Open follow-ups

1. Validate patch-mode dispatch on the next real patch (post-migration). The PreToolUse hook forces the path; observe whether the dispatch is clean.
2. Promote "Cron + Python script execution pattern" to `skill-builder/DECISION_POINTS.md` as a known recipe.
3. Re-survey openclaw's bundled skills periodically — the ecosystem is moving and we've reinvented patterns once already.

---

## Why this matters

Dave wants to plan skills untethered (iMessage from phone, away from laptop) and have Bishop dispatch builds while he's elsewhere. The methodology + agent + dispatch is that bootstrap. Once stable, every new skill is a planning conversation → spec → dispatch → iMessage updates.

---

## References

- Methodology: `workspace/skills/skill-builder/METHODOLOGY.md`
- Worked example: `workspace/skills/skill-builder/examples/job-search-spec.md`
- Dispatch protocol: `workspace/AGENTS.md` § Skills-Agent Dispatch
- Bundled patterns to compose with: `/opt/homebrew/lib/node_modules/openclaw/skills/coding-agent/SKILL.md`, `dist/extensions/acpx/skills/acp-router/SKILL.md`
- Related projects: [job-search](../job-search/CONTEXT.md) (first methodology subject), [bishop-identity](../bishop-identity/CONTEXT.md) (cron `bestEffort` workaround we're about to remove)
