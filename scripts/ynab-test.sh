#!/bin/bash
export OP_SERVICE_ACCOUNT_TOKEN=$(grep OP_SERVICE_ACCOUNT_TOKEN /Users/bishop/.openclaw/.env | cut -d'"' -f2 | tr -d '[:space:]')
TOKEN=$(/opt/homebrew/Caskroom/1password-cli/2.33.1/op read "op://Bishop/YnabApiKey/credential")
curl -s -H "Authorization: Bearer $TOKEN" "https://api.ynab.com/v1/budgets" | python3 -c "import json,sys; d=json.load(sys.stdin); [print(b['name']) for b in d['data']['budgets']]"
