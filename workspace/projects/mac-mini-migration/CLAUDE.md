# Mac Mini Migration

Move Bishop from a VM on Dave's laptop to a permanent Mac Mini, simultaneously transitioning identity (new Apple ID, phone, gmail, GitHub). Strategy: **cherry-pick clean install**, not whole-state-dir copy. Use the migration as the cleanup.

Supersedes the older `handoff/BISHOP-MIGRATION-CONTEXT.md` and `handoff/BOOTSTRAP.md`, which planned an Option-A whole-copy migration before we knew the openclaw conventions.

---

## Strategy

**Why not the documented "copy whole `~/.openclaw/` + run doctor" path:** that path preserves continuity. We don't want continuity — we want a clean identity transition and the chance to drop accumulated debris (stale duplicates, misplaced scripts, undocumented dirs). Cherry-picking forces every file to justify its trip.

**Sequence:**
1. Fresh openclaw install on the Mini (`openclaw onboard`)
2. Clone `~/.openclaw/workspace/` into place (with debris stripped before push)
3. Cherry-copy a small list of credentials and config
4. Run `openclaw doctor`, fix what it flags
5. Validate per phase, decommission VM

---

## Identity transition table

| | Old (VM) | New (Mini) |
|---|---|---|
| Apple ID | shared with Dave (collision) | Bishop's own |
| Phone | Dave's (+1-650-823-9528) | **+1-425-436-8004** (Bishop's own) |
| Gmail | bishopunit937@gmail.com | **yutani.w.bishop@gmail.com** |
| GitHub | none | **bishop-wayland** |
| Hardware | VM on laptop | Mac Mini (permanent) |

Dave's phone stays as the *delivery destination* in cron entries (`delivery.to: "+16508239528"`). Bishop's identity is what changes.

**Consequence:** `delivery.bestEffort: true` workaround in `cron/jobs.json` exists because of the old Apple ID collision. Root cause gone after migration — remove the flag on the Mini.

---

## Cherry-pick list

Keyed to [`workspace/HIERARCHY.md`](../../HIERARCHY.md). Files not listed don't cross.

### Workspace files — BRING

| Path | Notes |
|---|---|
| `workspace/AGENTS.md SOUL.md USER.md IDENTITY.md TOOLS.md HEARTBEAT.md MEMORY.md` | Identity + curated memory. Update gmail references during edit pass. |
| `workspace/HIERARCHY.md` | The doc that justifies the cleanup. |
| `workspace/memory/` (all daily logs + `active-dispatches.md`, `inbox-queue.md`) | History. Audit `active-dispatches.md` for stale DISPATCHED entries — delete those. |
| `workspace/skills/{alert-circuit, job-search, paddle-board-alert, skill-builder, ynab-categorize, hello-skill}/` | All 6 workspace skills. Strip `state/` and `logs/` subdirs (gitignored anyway). |
| `workspace/specs/` (new convention) | Move specs from `~/.openclaw/specs/` here as part of the cherry-pick. |
| `workspace/projects/mac-mini-migration/` | This dir — for reference on the Mini. |
| `workspace/projects/archive/` | Completed projects (`model-tiering.md`, `SESSION-ROUTING.md`, `BACKUP_PLAN.md`). |
| `workspace/.claude/settings.json` + `workspace/.claude/hooks/skill-edit-guard.py` | PreToolUse hook. Activates automatically when cwd=workspace under Claude Code backend. |

### Workspace files — LEAVE BEHIND

| Path | Reason |
|---|---|
| `workspace/architecture.md` | Stale Before/After framing. Rewrite on Mini from current openclaw concepts. |
| `workspace/METHODOLOGY.md` | Duplicate of `skills/skill-builder/METHODOLOGY.md`. Skill version is canonical. |
| `workspace/REASONING.md`, `workspace/SECURITY.md` | Fold relevant content into AGENTS.md or skill docs. |
| `workspace/claude/` (entire dir) | Stale duplicate identity files. No openclaw convention supports it. |
| `workspace/ynab*.py`, `workspace/build-merchant-lookup.py`, `workspace/fetch-uncategorized.py`, `workspace/merchant-lookup.json` | Pre-skill ynab experiments. ynab-categorize skill superseded them. |
| `workspace/hello_*.py`, `workspace/word_count.py` | Toy scripts. |
| `workspace/tmp-cron-patch*.py` | Temp files. |
| `workspace/ynab-categorization-plan.md` | Predates the skill. Archive locally before Mini push if Dave wants the history. |
| `workspace/.openclaw/workspace-state.json` | openclaw-regenerated on fresh install. |
| `workspace/.DS_Store` | macOS. |

