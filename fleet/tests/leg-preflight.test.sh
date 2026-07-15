#!/usr/bin/env bash
# leg-preflight.test.sh — FAIL-ON-REVERT tests for LEG-PREFLIGHT-CANARY
# (fleet/benchmark/leg-preflight.sh + fleet/benchmark/preflight-tasks/canary/).
#
# Design of record: fleet/board/LEG-PREFLIGHT-CANARY.md, reference impl
# fleet/state/leg-canary-prototype.py, adversarial review add-ons
# fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md F6 (leg-pinning end-to-end)
# and F14 (sandbox the exec-check).
#
# Fully HERMETIC: every scenario sets LPF_PROBE_CMD to a stub that stands in
# for the gateway (leg-preflight.sh's own doc comment: "Overriding this is
# how the test harness stays fully hermetic (no live network)"). No network
# call is ever made. The REAL canary task set (bal-parens exec-checked via
# the REAL exec_check.py subprocess sandbox, lcm-bound exact-match) is used
# unmodified — only the "call the leg" half is stubbed.
#
# Covers (ticket's FAIL-ON-REVERT clause, LEG-PREFLIGHT-CANARY.md bottom):
#   (a) a stubbed HEALTHY leg (fast, correct canary) ranks HEALTHY and is
#       --gate ELIGIBLE.                                          [CORE]
#   (b) a stubbed leg returning wrong content ranks DEGRADED-serves-wrong
#       and is --gate SKIPped.
#   (c) a stubbed unreachable/timeout leg ranks UNREACHABLE, and the
#       --gate hook SKIPS a model whose ONLY leg is UNREACHABLE.   [CORE —
#       this is the exact case the ticket names: "Revert the gate -> the
#       dead-leg model is sent to the full test -> test fails." If gate_mode
#       is ever reverted to always exit 0 (or split_leg/verdict logic is
#       broken so a dead leg is misread as HEALTHY), this assertion goes RED.]
#   (d) LEG-PINNING END TO END (F6): the SAME base model, probed on TWO
#       different legs (one healthy, one dead) in a single invocation,
#       produces TWO SEPARATE per-leg rows (never blended/averaged) and the
#       stub's invocation log proves the FULL leg-suffixed id was sent
#       VERBATIM to the "gateway" (never stripped to the bare model before
#       the call) — the load-bearing F6 assertion. --gate on that model is
#       ELIGIBLE (>=1 healthy leg), proving a dead sibling leg cannot sink
#       a model that has a healthy leg elsewhere.
#   (e) vendor-namespaced pin ("nvidia/…") splits into leg=nvidia,
#       model=<rest>, same as a -ds/-cb/-together suffix.
#   (f) an UNPINNED bare id (no recognized suffix/namespace) is still
#       probed but leg="unpinned" and a WARNING is logged (F6: "its rank
#       cannot be trusted as per-leg").
#   (g) sg-never-anthropic: an *-anthropic-suffixed id is SKIPPED outright —
#       the stub is never even invoked for it (no row is written).
#   (h) SANDBOX (F14): a leg that emits a genuinely hostile infinite-loop
#       payload for the exec-checked task does NOT hang the run — the REAL
#       exec_check.py subprocess sandbox times it out, that one check scores
#       0, and the leg still ranks DEGRADED (not HEALTHY, not a crash/hang).
#
# Run:  bash fleet/tests/leg-preflight.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$SRC/benchmark/leg-preflight.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: cannot find $SCRIPT" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }
not_has(){ printf '%s' "$1" | grep -q -- "$2" && bad "$3 (unexpectedly contains '$2')" || ok "$3"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

# ── stub "gateway": stands in for LPF_PROBE_CMD ─────────────────────────────
# <stub> <leg-id> <prompt-text> <max-tokens> ; must print raw completion text
# to stdout + exit 0 on success, or exit non-zero to simulate an unreachable/
# timed-out leg (per leg-preflight.sh's own LPF_PROBE_CMD contract).
STUB="$D/stub-probe.sh"
cat > "$STUB" <<'STUBEOF'
#!/usr/bin/env bash
leg="$1"; prompt="$2"
printf '%s\n' "$leg" >> "${TEST_PROBE_LOG:?TEST_PROBE_LOG unset}"
case "$leg" in
  *dead*|*-together) exit 1 ;;   # simulate unreachable/timeout: no output, non-zero exit
