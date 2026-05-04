#!/usr/bin/env python3
"""Three-fires verification harness for ynab-categorize skill.

Runs 3 dry fires (--dry-send --no-apply) + 1 real fire (--no-apply only).
All fires validate the pipeline end-to-end.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
LOG_DIR = SKILL_DIR / "logs"


def latest_log() -> Path | None:
    files = sorted(LOG_DIR.glob("run-*.jsonl"))
    return files[-1] if files else None


def parse_log(path: Path) -> dict[str, list]:
    """Parse JSONL log into event buckets."""
    events = {}
    with path.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            event = rec.get("event")
            events.setdefault(event, []).append(rec)
    return events


def assert_clean_run(events: dict, *, dry_send: bool) -> tuple[bool, list[str]]:
    """Check that a run log is clean."""
    issues = []
    
    # Required hops in order
    required = [
        "triggered", "auth", "fetch_categories", "fetch_uncategorized",
        "load_lookup", "classify_summary", "compose_digest", "compose_imessage",
        "done"
    ]
    
    for hop in required:
        if hop not in events:
            issues.append(f"missing event: {hop}")
    
    # Error events are bad
    if events.get("error"):
        issues.append(f"error events present: {len(events['error'])}")
    
    # Delivery checks
    if dry_send:
        if "deliver_email_skipped" not in events:
            issues.append("dry run should have deliver_email_skipped")
        if "deliver_imessage_skipped" not in events:
            issues.append("dry run should have deliver_imessage_skipped")
    else:
        if "deliver_email_sent" not in events:
            issues.append("real fire should have deliver_email_sent")
        if "deliver_imessage_sent" not in events:
            issues.append("real fire should have deliver_imessage_sent")
    
    # Pending persist should always happen
    if "persist_pending" not in events:
        issues.append("persist_pending event missing")
    
    return (not issues), issues


def fire(label: str, *, dry_send: bool, limit_txns: int = 20) -> bool:
    """Run one fire and validate."""
    flags = ["dry_send" if dry_send else "real_fire", f"limit={limit_txns}"]
    print(f"\n══════ FIRE: {label} ({', '.join(flags)}) ══════")
    
    cmd = [sys.executable, str(SCRIPT_DIR / "propose.py")]
    if dry_send:
        cmd.append("--dry-send")
    # All test fires use --no-apply to avoid writing to YNAB
    cmd.append("--no-apply")
    # Limit transactions for faster test feedback
    cmd.extend(["--limit-txns", str(limit_txns)])
    
    proc = subprocess.run(cmd, capture_output=False, timeout=300)
    
    if proc.returncode != 0:
        print(f"  → exit code {proc.returncode}")
        return False
    
    log_path = latest_log()
    if not log_path:
        print("  → no log file produced")
        return False
    
    events = parse_log(log_path)
    ok, issues = assert_clean_run(events, dry_send=dry_send)
    
    print(f"  → log: {log_path.name}")
    
    if ok:
        auto_apply = len(events.get("classify_lookup_hit", []))
        pending = events.get("classify_summary", [{}])[0].get("pending_approval", 0)
        manual = events.get("classify_summary", [{}])[0].get("manual_review_needed", 0)
        print(f"  → CLEAN. auto_apply={auto_apply} pending={pending} manual={manual}")
    else:
        print("  → ISSUES:")
        for issue in issues:
            print(f"     - {issue}")
    
    return ok


def main():
    parser = __import__("argparse").ArgumentParser(description="Three-fires harness for ynab-categorize")
    parser.add_argument("--no-real", action="store_true", help="Skip real fire")
    args = parser.parse_args()
    
    print("Three-fires verification (3 dry + 1 real)")
    print("(Running with --limit-txns 20 for faster feedback)")
    
    results = []
    
    # 3 dry fires (with limited transaction count for speed)
    for i in range(3):
        try:
            ok = fire(f"dry #{i+1}", dry_send=True, limit_txns=20)
            results.append(("dry", ok))
        except subprocess.TimeoutExpired:
            print(f"  → TIMEOUT after 300s")
            results.append(("dry", False))
        time.sleep(1)
    
    # 1 real fire (with more transactions for more realistic validation)
    if not args.no_real:
        try:
            ok = fire("REAL (sends email+iMessage)", dry_send=False, limit_txns=30)
            results.append(("real", ok))
        except subprocess.TimeoutExpired:
            print(f"  → TIMEOUT after 300s")
            results.append(("real", False))
    
    # Summary
    print("\n══════ SUMMARY ══════")
    for label, ok in results:
        print(f"  {label:8} {'✓ PASS' if ok else '✗ FAIL'}")
    
    all_ok = all(ok for _, ok in results)
    print(f"\nOverall: {'PASS' if all_ok else 'FAIL'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
