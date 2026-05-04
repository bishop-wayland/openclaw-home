"""Per-hop JSONL logger. One line per hop, line-buffered.

Pattern copied from ~/.openclaw/workspace/skills/job-search/scripts/logger.py — same
shape (run_id, ts, event, fields), same forensic-debug discipline.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


class RunLogger:
    def __init__(self, run_id: str | None = None):
        if run_id is None:
            run_id = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = run_id
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOG_DIR / f"run-{run_id}.jsonl"
        self._fh = self.path.open("a", buffering=1)

    def emit(self, event: str, **fields):
        rec = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **fields,
        }
        line = json.dumps(rec, ensure_ascii=False, default=str)
        self._fh.write(line + "\n")
        print(line, file=sys.stderr)

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.emit("error", exc_type=exc_type.__name__, message=str(exc))
        self.close()
        return False
