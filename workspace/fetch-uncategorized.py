#!/usr/bin/env python3
"""Fetch uncategorized YNAB transactions for April 2026."""
import os, sys, json, subprocess, urllib.request
from datetime import datetime

BUDGET_ID = "2f6bc004-22ff-4e29-be77-a8907cb1c537"
BASE_URL = "https://api.ynab.com/v1"

def get_token():
    """Load YNAB token from 1Password via service account."""
    env_path = "/Users/bishop/.openclaw/.env"
    with open(env_path) as f:
        for line in f:
            if "OP_SERVICE_ACCOUNT_TOKEN" in line:
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = token
                break
    result = subprocess.run(
        ["/opt/homebrew/Caskroom/1password-cli/2.33.1/op", "read", "op://Bishop/YnabApiKey/credential"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

def ynab_get(path, token):
    """Make YNAB API call."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def main():
    token = get_token()
    
    # Fetch all April transactions
    data = ynab_get(f"/budgets/{BUDGET_ID}/transactions?since_date=2026-04-01", token)
    txns = data["data"]["transactions"]
    
    # Filter for uncategorized
    uncategorized = [t for t in txns if not t.get("category_id") or t["category_id"] is None]
    
    print(f"Found {len(uncategorized)} uncategorized transactions in April 2026\n")
    print("=" * 100)
    print(f"{'Date':<12} {'Payee':<35} {'Amount':>12} {'Account':<20} {'Memo':<20}")
    print("=" * 100)
    
    total = 0
    for t in sorted(uncategorized, key=lambda x: x["date"], reverse=True):
        date_str = t["date"]
        payee = (t.get("payee_name") or "Unknown")[:35]
        amount = t["amount"] / 1000.0
        account = (t.get("account_name") or "")[:20]
        memo = (t.get("memo") or "")[:20]
        
        print(f"{date_str:<12} {payee:<35} ${amount:>11.2f} {account:<20} {memo:<20}")
        total += amount
    
    print("=" * 100)
    print(f"{'TOTAL UNCATEGORIZED':<48} ${total:>11.2f}\n")

if __name__ == "__main__":
    main()
