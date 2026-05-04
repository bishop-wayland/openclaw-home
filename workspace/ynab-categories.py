#!/usr/bin/env python3
"""List all YNAB categories grouped by group."""
import os, sys, json, subprocess, urllib.request

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
    data = ynab_get(f"/budgets/{BUDGET_ID}/categories", token)
    for group in data["data"]["category_groups"]:
        if group.get("hidden") or group.get("deleted"):
            continue
        print(f"\n[{group['name']}]")
        for cat in group["categories"]:
            if cat.get("hidden") or cat.get("deleted"):
                continue
            print(f"  - {cat['name']}")

if __name__ == "__main__":
    main()
