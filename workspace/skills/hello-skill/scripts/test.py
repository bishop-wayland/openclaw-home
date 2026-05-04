#!/usr/bin/env python3
"""Three-fires harness for hello-skill.

Runs 3 dry + 1 real fire. Validates logs, events, and delivery confirmation.
Exits 0 only when all fires pass.
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
LOGS_DIR = SKILL_DIR / "logs"


def clear_logs():
    """Clear the logs directory before each fire."""
    if LOGS_DIR.exists():
        shutil.rmtree(LOGS_DIR)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def run_fire(dry=True):
    """Run a single fire (dry or real).
    
    Returns:
        (exit_code, log_path) if successful, (1, None) if subprocess fails.
    """
    cmd = [sys.executable, str(SCRIPT_DIR / "hello.py")]
    if dry:
        cmd.append("--dry-send")

    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Find the most recent log file
    if LOGS_DIR.exists():
        log_files = sorted(LOGS_DIR.glob("run-*.jsonl"))
        if log_files:
            log_path = log_files[-1]
            return result.returncode, log_path
    
    return result.returncode, None


def validate_log(log_path, expect_real=False):
    """Validate log structure and events.
    
    Expected events:
    - triggered
    - config_load
    - compose_greeting
    - delivery_skipped (if dry) or delivery_sent (if real)
    - done
    
    Returns:
        (pass, errors) where errors is a list of validation failures.
    """
    errors = []
    events = []
    
    try:
        with open(log_path, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        errors.append(f"Invalid JSON in log: {e}")
                        return False, errors
    except Exception as e:
        errors.append(f"Failed to read log {log_path}: {e}")
        return False, errors
    
    if not events:
        errors.append("No events in log")
        return False, errors
    
    # Check for required events in order
    required_events = [
        "triggered",
        "config_load",
        "compose_greeting",
        "delivery_skipped" if not expect_real else "delivery_sent",
        "done",
    ]
    
    event_names = [e.get("event") for e in events]
    for req in required_events:
        if req not in event_names:
            errors.append(f"Missing required event: {req}")
    
    # Check for error events
    error_events = [e for e in events if e.get("event") == "error"]
    if error_events:
        for err_evt in error_events:
            errors.append(f"Error event found: {err_evt.get('message', 'unknown')}")
    
    # Validate triggered event
    triggered = next((e for e in events if e.get("event") == "triggered"), None)
    if triggered:
        if "dry_send" not in triggered:
            errors.append("triggered event missing dry_send field")
    
    # Validate delivery event
    delivery = next(
        (e for e in events if e.get("event") in ["delivery_skipped", "delivery_sent"]),
        None,
    )
    if not delivery:
        errors.append("No delivery event found")
    elif expect_real and delivery.get("event") != "delivery_sent":
        errors.append(f"Expected delivery_sent, got {delivery.get('event')}")
    elif not expect_real and delivery.get("event") != "delivery_skipped":
        errors.append(f"Expected delivery_skipped, got {delivery.get('event')}")
    
    return len(errors) == 0, errors


def run_harness():
    """Run the three-fires harness."""
    print("=" * 60)
    print("Hello-skill three-fires harness")
    print("=" * 60)
    
    all_passed = True
    
    # Run 3 dry fires
    for i in range(1, 4):
        clear_logs()
        
        print(f"\n[Dry fire {i}/3]")
        exit_code, log_path = run_fire(dry=True)
        
        if exit_code != 0:
            print(f"  ✗ FAILED: script exited with code {exit_code}")
            all_passed = False
            continue
        
        if not log_path:
            print(f"  ✗ FAILED: no log file found")
            all_passed = False
            continue
        
        passed, errors = validate_log(log_path, expect_real=False)
        if passed:
            print(f"  ✓ PASS")
        else:
            print(f"  ✗ FAILED:")
            for err in errors:
                print(f"    - {err}")
            all_passed = False
    
    if not all_passed:
        print("\n[Summary] Dry fires failed. Skipping real fire.")
        return 1
    
    # Run 1 real fire
    clear_logs()
    
    print(f"\n[Real fire 1/1]")
    exit_code, log_path = run_fire(dry=False)
    
    if exit_code != 0:
        print(f"  ✗ FAILED: script exited with code {exit_code}")
        return 1
    
    if not log_path:
        print(f"  ✗ FAILED: no log file found")
        return 1
    
    passed, errors = validate_log(log_path, expect_real=True)
    if passed:
        print(f"  ✓ PASS")
    else:
        print(f"  ✗ FAILED:")
        for err in errors:
            print(f"    - {err}")
        return 1
    
    print("\n" + "=" * 60)
    print("All fires passed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_harness())
