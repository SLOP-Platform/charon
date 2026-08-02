#!/usr/bin/env bash
# sync-checkouts.test.sh — FAIL-ON-REVERT tests for fleet/sync-checkouts.sh and for the
# `scan` dispatch that now invokes it (fleet/preflight.sh).
#
# WHY THIS FILE EXISTS. sync-checkouts.sh runs on the SESSION-START CRITICAL PATH, and until
# now nothing tested it there: preflight.sh's dispatch guard (`[ "${BASH_SOURCE[0]}" = "${0}" ]`)
# means every other preflight test either SOURCES the file (dispatch never runs) or calls a
# non-`scan` subcommand. The existing green counts would have reported identically if the new
# scan command were `sleep 600`. (D) below fixes exactly that.
#
# Fully hermetic: every fixture is a fresh `mktemp -d` git repo or fleet dir. NEVER touches the
# live checkouts (/home/stack/code/charon, /home/stack/charon-private) — (A) is a branch-flip
# regression test, so running it against a real checkout is the very thing it guards against.
# The one network-ish case (B) dials TEST-NET-1 (192.0.2.0/24, RFC 5737 — guaranteed
# unroutable), which is how the timeout is proven rather than asserted.
#
# Covers:
#   (A) NO SILENT BRANCH FLIP — a checkout on a feature branch STAYS on it across a sync, while
#       master is still fast-forwarded.
#       REVERT LINE: sync-checkouts.sh, the `if [ "$cur" != "master" ]` arm. Replacing it with
#       the old unconditional `git checkout --quiet master` on the success path makes A1 RED.
#       (A2) HEAD on master is restored to master (not left detached). (A3) a detached HEAD
#       stays detached. (A4) the FF actually happened — anti-vacuous: a script that did nothing
#       at all would pass A1 alone.
#   (B) UNREACHABLE REMOTE IS BOUNDED AND REPORTED — never an indefinite block.
#       REVERT LINE: sync-checkouts.sh, `_git_fetch`'s `"$TIMEOUT_BIN" -k 5 "$SYNC_FETCH_TIMEOUT"`
#       prefix. Drop it and B1 hangs past the budget -> RED.
#       (B3) the ssh transport is non-interactive: BatchMode=yes + ConnectTimeout are really
#       passed to ssh, and GIT_TERMINAL_PROMPT=0 is really in git's child environment. Asserted
#       by observing a shim `ssh`'s argv and env, not by grepping the script.
#       (B4) a SIGTERM-IMMUNE transport child cannot hold the fetch past its budget, and the
#       printed receipt must match the measured elapsed.
#       REVERT LINE: sync-checkouts.sh, `_git_fetch`'s `>"${tmp:-/dev/null}"` redirect. Restore
#       the `err="$( ... )"` capture and B4a/B4b go RED at 45s against a 3s budget.
#       (B5) inherited GIT_ASKPASS/SSH_ASKPASS are blanked before git runs.
#   (C) CONCURRENCY LOCK — a second sync against the same repo while the lock is held SKIPS with
#       a reason instead of interleaving checkout/fetch.
#   (D) THE `scan` DISPATCH IS ACTUALLY EXECUTED — `preflight.sh scan` really runs
#       sync-checkouts.sh, FIRST, ahead of reconcile-merged.sh and retire-done.sh, with the rest
#       of the chain intact. (D2) a MISSING sync script warns and does not abort the chain.
#
# Run:  bash fleet/tests/sync-checkouts.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
SYNC="$SRC/sync-checkouts.sh"
# SANDBOX CONTAINMENT + FAIL-CLOSED (2026-08-01) — same class, same `f.txt`/`c1`/`c2` fixture
# shape as session-start-hook.test.sh, which is the one that actually reached origin/master.
# `set -uo pipefail` does not stop a subshell on a failed `cd`, and GIT_AUTHOR_EMAIL=t@t below
# is exported process-wide, so a vanished $ROOT turned these fixtures into commits on the LIVE
# checkout. sandbox_mk keeps the sandbox out of the tree; sandbox_cd aborts instead of falling
# through to $PWD.
# shellcheck source=fleet/tests/lib/sandbox.sh
source "$SRC/tests/lib/sandbox.sh"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

ROOT="$(sandbox_mk sync-checkouts)"
trap "rm -rf $(printf '%q' "$ROOT")" EXIT
LOCKS="$ROOT/locks"; mkdir -p "$LOCKS"

