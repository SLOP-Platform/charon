repo: charon-private
tier: strong
difficulty: 2
work_class: ci-infra
priority: 1
branch: feat/bash-inert-coverage
depends_on: FIXTURE-BYPASS-GATE
real-dep: FIXTURE-BYPASS-GATE lands gate-integrity.sh, whose G1 INERT rule this ticket widens — the file does not exist until then
owns: fleet/tests/bash-inert-coverage.test.sh
substrate: N/A
substrate-novel: |
  REUSE, NOT NEW BUILD. `gate-integrity.sh` (landing via FIXTURE-BYPASS-GATE) ALREADY implements
  bash inertness as its G1 INERT rule — "zero callers outside itself, fleet/tests/ and
  documentation" — and already proved it on the live rig by flagging `fleet/checks/selfcheck-cycle.sh`
  and `fleet/dark-work-check.sh`. No external tool covers dead Bash: the DEADCODE-TOOL-REDERIVE
  matrix tested 5 tools and every one scored NO on the "Bash dead code" row. So the novel slice is
  SCOPE WIDENING of a gate we already own, not a new detector.
serial_justified: |
  One scope change to one existing rule, plus its proof.
source: |
  DEADCODE-TOOL-REDERIVE (merged d90381d): "Bash — fleet shell scripts (60,259 LOC) — covered by
  NONE of the tools; dead-Bash is unaddressed." Operator approved 2026-08-01 as rec #2.
note: |
  ## THE GAP
  **60,259 LOC of fleet Bash has zero dead-code coverage.** Five Python tools were executed
  against four corpora; every one scored NO on Bash. This is not a tooling-choice question — no
  candidate exists.

  It is not academic. **Faktory is the live case**: `fleet/lease-enqueue.sh` self-describes as
  "THE single enqueue chokepoint ... the ONLY sanctioned path that starts work", yet
  `grep -cE 'lease.enqueue|faktory|enqueue' fleet/claim.sh` = **0**. A Faktory server has run on
  4-LOM for 7 days with zero workers. Dead Bash wiring, invisible to every tool we own.

  ## SCOPE — WIDEN G1, DO NOT BUILD A SECOND DETECTOR
  1. `gate-integrity.sh`'s G1 INERT rule currently runs over the gate/check population. Widen its
     scope to the full `fleet/**/*.sh` surface.
  2. Expect a large first-run population across 60k LOC. Do NOT freeze it as a baseline
     [[best-not-defensible]] — classify it:
       - genuinely dead -> delete (deleting dead code is a WIN, not a risk)
       - alive but called only from a doc/README -> that IS the wiring bug; ticket it
       - intentionally standalone (operator-invoked tools) -> needs an explicit reason-bearing
         marker, mirroring the `@inert_by_design` allowlist pattern the product already uses
  3. Report the classified counts. The population IS the deliverable.

  ## KNOWN FALSE-POSITIVE SOURCES (handle explicitly, do not ignore)
  Bash has invocation paths static grep misses: `bash "$VAR"`, `source`/`.`, `exec`, dispatch via
  `case`, cron/systemd units, Windows-Terminal tab launchers under `fleet/state/tabs/`, and
  git hooks. A file reached only through one of these is ALIVE. If the rule cannot see a path,
  say so and mark it UNKNOWN — never silently call it dead. Fail closed: UNKNOWN is never deleted.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline. Each RED on the named revert, then GREEN:
    a. a fixture .sh with zero callers is flagged INERT. Revert the widening -> RED.
    b. a fixture .sh invoked ONLY via `bash "$VAR"` / `source` / a cron line is NOT flagged
       (anti-false-positive — this is the case that makes or breaks the rule).
    c. a file whose only reference is in a README is flagged, with that fact stated.
    d. ANTI-OVER-BLOCK: a normally-called script is untouched.
  Then run against the real rig and report classified counts.

D&S — Deps & Sequence:
  - Depends on FIXTURE-BYPASS-GATE: that lands `gate-integrity.sh`. Do not fork a copy before it.
