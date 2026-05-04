"""BlueBubbles-direct iMessage delivery from inside the Python script.

This skill runs from openclaw cron via the `exec` tool, which suppresses
alert-circuit's announce/deliver path (any tool call trips
hasOutboundSideEffects). So we deliver iMessage directly here, same end-to-end
shape job-search uses with launchd, just adapted for openclaw cron.

Architectural rules baked in (alert-circuit invariant 6):
- chatGuid is email-keyed: "iMessage;-;otte.dave@gmail.com"
- creds come from ~/.openclaw/openclaw.json at runtime, NOT env files / repo
- phone-keyed sends are forbidden (Bishop Identity Track collision)
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
DAVE_CHAT_GUID = "iMessage;-;otte.dave@gmail.com"


def _load_bb_config() -> tuple[str, str]:
    cfg = json.loads(OPENCLAW_CONFIG.read_text())
    bb = cfg["channels"]["bluebubbles"]
    return bb["serverUrl"].rstrip("/"), bb["password"]


def send_imessage(text: str, *, timeout: float = 30.0) -> tuple[bool, dict]:
    """POST to BB /api/v1/message/text. Returns (ok, detail)."""
    server_url, password = _load_bb_config()
    url = f"{server_url}/api/v1/message/text?{urllib.parse.urlencode({'password': password})}"
    body = json.dumps({
        "chatGuid": DAVE_CHAT_GUID,
        "tempGuid": str(uuid.uuid4()),
        "message": text,
        "method": "apple-script",
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"raw": raw[:500]}
            return True, {"status": resp.status, "response": payload}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500] if e.fp else ""
        return False, {"status": e.code, "error": body_text}
    except urllib.error.URLError as e:
        return False, {"error": f"URLError: {e.reason}"}
    except Exception as e:
        return False, {"error": f"{type(e).__name__}: {e}"}
