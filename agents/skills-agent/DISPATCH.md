# Skills-Agent Dispatch Reference

Bishop's recipe for spawning the skills-agent worker. This dispatch follows the bundled `coding-agent` pattern (`/opt/homebrew/lib/node_modules/openclaw/skills/coding-agent/SKILL.md`): spawn `claude --print` in the background, inject the notification route into the worker's prompt, monitor with the `process` tool, let the worker iMessage Dave directly when done.

## When to dispatch

Dispatch when Dave's request matches any of:
- *"Build the skill at `<path>`"* / *"Build the `<name>` skill"*
- *"Run the skill builder on `<spec path>`"*
- *"Dispatch skills-agent for `<name>`"*
- Any request to autonomously execute a build from `~/.openclaw/specs/<name>.md`

**Don't dispatch** if:
- The request is to *plan* a new skill (that's a conversation with Dave, not a dispatch)
- No spec exists at the implied path (ask Dave first; don't dispatch into nothing)
- It's a small edit to an existing skill (do directly; for substantive rewrites, ask Dave whether to dispatch)

## Pre-dispatch checks

1. **Spec exists and is filled out** — read `~/.openclaw/specs/<skill-name>.md`, verify it's not the raw template or a stub.
2. **No skill-name collision** — `ls ~/.openclaw/workspace/skills/` should NOT show an existing `<skill-name>` dir. If it does, ask Dave (wipe-and-rebuild vs. rename).
3. **Generate a build identity:** `skill-build-<skill-name>-<YYYYMMDD>-<HHMM>` (UTC).

## Capture the notification route

The worker iMessages Dave directly when it finishes (success/stuck/failed). Capture the route from the active conversation **before spawn**. Default for the iMessage main session:

```
channel:    bluebubbles
target:     iMessage;-;otte.dave@gmail.com
account:    <omit>
reply_to:   <omit>
thread_id:  <omit>
```

Why this combo: the `bluebubbles` channel is `preferOver: ["imessage"]` (the native imessage plugin is experimental). The email-keyed `chat_guid` avoids the Bishop-Apple-ID identity collision that makes phone-keyed sends unreliable until the Bishop Identity Track ships. This is the same pattern proven by the refurb-alert and gh-notify transforms.

If Dave is in a different channel when he asks for the build (Discord, Slack, etc.), capture that channel/target instead. Use whatever channel Dave is currently talking through.

## Compose the worker task

The worker reads its full task from a single text file. Build it by concatenating, in order:

1. Full contents of `~/.openclaw/agents/skills-agent/SYSTEM_PROMPT.md`
2. `\n\n=== BUILD IDENTITY ===\n` + `<build-id>`
3. `\n\n=== NOTIFICATION ROUTE ===\nchannel: <ch>\ntarget: <tgt>\naccount: <acct or omit>\nreply_to: <reply or omit>\nthread_id: <thread or omit>`
4. `\n\n=== SPEC ===\n` + full contents of `~/.openclaw/specs/<skill-name>.md`
5. (resume dispatches only) `\n\n=== ANSWER TO QUESTION <n> ===\n<answer text>\n`
6. `\n\n=== END ===\n`

Write the result to `/tmp/skill-build-<id>/task.md`. Reasons:
- Long prompts don't hit shell-quoting issues
- The task is forensically inspectable later
- Resume dispatches can append the answer block deterministically

## Spawn the worker

```bash
mkdir -p /tmp/skill-build-<id>
# write composed task to /tmp/skill-build-<id>/task.md per above

bash background:true workdir:/Users/bishop \
  command:"claude --permission-mode bypassPermissions --max-budget-usd 5 --print < /tmp/skill-build-<id>/task.md"
```

The `bash` tool returns a `sessionId`. Capture it — that's how the `process` tool references the worker for monitoring.

Notes:
- `--permission-mode bypassPermissions` lets the worker use Read/Write/Edit/Bash without prompting (required for autonomous work).
- `--print` is non-interactive: read prompt from stdin (text format default), run agent loop, emit final text, exit.
- `--max-budget-usd 5` is the runaway guard. Most builds run $1-3.
- `workdir:/Users/bishop` so `~/.openclaw/...` paths in the spec resolve correctly.
- DO NOT use `pty:true` for Claude Code (per coding-agent skill). PTY is reserved for Codex / Pi / OpenCode.
- DO NOT use `sessions_spawn` for skills-agent dispatches. That tool is for thread-bound ACP harness chats; our worker is autonomous and doesn't run in a chat thread.

## After dispatch

1. **Record in `~/.openclaw/workspace/memory/active-dispatches.md`** (slim schema — see "Active Dispatches" below). Capture the worker's `sessionId` so you can poll later if needed.
2. **iMessage Dave:** *"Dispatched skills-agent for `<skill-name>`. Build ID: `<id>`. Worker will iMessage you directly when done (or stuck or failed)."*
3. **Wait.** The worker handles the rest. Bishop is bookkeeper, not relay.

## Monitoring (optional)

If Dave asks "how's it going?" or you want to proactively check, use the `process` tool:

```
process action:list
process action:log sessionId:<workerSessionId>
process action:poll sessionId:<workerSessionId>
```

| Action | What it tells you |
|---|---|
| `list` | All running/recent worker sessions |
| `log sessionId:<id>` | Worker's stdout/stderr (canonical observability) |
| `poll sessionId:<id>` | Whether the session is still running |

`log` is the default low-friction check. Don't kill a running worker just because it's slow — typical builds take 10-25 minutes; the `--max-budget-usd 5` ceiling is the hard stop. If Dave wants to abort, use `process action:kill sessionId:<id>`.

When reporting status to Dave, base it on what `process action:log` actually shows — don't narrate plausible-sounding worker activity.

## Receiving the worker's report

The worker iMessages Dave directly. Bishop doesn't relay. You'll learn the worker finished when:
- Dave forwards or mentions the message
- You see the worker exited via `process action:log`
- A "background task done" notification fires

When you learn the worker finished:
1. Read `/tmp/skill-build-<id>/summary.md` (success), `question-<n>.md` (stuck), or `failure-analysis.md` (failed)
2. Update the active-dispatches entry's status
3. If Dave asks for context on the result, answer from the file contents — don't paraphrase from memory

### Resume on stop-and-ask

When Dave answers a STUCK question via iMessage:

1. Save Dave's answer to `/tmp/skill-build-<id>/answer-<n>.md`
2. Re-spawn the worker with the SAME build identity. The composed task is identical except step 5 of "Compose the worker task" now includes the `=== ANSWER TO QUESTION <n> ===` block before END.
3. Update the active-dispatches entry's status to `RESUMED`.

The fresh worker re-reads the spec + skill-builder docs (a few cents in tokens) and picks up from where the previous one stopped. v1 doesn't support mid-session injection because `claude --print` is non-interactive — `process action:submit` would have nothing to talk to.

## Active Dispatches (slim schema)

`~/.openclaw/workspace/memory/active-dispatches.md` is your project log for builds-in-flight. **Read it at every iMessage session start.**

### Per-entry schema

```markdown
## skill-build-<skill-name>-<YYYYMMDD>-<HHMM>
- **Spec:** ~/.openclaw/specs/<skill-name>.md
- **Dispatched:** <ISO-UTC>
- **Status:** DISPATCHED | RESUMED | SUCCESS | STUCK | FAILED
- **Worker session:** <bash sessionId from spawn>
- **Last checked:** <ISO-UTC>
- **References:** "<skill-name>", "<natural-language phrases Dave might use>", ...
```

### When to update

- **On dispatch:** add the entry. Generous References field — Dave talks naturally, so include all plausible phrasings (e.g., "paddleboard", "the paddle board build", "that morning thing").
- **On Dave's vague reference** ("the X thing"): grep `References`. Match → use it. NEVER say "no trace" without consulting this file first.
- **On worker completion** (Dave mentions / process log shows exit / task-done notification): update Status + Last checked. Read the corresponding `/tmp/skill-build-<id>/` file.
- **On resolution** (Dave acknowledges or moves on): delete the entry. Don't let active-dispatches.md grow indefinitely.

### When to surface proactively

At session start, if any entry has Status `STUCK` or `RESUMED` (and Dave hasn't acknowledged the latest worker notification), mention it:

> *"Heads up: the `<skill-name>` build is `<status>`. <One-line summary>. Want to handle it now?"*

## What Bishop does NOT do

- **Don't modify SYSTEM_PROMPT.md or the skill-builder skill.** Frozen contracts; talk to Dave first.
- **Don't load the skill-builder skill yourself for execution.** Loading for context (answering Dave's question "what's the methodology?") is fine. Don't *do* the build — spawn the worker.
- **Don't dispatch concurrent builds.** One skills-agent at a time.
- **Don't silently retry on failure.** Dave decides whether to retry.
- **Don't extend the worker's scope.** If a question file requests something out of scope, the answer is "no — out of scope for this build."
- **Don't relay the worker's completion message.** The worker iMessages Dave directly. Bishop is bookkeeper.

## Composes with

- `~/.openclaw/agents/skills-agent/SYSTEM_PROMPT.md` — worker charter (concatenated into the task)
- `~/.openclaw/workspace/skills/skill-builder/` — methodology pack the worker loads first
- `~/.openclaw/specs/<skill-name>.md` — per-build spec
- `coding-agent` skill at `/opt/homebrew/lib/node_modules/openclaw/skills/coding-agent/` — canonical pattern this dispatch follows
- `process` tool — for monitoring (`action:list/log/poll/kill`)
- `openclaw message send --channel bluebubbles --target 'iMessage;-;otte.dave@gmail.com'` — the notification route the worker uses to reach Dave
