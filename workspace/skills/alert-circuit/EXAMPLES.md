# Alert Circuit Examples

Read these before building a new circuit. Each is a working canonical example.

---

## Example 1: Cron-driven alert (medication reminder)

**Use case:** Dave wants a brief warm reminder at noon and 3pm every day to take meds.

**Ingredients:**
1. **Upstream filter:** Cron expression `0 12 * * *` and `0 15 * * *`
2. **Channel + recipient:** `delivery: { mode: "announce", channel: "bluebubbles", to: "+16508239528", bestEffort: true }` — explicit channel/to (not `channel: "last"`, which is more variable), with `bestEffort: true` to swallow the BB API hang
3. **Template:** Embedded in `payload.message` — short prompt instructing Haiku to emit a one-line reminder, no tool calls
4. **Test fire:** `scripts/test-cron-meds-noon.sh` (or `openclaw cron run <id>` directly)
5. **Trace:** `scripts/trace-cron.sh medication-noon`

**Config location:** `~/.openclaw/cron/jobs.json`

**Notes:**
- `sessionTarget: "isolated"` is required (NOT `"main"` — that path is the broken heartbeat-piggyback hazard)
- `payload.kind: "agentTurn"` (NOT `"systemEvent"`)
- Prompt explicitly says "Do not call any tools" — this is non-negotiable; any tool call suppresses delivery
- `delivery.bestEffort: true` is required (see SKILL.md invariant 8). Without it, BB's slow HTTP response causes spurious failure alerts. Set via `openclaw cron edit <id> --best-effort-deliver` — raw file edits get stripped by the normalizer.
- `delivery.to` accepts only phone-format E.164 for BB. Attempts to use `chat_guid:iMessage;-;...` form get normalized back to phone on reload.
- `failureAlert` is the safety net for cron worker errors (separate from `delivery`). With `bestEffort: true`, delivery aborts no longer count as errors, so failure alerts only fire on actual cron-worker failures (timeouts, agent crashes, etc).

---

## Example 2: Email-triggered alert via transform (refurb-tracker → iMessage)

**Use case:** Dave wants an iMessage with a buy link whenever an email from `info@refurb-tracker.com` arrives in his Gmail.

**This is the canonical webhook-triggered alert pattern.** Validated end-to-end on 2026-05-01: three clean test fires, plus a real fire that led Dave to buy a refurbished Mac mini.

### Why a transform, not an agent

A hook can route to either an agent run (`action: "agent"`) or to a JS transform module (`mapping.transform: { module: ... }`). For deterministic alerts, **always use a transform**:

- No LLM in the delivery path → no risk of agent reasoning interfering with the alert
- Returns `null` → OpenClaw skips the agent path entirely (no `hasOutboundSideEffects` interference, no announce-step Q&A)
- The transform calls BlueBubbles directly via `fetch`, so delivery is plain HTTP — easy to forensically trace
- Costs nothing in tokens

The older agent-with-`messageTemplate` echo approach (still works for the cron flavor in Example 1) is *not* the right shape here. Webhook alerts go through a transform.

### Stage 1 (upstream): Gmail filter

Dave configures this in Gmail web UI under Settings → Filters and Blocked Addresses → Create new filter:

```
From: info@refurb-tracker.com
→ Apply label: bishop-alert-refurb
→ (optional) Forward to: bishopunit937@gmail.com  [needed if filtering Dave's personal inbox]
```

This stage does the matching. By the time the email reaches OpenClaw, it's already classified.

### Stage 2 (OpenClaw): Hook mapping with transform

The Gmail watcher in `~/.openclaw/openclaw.json` listens for the labeled emails. The hook mapping points at a transform module:

```json
{
  "match": { "path": "gmail-alert-refurb" },
  "name": "Refurb Mac mini alert",
  "transform": { "module": "refurb-alert.v3.js" }
}
```

The transform file lives at `~/.openclaw/hooks/transforms/refurb-alert.v3.js` (configured via `hooks.transformsDir`). It:

1. Inspects the inbound webhook payload.
2. Recognizes a refurb-tracker email (matches `info@refurb-tracker.com` in `from` or forwarded body).
3. Builds the alert text from the original subject (strips `Fwd:` prefixes).
4. POSTs directly to BlueBubbles' `/api/v1/message/text` endpoint with a hardcoded `chatGuid`.
5. Logs status to `gateway.err.log` (or wherever console output is captured).
6. Returns `null` to skip the agent path.

See `hooks/transforms/refurb-alert.v3.js` in the repo for the working source — clone its shape for new transforms.

### Architectural rule: hardcode email-keyed chatGuid

Inside the transform, send to:

```js
const DAVE_CHAT_GUID = "iMessage;-;otte.dave@gmail.com";
```

**Do NOT use phone-keyed chatGuid (`iMessage;-;+16508239528`) and do NOT use the BB `address` API path with a phone number.** Bishop's Apple ID currently has Dave's phone number registered to it (transitional state — see Bishop Identity Track), so phone-keyed sends hit an identity collision and either return 500 or sync to Bishop's own devices instead of delivering to Dave's iPhone. Email-keyed is unambiguously Dave-only and routes cleanly. This rule will become obsolete once Bishop has his own Apple ID + phone number.

### Stage 3 (test infrastructure)

`scripts/test-refurb-alert.sh` POSTs a synthetic payload to `/hooks/gmail-alert-refurb`:

```bash
curl -X POST http://127.0.0.1:18789/hooks/gmail-alert-refurb \
  -H "x-openclaw-token: $TOKEN" \
  -d '{"messages":[{"id":"test-x","from":"...","subject":"1 new refurb...","body":"...","snippet":"..."}]}'
```

`scripts/trace-refurb-alert.sh` shows the per-hop trace, including the transform's BB call/response logged to `gateway.err.log`.

**Validation:** three consecutive test fires, each producing an iMessage on Dave's iPhone within ~5s.

---

## Anti-pattern (what NOT to do)

The earlier (broken) implementation tried to put **branching logic in the messageTemplate**:

```
"If from refurb-tracker → emit alert.
 Else → write to inbox-queue.md.
 Else → SPAM."
```

This failed because the runtime wraps `messageTemplate` content as `<<<EXTERNAL_UNTRUSTED_CONTENT>>>` and Haiku correctly identified the embedded instructions as a prompt-injection attempt. Result: agent ignored the instructions, narrated its security reasoning, and the narration got shipped to Dave instead of the alert.

**Lesson:** filter UPSTREAM. By the time the trigger reaches OpenClaw, there's nothing left to decide.
