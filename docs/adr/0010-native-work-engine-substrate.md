# ADR-0010 — Native work-engine substrate (promote the engine in-tree)

Status: **Proposed** (2026-06-26). **Amends ADR-0007 D10** for the coordination
substrate. Builds on ADR-0006 (PERF-4: `run_parallel`/ledger/SharedBudget), ADR-0007
(safe-landing-first; `land.py`), ADR-0008 (intake→ticket-plan). Honors ADR-0005 R3 /
ADR-0007 D11 (anti-dilution: never touch the gateway request path or install footprint).

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
The `charon-private/fleet/` bash rig (board/claim/done/fleet-droid) is the **proven
reference implementation**, not the product. Port its design native over PERF-4's
existing ledger/PID-lock/SharedBudget primitives. The rig stays as a sibling/operator tool
([[droid-robot-mode-harness]]); it is not the engine of record.

### D2 — Components (all new modules, gateway path untouched — D11)
- `engine/board.py` — a durable, file-backed work backlog (tickets: id, tier, owns,
  depends_on, state). One Charon-owned schema; diffable/auditable artifact (ADR-0008 §6).
- `engine/claim.py` — **atomic claim/lease** with a PID/heartbeat liveness check and lease
  expiry (generalizes the ledger PID-lock to N independent workers); release on
  crash/timeout for retry. This is the D10 item-1 substrate, built because the operator
  owns the decision — tripwire becomes *sequencing*, not a gate.
- `ports/worker.py` — a **`WorkerBackend` port** (D10 item-2): `dispatch`, `poll`,
  `kill`, `liveness`. Adapters: in-process ACP (exists), **headless-CLI** (`claude -p` /
  droid), and a mock. Lets a worker that a blocking `dispatch()` can't drive participate.
- `engine/scheduler.py` — spawn-to-demand assignment over the board honoring
  `depends_on` waves + disjoint-`owns` (the `coordinator.py` collision rule, mechanized),
  bounded by SharedBudget + the fence.

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
  dead code? Partially possible, but the operator's need is **cross-vendor, gateway-routed
  workers with a Charon-owned auditable backlog** — not a single-vendor feature. Build the
  port thin so a platform primitive can sit *under* `WorkerBackend` if it arrives.
- **Performance/security of auto-land:** unchanged risk posture — D3 keeps propose-default;
  D4 keeps scanners advisory until measured + auto-land-on. Substrate adds concurrency, not
  new trust.

Reconcile in REVIEW-LOG before code (house rule).

## Build sequence (waves; fleet-built, file-disjoint)
1. `ports/worker.py` + headless-CLI adapter + mock (the abstraction first).
2. `engine/board.py` + `engine/claim.py` (durable backlog + atomic lease/liveness).
3. `engine/scheduler.py` (spawn-to-demand over board, waves + disjoint-owns + budget).
4. Scanner matrix per D4 — Tier A/B wired into `land.py` as **advisory**, change-scoped,
   parallel, cached; benchmark harness to measure wall-time (gates "required" status).
5. ADR-0008 Phase 1 (human-reviewed intake→plan front door) — parallelizable anytime;
   captures the top-level acceptance that `validate.py` (D12) currently stubs.
Then behind their gates: D5 auto-land + scanner-required; Phase 2 autonomous; AIMD.
