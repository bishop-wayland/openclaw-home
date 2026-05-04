#!/usr/bin/env python3
"""
Initialize/reset merchant lookup table from YNAB history.

Run this if you want to rebuild the lookup table from scratch.
Typically only needed once at install time or if merchant-lookup.json is corrupted.

Usage:
  python3 init-lookup.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Local imports
sys.path.insert(0, str(Path(__file__).parent))
from logger import RunLogger
import merchant_lookup


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
    """Make a GET request to YNAB API."""
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


def main():
    logger = RunLogger()
    
    try:
        logger.emit("init_started")
        
        # Get token
        token = get_ynab_token()
        logger.emit("auth_ok")
        
        # Fetch all transactions (no filter)
        budget_id = "2f6bc004-22ff-4e29-be77-a8907cb1c537"
        resp = ynab_get(f"/budgets/{budget_id}/transactions", token)
        
        if not resp or "data" not in resp:
            logger.emit("error", message="Failed to fetch YNAB transactions")
            sys.exit(1)
        
        transactions = resp["data"]["transactions"]
        logger.emit("fetch_complete", count=len(transactions))
        
        # Build lookup from transactions that have categories
        lookup = {}
        for txn in transactions:
            payee = txn.get("payee_name")
            category = txn.get("category_name")
            
            if payee and category and category != "Uncategorized":
                # Store latest category for each payee
                lookup[payee] = category
        
        logger.emit("lookup_built", entries=len(lookup))
        
        # Save
        lookup_path = Path(__file__).parent.parent / "state" / "merchant-lookup.json"
        merchant_lookup.save_lookup(lookup, lookup_path)
        logger.emit("lookup_saved", path=str(lookup_path), entries=len(lookup))
        
        logger.emit("done", exit_status=0)
        print(f"✓ Lookup initialized with {len(lookup)} merchants")
        
    except Exception as e:
        logger.emit("error", message=str(e))
        sys.exit(1)
    finally:
        logger.close()


if __name__ == "__main__":
    main()
