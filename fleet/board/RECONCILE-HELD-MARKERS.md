repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: fix/reconcile-held-markers
owns: fleet/reconcile-held-markers.sh, fleet/tests/reconcile-held-markers.test.sh
depends_on:
note: |
  33 state/done/* markers are HELD (not merge-verified) by retire-done.sh because they carry
  only `merged:#PR` (no sha) or no proof, so verify_merged falls to a network check that can't
  confirm — leaving them cluttering the active board forever (board↔GitHub done-marker drift).
  MECHANICAL data hygiene, NO merge-to-master. Pairs with DONE-SH-REPO-AWARE (rig PRs need the
  ticket's own repo for the lookup).
accept: |
  ## Task — fleet/reconcile-held-markers.sh
  For each HELD marker (retire-done.sh reports them), resolve its status ONCE, repo-aware:
  - Read the ticket's `repo:` from board/<id>.md or board/archive/<id>.md; map to owner/slug.
  - Look up the ticket's branch's PR in THAT repo. If MERGED: backfill the marker with
    `merged:<merge-sha>` (so verify_merged's fast LOCAL sha-ancestry check passes henceforth) and
    let retire-done archive it. If genuinely NOT merged: leave it HELD and EMIT it to a
    needs-action list (do NOT silently archive unmerged work — matches retire-done's G3c guard).
  - Idempotent; batch the gh lookups (one `gh pr list --state merged` per repo, not per-marker) —
    avoid the O(markers×network) trap (same class as the done.sh / reconcile-merged perf bugs).
  ## Accept (fail-on-revert)
  - After a run: `bash fleet/retire-done.sh` reports 0 HELD for every marker that has a merged PR
    (all now carry merged:<sha>); genuinely-unmerged ones are listed, not archived.
  - Test: a fixture with (a) a marker whose branch has a merged PR -> gets a sha + retires;
    (b) a marker with no merged PR -> stays HELD + listed. Batched lookup (assert not per-marker).
  ## Dependencies & sequence
  depends_on: (none) — read-only against GitHub + local markers; no master merge.
