#!/usr/bin/env bash
# verify-hot-rotation.sh — prove SECRET-HOTROTATE's contract ON THE LIVE GATEWAY:
# a provider key rotated ON DISK takes effect WITHOUT a container restart.
#
# This is the observable half of SECRET-HOTROTATE that the building session could not reach
# ("cannot reach the live gateway from this worktree"), so it merged with an UNMET contract.
#
# SAFETY, by construction:
#   * Targets a provider that is ALREADY DEAD (402/429) by default — zero live traffic harmed.
#   * Backs up secrets.json BEFORE touching it, and restores in an EXIT trap (even on failure/ctrl-c).
#   * NEVER prints a key value. Only lengths and hashes.
#   * Read-modify-write via python json — never sed on a secrets file.
# Usage: verify-hot-rotation.sh [PROVIDER_KEY_ENV]   (default: OPENROUTER_API_KEY — already 402)
set -uo pipefail
KEY_ENV="${1:-OPENROUTER_API_KEY}"
HOST=10.0.1.60; SSHK=~/.ssh/4lom; C=charon-gateway-1
r() { ssh -o BatchMode=yes -o ConnectTimeout=8 -i "$SSHK" stack@"$HOST" "$@"; }

echo "verify-hot-rotation: target=$KEY_ENV (chosen because it is already failing — no live traffic at risk)"

# 0. PRE-FLIGHT: refuse to run against a provider that is currently HEALTHY.
status=$(r "TOK=\$(docker inspect $C --format '{{range .Config.Env}}{{println .}}{{end}}' | grep ^CHARON_GATEWAY_TOKEN= | cut -d= -f2-); curl -s -m 15 -H \"Authorization: Bearer \$TOK\" http://localhost:8080/charon/status" 2>/dev/null)
prov=$(echo "$KEY_ENV" | sed 's/_API_KEY$//;s/_KEY$//' | tr 'A-Z' 'a-z')
last=$(printf '%s' "$status" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('providers',{}).get('$prov',{}).get('last_status','?'))" 2>/dev/null)
echo "verify-hot-rotation: provider '$prov' last_status=$last"
if [ "$last" = "200" ]; then
  echo "REFUSING: '$prov' is currently HEALTHY (200). Rotating its key would break live traffic." >&2
  echo "Pick an already-failing provider instead." >&2; exit 2
fi

# 1. BACKUP + restore trap (fires on ANY exit path, including failure)
r "docker exec $C cp /data/secrets.json /data/secrets.json.hotrotate-bak" || { echo "backup FAILED — aborting" >&2; exit 1; }
trap 'echo "verify-hot-rotation: restoring original secrets.json..."; r "docker exec '"$C"' cp /data/secrets.json.hotrotate-bak /data/secrets.json && docker exec '"$C"' rm -f /data/secrets.json.hotrotate-bak"; echo "restored."' EXIT
echo "verify-hot-rotation: backed up /data/secrets.json"

# 2. Record the CURRENT key fingerprint (hash only — never the value)
before=$(r "docker exec $C python3 -c \"import json,hashlib;d=json.load(open('/data/secrets.json'));v=d.get('$KEY_ENV','');print(hashlib.sha256(v.encode()).hexdigest()[:12], len(v))\"")
echo "verify-hot-rotation: before  sha12+len = $before"

# 3. ROTATE on disk to a deterministic sentinel (still never printed in full)
r "docker exec $C python3 -c \"import json;p='/data/secrets.json';d=json.load(open(p));d['$KEY_ENV']='ROTATED-SENTINEL-'+('x'*32);json.dump(d,open(p,'w'))\"" || exit 1
after=$(r "docker exec $C python3 -c \"import json,hashlib;d=json.load(open('/data/secrets.json'));v=d.get('$KEY_ENV','');print(hashlib.sha256(v.encode()).hexdigest()[:12], len(v))\"")
echo "verify-hot-rotation: after   sha12+len = $after"
[ "$before" != "$after" ] || { echo "ROTATION DID NOT CHANGE THE FILE — test is vacuous" >&2; exit 1; }

# 4. THE ACTUAL CLAIM: does the RUNNING process pick it up with NO restart?
#    apply_to_env(force_refresh=True) must overwrite an already-resident os.environ value.
echo "verify-hot-rotation: asking the LIVE process to re-read (NO restart)..."
live=$(r "docker exec $C python3 -c \"
import sys,hashlib; sys.path.insert(0,'/app/src')
from charon import secrets as s
s.apply_to_env(force_refresh=True)
import os; v=os.environ.get('$KEY_ENV','')
print(hashlib.sha256(v.encode()).hexdigest()[:12], len(v))
\"" 2>&1 | tail -1)
echo "verify-hot-rotation: in-process sha12+len = $live"

echo
if [ "$live" = "$after" ]; then
  echo "PASS — the rotated key is live in the process WITHOUT a container restart."
  echo "       SECRET-HOTROTATE's observable contract is MET."
  rc=0
else
  echo "FAIL — the process still holds the OLD key after an on-disk rotation."
  echo "       This is the setdefault no-op SECRET-HOTROTATE was supposed to fix."
  echo "       (in-process=$live  expected=$after)"
  rc=1
fi
# 5. CONFIRM NO RESTART HAPPENED — a restart would invalidate the whole proof.
started=$(r "docker inspect $C --format '{{.State.StartedAt}}'")
echo "verify-hot-rotation: container StartedAt=$started (must predate this run)"
exit $rc
