"""Amount-based lookup rules for fixed-dollar recurring transactions."""
from __future__ import annotations

import json
from pathlib import Path


EMPTY_RULES: dict = {"version": 1, "rules": []}


def load_amount_rules(path: Path) -> dict:
    """
    Load amount rules from JSON file.

    Returns {"version": 1, "rules": [...]} on success.
    Returns EMPTY_RULES (no mutation) if the file is missing — empty rules is valid.
    Raises ValueError if the file exists but JSON is malformed or schema is invalid.
    """
    if not path.exists():
        return {"version": 1, "rules": []}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"amount-lookup.json is malformed JSON: {e}") from e

    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError("amount-lookup.json malformed: missing top-level 'rules' key")
    if not isinstance(data["rules"], list):
        raise ValueError("amount-lookup.json malformed: 'rules' must be a list")

    return data


def save_amount_rules(data: dict, path: Path) -> None:
    """Save amount rules dict to JSON file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def match_amount(
    amount_dollars: float,
    rules: list[dict],
    tolerance: float = 0.0,
) -> dict | None:
    """
    Search rules list for an entry matching amount_dollars (within tolerance).

    Returns the first matching rule dict, or None if no match.
    Dollar comparison: abs(amount_dollars - rule["amount"]) <= tolerance.
    """
    for rule in rules:
        rule_amount = rule.get("amount")
        if rule_amount is None:
            continue
        if abs(amount_dollars - float(rule_amount)) <= tolerance:
            return rule
    return None


def add_amount_rule(
    data: dict,
    amount: float,
    category: str,
    note: str = "",
) -> tuple[dict, str]:
    """
    Add a new amount rule to the data dict.

    Returns: (updated_data, status)
      status is one of:
        "added"     — rule appended
        "duplicate" — same amount + same category already present (no-op, idempotent)
        "conflict"  — same amount, DIFFERENT category; raises ValueError

    Raises:
        ValueError("conflict:<existing_category>") if the amount already maps to a
        different category. Caller should surface this to Dave and instruct him to
        edit state/amount-lookup.json directly to replace.
    """
    rules = data.get("rules", [])

    for rule in rules:
        existing_amount = rule.get("amount")
        if existing_amount is None:
            continue
        if abs(float(existing_amount) - amount) == 0.0:
            if rule["category"] == category:
                return data, "duplicate"
            else:
                raise ValueError(f"conflict:{rule['category']}")

    new_rule: dict = {"amount": amount, "category": category}
    if note:
        new_rule["note"] = note

    updated = {**data, "rules": rules + [new_rule]}
    return updated, "added"