esac
if printf '%s' "$prompt" | grep -q "is_bal"; then
  case "$leg" in
    *degraded*) printf 'def is_bal(s):\n    return True\n' ;;                 # wrong on purpose
    *hostile*)  printf 'def is_bal(s):\n    while True:\n        pass\n' ;;   # F14 hostile payload
    *) printf 'def is_bal(s):\n    depth = 0\n    for c in s:\n        if c == "(":\n            depth += 1\n        elif c == ")":\n            depth -= 1\n            if depth < 0:\n                return False\n    return depth == 0\n' ;;
  esac
else
  case "$leg" in
    *degraded*) printf '999' ;;   # wrong on purpose (correct answer is 120)
    *) printf '120' ;;
  esac
fi
exit 0
STUBEOF
chmod +x "$STUB"

export TEST_PROBE_LOG="$D/probe.log"
RANK="$D/LEG-RANK.tsv"

run_lpf() {
  LPF_RANK_FILE="$RANK" LPF_PROBE_CMD="$STUB" LPF_REQ_TIMEOUT_S=10 \
    bash "$SCRIPT" "$@"
}
gate() {
  LPF_RANK_FILE="$RANK" bash "$SCRIPT" --gate "$1"
}
# row_verdict <model> <leg> -> LAST recorded verdict for that (model,leg) pair
row_verdict() { awk -F'\t' -v m="$1" -v l="$2" '$1==m && $2==l {v=$7} END{print v}' "$RANK"; }
row_reachable() { awk -F'\t' -v m="$1" -v l="$2" '$1==m && $2==l {v=$3} END{print v}' "$RANK"; }

# ── (a) HEALTHY leg -> ranks HEALTHY, --gate ELIGIBLE (exit 0) ──────────────
out="$(run_lpf goodmodel-ds 2>&1)"
v="$(row_verdict goodmodel ds)"
[ "$v" = "HEALTHY" ] && ok "(a) stubbed correct/fast leg ranks HEALTHY" \
                     || bad "(a) stubbed correct/fast leg ranks HEALTHY (got '$v')"
[ "$(row_reachable goodmodel ds)" = "true" ] && ok "(a) HEALTHY leg marked reachable" \
                                              || bad "(a) HEALTHY leg marked reachable"
gate goodmodel >/dev/null 2>&1
[ $? -eq 0 ] && ok "(a) --gate ELIGIBLE for a model with a HEALTHY leg" \
             || bad "(a) --gate ELIGIBLE for a model with a HEALTHY leg"

# ── (b) DEGRADED leg (wrong content) -> ranks DEGRADED, --gate SKIP ─────────
run_lpf degradedmodel-ds >/dev/null 2>&1
v="$(row_verdict degradedmodel ds)"
[ "$v" = "DEGRADED-serves-wrong" ] && ok "(b) stubbed wrong-content leg ranks DEGRADED-serves-wrong" \
                                   || bad "(b) stubbed wrong-content leg ranks DEGRADED-serves-wrong (got '$v')"
gate degradedmodel >/dev/null 2>&1
[ $? -eq 1 ] && ok "(b) --gate SKIPs a model whose only leg is DEGRADED" \
             || bad "(b) --gate SKIPs a model whose only leg is DEGRADED"

# ── (c) UNREACHABLE leg -> ranks UNREACHABLE, --gate SKIP [CORE, fail-on-revert] ──
run_lpf deadmodel-ds >/dev/null 2>&1
v="$(row_verdict deadmodel ds)"
[ "$v" = "UNREACHABLE" ] && ok "(c) stubbed unreachable leg ranks UNREACHABLE" \
                         || bad "(c) stubbed unreachable leg ranks UNREACHABLE (got '$v')"
[ "$(row_reachable deadmodel ds)" = "false" ] && ok "(c) UNREACHABLE leg marked NOT reachable" \
                                               || bad "(c) UNREACHABLE leg marked NOT reachable"
gate deadmodel >/dev/null 2>&1
rc=$?
[ "$rc" -eq 1 ] && ok "(c) CORE: --gate SKIPs a model whose ONLY leg is UNREACHABLE (revert the gate -> this goes RED)" \
                || bad "(c) CORE: --gate SKIPs a model whose ONLY leg is UNREACHABLE (got exit $rc — GATE REVERTED, dead-leg model would reach the full battery)"

