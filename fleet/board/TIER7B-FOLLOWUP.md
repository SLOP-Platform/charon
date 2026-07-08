tier: sonnet
work_class: tests
branch: feat/tier7b-followup
depends_on:
owns: tests/test_tier_lifecycle.py, src/charon/api.py
prompt: /home/stack/charon-private/prompts/tier7b-followup.md
scope: TWO non-blocking items surfaced by TIER7B's (#56, merged) escalated review — small
  test + small hardening. `owns:` is PROVISIONAL (set at activation when the prompt is written).
  No marker conventions needed: depends_on is EMPTY, so there is no disjoint-owns dep to justify
  (no `real-dep:`/`dep-kind:` line required).
  1. **Multi-member within-tier ordering guard (test).** TIER7B routes to a TIER; the
     within-tier free-first/cost_rank ordering is DELEGATED to the gateway and is currently
     only tested with SINGLE-member tier pools. Add a regression test that gives one tier a
     2-member pool and asserts the cheaper/free member is selected through the per-tier
     warm-map path. Locks the HARD1-flagged concern under regression.
  2. **Proxy-teardown-on-setup-error (small hardening).** Pre-existing window, WIDENED by
     Phase B from 1 render to N: in `api.py`, the proxy started by `serve_in_thread()`
     (~api.py:183) is only torn down inside the inner try/finally (~api.py:245); if the
     warm-map build (`_acp_via_renderer`/`render`, ~api.py:197) throws between proxy-start and
     the inner try, the proxy thread LEAKS (the worktree is still cleaned by the outer finally).
     Wrap proxy-start + warm-map build so the proxy is torn down on ANY setup failure. Low risk
     (`render()` is pure templating) — hardening, NOT a bug fix.
note: PARKED follow-up to TIER7B (#56, merged). Non-blocking polish — NOT a production-readiness
  blocker. Activate after the dogfood/production-readiness push. Low priority.

## NOTE — PARKED, NOT CLAIMABLE

**Non-blocking polish, deferred.** Staged `.parked` so no droid claims it ahead of the
production-readiness push. Both items are HARD-flag follow-ups from the TIER7B (#56) escalated
review — neither blocks release.

TYPE: **droid-build** (small). `depends_on` EMPTY (board-unblocked). `owns:` is PROVISIONAL —
confirm exact file set when the build prompt is written at activation.

Un-park / activation checklist:
1. Dogfood / production-readiness push complete (this is explicitly lower priority than that).
2. Write the build prompt at `/home/stack/charon-private/prompts/tier7b-followup.md`.
3. Re-confirm `owns:` (tests/test_tier_lifecycle.py, src/charon/api.py) still disjoint vs any
   in-flight wave; `bash validate_board.sh` GREEN before renaming `.parked` -> `.md`.