# mkpair -> prints a dir holding origin.git + a clone whose master is 1 commit BEHIND origin.
mkpair(){
  local d; d="$(mktemp -d -p "$ROOT")"
  git init --quiet --bare "$d/origin.git"
  git clone --quiet "$d/origin.git" "$d/seed" 2>/dev/null
  (
    sandbox_cd "$d/seed"
    echo one > f.txt && git add f.txt && git commit --quiet -m c1
    git branch -M master && git push --quiet origin master
  )
  git clone --quiet "$d/origin.git" "$d/co" 2>/dev/null
  ( sandbox_cd "$d/co" && git checkout --quiet -B master origin/master)
  ( sandbox_cd "$d/seed" && echo two >> f.txt && git add f.txt && git commit --quiet -m c2 \
    && git push --quiet origin master )
  printf '%s' "$d"
}

# run_sync <repo> -> stdout+stderr of a sync of ONLY that repo (the other slot is pointed at a
# non-repo path, which the script reports and skips).
run_sync(){
  SYNC_CHECKOUTS_PRODUCT="$1" SYNC_CHECKOUTS_PRIV="$ROOT/no-such-repo" \
  SYNC_CHECKOUTS_LOCK_DIR="$LOCKS" bash "$SYNC" 2>&1
}
head_branch(){ git -C "$1" symbolic-ref --short HEAD 2>/dev/null || echo DETACHED; }

echo "== (A) a feature-branch checkout is NEVER flipped to master =="
d="$(mkpair)"; co="$d/co"
git -C "$co" checkout --quiet -b feat/work
before_origin="$(git -C "$d/seed" rev-parse master)"
out="$(run_sync "$co")"
[ "$(head_branch "$co")" = "feat/work" ] \
  && ok "(A1) HEAD still on feat/work after sync" \
  || bad "(A1) HEAD still on feat/work after sync (got $(head_branch "$co"); out: $out)"
[ "$(git -C "$co" rev-parse master)" = "$before_origin" ] \
  && ok "(A4) master WAS fast-forwarded (the sync did real work, not nothing)" \
  || bad "(A4) master WAS fast-forwarded (out: $out)"
case "$out" in *"FF'd"*) ok "(A5) reports the FF" ;; *) bad "(A5) reports the FF (out: $out)" ;; esac

echo "== (A2) HEAD on master is restored to master, not left detached =="
d="$(mkpair)"; co="$d/co"
out="$(run_sync "$co")"
[ "$(head_branch "$co")" = "master" ] \
  && ok "(A2) HEAD back on master" \
  || bad "(A2) HEAD back on master (got $(head_branch "$co"); out: $out)"
[ "$(git -C "$co" rev-parse HEAD)" = "$(git -C "$d/seed" rev-parse master)" ] \
  && ok "(A2b) and master is current with origin" \
  || bad "(A2b) and master is current with origin (out: $out)"

echo "== (A3) an already-detached HEAD stays detached (no surprise re-attach) =="
d="$(mkpair)"; co="$d/co"
det_sha="$(git -C "$co" rev-parse HEAD)"
git -C "$co" checkout --quiet --detach
out="$(run_sync "$co")"
if [ "$(head_branch "$co")" = "DETACHED" ] && [ "$(git -C "$co" rev-parse HEAD)" = "$det_sha" ]; then
  ok "(A3) HEAD still detached at the same commit"
else
  bad "(A3) HEAD still detached at the same commit (branch=$(head_branch "$co"); out: $out)"
fi

echo "== (B) an unreachable remote is BOUNDED and REPORTED, never an indefinite block =="
# 192.0.2.1 is RFC 5737 TEST-NET-1: routed nowhere, so the TCP connect blackholes (no RST).
# Pre-fix this fetch had no timeout, no lowSpeedLimit and no ConnectTimeout -> it would sit
# until the kernel gave up (~130s) or, for a stalled HTTPS half-open, forever.
d="$(mkpair)"; co="$d/co"
git -C "$co" remote set-url origin "https://192.0.2.1/blackhole.git"
t0=$(date +%s)
out="$(SYNC_CHECKOUTS_FETCH_TIMEOUT=3 SYNC_CHECKOUTS_PRODUCT="$co" \
       SYNC_CHECKOUTS_PRIV="$ROOT/no-such-repo" SYNC_CHECKOUTS_LOCK_DIR="$LOCKS" \
       bash "$SYNC" 2>&1)"
