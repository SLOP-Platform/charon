# ADR-0017 — Charon is an Outcome-Graded Gateway; MVP is Wiring the Brain

- **Status:** Accepted (2026-07-19; operator-ratified)
- **Deciders:** Nnyan (solo operator)
- **Repo:** `github.com/SLOP-Platform/charon`
- **Relates to:** ADR-0001 (thin orchestrator / integrate-don't-rebuild — this ADR
  re-asserts that posture after months of drift), ADR-0005 (routing posture)
- **Evidence:** four investigations + a passing LiteLLM spike + one adversarial review +
  one orchestration eval, archived in the session salvage set
  (`SURVEY-*.md`, `REDDIT-DEEPDIVE-*.md`, `REVIEW-*.md`, `EVAL-orchestration-options.md`,
  `DECISION-RECORD-charon-strategy.md`).

---

## Context

Charon shipped ~zero user-facing product in months while a hand-rolled build-rig grew
nearly as large as the thing it guards. Root cause: a doctrine bias (`core is stdlib, wrap
tools as plugins`) that never let the commodity *substrate* be adopted — so every subsystem
became ~70% reinvented commodity around a ~30% novel slice. ADR-0001 already prescribed the
opposite ("integrate established tools; build only the gap"); it drifted. The default is now
flipped in both projects' session-doctrine files and this ADR is its canonical home.

## Decision

**Charon is an outcome-graded gateway.** The product is a routing brain that sends each unit
of work to the cheapest model *proven by real graded outcomes* (tests pass / review accept /
merge / revert) to handle that class of work — not by an up-front difficulty guess (the
approach RouterArena shows never beats the oracle) and not by spend-share (what OpenRouter
Auto actually does). This is the confirmed open gap in OSS; Braintrust/Inworld sell only
closed SaaS versions, so Charon is **the open, self-hostable one**.

### The honest current state (confirmed against code)

The differentiator **already exists — in the fleet**: `model-scorecard.tsv` → `grades.py` /
`assign.py`, real per-(model × work-type) verdicts. The **gateway does not use it yet** — its
request router reads a separate `quality.json` (latency + HTTP-200 health routing; the
"no-downgrade" weight is a dead constant), and `grep` finds zero references to the brain in
the gateway `src/`. "One brain, two surfaces" is the target, not the shipped state.

### MVP (ratified)

> **Wire the fleet's existing outcome-graded brain into the gateway's request routing,
> replacing the commodity health-check — with a cold-start fallback.**

This is a bounded connection task, not a from-scratch build. **MVP = the gateway (Capability
A) only.** Fleet orchestration (B) and review gates (C) are post-MVP.

### Cold-start (required design, not yet designed)

A fresh install has zero graded outcomes → `assign()` refuses → on day 1 an "outcome-graded"
router is just static config. Before the differentiator is a day-1 property it needs a
bootstrapping story (seed scorecard / static cheapest-capable fallback until N real outcomes
/ importable scorecard). Until designed, "outcome-graded" is a v2 property.

## Build vs Adopt (by evidence tier)

| Concern | Verdict | Tier |
|---|---|---|
| OpenAI proxy / failover / cost / cooldown | ADOPT — LiteLLM | **PROVEN** (spike PASS; policy unchanged; deletes ~650–750 LOC; cost 218MB + native deps on hot path) |
| Gates: checks / mutation / inert / drift | ADOPT — pre-commit + Semgrep + mutmut + shellcheck | STRONG (survey); the gate→guard→meta-gate recursion is self-inflicted by bash |
| Branch / merge / worktree lifecycle | ADOPT — merge-queue + git-town + auto-delete | PARTIAL (auto-delete ON; merge-queue blocked on plan) |
| Crash-recovery / durable orchestration | ADOPT? — DBOS/Restate | UNPROVEN but FIT CONFIRMED (durable activities can supervise external processes); DEFERRED |
| **Outcome-graded router brain** | **BUILD — the product** | the ~30%, unmet in OSS |
| **disjoint-`owns` + gate-before-merge policy** | **BUILD — thin novel bit of B/C** | the verification ceiling |

