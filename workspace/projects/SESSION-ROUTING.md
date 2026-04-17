# Project: Bishop Session Routing / Active Session Registry
**Created:** 2026-04-11  
**Status:** Planning complete, implementation not started  
**Pick up at:** Phase 1

---

## Problem Statement

Bishop runs as separate sessions per channel — iMessage, browser, Telegram, cron jobs. When a background session (e.g. a meds reminder cron) fires while Dave is mid-conversation in iMessage, it sends a message through its own channel with no awareness that Dave is already talking to Bishop elsewhere. This creates split-brain delivery: two Bishop voices, no shared context.

**Goal:** Background/proactive sessions should detect which session Dave is actively using and relay through that session instead of delivering independently.

---

## Architecture

### Core Concept: Presence-Aware Routing

```
Proactive agent wants to reach Dave
         ↓
Check memory/active-session.json
         ↓
Am I the active session?
    ├── YES → deliver normally (I'm already talking to Dave)
    └── NO → is there another active session?
              ├── YES → sessions_send to that session: "tell Dave X"
              └── NO  → fall back to default channel (iMessage/Telegram)
```

### Key Design Decisions
- **No master/slave hierarchy** — peer mesh, sessions are equal
- **Lazy updates** — sessions only broadcast when about to act, not constantly
- **Active session owns delivery** — background sessions hand off, never deliver in parallel
- **Fire-and-forget handoff** — background session calls sessions_send and moves on, doesn't block
- **Deterministic routing logic** — pure Python/shell, no LLM inference in the routing layer
- **TTL-based staleness** — registry entry expires after 5 min of inactivity; fallback to direct delivery

### Latency Profile
- File I/O overhead: ~0.65ms (negligible)
- Relay penalty: ~2-5s extra for proactive messages routed through active session (acceptable for reminders/alerts)
- Conversational latency (Dave ↔ active session): **unchanged**

---

## What OpenClaw Provides (and Doesn't)

**Has:**
- `sessions_list` — see running sessions
- `sessions_send(sessionKey, message)` — push message into another session
- `agent:bootstrap` hook — runs before system prompt is finalized; can inject context/files
- Session files on disk: `~/.openclaw/agents/main/sessions/sessions.json`, `.jsonl` transcripts
- `OPENCLAW_GATEWAY_PORT`, `OPENCLAW_SERVICE_VERSION` etc. in env

**Does NOT have:**
- Built-in active session registry
- Session self-identification env var (no `OPENCLAW_SESSION_ID`)
- Cross-channel session merging or presence tracking

---

## Implementation Plan

### Phase 1 — Session Self-Identification
**Goal:** Each session knows its own ID at startup.

**The gap:** OpenClaw doesn't expose `OPENCLAW_SESSION_ID` in the environment. Need to either:
- Option A: Use `agent:bootstrap` hook to write session ID to a file at session start
- Option B: At response time, call `sessions_list` and match against recent activity

**Recommended:** Option A (bootstrap hook) — cleaner, runs once at session start, not per-response.

**Steps:**
1. Read OpenClaw hooks docs: `/opt/homebrew/lib/node_modules/openclaw/docs/automation/hooks.md` (read via `cat`, sandbox blocks the `read` tool)
2. Locate hook config in `~/.openclaw/openclaw.json`
3. Write script: `projects/session-routing/scripts/bootstrap_session.sh`
   - Reads session ID from sessions.json or hook-provided env
   - Writes `memory/active-session.json` with session ID, channel, timestamp
4. Register it as an `agent:bootstrap` hook
5. Test: start a fresh session, confirm file is written

**Deliverable:** `memory/active-session.json` written at session start with correct session ID

---

### Phase 2 — Active Session Registry Updates
**Goal:** Registry stays current as Dave uses a session.

**Steps:**
1. Write `projects/session-routing/scripts/update_registry.py`
   - Atomic write (tmp file → mv) to `memory/active-session.json`
   - Schema: `{session_id, channel, last_active (unix timestamp), ttl (seconds, default 300)}`
2. Wire it to run on every inbound message in active session
   - Preferred: via bootstrap hook or OpenClaw hook system
   - Fallback: Bishop calls it as first action of every response (adds ~0.5ms)
