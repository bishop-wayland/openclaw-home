"""Merchant lookup table operations."""
from __future__ import annotations

import json
from pathlib import Path


def load_lookup(path: Path) -> dict[str, str]:
    """Load merchant -> category mapping from JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Lookup file not found: {path}. Run init-lookup.py to create it.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_lookup(lookup: dict[str, str], path: Path) -> None:
    """Save merchant -> category mapping to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lookup, f, ensure_ascii=False, indent=2)


def lookup_hit(payee: str, lookup: dict[str, str], 
               min_partial_key_length: int = 5) -> tuple[str | None, str, float]:
    """
    Search for payee in lookup table.
    
    Returns: (category, match_type, confidence)
    - match_type: "exact" or "partial" or None
    - confidence: 0.99 for exact, 0.85 for partial, None if no hit
    """
    if not payee:
        return None, None, None
    
    # Exact match
    if payee in lookup:
        return lookup[payee], "exact", 0.99
    
    # Partial match: key (>= min_partial_key_length) is substring of payee (case-insensitive)
    for key in sorted(lookup.keys(), key=len, reverse=True):  # longest matches first
        if len(key) >= min_partial_key_length:
            if key.lower() in payee.lower():
                return lookup[key], "partial", 0.85
    
    return None, None, None


def append_to_lookup(payee: str, category: str, lookup: dict[str, str]) -> None:
    """Add or update a merchant in the lookup table."""
    lookup[payee] = category