## Explicitly NOT built

A coding agent (swap behind `CHARON_AGENT_CMD`); a standalone fleet SaaS (dead category —
Terragon/Vibe Kanban shut 2026); a predict-time/difficulty-classifier router; a hand-rolled
rules/doctrine loader (Claude Code ships scoped rules + skills + memory recall natively).

## Fleet & orchestration engine (deferred, direction pre-chosen)

The disciplined fleet (disjoint-`owns`, isolated worktrees, 3–5 parallel, gate-before-merge)
is the pattern Anthropic runs in production — validated, kept as a post-MVP capability and as
how-we-build, on **adopted** plumbing. Engine choice is DEFERRED; the eval settled the
direction: **not LangGraph** (in-process nodes, wrong shape for external workers), **not
MCP-alone** (a seam with no engine) — **spike DBOS/Restate when B reaches the critical path.**
What keeps B alive now already exists: `CHARON_AGENT_CMD` + git worktrees + session-bridge
MCP + auto-delete + git-town.

## Consequences

**Positive:** a bounded, shippable MVP; deletes a large commodity/rig surface; concentrates
build effort on the one thing nobody else ships open.
**Open constraints (must resolve before a multi-user offering):** provider ToS / code-privacy
of routing *other users'* code through personal-tier providers; merge-queue plan-gate; the
cold-start design; a durable-exec spike before that adopt is a verdict.
**Risks that survive even the disciplined shape:** disjoint files ≠ disjoint decisions
(prescribe shared contracts in the ticket); verification throughput is the true ceiling
(the gate must be mechanized); 15× token cost + thin real parallelism in coding (don't
manufacture parallel tickets on coupled work).


---

## Amendment (2026-07-19) — the gateway consumes grades; it does not produce them

Scoping the MVP against the code corrected the "bounded connection task" framing. Two facts,
confirmed against the source:

1. **The product ships no outcome store yet.** `capability/scorecard.py` is a freeze-ring /
   onboarding store (the wrong one); the "actuals ledger" referenced in
   `capability/__init__.py` does not exist as a file; `routing_policy/matrix.py` is a
   `(model × work_class) → grade` *shape* whose populating engine is still unbuilt. So the MVP
   has a **prerequisite build**, not just a wire.
2. **Live request traffic is not a grading signal.** A gateway response yields only
   HTTP-status / latency / cost — the commodity health signal already captured by the existing
   quality scorer. A real outcome grade (a unit of work judged pass/fail/merge/revert) is
   produced **out-of-band** — by graded work runs or an imported scorecard — never by serving
   an API request. **The gateway is a read-only consumer of the grade ledger; it never writes
   grades from its own traffic.**

**Consequences (these sharpen, not reverse, the decision):**

- **Supply chain of the differentiator:** graded work (or an imported scorecard) → outcome
  ledger → gateway routing. The routing edge depends on a grade *source*; with none, the
  gateway falls back to static cheapest-capable ordering — so the cold-start path is
  load-bearing, not a corner case.
- **Day-1:** ship a **seed scorecard**, or "outcome-graded" is inert on a fresh install.
- **Decomposition (revised MVP):** (1) build a product-side outcome ledger + a grades
  provider + a seed/import path; then (2) the bounded, read-only gateway consumer that orders
  candidates by grade with a fail-open static fallback. The request → work-type key is handled
  by the existing *kind* classifier (`taxonomy.py`) — a classifier of work KIND, not a
  difficulty predictor, so it does not violate the "no predict-time router" line above.
- **Coupling:** this means the routing differentiator and the work-orchestration capability
  are more coupled than a strict "A-only" reading implied — the orchestration path is where
  grades are *born*. The gateway remains the MVP surface; the grade source (graded runs or
  import) is its required input.
