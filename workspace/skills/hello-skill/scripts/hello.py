"""Hello-skill main pipeline.

Hops:
  1. config_load       — read config.json
  2. compose_greeting  — fill template with tone clause + current time
  3. deliver           — call `openclaw message send` (skipped under --dry-send)
  4. done              — exit 0

CLI:
  python3 hello.py              # real send (default)
  python3 hello.py --dry-send   # compose only, no iMessage
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
import time as _time
import traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
CONFIG_PATH = SKILL_DIR / "config.json"

sys.path.insert(0, str(SCRIPT_DIR))
from logger import RunLogger  # noqa: E402

REQUIRED_KEYS = ("tone", "greeting_template", "target_channel", "target_recipient", "tone_clauses")


def config_load(log: RunLogger) -> dict:
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"config not found at {CONFIG_PATH}")
    cfg = json.loads(CONFIG_PATH.read_text())
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise RuntimeError(f"config missing required keys: {missing}")
    if cfg["tone"] not in cfg["tone_clauses"]:
        raise RuntimeError(
            f"tone={cfg['tone']!r} has no entry in tone_clauses (keys: {list(cfg['tone_clauses'])})"
        )
    log.emit(
        "config_load",
        path=str(CONFIG_PATH),
        tone=cfg["tone"],
        target_channel=cfg["target_channel"],
        target_recipient=cfg["target_recipient"],
    )
    return cfg


def compose_greeting(cfg: dict, log: RunLogger) -> str:
    tone_clause = cfg["tone_clauses"][cfg["tone"]]
    now_local = _dt.datetime.now().astimezone()
    hhmm = now_local.strftime("%H:%M")
    tz = _time.strftime("%Z", _time.localtime())
    text = cfg["greeting_template"].format(tone_clause=tone_clause, hhmm=hhmm, tz=tz)
    if not text or not text.strip():
        raise RuntimeError("composed greeting is empty after substitution")
    log.emit("compose_greeting", tone_clause=tone_clause, final_text=text[:200])
    return text


def deliver(cfg: dict, text: str, *, dry_send: bool, log: RunLogger) -> None:
    if dry_send:
        log.emit("delivery_skipped", would_send=text)
        return
    cmd = [
        "openclaw",
        "message",
        "send",
        "--channel",
        cfg["target_channel"],
        "--target",
        cfg["target_recipient"],
        "--message",
        text,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        log.emit(
            "error",
            hop="deliver",
            message=f"openclaw message send exited {proc.returncode}",
            traceback=(proc.stderr or "")[-500:],
        )
        raise RuntimeError(f"openclaw message send failed: rc={proc.returncode}")
    log.emit(
        "delivery_sent",
        bb_exit_code=proc.returncode,
        bb_stdout=(proc.stdout or "")[:500],
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="hello-skill: smoke-test iMessage greeting.")
    ap.add_argument("--dry-send", action="store_true", help="compose only; no iMessage delivered")
    args = ap.parse_args(argv)

    log = RunLogger()
    log.emit("triggered", dry_send=bool(args.dry_send), argv=sys.argv[1:])
    try:
        cfg = config_load(log)
        text = compose_greeting(cfg, log)
        deliver(cfg, text, dry_send=args.dry_send, log=log)
        log.emit("done", exit_status=0)
        print(json.dumps({"dry_send": bool(args.dry_send), "log": str(log.path)}))
        return 0
    except Exception as e:
        log.emit(
            "error",
            hop="main",
            message=f"{type(e).__name__}: {e}",
            traceback=traceback.format_exc(limit=4),
        )
        log.emit("done", exit_status=1)
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main())
