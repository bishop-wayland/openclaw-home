#!/usr/bin/env python3
"""Pull April 2026 spending from David's YNAB budget."""
import os, sys, json, subprocess, urllib.request

BUDGET_ID = "2f6bc004-22ff-4e29-be77-a8907cb1c537"
BASE_URL = "https://api.ynab.com/v1"

def get_token():
    # Load service account token from .env
    env_path = "/Users/bishop/.openclaw/.env"
    with open(env_path) as f:
        for line in f:
            if "OP_SERVICE_ACCOUNT_TOKEN" in line:
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = token
                break
    # Fetch YNAB token from 1Password
    result = subprocess.run(
        ["/opt/homebrew/Caskroom/1password-cli/2.33.1/op", "read", "op://Bishop/YnabApiKey/credential"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"1Password error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

def ynab_get(path, token):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def main():
    token = get_token()
    month_str = "2026-04-01"

    try:
        data = ynab_get(f"/budgets/{BUDGET_ID}/months/{month_str}", token)
        month_data = data["data"]["month"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Fall back to most recent month
            months_data = ynab_get(f"/budgets/{BUDGET_ID}/months", token)
            months = sorted([m["month"] for m in months_data["data"]["months"]])
            latest = months[-1]
            print(f"April not available yet; showing {latest[:7]}")
            data = ynab_get(f"/budgets/{BUDGET_ID}/months/{latest}", token)
            month_data = data["data"]["month"]
        else:
            raise

    categories = month_data["categories"]
    spending = []
    for cat in categories:
        activity = cat.get("activity", 0)
        budgeted = cat.get("budgeted", 0)
        balance = cat.get("balance", 0)
        if activity < 0:
            spent = abs(activity) / 1000.0
            bud = budgeted / 1000.0
            bal = balance / 1000.0
            spending.append((cat["name"], cat.get("category_group_name", ""), spent, bud, bal))

    if not spending:
        print("No spending recorded.")
        return

    spending.sort(key=lambda x: x[2], reverse=True)
    total_spent = sum(s[2] for s in spending)
    total_budgeted = sum(s[3] for s in spending)

    print("YNAB - David's Budget - April 2026")
    print("=" * 62)
    print(f"  {'Category':<28} {'Spent':>8}  {'Budgeted':>9}  {'Left':>8}  Group")
    print("-" * 62)
    for name, group, spent, bud, bal in spending:
        print(f"  {name:<28} ${spent:>7.2f}  ${bud:>8.2f}  ${bal:>7.2f}  [{group}]")
    print("=" * 62)
    print(f"  {'TOTAL':<28} ${total_spent:>7.2f}  ${total_budgeted:>8.2f}")

if __name__ == "__main__":
    main()
