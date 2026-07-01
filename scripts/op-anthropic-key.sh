#!/bin/bash
export OP_SERVICE_ACCOUNT_TOKEN=$(grep OP_SERVICE_ACCOUNT_TOKEN /Users/bishop/.openclaw/.env | cut -d'"' -f2 | tr -d '[:space:]')
VALUE=$(/opt/homebrew/bin/op read "op://Bishop/AnthropicKey/credential" 2>/tmp/op-anthropic-key.err)
if [ -z "$VALUE" ]; then
  ERR=$(cat /tmp/op-anthropic-key.err 2>/dev/null | tr -d '\n' | sed 's/"/\\"/g')
  printf '{"protocolVersion": 1, "values": {}, "errors": {"value": {"message": "%s"}}}' "$ERR"
  exit 1
fi
printf '{"protocolVersion": 1, "values": {"value": "%s"}}' "$VALUE"
