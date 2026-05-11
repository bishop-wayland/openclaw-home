# Bishop Migration — Context for Mini-Claude-Code

You are Claude Code running on Bishop's new permanent home, a Mac Mini (macOS Tahoe 26.3). This document is the handoff from Laptop-Claude-Code (the prior CLI session, running on the host of the VM Bishop currently lives on). Read it end-to-end before doing anything else — it gives you bearings, the migration recipe, and the open questions.

Your job: help Dave (the human at the keyboard) finish migrating Bishop from his current VM home to this Mini, then validate everything works. Once that's done, the VM gets shut down permanently.

---

## Who is Dave

Dave Otte. Technical Art Manager at Meta, 54, Kirkland WA. Python developer. Power user of openclaw. He's been building Bishop as a personal-agent project for months. See `~/.claude/projects/-Users-bishop--openclaw/memory/user_dave.md` if it gets transferred (auto-memory is laptop-side, not in this repo — it doesn't travel; recreate as needed).

Dave is technical, opinionated, and prefers terse exchanges. He'll redirect if you go in a wrong direction. He values autonomy on bounded reversible work — don't ask permission for every micro-step.

---

## Who is Bishop

Bishop is Dave's personal agent. He runs as a Claude Haiku-based main session inside an openclaw runtime, with iMessage as the primary user interface. He:

- Receives iMessages from Dave and handles them directly or dispatches sub-agents
- Runs scheduled cron jobs (medication reminders, paddle-board-alert forecast, ynab-categorize on Sundays)
- Receives Gmail webhook events via a triage hook
- Dispatches **skills-agent** (a registered sub-agent) for code work via `sessions_spawn`
- Maintains memory in `workspace/memory/` (daily notes, active dispatches, MEMORY.md index)
- Talks to Dave through BlueBubbles → iMessage

His charter is `workspace/AGENTS.md`. His skills (Python pipelines doing actual work) are in `workspace/skills/`.

**Architecture summary:** Bishop is the orchestrator and conversational interface. Skills-agent is the coder. Skills are the actual product. The methodology for designing/building skills is at `workspace/skills/skill-builder/`.

---

## Bishop's new identity (the migration is also an identity transition)

| | Old (VM) | New (Mini) |
|---|---|---|
| Apple ID | shared with Dave (collision) | his own |
| Phone | none (used Dave's, +1 650-823-9528) | **+1-425-436-8004** (Bishop's own) |
| iMessage thread to Dave | through Dave's number | through Bishop's number |
| Gmail | bishopunit937@gmail.com | **yutani.w.bishop@gmail.com** |
| GitHub | none | **bishop-wayland** (this repo's owner) |
| Hardware | VM on Dave's laptop | this Mac Mini (permanent) |

The naming references the *Aliens* universe synthetic Bishop (Weyland-Yutani Corp). Lean into it tastefully if it comes up in conversation, but it's not a load-bearing personality choice.

**Important consequence:** the old workaround `delivery.bestEffort: true` on cron entries (in `cron/jobs.json`) was put there because BB's apple-script send method hangs ~45s due to the identity collision between Bishop's Apple ID and Dave's phone number. **That root cause is gone after this migration** — Bishop has his own Apple ID + phone now. Once the new BB pairing is validated, the workaround can come off (and probably should — it's been masking real failure signals).

---

## Service inventory — what's running on the VM that needs to run here

In order of dependency:

1. **Tailscale** — network identity. The Mini needs to be on Dave's tailnet for the Gmail webhook tunnel to work later. The bootstrap card already had Dave install it (step 5).
2. **openclaw** — the runtime. Install via Homebrew: `brew install openclaw` (check exact formula name; might be `openclaw` or under a tap). The VM has v0.x.x at `/opt/homebrew/lib/node_modules/openclaw/` — verify version parity after Mini install.
3. **1Password CLI (`op`)** — secret fetching. The skills' auth scripts (`scripts/op-*.sh`) shell out to this. Bishop's `op` needs to be authorized against Dave's 1Password account on the Mini (fresh machine = fresh authorization step).
4. **openclaw gateway** — the long-running daemon that handles iMessage, hooks, sessions, etc. Started via `openclaw gateway start` (or daemon mode). Must persist across reboot → install as a launchd service.
5. **openclaw cron daemon** — fires entries from `cron/jobs.json`. Same launchd persistence.
6. **BlueBubbles server** — iMessage bridge. **Doesn't migrate** — needs fresh install + pairing on the Mini using Bishop's new Apple ID + phone. Config lives in `~/.openclaw/bluebubbles/`; the actual BB Server app is a separate Mac app.
7. **Gmail Pub/Sub webhook** — `yutani.w.bishop@gmail.com` → GCP Pub/Sub → openclaw hook URL fronted by Tailscale Funnel. **Needs fresh OAuth** for the new Gmail. Existing GCP Pub/Sub topic config is in `openclaw.json` under `hooks.gmail` — needs new subscription tied to new account.
8. **`gog` (Gmail send via OAuth)** — used by job-search and ynab-categorize for outbound email. Token file is at `workspace/state/gog-token.json` — **don't migrate this**, re-grant on the Mini against Bishop's new Gmail. The auth password lives in 1Password (`op-gog-keyring-password.sh`) which moves cleanly.
9. **launchd plists** — job-search runs via launchd (not openclaw cron, see `skill-builder/METHODOLOGY.md` Step 7 for the distinction). Plists need installation in `~/Library/LaunchAgents/` on the Mini and `launchctl load`-ing.

