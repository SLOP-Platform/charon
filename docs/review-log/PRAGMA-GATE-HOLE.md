# PRAGMA-GATE-HOLE — pragma-evasion hole in the diff-coverage gate

## Charge

A single diff (PR #266, 2026-08-09) added 42 `# pragma: no cover` lines to `src/`,
flipping the `gate` (diff-coverage) required check from RED to green while hiding a
live money-path bug: `cost` was bound to $0.00 at `forwarder.py:491` and never
reassigned, so every request silently booked $0.00. A gate that a PR can silence
by annotating the code it is judging is not a gate. This ticket closes that hole.

## Decision: rule belongs inside `diff_cover_gate.py`, not `gate-weaken-guard`

The two candidate homes differ in what they can safely do. `diff_cover_gate.py`
already parses the added-line set via `tools/diff_scope.py`, already owns the
`gate` context (which is a REQUIRED status check on master), and already runs as a
subprocess of `gate_runner` inside CI — it can read the content of added lines
because it runs against the PR's merge ref with full checkout. `gate-weaken-guard`
is a `pull_request_target` workflow that reads workflow YAML from the BASE branch
and deliberately never checks out, builds, or executes PR content (see its own
security header at `.github/workflows/gate-weaken-guard.yml:14-16`). Reading added
*line content* in a `pull_request_target` job would require executing PR content in
a context that has access to repo secrets — exactly what the guard's own design
rules out. The rule therefore belongs in `diff_cover_gate.py`, where it inherits
the existing required `gate` context and the existing diff scope machinery without
introducing any new trust boundary.

## Implementation

Two-prong rule, applied after computing the added-line set and BEFORE the expensive
coverage analysis (fast-fail):

1. **Justification required.** Any `# pragma: no cover` ADDED in a diff must carry a
   one-line justification comment. An added pragma with no justification is RED.
2. **Money-path pragmas REFUSED outright** — no justification can rescue them. The
   refused set is pragmas on or adjacent to money-path call sites:
   `record_spend`, `note_request`, spend-limiter call sites, balance-tracker
   call sites. Defined by call site, not filename, so moving the code does not
   evade it. Removing an existing pragma is always allowed; only ADDED ones are
   judged.

The rule prints an explicit "no added pragmas in this diff" message when the diff
has none — never a silent skip.

## Red-proof

Four cases, all executed in CI (`tests/test_pragma_gate.py`):

1. RED: added unjustified pragma → FAIL with file+line diagnostic.
2. RED (prong b): added money-path pragma (even justified) → FAIL.
3. GREEN: added justified pragma on genuinely unreachable guard → PASS.
4. GREEN: no pragmas → PASS with explicit "no added pragmas" message.

## Branch protection

The rule sits behind the already-required `gate` context (verified via
`gh api repos/SLOP-Platform/charon/branches/master/protection`:
`["gate","bandit","gitleaks","semgrep","gate-weaken-guard","wheel-smoke"]`).
No new required check was added.
