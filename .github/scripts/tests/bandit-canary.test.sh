#!/usr/bin/env bash
# bandit-canary.test.sh — FAIL-ON-REVERT canary for the ADOPTED bandit Python SAST gate.
#
# This is the proof the gate ACTUALLY EXECUTES. A gate whose green is not backed by a firing red
# is a false receipt. This canary asserts, hermetically:
#   (1) CANARY FIRES  — the wrapper flags fixtures/bandit-known-bad.py (>=1 finding, exit 1).
#   (2) FAIL-ON-REVERT— point the SAME wrapper at a neutered config (BANDIT_CONFIG with
#                        skips: [B602,...]) -> findings drop to 0 and the wrapper goes GREEN. This
#                        proves the RED in (1) is produced BY bandit's B602 (subprocess
#                        shell=True) test, not by accident. If neutering did NOT flip it, this
#                        step FAILS — reverting the test breaks the canary, as required.
#                        (Severity CANNOT neuter it: B602 is HIGH, so even BANDIT_SEVERITY=high
#                        still catches it — the gate is severity-robust.)
#   (3) CLEAN PASSES  — a clean snippet yields 0 findings, exit 0.
#   (4) VACUOUS GUARD — a scan that touches ZERO files must NEVER go green: bandit itself exits 0
#                        "no issues" over an empty dir (verified 1.9.4). The wrapper's OWN
#                        files-scanned guard reds on that (exit 2) — VERSION-INDEPENDENT, not
#                        relying on bandit's exit code.
#   (5) FAIL-CLOSED   — --diff against an UNRESOLVABLE base must exit non-zero, never green. A
#                        shallow CI checkout is the classic silent-green cause.
#
# Fully hermetic: neutered config + empty scope live in mktemp dirs; nothing tracked is mutated.
# Run:  bash .github/scripts/tests/bandit-canary.test.sh   (exit 0 = all pass)
set -uo pipefail
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAP="$SCRIPTS/bandit.sh"
FIXTURE="$SCRIPTS/fixtures/bandit-known-bad.py"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

command -v bandit >/dev/null 2>&1 || {
  echo "bandit-canary: bandit is not installed — cannot run the canary. Adopt the SAST first" >&2
  echo "(pip install --user bandit==<pin> / pipx install bandit). REFUSING to fake a green." >&2
  exit 2
}
[ -f "$FIXTURE" ] || { echo "bandit-canary: fixture missing: $FIXTURE" >&2; exit 2; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# A neutered config: skip the B602 (and its low-severity B404 import companion) tests -> the
# fixture's shell=True finding disappears. This is bandit's native --configfile knob (what the
# wrapper exposes via BANDIT_CONFIG).
neutcfg="$tmp/neutered.yaml"
printf "skips: ['B602','B404','B603','B607']\n" > "$neutcfg"

# Count findings via the SAME scanner the wrapper uses, over an arbitrary config + target, at the
# wrapper's default (medium) severity threshold. bandit exits 1 when it finds issues, so capture
# its output FIRST (|| true) and parse separately — otherwise pipefail would let bandit's exit-1
# trip the fallback and corrupt the count.
# -x '/__none__' mirrors the wrapper: it overrides bandit's DEFAULT exclusion list, which contains
# `.git` and also swallows `.github/...` — without it the fixture under .github/scripts/fixtures/
# is silently not scanned and this canary would compare 0 against 0 and "pass" vacuously.
count(){ local tgt="$1"; shift
  local rep; rep="$(bandit -q -f json --severity-level medium -x '/__none__' "$@" -- "$tgt" 2>/dev/null || true)"
  printf '%s' "$rep" | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("results",[])))' 2>/dev/null || echo -1
}

# (1) CANARY FIRES on the known-bad fixture.
n="$(count "$FIXTURE")"
[ "${n:-0}" -ge 1 ] && ok "1 canary FIRES: known-bad yields $n finding(s)" \
                    || bad "1 canary must fire on known-bad (got '${n}')"
rc=0; bash "$WRAP" "$FIXTURE" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 1 ] && ok "1b wrapper exits 1 (blocks merge) on known-bad" \
              || bad "1b wrapper should exit 1 on known-bad (got $rc)"

# (2) FAIL-ON-REVERT: neuter B602 -> findings drop to 0, wrapper goes green.
nn="$(count "$FIXTURE" -c "$neutcfg")"
[ "${nn:-1}" -eq 0 ] && ok "2 FAIL-ON-REVERT: skipping B602 drops $n->0 (the shell=True test is load-bearing)" \
                     || bad "2 neutered config still finds '${nn}' — B602 NOT load-bearing (or skip missed)"
rc=0; BANDIT_CONFIG="$neutcfg" bash "$WRAP" "$FIXTURE" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "2b neutered wrapper goes GREEN on known-bad (confirms the RED came FROM B602)" \
              || bad "2b neutered wrapper should be green (got $rc)"

# (3) CLEAN PASSES: an ordinary snippet with no insecure pattern.
clean="$tmp/clean_ok.py"
printf 'def add(a, b):\n    return a + b\n' > "$clean"
cn="$(count "$clean")"
[ "${cn:-1}" -eq 0 ] && ok "3 CLEAN: clean snippet yields 0 findings" \
                     || bad "3 clean snippet should be 0 (got '${cn}')"
rc=0; bash "$WRAP" "$clean" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "3b wrapper exits 0 on clean" || bad "3b wrapper should exit 0 on clean (got $rc)"

# (4) VACUOUS GUARD (VERSION-INDEPENDENT): a scan that touches ZERO files can never find anything,
#     so its green is a false receipt. bandit ITSELF exits 0 "no issues" over an empty dir — so we
#     assert the WRAPPER's own files-scanned guard reds it (exit 2), NOT bandit's exit code.
emptydir="$tmp/emptyscope"; mkdir -p "$emptydir"
rc=0; out="$(bash "$WRAP" "$emptydir" 2>&1)" || rc=$?
[ "$rc" -ne 0 ] && ok "4 vacuous (zero-file) scope does NOT go green — wrapper fails closed (exit $rc)" \
              || bad "4 vacuous scope went green — zero-work-green not prevented"
printf '%s\n' "$out" | grep -q "scanned ZERO files" \
  && ok "4a wrapper's own files-scanned guard fired (independent of bandit's exit code / version)" \
  || bad "4a wrapper did not report the zero-file guard — vacuous red may be version-fragile, not the wrapper"
printf '%s\n' "$out" | grep -q "OK — no bandit findings" \
  && bad "4b vacuous scope printed the OK line — that is the false receipt this canary forbids" \
  || ok "4b vacuous scope never printed the OK line"

# (5) FAIL-CLOSED on an unresolvable diff base (the shallow-checkout silent-green case).
rc=0; out="$(CHARON_CI_BASE=__no_such_ref__ CHARON_CI_HEAD=HEAD bash "$WRAP" --diff 2>&1)" || rc=$?
[ "$rc" -ne 0 ] && ok "5 unresolvable merge-base fails closed (exit $rc)" \
              || bad "5 unresolvable merge-base went green — shallow-checkout silent green not prevented"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL BANDIT CANARY TESTS PASS"
