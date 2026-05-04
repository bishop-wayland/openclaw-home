#!/usr/bin/env python3
"""Check how far back uncategorized transactions go and total the damage."""
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
    if result.returncode != 0:
        sys.exit(1)
    return result.stdout.strip()

def ynab_get(path, token):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def main():
    token = get_token()
    # Pull all transactions (no since_date = everything)
    data = ynab_get(f"/budgets/{BUDGET_ID}/transactions", token)
    txns = data["data"]["transactions"]

    uncategorized = [t for t in txns if not t.get("category_id")]
    spending = [t for t in uncategorized if t["amount"] < 0]

    by_month = defaultdict(list)
    for t in uncategorized:
        month = t["date"][:7]
        by_month[month].append(t)

    print(f"\nTotal uncategorized transactions: {len(uncategorized)}")
    print(f"Date range: {min(t['date'] for t in uncategorized)} → {max(t['date'] for t in uncategorized)}")
    print(f"\nBy month:")
    print(f"  {'Month':<12} {'Count':>6}  {'Spent':>12}  {'Inbound':>12}")
    print(f"  {'-'*50}")

    total_spent = 0
    total_in = 0
    for month in sorted(by_month.keys()):
        txns_m = by_month[month]
        spent = sum(abs(t["amount"]) for t in txns_m if t["amount"] < 0) / 1000
        inbound = sum(t["amount"] for t in txns_m if t["amount"] > 0) / 1000
        total_spent += spent
        total_in += inbound
        print(f"  {month:<12} {len(txns_m):>6}  ${spent:>11.2f}  ${inbound:>11.2f}")

    print(f"  {'-'*50}")
    print(f"  {'TOTAL':<12} {len(uncategorized):>6}  ${total_spent:>11.2f}  ${total_in:>11.2f}")

if __name__ == "__main__":
    main()
