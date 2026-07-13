#!/usr/bin/env bash
# test_add_provider.sh — FAIL-ON-REVERT tests for fleet/add-provider.sh
# (ADD-PROVIDER-MECHANIZE). Runs the script ONLY in --dry-run mode: no real ssh,
# no real docker, no traffic to .60 — everything is asserted against the printed
# command sequence.
#
# Covers:
#   (a) dry-run exits 0 and the KEY VALUE never appears anywhere in the emitted
#       output (the whole point of piping the key over stdin instead of --key).
#   (b) the exact remote CLI call sequence is present, IN ORDER: backup ->
#       providers add (key over stdin) -> models import -> model:upstream mapping
#       -> providers test -> docker restart -> /v1/models verify.
#   (c) argument validation (bad base_url scheme, missing key file) fails loud.
#   (d) idempotent: running twice produces the same shape of sequence both times.
#
# Revert the key-safety handling (e.g. swap the stdin pipe for `--key "$(cat
# "$KEYFILE")"` on argv) -> the key VALUE shows up in the printed docker exec
# command line -> test (a) greps it and goes RED.
#
# Run: bash fleet/tests/test_add_provider.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$SRC/add-provider.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

D="$(mktemp -d)"
KEYFILE="$D/test.key"
SECRET="sk-TOTALLY-SECRET-VALUE-9f8e7d6c"
printf '%s' "$SECRET" > "$KEYFILE"

# ---------------------------------------------------------------------------
echo "== t1: dry-run exits 0 and never prints the key value =="
out="$(bash "$SCRIPT" --dry-run myprov https://api.example.com/v1 "$KEYFILE" phi-4:microsoft/phi-4 2>&1)"; rc=$?
check "t1 exit 0" "$rc" "0"
if printf '%s' "$out" | grep -qF "$SECRET"; then
  bad "t1 key value ABSENT from emitted output (H1: key leaked into a printed command)"
else
  ok "t1 key value ABSENT from emitted output"
fi

# ---------------------------------------------------------------------------
echo "== t2: exact remote CLI call sequence present =="
declare -a pats=(
  'docker exec .*charon-gateway-1.* sh -c .cp -f /data/providers\.json .*providers\.json\.bak-'
  "docker exec -i .*charon-gateway-1.* python3 -m charon\\.cli providers add 'myprov' --base-url 'https://api\\.example\\.com/v1'"
  "docker exec .*charon-gateway-1.* python3 -m charon\\.cli models import 'myprov'"
  "docker exec .*charon-gateway-1.* python3 -c .*config\\.add_model.*'phi-4' 'myprov' 'microsoft/phi-4' '50'"
  "docker exec .*charon-gateway-1.* python3 -m charon\\.cli providers test 'myprov'"
  'docker restart .*charon-gateway-1'
  '/v1/models'
)
seq_ok=1
for pat in "${pats[@]}"; do
  if printf '%s' "$out" | grep -qE "$pat"; then
    ok "t2 sequence contains: $pat"
  else
    seq_ok=0
    bad "t2 sequence contains: $pat"
  fi
done
[ "$seq_ok" -eq 1 ] && ok "t2 full sequence matched" || bad "t2 full sequence matched"

echo "== t2b: sequence is IN ORDER =="
line_no(){ printf '%s\n' "$out" | grep -nE "$1" | head -1 | cut -d: -f1; }
l1="$(line_no 'providers\.json\.bak-')"
l2="$(line_no "providers add 'myprov'")"
l3="$(line_no "models import 'myprov'")"
l4="$(line_no "config\\.add_model")"
l5="$(line_no "providers test 'myprov'")"
l6="$(line_no 'docker restart')"
l7="$(line_no '/v1/models')"
if [ -n "$l1" ] && [ -n "$l2" ] && [ -n "$l3" ] && [ -n "$l4" ] && [ -n "$l5" ] && [ -n "$l6" ] && [ -n "$l7" ] \
   && [ "$l1" -lt "$l2" ] && [ "$l2" -lt "$l3" ] && [ "$l3" -lt "$l4" ] && [ "$l4" -lt "$l5" ] \
   && [ "$l5" -lt "$l6" ] && [ "$l6" -lt "$l7" ]; then
  ok "t2b backup < add < import < mapping < test < restart < verify"
else
  bad "t2b backup < add < import < mapping < test < restart < verify (lines: $l1 $l2 $l3 $l4 $l5 $l6 $l7)"
fi

echo "== t2c: the key is piped via stdin, not embedded as --key on the add command =="
if printf '%s' "$out" | grep -qE "stdin: <redacted, [0-9]+ bytes from .*test\\.key>"; then
  ok "t2c stdin-redacted marker present for the providers-add step"
else
  bad "t2c stdin-redacted marker present for the providers-add step"
fi
if printf '%s' "$out" | grep -E "providers add" | grep -q -- '--key'; then
  bad "t2c providers-add command does NOT use --key (would put the key on argv)"
else
  ok "t2c providers-add command does NOT use --key (would put the key on argv)"
fi

# ---------------------------------------------------------------------------
echo "== t3: no model:upstream args -> no mapping step, rest unchanged =="
out3="$(bash "$SCRIPT" --dry-run otherprov https://api.example.com/v1 "$KEYFILE" 2>&1)"; rc3=$?
check "t3 exit 0" "$rc3" "0"
if printf '%s' "$out3" | grep -q "config.add_model"; then
  bad "t3 no mapping step when no model:upstream given"
else
  ok "t3 no mapping step when no model:upstream given"
fi
if printf '%s' "$out3" | grep -qF "$SECRET"; then
  bad "t3 key value still absent with no mappings"
else
  ok "t3 key value still absent with no mappings"
fi

# ---------------------------------------------------------------------------
echo "== t4: argument validation fails loud =="
rc=0; bash "$SCRIPT" --dry-run badprov ftp://not-http/v1 "$KEYFILE" >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "t4a rejects non-http(s) base_url" || bad "t4a rejects non-http(s) base_url"

rc=0; bash "$SCRIPT" --dry-run badprov https://api.example.com/v1 "$D/does-not-exist.key" >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "t4b rejects a missing key file" || bad "t4b rejects a missing key file"

rc=0; bash "$SCRIPT" --dry-run "bad name" https://api.example.com/v1 "$KEYFILE" >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "t4c rejects an invalid provider name" || bad "t4c rejects an invalid provider name"

rc=0; bash "$SCRIPT" --dry-run onlyoneargument >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "t4d rejects too few args" || bad "t4d rejects too few args"

# ---------------------------------------------------------------------------
echo "== t5: idempotent — same dry-run twice yields the same call shape =="
out5a="$(bash "$SCRIPT" --dry-run idem https://api.example.com/v1 "$KEYFILE" m1:up/m1 2>&1 | sed -E 's/[0-9]{8}T[0-9]{6}Z//g')"
out5b="$(bash "$SCRIPT" --dry-run idem https://api.example.com/v1 "$KEYFILE" m1:up/m1 2>&1 | sed -E 's/[0-9]{8}T[0-9]{6}Z//g')"
check "t5 identical shape on re-run" "$out5a" "$out5b"

rm -rf "$D"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL ADD-PROVIDER TESTS PASS"
