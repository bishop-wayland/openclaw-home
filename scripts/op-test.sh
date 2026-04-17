#!/bin/bash
TOKEN=$(grep OP_SERVICE_ACCOUNT_TOKEN /Users/bishop/.openclaw/.env | cut -d'"' -f2 | tr -d '[:space:]')
OP_SERVICE_ACCOUNT_TOKEN="$TOKEN" /opt/homebrew/Caskroom/1password-cli/2.33.1/op read "op://Bishop/AnthropicKey/credential" 2>&1 | head -c 20
echo
