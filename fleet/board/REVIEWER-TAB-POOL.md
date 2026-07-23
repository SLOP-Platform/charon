repo: charon-private
tier: strong
difficulty: 4
work_class: rig-meta
priority: 0
branch: feat/reviewer-tab-pool
depends_on:
owns: fleet/review-pool.sh, fleet/tests/review-pool.test.sh, fleet/state/review-queue.tsv
work_class_note: |
  Operator-approved 2026-07-23. The REVIEW analog of the SG-tab pool: reviewer tabs claim PR-review work
  from a queue (just like SG tabs claim build tickets), run the adversarial review OFF-CLAUDE via CG,
  write a verdict, and surface it to the Manager session for FINAL DISPENSATION (merge/close). Keeps the
  Manager token-lean (dispensation only, never runs reviews from its own context) and mechanizes the
  reviewer≠builder gate + the anti-pile flow in one. [[dispose-open-prs-never-pile]]
  [[charon-headless-review-loop]] [[adversarial-review-default-for-droid-prs]] [[token-lean-review-and-droids]]
  [[reviews-use-our-own-tools]] [[no-rig-as-product-adopt-dont-handroll]]
accept: |
  Build a reviewer-tab pool that mirrors the SG-tab work model for PR REVIEWS. COMPOSE, don't hand-roll —
  reuse claim.sh's atomic claim ladder, the existing headless review loop ([[charon-headless-review-loop]]
  — `opencode --model charon/*`, off-Claude via CG), and the board/state substrate.
    1. **Review queue:** each open droid PR needing review = a claimable review item. Auto-mint one per
       open PR (source of truth = open PRs on each repo). An already-reviewed PR (verdict on file) is not
       re-queued. This is the board↔PR↔done reconciliation drift-leg — coordinate with UNIFIED-
       RECONCILIATION-GATE (#178) so it's one mechanism, not two.
    2. **Reviewer launcher:** `fleet/review-pool.sh <tier> [--wait --retries]` — claims a review item
       (atomic, own worktree, reviewer≠builder enforced: the reviewer must NOT be the PR's author droid),
       runs an ADVERSARIAL review of that PR off-Claude via CG (ground-truth the diff, money-path gets the
       deep pass), and writes a structured VERDICT (APPROVE-FOR-MERGE / NEEDS-REVISION / BOUNCE + blockers
       + fail-on-revert check) to a review-log the Manager reads. Do NOT reuse/edit fleet-droid.sh's owns
       (avoid the collision) — its own script.
    3. **Manager dispensation stays manual:** the pool produces verdicts; the Manager merges/closes. The
       pool NEVER merges or closes a PR itself (two-owner firewall + human/manager final call on money-path).
  PROVE IT: fail-on-revert test — a fixture PR queued → a reviewer claims it (not its author) → produces a
  verdict of the right schema → Manager can read it. Dogfood: run it against 1-2 of today's open PRs and
  confirm the verdict matches the hand-reviews (this session's #187/#188 verdicts are the ground truth —
  the pool must have caught the #188 dead-no-op).
scope: |
  Reviewer-tab pool = the SG-pool model for PR reviews: queue open PRs → reviewer tabs claim + adversarially
  review off-Claude via CG (reviewer≠builder) → verdict to Manager for final merge/close. Composes claim.sh
  + the headless review loop + the reconciliation board↔PR↔done leg. Manager never runs reviews from context.
ds: |
  ## Dependencies & sequence
  - depends_on: none to start; COORDINATE with UNIFIED-RECONCILIATION-GATE (#178) on the board↔PR↔done
    queue-source so there's one drift mechanism. Reuse claim.sh + charon-headless-review-loop — do not
    rebuild them.
  - owns its own script (fleet/review-pool.sh) — NOT fleet-droid.sh (owned elsewhere; avoid collision).
  - firewall: reviewer≠builder is a HARD requirement; the pool must never merge/close (Manager dispenses).
