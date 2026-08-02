# Review: 400@charon-private
**PR:** docs(review-log): correct UNBLOCK-REVIEW-INFRA PR attribution + current status
**URL:** https://github.com/Nnyan/charon-private/pull/400
**Date:** 2026-08-02T05:11:36Z
**Reviewer:** reviewer-tab-2808948
**Author:** strong-2780982

## Verdict
NEEDS-REVISION

## Findings
- fleet/state/UNBLOCK-REVIEW-INFRA.md self-contradicts on the #346↔#393 conflict: the machine-actionable `accept:` block says "#346 ... now conflicts with #393's review-pool.sh hunk," while the same file's `note:` and docs/review-log both assert it "merges cleanly against current master (no conflict with #393's trap fix)." A pool operator or gate parsing `accept:` as criteria will act on the stale claim and mis-dispose #346.
- `accept:` step 2 is stale — it instructs "PR #389 (reviewer-tab) ... Land or fix it before scaling," yet both files record #389 as already LANDED (merge e83bea0, 2026-08-02T04:48:33Z). The gate criteria contradict the doc's own findings, so the "accept" section cannot be trusted as the operative checklist.
- Count inconsistency proving the correction is incomplete: `accept:` says the CHARON-AUTHOR-DROID marker appears in "ZERO of 16 PRs," while the review log and `note:` both say ZERO of 32 open PRs. The accept block still carries the errors of the very "first fragment" the doc admits was wrong.
- Unverifiable, future-dated evidence: the #389 merge timestamp 2026-08-02T04:48:33Z postdates today (2026-08-01), and no gh/git output is attached to support the "What I proved by executing" section. The doc is the only ground truth other droids will act on to close/rework real PRs, yet its core evidence is either fabricated or non-contemporaneous — a trust/supply-chain violation in the disposition channel.
- The stated goal "preserve B1 / prevent silent disarm" is not actually achieved: #392's git-commit-author extraction is endorsed as "same semantics," but commit author name is self-asserted (spoofable, and reads as Nnyan on human pushes — the exact failure mode used to dismiss `user.login`). The doc blocks both alternatives (marker, user.login) while cementing a gate that is still trivially disarmed, and never verifies whether the reviewer-tab tooling it lands (#389) is supposed to write the marker before rejecting #346's producer-less check.

## Fail-on-revert check
A revert drops the disposition record that keeps #346's CHARON-AUTHOR-DROID fail-closed author extraction from landing; without it, B1 would reject every PR as unknown author and the reviewer pool would review nothing.

## Status
Pending Manager dispensation