elapsed=$(( $(date +%s) - t0 ))
[ "$elapsed" -le 20 ] \
  && ok "(B1) returned in ${elapsed}s against a blackholed remote (budget 20s)" \
  || bad "(B1) returned in ${elapsed}s against a blackholed remote (budget 20s)"
case "$out" in
  *"TIMED OUT"*|*"FAILED rc="*) ok "(B2) printed the reason instead of failing silently" ;;
  *) bad "(B2) printed the reason instead of failing silently (out: $out)" ;;
esac

echo "== (B3) the ssh transport is non-interactive (observed via a shim ssh) =="
# A shim `ssh` on PATH records the argv and environment git handed it. This proves the real
# invocation carries BatchMode/ConnectTimeout and GIT_TERMINAL_PROMPT=0 — grepping the script
# for those strings would prove only that they were typed.
d="$(mkpair)"; co="$d/co"; shim="$d/bin"; mkdir -p "$shim"
git -C "$co" remote set-url origin "unreachable.invalid:repo.git"
cat > "$shim/ssh" <<'EOS'
#!/usr/bin/env bash
{ echo "ARGV: $*"; echo "TERMPROMPT: ${GIT_TERMINAL_PROMPT-unset}"; } >> "$SSH_SHIM_LOG"
exit 255
EOS
chmod +x "$shim/ssh"
SSH_SHIM_LOG="$d/ssh.log"; : > "$SSH_SHIM_LOG"
SSH_SHIM_LOG="$SSH_SHIM_LOG" PATH="$shim:$PATH" SYNC_CHECKOUTS_FETCH_TIMEOUT=10 \
  SYNC_CHECKOUTS_PRODUCT="$co" SYNC_CHECKOUTS_PRIV="$ROOT/no-such-repo" \
  SYNC_CHECKOUTS_LOCK_DIR="$LOCKS" bash "$SYNC" >/dev/null 2>&1
log="$(cat "$d/ssh.log" 2>/dev/null)"
case "$log" in *"BatchMode=yes"*) ok "(B3a) ssh really invoked with BatchMode=yes" ;;
  *) bad "(B3a) ssh really invoked with BatchMode=yes (log: $log)" ;; esac
case "$log" in *"ConnectTimeout="*) ok "(B3b) ssh really invoked with a ConnectTimeout" ;;
  *) bad "(B3b) ssh really invoked with a ConnectTimeout (log: $log)" ;; esac
case "$log" in *"TERMPROMPT: 0"*) ok "(B3c) GIT_TERMINAL_PROMPT=0 is in git's child environment" ;;
  *) bad "(B3c) GIT_TERMINAL_PROMPT=0 is in git's child environment (log: $log)" ;; esac

echo "== (B4) a SIGTERM-IMMUNE transport child cannot hold the fetch past its budget =="
# R1 regression. `timeout` signals only `git`, not its process group. When _git_fetch captured
# with $( ), bash blocked until every writer to that pipe closed — so a grandchild that ignored
# SIGTERM kept the capture open and the script ran ~46s against a 3s budget while PRINTING
# "TIMED OUT after 3s". This shim ssh reproduces exactly that grandchild. Two assertions:
# the wall clock must respect the budget, AND the printed receipt must not claim a bound it
# did not enforce. Revert the temp-file redirect and this goes RED on both.
d="$(mkpair)"; co="$d/co"; shim="$d/bin"; mkdir -p "$shim"
git -C "$co" remote set-url origin "unreachable.invalid:repo.git"
cat > "$shim/ssh" <<'EOS'
#!/usr/bin/env bash
trap '' TERM INT HUP
sleep 45
exit 255
EOS
chmod +x "$shim/ssh"
t0=$(date +%s)
out="$(PATH="$shim:$PATH" SYNC_CHECKOUTS_FETCH_TIMEOUT=3 SYNC_CHECKOUTS_PRODUCT="$co" \
       SYNC_CHECKOUTS_PRIV="$ROOT/no-such-repo" SYNC_CHECKOUTS_LOCK_DIR="$LOCKS" \
       bash "$SYNC" 2>&1)"
elapsed=$(( $(date +%s) - t0 ))
[ "$elapsed" -le 15 ] \
  && ok "(B4a) returned in ${elapsed}s despite a SIGTERM-immune child (3s budget, 15s ceiling)" \
  || bad "(B4a) returned in ${elapsed}s despite a SIGTERM-immune child (3s budget, 15s ceiling; out: $out)"
