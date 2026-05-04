"""Thin wrapper around `gog gmail send`. Returns (ok, detail).

Fetches GOG_KEYRING_PASSWORD from 1Password via op-gog-keyring-password.sh and
injects it into the subprocess env. This lets gog read its file-backend keyring
without a TTY — required for launchd / cron / non-interactive shells.
"""
from __future__ import annotations

import json
import os
import subprocess

GOG_ACCOUNT = "bishopunit937@gmail.com"
DEFAULT_TO = "otte.dave@gmail.com"
KEYRING_PW_SCRIPT = "/Users/bishop/.openclaw/scripts/op-gog-keyring-password.sh"


def _fetch_keyring_password() -> str:
    proc = subprocess.run([KEYRING_PW_SCRIPT], capture_output=True, text=True, check=True, timeout=20)
    envelope = json.loads(proc.stdout)
    return envelope["values"]["value"]


def send_html(subject: str, html_body: str, to: str = DEFAULT_TO) -> tuple[bool, str]:
    env = os.environ.copy()
    env["GOG_ACCOUNT"] = GOG_ACCOUNT
    try:
        env["GOG_KEYRING_PASSWORD"] = _fetch_keyring_password()
    except Exception as e:
        return False, f"keyring password fetch failed: {type(e).__name__}: {e}"

    try:
        proc = subprocess.run(
            ["gog", "gmail", "send",
             "--to", to,
             "--subject", subject,
             "--body-html", html_body,
             "--no-input"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "gog timed out after 60s"
    except FileNotFoundError:
        return False, "gog binary not found on PATH"

    if proc.returncode != 0:
        return False, f"gog exit={proc.returncode} stderr={proc.stderr.strip()[:500]}"
    return True, proc.stdout.strip()[:500]
