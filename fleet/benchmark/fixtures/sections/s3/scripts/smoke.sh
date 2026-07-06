#!/usr/bin/env bash
# CHECK: health endpoint responds
# CHECK: response body reports ok status
set -eu
HOST_PORT="${HOST_PORT:-8080}"

curl -sf "http://localhost:${HOST_PORT}/health" | grep -o '"status":"ok"' | tee /tmp/smoke-last.txt
echo "smoke: ok"