# Truthful receipt: if it says it timed out at 3s, it must not have kept running much longer.
case "$out" in
  *"TIMED OUT after 3s"*)
    [ "$elapsed" -le 15 ] \
      && ok "(B4b) the 'TIMED OUT after 3s' receipt matches reality (${elapsed}s)" \
      || bad "(B4b) LIED: printed 'TIMED OUT after 3s' but ran ${elapsed}s" ;;
  *) bad "(B4b) expected a bounded TIMED OUT receipt (out: $out)" ;;
esac
# The reported elapsed is real, not the configured budget echoed back.
case "$out" in
  *"elapsed "*"s;"*) ok "(B4c) the receipt reports MEASURED elapsed, not just the budget" ;;
  *) bad "(B4c) the receipt reports MEASURED elapsed, not just the budget (out: $out)" ;;
esac
# The orphaned shim would otherwise linger 45s past the test.
pkill -KILL -f "$shim/ssh" 2>/dev/null; pkill -KILL -f "sleep 45" 2>/dev/null; true

echo "== (B5) the askpass vectors are neutralized in git's child environment =="
# Defence in depth beside GIT_TERMINAL_PROMPT=0: an inherited askpass helper is a second route
# to an indefinite interactive read. Observed through the transport, not grepped from source.
d="$(mkpair)"; co="$d/co"; shim="$d/bin"; mkdir -p "$shim"
git -C "$co" remote set-url origin "unreachable.invalid:repo.git"
cat > "$shim/ssh" <<'EOS'
#!/usr/bin/env bash
{ echo "GITASKPASS: [${GIT_ASKPASS-unset}]"; echo "SSHASKPASS: [${SSH_ASKPASS-unset}]"; } >> "$SSH_SHIM_LOG"
exit 255
EOS
chmod +x "$shim/ssh"
SSH_SHIM_LOG="$d/ssh2.log"; : > "$SSH_SHIM_LOG"
SSH_SHIM_LOG="$SSH_SHIM_LOG" GIT_ASKPASS="/bin/false-askpass" SSH_ASKPASS="/bin/false-askpass" PATH="$shim:$PATH" \
  SYNC_CHECKOUTS_FETCH_TIMEOUT=10 SYNC_CHECKOUTS_PRODUCT="$co" \
  SYNC_CHECKOUTS_PRIV="$ROOT/no-such-repo" SYNC_CHECKOUTS_LOCK_DIR="$LOCKS" \
  bash "$SYNC" >/dev/null 2>&1
log="$(cat "$d/ssh2.log" 2>/dev/null)"
case "$log" in
  *"GITASKPASS: []"*) ok "(B5a) a hostile inherited GIT_ASKPASS is blanked before git runs" ;;
  *) bad "(B5a) a hostile inherited GIT_ASKPASS is blanked before git runs (log: $log)" ;;
esac
case "$log" in
  *"SSHASKPASS: []"*) ok "(B5b) a hostile inherited SSH_ASKPASS is blanked before git runs" ;;
  *) bad "(B5b) a hostile inherited SSH_ASKPASS is blanked before git runs (log: $log)" ;;
esac
# STRUCTURAL, not behavioural — stated as such. git does NOT propagate GIT_CONFIG_PARAMETERS to
# the ssh transport child, so `-c core.askpass=` cannot be observed the way B5a/B5b are, and
# provoking a real askpass call needs an auth-demanding HTTPS server (out of scope for a
# hermetic offline test). This asserts every fetch invocation still carries the option.
fetch_lines="$(grep -c -- '-c core.askpass= *\\*$' "$SYNC" 2>/dev/null || echo 0)"
[ "${fetch_lines:-0}" -ge 2 ] \
  && ok "(B5c) both fetch invocations carry -c core.askpass= (structural)" \
  || bad "(B5c) both fetch invocations carry -c core.askpass= (structural; found $fetch_lines)"

