# Bishop Backup & Rollback Plan
**Created:** 2026-04-11

---

## What Needs Protecting

| What | Where | Risk |
|------|-------|------|
| OpenClaw config | `~/.openclaw/openclaw.json` | Breaking integrations, channels, hooks |
| Cron jobs | `~/.openclaw/cron/jobs.json` | Losing meds reminders, wind-down |
| Workspace (memory, soul, agents) | `~/.openclaw/workspace/` | Losing Bishop's identity + memory |
| Credentials | `~/.openclaw/credentials/` | Losing API keys (sensitive — handle carefully) |

---

## Option A: Git on the Workspace (Recommended — Do This First)

The workspace is just files. Git gives you full revision history, easy rollback, and diffs.

```bash
cd ~/.openclaw/workspace
git init
echo "state/" >> .gitignore        # exclude runtime state dirs if needed
git add -A
git commit -m "Initial Bishop workspace snapshot"
```

Then after any significant change:
```bash
cd ~/.openclaw/workspace
git add -A
git commit -m "describe what changed"
```

Rollback any file:
```bash
git checkout HEAD~1 -- MEMORY.md   # restore one file
git reset --hard HEAD~1            # nuclear: roll back everything
```

**Do NOT commit credentials/ into git** — add it to `.gitignore`.

---

## Option B: Pre-Change Manual Snapshots

Before any risky config change (hooks, cron edits, openclaw.json):

```bash
# OpenClaw already does this automatically, but do it manually before risky work:
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.pre-<project-name>
cp ~/.openclaw/cron/jobs.json ~/.openclaw/cron/jobs.json.pre-<project-name>
```

OpenClaw's own auto-backups:
- `~/.openclaw/openclaw.json.bak` through `.bak.4` — last 5 versions
- `~/.openclaw/openclaw.json.clobbered.*` — timestamped snapshots on major changes
- `~/.openclaw/openclawbackup.json` — exists already

Restore from auto-backup:
```bash
cp ~/.openclaw/openclaw.json.bak ~/.openclaw/openclaw.json
openclaw gateway restart
```

---

## Option C: Full Workspace Tarball

For a point-in-time full snapshot before major work:

```bash
tar -czf ~/bishop-backup-$(date +%Y%m%d).tar.gz \
  ~/.openclaw/workspace \
  ~/.openclaw/openclaw.json \
  ~/.openclaw/cron/jobs.json
# Do NOT include credentials/ unless you're storing the tarball securely
```

---

## Recommended Setup Right Now

1. **Init git on workspace** (Option A) — do this before session-routing project
2. **Commit current state** as baseline
3. **Before each phase** of session-routing: `git commit -m "pre-phase-N checkpoint"`
4. If something breaks: `git reset --hard` or `openclaw gateway restart` + restore `.bak`

---

## Quick Rollback Reference

| Problem | Fix |
|---------|-----|
| openclaw.json broken | `cp ~/.openclaw/openclaw.json.bak ~/.openclaw/openclaw.json && openclaw gateway restart` |
| Cron jobs broken | `cp ~/.openclaw/cron/jobs.json.bak ~/.openclaw/cron/jobs.json` |
| Workspace file corrupted | `git checkout HEAD -- <filename>` |
| Everything broken | `git reset --hard HEAD~1` + restart gateway |
| Nuclear option | Restore from tarball snapshot |
