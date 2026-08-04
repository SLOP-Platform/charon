#!/usr/bin/env bash
# deploy-drift.test.sh — FAIL-ON-REVERT tests for fleet/checks/deploy-drift.sh.
#
# WHY THESE ASSERTIONS EXIST (DEPLOY-MECHANIZE): the drift check reports on the MONEY path — a
# false green here means a billed money leak stays live in production while master carries the
# fix nobody deployed. The rig's recurring defect is not a missing check, it is a check that still
# prints green after its body stopped meaning anything. Each verdict path therefore gets a test
# that goes RED if that path is deleted or gutted, plus assertions that an unreachable / unknown
# input NEVER produces green (the deploy host has no git checkout, so a git-based staleness check
# can never see it — only this check can).
#
# HERMETIC: the REAL script runs against a LOCAL fixture git product repo (built under mktemp -d)
# with every ssh lookup replaced by an env-command override (DEPLOY_DRIFT_RUNNING_CMD /
# DEPLOY_DRIFT_PINNED_CMD). No ssh, no network, nothing leaves the box. The script's own
# env-override seams are the production code paths, not a fixture bypass.
#
# Run:  bash fleet/tests/deploy-drift.test.sh   (exit 0 = all pass)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/../checks/deploy-drift.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ok   $*"; }
no(){ FAIL=$((FAIL+1)); echo "  FAIL $*"; }
chk(){ # chk <desc> <needle> <haystack>
  case "$3" in *"$2"*) ok "$1";; *) no "$1 (missing: $2)";; esac; }
nchk(){ case "$3" in *"$2"*) no "$1 (unexpected: $2)";; *) ok "$1";; esac; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

# ---- fixture product repo: tags v0.6.1, v0.6.2; master carries 3 commits past v0.6.2 ----------
PROD="${TMP}/prod"
git init -q -b master "${PROD}"
git -C "${PROD}" config user.name t; git -C "${PROD}" config user.email t@t
commit(){ # commit <msg> -> sha
  echo "$1" > "${PROD}/msg.txt"
  git -C "${PROD}" add -A && git -C "${PROD}" commit -qm "$1" && git -C "${PROD}" rev-parse --short HEAD
}
commit "chore(release): 0.6.1 base" > /dev/null
git -C "${PROD}" tag v0.6.1
commit "chore(release): 0.6.2 base" > /dev/null
git -C "${PROD}" tag v0.6.2
D012_SHA="$(commit "fix(pools): D-012 stop fully-parked pool from serving a billed 200")"
commit "chore(deps): bump requests" > /dev/null
commit "docs: note deploy drift" > /dev/null
commit "fix: unreleased-but-on-master" > /dev/null
MASTER_AHEAD=$(( $(git -C "${PROD}" rev-list --count v0.6.2..master) ))

# ---- helpers to run the REAL script against fixtures ------------------------------------------
run(){ # run <max_ahead> <running_cmd> <pinned_cmd> [extra_env...]
  local max="$1" rcmd="$2" pcmd="$3"; shift 3
  env \
  DEPLOY_DRIFT_MAX_AHEAD="${max}" \
  CHARON_PRODUCT_REPO="${PROD}" \
  CHARON_PRODUCT_MASTER=master \
  DEPLOY_DRIFT_FETCH=0 \
  DEPLOY_DRIFT_RUNNING_CMD="${rcmd}" \
  DEPLOY_DRIFT_PINNED_CMD="${pcmd}" \
  "$@" bash "${SCRIPT}" --quiet 2>&1
}
RC(){ return "$1"; } # no-op; capture $? inline below

run_expect(){ # run_expect <expect-rc> <max_ahead> <running> <pinned> <desc> [extra_env...]
  local expect="$1" max="$2" running="$3" pinned="$4" desc="$5"; shift 5
  local out rc
  out="$(run "${max}" "printf '%s\\n' 'ghcr.io/slop-platform/charon:${running}'" "printf '%s\\n' 'image: ghcr.io/slop-platform/charon:${pinned}'" "$@")"; rc=$?
  if [[ "${rc}" -eq "${expect}" ]]; then ok "${desc} (rc=${rc})"; else no "${desc} — expected rc=${expect}, got ${rc}"; printf '%s
' "${out}" | sed 's/^/      /'; fi
  printf '%s\n' "${out}"
}

echo "== A. GREEN when everything agrees =="
OUT="$(run_expect 0 5 v0.6.2 v0.6.2 "A1 running==pinned==latest with master within budget -> GREEN(0)")"
chk "A2 reports RUNNING tag" "RUNNING=v0.6.2" "${OUT}"
chk "A3 reports PINNED tag" "PINNED=v0.6.2" "${OUT}"
chk "A4 reports LATEST tag" "LATEST=v0.6.2" "${OUT}"
chk "A5 reports AHEAD count" "AHEAD=${MASTER_AHEAD}" "${OUT}"
chk "A6 prints GREEN verdict" "GREEN" "${OUT}"

