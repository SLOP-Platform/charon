repo: charon
tier: frontier
difficulty: 4
work_class: routing
priority: 1
branch: feat/sw-p2-context-admit
depends_on: SW-STATIC-LEGS-RETIRE, ORDER-A-COST-PRIMARY-LAND
real-dep: SW-STATIC-LEGS-RETIRE — REAL BUILD PREREQ. The admit decision must read the context value that
  DISCOVERY supplies (catalog_refresh.py:55 `_META_KEYS` carries `context_window`, bridged into the spec
  at :122 and read at routing_policy/__init__.py:81). Until the static legs are retired, some routes get
  their context from a hand-pinned catalog row that Phase 1 deletes — building the filter against that
  value is throwaway. Owns are DISJOINT (this ticket does not touch catalog_refresh/__init__.py).
dep-kind: build
owns: src/charon/forwarder.py, tests/test_context_admit.py
serial_justified: |
  One decision point plus its proof. The admit/skip choice lives in a single block
  (forwarder.py:400-422, "R7 capability-engine") and the estimate it compares against is computed three
  lines above it; separating the estimate from the comparison ships a filter that reads a number nobody
  owns.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Graded run — record into fleet/model-scorecard.tsv under work_class `routing`. Own git worktree.
source: |
  Switchboard-convergence investigation, 2026-07-26 (manager session), CORRECTED at authoring time.
note: |
  ## CORRECTION TO THE BRIEF — READ THIS FIRST
  The investigation reported "no `context_window` reference anywhere in src/charon/forwarder.py, so
  INV-SW3's context filter is captured but never filtered on." The string is indeed absent, **but the
  filter EXISTS under a different name**: `src/charon/forwarder.py:400-422` is an R7 max_context /
  max_concurrency eligibility pass, and `routing_policy/__init__.py:81` maps the catalog's
  `context_window` onto the route's `max_context`. A zero-hit grep was read as absence — the exact
  wrong-pattern class recorded as A3 in `VERIFICATION-SUBSTRATE-HARDENING`. **Do not "build" this filter.
  It is there. Fix what is actually wrong with it.**

  ## THE REAL INV-SW3 GAP (three defects in the existing filter)
  1. **Unknown context ADMITS.** `forwarder.py:407-409`: `mc = getattr(r, "max_context", None)`; if `mc`
     is `None` the route is admitted with no check. Every discovery-sourced route whose provider does not
     advertise `context_window` therefore bypasses the filter entirely — it is not
     "cheapest-capable-WITH-CONTEXT", it is "cheapest, context permitting, if we happen to know it."
     Decide the disposition and make it LOUD: unknown context must be attributable, not silently
     equivalent to unlimited.
  2. **The estimate is `len(raw_body) // 4`** (`forwarder.py:402`), floored at 100. A byte/4 heuristic
     over the raw JSON body counts envelope and escaping as prompt, and has no relationship to the
     provider's own tokenizer. A wrong estimate in the admitting direction is an overflow failure at the
     upstream; in the excluding direction it is a false exhaustion (INV-SW2). Say which way it errs and
     bound it.
  3. **The strand fallback erases the invariant.** `forwarder.py:418-422`: if EVERY route is excluded,
     the full chain is restored with a warning. That is the correct safety choice and must stay — but as
     written it means a request larger than every known context still gets dispatched to a route that
     cannot serve it, and the operator learns about it from a log line nobody reads. Make the
     fall-back-to-full-chain event a first-class, attributable signal (it is a genuine "no capable leg"
     condition, which is exactly what INV-SW2 wants surfaced rather than hidden).
accept: |
  DONE-CONTRACT (observable, on the LIVE gateway):
  - A request whose estimated size exceeds a route's context is NOT dispatched to that route, AND a
    route with UNKNOWN context is handled by a stated, attributable rule rather than admitted silently.
    Demonstrate both on the live gateway with a real oversized request and name the routes skipped.
  - The "all routes excluded -> full chain" fallback still NEVER strands a request (prove it), but now
    emits an attributable no-capable-leg signal visible outside the log — a reviewer can see it fired.
  - `tests/test_context_admit.py`, FAIL-ON-REVERT and red-proofed by execution: (a) oversized request +
    small-context route -> route skipped; revert -> RED. (b) route with `max_context=None` -> the new
    rule applies; revert to blind admit -> RED. (c) all-excluded -> full chain restored AND the signal
    fires. Report BOTH exit codes for each. Non-vacuous: zero routes examined is RED.
  - Estimator accuracy is stated as a measured bound against at least one real provider's reported
    prompt tokens — not asserted.
  - `charon.cli gate` GREEN + `pytest -q` GREEN from the worktree.
  - ADVERSARIAL REVIEW (reviewer != builder): this filter can cause false exhaustion, which is
    release-blocking under ADR-0011.

## Dependencies & sequence

- **Depends on: SW-STATIC-LEGS-RETIRE** (real build prereq, see `real-dep:`) and
  **ORDER-A-COST-PRIMARY-LAND** (MERGE-ORDER ONLY — shared `src/charon/forwarder.py`).
- **SCHEDULING HAZARD, operator decision needed:** `ORDER-A-COST-PRIMARY-LAND` is live but itself
  depends on `GW-CUTOVER-LIVE-WIRE`, which is PARKED and currently claimed. As written, this ticket
  cannot start until that chain moves. The dep exists because two concurrent writers of forwarder.py is
  a board RED, not because the work is coupled. **Resolve one of:** (a) land or unblock ORDER-A,
  (b) transfer forwarder.py ownership to this ticket and re-scope ORDER-A, or (c) accept the wait.
  Do NOT silently drop the edge — that reintroduces the owns-collision.
- **Wave:** wave 1, PHASE 2. Concurrent with SW-P2-METER-OBSERVED and SW-P2-GRADE-PLANE-SETTLE
  (all three own disjoint files) and with SW-ADR0016-SETTLE.
- **Blocks: nothing.**
- **Concurrency safety:** `tests/test_context_admit.py` is unowned; `src/charon/forwarder.py` is owned
  only by ORDER-A (live, sequenced above) and by FT-WIRE-QUOTA / GW-CUTOVER-LIVE-WIRE, both PARKED.
  Verified against the full `owns:` set of `fleet/board/*.md`, 2026-07-26.
