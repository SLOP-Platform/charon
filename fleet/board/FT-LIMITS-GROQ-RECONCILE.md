repo: charon-private
tier: economy
priority: 2
difficulty: 2
work_class: money-path
branch: feat/ft-limits-groq-reconcile
depends_on:
owns: fleet/state/FREE-TIER-LIMITS.tsv, fleet/tests/ft-limits-reconcile.test.sh
accept: |
  ADVERSARIAL REVIEW REQUIRED (trust / money-path): this row decides whether the LARGEST free tier in
  the stack (groq, 14,400 RPD) is trusted for routing + preflight. A wrong number here spends real money
  by pushing traffic off a free tier, or burns quota by over-trusting one. Reviewer verifies each number
  against a CITED source, not against the previous row.

  BLOCKER — READ THIS FIRST (verified 2026-07-16, this is why the ticket exists in this shape):
  `fleet/state/FREE-TIER-LIMITS.tsv` is **GITIGNORED AND UNTRACKED** (`.gitignore:10` -> `fleet/state/*`;
  `git check-ignore -v` confirms; `git ls-files fleet/state` -> 20 tracked files, this is NOT one). It
  exists ONLY as local state in the live rig tree. Consequence: a droid branch/clone does NOT contain
  this file, and a normal `git add` SILENTLY does nothing — the "fix" would land as an empty PR and the
  mismatch would persist. THE FIRST DELIVERABLE IS THEREFORE TO PUT THE FILE UNDER VERSION CONTROL:
    1. Seed the file into your worktree from the live rig tree state copy (it is local-only state).
    2. `git add -f fleet/state/FREE-TIER-LIMITS.tsv` — the `-f` is REQUIRED to defeat .gitignore.
       PRECEDENT (not a new pattern): 20 sibling state files are already force-tracked this exact way,
       incl. fleet/state/CONFIG-SOURCES.tsv, ON-DEMAND-TOOL-LEDGER.tsv, ROADMAP.tsv, RULE-SYNC-REGISTER.tsv.
    3. Verify with `git ls-files --error-unmatch fleet/state/FREE-TIER-LIMITS.tsv` BEFORE committing.
  If you skip this, your PR is empty and the ticket is not done.

  PROBLEM. The groq row SELF-FLAGS its own disagreement. Verified current content of line 5:
    groq	free-groq|deepseek-v4-pro-groq|gpt-oss-120b-groq_MISMATCH_UNRECONCILED	unpublished	unpublished	unpublished	unpublished	unpublished	unknown	unknown	unverified
  Header (line 1): provider / model_ids / rpd / rpm / tpm / tpd / context_cap / trains_on_data /
  personal_only / exhaustion_signal.
  The literal token `_MISMATCH_UNRECONCILED` is welded onto a model id inside the pipe-delimited
  model_ids field, so `gpt-oss-120b-groq` does not parse as a model id at all — any consumer splitting
  model_ids on `|` reads a model that does not exist. Every other numeric column is `unpublished` /
  `unknown` / `unverified`, so this row currently carries ZERO usable routing facts for the biggest free
  tier in the stack. Operator directive #30 ([[always-fix-catalog-mismatches]]): fix catalog mismatches
  ON SIGHT and mechanize the detection.

  DO.
    (a) Track the file (see BLOCKER above) — non-negotiable first step.
    (b) RECONCILE the groq row against groq's PUBLISHED free-tier limits. Resolve `_MISMATCH_UNRECONCILED`
        by determining which model ids are REAL and separating them properly with `|`. Fill rpd/rpm/tpm/
        tpd/context_cap with sourced values; every value you cannot source stays explicitly `unpublished`
        (do NOT invent numbers — an invented limit is worse than an admitted unknown). Cite the source
        URL + retrieval date in the PR body for each number you set.
    (c) `personal_only` and `trains_on_data` are POLICY columns, not perf: per [[charon-free-tier-routing]]
        free tiers are PERSONAL-only per ToS. Set from the provider's actual terms, cite them.
    (d) MECHANIZE (#30 requires detection, not just a one-time fix): fleet/tests/ft-limits-reconcile.test.sh
        must FAIL on any row carrying an unreconciled marker or a malformed model_ids field — so the next
        mismatch cannot sit in the file for weeks unnoticed. This is the durable half of the ticket.

  FAIL-ON-REVERT (fleet/tests/ft-limits-reconcile.test.sh — REQUIRED):
    (1) Feed the checker a FIXTURE row containing `_MISMATCH_UNRECONCILED` (or any `_MISMATCH`/
        `UNRECONCILED` marker) -> checker RED. Remove the marker -> GREEN. Revert the checker -> the
        fixture stops failing -> the test itself fails. Test the CHECKER against a fixture; never assert
        against the live TSV's current contents (a live-content assertion goes green the moment the row
        is edited and proves nothing about the detector).
    (2) MALFORMED model_ids: a fixture whose model_ids field contains a token that is not a valid model
        id shape (e.g. a welded suffix) -> RED.
    (3) TRACKING GUARD: assert `git ls-files --error-unmatch fleet/state/FREE-TIER-LIMITS.tsv` succeeds.
        `git rm --cached` the file -> RED. This is the fail-on-revert for the BLOCKER fix and the ONLY
        thing preventing this ticket from silently regressing to a local-only file.

  GREEN-IS-NOT-PROOF (explicit): NO existing rig test reads FREE-TIER-LIMITS.tsv — the file is untracked
  local state, so the entire suite is green RIGHT NOW with the mismatch sitting in the file, and would
  stay green if the file were deleted outright. A green suite is therefore zero evidence for this ticket.
  Worse, the reconciled row is DATA: a test that asserts today's numbers is a tautology that passes by
  construction and re-goes-green on any future corruption. Only the three fixture-driven checker tests
  above count. Reviewer: confirm the file is force-tracked (step 3), that no number is uncited, and that
  the checker is exercised against fixtures rather than the live file.
