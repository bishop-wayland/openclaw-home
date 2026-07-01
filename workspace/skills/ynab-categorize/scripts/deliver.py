"""Delivery modules for email (gog) and iMessage (BlueBubbles)."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# Email delivery via gog (Gmail OAuth)
# ─────────────────────────────────────────────────────────────

GOG_ACCOUNT = "yutani.w.bishop@gmail.com"
KEYRING_PW_SCRIPT = "/Users/bishop/.openclaw/scripts/op-gog-keyring-password.sh"


def _fetch_gog_keyring_password() -> str:
    """Fetch GOG keyring password from 1Password."""
    proc = subprocess.run(
        [KEYRING_PW_SCRIPT],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    envelope = json.loads(proc.stdout)
    return envelope["values"]["value"]


def send_email(subject: str, html_body: str, to: str) -> tuple[bool, dict]:
    """
    Send HTML email via gog (Gmail OAuth).
    
    Returns: (success, detail)
    """
    env = os.environ.copy()
    env["GOG_ACCOUNT"] = GOG_ACCOUNT
    
    try:
        env["GOG_KEYRING_PASSWORD"] = _fetch_gog_keyring_password()
    except Exception as e:
        return False, {
            "error": f"keyring password fetch failed: {type(e).__name__}: {e}",
        }
    
    try:
        proc = subprocess.run(
            [
                "gog", "gmail", "send",
                "--to", to,
                "--subject", subject,
                "--body-html", html_body,
                "--no-input",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, {"error": "gog timed out after 60s"}
    except FileNotFoundError:
        return False, {"error": "gog binary not found on PATH"}
    
    if proc.returncode != 0:
        return False, {
            "error": f"gog exit={proc.returncode}",
            "stderr": proc.stderr.strip()[:200],
        }
    
    return True, {
        "status": 204,
        "response": proc.stdout.strip()[:200],
    }


# ─────────────────────────────────────────────────────────────
# iMessage delivery via BlueBubbles
# ─────────────────────────────────────────────────────────────

OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
DAVE_CHAT_GUID = "iMessage;-;otte.dave@gmail.com"


def _load_bb_config() -> tuple[str, str]:
    """Load BlueBubbles server URL and password from openclaw config."""
    cfg = json.loads(OPENCLAW_CONFIG.read_text())
    bb = cfg["channels"]["bluebubbles"]
    return bb["serverUrl"].rstrip("/"), bb["password"]


def send_imessage(text: str, *, timeout: float = 30.0) -> tuple[bool, dict]:
    """
    Send iMessage via BlueBubbles.
    
    Returns: (success, detail)
    """
    try:
        server_url, password = _load_bb_config()
    except Exception as e:
        return False, {
            "error": f"Failed to load BlueBubbles config: {type(e).__name__}: {e}",
        }
    
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
            return True, {
                "status": resp.status,
                "response": payload,
            }
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500] if e.fp else ""
        return False, {
            "status": e.code,
            "error": body_text,
        }
    except urllib.error.URLError as e:
        return False, {
            "error": f"URLError: {e.reason}",
        }
    except Exception as e:
        return False, {
            "error": f"{type(e).__name__}: {e}",
        }
