#!/bin/bash
VALUE=$(/opt/homebrew/Caskroom/1password-cli/2.33.1/op read "op://Bishop/AnthropicKey/credential")
printf '{"protocolVersion": 1, "values": {"value": "%s"}}' "$VALUE"
