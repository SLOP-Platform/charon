#!/usr/bin/env bash
# CHECK: health endpoint responds
# CHECK: response body reports ok status
set -eu
set -o pipefail
HOST_PORT="${HOST_PORT:?HOST_PORT must be provided (ephemeral, not hardcoded)}"

curl -sf "http://localhost:${HOST_PORT}/health" | grep -o '"status":"ok"' | tee /tmp/smoke-last.txt
echo "smoke: ok"
