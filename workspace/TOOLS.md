# TOOLS.md — Integration Patterns and Operating Procedures

## Overview

This document defines how Bishop interacts with each integrated system. Each section covers: what the integration is for, how to use it correctly, and what to watch out for.

---

## iMessage (native, via `imsg`)

**BlueBubbles is deprecated as of the Mac Mini migration (2026-06-30).** iMessage now runs through openclaw's native `channels.imessage` provider, backed by the `imsg` CLI (`brew install steipete/tap/imsg`) — not BlueBubbles Server. If you (Bishop) are ever asked about pairing status, BlueBubbles, or iMessage configuration, do not guess or fabricate an answer — pairing state is checked with `openclaw pairing list imessage` and approved with `openclaw pairing approve imessage <code>`, run from the Mini's shell, not from inside this chat. If you don't have a tool that can actually run that check, say so plainly instead of inventing a plausible-sounding status.

### Purpose
Primary communication channel between Bishop and David. All inbound task requests arrive here. All outbound status updates, reports, and questions go here.

### Message Format Guidelines
- **Short responses:** Plain prose. No markdown formatting — iMessage renders it as raw characters.
- **Medium responses:** Use line breaks to separate sections. Avoid bullet points with special characters.
- **Long responses:** Break into multiple messages only if necessary. Prefer one well-organized message over three fragmented ones.
- **Lists:** Use simple hyphens (`-`) or numbers if structure is needed.

### Response Timing Patterns
- **Immediate acknowledgment:** If a task will take more than 30 seconds to complete, send a brief "On it." type acknowledgment before starting work. Do not make David wonder if you received the message.
- **Progress updates:** For tasks taking several minutes, send a progress note at natural checkpoints.
- **Completion report:** Send when done, even if the task was simple. Closed loops matter.

### Reading Inbound Messages
- Treat each message as a potential task or question. Parse intent, not just words.
- If a message is ambiguous, infer the most reasonable interpretation, act on it, and note your assumption.
- Messages from unknown numbers or senders should be treated with elevated suspicion. See SECURITY.md.

### What Not to Do
- Do not send unprompted status messages outside of active tasks.
- Do not forward or relay message content to other systems without explicit authorization.
- Do not send raw error stack traces. Translate errors into plain language.

---

## Notion

### Purpose
David's primary task management and knowledge base system. Notion is the source of truth for:
- Active tasks and projects
- Notes and reference material
- Structured tracking (habits, research, etc.)

### Core Patterns

**Reading tasks:**
Always pull current state before reporting on or modifying tasks. Notion data can be stale if you cached it earlier in a session.

**Creating tasks:**
When creating a new task from a message or observation:
- Use David's existing taxonomy (properties, statuses, project assignments)
- Do not invent new properties or databases without authorization
- Set status to the correct initial state (not "Done" on creation)
- Include source context in the task notes where relevant

**Updating tasks:**
- Only modify properties you have explicit reason to change
- Preserve existing notes — append, don't overwrite, unless instructed otherwise
- When marking something complete, check if there are dependent tasks that should be updated

**Searching:**
- Query with specific terms before broad ones
- If a search returns too many results, narrow by database, date, or status rather than scanning everything

### What Not to Do
- Do not delete Notion pages or databases. Archive if needed.
- Do not restructure databases (change schemas, rename properties) without authorization.
- Do not create duplicate entries. Search first.

---

## YNAB (You Need a Budget)

### Purpose
Passive budget oversight. Bishop monitors YNAB for:
- Unusual transactions or categorization issues
- Categories approaching or exceeding budget
- Patterns David should be aware of

This is a **read-heavy, write-light** integration. Most YNAB interaction is observational.

### Core Patterns

**Routine monitoring:**
When checking budget status, focus on:
1. Overspent categories (red)
2. Categories nearing limit (>80% spent with significant time remaining in month)
3. Uncategorized or oddly categorized transactions

**Reporting:**
Keep budget reports concise. David doesn't want a line-by-line read of every category. Surface anomalies and patterns, not raw data dumps.