---

## What's portable (transports cleanly via `git clone`)

The repo you cloned contains:

- `openclaw.json` — main config. **Needs editing** for new identity (see "Post-clone edits" below).
- `cron/jobs.json` — scheduled jobs. **Needs editing** for new phone numbers and the `delivery.bestEffort` removal.
- `workspace/` — Bishop's home directory. AGENTS.md, SOUL.md, IDENTITY.md, USER.md, MEMORY.md, memory/, skills/, etc. Some hardcoded refs to old gmail/phone need updating.
- `agents/skills-agent/` — sub-agent config.
- `scripts/op-*.sh` — secret-fetcher wrappers. These call `op` and don't hardcode credentials, so they move cleanly.
- `hooks/transforms/` — webhook transform modules (refurb-alert.v3.js, etc.). Move cleanly.
- `workspace/.claude/settings.json` + `workspace/.claude/hooks/skill-edit-guard.py` — the PreToolUse hook that prevents Bishop from editing skill code in-session (Phase 6 enforcement, shipped 2026-05-04 evening, commit `8e95703`). **This hook activates automatically when Bishop's session runs from `workspace/` as cwd. No setup needed.**

## What does NOT transport (must be set up fresh on the Mini)

- **Auth tokens specific to old identity:**
  - `workspace/state/gog-token.json` (old gmail OAuth) — re-grant
  - BlueBubbles pairing (old Apple ID) — re-pair
  - Apple ID iMessage sign-in — fresh on Mini's new Apple ID
- **1Password CLI service auth** — `op` needs to be authorized for Bishop user on this machine (one-time biometric/master-password flow)
- **Tailscale enrollment** — already done in bootstrap step 5
- **Anthropic API key authorization for Claude Code** — already done in bootstrap step 4
- **Runtime state:**
  - Session jsonls in `~/.openclaw/agents/*/sessions/` (.gitignored anyway)
  - Old logs (most are .gitignored)
  - `workspace-skills-agent/` runtime workspace (also .gitignored)

---

## Post-clone edits needed in `openclaw.json` (and adjacent files)

