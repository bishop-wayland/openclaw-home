#!/bin/bash
export OP_SERVICE_ACCOUNT_TOKEN=$(grep OP_SERVICE_ACCOUNT_TOKEN /Users/bishop/.openclaw/.env | cut -d'"' -f2 | tr -d '[:space:]')
VALUE=$(/opt/homebrew/Caskroom/1password-cli/2.33.1/op read "op://Bishop/AnthropicKey/credential")
printf '{"protocolVersion": 1, "values": {"value": "%s"}}' "$VALUE"