scope: |
  Rig free-tier catalog reconcile + detector. The groq row of fleet/state/FREE-TIER-LIMITS.tsv
  self-flags `gpt-oss-120b-groq_MISMATCH_UNRECONCILED` and carries no usable numbers, while groq is the
  largest free tier in the stack (14,400 RPD). The file is additionally GITIGNORED/untracked, so the fix
  is unlandable until it is force-tracked (20 sibling state files set the precedent). Reconcile the row
  against sourced limits and mechanize marker/malformed-row detection per directive #30.
  [[always-fix-catalog-mismatches]] [[charon-free-tier-routing]] [[use-free-tiers-to-their-limits]]
  [[config-ssot-git-manifest]]
ds: |
  ## Dependencies & sequence
  depends_on: (none) — the rig TSV is UNOWNED by any live ticket (board-verified 2026-07-16).
  not-covered-by (checked, genuinely disjoint): FT-CATALOG-SEED owns the PRODUCT-side seed
    (src/charon/provider_presets/hosted.py, routing_policy/free_tier_catalog.py,
    tests/test_free_tier_catalog.py) and its accept states verbatim that "the product cannot read the
    build-rig FREE-TIER-LIMITS.tsv (product/rig boundary), so it needs its OWN shipped seed" — it is
    product-side BY DESIGN and does not own this rig file. FREE-TIER-QUOTA-SPILL is PARKED. No overlap.
  boundary: RIG-side data only ([[product-vs-build-rig-boundary]]). Do NOT edit product files and do NOT
    make the product read this rig TSV — that boundary is deliberate and FT-CATALOG-SEED depends on it.
  concurrency: RUNS NOW, zero-dep. Owns one untracked data file + one NEW test -> parallel-safe with
    every live ticket, no shared writer.
  soft-follow-on (NOT owned here, do not build): once tracked, this row becomes a candidate fact row for
    SSOT-DRIFT-GATE's SSOT-REGISTRY.tsv. Data feed only, no code edit, no build dep either direction.
  wave: economy refill 2026-07-16. Do FIRST — zero-dep economy work feeding an idle economy tab.
  repo: charon-private (rig).
note: Created 2026-07-16 from fleet/session-notes/2026-07-16-evidence/audit-harvest.md item 5. Zero-dep,
  economy, READY NOW. ADVERSARIAL REVIEW REQUIRED (trust). BLOCKER baked into accept: the owned TSV is
  gitignored/untracked (.gitignore:10) — must be `git add -f`'d or the PR lands empty.
</content>
</invoke>
