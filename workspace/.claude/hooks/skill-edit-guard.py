#!/usr/bin/env python3
"""
PreToolUse guard for Bishop's session.

Denies Edit/Write/MultiEdit on files under ~/.openclaw/workspace/skills/.
Code changes to skills route through skills-agent dispatch, not in-session edits.

Trust model: Bishop runs on Haiku; skills-agent runs on a stronger model with a
code-focused harness. Routing all code work to skills-agent ensures code quality.
This is a competence-based restriction, not a security boundary.
"""
import json
import os
import sys

PROTECTED_ROOT = os.path.realpath(os.path.expanduser("~/.openclaw/workspace/skills"))


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        # Malformed input — don't block. Let Claude Code's normal handling apply.
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path")
    if not file_path:
        sys.exit(0)

    abs_path = os.path.realpath(os.path.expanduser(file_path))
    if abs_path != PROTECTED_ROOT and not abs_path.startswith(PROTECTED_ROOT + os.sep):
        sys.exit(0)

    deny_reason = (
        f"Skill files under {PROTECTED_ROOT}/ cannot be edited in your session. "
        "Code changes to skills route through skills-agent dispatch.\n\n"
        "What to do instead:\n"
        "  1. Write a patch-spec at ~/.openclaw/specs/<skill-name>-patch-<short-name>.md "
        "(see ~/.openclaw/workspace/skills/skill-builder/SPEC_TEMPLATE.md for the shape; "
        "patch-spec headers: Mode: patch, Derive from: null).\n"
        "  2. Dispatch the worker via sessions_spawn(agentId: 'skills-agent', task: ...) "
        "per the 'Skills-Agent Dispatch' section of your own AGENTS.md.\n"
        "  3. After the announce, run the patch-mode post-announce protocol "
        "(verify state preservation, fire one preview, relay diff to Dave).\n\n"
        f"Attempted edit blocked: {file_path}\n\n"
        "If you believe this hook is misfiring (e.g., the path is genuinely outside the "
        "skills tree but matched by mistake), surface it to Dave — do not work around it."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": deny_reason,
        }
    }))


if __name__ == "__main__":
    main()
