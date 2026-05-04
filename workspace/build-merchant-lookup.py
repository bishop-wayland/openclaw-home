#!/usr/bin/env python3
"""Build merchant→category lookup from YNAB history."""
import os, sys, json, subprocess, urllib.request
from collections import defaultdict

BUDGET_ID = "2f6bc004-22ff-4e29-be77-a8907cb1c537"
BASE_URL = "https://api.ynab.com/v1"

def get_token():
    env_path = "/Users/bishop/.openclaw/.env"
    with open(env_path) as f:
        for line in f:
            if "OP_SERVICE_ACCOUNT_TOKEN" in line:
                os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    result = subprocess.run(
        ["/opt/homebrew/Caskroom/1password-cli/2.33.1/op", "read", "op://Bishop/YnabApiKey/credential"],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def ynab_get(path, token):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def main():
    token = get_token()
    
    # Fetch all transactions
    data = ynab_get(f"/budgets/{BUDGET_ID}/transactions", token)
    txns = data["data"]["transactions"]
    
    # Build lookup: payee → most recent category
    lookup = {}
    payee_history = defaultdict(list)
    
    for t in txns:
        payee = t.get("payee_name")
        cat_id = t.get("category_id")
        cat_name = t.get("category_name")
        date = t.get("date")
        
        if payee and cat_id and cat_name and cat_name != "Uncategorized":
            payee_history[payee].append((date, cat_name))
    
    # For each payee, use the most recent categorization
    for payee, history in payee_history.items():
        history.sort(reverse=True)  # Most recent first
        lookup[payee] = history[0][1]
    
    # Save lookup
    with open("/Users/bishop/.openclaw/workspace/merchant-lookup.json", "w") as f:
        json.dump(lookup, f, indent=2, sort_keys=True)
    
    print(f"Built lookup table: {len(lookup)} unique merchants")
    print(f"Saved to merchant-lookup.json")
    
    # Show sample
    sample = sorted(lookup.items())[:20]
    print(f"\nSample entries:")
    for payee, cat in sample:
        print(f"  {payee:<40} → {cat}")

if __name__ == "__main__":
    main()
