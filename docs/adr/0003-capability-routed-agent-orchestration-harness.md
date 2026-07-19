# ADR-0003 — Capability-Routed Agent Orchestration Harness

> **Number is a placeholder.** Assign the next free integer in the target
> repo's ADR sequence before commit; do not merge with `NNNN`. This ADR is a
> peer of the agent-framework evaluation that adopted ZeroClaw on Path C and
> decided to build `ms-router` natively (the "Mediastack autonomous ops agent"
> backlog item). It supersedes nothing; it promotes `ms-router` from a routing
> *library* to the *brain* of an orchestrator.

> **Posture superseded by ADR-0017 (2026-07-19).** This ADR's "build the routing brain (and engine) natively" posture is overtaken by ADR-0017's adopt-substrate / build-only-the-brain framing: the outcome-graded **brain stays**, but the routing/gateway **plumbing is adopted (LiteLLM)** rather than hand-built, and the engine is deferred.

- **Status:** Accepted (2026-06-26)
- **Deciders:** Nnyan (solo operator)
- **Relates to:** `ms-router` decision; agent-framework evaluation (ZeroClaw Path C); memU schema lift for success-rate tracking; ADR-0017 (outcome-graded gateway)
- **Methodology:** ADR + tiered implementation; ports-and-adapters; derive-or-verify; structural enforcement over honor-system

---

## 1. Context

The goal is a harness that, with minimal operator input, works a project to
completion by (a) routing each unit of work to the most capable available
agent/model, (b) continuing on a different agent when one exhausts its session,
(c) running adversarial review to a consensus gate before accepting work, and
(d) staying in a working loop until done.

A survey of the current landscape (mid-2026) establishes the constraint that
shapes this ADR: **no single tool does all four.** They cluster into four
*planes*, and existing tools each cover a subset:

- **Capability routing** is covered by model gateways (OmniRoute-class) and by
  orchestration plugins (oh-my-claudecode / oh-my-codex) that route across
  Haiku/Sonnet/Opus tiers and specialist agent roles.
- **Adversarial review-to-consensus** is covered by dedicated loops
  (cross-model debate with a circuit breaker) and by native Agent Teams.
- **Autonomous looping** is covered by persistence modes (Ralph / autopilot /
  ultrawork) that block stop events.
- **Cross-agent session-exhaustion handoff is covered by nothing cleanly.** Per-turn
  model *fallback* lives in gateways; cross-*session* *resume* lives in
  checkpoint harnesses (agx-class) — but resume-on-the-same-agent is not
  handoff-to-the-next-agent. The seam between them is the novel contract.

Existing assets reduce scope: `ms-router` already is the routing brain; the
memU schema already gives structured success-rate memory. What is missing is
(i) a stable execution port that treats CLI agents as swappable backends, and
(ii) the continuity contract that makes "the next appropriate agent continues"
mean something precise rather than "re-run and hope."

Two standing constraints from prior decisions carry in:

- **Supply-chain bar.** LiteLLM was rejected (supply-chain compromise);
  NanoBOT, trustclaw, one-api rejected as thin/over-large/untrusted. Any
  third-party dependency in a privileged loop must clear that bar.
- **Control-plane discipline.** The embedding host project keeps a hard control-plane fence (admin
  surfaces LAN/Tailscale-only). An orchestrator that spawns CLI agents with
  `--dangerously-skip-permissions` and applies diffs unattended is a control
  plane; it inherits the fence requirement.

---

## 2. Decision

Build a **ports-and-adapters orchestrator** that treats CLI coding agents
(Claude Code, Codex CLI, Gemini CLI, …) as swappable execution backends behind a
stable task-execution port, composed of **four planes** over a single
vendor-neutral source of truth (the **Work Ledger**):

```
                    ┌─────────────────────────────────────────────┐
                    │              Orchestrator core               │
                    │  (loop authority · fence · tier selection)   │
                    └───────────────┬──────────────┬───────────────┘
            Routing plane ──────────┘              └────── Consensus plane
        (ms-router: predictive,                      (cross-model adversarial
         task-level, tier+provider)                   review → consensus gate)
                    │                                          │
                    ▼                                          ▼
        ┌───────────────────────── Execution plane ───────────────────────┐
        │  stable port: dispatch(unit, tier, budget, ledger_ref)→Outcome  │
        │   ClaudeCodeAdapter   │   CodexAdapter   │   GeminiAdapter  ...  │
        └────────────────────────────┬─────────────────────────────────────┘
                                      │
                              Continuity plane
                   (Work Ledger · checkpoint boundaries · handoff)
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  Work Ledger (ONE per task)          │
                    │  + git worktree per provider         │
                    │  + last-known-good ref               │
                    └─────────────────────────────────────┘
```

