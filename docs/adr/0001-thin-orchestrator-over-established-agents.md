# ADR-0001 — Thin Orchestrator over Established Agents (rev. C)

> **Supersedes** the earlier "build-four-planes" draft of this ADR. Same goal,
> inverted build posture: integrate established tools; build only the gap.

> **SUPERSEDED (stdlib-only invariant) 2026-07-21 by operator ADOPT-FIRST directive** —
> the "stdlib-only privileged core / no runtime dependencies" invariant referenced here
> is removed. Maintained dependencies are allowed and no ADR is required to add one;
> adopt-first is the default and hand-rolling is the last-resort choice (negative eval
> weight). Other invariants in this ADR stand.

- **Status:** Accepted (2026-06-26; product framing & §7 routing posture amended by ADR-0005)
- **Deciders:** Nnyan (solo operator)
- **Repo:** `github.com/SLOP-Platform/charon` *(name TBD)*
- **Relates to:** ADR-0002 (project boundary & host-project integration)
- **Methodology:** ADR + tiered; ports-and-adapters; derive-or-verify
- **Priorities, in order:** (1) it works, (2) it's performant, (3) it's broadly
  compatible. Compatibility never outranks the first two.

---

## 1. Context

Form is a **thin orchestrator process** (consumption mode C): it drives existing
coding agents as backends, talks to existing gateways for model selection, and
reuses existing review tooling — owning only what nothing else owns.

The operator does not have time to build and test routing, execution loops, or
review from scratch, and shouldn't: the ecosystem now standardizes the seams.

- **Execution** is standardized by **ACP (Agent Client Protocol** — Zed/JetBrains,
  stdio + NDJSON JSON-RPC). One ACP client drives Claude Code, Codex, Gemini CLI,
  Cursor, OpenCode, KiloCode, Cline, Hermes, and more, via vendor/Zed-maintained
  adapters. ACP natively exposes **session resume/fork** and **token-usage
  reporting** — the primitives handoff and exhaustion-detection need.
- **Routing/fallback** is standardized by **OpenAI-compatible gateways**
  (OpenRouter, neuralwatt, etc.) — model selection, fallback, rate-limit handling
  as a service.
- **Review/consensus** is covered by existing cross-model review agents/skills.

