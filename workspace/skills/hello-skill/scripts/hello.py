#!/usr/bin/env python3
"""Hello-skill: send Dave a greeting via iMessage.

Hop sequence:
1. config_load — read config.json
2. compose_greeting — select tone clause, substitute template
3. deliver — call `openclaw message send` (skipped on --dry-send)
4. done — exit
"""

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Add scripts dir to path so we can import logger
SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from logger import Logger


def config_load(logger, dry_send):
    """Hop 1: Load and validate config.json."""
    try:
        config_path = SKILL_DIR / "config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            config = json.load(f)

        # Validate required keys
        required_keys = [
            "tone",
            "greeting_template",
            "target_channel",
            "target_recipient",
            "tone_clauses",
        ]
        for key in required_keys:
            if key not in config:
                raise KeyError(f"Missing required config key: {key}")

        logger.event(
            "config_load",
            path=str(config_path),
            tone=config["tone"],
            target_channel=config["target_channel"],
            target_recipient=config["target_recipient"],
        )
        return config
    except Exception as e:
        logger.event(
            "error",
            hop="config_load",
            message=str(e),
            traceback=traceback.format_exc(),
        )
        raise


def compose_greeting(logger, config):
    """Hop 2: Compose greeting by substituting template."""
    try:
        tone = config["tone"]
        template = config["greeting_template"]
        tone_clauses = config["tone_clauses"]

        if tone not in tone_clauses:
            raise ValueError(f"Unknown tone: {tone}. Available: {list(tone_clauses.keys())}")

        tone_clause = tone_clauses[tone]

        # Get current time in PT
        now = datetime.now(timezone.utc)
        # Simplified: just use local time for hhmm and tz
        # In production, would use tzinfo to get PT correctly
        import time
        local_time = time.localtime()
        hhmm = time.strftime("%H:%M", local_time)
        tz = "PDT" if time.daylight else "PST"  # Simplified

        # Substitute placeholders
        final_text = template.format(tone_clause=tone_clause, hhmm=hhmm, tz=tz)

        # Truncate for logging (max 200 chars)
        log_text = final_text[:200] if len(final_text) > 200 else final_text

        logger.event(
            "compose_greeting",
            tone_clause=tone_clause,
            final_text=log_text,
        )
        return final_text
    except Exception as e:
        logger.event(
            "error",
            hop="compose_greeting",
            message=str(e),
            traceback=traceback.format_exc(),
        )
        raise


def deliver(logger, config, greeting_text, dry_send):
    """Hop 3: Deliver greeting via openclaw message send (or skip if dry)."""
    try:
        if dry_send:
            logger.event(
                "delivery_skipped",
                would_send=greeting_text[:100],
                reason="--dry-send flag set",
            )
            return
        
        channel = config["target_channel"]
        recipient = config["target_recipient"]

        # Call openclaw message send
        cmd = [
            "openclaw",
            "message",
            "send",
            "--channel",
            channel,
            "--target",
            recipient,
            "--message",
            greeting_text,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise RuntimeError(
                f"openclaw message send failed with exit code {result.returncode}: {result.stderr}"
            )

        # Log success
        bb_stdout = result.stdout[:200] if result.stdout else "(empty)"
        logger.event(
            "delivery_sent",
            bb_exit_code=result.returncode,
            bb_stdout=bb_stdout,
        )
    except Exception as e:
        logger.event(
            "error",
            hop="deliver",
            message=str(e),
            traceback=traceback.format_exc(),
        )
        raise


def main():
    """Main pipeline orchestrator."""
    parser = argparse.ArgumentParser(description="Hello-skill: send Dave a greeting.")
    parser.add_argument("--dry-send", action="store_true", help="Compose but don't deliver")
    args = parser.parse_args()

    logger = Logger(SKILL_DIR)

    try:
        # Log entry
        logger.event(
            "triggered",
            dry_send=args.dry_send,
            argv=sys.argv,
        )

        # Run hops
        config = config_load(logger, args.dry_send)
        greeting_text = compose_greeting(logger, config)
        deliver(logger, config, greeting_text, args.dry_send)

        # Log completion
        logger.event("done", exit_status="success")
        sys.exit(0)

    except Exception as e:
        logger.event("done", exit_status="error")
        sys.exit(1)


if __name__ == "__main__":
    main()
