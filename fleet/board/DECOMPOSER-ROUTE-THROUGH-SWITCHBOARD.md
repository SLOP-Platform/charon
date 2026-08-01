repo: charon
tier: strong
priority: 2
difficulty: 3
work_class: money-path
branch: feat/decomposer-route-through-switchboard
owns: src/charon/decompose_planner.py
depends_on:
dep-kind:
work_class_note: MONEY/routing-adjacent — bypasses the cost-based switchboard, so a fix here
  changes what the decomposer pays. Adversarial review REQUIRED before land.
note: |
  OBSERVED 2026-07-15: the work-decomposer dead-ended with "all candidates exhausted"
  (PlannerError) despite ~2 dozen configured providers. Root cause is architectural, not just
  the exhaustion path: ``decompose_planner.py`` never asks the switchboard (the existing
  router/forwarder stack — ``src/charon/router.py`` (StaticRouter), ``forwarder.py``
  (``forward_with_failover``), ``routing_policy/cost_rank.py`` + siblings, ``capability/``) which
  dynamically inspects ALL providers and picks the cheapest that is (a) capability/context-
  capable and (b) available. Instead ``_ordered_planner_candidates`` (decompose_planner.py:454)
  calls ``recommend._find_trusted_models`` — a PARALLEL, self-contained "trusted models" slate —
  and ``plan_decomposition`` posts to each candidate directly via its own ``_post_chat``
  (decompose_planner.py:519, raw ``urllib.request`` to the resolved ``base_url``), entirely
  outside the gateway's router/forwarder/cost_rank path. This is a
  [no-stiff-single-provider-tools] — the decomposer IS its own separate un-cost-aware router.

  A same-day commit (3c306cc, "provider-failover across ordered candidate pool") added
  failover ACROSS this self-built slate (fixing the immediate observed dead-end symptom — the
  slate isn't actually family-narrow, it includes every trusted/keyed model) but did NOT fix the
  architecture: the decomposer still self-selects/self-ranks (pin -> tier-"high" -> rest) instead
  of routing through the switchboard's cheapest-capable-available logic. Any future rate-limit/
  cost-drift on the switchboard's model catalog is invisible to the decomposer, and its ranking
  ignores real $/request.
accept: |
  ``decompose_planner.py`` becomes a DUMB CLIENT of the switchboard: it submits its NEED
  (capability class + required context size) through the gateway's router/forwarder path and
  lets the switchboard pick cheapest-capable-available — it must never enumerate, rank, or
  directly HTTP-call a provider itself. Delete ``_ordered_planner_candidates`` /
  ``_select_planner_model`` / the direct ``_post_chat`` transport once the switchboard client
  seam replaces them (keep ``failover_loop.invoke_with_failover`` as the reusable retry
  primitive around the switchboard call, matching the pattern other switchboard clients use).
  FAIL-ON-REVERT: mock the high-tier family as all-429/exhausted at the switchboard layer while
  >=1 OTHER capable+available provider is configured -> the decomposer's NEED still gets served
  (through the switchboard, not a self-built list); it only raises ``PlannerError`` when EVERY
  capable provider is unavailable. A second test asserts ``decompose_planner.py`` makes NO direct
  ``urllib``/HTTP call and NO call to ``recommend._find_trusted_models`` — it only calls the
  switchboard client seam (revert to direct-call -> test goes RED).
  CLASS AUDIT (record as follow-on convergence tickets, do not fix here beyond decompose_planner):
  every other model-invoking caller that picks/ranks providers itself instead of routing through
  the switchboard — ``recommend._ask_model`` / ``recommend._find_trusted_models`` (recommend.py,
  used by ``recommend_tiers`` for tier-voting — same static-slate shape, distinct from live work
  routing, still worth convergence review) and ``fleet/capability/assign.py`` (rig-side dispatch
  picker, separate repo/boundary — note only, no product owns overlap). List them in the PR
  description; do not silently expand this ticket's owns to cover them.
scope: |
  Root-cause architectural fix for today's decomposer dead-end: the decomposer must be a
  switchboard client, never its own router. MONEY-adjacent (changes provider spend); routing-
  adjacent (touches the north-star "never out of workers while >=1 viable" invariant). Product
  repo, no rig change.
ds: HIGH — auto-decomposition feeds the claim hopper; a dead-ended decomposer starves the board.
  No blocking depends_on (decompose_planner.py is not owned elsewhere on the board); sequence
  ahead of any ticket that relies on auto-decomposition being reliable.