The architectural commitments, in order of how load-bearing they are:

1. **The Work Ledger is the single source of truth for task progress.** Agent
   internal sessions are *satellite copies* and may be discarded at any
   checkpoint boundary. This is derive-or-verify applied to agent state.
2. **Handoff happens only at checkpoint boundaries, never mid-trajectory.** An
   agent's internal reasoning state is not portable across vendors; the only
   portable unit is `(files-on-disk + ledger entry)`.
3. **Routing is predictive and task-level** — tier+provider chosen *before*
   generation, not per-token, not run-all-then-pick.
4. **"Always working" is bounded by a consensus gate and a circuit breaker.**
   An unbounded working loop is indistinguishable from unbounded cost and blast
   radius; the stop condition is part of the contract, not an afterthought.
5. **Privileged actions cross a control-plane fence.** Auto-apply is
   default-deny; autonomy is a graded ladder the operator sets.

---

## 3. The execution port (stable indirection)

Adapters are swappable behind one interface; this is the same pattern as the
host project's auth-provider indirection with Tinyauth/Authelia as adapters.

```
Port: AgentBackend
  dispatch(unit: WorkUnit, tier: Tier, budget: Budget, ledger: LedgerRef) -> Outcome
  health() -> Health            # {budget_remaining, rate_limit_state, context_pressure}
  capabilities() -> CapSet      # task-classes this backend is competent at
  kill()                        # terminate at the nearest checkpoint boundary, no data loss
```

Adapter responsibilities (the contract every backend must honor):

- Translate `WorkUnit` → CLI invocation in an **isolated git worktree** for that
  provider (clean rollback; no cross-provider contamination).
- Stream/capture the trajectory; surface `health()` truthfully.
- On completion **or** interruption, write the checkpoint to the Ledger
  (§4). Adapters never own progress truth — they report it to the Ledger.
- Be killable at any checkpoint boundary with no progress loss (INV-5).

**Non-portability is explicit:** adapters MUST NOT rely on rehydrating another
provider's internal session. Rehydration is always from Ledger + disk (H3).

---

## 4. Continuity plane — the handoff contract (core, novel)

This is the part no existing tool ships and the part most likely to be wrong if
left implicit. It is specified as predicates and invariants.

### 4.1 The Work Ledger

Exactly one per task. A vendor-neutral, on-disk, append-mostly record. Each
**checkpoint entry** contains, at minimum:

- `goal` — the unit's objective.
- `acceptance` — **executable** acceptance criteria (tests/checks/commands),
  not prose. See Prediction 2.
- `done` — what is completed and committed.
- `verified` — what has passed its acceptance check.
- `remaining` — machine-derivable as `acceptance \ verified`.
- `lkg_ref` — last-known-good commit; never points past an unverified commit.
- `provider_history` — which backend produced each checkpoint (for routing and
  for excluding an exhausted provider on handoff).

### 4.2 H-predicates (handoff preconditions)

- **H1 (Resumability).** A unit is resumable iff its Ledger entry contains
  `{goal, acceptance, done, verified, remaining, lkg_ref}`. A unit lacking any
  field is not handoff-eligible and must be repaired before dispatch.
- **H2 (Boundary).** Handoff occurs only at a checkpoint boundary. No
  mid-trajectory handoff. Ever.
- **H3 (Idempotent rehydration).** A receiving adapter rehydrates from
  `Ledger + disk` alone and derives the *same* `remaining` regardless of which
  provider wrote the checkpoint. (Requires executable `acceptance`; prose
  acceptance is an H3 hazard — Prediction 2.)
- **H4 (Exhaustion detection).** The orchestrator triggers snapshot-and-handoff
  — not retry-on-same — when any of: hard budget cap hit, rate-limit/quota
  error, or context-pressure threshold exceeded. Exhaustion is detected by the
  orchestrator via `health()`, not inferred from failure alone.
- **H5 (No progress loss).** On exhaustion, work committed before the last
  checkpoint is never discarded. Only the uncommitted in-flight delta since the
  last checkpoint may be replayed by the receiving agent.
