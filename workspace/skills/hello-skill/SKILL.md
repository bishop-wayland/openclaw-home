# `hello-skill` Skill

Send Dave a short iMessage greeting. Tunable tone (formal/casual/dry-humor) and target route. Smoke test for the skills-agent dispatch pipeline.

## Invocation

**On-demand (manual):**
```bash
python3 ~/.openclaw/workspace/skills/hello-skill/scripts/hello.py
python3 ~/.openclaw/workspace/skills/hello-skill/scripts/hello.py --dry-send
```

**Dry-send mode:** composes and logs the greeting, but does NOT call `openclaw message send`. Used for testing and for the harness.

## What happens

1. Load `config.json` (tone, template, route, tone clauses).
2. Compose the greeting by selecting a tone clause and substituting template variables.
3. Call `openclaw message send --channel bluebubbles --target '<recipient>'` with the greeting.
4. Log the result (delivery_sent or delivery_skipped in dry mode).

## Parameters (tunable)

All parameters live in `config.json`:
- `tone` — one of `formal`, `casual`, `dry-humor`. Default: `dry-humor`.
- `greeting_template` — string with `{tone_clause}`, `{hhmm}`, `{tz}` placeholders. Default: `"Hello, Dave. {tone_clause} Skill-builder smoke test passed at {hhmm} {tz}."`
- `target_channel` — `bluebubbles` (only option for now). Default: `bluebubbles`.
- `target_recipient` — iMessage handle; default: `iMessage;-;otte.dave@gmail.com`.
- `tone_clauses` — dict mapping tone names to short phrases. Defaults provided.

Edit `config.json` to change tone, template, or recipient without touching code.

## When Dave invokes Bishop

Dave doesn't typically invoke this skill directly — it's a smoke test for the dispatch pipeline. But for reference:

- `Bishop, send Dave a hello in formal tone.`
- `Bishop, dry-run the hello skill.`
- `Bishop, run the hello script now.`

Bishop reads SKILL.md (this file) and either runs the script directly or loads `config.json` to override the tone parameter.

## Cost

$0 per run. No paid APIs. BlueBubbles uses the Mac app's local iMessage stack.

## Logging & forensics

Logs land in `~/.openclaw/workspace/skills/hello-skill/logs/run-<iso>.jsonl`.

Required events:
- `triggered` — entry
- `config_load` — config loaded
- `compose_greeting` — greeting composed
- `delivery_skipped` (dry mode) — `openclaw message send` skipped
- `delivery_sent` (real mode) — `openclaw message send` succeeded
- `done` — exit

## Testing

```bash
# Run the three-fires harness
python3 ~/.openclaw/workspace/skills/hello-skill/scripts/test.py
```

The harness runs 3 dry fires + 1 real fire, verifying logs and delivery confirmation.

## Follow-ups

None — this is a minimal smoke test skill. Any enhancements (add more tones, support other channels) belong in a separate spec.