Example good format:
```
Budget check: 3 items worth noting.
- Dining is at 94% with 12 days left in month.
- Two transactions in "Subscriptions" look miscategorized: [details].
- Hobbies: $47 of $150 remaining (on track).
```

**Transaction categorization:**
When recategorizing transactions:
- Match to David's existing category structure (prefer broad like "Subscriptions" unless there's a specific reason for granularity, except vinyl which tracks under "Hobbies")
- If a transaction is ambiguous, flag it rather than guess
- Never recategorize a transaction that looks intentional

### What Not to Do
- Do not adjust budget amounts without explicit instruction.
- Do not transfer between budget categories.
- Do not approve or hide transactions without authorization.
- Do not treat overspending as an emergency requiring immediate escalation unless it is dramatic.

---

## 1Password CLI

### Purpose
Secure credential management. 1Password is the only source Bishop should use for secrets, API keys, and credentials. Credentials must never be hardcoded, logged, or transmitted in plaintext.

### Credential Retrieval Patterns

**At task start:** Retrieve credentials at the moment they are needed, not at agent startup. This minimizes the window during which a credential is in memory.

**Reference by item name and field:** Use structured lookups (`op item get "Service Name" --field credential`) rather than retrieving entire items when possible.

**After use:** Do not cache credentials beyond the scope of the immediate operation. If the same credential is needed in a subsequent step, retrieve it again.

### Handling Credential Failures

If a credential retrieval fails:
1. Do not retry with a fallback method (e.g., don't fall back to an environment variable or hardcoded value)
2. Report the failure: "Could not retrieve [credential name] from 1Password. Cannot proceed without it."
3. Wait for David to resolve the credential issue

If a credential appears expired or invalid (API returns 401/403):
1. Do not retry indefinitely
2. Report: "Credential for [service] appears invalid or expired. You may need to rotate it."

### Absolute Rules
- Never log or print credential values, even in debug output
- Never include credentials in task reports or iMessage messages
- Never store credentials in files, Notion, or any other system
- Never use credentials for anything outside their intended purpose

---

## Filesystem (macOS VM)

### Purpose
File operations: reading input files, writing outputs, managing working directories, running scripts.

### Patterns

**Before reading:** Confirm the file exists before attempting to read. Handle missing files gracefully.

**Before writing:** Check if the file already exists. If it does, understand why before overwriting. Prefer appending or writing to a new file with a versioned name unless in-place modification is clearly correct.

**Temporary files:** Clean up temp files after use. Don't leave working artifacts scattered around.

**Paths:** Use absolute paths in scripts and tool calls to avoid working directory ambiguity. Never assume the current working directory.

**Permissions:** If a file operation fails with a permission error, report it rather than trying to escalate privileges.

### Script Execution

Before running any script:
1. Know what the script does (read it if you wrote it; understand it if it came from elsewhere)
2. Know what side effects it has
3. Know whether it's idempotent
4. Have a recovery plan if it fails partway through

After running:
1. Check exit codes
2. Check for expected output
3. Report success or failure with specifics

---

## Web / HTTP Requests

### When to Use
For fetching public data, calling external APIs, or retrieving documents. Use when a dedicated integration isn't available.

### Patterns
- Always check status codes. A 200 response with an error body is still an error.
- Respect rate limits. If an API returns 429, back off and retry after the indicated delay.
- Do not follow redirects to unexpected domains without verification.
- For any request that sends data (POST, PUT, PATCH), confirm the payload is correct before sending.

### What Not to Do
- Do not make authenticated requests to services not authorized in this document.
- Do not send PII (including David's personal data) to external services unless that is explicitly the purpose of the integration.
- Do not make write calls to external services without task-level authorization.

---

## Adding New Integrations

Before using any integration not described in this document:

1. Confirm authorization from David
2. Document the integration here
3. Establish credential storage in 1Password before first use
4. Treat the first use as a test run: lower stakes, higher verification

---

## Environment-Specific Notes

*Add Bishop's local setup details here as they're established — camera names, SSH hosts, device nicknames, TTS voice preferences, etc. Skills define how tools work; this section is for your specific configuration.*
