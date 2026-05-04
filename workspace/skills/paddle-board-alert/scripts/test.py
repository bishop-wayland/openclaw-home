"""Three-fires verification harness for paddle-board-alert.

Three consecutive dry fires (real Open-Meteo fetch, no iMessage send) followed
by ONE real fire (sends an iMessage on go-days; silent on no-go-days).

A dry fire is "clean" when:
  - exit code 0
  - hops fire in order: triggered, config_loaded, forecast_fetched, evaluated,
    (deliver_skipped | suppressed), done(ok=true)
  - no event=error
  - forecast_fetched.n_hours >= 24, units == "mph"
  - evaluated.decision in {"go", "no-go"}
  - on "go": deliver_skipped present
  - on "no-go": suppressed present

If any dry fails, the real fire does NOT run.

The real fire's outcome depends on actual current weather. If the actual
forecast is "no-go", the harness still PASSES — silence is the no-go signal.
If "go", an iMessage is sent (verify it lands on Dave's phone).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
LOG_DIR = SKILL_DIR / "logs"
CHECK = SCRIPT_DIR / "check.py"


def latest_log() -> Path | None:
    files = sorted(LOG_DIR.glob("run-*.jsonl"))
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
    base_required = ["triggered", "config_loaded", "forecast_fetched", "evaluated", "done"]
    for k in base_required:
        if k not in events:
            issues.append(f"missing event: {k}")

    if events.get("error"):
        issues.append(f"error events present ({len(events['error'])})")

    ff = (events.get("forecast_fetched") or [{}])[0]
    if ff.get("n_hours", 0) < 24:
        issues.append(f"forecast_fetched.n_hours={ff.get('n_hours')} (<24)")
    if ff.get("units") != "mph":
        issues.append(f"forecast_fetched.units={ff.get('units')!r} (want 'mph')")

    ev = (events.get("evaluated") or [{}])[0]
    decision = ev.get("decision")
    if decision not in ("go", "no-go"):
        issues.append(f"evaluated.decision={decision!r} (want 'go' or 'no-go')")

    done = (events.get("done") or [{}])[0]
    if done.get("ok") is not True:
        issues.append(f"done.ok={done.get('ok')!r} (want True)")

    if decision == "go":
        if not real_send and "deliver_skipped" not in events:
            issues.append("decision=go + dry: missing deliver_skipped event")
        if real_send and "delivered" not in events:
            issues.append("decision=go + real: missing delivered event")
    elif decision == "no-go":
        if "suppressed" not in events:
            issues.append("decision=no-go: missing suppressed event")

    return (not issues), issues


def fire(label: str, *, real_send: bool) -> bool:
    flag = "--real-send" if real_send else "--dry-send"
    print(f"\n══════ FIRE: {label} ({flag}) ══════")
    cmd = [sys.executable, str(CHECK), flag]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"  → exit {proc.returncode}")
        if proc.stderr:
            print(f"  stderr (tail):\n{proc.stderr[-500:]}")
        return False

    log_path = latest_log()
    if not log_path:
        print("  → no log file produced")
        return False
    events = parse_log(log_path)
    ok, issues = assert_clean(events, real_send=real_send)

    ev = (events.get("evaluated") or [{}])[0]
    decision = ev.get("decision", "?")
    max_wind = ev.get("max_wind_in_window", "?")
    threshold = ev.get("threshold", "?")
    print(f"  → log: {log_path.name}")
    print(f"  → decision = {decision}    max_wind = {max_wind} mph    threshold = {threshold} mph")

    if decision == "go":
        ds = (events.get("deliver_skipped") or [{}])[0].get("would_send")
        dv = (events.get("delivered") or [{}])[0].get("message")
        msg = ds if not real_send else dv
        if msg:
            print(f"  → would_send = {msg!r}")

    if ok:
        print("  → CLEAN")
    else:
        print("  → ISSUES:")
        for i in issues:
            print(f"     - {i}")
    return ok


def main():
    ap = argparse.ArgumentParser(description="Three-fires harness for paddle-board-alert.")
    ap.add_argument("--no-real", action="store_true", help="Skip the real fire (3 dry only).")
    args = ap.parse_args()

    suffix = "(3 dry + 1 real)" if not args.no_real else "(3 dry, no real fire)"
    print(f"Three-fires harness for paddle-board-alert {suffix}")

    results: list[tuple[str, bool]] = []
    for i in range(3):
        ok = fire(f"dry #{i+1}", real_send=False)
        results.append((f"dry #{i+1}", ok))
        if not ok:
            print("\n  Dry fire failed — aborting before any real fire (per harness contract).")
            break
        time.sleep(1)

    if all(ok for _, ok in results) and not args.no_real:
        ok = fire("REAL (sends iMessage if go-day)", real_send=True)
        results.append(("real", ok))

    print("\n══════ SUMMARY ══════")
    for label, ok in results:
        print(f"  {label:30s} {'✓' if ok else '✗'}")
    all_ok = len(results) >= (3 if args.no_real else 4) and all(ok for _, ok in results)
    print(f"\nOverall: {'PASS' if all_ok else 'FAIL'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
