repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/rig-ci-gate
depends_on:
owns: .github/workflows/rig-ci.yml, fleet/checks/rig-ci-scope.sh, fleet/tests/rig-ci.test.sh
serial_justified: The workflow and rig-ci-scope.sh are ONE gate, not two surfaces. The workflow is
  little more than the invocation shell for the scope script — the entire design question (which
  files, which checks, which suites survive a fresh checkout with an empty fleet/state/) is decided
  IN rig-ci-scope.sh, and the workflow's steps are written directly against its flags and exit
  codes. Two concurrent writers would leave the workflow calling a contract the script does not
  implement, and the fail-on-revert tests exercise the pair as a single unit (test 3 reverts the
  script and asserts the workflow's board step goes RED). Same checker+its-invoker pairing already
  accepted on MARKER-PROOF-MECHANIZE (preflight.sh + checks/marker-proof.sh).
note: |
  THE RIG HAS NO CI. Not "failing CI", not "stale CI" — NONE. VERIFIED 2026-07-19 on
  Nnyan/charon-private, do NOT re-research the existence question (DO re-measure the counts,
  the PR list moves):
    - `.github/` DOES NOT EXIST in the rig repo at all. Zero workflow files. Never had one.
    - `gh pr view <n> --json statusCheckRollup` -> `checks=0` for ALL TEN open PRs cited as
      "uncovered" (#47 #62 #93 #95 #96 #97 #114 #116 #118 #119) AND for the five most recently
      MERGED PRs (#111 #112 #113 #115 #120). So this is not a 10-PR gap — it is EVERY RIG PR
      EVER, open and merged. Every rig change that has ever landed, landed unverified.
    - It is NOT disabled and NOT a runner problem: `actions/permissions` -> `{"enabled":true,
      "allowed_actions":"all"}`. `gh variable list` -> EMPTY, so the `CI_RUNNER` repo variable
      documented in [[charon-ci-runner-pattern]] is UNSET for this repo, and
      `actions/runners` -> `total_count: 0` (no self-hosted runner registered). Per that pattern
      an unset CI_RUNNER falls back to GitHub-hosted, so hosted runners are available the moment
      a workflow exists. NOTHING is blocking this except the absent workflow.
  READ THE GREEN CAREFULLY: these PRs are UNVERIFIED, not passing. A PR page with no checks
  renders as mergeable, which is the same false-receipt class as a proofless done-marker
  [[gates-must-actually-run]] [[document-model-self-report-lies]]. The rig is the machine that
  gates the PRODUCT; an ungated gate-machine is the highest-leverage blind spot on the board.
accept: |
  DO — add ONE workflow (.github/workflows/rig-ci.yml) that runs on pull_request against the rig
  and gates it. Minimum content, all three:
    (1) `bash -n` on every CHANGED `*.sh` file in the PR diff (syntax gate — catches the class of
        break that has been landing unchecked). Changed-files-scoped, not a whole-tree sweep.
    (2) board validation — see the FRESH-CHECKOUT CONSTRAINT below, it is a real design problem
        and the ticket is wrong if it ignores it.
    (3) the TARGETED rig test suites only — see the TEST-SCOPE CONSTRAINT below.
  Default to GitHub-hosted runners (CI_RUNNER is unset for this repo). If the workflow is written
  to honour CI_RUNNER, it MUST fall back to hosted when unset, per [[charon-ci-runner-pattern]] —
  a workflow that pins `runs-on: self-hosted` would queue forever against 0 registered runners
  and produce a THIRD flavour of false green (a check that never completes).

  FRESH-CHECKOUT CONSTRAINT (mandatory, load-bearing — the naive implementation is WRONG).
  `fleet/validate_board.sh` is only board-accurate in the LIVE tree. `fleet/state/` is gitignored,
  so a CI checkout has NO done-markers; every already-done ticket reads as LIVE and the validator
  emits false REDs. Running it unmodified in CI produces a gate that is RED on a clean PR — which
  gets disabled or bypassed, i.e. a gate that stops actually running [[gates-must-actually-run]].
  REQUIRED SHAPE: scope CI's board check to the ticket files CHANGED IN THE PR and to the
  marker-INDEPENDENT checks only (field presence, `work_class` enum validity, `repo:` present,
  D&S present, owns-format). Marker-dependent checks (live-vs-done status, retirement, dependency
  satisfaction) are EXPLICITLY OUT OF SCOPE for CI and must be documented as such in the workflow
  itself, so a later session does not "fix" CI by re-enabling them.
  DO NOT EDIT fleet/validate_board.sh. It is CONTENDED by four live tickets — REPO-MAP-CONVERGE,
  REPO-FIELD-REQUIRED, CREATION-GATE-DECOMPOSE-WIRE, PROJECT-MEMBERSHIP-GATE all own it. Put the
  diff-scoping in the NEW `fleet/checks/rig-ci-scope.sh` (owned here) and have the workflow call
  that. This is why this ticket owns a new check script instead of the validator.

  TEST-SCOPE CONSTRAINT (mandatory). `fleet/tests/` contains BENCHMARK GRADER tests that invoke
  real models over the network and can block for HOURS. CI MUST run a bounded, explicitly named
  subset — never the full sweep. Name the included suites literally in the workflow (an allowlist,
  not an exclude-list: a new grader test added later must be excluded BY DEFAULT). Give every job
  a `timeout-minutes`. Also apply the rig's own reentrancy rule — CI must not invoke a gate that
  re-invokes CI [[fleet-selfcheck-forkbomb-class]].

  FAIL-ON-REVERT (fleet/tests/rig-ci.test.sh — required, all three):
  (1) BROKEN SHELL FAILS: a fixture PR/branch carrying a deliberately syntax-broken `*.sh`
      (e.g. an unclosed `if`) -> the workflow's shell-syntax step exits NON-ZERO and the PR shows
      a FAILING check. Assert on the step's rc, not on the PR page.
  (2) CLEAN PASSES (anti-over-block): an unmodified branch off master -> ALL steps green, rc=0.
      A gate that reds on a clean tree is worse than no gate; it will be turned off.
  (3) FALSE-RED GUARD: run the board step against a checkout with an EMPTY `fleet/state/` —
      it must NOT red on tickets that are done-but-unmarked. Revert the diff-scoping in
      rig-ci-scope.sh -> this test goes RED. This is the test that proves the fresh-checkout
      constraint was actually solved and not hand-waved.
  Reverting `.github/workflows/rig-ci.yml` must make (1) unable to fail -> test (1) RED.

  TIME BUDGET (stated, and asserted): the full rig-ci run completes in <= 10 MINUTES wall-clock on
  a hosted runner. Record the observed duration of a real run in the review-log. If it exceeds the
  budget, cut suite scope — do NOT raise the budget silently [[latency-is-a-failure-class]].

  GREEN-IS-NOT-PROOF: `checks=0` is the current state and it LOOKS like nothing is wrong. Do not
  accept this ticket on "the workflow file exists" or "the run was green" — acceptance REQUIRES
  observing a deliberately-broken PR go RED (test 1). A gate never seen to fail is not a gate.
scope: |
  Rig-only, no product change [[product-vs-build-rig-boundary]]. Stand up the first-ever CI gate on
  Nnyan/charon-private so rig PRs are VERIFIED rather than merely unchecked. Product CI already
  runs via `.github/workflows/ci.yml` in SLOP-Platform/charon; this brings the rig to parity at a
  deliberately minimal scope (shell syntax + diff-scoped board validation + a bounded test subset).
  [[gates-must-actually-run]] [[security-is-a-ratchet-gate]] [[never-ignore-preexisting-issues]]
ds: |
  ## Dependencies & sequence
  depends_on: NONE. `.github/` does not exist in the rig, so there is no file to contend for and
  no predecessor to wait on — this is a greenfield path in this repo. Confirmed no live ticket
  owns `.github/**` or any workflow file in the rig (`grep "owns:.*github\|owns:.*workflow"` over
  fleet/board/*.md returns only GITHUB-LIMITS-HARDENING, which owns fleet/gh-cache.sh + fleet/
  done.sh — the gh API seam, NOT workflows; no overlap). Branch `feat/rig-ci-gate` is unused on
  origin (verified via git ls-remote).
  ANTI-DEP / explicitly NOT owned: fleet/validate_board.sh. Four live tickets own it
  (REPO-MAP-CONVERGE, REPO-FIELD-REQUIRED, CREATION-GATE-DECOMPOSE-WIRE, PROJECT-MEMBERSHIP-GATE).
  This ticket must NOT become a fifth writer — that is why the diff-scoping lives in the new
  fleet/checks/rig-ci-scope.sh. If validate_board.sh genuinely needs a fresh-checkout flag, that
  is a SEPARATE ticket sequenced behind those four, not a silent edit here.
  ORDER-INDEPENDENT but HIGH-LEVERAGE-FIRST: this gate should land EARLY relative to the other
  open rig PRs. Every rig PR that merges before it merges unverified, so its value decays with
  every landing. It does not block those PRs (no shared owns) — but landing it first means the
  remaining ones get checked.
  SEQUENCING NOTE: once this lands, the 10 currently-uncovered PRs get checks only after a rebase
  or a push onto each branch. Expect to re-run them; that re-run is the first real measurement of
  how much unverified rig code is actually broken. Budget for reds — and per
  [[gate-hardening-strands-open-branches]] a newly-tightened gate strands pre-existing open
  branches, so plan to rebuild net-diffs onto master rather than merging base in.
  wave: rig integrity, 2026-07-19. Frontier may claim down.
  repo: charon-private (rig).
