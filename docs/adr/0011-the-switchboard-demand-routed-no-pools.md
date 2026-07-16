# ADR-0011 — The Switchboard: demand-routed provider selection (no pools, no lists)

Status: Accepted (2026-07-16)
Supersedes the "pool"/list framing in ADR-0004 for provider selection; refines
ADR-0003 (capability routing) and the demand-driven routing engine
(FLEET-DEMAND-DRIVEN-ROUTING).

## Context

Charon must never be "out of workers" while at least one viable provider exists.
The recurring failure mode is **static-list thinking**: a tool holds a fixed
pool / candidate slate / tier-slate of providers, iterates it, and dead-ends when
*that list* is exhausted — even though other capable providers are available. On
2026-07-16 the work-decomposer raised `PlannerError: all candidates exhausted`
against `glm-4.5/air/4.6` (one provider family, all HTTP 429) while ~20 other
configured providers sat idle, because `decompose_planner` selected models via
`recommend._find_trusted_models` (a static slate) instead of routing through the
demand-driven router.

## Decision

There is **no pool of providers, no list, no static candidate slate**. There is
**one Switchboard**.

**The Switchboard** is the single demand-routed selection mechanism (implemented
by `src/charon/router.py` + `forwarder.py` + `routing_policy/cost_rank.py` +
`capability/`). The contract is:

1. A **NEED** arises (a job/ticket/model-invoke), carrying its capability
   requirement and its required **context size**.
2. The NEED goes to the Switchboard.
3. The Switchboard dynamically inspects **all** providers that can serve that
   NEED, and selects the **cheapest** provider that both (a) offers the required
   **context window** and (b) is **available** (not rate-limited, not down).
4. It **connects the NEED to that provider**. If that provider becomes
   unavailable mid-flight, the Switchboard re-selects — same rule — from what
   remains available.

### Invariants

- **INV-SW1 (no list):** no tool enumerates, ranks, or holds its own set of
  providers/models. Every model-invoke is a NEED submitted to the Switchboard.
- **INV-SW2 (never falsely exhausted):** a NEED fails **only** when **every**
  capable provider is unavailable — never because one family/tier/list is
  exhausted while another capable provider is free.
- **INV-SW3 (cheapest-capable-with-context-and-available):** selection is by
  live cost among providers that pass the capability + context-window +
  availability filter, computed per-NEED, not from a cached ranking snapshot.

## Consequences

- Any code path that picks/ranks providers itself is a **bypass** and must be
  converged onto the Switchboard. Known bypasses to fix:
  `decompose_planner` (via `recommend._ask_model`/`_find_trusted_models`), and
  an audit of every other `_ask_model` / static-slate caller.
- "Broaden the candidate list" / "add tier-fallback to the slate" are **wrong
  fixes** — they are still list-thinking. The only correct fix is: route the
  NEED through the Switchboard and delete the local slate.
- `pools.py` and any remaining pool vocabulary are a legacy alias surface, not a
  selection mechanism (see [pool-is-single-source-already]); the Switchboard is
  the source of truth.

## Enforcement

- Tickets: DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD (converge the decomposer) +
  the `no-stiff-single-provider-tools` class audit.
- A NEED that dead-ends with capable providers still available is a
  release-blocking defect (INV-SW2), not a transient.