- **H6 (Handoff is a routing decision).** The next provider is chosen by
  re-running the router with the exhausted provider excluded and the current
  Ledger state as input. Handoff order is not a static fallback list.

### 4.3 Invariants

- **INV-1.** Exactly one Work Ledger per task; it is the sole source of truth
  for progress. Agent sessions are satellite copies (derive-or-verify).
- **INV-2.** `lkg_ref` never points past an unverified commit.
- **INV-3.** No unit is marked complete until it passes the consensus gate (§6).
- **INV-4.** Privileged/destructive operations (apply, delete, deploy) require
  crossing the control-plane fence (§7); auto-apply is default-deny.
- **INV-5.** An agent session may be killed at any checkpoint boundary with no
  data loss (follows from H5 + INV-1).
- **INV-6.** `remaining` is always machine-derivable (`acceptance \ verified`),
  never a human-authored free-text field.

---

## 5. Routing plane (`ms-router` extended)

**Predictive, task-level routing** — select `(tier, provider, budget)` for a
whole unit *before* generation. Rejected alternatives and rationale in §9.

Classifier inputs: task-class `{codegen, refactor, test-authoring, review,
diagnosis}`, blast radius (files touched · reversibility), target-region code-
quality signals, novelty. Output: `(tier ∈ {LOW=Haiku, MED=Sonnet, HIGH=Opus},
provider, budget_envelope)`.

The routing policy is **data, not code** — externalized so it tunes without a
redeploy. memU-style success-rate memory feeds back: per
`(task-class, tier, provider)` success rate updates the policy, with a **stable
default** so the system is useful before the bandit converges (MAB convergence
is slow; the default prevents cold-start thrash).

---

## 6. Consensus plane (adversarial review → gate)

After a unit executes, a **cross-model** reviewer (different provider than the
executor — cross-model catches more and filters false positives) reviews against
the executable `acceptance`. Review is itself a task-class and is routed.

- **Consensus gate predicate.** A unit passes iff `{no blocking findings}` OR
  `{disagreements resolved through bounded debate to agreement}`.
- **Circuit breaker.** Debate is bounded to `N` rounds; on non-convergence,
  escalate to the operator. This is what makes "always working" terminate
  rather than diverge. Borrow the structure of existing adversarial-review
  circuit breakers; do not reinvent.
- **Confidence skip.** Low-blast-radius units may skip review under a confidence
  threshold (Prediction 3 — review on *every* unit roughly doubles token cost).

---

## 7. Control-plane fence & autonomy ladder

Direct analog of the host project's hard control-plane fence. The orchestrator's
privileged actions — spawning agents with skip-permissions, applying diffs,
running destructive shell — are the control plane and are default-deny.

**Autonomy ladder** (operator-set, structurally enforced — not honor-system):

- **L0 — Propose-only.** Agents produce diffs; nothing is applied.
- **L1 — Apply reversible-only.** Apply changes with a clean `lkg_ref` rollback;
  no deletes/deploys.
- **L2 — Apply with consensus.** Apply once the consensus gate passes.
- **L3 — Full-auto within fence.** Unattended, but destructive ops still gated
  by predicate; nothing escapes the worktree/fence boundary.

Worktree isolation per provider is part of the fence: a misbehaving agent's
blast radius is its worktree, and rollback is `git`-clean.

---

## 8. Build vs. buy (per plane)

- **Routing plane — BUILD.** `ms-router` lineage; existing libs already
  rejected. The brain is the differentiator.
- **Execution adapters — BUILD THIN.** Buy the agents (Claude Code, Codex,
  Gemini CLI); build the thin adapters that wrap them behind the port.
- **Transport/gateway — BUY ONLY IF IT CLEARS THE BAR, else THIN NATIVE.**
  Because execution runs *through* CLI agents that manage their own model calls,
  a gateway is only needed for the router's own classifier calls and any
  direct-API review. Keep it minimal; do not take a LiteLLM-class dependency in
  the privileged loop.
- **Continuity plane — BUILD NATIVE.** This is the gap; agx-class tools resume
  the same agent, not the next one. The Ledger and handoff contract are yours.
- **Consensus plane — BUILD ORCHESTRATION.** Reference existing adversarial-
  review loop structure; own the gate and circuit breaker.

---

## 9. Alternatives considered

