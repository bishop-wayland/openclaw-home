#!/usr/bin/env python3
"""
Apply an amount-based categorization rule from Dave's iMessage.

Parses iMessages like:
  "remember $-2500.00 = Spousal Support"
  "remember $500 means Groceries"
  "always $-100.00 → Housing"
  "remember $-2500.00 as 💰 Spousal Support"

Validates amount (must be a parseable number) and category (must exactly match
an existing YNAB category name). On success, appends the rule to
state/amount-lookup.json and sends Dave a confirmation iMessage.

Usage:
  python3 apply-amount-rule.py --message "<iMessage text>"
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Local imports
sys.path.insert(0, str(Path(__file__).parent))
import amount_lookup
import deliver

SKILL_DIR = Path(__file__).resolve().parent.parent
AMOUNT_LOOKUP_PATH = SKILL_DIR / "state" / "amount-lookup.json"

# Config
CONFIG_PATH = SKILL_DIR / "config.json"

# iMessage pattern: "remember $-2500.00 = Spousal Support"
# Accepts: remember / always
# Separators: = | → | -> | means | as
AMOUNT_RULE_RE = re.compile(
    r"(?i)\b(?:remember|always)\b\s+\$?(-?\d+(?:\.\d+)?)\s*(?:=|→|->|means|as)\s+(.+?)$",
    re.MULTILINE,
)


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def get_ynab_token() -> str:
    """Fetch YNAB token from 1Password."""
    proc = subprocess.run(
        ["/Users/bishop/.openclaw/scripts/op-ynab-key.sh"],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    envelope = json.loads(proc.stdout)
    return envelope["values"]["value"]


def ynab_get(endpoint: str, token: str, timeout: int = 30) -> dict | None:
    """GET request to YNAB API."""
    url = f"https://api.ynab.com/v1{endpoint}"
    try:
        proc = subprocess.run(
            ["curl", "-s", "-H", f"Authorization: Bearer {token}", url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        return None
    except Exception:
        return None


def fetch_category_names(budget_id: str, token: str) -> list[str]:
    """Fetch all YNAB category group + category names for the given budget."""
    resp = ynab_get(f"/budgets/{budget_id}/categories", token)
    if not resp:
        return []
    names = []
    for group in resp.get("data", {}).get("category_groups", []):
        for cat in group.get("categories", []):
            names.append(cat["name"])
    return names


def parse_message(message: str) -> tuple[float, str] | None:
    """
    Parse Dave's iMessage into (amount_dollars, category_text).
    Returns None if the message doesn't match the expected pattern.
    """
    m = AMOUNT_RULE_RE.search(message)
    if not m:
        return None
    amount_str = m.group(1).strip()
    category_text = m.group(2).strip()
    try:
        amount = float(amount_str)
    except ValueError:
        return None
    return amount, category_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply amount-based categorization rule")
    parser.add_argument("--message", required=True, help="Dave's iMessage text")
    args = parser.parse_args()

    # Parse message
    parsed = parse_message(args.message)
    if parsed is None:
        ok, _ = deliver.send_imessage(
            "⚠️ Couldn't parse that amount rule. Expected format:\n"
            "  remember $-2500.00 = Spousal Support\n"
            "  remember $500 means Groceries\n"
            "  always $-100.00 → Housing"
        )
        sys.exit(1)

    amount, category_text = parsed

    # Auth + fetch YNAB categories for validation
    try:
        ynab_token = get_ynab_token()
    except Exception as e:
        deliver.send_imessage(f"⚠️ Amount rule failed: couldn't fetch YNAB token: {e}")
        sys.exit(1)

    config = load_config()
    budget_id = config.get("budget_id", "")
    category_names = fetch_category_names(budget_id, ynab_token)

    if not category_names:
        deliver.send_imessage(
            f"⚠️ Amount rule failed: couldn't fetch YNAB categories to validate '{category_text}'. "
            "Check YNAB connectivity and retry."
        )
        sys.exit(1)

    # Exact-match validation
    if category_text not in category_names:
        # Find close matches to help Dave
        lower_text = category_text.lower()
        close = [c for c in category_names if lower_text in c.lower() or c.lower() in lower_text]
        hint = ""
        if close:
            hint = "\n\nClose matches:\n" + "\n".join(f"  • {c}" for c in close[:5])
        deliver.send_imessage(
            f"⚠️ Category '{category_text}' doesn't exactly match any YNAB category.{hint}\n\n"
            f"Retry with the exact name (including emoji if present)."
        )
        sys.exit(1)

    # Load existing rules
    try:
        data = amount_lookup.load_amount_rules(AMOUNT_LOOKUP_PATH)
    except ValueError as e:
        deliver.send_imessage(
            f"⚠️ Amount rule failed: state/amount-lookup.json is malformed: {e}\n"
            "Edit the file directly to fix it, then retry."
        )
        sys.exit(1)

    # Apply rule
    try:
        updated_data, status = amount_lookup.add_amount_rule(data, amount, category_text)
    except ValueError as e:
        error_str = str(e)
        existing_category = error_str.removeprefix("conflict:") if error_str.startswith("conflict:") else error_str
        deliver.send_imessage(
            f"⚠️ Amount rule conflict: ${amount:.2f} is already mapped to '{existing_category}'.\n\n"
            f"To replace it, edit state/amount-lookup.json directly:\n"
            f"  ~/.openclaw/workspace/skills/ynab-categorize/state/amount-lookup.json"
        )
        sys.exit(1)

    if status == "duplicate":
        deliver.send_imessage(
            f"✅ ${amount:.2f} → {category_text} already in rules, no change."
        )
        sys.exit(0)

    # Save
    try:
        amount_lookup.save_amount_rules(updated_data, AMOUNT_LOOKUP_PATH)
    except Exception as e:
        deliver.send_imessage(f"⚠️ Amount rule failed: couldn't save state file: {e}")
        sys.exit(1)

    # Confirm
    rule_count = len(updated_data.get("rules", []))
    deliver.send_imessage(
        f"✅ Amount rule added:\n"
        f"  ${amount:.2f} → {category_text}\n\n"
        f"Active next cron run. Total rules: {rule_count}."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
