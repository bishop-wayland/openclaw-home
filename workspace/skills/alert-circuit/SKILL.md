---
name: alert-circuit
description: Set up a deterministic alert circuit that fires an iMessage to Dave when a trigger event occurs (cron schedule, Gmail filter+label, or dedicated webhook). Each circuit is a short-circuit — no LLM judgment in the delivery path — and ships with test + trace scripts for forensic debugging.
metadata: { "openclaw": { "emoji": "🚨", "requires": { "config": ["channels.bluebubbles"] } } }
---

# Alert Circuit

Bishop's standard pattern for "ping Dave when X happens." Every alert in the system follows this shape.

## When to use

Dave says: *"Alert me when…"* / *"Text me if…"* / *"Let me know whenever…"*

If the request describes a **deterministic trigger** (a specific email pattern, a time of day, a webhook) producing a **predictable message** (template, no per-event judgment needed), this is the right skill.

If the request needs Bishop to *decide* whether to interrupt — *"tell me if anything important happens in my email today"* — this is NOT an alert circuit. That's triage, which lives in the Gmail-triage flow with `inbox-queue.md` drainage. Keep alert circuits for pre-authored intents only.

## The four ingredients

Every alert circuit has these four pieces. Collect them from Dave before writing any config.

| # | Ingredient | Examples |
|---|---|---|
| 1 | **Upstream filter** — what produces the trigger event | Gmail filter `from:info@refurb-tracker.com` → label `bishop-alert-refurb`; cron expression `0 12 * * *`; webhook URL `/hooks/custom-x` |
| 2 | **Channel + recipient** | `channel: bluebubbles`, `to: +16508239528` |
| 3 | **Message template** — pure data, no agent instructions | `"🚨 Mac mini alert: {{messages[0].subject}} → https://www.apple.com/shop/refurbished/mac/mac-mini"` |
| 4 | **Test fire** — synthetic trigger payload | curl POST to hook URL with sample fields; `openclaw cron run <id>` for crons |

## The pattern (architectural invariants — do not violate)

These rules came from real debugging. Violating any of them re-introduces a bug we've already paid to fix.

1. **Filtering happens upstream of OpenClaw.** Gmail filters, cron schedules, dedicated webhook URLs. By the time the trigger reaches the OpenClaw hook, there is nothing left to decide.
2. **The template is data, not instructions.** OpenClaw's runtime wraps `messageTemplate` content as `<<<EXTERNAL_UNTRUSTED_CONTENT>>>`. Anything that looks like instructions to the agent gets correctly flagged as injection. Use only field substitutions like `{{messages[0].subject}}`. NEVER write "do X, do not do Y" inside the template.
3. **No tool calls in the cron-style agent path.** Any tool call (even one that fails) trips `hasOutboundSideEffects` (`result-fallback-classifier-BfQx-pcn.js:16`) and suppresses the announce/deliver fallback. Cron prompts must instruct: *"Do not call any tools. Reply with the message text only."*
4. **No `sessions_send` to main from the alert path.** The mirror is the iMessage thread itself (Bishop reads it on his next interactive turn). `sessions_send` triggers the announce-step prompt to Bishop, who may reply `ANNOUNCE_SKIP` and silently kill the alert. Architecture spec: *pre-authored outbound bypasses Bishop's session entirely.*
5. **Three clean test fires before declaring the circuit stable.** A circuit is not "done" until you've seen it deliver three consecutive times via the test script.
6. **Direct iMessage sends use email-keyed chatGuid only.** Hardcode `chatGuid: "iMessage;-;otte.dave@gmail.com"` in transforms. Do not use phone-keyed chatGuid or the BB `address` API path with a phone number — Bishop's Apple ID currently has Dave's phone number on it (Bishop Identity Track in progress), so phone-keyed sends hit an identity collision (500 or silent-sync-to-self). This invariant relaxes once Bishop has his own Apple ID.
7. **Webhook-triggered alerts go through a transform, not an agent.** Set `mapping.transform: { module: "<file>.js" }`. The transform inspects the payload, calls BlueBubbles directly via `fetch`, and returns `null` to skip the agent path. No LLM in the delivery loop = deterministic. The cron flavor (Example 1 in `EXAMPLES.md`) still uses the agent + announce path; that one's been validated and is fine. But for hooks, prefer transforms.
8. **Cron alerts must use `delivery.bestEffort: true`.** The cron's announce-path BB call has a known issue: BB delivers the iMessage successfully but its HTTP response back to the gateway can take >45s, which trips the gateway's timeout and marks the run as error → fires a spurious failure alert. `bestEffort: true` swallows the post-delivery error so the cron stays "ok" and no false failure alerts fire. Apply via the CLI (`openclaw cron edit <id> --best-effort-deliver`) — raw file edits get stripped by openclaw's normalizer on reload. Side note: this also means a *real* delivery failure becomes silent, which is a known trade-off until the BB API hang is root-caused.

## Procedure

When Dave asks for a new alert circuit:

1. **Ask for the four ingredients.** If any are missing or ambiguous, get them in one back-and-forth — don't guess.
2. **Pick the trigger type:**
   - Time-based → cron job (announce/agent path)
   - Email-based → Gmail filter + dedicated label/path + hook mapping with transform module
   - External event → dedicated webhook URL + hook mapping with transform module
3. **Apply the matching stencil:**
   - `stencils/cron-job.json.tmpl` for crons
   - `stencils/hook-mapping.json.tmpl` for hooks
4. **Write the test fire script** based on `stencils/test-fire.sh.tmpl`.
5. **Write the trace script** based on `stencils/trace.sh.tmpl`.
6. **Tell Dave the test command + the validation criteria** (three clean fires, an iMessage each, a clean trace each).

## File locations

| What | Where |
|---|---|
| Cron jobs | `~/.openclaw/cron/jobs.json` |
| Hook mappings | `~/.openclaw/openclaw.json` → `hooks.mappings[]` |
| Test fire scripts | `~/.openclaw/scripts/test-<circuit-name>.sh` |
| Trace scripts | `~/.openclaw/scripts/trace-<circuit-name>.sh` |
| Hook auth token | `~/.openclaw/openclaw.json` → `hooks.token` (header name: `x-openclaw-token`) |

## Reference: working circuits in the system

Read these as canonical examples before building a new one:

- **medication-noon / medication-3pm / winddown-9pm** (cron pattern) — `~/.openclaw/cron/jobs.json`. Fixed 2026-04-30. Validated 2026-05-01 noon natural firing.
- **refurb-tracker** (Gmail+label two-stage hook pattern) — see `EXAMPLES.md` in this skill directory.

## What this skill does NOT cover

- Conversational AI behavior (Bishop's main session — that's `AGENTS.md`).
- Triage of arbitrary email (the existing Gmail hook + `inbox-queue.md` flow).
- Outbound that needs Bishop's reasoning (those go through main session, not short-circuits).
- Credentials/secrets management (use the `1password` skill).

## Testing principle (codified, do not skip)

Every alert circuit must be **forensically debuggable in under 60 seconds** via:
1. A way to fire it deliberately (`scripts/test-<name>.sh`)
2. A per-hop trace (`scripts/trace-<name>.sh`) that shows: trigger received → agent dispatched → agent decision → channel deliver
3. Three clean consecutive fires before declaring the circuit ready for production

If any of these are missing, the circuit is not done.
