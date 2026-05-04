"""Per-hop JSONL logger. One line per hop, written immediately (line-buffered)."""
from __future__ import annotations

import datetime as _dt
import json
import os
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
        self._fh = self.path.open("a", buffering=1)  # line-buffered

    def emit(self, event: str, **fields):
        rec = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **fields,
        }
        line = json.dumps(rec, ensure_ascii=False, default=str)
        self._fh.write(line + "\n")
        # Also mirror to stderr for interactive debugging
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
        return False  # do not suppress
