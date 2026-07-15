# Planner provider-failover — session notes

Branch: `feat/planner-provider-failover` (from `master`)
Ticket: de-stiffen the decompose planner — search across ALL configured providers until one
serves chat, instead of picking ONE model and hard-failing.

## Before / after control flow

BEFORE:
- `plan_decomposition` → `_default_invoker` → `_select_planner_model` returned exactly ONE
  model. Every reprompt in the loop hit that SAME model.
- `_post_chat` caught ALL exceptions (HTTPError/URLError/JSONDecodeError/…) → returned `None`.
  A 401 auth failure was indistinguishable from a genuine unparseable plan, surfacing as the
  opaque `PlannerError: no parseable JSON after N attempts`.

AFTER:
- `plan_decomposition` builds an ORDERED candidate pool (`_ordered_planner_candidates`) and
  delegates iteration to the new reusable primitive `failover_loop.invoke_with_failover`.
- Per candidate it runs the existing reprompt loop (`build_prompt → _parse_units →
  assert_disjoint_waves`) via `_attempt_candidate`, which classifies each attempt:
  - provider-level transport fault (`PlannerTransportError`) → `FAILOVER` → next candidate.
  - 200-but-garbage body / hallucinated unit / disjointness violation → `RETRY` (same model,
    up to `max_reprompts`), then advance.
  - valid collision-free split → `OK`, returned immediately (first valid wins).
- Only when EVERY candidate is exhausted → `PlannerError` naming each model's failure class
  and ending with: "pool exhausted — configure a chat-capable provider or set
  CHARON_DECOMPOSE_PLANNER_MODEL to a working model".

## Reusable-by-composition design (operator directive: "no tool should be that inflexible")

The failover control-flow is NOT inlined in the planner. New stdlib-only module
`src/charon/failover_loop.py` exposes the generic primitive:

    invoke_with_failover(candidates, attempt, *, max_retries, describe, recommendation, error) -> T

with `AttemptResult(kind=OK|RETRY|FAILOVER, value, feedback, attribution)`. The planner is the
FIRST consumer; `_post_chat` is its per-candidate `ask_one`. This is a distinct concern from
the existing `failover.py` (proxy↔pool-router glue with gateway deps) — the new module is
dependency-free so privileged-core (stdlib-only) callers can adopt it.

FOLLOW-UP ADOPTERS (not touched in this ticket — de-stiffen next):
- `recommend._ask_model` (recommend.py:74) — same one-model-then-None stiffness; wrap its
  `_find_trusted_models` list with `invoke_with_failover`.
- `cli.py` chat path — same single-model invoke.

## Failure-class taxonomy chosen (fix A)

`_post_chat` now RAISES `PlannerTransportError(failure_class, status, detail)` instead of a
blanket `None`:
- auth  → HTTP 401 / 403 / 407
- limit → HTTP 402 / 429
- infra → 5xx and any other HTTP status, plus URLError / TimeoutError / OSError (no status)
Classification via `_classify_status`. A 200 whose body is not a parseable JSON dict still
returns `None` = a quality/parse fault of THAT model (→ reprompt same). urllib types never
leak to callers.

## Public-signature preservation

- `_select_planner_model` kept working — now returns the FIRST of the ordered pool.
- `plan_decomposition` / `BroadTicket` / `ChangeSurface` / `ModelInvoker` / `PlannerError`
  signatures unchanged. `intake.py:1051` caller and all existing tests untouched-compatible.
- Removed the now-redundant `_default_invoker` (folded into `plan_decomposition`); it had no
  external callers.

## Accept results

- `PYTHONPATH=src python3 -m pytest -q tests/test_decompose_planner.py` → **21 passed**
- `PYTHONPATH=src python3 -m pytest -q` → **1746 passed, 1 xfailed, 1 xpassed** (161s)
- `ruff check src/charon/decompose_planner.py` → **All checks passed!**
- `mypy src/charon/decompose_planner.py` → **Success: no issues found**
- `PYTHONPATH=src python3 -m charon.cli gate` → **CHARON-GATE: all checks passed**
  (inert-code OK — all new public symbols are production-reachable; NO disposition entry needed)

New tests added (tests/test_decompose_planner.py):
- `test_failover_on_auth_advances_to_next_provider` — 1st 401s, 2nd serves valid plan.
- `test_pool_exhaustion_names_each_failure_and_recommends` — all 401 → PlannerError names each
  model + failure class + "configure a chat-capable provider".
- `test_garbage_body_reprompts_same_model_not_failover` — 200-garbage reprompts SAME model
  (asserts call sequence == same id twice), not failover.
- `test_ordered_candidates_pin_first_and_never_anthropic` — pin first, tier-high next, no
  Anthropic/claude in the ordered list (guards intact, fail-on-revert).
Existing fail-on-revert proofs (`assert_disjoint_waves` gate, SG-never-Anthropic, pin/tier
ordering) all still green.

## Files
- `src/charon/failover_loop.py` (new, stdlib-only reusable primitive)
- `src/charon/decompose_planner.py` (consumer + taxonomy + ordered candidates)
- `tests/test_decompose_planner.py` (new failover/exhaustion/distinction/guard tests)

Commit SHA: 3c306cc (3c306cc93c0d11a154d2236367b921c1a469e607)
NOT pushed / NOT landed — manager lands and re-runs live e2e dogfood.
