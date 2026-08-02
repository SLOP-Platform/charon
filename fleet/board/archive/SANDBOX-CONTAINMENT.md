repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: rig-meta
branch: fix/sandbox-containment
owns: fleet/tests/lib/sandbox.sh, fleet/checks/sandbox-containment.sh, fleet/tests/sandbox-containment.test.sh, fleet/tests/session-start-hook.test.sh, fleet/tests/sync-checkouts.test.sh, fleet/tests/branch-reaper.test.sh, fleet/tests/ladder-health.test.sh, fleet/ladder-health.sh, fleet/review-pool.sh, fleet/gate.sh, .github/workflows/rig-ci.yml
depends_on: SHELLCHECK-OPTIONAL-CHECKS-ON, CLAIM-READER-CANONICAL, MODEL-HARDCODE-PURGE, PR-QUEUE-REST-ETAG, REVIEWER-TAB-POOL
real-dep: |
  READ THE DIRECTION BEFORE ACTING ON THIS LINE. These five edges exist to SEQUENCE three shared
  surfaces, not because this ticket needs anything those tickets produce. validate_board's
  owns-collision rule is satisfied by an edge in EITHER direction (`ordered(a,b) = reaches(a,b) or
  reaches(b,a)`, validate_board.sh:305), and a ticket may only edit its OWN frontmatter, so this
  is the only side of the edge this branch can write.
  The correct landing order is the INVERSE: this is a P0 incident anchor and should land FIRST,
  with the five rebasing onto it. Each collision is a small, surgical edit that a rebase absorbs
  cleanly, and none of them overlaps the other ticket's actual subject matter:
    * fleet/gate.sh <- SHELLCHECK-OPTIONAL-CHECKS-ON. That ticket changes the shellcheck block's
      blocking-ness. This branch adds a `source` + `sandbox_init` pair immediately after the
      reentrancy guard, ~60 lines above it. Disjoint hunks.
    * fleet/ladder-health.sh <- CLAIM-READER-CANONICAL. That ticket canonicalises claim READING.
      This branch renames one temp variable (TMPDIR -> LH_WORK) and its 6 uses. No claim-reading
      code is touched.
    * fleet/review-pool.sh <- MODEL-HARDCODE-PURGE, PR-QUEUE-REST-ETAG, REVIEWER-TAB-POOL (a
      pre-existing 3-way collision this branch joins as a 4th). Those three concern model-id
      hardcoding, the PR-queue REST/ETag path, and the tab pool. This branch touches ONLY the
      six lines of the temp-dir lifecycle in _review_one (204-205 + four rm -rf call sites),
      renaming the shadowing `local TMPDIR` to `_rp_work`. It is also PR #346's file — that PR's
      author should be told, and this hunk is small enough to re-apply by hand if it conflicts.
  If a reviewer would rather this branch NOT own these three files, the alternative is to split
  the trap fix into its own follow-up owned by the incumbent tickets — at the cost of leaving
  fleet/gate.sh unrunnable in the meantime. That trade was judged wrong for a P0.
serial_justified: |
  One root, three faces — and the three faces are not separable lanes, they are the SAME
  defect observed from three places. Containment (sandboxes must not be inside the work tree)
  is what makes the other two impossible, so a branch that fixed only one face would leave the
  class live while reading as done. The trap fix and the containment fix are also mutually
  blocking in practice: fleet/gate.sh cannot be RUN to verify containment until the trap defect
  is fixed, because the trap deletes the verifying run's own sandboxes. Measured: 124/124 tests
  "killed (no exit status recorded)" on master before the trap fix.
substrate: N/A
substrate-novel: |
  Checked the obvious substrate before writing the helper, because "tests need isolated temp
  dirs" is the most solved problem in testing and hand-rolling it would be indefensible.
  pytest's `tmp_path`/`tmp_path_factory` genuinely solves this for the PYTHON suites, and the
  product repo already uses it. It is not applicable here: the 124 files in fleet/tests/ are
  bash, and pytest's basetemp is itself rooted at $TMPDIR — it was pytest that produced the
  `pytest-of-stack/pytest-4/` trees found INSIDE the work tree. So the substrate was already
  present and still landed in-tree, which is the whole point: the defect is upstream of the
  temp-dir library, in the value of $TMPDIR that every one of them reads.
  bats-core (the standard bash test framework) ships BATS_TEST_TMPDIR with per-test isolation
  and would be the right answer to "how should fleet tests get temp dirs". Rejected for THIS
  ticket on scope, not merit: adopting it means porting 124 hand-rolled suites, and this is a
  P0 with two droid tabs dead. It also would not have prevented the incident — BATS_TMPDIR
  defaults to $TMPDIR too, so an in-tree $TMPDIR yields in-tree BATS sandboxes.
  `mktemp -p <dir>` is plain coreutils and needs no adoption at all; several fleet tests already
  use it. It pins the PARENT but asserts nothing, so it cannot answer "is this parent inside a
  git work tree" — which is the actual question.
  In-tree, fleet/tests/dogfood-eval-guard.test.sh:56 already carries the closest relative:
  `case "$TMPROOT" in /tmp/*|/var/*) ;; *) refusing ...` — exactly the right instinct, present
  in ONE of 124 files, and matching on a path prefix rather than on repo containment. This
  ticket generalises that single guard into a sourced helper and swaps the prefix match for
  `git rev-parse --show-toplevel`, which is literally the discovery walk a stray `git add`
  would perform. That predicate is the novel slice; everything around it is coreutils.