### State-dir files — BRING (selective)

| Path | Notes |
|---|---|
| `cron/jobs.json` | Edit during transit: remove `delivery.bestEffort` lines, update gmail references. Doctor flagged it as "legacy storage" — read the doctor message on the Mini before running `--fix`. |
| `hooks/transforms/refurb-alert.v3.js` + any other transform modules | Move cleanly. |
| `scripts/op-*.sh` | Secret-fetch wrappers. Move cleanly (they call `op`, no embedded credentials). |
| 1Password vault entries (in 1Password, not on disk) | Re-grant `op signin` on the Mini. |

### State-dir files — LEAVE BEHIND

| Path | Reason |
|---|---|
| `openclaw.json` | Fresh `openclaw onboard` generates a clean one. Re-add hooks/cron/channel config after, with new identity bits. |
| `openclaw.json.bak*`, `.clobbered.*`, `.pre-*` | Backups of stale config. |
| `credentials/` | Channel auth — re-pair fresh against new Apple ID. |
| `agents/` (all subdirs) | Per-agent runtime state. Regenerated. |
| `subagents/runs.json` | Empty + undocumented. Don't recreate on Mini. |
| `logs/`, `tasks/`, `delivery-queue/`, `flows/`, `acpx/`, `bluebubbles/`, `canvas/`, `completions/`, `devices/`, `identity/`, `media/`, `plugin-runtime-deps/`, `qqbot/`, `telegram/` | Either openclaw-managed (regenerated) or unused / channel-specific (start fresh). |
| `workspace-skills-agent/` (entire dir) | Will get a fresh workspace on the Mini after the second `agents.list[]` entry is registered. Stale debris (skill-builder/ misplaced at root, duplicate hello-skill/ynab-categorize, compose-refs/, spec.md, merchant-lookup.json) stays behind. |
| `handoff/` (entire dir) | Superseded by `workspace/projects/mac-mini-migration/`. Delete after migration validates. |
| `specs/` (top-level — wrong location) | Contents move into `workspace/specs/` as part of the cherry-pick. |

---

## Mini install procedure

Replaces the old `BOOTSTRAP.md` 9-step card.

### Phase A — Mini foundations

1. Install Homebrew, node, git, gh, claude (`@anthropic-ai/claude-code`), 1Password CLI, Tailscale. (Same as old BOOTSTRAP.md steps 1-5.)
2. `claude` (auth against Anthropic account).
3. Sign Mini into Bishop's new Apple ID (System Settings → Apple ID → iMessage on).
4. `op signin` against Dave's 1Password account.
5. `gh auth login` as **bishop-wayland**.

### Phase B — openclaw install

1. `brew install openclaw` (verify formula path).
2. Run `openclaw onboard` — let it seed a clean `~/.openclaw/` + workspace with bootstrap files.
3. Verify `openclaw doctor` is green on a fresh install before adding any content.

### Phase C — Workspace cherry-copy

1. `git clone https://github.com/bishop-wayland/openclaw-home.git /tmp/openclaw-source` (the cleaned-up repo).
2. Copy only the BRING entries from the cherry-pick list above into `~/.openclaw/workspace/`.
3. Edit identity references during copy: gmail address, phone numbers (Bishop's source identity changes; Dave's delivery destination stays).
4. Remove the `workspace-skills-agent` cherry-pick from this phase — let it auto-create on first skills-agent dispatch instead.

### Phase D — Cherry-copy state-dir files

1. Copy `cron/jobs.json` (edited: no `bestEffort`, new identity refs), `hooks/transforms/*.js`, `scripts/op-*.sh`.
2. Re-add hooks/cron/channel config to fresh `openclaw.json` via `openclaw configure` or direct edit.
3. Update `openclaw.json` hooks.gmail block: new account, new GCP topic/subscription, new pushToken, new tailscale path.

