# Project: Bishop identity track

**Status:** Active — execution phase, partially blocked on Mac Mini migration.

Bishop as a separate person/colleague with his own accounts, devices, phone number, and controlled access to Dave's data. Treat Bishop as a colleague, not a tool — limits blast radius if something goes wrong, clean separation of Dave's personal data from what Bishop accesses.

---

## Identity transition table

| | Old (VM) | New (Mini) |
|---|---|---|
| Apple ID | shared with Dave (collision) | Bishop's own |
| Phone | Dave's (+1-650-823-9528) | **+1-425-436-8004** (Bishop's own) |
| iMessage thread to Dave | through Dave's number | through Bishop's number |
| Gmail | bishopunit937@gmail.com | **yutani.w.bishop@gmail.com** |
| GitHub | none | **bishop-wayland** |
| Hardware | VM on Dave's laptop | dedicated Mac Mini |

---

## Why a Mac Mini (not just better VM hosting)

Dedicated hardware = cleaner SIP/SSV story if BlueBubbles ever needs Private API. Plus a permanent, always-on host instead of a VM tied to Dave's laptop battery (which has already caused at least one mid-flight session death).

---

## Status of identity pieces

| Piece | Status |
|---|---|
| iPhone purchased for Bishop | ✅ (per Dave, 2026-05-02-ish) |
| Phone number `+1-425-436-8004` | provisioned? confirm during Mini Phase A |
| Apple ID for Bishop | created? confirm during Mini Phase A |
| Gmail `yutani.w.bishop@gmail.com` | created? confirm before Mini Phase D |
| GitHub `bishop-wayland` | ✅ (this repo's owner) |
| Mac Mini hardware | ✅ in hand (2026-06-29) |
| BlueBubbles re-pair to Bishop's Apple ID | Mini Phase C |
| Gmail webhook on new account | Mini Phase D |

---

## The cron `bestEffort` workaround (gating dependency)

Cron alerts use `delivery.bestEffort: true` because BB's `apple-script` send method hangs ~45s on Bishop's Mac. Root cause is the Apple ID collision (Bishop's Apple ID currently has Dave's phone number registered to it, sender_phone == recipient_phone confuses iMessage routing).

**Verification step on the Mini, once Bishop has his own number:**
1. Re-fire `~/.openclaw/workspace/skills/alert-circuit/scripts/test-cron-meds-noon.sh` (or equivalent).
2. Expect `delivered: true` and total duration `<2s`.
3. If confirmed: remove `bestEffort: true` from each reminder cron entry in `cron/jobs.json`.
4. Update `alert-circuit/stencils/cron-job.json.tmpl` to drop the `bestEffort` line so future cron installs default cleanly.

---

## Key decisions (don't re-litigate)

- **Cherry-pick clean install for the migration**, NOT whole `~/.openclaw/` copy. The migration *is* the cleanup opportunity — see [mac-mini-migration](../mac-mini-migration/CLAUDE.md). Continuity is not a goal here.
- **Bishop only gets data Dave explicitly shares.** Isolation by design. Don't carry over Dave's keyring entries or personal credentials reflexively — only what skills demonstrably need.
- **Apple ID first, then phone, then BlueBubbles re-pairing.** Don't mix into Dave's personal Apple ecosystem.

---

## Open follow-ups (post-migration)

1. After 2-3 days stable on the Mini: revoke old credentials — old GCP Pub/Sub subscription, old `gog` tokens, old BB pairing on Dave's Apple ID.
2. Decide what to do with `bishopunit937@gmail.com` — abandon, or keep as backup inbox? Affects AGENTS.md Rule 3a trusted-senders list.
3. After `bestEffort` removal: confirm cron behavior is stable for a week before declaring the workaround dead.

---

## Relationship to other projects

- **[mac-mini-migration](../mac-mini-migration/CLAUDE.md)** is the *execution arm* of this track for the hardware + identity cutover.
- **[skill-builder](../skill-builder/CLAUDE.md)** Phase 6's PreToolUse hook is structural enforcement that survives the migration intact.
- Once Bishop is fully consolidated under his own identity, the openclaw-message-send `chatGuid` handling may need a second pass — direct outbound currently relies on hardcoded email-keyed addressing because phone-keyed sends hit the same collision.
