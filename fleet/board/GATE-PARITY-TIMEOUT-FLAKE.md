repo: charon-private
tier: economy
priority: 1
difficulty: 2
work_class: ci-infra
branch: fix/gate-parity-timeout-flake
depends_on:
owns: fleet/checks/gate-parity.sh, fleet/tests/gate-parity-timeout.test.sh
serial_justified: |
  One check, one timeout budget, one red-proof. Nothing to split.
substrate: N/A
substrate-novel: |
  No tool to adopt — this is a timeout budget and an error-classification bug in one of our own
  checks. The novel slice is making "could not check" stop presenting as "check failed", which is
  a semantics decision about our own gate output.
source: |
  Operator asked at session close 2026-08-02 whether this was ticketed. It was NOT — the manager
  had seen it as the only board RED and moved past it as "just a timeout", which is precisely the
  dismissal this ticket exists to prevent.
note: |
  ## MEASURED 2026-08-02
    - `fleet/validate_board.sh:599` runs `gate-parity.sh scan` with a **30-second** timeout.
    - `time bash fleet/checks/gate-parity.sh scan` -> **31s, rc=0**, output:
      `gate-parity scan: OK — no live ticket would be refused at launch (parity holds).`
  **The check PASSES. It is one second over budget.** So under any load it trips the timeout and
  `validate_board` emits:
      RED gate-parity-check-failed: could not run gate-parity.sh — ... timed out after 30 seconds
  A PASSING check is therefore reported as a board RED at random.

  ## WHY THIS IS THE CLASS, NOT A NUISANCE
  Two failure modes, both already expensive in this rig:
  1. **"Could not check" is presented as "check failed".** They are different facts and must never
     share an output shape. This is the same confusion as a 302-with-zero-body reading as success,
     and as a rate-limit outage reading as a drained backlog.
  2. **A flaky RED trains people to ignore REDs.** At session close this was the ONLY board RED;
     the manager glanced at it, classified it as noise, and moved on WITHOUT TICKETING IT. That is
     exactly how a real finding gets skipped later. A gate that cries wolf is worse than no gate.
  Note the second-order risk: because it times out, **gate-parity may effectively never complete
  during `validate_board`** — so the parity check it performs is not actually protecting anything
  most of the time. Check whether it has EVER completed in a `validate_board` run.

  ## FIX — decide deliberately, do not just raise the number
  Raising the timeout alone leaves a check one slow day from flaking again. Do BOTH:
  a. **Separate the outcomes.** A timeout/crash is `UNKNOWN`, not `RED`. Print it distinctly and
     give it its own exit code, so "we could not verify parity" can never be read as "parity is
     broken" — nor silently as "parity holds".
  b. **Make it fast, or make it async.** 31s for a scan that emits one line suggests it re-walks
     the whole board per ticket. Profile it. If it is inherently slow, move it OFF the
     `validate_board` hot path onto the cadence (like `stranded-work-cron.sh`) and have
     `validate_board` read its last result plus a freshness stamp — a stale result must be
     UNKNOWN, never GREEN.
  Only after (a) and (b) pick a timeout, and justify it as a multiple of the measured p95.
accept: |
  a. `gate-parity.sh scan` measured runtime recorded before and after. If it stays on the
     `validate_board` path, the budget is >= 3x the measured p95 and the number is justified.
  b. TIMEOUT/CRASH renders as a DISTINCT `UNKNOWN` outcome with its own exit code — never as RED
     and never as GREEN. Red-proof BOTH directions: force a timeout (e.g. `GATE_PARITY_TIMEOUT=1`)
     and assert UNKNOWN, not RED; run normally and assert the real verdict.
  c. ANTI-REGRESSION: a genuine parity VIOLATION still produces a RED. A fix that turns real
     findings into UNKNOWN is worse than the flake.
  d. State whether gate-parity has ever completed inside a `validate_board` run, with evidence.
  e. If moved to the cadence: BOTH legs verified (registered AND heartbeat fresh), and a stale
     result reports UNKNOWN.
  f. Suite registered in the LITERAL `CI_SUITES` allowlist in `fleet/checks/rig-ci-scope.sh` —
     `grep -c gate-parity fleet/checks/rig-ci-scope.sh` is currently **0**, so no gate-parity test
     has ever run in CI.
scope: |
  The gate-parity runtime, its timeout handling and outcome classification, plus its test. Does
  NOT change what parity itself asserts.

## Dependencies & Sequence

- **depends_on: none.**
- Same class as `AUTH-302-SILENT-FAILURE` (could-not-check indistinguishable from a verdict) and
  as the distinct-exit-code requirement on `EVAL-REGISTRY-DERIVE` / `CRON-REGISTRY-VISIBLE`.
  Reuse their 0/1/8 exit-code shape so all four read identically to an operator.
