repo: charon
tier: strong
difficulty: 3
work_class: routing
branch: feat/destiff-recommend
owns: src/charon/recommend.py, tests/test_recommend.py
depends_on:
note: |
  "No stiff single-provider tools" class-fix (operator directive 2026-07-15). recommend._ask_model
  (recommend.py:74) POSTs to ONE model and hard-fails — same stiffness the planner had. Adopt the
  SHARED primitive src/charon/failover_loop.py::invoke_with_failover (already on master, built for
  the planner) so tier-voting fails over across ALL configured providers before giving up. This is
  fix-at-the-CLASS-level via COMPOSITION (do NOT re-implement a bespoke loop). See
  MANAGER-OPERATING-RULES §12 "FIX AT THE CLASS LEVEL".
accept: |
  ## Task
  - Route recommend._ask_model / recommend_tiers' model call through
    failover_loop.invoke_with_failover over the ORDERED trusted-model candidate list (reuse
    recommend._find_trusted_models for discovery), so a transport/auth/limit failure on one
    provider fails over to the next, exhausting the pool before returning empty.
  - Preserve existing behavior: the tier-voter path MAY use Anthropic (unlike the planner's
    SG-never-Anthropic guard — do NOT add that guard here); keep the current return contract.
  - Distinguish transport/auth failures from a genuine unparseable reply (reuse the primitive's
    classification), so a single dead provider no longer zeroes out the recommendation.
  ## Accept (fail-on-revert)
  - New test: first candidate 401s, second returns a valid catalog answer -> recommend_tiers
    uses the SECOND (proves failover). All-candidates-fail -> clear empty/err result, not a hang.
  - PYTHONPATH=src python3 -m pytest -q tests/test_recommend.py && PYTHONPATH=src python3 -m pytest -q
    && ruff check src/charon/recommend.py && mypy src/charon/recommend.py
    && PYTHONPATH=src python3 -m charon.cli gate   (all GREEN; gate is deterministic now)
  ## Dependencies & sequence
  depends_on: (none) — failover_loop.invoke_with_failover is already on master (#141).
