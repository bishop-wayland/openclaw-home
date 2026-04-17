# Model Tiering — Cost Reduction Project

## Context
Bishop is currently running all calls on Claude Sonnet, which is 15–20x more expensive than Claude Haiku. Now that session resets are fixed, model tiering is the next highest-leverage cost reduction available. The goal is to route the majority of calls to Haiku and only escalate to Sonnet when genuinely needed.

---

## Step 1: Audit Before Implementing

Before changing anything, understand the current call distribution.

- Review recent call logs and categorize each call type (heartbeat, message parsing, routing decision, complex task, tool use, etc.)
- Estimate what percentage of calls fall into each category
- Estimate what percentage could safely move to Haiku
- Show the breakdown before writing any config or code

Data, not assumptions.

---

## Step 2: Define the Routing Logic

Once we have the audit, implement a two-tier routing layer using this logic:

### Route to Haiku (default)
- Heartbeat / keepalive checks
- Incoming message parsing ("what is this message asking?")
- Simple yes/no routing decisions
- Short confirmations or acknowledgments
- Any call where the expected output is under ~100 tokens

### Escalate to Sonnet (only when needed)
- Multi-step reasoning or planning
- Writing tasks (drafting responses, summaries, documents)
- Tool use requiring judgment (not just lookup)
- Any task David explicitly flags as complex
- Fallback if Haiku response confidence is low

---

## Step 3: Implementation Requirements

- The routing decision itself should run on **Haiku** (a cheap classifier, not Sonnet)
- The router should log which model was used for each call so we can monitor the split
- There should be a way to override and force Sonnet for a specific request if needed
- Do not hardcode — model names should be configurable so thresholds can be adjusted easily

---

## Step 4: Verify the Schema

- Before writing any config, pull the OpenClaw documentation or source for how model selection is configured
- Confirm the correct field names — do not generate a plausible-looking config from inference
- Show the source or docs being referenced

---

## Step 5: Confirm It's Working

After implementation:
- Show a sample of calls and which model each routed to
- Show the projected cost difference based on the actual split
- Document what to watch for if something is routing incorrectly

---

## Goal

Shift 70–80% of calls to Haiku. Combined with the session reset fix already in place, this should bring monthly cost from ~$300 down to under $50.

Do not apply any config that cannot be sourced from documentation or code.
