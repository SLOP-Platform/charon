#!/usr/bin/env bash
# deploy-session-end.test.sh — FAIL-ON-REVERT tests for advisory session-end deploy:
# no live ssh, no live gh, no live deploy. Every external call is stubbed through env hooks.
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

fixture(){
  local d; d="$(mktemp -d)"
  cp "$SRC/deploy-session-end.sh" "$SRC/end-session.sh" "$d/"
  printf '# id\topened\tsev\tarea\tdesc\tcheck\tstatus\tclosed_by\n' > "$d/reds.tsv"
  echo "$d"
}

run_deploy_hook(){
  local d="$1" latest="$2" running="$3" ci="$4" deploy_rc="$5"
  cat > "$d/deploy.sh" <<'DEPLOY'
#!/usr/bin/env bash
printf '%s\n' "$1" >> "$DEPLOY_LOG"
exit "$DEPLOY_RC"
DEPLOY
  chmod +x "$d/deploy.sh"
  : > "$d/deploy.log"
  FLEET="$d" \
  SESSION_END_REDS_TSV="$d/reds.tsv" \
  SESSION_END_LATEST_TAG_CMD="printf '%s\\n' '$latest'" \
  SESSION_END_RUNNING_TAG_CMD="printf '%s\\n' 'ghcr.io/slop-platform/charon:$running'" \
  SESSION_END_CI_GREEN_CMD="printf '%s\\n' '$ci'" \
  SESSION_END_DEPLOY_SH="$d/deploy.sh" \
  DEPLOY_LOG="$d/deploy.log" \
  DEPLOY_RC="$deploy_rc" \
  bash -c 'source "$1"; session_end_deploy' _ "$d/deploy-session-end.sh"
}

echo "== t1 no-op when already current =="
d="$(fixture)"
rc=0; out="$(run_deploy_hook "$d" v1.2.3 v1.2.3 "completed success" 0 2>&1)" || rc=$?
check "t1 returns 0" "$rc" "0"
[ ! -s "$d/deploy.log" ] && ok "t1 deploy stub NOT called" || bad "t1 deploy stub NOT called"
case "$out" in *"already on v1.2.3; no deploy"*) ok "t1 logs no-op";; *) bad "t1 logs no-op";; esac
rm -rf "$d"

echo "== t2 deploys when behind + CI green =="
d="$(fixture)"
rc=0; run_deploy_hook "$d" v1.2.4 v1.2.3 "completed success" 0 >/dev/null 2>&1 || rc=$?
check "t2 returns 0" "$rc" "0"
check "t2 deploy called with latest tag" "$(tr -d '\n' < "$d/deploy.log")" "v1.2.4"
rm -rf "$d"

echo "== t3 behind + CI not green registers advisory red, no deploy =="
d="$(fixture)"
rc=0; run_deploy_hook "$d" v1.2.4 v1.2.3 "completed failure" 0 >/dev/null 2>&1 || rc=$?
check "t3 returns 0" "$rc" "0"
[ ! -s "$d/deploy.log" ] && ok "t3 deploy stub NOT called" || bad "t3 deploy stub NOT called"
awk -F'\t' '$1=="deploy-4lom-unverified" && $3=="P1" && $4=="gate" && $7=="open"{found=1} END{exit found?0:1}' "$d/reds.tsv" \
  && ok "t3 advisory red registered" || bad "t3 advisory red registered"
rm -rf "$d"

echo "== t4 deploy failure is advisory + rollback red =="
d="$(fixture)"
rc=0; out="$(run_deploy_hook "$d" v1.2.4 v1.2.3 "completed success" 42 2>&1)" || rc=$?
check "t4 returns 0 despite deploy failure" "$rc" "0"
check "t4 deploy called with latest tag" "$(tr -d '\n' < "$d/deploy.log")" "v1.2.4"
awk -F'\t' '$1=="deploy-4lom-failed" && $3=="P1" && $4=="gate" && $7=="open" && $5 ~ /v1.2.4/ && $5 ~ /auto-rolled-back/{found=1} END{exit found?0:1}' "$d/reds.tsv" \
  && ok "t4 deploy failure red registered with rollback context" || bad "t4 deploy failure red registered with rollback context"
case "$out" in *"WARNING"*) ok "t4 prints loud warning";; *) bad "t4 prints loud warning";; esac
rm -rf "$d"

echo "== t5 end-session Phase 2 closes even when deploy fails =="
d="$(fixture)"
cat > "$d/git-stub.sh" <<'GIT'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GITLOG"
exit 0
GIT
chmod +x "$d/git-stub.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$d/check-pass.sh"; chmod +x "$d/check-pass.sh"
echo "handoff" > "$d/HO.md"
cat > "$d/deploy.sh" <<'DEPLOY'
#!/usr/bin/env bash
printf '%s\n' "$1" >> "$DEPLOY_LOG"
exit 42
DEPLOY
chmod +x "$d/deploy.sh"
: > "$d/git.log"; : > "$d/deploy.log"
rc=0
out="$( SESSION=selftest \
        END_SESSION_GIT="$d/git-stub.sh" \
        GITLOG="$d/git.log" \
        END_SESSION_CHECK_SH="$d/check-pass.sh" \
        END_SESSION_PRIV="$d" \
        END_SESSION_FILE="$d/HO.md" \
        END_SESSION_DEPLOY_HOOK="$d/deploy-session-end.sh" \
        FLEET="$d" \
        SESSION_END_REDS_TSV="$d/reds.tsv" \
        SESSION_END_LATEST_TAG_CMD="printf '%s\\n' 'v1.2.4'" \
        SESSION_END_RUNNING_TAG_CMD="printf '%s\\n' 'ghcr.io/slop-platform/charon:v1.2.3'" \
        SESSION_END_CI_GREEN_CMD="printf '%s\\n' 'completed success'" \
        SESSION_END_DEPLOY_SH="$d/deploy.sh" \
        DEPLOY_LOG="$d/deploy.log" \
        DEPLOY_RC=42 \
        bash "$d/end-session.sh" 2>&1 )" || rc=$?
check "t5 end-session returns 0" "$rc" "0"
case "$out" in *"SESSION CLOSED"*) ok "t5 prints CLOSED despite failed deploy";; *) bad "t5 prints CLOSED despite failed deploy";; esac
grep -q 'commit' "$d/git.log" && ok "t5 handoff commit still happened" || bad "t5 handoff commit still happened"
check "t5 deploy attempted latest tag" "$(tr -d '\n' < "$d/deploy.log")" "v1.2.4"
rm -rf "$d"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL DEPLOY-SESSION-END TESTS PASS"
