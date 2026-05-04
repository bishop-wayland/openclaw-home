"""Three-fires verification harness.

Per the methodology: three consecutive clean runs of the full pipeline (except for the
final email send — we use --dry-send to avoid spamming Dave's inbox three times) plus
ONE final real fire that actually sends the email.

Each dry-run validates: ATS fetch counts within tolerance, pre-filter narrows, Claude
returns valid JSON, dedup runs, format produces non-empty body. Real fire validates the
gmail send actually completes.
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
DEDUP_DB = SKILL_DIR / "state" / "seen.db"


def latest_log() -> Path | None:
    files = sorted(LOG_DIR.glob("run-*.jsonl"))
    return files[-1] if files else None


def parse_log(path: Path) -> dict:
    events = {}
    with path.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            events.setdefault(rec.get("event"), []).append(rec)
    return events


def assert_clean_run(events: dict, *, expect_send: bool, expect_layer2: bool) -> tuple[bool, list[str]]:
    issues = []
    base_required = ["triggered", "config_loaded", "layer1_complete", "prefiltered",
                     "claude_invoked", "claude_responded", "validated", "deduped",
                     "email_formatted", "done"]
    for k in base_required:
        if k not in events:
            issues.append(f"missing event: {k}")
    if events.get("error"):
        issues.append(f"error events present: {len(events['error'])}")
    if expect_layer2:
        if "layer2_invoked" not in events:
            issues.append("expected layer2_invoked (Phase 2 enabled) but missing")
        if "layer2_responded" not in events:
            issues.append("expected layer2_responded (Phase 2 enabled) but missing")
    else:
        if "layer2_skipped" not in events:
            issues.append("expected layer2_skipped (Phase 2 disabled) but missing")
    if expect_send:
        if "gmail_sent" not in events:
            issues.append("expected gmail_sent (real fire) but missing")
        if "marked_seen" not in events:
            issues.append("expected marked_seen (real fire) but missing")
    else:
        if "deliver_skipped" not in events:
            issues.append("dry-run should have deliver_skipped event")
        if "marked_seen_skipped" not in events:
            issues.append("dry-run should have marked_seen_skipped event")
    return (not issues), issues


def fire(label: str, *, dry_send: bool, skip_layer2: bool, layer2_max_searches: int | None = None) -> bool:
    flags = []
    if dry_send:
        flags.append("dry_send")
    flags.append("layer2=on" if not skip_layer2 else "layer2=off")
    if layer2_max_searches is not None and not skip_layer2:
        flags.append(f"max_searches={layer2_max_searches}")
    print(f"\n══════ FIRE: {label} ({', '.join(flags)}) ══════")
    cmd = [sys.executable, str(SCRIPT_DIR / "search.py")]
    if dry_send:
        cmd.append("--dry-send")
    if skip_layer2:
        cmd.append("--skip-layer2")
    if layer2_max_searches is not None:
        cmd.extend(["--layer2-max-searches", str(layer2_max_searches)])
    proc = subprocess.run(cmd, capture_output=False)
    if proc.returncode != 0:
        print(f"  → exit code {proc.returncode}")
        return False
    log_path = latest_log()
    if not log_path:
        print("  → no log file produced")
        return False
    events = parse_log(log_path)
    ok, issues = assert_clean_run(events, expect_send=not dry_send, expect_layer2=not skip_layer2)
    print(f"  → log: {log_path.name}")
    if ok:
        results = events.get("validated", [{}])[0].get("results", "?")
        kept = events.get("prefiltered", [{}])[0].get("kept", "?")
        new = events.get("deduped", [{}])[0].get("new", "?")
        l1_cost = events.get("claude_responded", [{}])[0].get("cost_usd", 0) or 0
        l2 = events.get("layer2_responded", [{}])[0] if events.get("layer2_responded") else {}
        l2_cost = l2.get("cost_usd", 0) or 0
        l2_searches = l2.get("web_searches", 0) if l2 else 0
        l2_results = l2.get("l2_results", 0) if l2 else 0
        total_cost = round(float(l1_cost) + float(l2_cost), 4)
        print(f"  → CLEAN. prefilter_kept={kept} claude_results={results} new_after_dedup={new}")
        if l2:
            print(f"           layer2_searches={l2_searches} layer2_results={l2_results} l2_cost=${l2_cost}")
        print(f"           total_cost=${total_cost}")
    else:
        print("  → ISSUES:")
        for i in issues:
            print(f"     - {i}")
    return ok


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Three-fires verification harness for job-search skill.")
    ap.add_argument("--no-real", action="store_true", help="Skip the final real-send fire (dry only).")
    ap.add_argument("--skip-layer2", action="store_true",
                    help="Skip Layer 2 in all fires (cheap smoke test mode).")
    ap.add_argument("--layer2-max-searches", type=int, default=None,
                    help="Override Layer 2 max_searches budget for harness fires.")
    ap.add_argument("--phase1-only-dry", action="store_true",
                    help="Run dry fires with --skip-layer2 (cheaper) but the real fire still does Phase 2.")
    args = ap.parse_args()
    label_dry = "Phase 1 only" if (args.skip_layer2 or args.phase1_only_dry) else "Phase 1+2"
    label_real = "Phase 1 only" if args.skip_layer2 else "Phase 1+2"
    suffix = "(3 dry + 1 real)" if not args.no_real else "(3 dry, no real send)"
    print(f"Three-fires verification {suffix}  dry={label_dry}  real={label_real}")

    # Reset dedup db so each fire produces a meaningful digest. Dry fires don't commit
    # state (search.py skips mark_seen on --dry-send), but the real fire at the end will.
    if DEDUP_DB.exists():
        DEDUP_DB.unlink()
        print(f"  reset {DEDUP_DB.name}")
    results = []
    dry_skip_l2 = args.skip_layer2 or args.phase1_only_dry
    for i in range(3):
        ok = fire(f"dry #{i+1}", dry_send=True, skip_layer2=dry_skip_l2,
                  layer2_max_searches=args.layer2_max_searches)
        results.append(("dry", ok))
        time.sleep(1)
    if not args.no_real:
        real_ok = fire("REAL (sends email)", dry_send=False, skip_layer2=args.skip_layer2,
                       layer2_max_searches=args.layer2_max_searches)
        results.append(("real", real_ok))

    print("\n══════ SUMMARY ══════")
    for label, ok in results:
        print(f"  {label:8} {'✓' if ok else '✗'}")
    all_ok = all(ok for _, ok in results)
    print(f"\nOverall: {'PASS' if all_ok else 'FAIL'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
