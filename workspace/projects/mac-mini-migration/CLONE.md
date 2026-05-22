# Clone Cheat Sheet — Mini setup

For cloning `bishop-wayland/openclaw-home` to the Mac Mini as a **scratch source for cherry-picking**. The clone does *not* become `~/.openclaw/` — that's created fresh by `openclaw onboard` in a separate step.

See [`CONTEXT.md`](CONTEXT.md) for the full migration plan; this card is just the clone phase.

---

## 0. Auth `gh` as bishop-wayland

The repo is owned by Bishop's GitHub account, not Dave's. Make sure you sign in as the right account.

```bash
gh auth login -h github.com
```

Choose:
- **GitHub.com**
- **HTTPS**
- Authenticate Git with your GitHub credentials → **Y**
- Login with a **web browser**

In the browser that opens: sign in as **`bishop-wayland`**. If you're already signed into your personal GitHub in that browser, use a private/incognito window or sign out first.

Verify:

```bash
gh auth status
```

Expect: `Logged in to github.com account bishop-wayland`. If it shows your personal account, run `gh auth logout` and redo step 0.

---

## 1. Clone to a scratch dir

**Not** into `~/.openclaw/` — that path is reserved for the fresh `openclaw onboard` install.

```bash
git clone https://github.com/bishop-wayland/openclaw-home.git /tmp/openclaw-source
```

---

## 2. Verify the clone

```bash
cd /tmp/openclaw-source
git log -1 --oneline
ls workspace/projects/mac-mini-migration/
```

The latest commit should be the workspace/HIERARCHY.md + mac-mini-migration project commit (or newer). The migration project dir should contain at least `CONTEXT.md` and this file.

---

## 3. Hand off to Claude Code

Once cloned, exit any current shell tasks and start Claude Code with the cloned repo as context:

```bash
cd /tmp/openclaw-source && claude
```

First prompt to Mini-Claude-Code:

> Load project mac-mini-migration. I'm Dave. We're cherry-picking files from this clone into a fresh openclaw install on this Mini per the Option B plan in CONTEXT.md.

Mini-Claude-Code reads `workspace/projects/mac-mini-migration/CONTEXT.md`, then drives the install phases with you.

---

## Why not clone over `~/.openclaw/`?

- `openclaw onboard` (run before this clone, per CONTEXT.md Phase B) creates a clean state dir + seeds bootstrap files in `~/.openclaw/workspace/`.
- Cloning over that overwrites the fresh state with old VM debris — defeats the whole Option B strategy.
- Cherry-pick into `~/.openclaw/` selectively from `/tmp/openclaw-source/` per CONTEXT.md's cherry-pick list.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Repository not found` | gh authed as wrong user | `gh auth logout`, redo step 0, sign in as bishop-wayland |
| `Permission denied (publickey)` | Cloned via SSH instead of HTTPS | Use the HTTPS URL in step 1 |
| `gh auth status` shows token invalid | Stale credentials | Redo step 0 |
| Browser didn't open | Headless terminal / no GUI | Use `gh auth login -h github.com --web` and copy the URL manually to a browser |
| Clone succeeds but `git log` shows ancient history | Wrong repo (somebody else's fork) | Double-check `git remote get-url origin` is `https://github.com/bishop-wayland/openclaw-home.git` |
