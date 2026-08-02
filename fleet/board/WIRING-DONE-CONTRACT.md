repo: charon-private
tier: frontier
priority: 0
difficulty: 5
work_class: ci-infra
branch: feat/wiring-done-contract
depends_on:
owns: fleet/checks/wiring-done-contract.sh, fleet/tests/wiring-done-contract.test.sh, fleet/state/WIRING-DONE-CONTRACT.md, docs/review-log/WIRING-DONE-CONTRACT.md
serial_justified: |
  One gate, one enforcement point, one contract. Splitting the reachability proof from the
  done-marking it gates produces a window in which tickets close under the old rule — which is
  precisely the hole being closed.
substrate: N/A
substrate-novel: |
  Every INPUT is already adopted and stays adopted: graphify's call graph for reachability,
  tools/check_inert_code.py for the product side, fleet/checks/gate-integrity.sh for gate
  liveness, and the existing plane-canary for runtime proof. No new analyser is built and none
  should be. The novel slice is the CONTRACT — binding those existing signals to the done
  transition so a ticket cannot reach DONE while its code is unreachable. No external tool
  encodes your board's definition of done.
accept: |
  OPERATOR DIRECTIVE 2026-08-02: top-3 P0. APPROVED 2026-08-01 and never minted — this ticket
  is itself an instance of the class it closes.
  THE HOLE: fleet/done.sh proves a ticket's PR MERGED. Nothing proves the merged code is
  REACHABLE. So "done" means "landed", not "working", and the built-but-inert backlog is the
  direct consequence — measured today: 9 fleet checks wired NOWHERE, 101 red-proof suites never
  executed, `graphify affected` at 0 call sites, an entire litellm plane merged with ZERO
  production importers, and a claimed-but-absent Faktory guarantee already coded against.
  THE CONTRACT: a ticket cannot reach DONE unless its owned code is proven reachable from a real
  entrypoint. FAIL-CLOSED — unproven is NOT done.
  Build it as a MECHANIZED DONE-CONTRACT, deliberately NOT an auto-wirer: code generation into a
  money path that can be silently wrong is a worse version of this problem (PRIORITY-TODO §D1).
  Done contract:
  1. Wire into fleet/done.sh as a REFUSAL, the same shape as its existing merge proof: no
     reachability evidence, no done marker.
  2. Evidence must be EXECUTED, not read: the check must have been seen to FAIL on a
     deliberately-unwired fixture. Registration is not proof; a green that has never been red
     proves nothing.
  3. Cover both repos — the product side has check_inert_code.py, the rig side does not, and the
     rig is where the 9 inert checks live.
  4. Emit the ticket ids it would have REFUSED had it existed, run against the current done/
     markers. That retrospective list is the acceptance evidence and sizes the existing debt.
  5. Fail-on-revert: removing the contract must let a knowingly-inert fixture ticket reach DONE.

## Dependencies & Sequence

TOP-3 P0, no inbound deps. Ranked immediately behind GRAPHIFY-AFFECTED-WIRE because this gate
CONSUMES the blast-radius query that ticket wires — build them in that order and this one gets
its reachability signal for free rather than hand-rolling a second traversal.
Blocks nothing structurally, but every future ticket's DONE is only worth what this gate makes
it worth, so it precedes all P1 work.
