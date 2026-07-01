"""OpenClaw native imsg CLI for iMessage delivery.

This skill runs from openclaw cron via the `exec` tool, which suppresses
alert-circuit's announce/deliver path. We deliver iMessage via the imsg CLI
(OpenClaw's native provider, which replaced BlueBubbles on 2026-06-30).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

DAVE_PHONE = "+16508239528"


def send_imessage(text: str, *, timeout: float = 30.0) -> tuple[bool, dict]:
    """Call imsg CLI to send iMessage. Returns (ok, detail)."""
    try:
        result = subprocess.run(
            ["imsg", "send", "--to", DAVE_PHONE, "--text", text],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, {"status": 0, "response": {"sent": True}}
        else:
            return False, {"status": result.returncode, "error": result.stderr}
    except subprocess.TimeoutExpired:
        return False, {"error": "imsg command timed out"}
    except FileNotFoundError:
        return False, {"error": "imsg CLI not found (not installed or not in PATH)"}
    except Exception as e:
        return False, {"error": f"{type(e).__name__}: {e}"}