### Phase E — BlueBubbles + Gmail

1. Install BlueBubbles Server app, pair to Mini's new Apple ID iMessage account.
2. Configure openclaw bluebubbles channel (server URL, password).
3. Re-grant `gog` OAuth for `yutani.w.bishop@gmail.com`.
4. Create new GCP Pub/Sub topic + subscription, expose via Tailscale Funnel, update `openclaw.json` hooks.gmail.

### Phase F — Register skills-agent

1. Add the `agents.list[]` entry for `skills-agent` with `workspace: ~/.openclaw/workspace-skills-agent`.
2. Let openclaw create the workspace + bootstrap files on first dispatch.
3. Copy skill-builder methodology into `workspace-skills-agent/skills/skill-builder/` if it needs to be loadable for skills-agent (currently it lives in main workspace; verify which agent loads it).

### Phase G — Doctor + smoke tests

1. `openclaw doctor` — must be green or have known-acceptable warnings.
2. Address VM-era doctor findings on the fresh install:
   - **Gateway service inline `OP_SERVICE_ACCOUNT_TOKEN`**: install service with runtime token load from `~/.openclaw/.env`, not embedded.
   - **Gateway PATH**: minimal PATH, no version-manager dirs.
   - **Cron legacy storage**: read what doctor reports on the fresh install — clean install may default to whatever the current format is.
3. iMessage Bishop's number from Dave's phone — Bishop responds in character.
4. Trigger a cron job manually (medication reminder) — Dave receives.
5. Run a workspace skill: `python3 workspace/skills/paddle-board-alert/scripts/check.py --dry-send`.

### Phase H — Cutover + cleanup

1. Stop openclaw on the VM, shut down VM.
2. Confirm Bishop is stable on the Mini for 2-3 days.
3. Revoke old credentials: old GCP Pub/Sub subscription, old gog tokens, old BB pairing on Dave's Apple ID.
4. Delete `handoff/` from the repo; this dir (`projects/mac-mini-migration/`) is now historical.

---

## Open questions to surface on the Mini

1. **GCP Pub/Sub** — new topic+subscription for `yutani.w.bishop@gmail.com`, or repoint the existing subscription? Repoint is faster; fresh is cleaner.
2. **Tailscale Funnel URL** — same URL as the VM (re-point at Mini node) or new URL (re-point GCP subscription)?
3. **Old `bishopunit937@gmail.com`** — abandoned or kept as a backup inbox? Affects AGENTS.md Rule 3a trusted-senders list.
4. **`workspace/architecture.md`** — rewrite from scratch on the Mini against the documented openclaw model, or skip and rely on HIERARCHY.md + openclaw's own docs?

---

## What carries over (recent work context)

Recent VM-side milestones the Mini inherits:
- **Build/Patch methodology** (`skills/skill-builder/METHODOLOGY.md`) — two-mode skill workflow.
- **Install-with-preview** — skills install in preview mode behind a gate. `ynab-categorize` is currently in preview (`--no-apply` in cron payload), awaiting Dave's "go".
- **PreToolUse hook** (`workspace/.claude/`) — enforces skill-edit-via-skills-agent. Activates from `workspace/` cwd.
- **YNAB skill** — built, awaiting go-live.
- **Patch-mode dispatch not yet empirically validated.** Next patch on the Mini is the test.

---

## Trust model (carried over)

Bishop = orchestrator + bookkeeper (Haiku). Skills-agent = coder. Skill code is edited only via skills-agent dispatch. The PreToolUse hook enforces this structurally when Bishop's runtime cwd is `workspace/`.

The Mini install does not weaken this.

---

## Ending state

- VM is shut down. openclaw runs only on the Mini.
- Bishop has his own iMessage thread to Dave on his own number.
- Gmail webhook live on `yutani.w.bishop@gmail.com`.
- All crons fire from the Mini.
- `delivery.bestEffort` removed.
- PreToolUse hook intact.
- `~/.openclaw/` on the Mini is clean — no debris carried over.
- Bishop's identity is fully consolidated.