echo "== B. RED when running is behind the latest published release =="
OUT="$(run_expect 1 5 v0.6.1 v0.6.1 "B1 running v0.6.1 < latest v0.6.2 -> RED(1)")"
chk "B2 says BEHIND" "BEHIND" "${OUT}"
chk "B3 names both versions" "v0.6.1" "${OUT}"; chk "B3b names latest" "v0.6.2" "${OUT}"

echo "== C. RED when compose pins a DIFFERENT image than running (downgrade hazard) =="
OUT="$(run_expect 1 5 v0.6.2 v0.3.3 "C1 running v0.6.2 but compose pins v0.3.3 -> RED(1)")"
chk "C2 names the compose pin mismatch" "downgrade hazard" "${OUT}"
chk "C3 prints RED" "RED" "${OUT}"

echo "== D. RED when master is ahead of the deployed version by more than MAX_AHEAD =="
OUT="$(run_expect 1 1 v0.6.2 v0.6.2 "D1 master ahead ${MASTER_AHEAD} > max 1 -> RED(1)")"
chk "D2 names the ahead count" "AHEAD=${MASTER_AHEAD}" "${OUT}"
chk "D3 names the budget" "max 1" "${OUT}"
chk "D4 NAMES the undeployed commits (acceptance c)" "D-012" "${OUT}"
chk "D5 names a specific commit sha" "${D012_SHA}" "${OUT}"

echo "== E. GREEN again when the same master is within budget =="
OUT="$(run_expect 0 "${MASTER_AHEAD}" v0.6.2 v0.6.2 "E1 master ahead ${MASTER_AHEAD} within max ${MASTER_AHEAD} -> GREEN(0)")"
chk "E2 GREEN verdict" "GREEN" "${OUT}"

echo "== F. UNKNOWN when an input cannot be read — NEVER green =="
OUT="$(run_expect 2 5 v0.6.2 v0.6.2 "F1 running lookup failure -> UNKNOWN(2)" "DEPLOY_DRIFT_RUNNING_CMD=false")"
nchk "F2 failed lookup is not GREEN" "GREEN" "${OUT}"
nchk "F3 failed lookup is not clean" "VERDICT: GREEN" "${OUT}"
chk "F4 names the failing source" "running lookup FAILED" "${OUT}"

OUT="$(run_expect 2 5 v0.6.2 v0.6.2 "F5 pinned lookup failure -> UNKNOWN(2)" "DEPLOY_DRIFT_PINNED_CMD=false")"
nchk "F6 failed pinned lookup is not GREEN" "GREEN" "${OUT}"

echo "== G. UNKNOWN when running tag is not a comparable / known tag =="
OUT="$(run_expect 2 5 latest v0.6.2 "G1 running 'latest' (no comparable tag) -> UNKNOWN(2)")"
nchk "G2 not GREEN" "GREEN" "${OUT}"
OUT="$(run_expect 2 5 v9.9.9 v9.9.9 "G3 running v9.9.9 (not a known ref) -> UNKNOWN(2)")"
nchk "G4 not GREEN" "GREEN" "${OUT}"

echo "== H. UNKNOWN when compose declares NO charon image =="
OUT="$(run_expect 2 5 v0.6.2 "" "H1 empty pinned lookup -> UNKNOWN(2)")"
nchk "H2 not GREEN" "GREEN" "${OUT}"
OUT="$(run 5 "printf '%s\\n' 'ghcr.io/slop-platform/charon:v0.6.2'" "printf '%s\\n' 'image: ghcr.io/other/app:v1'" )"; rc=$?
if [[ "${rc}" -eq 2 ]]; then ok "H3 unrelated compose image -> UNKNOWN(2)"; else no "H3 unrelated compose image -> expected 2, got ${rc}"; fi

echo "== I. product repo missing -> UNKNOWN =="
OUT="$(DEPLOY_DRIFT_MAX_AHEAD=5 CHARON_PRODUCT_REPO="${TMP}/NOPE" DEPLOY_DRIFT_FETCH=0 \
  DEPLOY_DRIFT_RUNNING_CMD="printf '%s\\n' 'ghcr.io/slop-platform/charon:v0.6.2'" \
  DEPLOY_DRIFT_PINNED_CMD="printf '%s\\n' 'image: ghcr.io/slop-platform/charon:v0.6.2'" \
  bash "${SCRIPT}" --quiet 2>&1)"; rc=$?
if [[ "${rc}" -eq 2 ]]; then ok "I1 missing product repo -> UNKNOWN(2)"; else no "I1 missing product repo -> expected 2, got ${rc}"; fi

echo "--- deploy-drift.test: ${PASS} passed, ${FAIL} failed ---"
[[ "${FAIL}" -eq 0 ]]
