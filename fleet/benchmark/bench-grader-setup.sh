#!/usr/bin/env bash
# bench-grader-setup.sh — ONE idempotent command to provision the MODEL-PREFLIGHT
# out-of-band grader substrate. Run as root:  sudo bench-grader-setup.sh
#
# Ends the recurring per-session substrate scramble (this session hit THREE gaps in a
# row: ACL traverse, session-dir perms, missing pytest). Provisions everything the
# isolated `bench-grader` user needs so preflight can run + grade:
#   1. test deps (pytest, hypothesis) in the interpreter bench-grader's python3 resolves to
#   2. filesystem reachability (ACLs) — bench-grader can read fleet source + write the scorecard
#   3. the load-bearing graders deployed to /home/bench-grader/keys/preflight (0700)
#   4. the grader-daemon running (watching the spool)
# Idempotent + fail-loud: safe to re-run; verifies each step and exits non-zero on any gap.
#
# FLEET path: from $CHARON_FLEET, else relative to this script's repo location. The installed
# (root-owned) copy MUST be given CHARON_FLEET (it lives outside the repo) — it fails loud if
# it can't find the benchmark tree rather than silently using a wrong path.
#
# SECURITY (scoped-NOPASSWD): for the sudoers rule `stack ALL=(ALL) NOPASSWD: <this>` to
# actually limit blast radius, install a ROOT-OWNED, stack-UNWRITABLE copy (e.g. in
# /usr/local/sbin) and NOPASSWD *that* path. A stack-writable script under /home/stack is
# equivalent to NOPASSWD ALL (stack could rewrite what runs as root).
set -uo pipefail

BG_USER="bench-grader"
KEYS="/home/bench-grader/keys"
# FLEET resolution: explicit env > repo-relative (when run from the repo) > known host default.
# The host default is intentional for THIS provisioning script (it targets this box's
# bench-grader) and is override-able via CHARON_FLEET; the guard below fails loud if wrong.
# (Documented allowlist case for the REACHABILITY-GATE no-unreachable-paths check.)
FLEET="${CHARON_FLEET:-}"
if [ -z "$FLEET" ]; then
  _rel="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
  if [ -f "$_rel/benchmark/grader-daemon.py" ]; then FLEET="$_rel"; else FLEET="/home/stack/charon-private/fleet"; fi
fi
BENCH="$FLEET/benchmark"

fail(){ echo "bench-grader-setup: FAIL — $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || { echo "must run as root: sudo $0" >&2; exit 2; }
id "$BG_USER" >/dev/null 2>&1 || fail "no such user: $BG_USER"
[ -f "$BENCH/grader-daemon.py" ] || fail "benchmark tree not found at $BENCH — set CHARON_FLEET=/path/to/fleet"

echo "== 1/5 test deps (pytest, hypothesis) for $BG_USER =="
if ! sudo -u "$BG_USER" python3 -c "import pytest, hypothesis" 2>/dev/null; then
  apt-get update -qq && apt-get install -y python3-pytest python3-hypothesis
fi
sudo -u "$BG_USER" python3 -c "import pytest, hypothesis" \
  || fail "$BG_USER still cannot import pytest/hypothesis — check its interpreter: sudo -u $BG_USER python3 -c 'import sys;print(sys.executable)'"
echo "   ok"

echo "== 2/5 filesystem reachability (ACLs, key-isolation preserved) =="
command -v setfacl >/dev/null || { apt-get update -qq && apt-get install -y acl; }
setfacl -m "u:$BG_USER:x"   /home/stack                 || fail "setfacl traverse /home/stack"
setfacl -m "u:$BG_USER:rwx" "$FLEET"                     || fail "setfacl rwx $FLEET"
sudo -u "$BG_USER" test -r "$BENCH/grader-daemon.py"     || fail "$BG_USER cannot READ $BENCH/grader-daemon.py"
sudo -u "$BG_USER" test -w "$FLEET"                      || fail "$BG_USER cannot WRITE $FLEET (scorecard artifacts)"
echo "   ok (keys stay 0700 $BG_USER — models run as stack and still cannot read them)"

echo "== 3/5 deploy load-bearing graders =="
sudo -u "$BG_USER" KEYS="$KEYS" "$BENCH/deploy-preflight-graders.sh" || fail "grader deploy"
echo "   ok"

echo "== 4/5 grader-daemon running =="
if pgrep -u "$BG_USER" -f grader-daemon.py >/dev/null; then
  echo "   already running (pid $(pgrep -u "$BG_USER" -f grader-daemon.py | tr '\n' ' '))"
else
  sudo -u "$BG_USER" bash -c "setsid nohup python3 '$BENCH/grader-daemon.py' >/tmp/grader-daemon.log 2>&1 </dev/null &"
  for _ in 1 2 3 4 5 6; do pgrep -u "$BG_USER" -f grader-daemon.py >/dev/null && break; sleep 0.5; done
  pgrep -u "$BG_USER" -f grader-daemon.py >/dev/null || fail "daemon did not start — see /tmp/grader-daemon.log"
  echo "   started"
fi

echo "== 5/5 verify =="
tail -n 3 /tmp/grader-daemon.log 2>/dev/null | sed 's/^/   log: /'
echo "OK: bench-grader preflight substrate provisioned (idempotent — safe to re-run)."
