#!/bin/bash
# Fetch the gog keyring password from 1Password and emit the openclaw secrets-exec envelope.
# Mirrors op-anthropic-key.sh shape so deliver.py can parse it the same way.
export OP_SERVICE_ACCOUNT_TOKEN=$(grep OP_SERVICE_ACCOUNT_TOKEN /Users/bishop/.openclaw/.env | cut -d'"' -f2 | tr -d '[:space:]')
VALUE=$(/opt/homebrew/bin/op read "op://Bishop/GogKeyringPassword/credential" 2>/tmp/op-gog-keyring-password.err)
if [ -z "$VALUE" ]; then
  ERR=$(cat /tmp/op-gog-keyring-password.err 2>/dev/null | tr -d '\n' | sed 's/"/\\"/g')
  printf '{"protocolVersion": 1, "values": {}, "errors": {"value": {"message": "%s"}}}' "$ERR"
  exit 1
fi
printf '{"protocolVersion": 1, "values": {"value": "%s"}}' "$VALUE"
