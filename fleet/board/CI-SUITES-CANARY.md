repo: charon-private
tier: strong
difficulty: 2
work_class: ci-infra
priority: 1
branch: feat/ci-suites-canary
depends_on: MERGE-DROP-RATCHET
owns: fleet/tests/ci-suites-canary.test.sh
substrate: N/A
substrate-novel: |
  The rule is "a suite may run non-blocking for a bounded window, then MUST be promoted or
  removed" — a staleness ratchet over OUR OWN CI allowlist, which is a literal bash array in
  `fleet/checks/rig-ci-scope.sh`. GitHub's native equivalents do not fit: `continue-on-error`
  marks a step non-blocking with NO expiry (the exact decay this design exists to prevent), and
  required-checks configuration is repo settings, not reviewable code. `nektos/act` is a
  RELATED but different adopt — it runs workflow FILES locally; it does not stage individual
  suites. Recommend `act` separately if the lane finds it useful; it does not cover this rule.
serial_justified: |
  The canary list and its expiry ratchet are inseparable — a canary list without an expiry IS the
  advisory-gate anti-pattern, so shipping the list alone would be a net negative.
execution: |
  Off-Claude via fleet-droid.sh, own worktree.
source: |
  Operator, 2026-08-01: "can we stage a 'testing CI' that clones our CI so we can test there
  instead of potentially killing our CI until we fix it?" — then "the CI_SUITES_CANARY approach
  approved".
note: |
  ## THE PROBLEM (measured today)
  `gate-integrity.sh` found **6 suites that have NEVER executed in CI** because `fleet/tests/` is
  an ALLOWLIST and they are absent from `CI_SUITES` in `fleet/checks/rig-ci-scope.sh`:
    `land-gate.test.sh` · `handoff-mechanize.test.sh` · `rule-sync.test.sh` ·
    `selfcheck-cycle.test.sh` · `claim-loop-guard.test.sh` · `test_droid_reap.sh`
  `land-gate.test.sh` defends our most critical path and has never run. But adding six
  never-executed suites straight into a REQUIRED check risks reddening CI for everyone at once —
  which is precisely the operator's concern.

  ## THE DESIGN (operator-approved — do NOT redesign, implement it)
  A second list, `CI_SUITES_CANARY`, beside the existing `CI_SUITES` in the SAME file:
    - canary suites RUN on every PR, on the runners we already have, **non-blocking**;
    - promotion = move ONE LINE from `CI_SUITES_CANARY` to `CI_SUITES`;
    - **STALENESS RATCHET (the load-bearing part): an entry that sits in canary beyond its window
      goes RED.** Each entry carries an added-date + owner. Past the window: promote it, fix it, or
      delete the suite — but it CANNOT sit there forever.
  Without the ratchet this is just `continue-on-error` with extra steps, i.e. the advisory-gate
  pattern that decays — the same failure mode as a grandfathered baseline [[best-not-defensible]].

  Default window: 14 days. Make it a single named constant, not a literal sprinkled through the code.

  ## EXPLICITLY OUT OF SCOPE
  - Do NOT stand up a second repo, a second runner, or a mirrored workflow. We have 3 self-hosted
    runners on 4-LOM already; this rides them.
  - Do NOT promote the 6 suites as part of this ticket. Land the MECHANISM; seed the canary list
    with them and let the window do its job. Whatever they surface becomes its own ticket.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline. Each RED on the named revert, then GREEN:
    a. a canary suite that FAILS does NOT fail the overall CI run (non-blocking works);
    b. a canary suite that fails is still REPORTED loudly and visibly — silent non-blocking is the
       anti-pattern, so a failure nobody can see is a RED for this ticket;
    c. a canary entry older than the window makes the check go RED, naming the suite and its age.
       Revert the ratchet and this test goes RED (proves the expiry FIRES, not merely that it exists);
    d. a promoted suite (moved to `CI_SUITES`) DOES block on failure;
    e. ANTI-OVER-BLOCK: an empty canary list is GREEN and changes nothing about today's behaviour.
  Then seed the list with the 6 suites above and show the run output.

## Dependencies & Sequence
  - Depends on MERGE-DROP-RATCHET: both edit `fleet/checks/rig-ci-scope.sh`. MERGE-DROP-RATCHET is
    already merged (PR #291), so this is sequencing, not a block.
  - Feeds: FIXTURE-BYPASS-GATE's baseline-to-zero work — the canary is how those 6 suites get
    promoted safely instead of being grandfathered.
