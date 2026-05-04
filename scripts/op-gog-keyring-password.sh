#!/bin/bash
# Fetch the gog keyring password from 1Password and emit the openclaw secrets-exec envelope.
# Mirrors op-anthropic-key.sh shape so deliver.py can parse it the same way.
export OP_SERVICE_ACCOUNT_TOKEN=$(grep OP_SERVICE_ACCOUNT_TOKEN /Users/bishop/.openclaw/.env | cut -d'"' -f2 | tr -d '[:space:]')
VALUE=$(/opt/homebrew/Caskroom/1password-cli/2.33.1/op read "op://Bishop/GogKeyringPassword/credential")
printf '{"protocolVersion": 1, "values": {"value": "%s"}}' "$VALUE"
