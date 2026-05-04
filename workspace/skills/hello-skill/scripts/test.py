"""Three-fires harness for hello-skill.

3 dry fires (compose only, no iMessage), then 1 real fire (sends iMessage).

A dry fire is "clean" when:
  - exit code 0
  - hops fire in order: triggered, config_load, compose_greeting,
    delivery_skipped, done
  - no event=error
  - compose_greeting.final_text is non-empty
  - no delivery_sent event

A real fire is "clean" when:
  - exit code 0
  - hops fire in order: triggered, config_load, compose_greeting,
    delivery_sent, done
  - no event=error
  - delivery_sent.bb_exit_code == 0

If any dry fails, the real fire does NOT run.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
LOG_DIR = SKILL_DIR / "logs"
HELLO = SCRIPT_DIR / "hello.py"

TEST_LOG_DIR = LOG_DIR


def latest_log(after: float) -> Path | None:
    files = [p for p in LOG_DIR.glob("run-*.jsonl") if p.stat().st_mtime >= after]
    files.sort()
    return files[-1] if files else None


def parse_log(path: Path) -> dict:
    events: dict[str, list[dict]] = {}
    with path.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            events.setdefault(rec.get("event"), []).append(rec)
    return events


def assert_clean(events: dict, *, real_send: bool) -> tuple[bool, list[str]]:
    issues: list[str] = []
    base_required = ["triggered", "config_load", "compose_greeting", "done"]
    for k in base_required:
        if k not in events:
            issues.append(f"missing event: {k}")

    if events.get("error"):
        issues.append(f"error events present ({len(events['error'])})")

    cg = (events.get("compose_greeting") or [{}])[0]
    if not cg.get("final_text"):
        issues.append("compose_greeting.final_text is empty")

    done = (events.get("done") or [{}])[0]
    if done.get("exit_status") != 0:
        issues.append(f"done.exit_status={done.get('exit_status')!r} (want 0)")

    if real_send:
        if "delivery_sent" not in events:
            issues.append("real fire: missing delivery_sent event")
        else:
            ds = events["delivery_sent"][0]
            if ds.get("bb_exit_code") != 0:
                issues.append(f"delivery_sent.bb_exit_code={ds.get('bb_exit_code')!r} (want 0)")
        if "delivery_skipped" in events:
            issues.append("real fire: delivery_skipped present (should be absent)")
    else:
        if "delivery_skipped" not in events:
            issues.append("dry fire: missing delivery_skipped event")
        if "delivery_sent" in events:
            issues.append("dry fire: delivery_sent present (should be absent)")

    return (not issues), issues


def fire(label: str, *, real_send: bool, test_log) -> bool:
    flag_args = [] if real_send else ["--dry-send"]
    print(f"\n══════ FIRE: {label} ({'real' if real_send else 'dry'}) ══════")
    start = time.time() - 1
    cmd = [sys.executable, str(HELLO), *flag_args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"  → exit {proc.returncode}")
        if proc.stderr:
            print(f"  stderr (tail):\n{proc.stderr[-500:]}")
        test_log.write({"label": label, "real_send": real_send, "ok": False, "exit": proc.returncode})
        return False

    log_path = latest_log(start)
    if not log_path:
        print("  → no log file produced")
        test_log.write({"label": label, "real_send": real_send, "ok": False, "issue": "no_log"})
        return False
    events = parse_log(log_path)
    ok, issues = assert_clean(events, real_send=real_send)

    cg = (events.get("compose_greeting") or [{}])[0]
    text = cg.get("final_text", "?")
    print(f"  → log: {log_path.name}")
    print(f"  → final_text = {text!r}")
    if real_send:
        ds = (events.get("delivery_sent") or [{}])[0]
        print(f"  → bb_exit_code = {ds.get('bb_exit_code')}")

    if ok:
        print("  → CLEAN")
    else:
        print("  → ISSUES:")
        for i in issues:
            print(f"     - {i}")
    test_log.write({
        "label": label,
        "real_send": real_send,
        "ok": ok,
        "issues": issues,
        "log_path": str(log_path),
    })
    return ok


class TestLog:
    def __init__(self):
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = TEST_LOG_DIR / f"test-{ts}.jsonl"
        self._fh = self.path.open("a", buffering=1)

    def write(self, rec: dict):
        rec = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), **rec}
        self._fh.write(json.dumps(rec, default=str) + "\n")

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="Three-fires harness for hello-skill.")
    ap.add_argument("--no-real", action="store_true", help="Skip the real fire (3 dry only).")
    args = ap.parse_args()

    suffix = "(3 dry + 1 real)" if not args.no_real else "(3 dry, no real fire)"
    print(f"Three-fires harness for hello-skill {suffix}")

    test_log = TestLog()
    print(f"  test log: {test_log.path.name}")
    results: list[tuple[str, bool]] = []
    for i in range(3):
        ok = fire(f"dry #{i+1}", real_send=False, test_log=test_log)
        results.append((f"dry #{i+1}", ok))
        if not ok:
            print("\n  Dry fire failed — aborting before any real fire (per harness contract).")
            break
        time.sleep(1)

    if all(ok for _, ok in results) and not args.no_real:
        ok = fire("REAL (sends iMessage)", real_send=True, test_log=test_log)
        results.append(("real", ok))

    print("\n══════ SUMMARY ══════")
    for label, ok in results:
        print(f"  {label:30s} {'✓' if ok else '✗'}")
    all_ok = len(results) >= (3 if args.no_real else 4) and all(ok for _, ok in results)
    print(f"\nOverall: {'PASS' if all_ok else 'FAIL'}")
    test_log.close()
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
