#!/usr/bin/env bash
# substrate-first-gate.sh — force the PRIOR QUESTION at work-creation time.
#
# ================================ WHY THIS EXISTS ================================
# Standing doctrine [[adopt-substrate-build-only-novel-slice]] (canonical: product
# docs/adr/0017-outcome-graded-gateway.md; doctrine SSOT Charon PR #138): adopt commodity
# substrate, hand-roll ONLY the novel ~30%. A consult-first rule also already existed
# (fleet/state/EVAL-REGISTRY.md: grep it BEFORE researching/adopting/re-deciding).
#
# BOTH EXISTED AND BOTH FAILED (2026-07-19). A session handoff carried the doctrine
# correctly. The manager read it. Then a ticket arrived framed as "Option A (patch) vs
# Option B (redesign)" — BOTH BUILD OPTIONS — and the manager answered in the shape asked,
# dispatching ~900 LOC of bespoke machinery without ever asking "what is the substrate
# answer?". ROOT CAUSE: the doctrine was asserted at SESSION level; nothing fired at
# DECISION level. THIS GATE FIRES AT DECISION TIME: when a board ticket is created/changed.
#
# ============================= v2: THE PARSER WAS REPLACED =======================
# v1 hand-rolled ~285 lines of sed/case/awk frontmatter and markdown-table parsing beneath
# a ~30-line EVAL-REGISTRY cross-check. An adversarial review found NINE working evasions.
# EVERY parser-class evasion lived in the hand-rolled 285 lines; ZERO findings landed
# against the cross-check. So v2 keeps the novel slice and replaces the commodity part
# with a real YAML parser (PyYAML, pinned) — see fleet/checks/substrate_first_gate.py, which is
# where all the rules now live and where each fix is documented against its evasion.
#
# This file is now the WIRING: CLI contract, exit codes, and the reentrancy guard. Both
# call sites (fleet/checks/rig-ci-scope.sh:_check_ticket for CI, fleet/validate_board.sh's
# advisory scan) keep working unchanged.
#
# ================================ CONTEXT OF VALIDITY ============================
# This gate checks that the QUESTION WAS ASKED and answered against a real external
# candidate with a registry row that carries a receipt. It CANNOT judge whether the answer
# is CORRECT — that is an adversarial-review job. `pr-has-ticket` is its only diff-aware
# assertion and closes only the "code with no ticket at all" case; correlating a named tool
# to the dependency actually adopted remains OPEN by design (see substrate_first_gate.py).
#
# Usage:
#   substrate-first-gate.sh check <ticket.md> [ticket.md ...]   HARD verdict, rc 1 on RED
#   substrate-first-gate.sh scan [board-dir]                    ADVISORY, always rc 0
#   substrate-first-gate.sh retrofit [board-dir]                list live tickets that FAIL
#   substrate-first-gate.sh pr-has-ticket                       RED if the PR's code has no ticket
# Env:
#   SUBSTRATE_REGISTRY   override EVAL-REGISTRY.md path (tests point this at a fixture)
#   RIG_CI_BASE/HEAD     PR diff range (set by rig-ci.yml); enables the diff-aware checks
# Exit: 0 = GREEN, 1 = RED, 2 = usage/refusal.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- reentrancy guard [[fleet-selfcheck-forkbomb-class]] ---------------------------------
# v1 exited 0 here. A refusal that exits 0 is not a guard, it is a KILL SWITCH: any wrapper,
# hook, launcher or workflow `env:` block that exported SUBSTRATE_GATE_ACTIVE=1 turned every
# ticket green, and rig-ci-scope.sh inherits its environment from the workflow step. Two
# independent fixes, either of which alone closes it:
#   1. refusal now exits 2 (non-zero), so a caller can never read it as a pass; and
#   2. the guard only honours a marker naming a LIVE ANCESTOR PID that is itself running
#      this gate — an inherited or hand-set value does not match, so it cannot silence
#      anything; it is re-armed instead.
if [ -n "${SUBSTRATE_GATE_ACTIVE:-}" ]; then
  _sga="${SUBSTRATE_GATE_ACTIVE}"
  _nested=1
  case "$_sga" in
    ''|*[!0-9]*) _nested=0 ;;   # not a PID: forged/inherited junk, not our own nesting
    *) if [ -r "/proc/$_sga/cmdline" ]; then
         tr '\0' ' ' < "/proc/$_sga/cmdline" 2>/dev/null | grep -q 'substrate' || _nested=0
       fi ;;
  esac
  if [ "$_nested" = 1 ]; then
    echo "substrate-first-gate: already active (nested invocation refused — reentrancy guard)" >&2
    exit 2
  fi
  echo "substrate-first-gate: ignoring inherited SUBSTRATE_GATE_ACTIVE='$_sga' (not a live nested" >&2
  echo "  invocation of this gate). The guard re-arms; it is NEVER a way to disable this gate." >&2
fi
export SUBSTRATE_GATE_ACTIVE=$$

case "${1:-}" in
  check|scan|retrofit|pr-has-ticket)
    exec python3 "$HERE/substrate_first_gate.py" "$@" ;;
  *)
    echo "usage: substrate-first-gate.sh {check <ticket.md>...|scan [dir]|retrofit [dir]|pr-has-ticket}" >&2
    exit 2 ;;
esac
