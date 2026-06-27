# TIER7B-FOLLOWUP — review log

Two non-blocking polish items surfaced by TIER7B's (#56) escalated review. Neither
is a production-readiness blocker; this is hardening + regression coverage only.

## Item 1 — multi-member within-tier ordering guard (test)

TIER7B routes to a TIER and DELEGATES within-tier free-first/cost_rank ordering to
the gateway. The prior `test_tier_lifecycle.py` cases only ever used SINGLE-member
tier pools, so the within-tier ordering was never pinned through the engine's
per-tier warm-map path (the HARD1-flagged concern).

Added `test_within_tier_two_member_pool_selects_free_member`: one tier (`high`) with
a 2-member pool whose members rewrite to DISTINCT wire models on the same mock
upstream. `tiers.json` lists the members PAID-FIRST on purpose; the gateway's shared
compiler must still sort the free/cheaper member first. The mock upstream records
the served wire model, so a within-tier ordering regression flips the assertion from
`free-wire` to `paid-wire`. Locks the concern under regression at the wire.

## Item 2 — proxy-teardown-on-setup-error (hardening)

Pre-existing window, WIDENED by Phase B from one render to N: in `run_task`'s tier
branch the per-run proxy is started by `serve_in_thread()`, but the run's inner
`try/finally` (which reaps the proxy) is not yet in scope. If the warm-map build
(`_acp_via_renderer`/`render`) throws between proxy-start and that inner try, the
gateway thread leaks — the OUTER finally only reclaims the worktree.

Fix: wrap proxy-start + the warm-map build in a `try/except BaseException` that
`proxy_server.shutdown()`s and re-raises, so the proxy is torn down on ANY setup
failure. Applied the same pattern to `_start_proxy_acp` (the single-upstream
`--proxy` path has the identical start-then-render shape). Low risk — `render()` is
pure templating; this is hardening, NOT a bug fix.

Added `test_proxy_torn_down_when_warm_map_build_fails`: spies on every per-run
proxy's serve thread, injects a failure into `_acp_via_renderer`, and asserts the
proxy thread is not alive after the run raises.

## Scope

`owns:` = `tests/test_tier_lifecycle.py`, `src/charon/api.py` — both changes land
inside it. No other files touched (this fragment excepted). Full gate green:
549 passed · ruff · mypy · boundary · version 0.2.0.
