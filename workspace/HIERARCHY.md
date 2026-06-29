# Workspace Hierarchy

What lives where, and why. This is the source of truth for organizing files under `~/.openclaw/`. When in doubt, check here before inventing a new location.

**Validated against:** openclaw docs (docs.openclaw.ai), openclaw 2026.4.27, audit `2026-05-21`.

---

## The foundational split

openclaw draws a hard line between **state** and **workspace**:

| Tree | Owner | Purpose |
|---|---|---|
| `~/.openclaw/` (state dir) | openclaw | Config, credentials, sessions, channel state, agent runtime |
| `~/.openclaw/workspace/` | agent (Bishop) | Identity, memory, skills, projects — the agent's home |

Don't put Bishop content at the state-dir level. Don't put openclaw runtime data inside the workspace. If you're unsure which a file is, default to workspace.

---

## State dir layout (openclaw-managed)

```
~/.openclaw/
├── openclaw.json              # main config (JSON5)
├── .env                       # OP_SERVICE_ACCOUNT_TOKEN etc.
├── credentials/               # channel auth (whatsapp, telegram, bluebubbles)
├── agents/<agentId>/          # per-agent runtime state
│   ├── agent/                 # auth-profiles.json, codex-home, etc.
│   └── sessions/              # session ledgers
├── cron/
│   ├── jobs.json              # cron definitions
│   └── jobs-state.json        # runtime execution state (gitignore)
├── hooks/                     # managed hooks + transforms/
├── logs/                      # commands.log, gateway logs
├── plugins/                   # installed plugin packages
├── settings/                  # tts.json, etc.
├── skills/                    # globally-installed skills (--global flag)
├── scripts/                   # user secrets-fetch wrappers (op-*.sh) — referenced by openclaw.json
└── sandboxes/                 # sandbox workspaces (if sandbox mode on)
```

**Do not touch** the openclaw-managed dirs above unless you know what you're doing. `openclaw doctor` will tell you if any are wrong.

**User-touchable but state-level:** `scripts/`, `.env`. Both are referenced by `openclaw.json`.

---

## Workspace layout (Bishop's home)

```
~/.openclaw/workspace/
├── AGENTS.md           # operating instructions + memory usage
├── SOUL.md             # persona / tone / boundaries
├── USER.md             # who Dave is
├── IDENTITY.md         # agent name / vibe / emoji
├── TOOLS.md            # local-tool guidance
├── HEARTBEAT.md        # optional heartbeat checklist
├── MEMORY.md           # curated long-term memory (auto-loaded in main session)
├── HIERARCHY.md        # this file
├── memory/
│   ├── YYYY-MM-DD.md   # daily notes (surfaced by startupContext)
│   ├── active-dispatches.md
│   └── inbox-queue.md
├── skills/             # workspace skills (precedence #1 for loader)
│   └── <skill-name>/
│       ├── SKILL.md    # required, with YAML frontmatter
│       ├── scripts/
│       ├── config.json
│       ├── state/      # runtime — gitignore
│       └── logs/       # runtime — gitignore
├── projects/           # human+agent collaboration
│   ├── <project-name>/
│   │   └── CLAUDE.md   # entry point — "load project <name>" reads this; Claude Code auto-loads on cwd
│   └── archive/        # completed / abandoned
├── specs/              # skill specs (input to skills-agent dispatch)
│   └── <skill-name>.md # versioned via git, not filename
└── .claude/            # Claude Code runtime config (PreToolUse hook etc.)
    ├── settings.json
    └── hooks/
```

### Bootstrap basenames (the recognized identity files)

`AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`, `HEARTBEAT.md`, `MEMORY.md`, `BOOTSTRAP.md` — openclaw seeds these on `openclaw onboard` and recognizes them automatically. **Live at workspace root, nowhere else.**

### Skills

