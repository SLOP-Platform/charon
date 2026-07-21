# ADR-0010 — Native work-engine substrate (promote the engine in-tree)

> **SUPERSEDED (posture) by ADR-0017, 2026-07-19.** This ADR's "build the work-engine native NOW" posture is superseded: per ADR-0017 the engine is **deferred** (gateway MVP first), and when fleet-orchestration reaches the critical path the direction is to **adopt a commodity substrate (DBOS/Restate)**, not build native. The decisions below stand as the record of the native-substrate design; only the build-now / build-native posture is overtaken.

> **SUPERSEDED (D2 engine stdlib-only) 2026-07-21 by operator ADOPT-FIRST directive** —
> the D2 "engine stdlib-only / no third-party dependencies" rule is removed, and the gate
> that enforced it (`check_boundary.py` engine scan) is retired. A maintained runtime
> dependency is ALLOWED with no ADR required; adopt-first is the default, hand-rolling the
> last resort. Layer isolation (engine off the gateway path) is unaffected and still enforced.

Status: **Accepted** (2026-06-26; revised after a 4-lens DTC; engine substrate shipped); **posture superseded by ADR-0017** (engine deferred; adopt substrate when orchestration is on the critical path). **Amends ADR-0007 D10** for
the coordination substrate. Builds on ADR-0006 (PERF-4: `run_parallel`/ledger/SharedBudget),
ADR-0007 (safe-landing-first; `land.py`), ADR-0008 (intake→ticket-plan). Honors ADR-0005 R3 /
ADR-0007 D11 (anti-dilution: never touch the gateway request path or install footprint).

> **DTC correction (2026-06-26).** An earlier draft conflated the **dev-box build harness**
> (the `charon-private/fleet/` rig running `claude -p` droids — how we BUILD Charon here)
> with **Charon's product worker model**. They are different: **Charon's engine workers are
> ACP agents, never `claude -p`.** ACP agents are warm-poolable and blocking-drivable by the
> existing `AgentBackend`, so the engine is a **coordination layer over the existing
> execution substrate** — no new worker port, no per-unit process restart. The
> `WorkerBackend`/headless-CLI port (ADR-0007 D10-2) is therefore **deferred** (premature for
> an all-ACP product). We port the rig's *coordination* design, not its *worker* model.

## Context — a decision was diluted, now restored
The operator's settled vision ([[charon-vision-gateway-first]] "Vision EXTENSION") is that
Charon **is a work engine**: analyze → decompose → assign to multiple parallel workers,
"safely and much faster." The coordination substrate (assignment + atomic claim/lease +
worker liveness + safe result-landing + a worker-backend abstraction) is **core product
value to build NATIVE**, not external tooling.

ADR-0007's 3-lens adversarial review correctly tightened the *trust-extending* edges
(auto-land → propose-default; ephemeral → policy) but over-reached by folding the
**entire** engine — including the coordination substrate — into "deferred behind D10
tripwires." That inverted an operator decision and was recorded as settled. This ADR
restores it, while **keeping** the parts the review was right about gated.

The split this ADR draws:
- **Coordination substrate** = operator-owned, **build native, soon** (this ADR).
- **Trust-extending automation** (auto-land D5, scanner-as-required, autonomous decompose
  Phase 2) = review-owned, **stays gated** on data/measurement. The security case holds.

## Decisions

### D1 — Promote the substrate from the fleet rig to `src/charon`
The external bash dev harness (board / claim / done / worker-launch) is the **proven
reference implementation**, not the product. Port its design native over PERF-4's
existing ledger/PID-lock/SharedBudget primitives. That harness stays as a sibling
operator tool; it is not the engine of record.

### D2 — Components (all new modules under `engine/`, gateway path untouched — D11)
**Worker execution is NOT new.** Charon's product workers are **ACP agents**, which are
warm-poolable (reuse the subprocess + `session/new` + a fresh per-unit worktree, as
`AcpBackend` already does — ADR-0007 D7) and **blocking-drivable** by the existing
`AgentBackend` port + `parallel.py` ThreadPool. The engine is a **coordination layer over
that existing substrate** — it adds no worker port and no per-unit process restart.

- `engine/board.py` — a durable, file-backed work backlog (units: id, tier, owns,
  depends_on, state). One Charon-owned schema; diffable/auditable artifact (ADR-0008 §6).
- `engine/claim.py` — **atomic claim** as a thin generalization of `ledger.py`'s existing
  PID-liveness lock (CONC-4) to N units, plus a monotonic claim **epoch** as the
  double-execution fencing token (DTC Lens-4). Release on completion/crash; reclaim a
  stale claim only onto a *fresh* worktree. **Not** a second locking subsystem; **no**
  heartbeat / remote-lease in v1.
- `engine/scheduler.py` — assign claimed units to warm ACP workers honoring `depends_on`
  waves + disjoint-`owns` (the `coordinator.py` collision rule, mechanized), bounded by
  SharedBudget. **It drives each unit through the existing fenced `coordinator.run`**
  (`assert_environment` + `scrubbed_env` + escape-scan + lkg/rollback) — the scheduler is
  **never** a second, unfenced dispatch path (DTC Lens-2 R1). Liveness = ACP-deadline +
  checkpoint-kill (ADR-0007 D8); no process-group/zombie machinery.
- **Anti-dilution guard** (DTC Lens-3) — a transitive `sys.modules` import test (not AST)
  asserting `proxy_server`/`gateway`/`service.app` import nothing from `engine.*`, plus a
  stdlib-only scan over `engine/`. Built FIRST so the gateway boundary is locked before any
  engine code lands.

