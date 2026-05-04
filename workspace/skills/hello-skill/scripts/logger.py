"""JSONL event logger for hello-skill."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class Logger:
    """Emit per-hop JSONL log lines."""

    def __init__(self, skill_dir):
        """Initialize logger with skill directory path."""
        self.skill_dir = Path(skill_dir)
        self.logs_dir = self.skill_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Create log file with ISO timestamp
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.log_path = self.logs_dir / f"run-{now}.jsonl"

    def event(self, event_type, **fields):
        """Log a single event as JSONL."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **fields,
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def read_log(self):
        """Read all events from the current log file."""
        events = []
        if self.log_path.exists():
            with open(self.log_path, "r") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        return events