What remains unowned: a **vendor-neutral Work Ledger** and **cross-vendor
handoff**. ACP session state is per-agent and not portable across vendors (model
ids aren't portable across harnesses), so the cross-vendor continuity layer is
the irreducible thing to build. Everything else is integration.

---

## 2. Decision

Build a thin coordinator with exactly four responsibilities; integrate the rest.

```
        ┌──────────────────────────────────────────────────────┐
        │     charon coordinator  (the only new code)         │
        │   loop authority · Work Ledger · handoff · fence       │
        └───┬───────────────┬───────────────────┬────────────────┘
   ACP client│       gateway client│        gate/circuit-breaker│
  (stdio/NDJSON)   (OpenAI-compat) │         (thin predicate)   │
        ▼               ▼                       ▼
  ┌───────────┐   ┌───────────┐         ┌──────────────────┐
  │ ACP agents│   │ gateways  │         │ existing review  │
  │ OpenCode  │   │ OpenRouter│         │ agents / skills  │
  │ KiloCode  │   │ neuralwatt│         │ (cross-model)    │
  │ Cursor …  │   │ …         │         └──────────────────┘
  └───────────┘   └───────────┘
        │
        ▼
  Work Ledger (ONE per task) + git worktree per backend + last-known-good ref
```

**Build (the gap only):**
1. **Coordinator loop** — dispatch units, observe checkpoints, decide handoff.
2. **Work Ledger** — vendor-neutral source of truth for task progress.
3. **Cross-vendor handoff** — resume the same task on a different backend.
4. **Control-plane fence + autonomy ladder** — privileged-op gate.

**Integrate (do not rebuild):**
- **Execution** → be an **ACP client**. Lean on the Hermes generalized-ACP-client
  pattern (one client → 14 agents via official adapters) as reference or vendored-
  upstream; do not hand-roll per-tool subprocess drivers, and do not screen-scrape
  tmux panes (fragile, slow).
- **Routing/fallback** → **gateway via OpenAI-compatible API**. Per-turn model
  selection, fallback, and rate-limit handling are the gateway's job.
- **Consensus** → existing cross-model review agents; the harness owns only the
  gate predicate + circuit breaker, not the reviewer.

---

## 3. Compatibility = protocol-first

Compatibility is bought by speaking standards, not by per-tool code:

- **Agents:** ACP (Agent *Client* Protocol, stdio/NDJSON). Any ACP backend works
  with zero bespoke code. Non-ACP tools (AnythingLLM, LobeHub, raw Oh-My-Pi, etc.)
  are reached only if they expose a headless/API surface, behind the same
  internal port — but ACP is the default path and the only one guaranteed.
- **Gateways/models:** OpenAI-compatible HTTP. Any compliant gateway is a config
  line.
- **Tools:** MCP, where a backend wants direct tool access.

**INV-P0.** The harness depends on *protocols* (ACP, OpenAI-compat, MCP), not on
any specific vendor tool. Adding/removing a backend is configuration, not code.

---

## 4. Continuity plane — the only hard build

Unchanged in intent from the prior draft; now explicitly built *on top of ACP
primitives* rather than from zero.

- **Work Ledger** (ONE per task): `goal`, **executable** `acceptance`, `done`,
  `verified`, `remaining = acceptance \ verified`, `lkg_ref`, `provider_history`.
- ACP `session/usage` reporting feeds exhaustion detection; ACP `resume/fork`
  feeds same-backend continuation. The Ledger is what makes continuation work
  *across* backends, which ACP alone does not.

**H-predicates.** H1 Resumability (ledger entry complete) · H2 Boundary (handoff
only at checkpoints, never mid-trajectory) · H3 Idempotent rehydration (receiver
derives the same `remaining` from Ledger+disk regardless of producer) · H4
Exhaustion detection (budget cap / rate-limit / context-pressure via ACP usage →
snapshot-and-handoff, not retry-on-same) · H5 No progress loss (only the
uncommitted post-checkpoint delta may replay) · H6 Handoff is a routing decision
(re-ask the gateway/policy with the exhausted backend excluded).

**Invariants.** INV-1 one Ledger = sole progress truth (sessions are satellites) ·
INV-2 `lkg_ref` never past an unverified commit · INV-3 no unit complete until the
gate passes · INV-4 privileged ops cross the fence (auto-apply default-deny) ·
INV-5 any session killable at a boundary with no loss · INV-6 `remaining` always
machine-derived (executable `acceptance`).

---

## 5. Performance (priority 2 — first-class)

The coordinator must stay off the hot path. Concretely:

- **PERF-1 — observe, don't relay.** ACP backends stream tokens/edits directly to
  disk/worktree; the coordinator subscribes to *checkpoint and usage* events, not
  every token. The harness is never a proxy in the token stream.
- **PERF-2 — cheap Ledger I/O.** Ledger is structured files + git, not a heavy DB;
  checkpoint writes are batched/async and off the critical path. Rehydration =
  read files, no replay beyond the post-checkpoint delta (H5).
- **PERF-3 — predictive routing only.** Select tier/model/backend *before*
  generation; never run-all-then-pick. Cache routing decisions per task-class.
- **PERF-4 — parallel independent units.** Dispatch independent units concurrently
  across backends/worktrees, bounded by budget and the fence; serialize only true
  dependencies.
- **PERF-5 — handoff is bounded.** Exhaustion → snapshot → re-dispatch must be O(1)
  in checkpoints, not O(history). Checkpoint granularity is the tuning knob
  (Prediction 1).
- **PERF-6 — prefer programmatic ACP over interactive panes.** No `tmux send-keys`
  in the critical path; stdio JSON-RPC only.

---

## 6. Control-plane fence & autonomy ladder

Same as prior draft. Privileged actions default-deny; operator sets the level;
worktree-per-backend bounds blast radius. L0 propose-only · L1 apply reversible ·
L2 apply with consensus · L3 full-auto within fence.

---

## 7. Build vs. integrate (revised posture)

> **Amended by ADR-0005 (2026-06-26).** The "INTEGRATE routing/fallback" row below is
> superseded for the primary product: Charon now **builds** the gateway/failover plane
> (`proxy_server.py` + in-request failover) rather than depending on an external
> OpenAI-compatible gateway. ADR-0001's thin-core invariants — stdlib-only privileged
> core, gateway imports no coordinator, observe-don't-relay on the *orchestrator* path —
> are preserved (see ADR-0005 R3). PERF-1 ("never a proxy in the token stream") now
> scopes to the orchestrator hot path only; gateway mode is a proxy by design.

| Concern        | Decision     | Basis |
|----------------|--------------|-------|
| Coordinator loop | **BUILD** (thin) | the glue; nobody owns it |
| Work Ledger      | **BUILD**        | the gap |
| Cross-vendor handoff | **BUILD**    | the gap; ACP doesn't cross vendors |
| Fence / autonomy ladder | **BUILD** (thin) | trust boundary |
| Execution        | **INTEGRATE** (ACP client; Hermes pattern) | standardized |
| Routing/fallback | **INTEGRATE** (OpenAI-compat gateway) | standardized, commodity |
| Consensus reviewer | **INTEGRATE** (existing cross-model review) | exists |
| Model APIs       | **INTEGRATE** (via gateway) | commodity |

Net new code target: the coordinator + Ledger + handoff + fence. Single-digit-
thousands LOC, not a framework.

---

## 8. Alternatives considered

- **Hermes generalized ACP client, adopted wholesale as the orchestrator.**
  Strong candidate for the *execution* layer (it is exactly a one-client-many-
  agents ACP driver) — integrate or vendor it. Rejected as the *whole* harness:
  it doesn't provide the vendor-neutral Ledger or the cross-backend handoff
  contract. Use it under the port, don't reimplement it.
- **oh-my-claudecode / oh-my-pi / native Agent Teams.** Single-ecosystem
  orchestration; no cross-vendor handoff; supply-chain/solo-maintainer surface for
  a privileged loop. Reference, not dependency.
- **Pure gateway (OpenRouter/neuralwatt) alone.** Solves routing/fallback; no
  task continuity, no consensus gate. One plane, not the system — but it *is* the
  routing plane, which is why the harness doesn't rebuild it.
- **Build bespoke per-tool adapters.** Rejected: that's the per-pair integration
  cost ACP exists to delete (and the thing the operator has no time for).

---

## 9. Tiered plan

- **Tier 0 — Backend-support matrix (verification).** Confirm ACP availability,
  usage-reporting, and resume/fork for each intended backend; pin a gateway with
  clean OpenAI-compat. Blocks H3/H4 assumptions.
- **Tier 1 — ACP client + Ledger, single backend.** Coordinator drives one ACP
  agent; Work Ledger + executable-acceptance + L0/L1 fence. Mode-A standalone.
- **Tier 2 — Gateway routing + handoff, second backend.** Routing/fallback via
  gateway; light up H4/H6 cross-vendor handoff.
- **Tier 3 — Consensus gate.** Wire an existing cross-model reviewer behind the
  gate predicate + circuit breaker.
- **Tier 4 — Autonomy L2/L3 + parallelism (PERF-4).** Unattended within the fence.

---

## 10. Open questions

- Per-backend ACP capability/usage fidelity (Tier 0) — drives H4 truthfulness.
- Which gateway as default (OpenRouter vs neuralwatt vs both) — supply-chain vet
  before it enters the privileged loop.
- Executable-acceptance format — blocks H3/INV-6; first artifact Tier 1 needs.
- Whether to vendor the Hermes ACP client or depend on it (INV-B3 in ADR-0002
  says pinned dependency, not vendored — confirm it's consumable that way).
