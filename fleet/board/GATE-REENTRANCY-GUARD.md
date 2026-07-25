repo: charon
tier: strong
difficulty: 3
priority: 1
work_class: ci-infra
branch: fix/gate-reentrancy-guard
commit: 2b6d2ad
worktree: /home/stack/code/charon-wt-GATE-REENTRANCY
owns: src/charon/gate_runner.py, tools/gate_contract.py, tests/test_gate_contract.py, tests/test_gate_reentrancy.py
serial_justified: ALREADY BUILT as one commit (fix/gate-reentrancy-guard @ 2b6d2ad) — the guard in src/charon/gate_runner.py and its enforcement in tools/gate_contract.py are a single re-entrancy contract; either half alone still recurses. Remaining work is adversarial review + land, not a build that could fan out.
depends_on:
dep-kind:
priority_justification: P:1 (PRIORITY-LADDER "attached work") — it is the hard prerequisite of the
  P:0 ticket DIFF-COVER-MUTMUT-ADOPT, whose CRITICAL F4 fix cannot start until the gate stops
  invoking a pytest run that re-invokes the gate. Not P:0 itself: nothing is broken on master today
  (the recursion only arms once a gate that runs pytest is registered), and the branch is already
  built, so it drains fast and unblocks the P:0 behind it.
work_class_note: ci-infra — the gate runner / gate contract spine, not a product feature. A defect
  here makes every PR in the product repo non-terminating.
state: BUILT, NOT LANDED. Branch fix/gate-reentrancy-guard @ 2b6d2ad is checked out in
  /home/stack/code/charon-wt-GATE-REENTRANCY. Remaining work = adversarial review, then land.
note: |
  Closes the gate↔test-suite RECURSION CLASS in the PRODUCT repo (/home/stack/code/charon):

    pytest → tests/test_gate_contract.py → charon gate → pytest → test_gate_contract → …

  tests/test_gate_contract.py runs EVERY tools/-rooted gate declared in tools/gates.json as a
  subprocess. Any gate that itself runs the test suite therefore re-enters the suite, unbounded.
  Observed by execution (see the DIFF-COVER review): depth 3 and still growing at ~300 s, with a
  nested `coverage run -m pytest` at every level.

  Blast radius when armed: .github/workflows/ci.yml `pytest -q -n auto` AND
  `python3 -m charon.cli gate` both recurse, so EVERY PR in the repo burns its full 20-minute
  timeout on the shared self-hosted 4-LOM runner and dies — not just the PR that added the gate.
  Under `-n auto` the recursion is multiplied across xdist workers. Local `charon gate` breaks too.

  This is a CLASS fix (a re-entrancy guard), not a one-gate patch: it must hold for the next gate
  that shells out to pytest, not only for diff-cover.
accept: |
  - Adversarial review (reviewer != builder) — edits the load-bearing gate spine.
  - Fail-on-revert proof (tests/test_gate_reentrancy.py): a fixture gate that shells out to the
    test suite is detected and refused/short-circuited at depth 1; revert the guard → the test goes
    RED (it must be a real RED, not a timeout-shaped hang).
  - Bounded runtime asserted: the guard test must have a finite timeout so a regression fails fast
    instead of hanging CI, which is the exact symptom being fixed.
  - `python3 -m charon.cli gate` and `pytest -q` both terminate on a branch WITH a diff (the master
    no-diff path short-circuits and never showed the bug — do not accept a master-only trial).
ds: |
  ## Dependencies & sequence
  No depends_on — this branch is self-contained in the product repo and its owned surface
  (src/charon/gate_runner.py, tools/gate_contract.py, tests/test_gate_contract.py,
  tests/test_gate_reentrancy.py) collides with no live board ticket. It is claimable NOW.
  THIS ticket is the predecessor of DIFF-COVER-MUTMUT-ADOPT (product, P:0), which now carries
  `depends_on: ... GATE-REENTRANCY-GUARD` with a real-dep justification: F4 in that ticket's
  DO-NOT-LAND review is the same recursion, and the reviewer's own ordering is "F4 first — nothing
  else matters until the gate stops invoking a pytest run that re-invokes the gate."
  Concurrency safety: work from /home/stack/code/charon-wt-GATE-REENTRANCY — fix/gate-reentrancy-guard
  is checked out there and git will refuse a second checkout of the same branch.