# ── (d) LEG-PINNING END-TO-END (F6): same model, 2 legs, never blended ──────
: > "$TEST_PROBE_LOG"
run_lpf sharedmodel-ds sharedmodel-together >/dev/null 2>&1   # -ds healthy(default), -together dead
vd="$(row_verdict sharedmodel ds)"
vc="$(row_verdict sharedmodel together)"
[ "$vd" = "HEALTHY" ] && ok "(d) leg-pin: sharedmodel's -ds leg ranks HEALTHY independently" \
                      || bad "(d) leg-pin: sharedmodel's -ds leg ranks HEALTHY independently (got '$vd')"
[ "$vc" = "UNREACHABLE" ] && ok "(d) leg-pin: sharedmodel's -together leg ranks UNREACHABLE independently (not blended with -ds)" \
                          || bad "(d) leg-pin: sharedmodel's -together leg ranks UNREACHABLE independently (got '$vc')"
log="$(cat "$TEST_PROBE_LOG")"
has "$log" "^sharedmodel-ds$" "(d) F6: the FULL leg-suffixed id 'sharedmodel-ds' was sent VERBATIM to the probe (never stripped to bare 'sharedmodel')"
has "$log" "^sharedmodel-together$" "(d) F6: the FULL leg-suffixed id 'sharedmodel-together' was sent VERBATIM to the probe (never stripped)"
gate sharedmodel >/dev/null 2>&1
[ $? -eq 0 ] && ok "(d) --gate ELIGIBLE: a healthy leg elsewhere outweighs a dead sibling leg (per-leg, not averaged)" \
             || bad "(d) --gate ELIGIBLE: a healthy leg elsewhere outweighs a dead sibling leg (per-leg, not averaged)"

# ── (e) vendor-namespaced pin splits into leg=<vendor>, model=<rest> ────────
run_lpf "nvidia/GoodNimModel" >/dev/null 2>&1
v="$(row_verdict GoodNimModel nvidia)"
[ "$v" = "HEALTHY" ] && ok "(e) vendor-namespaced id 'nvidia/GoodNimModel' splits to leg=nvidia, model=GoodNimModel, ranks HEALTHY" \
                     || bad "(e) vendor-namespaced id splits to leg=nvidia, model=GoodNimModel (got verdict '$v')"

# ── (f) unpinned bare id: still probed, leg=unpinned, WARNING logged ───────
out="$(run_lpf bareidmodel 2>&1)"
v="$(row_verdict bareidmodel unpinned)"
[ "$v" = "HEALTHY" ] && ok "(f) unpinned bare id is still probed (leg=unpinned)" \
                     || bad "(f) unpinned bare id is still probed (leg=unpinned) (got '$v')"
has "$out" "WARNING" "(f) unpinned bare id logs a WARNING"
has "$out" "cannot be trusted" "(f) WARNING states the rank cannot be trusted as per-leg (F6)"

# ── (g) sg-never-anthropic: skipped outright, stub never invoked ───────────
: > "$TEST_PROBE_LOG"
out="$(run_lpf claude-3-anthropic-ds 2>&1)"
has "$out" "SKIP" "(g) anthropic-suffixed id is SKIPPED"
not_has "$(cat "$TEST_PROBE_LOG")" "claude" "(g) anthropic-suffixed id NEVER reaches the probe/gateway call"
v="$(row_verdict claude-3-anthropic ds)"
[ -z "$v" ] && ok "(g) no LEG-RANK row is written for an anthropic id" \
            || bad "(g) no LEG-RANK row is written for an anthropic id (found verdict '$v')"

# ── (h) SANDBOX (F14): hostile infinite-loop payload doesn't hang the run ──
t0=$(date +%s)
run_lpf hostilemodel-ds >/dev/null 2>&1
t1=$(date +%s)
v="$(row_verdict hostilemodel ds)"
[ "$v" = "DEGRADED-serves-wrong" ] && ok "(h) F14: hostile infinite-loop payload is sandboxed off and scores DEGRADED (not HEALTHY, not a crash)" \
                                   || bad "(h) F14: hostile infinite-loop payload scores DEGRADED (got '$v')"
elapsed=$((t1 - t0))
[ "$elapsed" -lt 30 ] && ok "(h) F14: sandbox timeout bounds the hostile leg's run (${elapsed}s, did not hang)" \
                       || bad "(h) F14: sandbox timeout bounds the hostile leg's run (took ${elapsed}s — looks unbounded)"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LEG-PREFLIGHT-CANARY TESTS PASS"