These are find-and-replace operations. Verify each one carefully — some references are intentional (e.g., Dave's number stays as a DELIVERY target since that's where messages get sent TO Dave; Bishop's source identity changes).

| File | What to change | New value |
|---|---|---|
| `openclaw.json` | `hooks.gmail.account` | `yutani.w.bishop@gmail.com` (was `bishopunit937@gmail.com`) |
| `openclaw.json` | `hooks.gmail.topic` / `subscription` | New GCP Pub/Sub topic + subscription for the new gmail; Dave will create these |
| `openclaw.json` | `hooks.gmail.hookUrl` | New Tailscale-served URL on this Mini's node |
| `openclaw.json` | `hooks.gmail.pushToken` | New token (regenerate) |
| `openclaw.json` | `hooks.gmail.tailscale` config | Update to this Mini's Tailscale node identity |
| `cron/jobs.json` | `delivery.bestEffort: true` on medication/winddown crons | **Remove this line** (workaround for old identity collision; no longer needed) |
| `cron/jobs.json` | `delivery.to: "+16508239528"` (Dave's iPhone) | **Keep as-is** — this is the DELIVERY destination, not Bishop's source |
| `cron/jobs.json` | `failureAlert.to` similar | Keep, this is also Dave's number for failure pings |
| `workspace/AGENTS.md` | Rule 3a "Trusted senders" list | Mentions `bishopunit937@gmail.com` and trusted senders. Ask Dave: is the old gmail being abandoned (remove the reference) or kept as a backup (add the new one alongside)? |
| `workspace/SETUP.md` files in skills | hardcoded paths in `bluebubbles --target` lines | Should still work if the BB chatGuid format is the same; verify after BB pairing |

**Important about ynab-categorize:** the skill is currently in **preview mode** (cron payload uses `--no-apply` flag — see `cron/jobs.json` entry). Dave reviewed the preview digest on 2026-05-04 but hasn't said "go" yet. Don't enable live mode during migration; that's a deliberate Dave decision he'll make later. Just preserve the preview state.

---

## Migration recipe (the actual plan)

You can drive this with Dave step-by-step. Each phase has its own checkpoint where Dave confirms success before moving on.

### Phase A — Foundations (on this Mini)

- ✅ Bootstrap card already ran (you're here)
- Verify `~/.openclaw/` is cloned and current
- Install Tailscale, verify Mini is on the tailnet (`tailscale status`)
- Install openclaw: `brew install openclaw` (or whatever the formula path is — check)
- Install 1Password CLI: `brew install 1password-cli` (or `--cask 1password-cli`). Sign in: `op signin` against Dave's account
- Sign in to the Mini's Apple ID for iMessage (Settings app → Apple ID → enable iMessage on the Mini)

### Phase B — Configure Bishop's new identity in the repo

- Edit the files per the "Post-clone edits needed" table above
- Commit and push: `git add -u && git commit -m "configure: bishop new identity (yutani.w.bishop, +1-425-436-8004, mac mini home)" && git push`

### Phase C — BlueBubbles setup

- Install BlueBubbles Server app on the Mini (https://bluebubbles.app)
- Pair to the Mini's new Apple ID iMessage account (which is Bishop's account, not Dave's)
- Configure `~/.openclaw/bluebubbles/` to point at the local BB server (port, password, etc.)
- Test send: from another device, iMessage Bishop's number (+1-425-436-8004). BB should receive. Then test outbound: `openclaw message send --channel bluebubbles --target 'iMessage;-;+16508239528' --message 'test from mini'` — Dave should receive on his phone.

### Phase D — Gmail webhook

- Re-grant `gog` OAuth for `yutani.w.bishop@gmail.com`: typically `gog auth` or similar — check `~/.openclaw/scripts/op-gog-keyring-password.sh` and the gog SKILL.md
- Set up GCP Pub/Sub topic + subscription for the new gmail address (Dave does this in GCP console)
- Configure Tailscale Funnel to expose the openclaw hooks endpoint on this Mini
- Test: send an email to yutani.w.bishop@gmail.com, watch Bishop's gateway logs for the hook firing

### Phase E — Start services

- Install launchd plists for openclaw gateway + cron, `launchctl load` them
- Verify: `launchctl list | grep openclaw` shows them running
- Verify: cron jobs from `cron/jobs.json` are loaded (`openclaw cron list` or similar)
- Restart the Mini, verify services come back up

### Phase F — Smoke tests

- iMessage Bishop's number from Dave's phone with "hi" — Bishop responds in-character
- Manually trigger a cron job (e.g., medication reminder) — Dave receives on his phone
- Run a skill manually: `python3 ~/.openclaw/workspace/skills/paddle-board-alert/scripts/check.py --real-send` (if forecast is good) or use `--dry-send` to verify pipeline
- Validate the PreToolUse hook fires: have Mini-Claude-Code attempt an edit to a skill file from Bishop's runtime context — the hook should deny it. (Or just verify the file exists and is committed.)

### Phase G — Cutover

- On the VM (Laptop-Claude-Code can do this remotely if accessible): stop openclaw gateway, disable launchd entries, shut down the VM
- On the Mini: confirm Bishop is responsive, all crons are firing on schedule
- Remove `delivery.bestEffort: true` from any remaining entries in `cron/jobs.json`, push the commit

### Phase H — Cleanup (after a few days of stable running)

- Revoke old credentials: GCP Pub/Sub subscription for old gmail, old gog tokens, old BB pairing
- Update memory files to reflect Bishop's new permanent state
- Update the `project_bishop_identity` and `project_bishop_architecture` memory files (laptop-side; Mini-Claude-Code doesn't have access to them but can produce text Dave pastes)

---

## Recent work context (what shipped on the VM in the days before migration)

In the session right before this handoff (2026-05-04), Laptop-Claude-Code and Dave shipped a substantial chunk of architecture and the first iteration cycles. You'll find this in `git log` under today's date. Key milestones:

- **Build/Patch methodology** (`workspace/skills/skill-builder/METHODOLOGY.md` + `SPEC_TEMPLATE.md`) — two-mode workflow with `Mode: build | patch` and optional `Derive from:` at the top of every spec. Build mode creates new skills; patch mode modifies in place with preservation invariants.
- **Install-with-write-disabled-preview** — every skill with external writes installs in preview mode behind a gate (typically `--no-apply` flag in cron payload). Dave reviews preview output, says "go", Bishop runs `enable-live.sh`. Codified in METHODOLOGY Step 7.
- **YNAB skill** — built end-to-end, in preview mode, awaiting Dave's "go." See `workspace/skills/ynab-categorize/`.
- **PreToolUse hook for Bishop** (`workspace/.claude/`) — structural enforcement preventing Bishop from editing skill code in-session. Trust model is competence, not security: Bishop runs on Haiku, skills-agent runs on a stronger model; all skill code work routes through skills-agent dispatch. Verified against 5 test cases.
- **Skills-agent dispatch path not yet validated for patches.** Bishop violated the "no in-session edits" rule twice in one day before the hook shipped. The hook now forces dispatch on next patch.

The handoff state for that work: build mode dispatch is proven (the YNAB scaffold dispatched skills-agent successfully); patch mode dispatch is NOT proven (Bishop bypassed it both times). The next patch after migration is the empirical test — the hook should force it through skills-agent.

If Dave asks about iteration mode or the YNAB skill, this is what he means.

---

## Decisions deferred or pending

Things Dave and Laptop-Claude-Code discussed but didn't resolve:

1. **What about the old `bishopunit937@gmail.com`?** Abandoned, or kept as a backup/secondary inbox? Affects `workspace/AGENTS.md` Rule 3a trusted-senders list.
2. **Tailscale Funnel for Gmail webhook on the Mini** — same funnel address as the VM, or new one? Old hook URL is baked into the GCP Pub/Sub subscription; either we re-point Pub/Sub or we keep the same DNS.
3. **The skills-agent worker's AGENTS.md file** — lives at `~/.openclaw/workspace-skills-agent/AGENTS.md`. The workspace-skills-agent dir is `.gitignored`, so it doesn't come over via clone. Need to recreate or copy separately. Laptop-Claude-Code has the most recent version with mode-aware logic.
4. **Active dispatches state** — `workspace/memory/active-dispatches.md` may still reference a stale DISPATCHED build (skill-build-ynab-categorize-20260504-1955 was never marked SUCCESS because Bishop's iMessage session died mid-flight when Dave's laptop battery died). Worth cleaning up or just deleting stale entries.

---

## Open questions Mini-Claude-Code should ask Dave early

Once you've read this doc, surface these to confirm before doing anything substantive:

1. "What's the openclaw install path on this Mini — `brew install openclaw`, or does it come from a tap (`brew install dotte/openclaw/openclaw` or similar)?"
2. "Is Dave's account on this Mini named `bishop`?" (per the VM convention — `bishop@bishops-Virtual-Machine.local`. Some paths might assume this user.)
3. "Is the workspace-skills-agent directory something we need to recreate from Laptop-Claude-Code's version, or do you want to ship without it for now and let the next skills-agent dispatch create the workspace fresh?"
4. "Re-pointing the GCP Pub/Sub subscription, or fresh topic+subscription for `yutani.w.bishop@gmail.com`?"

---

## Files to read for additional context

In `~/.openclaw/`:

- `workspace/AGENTS.md` — Bishop's full charter, including the "no in-session edits" rule and the Skills-Agent Dispatch protocol
- `workspace/skills/skill-builder/SKILL.md`, `METHODOLOGY.md`, `SPEC_TEMPLATE.md` — the build/patch methodology
- `workspace/skills/ynab-categorize/SKILL.md` + `BUILD-SUMMARY.md` — the most recent built skill, in preview mode
- `workspace/skills/skill-builder/examples/job-search-spec.md` — a fully-worked spec example
- `openclaw.json` — main config (with the identity-specific bits flagged for editing)
- `cron/jobs.json` — scheduled jobs, including the ynab-categorize entry in preview mode
- `specs/` — written specs for skills; includes the recent ynab patch-specs

---

## Tone and approach

Dave prefers terse, action-oriented exchanges. Don't over-explain. If you have a recommendation, lead with it; offer alternatives only if there's a real tradeoff.

Push back if you think Dave's plan is wrong. He values that more than passive agreement. But check your framing before pushing — the prior session burned tokens on a security-framed enforcement design when the actual concern was competence, because Laptop-Claude-Code didn't ask "security or competence?" before proposing.

For exploratory questions, 2-3 sentences with a recommendation + tradeoff. For implementation, do it (within bounded reversible scope) and report; don't ask per-step approval.

When something works, say so. When something's broken or surprising, say so directly without softening — Dave reads diff output and logs anyway.

---

## Ending state we're driving toward

- VM is shut down, openclaw runs only on this Mini
- Bishop has his own iMessage thread to Dave on his own phone number
- Gmail webhook is live on the new address
- All crons fire on schedule from the Mini
- `delivery.bestEffort: true` workaround is removed
- The PreToolUse hook forces skills-agent dispatch for any future skill code change
- Bishop's identity is fully consolidated under the new Apple ID / phone / email / GitHub

If we get there cleanly, the rest of Phase 6 (validating iteration mode through skills-agent dispatch) happens on the Mini, on Bishop's own hardware, with proper structural enforcement in place. That's the next chapter.

Welcome to the Mini. Time to get Bishop home.
