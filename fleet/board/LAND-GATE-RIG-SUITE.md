repo: charon-private
tier: strong
difficulty: 2
priority: 1
work_class: bugfix
branch: fix/land-gate-rig-suite
owns: fleet/tests/land-rig-suite-gate.test.sh
depends_on:
dep-kind:
source: OPERATOR DECISION 2026-07-24 (#6) — "fix the merge gate". Session agen-kolar.
priority_justification: P:1 — the rig's merge gate ran a BOARD-STRUCTURE check and no tests at all,
  so every rig merge to date was ungated. It sits at P:1 rather than P:0 because the shipped state
  of this fix is DISABLED (it changes no land behaviour until someone flips it), so nothing is
  unblocked or broken by landing it either way.
work_class_note: |
  bugfix — a defect in an existing gate's command selection, not new machinery.
  difficulty 2: a 3-line conditional plus its fail-on-revert suite.
note: |
  THE DEFECT (verified by reading fleet/land.sh:298 and by live observation on PR #264). land.sh's
  gate auto-detect resolved the RIG repo to exactly ONE command:
      elif [ -f "$REPO/fleet/validate_board.sh" ]; then
        GATE_PARTS+=("bash $REPO/fleet/validate_board.sh $REPO/fleet")
  validate_board.sh is a STRUCTURAL check over fleet/board/*.md. It asserts nothing about whether
  the rig's own code works. fleet/gate.sh — the canonical fleet suite (78 test files) — was NEVER
  invoked on a rig land. On PR #264 land.sh ran that one command, printed "GREEN board structurally
  valid", and merged onto a master carrying 8 RED suites. Rig merges were not test-gated at all,
  contrary to MANAGER-OPERATING-RULES §8 ("Merge gate = the FULL CI gate ... NEVER pytest-alone").

  THE FLIP: `LAND_RIG_TESTS=1` arms the suite; default 0 = DISABLED, and it ships DISABLED.
  `bash fleet/gate.sh` on master is 70 passed / 8 FAILED (rc=1, 1m44s wall, measured 2026-07-24),
  so arming it now would refuse EVERY rig land. Flipping it is a deliberate separate act gated on
  RIG-REDS-DISPOSITION. Do NOT arm it as a drive-by.

  HONEST LIMIT — CONVENTION, NOT ENFORCEMENT. This binds only callers who go through land.sh.
  `gh pr merge`, the web UI and any direct API merge defeat it entirely. The durable fix is
  forge-native branch protection with a required status check. GitHub CANNOT provide it here:
  `gh api repos/Nnyan/charon-private/branches/master/protection` returns 403 "Upgrade to GitHub Pro
  or make this repository public" (private repo, free plan). Gitea can, free and self-hosted. The
  acceptance clause is written up in fleet/state/GATE-FORGE-PROTECTION-agen-kolar.md for a board
  pass to fold into FORGE-PRIMARY-GITEA (P:1) — this ticket does NOT implement it.

  OWNS-COLLISION, DECLARED NOT HIDDEN: the 3-line conditional lives in fleet/land.sh, which
  HANDOFF-GATE-NONBYPASSABLE already owns. This ticket therefore claims ONLY the new test file and
  does not widen `owns:` to fleet/land.sh — widening it would manufacture a live owns-collision on
  the board. The land.sh hunk is a pure ADDITION inside an `elif` branch that is reached only after
  the product (src/charon/cli.py) and KSF branches, so it cannot alter the product gate path; it
  needs HANDOFF-GATE-NONBYPASSABLE's holder to accept it at merge, not to re-derive it.
accept: |
  A. land.sh's rig branch ADDS the rig suite to the existing board check; it does not REPLACE it.
     Both commands must appear in GATE_PARTS when the flip is on.
  B. ONE explicit flip, stated in-file: `LAND_RIG_TESTS=1`, default 0. Shipped OFF.
  C. The product path is provably untouched: the edited `elif` is reached only when neither
     $REPO/src/charon/cli.py nor $REPO/ksf/cli.py exists.
  D. FAIL-ON-REVERT (fleet/tests/land-rig-suite-gate.test.sh — hermetic: mktemp -d repo + local
     BARE remote + a `gh` stub first on PATH; runs the REAL land.sh, never the network):
     1. flip ON + RED suite  -> land refuses, exit 4, message names fleet/gate.sh, nothing pushed.
     2. flip ON + GREEN suite-> "gate GREEN", land proceeds past the gate; suite provably INVOKED
        (marker file), so the green is not vacuous.
     3. flip UNSET + RED suite -> the suite is NOT invoked and the land is NOT blocked. This pins
        "ships disabled"; changing the default to 1 turns it RED.
     4. flip ON -> BOTH validate_board.sh and fleet/gate.sh ran (replacing instead of adding = RED).
     Each of the three reverts (drop the block / default to 1 / replace the board line) was executed
     and observed RED before landing.
  E. `bash fleet/tests/land-rig-suite-gate.test.sh` exits 0, and it is named `*.test.sh` so
     fleet/gate.sh's glob executes it.
scope: |
  Rig-only. IN: the gate-selection conditional in fleet/land.sh and its fail-on-revert suite.
  OUT: fixing the 8 pre-existing red suites (RIG-REDS-DISPOSITION), arming the flip, adding the
  suite to the CI allowlist in fleet/checks/rig-ci-scope.sh (owned by HANDOFF-GATE-NONBYPASSABLE),
  and forge-side branch protection (folds into FORGE-PRIMARY-GITEA).
ds: |
  ## Dependencies & sequence
  depends_on: (none) — the change is inert until flipped, so it lands independently.
  SEQUENCED BEFORE ARMING: RIG-REDS-DISPOSITION must clear the 8 reds before `LAND_RIG_TESTS=1`
  becomes a sane default; arming it first blocks every rig land.
  COORDINATE WITH: HANDOFF-GATE-NONBYPASSABLE owns fleet/land.sh and fleet/checks/rig-ci-scope.sh.
  The land.sh hunk here is additive and confined to the rig `elif`; adding this suite to the CI
  allowlist belongs to that ticket, not this one.
  FOLDS INTO, DOES NOT BLOCK: FORGE-PRIMARY-GITEA (P:1) — see
  fleet/state/GATE-FORGE-PROTECTION-agen-kolar.md for the acceptance clause that makes the gate
  actual ENFORCEMENT rather than convention.