- One dir per skill under `workspace/skills/<name>/`.
- Each skill **must** have `SKILL.md` with YAML frontmatter (at minimum `name` + `description`; gating + installer hints under `metadata.openclaw`).
- No `config.json` requirement — that's a per-skill convention if useful.
- Skill loader precedence: `<workspace>/skills` → `<workspace>/.agents/skills` → `~/.agents/skills` → `~/.openclaw/skills` → bundled → `skills.load.extraDirs`.
- Globally-installed skills (via `openclaw skills install --global`) live at `~/.openclaw/skills`, not in the workspace.

### Projects

- One dir per project under `workspace/projects/<project-name>/`.
- **Entry point convention:** `CLAUDE.md` is the project root doc. When Dave says "load project X", the assistant reads `workspace/projects/X/CLAUDE.md`. Claude Code also auto-walks-up from cwd to load CLAUDE.md, so launching `claude` from inside a project dir loads it implicitly.
- Additional project files (plans, references, working docs) live alongside `CLAUDE.md`.
- Completed or abandoned projects move to `workspace/projects/archive/<name>/`.

### Specs

- Skill specs (the design docs handed to skills-agent for autonomous builds) live at `workspace/specs/<skill-name>.md`.
- **Kept out of `skills/<name>/`** so the skill loader doesn't try to load them as skills.
- Versioned via git. No `v1.md`/`v2.md` filename scheme.
- Patches (post-v1 spec changes) live in the same file — git diff is the history.

### Memory

- `MEMORY.md` — auto-injected in main private session only (not group chats).
- `memory/YYYY-MM-DD.md` — daily logs; surfaced via `startupContext` for the last N days (`dailyMemoryDays` config).
- Both are openclaw conventions, not user-invented.

---

## Multi-agent: sibling workspaces

Each non-main agent gets its own workspace at `~/.openclaw/workspace-<name>/`, registered via `agents.list[].workspace` in `openclaw.json`.

```
~/.openclaw/
├── workspace/              # Bishop (main agent)
└── workspace-skills-agent/ # skills-agent
    ├── AGENTS.md SOUL.md … # its own identity files (same convention)
    └── skills/             # its own skill set (often just skill-builder)
```

The sub-agent runtime model: openclaw injects only `AGENTS.md` + `TOOLS.md` from a sub-agent's workspace during a sub-agent session. The other identity files exist for direct/standalone runs of that agent.

**Anti-pattern:** putting identity files in a subdirectory of the main workspace (e.g., `workspace/skills-agent/AGENTS.md`). Use the sibling workspace pattern.

---

## Anti-patterns (don't)

| Don't | Why |
|---|---|
| Put identity files in `workspace/<name>/` | Use sibling `workspace-<name>/` at state-dir level |
| Put specs inside `workspace/skills/<name>/` | Skill loader will try to load them |
| Put project docs at workspace root | Use `workspace/projects/<name>/` |
| Put loose Python scripts at workspace root | Move into the skill or project they belong to |
| Invent `~/.openclaw/<thing>/` dirs at state-dir level | Probably belongs in workspace |
| Filename-versioning (`v1.md`, `v2.md`) for any doc | Git tracks history. One canonical filename per doc. |
| Duplicate skill copies across workspaces | Each agent loads from its own workspace; if both need the skill, decide which agent owns it |

---

## Migration & multi-machine

To move openclaw between machines: copy `~/.openclaw/` whole, run `openclaw doctor` on the new host, run `openclaw gateway restart`. Channel state (BlueBubbles pairing, OAuth tokens) survives the copy. See `projects/mac-mini-migration/CLAUDE.md` for our specific cutover, which is *not* a clean copy because we're also transitioning identity (new phone, new gmail, new Apple ID).

---

## References

- openclaw docs: `docs.openclaw.ai/concepts/agent-workspace`, `/tools/skills`, `/help/faq`
- openclaw version validated: 2026.4.27
- Audit conducted: 2026-05-21