3. Test: send a few messages, watch the file update

**Deliverable:** `memory/active-session.json` stays fresh during active conversation

---

### Phase 3 — Routing Decision Script
**Goal:** Deterministic Python script every proactive session runs before acting.

**Steps:**
1. Write `projects/session-routing/scripts/check_routing.py`
2. Logic:
```python
def get_routing_decision(my_session_id):
    active = read_registry()  # returns None if missing/stale
    if active is None:
        return ("fallback", None)       # no active session, deliver directly
    if active["session_id"] == my_session_id:
        return ("self", None)           # I'm the active session, deliver normally
    return ("delegate", active["session_id"])  # hand off to active session
```
3. Exit codes: 0=self, 1=delegate (prints session_id to stdout), 2=fallback
4. Unit test all three branches

**Deliverable:** `check_routing.py` — callable from any session/cron job, pure Python, no LLM

---

### Phase 4 — Wire Cron Jobs to Use Routing
**Goal:** Existing proactive sessions (meds reminders, wind-down) use routing before acting.

**Cron jobs to update:**
- Noon meds reminder
- 3 PM meds reminder  
- 9 PM wind-down check-in

**Steps:**
1. For each cron job, prepend routing check before message delivery
2. Pseudocode:
```
decision = check_routing.py --session-id $MY_SESSION_ID
if decision == "self":
    deliver via my channel (iMessage/Telegram)
elif decision == "delegate":
    sessions_send(delegate_session_id, "[RELAY] Meds reminder: time to take your meds")
elif decision == "fallback":
    deliver via default channel (iMessage direct)
```
3. Make handoff fire-and-forget (don't block on relay completion)
4. Test: trigger a cron manually while mid-conversation in iMessage, confirm relay works

**Deliverable:** All three cron jobs routing-aware

---

### Phase 5 — Active Session Relay Handling
**Goal:** When active session receives a `[RELAY]` message, it surfaces it naturally to Dave.

**Steps:**
1. Document `[RELAY]` message format: `[RELAY] <source session/job>: <message>`
2. Bishop handles this naturally in conversation (it's just a message in context)
3. Optional: add a brief note in AGENTS.md so future sessions know to expect relay messages
4. Test: simulate a relay, confirm it reads naturally in conversation

**Deliverable:** Relay messages surface cleanly without being robotic or confusing

---

## File Layout

```
~/.openclaw/workspace/
└── projects/
    └── session-routing/
        ├── PROJECT.md          ← this file
        └── scripts/
            ├── bootstrap_session.sh    (Phase 1)
            ├── update_registry.py      (Phase 2)
            └── check_routing.py        (Phase 3)

~/.openclaw/workspace/memory/
└── active-session.json         (runtime registry, created by scripts)
```

---

## Backup / Rollback Notes

OpenClaw already auto-generates `.bak` files of `openclaw.json`. Before making config changes, manually snapshot:

```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.pre-session-routing
cp ~/.openclaw/cron/jobs.json ~/.openclaw/cron/jobs.json.pre-session-routing
```

Workspace files (MEMORY.md, AGENTS.md, etc.) are in `~/.openclaw/workspace/` — consider a git repo here for full revision history (see BACKUP_PLAN.md).

---

## Open Questions

1. Does `agent:bootstrap` hook receive session ID as an env var or arg? (Need to read hooks docs)
2. Can `sessions_send` inject mid-conversation or only start new turns? (Affects Phase 5 UX)
3. Should relay messages be invisible (Bishop surfaces them naturally) or explicit ("⚡ Relay from cron: ...")? Dave's preference TBD.

---

## References

- OpenClaw session docs: `cat /opt/homebrew/lib/node_modules/openclaw/docs/concepts/session.md`
- OpenClaw hooks docs: `cat /opt/homebrew/lib/node_modules/openclaw/docs/automation/hooks.md`
- OpenClaw agent loop: `cat /opt/homebrew/lib/node_modules/openclaw/docs/concepts/agent-loop.md`
- Session files: `~/.openclaw/agents/main/sessions/`
- Cron jobs: `~/.openclaw/cron/jobs.json`