**Deferred (premature for an all-ACP product):** the `WorkerBackend` port + headless-CLI /
remote adapters (ADR-0007 D10-2). Their sole justification was "a worker a blocking
`dispatch()` can't drive" — the product has none (the `claude -p` fleet rig is dev-box
build tooling, not a product worker). Revisit only when a real non-ACP worker is needed.

### D3 — Result landing stays propose-default (unchanged)
Workers land through the existing `land.py` gate (diff-scope, sensitive-path hold,
acceptance/tests, gitleaks) and **open PRs; a human merges**. The substrate makes work
*concurrent*; it does not change *who merges*. Auto-land (ADR-0007 D5) stays gated.

### D4 — Intelligent scanner matrix (operator directive 2026-06-26)
The scanner matrix must be **lightweight and performant** — right tools, not all tools —
because under auto-land it becomes a blocking per-unit gate and kills parallel throughput.

**Tier A — fast, security-adjacent, always eligible:** `gitleaks` (secrets; already wired).

**Tier B — fast single-binary, run ONLY if the unit diff touches that domain:**
- `ruff` — Python; **already in the gate**, its `S` (bandit-derived) rules give Python
  SAST for zero new cost. Reuse.
- `shellcheck` — only if `*.sh` changed (C binary, sub-ms/file).
- `actionlint` — only if `.github/workflows/*` changed (Go single binary; workflow-
  injection detection).

**Tier C — heavy or marginal → gated or dropped:**
- `semgrep` — heavy (startup + rulesets; never `--config auto`). **Not default**; pinned
  minimal local ruleset, opt-in "deep scan" for sensitive-path/high-risk units only.
  ruff-`S` (+ optional bandit subset) covers Python at a fraction of the latency.
- `osv-scanner` — dependency CVEs. **Marginal for stdlib-only Charon** (no deps).
  Feature-flag ON only for consumer repos with a lockfile; OFF for Charon's own gate.
- license scanner — same (no deps → nothing to check). **Dropped from default**;
  feature-flag for dep-bearing repos.

**Performance contract:** (1) change-scoped — a scanner runs iff its file-domain is in the
diff; never blanket. (2) parallel, hard per-tool timeout. (3) content-hash cache —
unchanged files not re-scanned across retries/sibling units. (4) tiered enforcement —
advisory in propose-mode (heavy never blocks a human PR), required/fail-closed only under
auto-land. (5) **measured-before-required** (ADR-0007 D7 precedent) — a scanner earns
"required" only if catch-rate × signal beats its measured wall-time on representative
diffs; slow-and-low-yield tools are dropped, not carried "just in case."

### D5 — What stays gated (the review was right here)
- **Auto-land (D5/ADR-0007)** — extends trust to code whose provenance is the attack
  surface; human-in-loop until substrate + scanners prove out.
- **Autonomous decompose Phase 2 (ADR-0008)** — data-gated on PR-per-unit conflict rate.
  Phase 1 (human-reviewed plan) is unblocked and buildable in parallel.
- **AIMD adaptive capacity** — fixed conservative cap until a real run saturates a tier.

## Invariants preserved
ADR-0005 R3 / ADR-0007 D11 (engine never imports into or bloats the gateway path; core
stays stdlib-only; the engine is one opt-in consumer). ADR-0003 default-deny / L0-propose;
L2+ container-gated; fence escape-scan per unit. INV-1 one ledger per task. The container —
not env-munging — is the isolation boundary.

## Adversarial self-review (3-lens, before code)
- **Anti-dilution (D11):** does a native board/scheduler creep into the gateway? **No** —
  all new code under `engine/` + `ports/worker.py`; a boundary test (extend
  `test_boundary.py`) asserts the gateway server imports none of it, mirroring R3.
- **Absorbability:** will the platform ship native multi-session claiming and make this
  dead code? Partially possible, but the operator's need is **a Charon-owned auditable
  backlog assigning warm ACP-agent workers** — not a single-vendor feature. The substrate
  is `engine/`-local; if a platform primitive arrives it slots under the scheduler. (The
  `WorkerBackend` abstraction is deferred until a non-ACP worker exists — see D2.)
- **Performance/security of auto-land:** unchanged risk posture — D3 keeps propose-default;
  D4 keeps scanners advisory until measured + auto-land-on. Substrate adds concurrency, not
  new trust.

Reconcile in REVIEW-LOG before code (house rule).

## Build sequence (fleet-built, file-disjoint, depends_on-gated)
0. **Anti-dilution boundary guard** — extend `tools/check_boundary.py` + `tests/
   test_boundary.py` (transitive `sys.modules` test + stdlib-only scan over `engine/`).
   Lock the gateway boundary BEFORE any engine code. (no dep)
1. `engine/board.py` + `engine/claim.py` — durable backlog + atomic claim over the ledger
   lock + epoch fencing token. (dep: 0)
2. `engine/scheduler.py` — assign warm-ACP units over the board (waves + disjoint-owns +
   budget), driving each through fenced `coordinator.run`. (dep: 1)
3. Scanner matrix per D4 — Tier A/B wired into `land.py` as **advisory**, change-scoped,
   parallel, cached; benchmark harness measures wall-time (gates "required" status). (dep: 2)
4. ADR-0008 Phase 1 (human-reviewed intake→plan front door) — captures the top-level
   acceptance `validate.py` (D12) currently stubs. Independent of the substrate; gated
   after it per operator sequencing. (dep: 2)
Deferred behind their gates: `WorkerBackend` port (only if a non-ACP worker appears);
D5 auto-land + scanner-required; ADR-0008 Phase 2 autonomous; AIMD adaptive capacity.
