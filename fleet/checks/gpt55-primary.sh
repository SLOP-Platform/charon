#!/usr/bin/env bash
# Green (exit 0) ONLY when the live 4-LOM gpt-5.5 pool actually serves via nanogpt.
# Makes a real (tiny, 16-token) gpt-5.5 request through the gateway and asserts the
# X-Charon-Provider response header is nanogpt. Non-zero if any other provider serves
# (e.g. while nanogpt is in a rate-limit cooldown) or the call fails.
ssh -i ~/.ssh/4lom stack@10.0.1.60 'T=$(docker exec charon-gateway-1 printenv CHARON_GATEWAY_TOKEN); curl -s -D - -o /dev/null -X POST "http://127.0.0.1:8080/v1/chat/completions?token=$T" -H "Content-Type: application/json" -d "{\"model\":\"gpt-5.5\",\"messages\":[{\"role\":\"user\",\"content\":\"ok\"}],\"max_tokens\":16}"' | grep -qi '^x-charon-provider: nanogpt'
