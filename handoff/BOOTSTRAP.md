# Bishop Migration — Bootstrap Card

You're at the Mac Mini terminal. The repo isn't cloned yet. Follow these steps in order. Stop after step 9 — once Claude Code is running on the Mini, it reads `handoff/BISHOP-MIGRATION-CONTEXT.md` and takes over orchestration.

Time budget: 10–15 minutes for steps 1–9 if everything goes well.

## 1. Install Homebrew (skip if already present)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow its prompts. When it tells you to add Homebrew to PATH, run those `eval $(...)` lines so `brew` works in the current shell.

## 2. Install foundations

```bash
brew install node git gh
```

## 3. Install Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

Verify:

```bash
claude --version
```

## 4. Authorize Claude Code

```bash
claude
```

First-run prompts you to authenticate against your Anthropic account. Use the same account you've been using on the VM (you're billed against it; same model access). After auth, exit Claude Code for now (`Ctrl+D` or `/exit`).

## 5. Install Tailscale (needed later for the Gmail webhook tunnel)

```bash
brew install --cask tailscale
```

Open the Tailscale app from Applications, sign in to your tailnet. Once you see your tailnet's machine list with this Mini visible, you're done.

## 6. Authenticate `gh` as Bishop

```bash
gh auth login
```

Choose:
- GitHub.com
- HTTPS
- Authenticate Git with your GitHub credentials → Y
- Login with a web browser

**Important:** when the browser opens, sign in as **`bishop-wayland`** — not your personal GitHub account. The repo `openclaw-home` lives under Bishop's account; this Mini authenticates as Bishop.

## 7. Clone Bishop's repo

```bash
git clone https://github.com/bishop-wayland/openclaw-home.git ~/.openclaw
```

This pulls Bishop's full config + workspace + skills, including the handoff context document that Mini-Claude-Code will read next.

## 8. Start Claude Code in Bishop's home

```bash
cd ~/.openclaw && claude
```

You're now in a Claude Code session with `~/.openclaw/` as the working directory. The project-local `workspace/.claude/settings.json` does NOT load here (that's a Bishop runtime concern, not a dev concern — see the context doc).

## 9. First message to Mini-Claude-Code

Paste this as your first prompt:

> Read `handoff/BISHOP-MIGRATION-CONTEXT.md` to come up to speed on what we're doing. I'm Dave, you're picking up a migration in progress from Laptop-Claude-Code. The VM Bishop is being shut down once you and I finish moving things over.

Mini-Claude-Code reads the doc, comes up to speed, asks any clarifying questions, then we continue the migration phases together from there.

---

## If something breaks

- `brew install` failed: probably PATH issue — run `eval $(/opt/homebrew/bin/brew shellenv)` and retry
- `claude` command not found after npm install: PATH issue with global npm bins — `export PATH="$(npm bin -g):$PATH"` and retry
- `gh auth login` shows "token invalid" after: try again; sometimes the device-code flow doesn't save correctly on first try
- `git clone` says "Repository not found": double-check you're authed as `bishop-wayland`, not your personal account (`gh auth status`)
- Claude Code starts but can't find Anthropic credentials: re-run `claude` and complete the auth flow

If a step fails in a way the recipe doesn't cover, you can still walk through it manually — none of these are destructive. Worst case: tell Laptop-Claude-Code (the session you came from) what happened.