- **Adopt oh-my-claudecode / oh-my-codex wholesale.** Rejected as *primary*:
  solo-maintainer supply-chain surface (fails the established bar at the trust
  level required for an unattended privileged loop), runs skip-permissions, and
  — decisively — has no cross-vendor session-exhaustion handoff, the one thing
  most wanted. Retained as a *reference* and a candidate execution-plane adapter
  target.
- **Native Claude Code Agent Teams.** Single-vendor; no cross-provider handoff;
  no cross-vendor capability routing. Good fit for the *review plane*
  sub-problem only.
- **Pure multi-provider gateway (OmniRoute-class) alone.** Solves per-turn
  fallback; solves neither task continuity nor consensus. It is one plane, not
  the system.
- **Non-predictive routing (run-all-pick-best).** Rejected: prohibitive in
  agentic settings where trajectories are long-running.
- **Single frontier model for everything (do-nothing baseline).** Rejected: pays
  premium on trivial work and has no continuity story — but it is the honest
  fallback if the harness ROI does not materialize. Keep it as the comparison
  baseline.

---

## 10. Named class predictions

In keeping with the methodology, the predicted *classes* of failure this design
will face (so they are watched for, not discovered):

- **Prediction 1 — checkpoint granularity, not routing, is the dominant failure
  class.** Too-coarse boundaries → large H5 replay on handoff; too-fine →
  Ledger churn. Tuning effort concentrates here, not in the classifier.
- **Prediction 2 — cross-provider rehydration drift (H3 violations).** Different
  agents read the same `remaining` differently *when acceptance is prose.* The
  mitigation is structural: `acceptance` MUST be executable, making `remaining`
  machine-decidable (INV-6). Prose acceptance is the leading H3 hazard.
- **Prediction 3 — consensus-gate cost blowup.** Reviewing every unit roughly
  doubles token cost; the confidence-skip threshold (§6) is load-bearing, not
  optional.
- **Prediction 4 — the autonomy fence is what makes unattended operation safe.**
  Without §7, "minimal operator input" is indistinguishable from "unbounded
  blast radius." If exactly one thing ships first, it is the fence.

---

## 11. Tiered implementation plan

Mirrors the host project's auth adapter tier structure: prove the boundary contract before
adding the second backend.

- **Tier 1 — Single provider + Ledger.** One adapter (ClaudeCodeAdapter). Build
  the Work Ledger, checkpoint boundaries, executable-acceptance format, and the
  L0/L1 fence. Continuity plane is *contracted but single-provider* (resume on
  the same agent). Proves H1–H3, H5, INV-1/2/5/6.
- **Tier 2 — Second adapter + handoff.** Add CodexAdapter (or Gemini). Light up
  H4/H6 and real cross-vendor handoff. This is where the novel contract gets
  its first real test.
- **Tier 3 — Consensus plane.** Cross-model adversarial review, consensus gate,
  circuit breaker, confidence-skip. Proves INV-3.
- **Tier 4 — Autonomy ladder L2/L3.** Unattended operation within the fence,
  with success-rate memory feeding the routing policy.

---

## 12. Open questions / prerequisite workstreams

- **Executable-acceptance format.** Blocks H3/INV-6; this is the first design
  artifact Tier 1 needs and the thing most worth getting right early.
- **Exhaustion-signal availability per CLI.** Do Claude Code / Codex / Gemini
  CLI expose budget, quota state, and context-pressure cleanly enough for
  `health()` to be truthful? This needs grounding against real tool behavior
  (validate in Claude Code, plan mode) rather than reasoning in the abstract —
  H4 is only as good as the signal.
- **Supply-chain vetting** of any gateway dependency before it enters the
  privileged loop.

---

## 13. Consequences

**Positive.** A vendor-neutral continuity contract that is the actual
differentiator versus every surveyed tool; capability routing reusing existing
`ms-router` + memU assets; an autonomy ladder that makes unattended operation
auditable; clean rollback via per-provider worktrees.

**Negative / cost.** The Ledger + executable-acceptance discipline is real
upfront work and constrains how units may be authored (prose-only tasks are not
admissible). Consensus review adds token cost. The handoff contract adds a
layer that a single-vendor tool does not pay for — justified only because
cross-vendor continuity is the requirement that motivated the build.

**Reversibility.** If the harness ROI does not materialize, the §9 baseline
(single frontier model) remains available; Tier 1 alone (Ledger + single
adapter + fence) is independently useful as a checkpoint-disciplined autonomous
loop even if Tiers 2–4 are never built.
