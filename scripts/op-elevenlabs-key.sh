#!/bin/bash
# Fetch the ElevenLabs API key from 1Password and emit the openclaw secrets-exec envelope.
export OP_SERVICE_ACCOUNT_TOKEN=$(grep OP_SERVICE_ACCOUNT_TOKEN /Users/bishop/.openclaw/.env | cut -d'"' -f2 | tr -d '[:space:]')
VALUE=$(/opt/homebrew/bin/op read "op://Bishop/ElevenLabsApiKey/credential" 2>/tmp/op-elevenlabs-key.err)
if [ -z "$VALUE" ]; then
  ERR=$(cat /tmp/op-elevenlabs-key.err 2>/dev/null | tr -d '\n' | sed 's/"/\\"/g')
  printf '{"protocolVersion": 1, "values": {}, "errors": {"value": {"message": "%s"}}}' "$ERR"
  exit 1
fi
printf '{"protocolVersion": 1, "values": {"value": "%s"}}' "$VALUE"