source: |
  Live incident 2026-08-01, operator-reported. Two droid tabs killed within the hour by
  `git add` exit 128; `bash fleet/gate.sh` unrunnable; one reviewer returned a spurious GREEN;
  16 `t <t@t>` commits and an `f.txt` blob on origin/master.
note: |
  ## ONE ROOT
  `mktemp -d` roots its output at $TMPDIR. Nothing in the rig ever CONSTRAINED $TMPDIR. So when
  a caller exported one pointing inside a git work tree, every test sandbox — nested `git init`
  repos, `git worktree add` checkouts, pytest basetemps — was built INSIDE the repo under test.
  Measured residue: fleet/state/tmpdir-land/ (53M), fleet/state/pytmp-inert/ (3.1M), and a whole
  checkout copy under scratch/fleet-copy/.

  ## THREE FACES
  1. `git add` sweeps the sandboxes in and dies:
     `warning: adding embedded git repository: scratch/fleet-copy/.../repo`
     `error: '.../worktree/' does not have a commit checked out` -> `fatal` -> exit 128, tab dead.
  2. Any tool that rm -rf's "its own" temp root deletes every OTHER concurrent test's sandbox,
     because they share the one in-tree root. This is what made gate.sh unrunnable.
  3. When a sandbox vanishes mid-run, tests running under `set -uo pipefail` (note: NO `-e`)
     fall through a failed `cd` and execute their `git add`/`git commit` against the CURRENT
     WORKING DIRECTORY — the live checkout. Those suites also `export GIT_AUTHOR_EMAIL=t@t`,
     which is why the resulting commits carry that author.

  ## WHY THE FLEET SUITE NEVER CAUGHT IT
  It cannot: the suite IS the thing being corrupted. During the incident it reported 124/124
  "killed" — no assertion anywhere claims "a fleet test did not write to the live repo". The new
  check is deliberately NOT another bash test in the same suite; it is a static+filesystem guard
  fired from CI, which runs on a fresh checkout and cannot be corrupted by the run it is judging.

  ## THE DOMINANT ROOT CAUSE, FOUND BY MEASUREMENT NOT BY READING
  The trap defect alone did not explain the blast radius, so every suite was run against its own
  temp root with a canary directory in it. Exactly one suite destroyed its root:
  fleet/tests/ladder-health.test.sh cleaned up with `rm -rf "$(dirname "$FLEET")"`, and its
  `mk_fleet` returns the mktemp dir ITSELF — so `dirname` walked one level UP into $TMPDIR, the
  root shared by every concurrent test, 12 times per run. That is the 124/124 kill.
  The guard for it is RUNTIME (`sandbox_rm`), not a lint: two other suites use the identical
  `rm -rf "$(dirname "$X")"` text CORRECTLY because their builders return "$root/<subdir>".
  A text lint would red correct code and get itself turned off.

  ## FIX, IN DEPENDENCY ORDER
  1. fleet/tests/lib/sandbox.sh — `sandbox_init` pins $TMPDIR to a root validated OUTSIDE every
     git work tree (predicate: `git rev-parse --show-toplevel`); `sandbox_mk` re-asserts after
     creation; `sandbox_cd`/`sandbox_require` abort loudly (exit 99) instead of falling through.
  2. fleet/gate.sh calls `sandbox_init` once and EXPORTS the result — one choke point that gives
     all 124 test files containment without any of them being modified.
  3. The three suites that provably wrote to the live checkout use `sandbox_mk`/`sandbox_cd`.
  4. fleet/review-pool.sh + fleet/ladder-health.sh: trap-expansion class fixed (distinct
     non-shadowing variable, expanded at trap-DEFINITION time via `printf %q`).
  5. fleet/checks/sandbox-containment.sh, fired from .github/workflows/rig-ci.yml, REDs on both
     the static shape and on in-tree residue.

  ## SCOPE HELD DELIBERATELY
  `.gitignore` is NOT touched here: MARKER-PROOF-MECHANIZE owns it and a PR was bounced today
  for a drive-by edit to it. The exact lines are surfaced in the PR body for its owner. Note
  that `scratch/` cannot be ignored wholesale — 40 legitimate `scratch/*.md` docs are tracked.
  The residue half of the new check covers the same ground and is owned by this ticket.
