repo: charon-private
tier: economy
difficulty: 2
work_class: ci-infra
branch: fix/verify-merged-repo-aware
depends_on:
owns: fleet/_lib.sh, fleet/done.sh, fleet/tests/verify-merged-repo-aware.test.sh
accept: |
  IN FLIGHT — the branch `fix/verify-merged-repo-aware` ALREADY EXISTS and carries the work. This
  ticket was created 2026-07-18 to give that in-flight branch a board identity: it is the dependency
  target of REPO-DECL-CENTRAL, REPO-FIELD-REQUIRED and REPO-MAP-CONVERGE, and a depends_on with no
  ticket behind it is a HARD board failure (validate_board rule 2, `bad-dep`). Verify the branch
  against this accept rather than rebuilding it.

  PROBLEM. `verify_merged` / done.sh resolve a ticket's merged-PR proof against the PRODUCT repo for
  any ticket lacking a `repo:` field. verify_merged GATES DESTRUCTIVE ACTIONS (retire-done archives
  the ticket and REMOVES its worktree). A RIG ticket could therefore be "merge-proven" by a PRODUCT
  commit. This is not hypothetical — REPO-DECL-CENTRAL was closed exactly this way against
  c44e7bda (a PRODUCT docs-only merge) while zero rig code shipped.

  DO.
    (a) fleet/_lib.sh: ONE canonical declaration of PRODUCT_REPO / PRODUCT_SLUG / FLEET_REPO /
        FLEET_SLUG. This is the SINGLE HOME for the repo->path/slug map. Every other copy is drift.
    (b) fleet/done.sh: make the merge check repo-aware — resolve the ticket's `repo:` to BOTH the
        checkout root (for the local ancestor check) and the GitHub slug (for the gh check). Today
        the ticket's repo remaps only REPO_SLUG; CHARON_REPO (the path `sha_in_master` walks) is
        NOT remapped, so a `--merged-sha` proof is still validated against the wrong tree.
    (c) Prefer the LOCAL, offline-checkable `merged:<full-sha>` proof form over `merged:#<pr>`.

  FAIL-ON-REVERT (fleet/tests/verify-merged-repo-aware.test.sh — REQUIRED): construct a RIG ticket
  whose candidate proof sha exists ONLY in the PRODUCT repo, and assert verify_merged REJECTS it.
  Revert the repo-awareness -> the product sha is accepted again -> the test goes RED. Assert the
  REJECTION of the cross-repo sha; asserting that a correct sha is accepted is a tautology that
  passes with the bug present.
scope: |
  Repo-awareness for the merge-verification path, plus the canonical repo declaration in _lib.sh that
  the rest of the rig then sources. Root of the wrong-repo bug class.
  [[no-hardcoded-cross-boundary-paths]] [[product-vs-build-rig-boundary]]
  [[confirm-dont-trust-documentation]] [[security-is-a-ratchet-gate]]
ds: |
  ## Dependencies & sequence
  depends_on: (none) — zero-dep, and it is the ROOT of this chain. Land it FIRST.
  unblocks: REPO-DECL-CENTRAL (consumer migration), REPO-FIELD-REQUIRED (validator rule),
    REPO-MAP-CONVERGE (map convergence) — all three depend_on this ticket and all three are blocked
    until the canonical _lib.sh declarations exist.
  single-writer: this ticket is the ONLY writer of fleet/_lib.sh and fleet/done.sh in this chain.
    REPO-DECL-CENTRAL and REPO-MAP-CONVERGE were both deliberately scoped to EXCLUDE _lib.sh so the
    declarations are written exactly once ([[optimize-execution-wallclock-tokens]]).
  boundary: RIG-ONLY ([[product-vs-build-rig-boundary]]). No product-repo file is edited.
  concurrency: runs alone on _lib.sh + done.sh; parallel-safe with every ticket that does not touch
    those two files.
  wave: rig board correction 2026-07-18.
  repo: charon-private (rig).
note: |
  Created 2026-07-18 during board maintenance. The BRANCH PRE-EXISTS this ticket — verified diff vs
  origin/master: fleet/_lib.sh (+92), fleet/done.sh (12 changed), fleet/tests/
  verify-merged-repo-aware.test.sh (+110 new), fleet/board/archive/REPO-DECL-CENTRAL.md (+1).
  NOT YET LANDED. The board ticket exists so the three dependent tickets have a resolvable
  depends_on target; do not treat this as un-started work.
  MERGE-CONFLICT HEADS-UP: the branch's hunk against fleet/board/archive/REPO-DECL-CENTRAL.md will
  conflict — that ticket has been moved back to fleet/board/REPO-DECL-CENTRAL.md (its 2026-07-16
  done-marker was a phantom; the code never landed). Resolve by dropping that hunk.