echo "== (C) a held per-repo lock makes a concurrent sync SKIP, not interleave =="
if command -v flock >/dev/null 2>&1; then
  d="$(mkpair)"; co="$d/co"
  key="$(printf '%s' "$co" | tr -c 'A-Za-z0-9' '-')"
  lf="$LOCKS/sync-checkouts$key.lock"
  : >> "$lf"
  before="$(git -C "$co" rev-parse master)"
  flock "$lf" sleep 6 &
  holder=$!
  sleep 1
  out="$(SYNC_CHECKOUTS_LOCK_WAIT=2 SYNC_CHECKOUTS_PRODUCT="$co" \
         SYNC_CHECKOUTS_PRIV="$ROOT/no-such-repo" SYNC_CHECKOUTS_LOCK_DIR="$LOCKS" \
         bash "$SYNC" 2>&1)"
  case "$out" in *"holds the lock"*) ok "(C1) concurrent sync skipped with a reason" ;;
    *) bad "(C1) concurrent sync skipped with a reason (out: $out)" ;; esac
  [ "$(git -C "$co" rev-parse master)" = "$before" ] \
    && ok "(C2) and the repo was left untouched while the lock was held" \
    || bad "(C2) and the repo was left untouched while the lock was held"
  wait "$holder" 2>/dev/null
else
  echo "SKIP: flock not on PATH"
fi

echo "== (D) preflight.sh 'scan' ACTUALLY EXECUTES the sync, first in the chain =="
# The point of this case: run the REAL dispatch line (not a `source`, not a subcommand), so a
# deleted/renamed/no-op'd sync command goes RED. Siblings are recorder stubs so the chain is
# observed without letting reconcile/retire reach outside the fixture.
mkfleet(){
  local f; f="$(mktemp -d -p "$ROOT")"
  cp "$SRC/preflight.sh" "$SRC/_lib.sh" "$SRC/gh-cache.sh" "$SRC/repo-registry.sh" \
     "$SRC/verify-merged.sh" "$f/" 2>/dev/null
  printf '# reds registry (test fixture)\n' > "$f/reds.tsv"
  mkdir -p "$f/state/cache" "$f/state/done" "$f/board/archive" "$f/bin"
  printf '%s' "$f"
}
mkstub(){ printf '#!/usr/bin/env bash\nprintf "%%s\\n" "%s" >> "$SCAN_ORDER_LOG"\nexit 0\n' "$2" > "$1"; chmod +x "$1"; }

f="$(mkfleet)"
mkstub "$f/sync-checkouts.sh"   sync
mkstub "$f/reconcile-merged.sh" reconcile
mkstub "$f/retire-done.sh"      retire
: > "$f/order.log"
SCAN_ORDER_LOG="$f/order.log" GH_HOLD_FIXTURE="$f/state/empty-hold.tsv" \
  GH_CACHE_DIR="$f/state/cache" PATH="$f/bin:/usr/bin:/bin" \
  timeout 180 bash "$f/preflight.sh" scan > "$f/scan.out" 2>&1
scan_rc=$?
order="$(tr '\n' ' ' < "$f/order.log")"
[ "$scan_rc" -ne 124 ] \
  && ok "(D0) the scan dispatch ran to completion (rc=$scan_rc, not a timeout)" \
  || bad "(D0) the scan dispatch ran to completion (TIMED OUT)"
case "$order" in
  "sync reconcile"*) ok "(D1) sync-checkouts.sh ran, and ran FIRST (order: $order)" ;;
  *sync*)            bad "(D1) sync-checkouts.sh ran but NOT first (order: $order)" ;;
  *)                 bad "(D1) sync-checkouts.sh NEVER RAN under 'scan' (order: $order)" ;;
esac
case "$order" in
  *"reconcile retire"*) ok "(D2) the rest of the chain still runs, in order (order: $order)" ;;
  *) bad "(D2) the rest of the chain still runs, in order (order: $order)" ;;
esac

echo "== (D3) a MISSING sync script warns and does not abort the chain =="
f="$(mkfleet)"
mkstub "$f/reconcile-merged.sh" reconcile
mkstub "$f/retire-done.sh"      retire
: > "$f/order.log"          # note: NO sync-checkouts.sh in this fixture fleet
SCAN_ORDER_LOG="$f/order.log" GH_HOLD_FIXTURE="$f/state/empty-hold.tsv" \
  GH_CACHE_DIR="$f/state/cache" PATH="$f/bin:/usr/bin:/bin" \
  timeout 180 bash "$f/preflight.sh" scan > "$f/scan.out" 2>&1
order="$(tr '\n' ' ' < "$f/order.log")"
if grep -q 'sync script not found' "$f/scan.out" && case "$order" in *"reconcile retire"*) true;; *) false;; esac; then
  ok "(D3) missing sync script -> clear warning, chain continues"
else
  bad "(D3) missing sync script -> clear warning, chain continues (order: $order)"
fi

echo; echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] && echo "ALL SYNC-CHECKOUTS TESTS PASS" || exit 1
