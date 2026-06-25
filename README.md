# Charon

**A thin orchestrator that ferries one unit of work across swappable
coding-agent backends, keeping a single vendor-neutral Work Ledger as the source
of truth.**

Charon drives existing CLI coding agents (Claude Code, Codex, Gemini CLI, … via
the [Agent Client Protocol](https://agentclientprotocol.com)) as interchangeable
execution backends. It owns only what nothing else owns: a **Work Ledger**,
**cross-vendor handoff**, and a **control-plane fence** with a graded autonomy
ladder. Routing and review are integrations, not rebuilds.

> Named for the ferryman who carries across the boundary — which is exactly what
> the novel part does: ferry a task from an exhausted backend to the next one.

## ⚠️ Honest disclosure — read before installing

Charon is a **control plane**. At autonomy ≥ L1 it spawns CLI coding agents and
can apply their diffs **unattended**. Treat it accordingly:

- The **default autonomy is L0 (propose-only)** — nothing is applied.
- Per-backend **OS-level isolation is the container (Mode B)**, not the in-process
  fence. The fence hardens the subprocess env and *detects* worktree escapes, but
  a determined local agent process is only truly bounded by the container. **Do
  not run unattended (L2/L3) outside the container on a machine you care about.**
- **Scope:** Charon runs goals with **executable acceptance** (a command that
  exits 0 == done). Prose-only goals ("make it nicer") are out of scope by
  design — `remaining` must be machine-decidable.
- **Sunset clause:** this is a tactical bridge. As frontier agents grow native
  cross-vendor continuity, Charon's coordinator becomes removable — and your
  Work Ledger is just git + JSON, so it outlives Charon.

## Install (Mode A — standalone)

```bash
# isolated, on PATH (recommended)
pipx install git+https://gitlab.com/slop-platform/charon

# or for development
git clone https://gitlab.com/slop-platform/charon && cd charon
pip install -e '.[dev]'
```

## Quickstart

```bash
# Run a goal against a built-in mock backend, in an auto-created sandbox repo.
# (proves the loop with no live agent; nothing applied at the default L0)
charon run --goal "create hello" --accept "test -f hello.txt" --backend mock --autonomy L1

# Inspect the derived ledger state (verified / remaining are re-derived from disk)
charon ledger <task-id>

# Tier-0: probe a REAL ACP agent for usage/resume fidelity before trusting it
charon doctor --backend-cmd "claude-code acp"
```

## What it builds vs. integrates

| Concern | Charon | Why |
|---|---|---|
| Coordinator loop | **build** (thin) | the glue nobody owns |
| Work Ledger | **build** | the gap |
| Cross-vendor handoff | **build** | ACP doesn't cross vendors |
| Fence / autonomy ladder | **build** (thin) | trust boundary |
| Execution | **integrate** (ACP client) | standardized |
| Routing/fallback | **integrate** (OpenAI-compat gateway, Tier 2+) | commodity |
| Consensus reviewer | **integrate** (cross-model review, Tier 3) | exists |

## Architecture

```
CLI / Python API / HTTP service   ← the three stable public surfaces
            │
   Coordinator (loop authority)
   ├── Work Ledger  (ONE per task — sole progress truth; INV-1)
   ├── Fence + autonomy ladder (L0–L3, default-deny)
   ├── Router (static policy in Tier 1; gateway in Tier 2+)
   └── AgentBackend port ── MockBackend (proof) · AcpBackend (real, stdio/NDJSON)
```

See [`docs/adr/`](docs/adr/) for the decisions (ADR-0001 architecture, ADR-0002
project boundary, ADR-0003 plane detail) and [`docs/REVIEW-LOG.md`](docs/REVIEW-LOG.md)
for the adversarial review of the build plan and its reconciliation.

## Status

**Tier 1:** standalone repo, CLI, CI, the continuity core (Ledger, fence, ports),
proven end-to-end on the mock backend; real ACP adapter shipped to-spec (validate
with `charon doctor`).

**Tier 2a** (this release): **multi-backend cross-vendor handoff**, proven
end-to-end across two mock vendors — exhaustion (H4) routes to a *different*
backend (H6), which rehydrates `remaining` from the ledger+disk alone (H3) and
finishes without replaying committed work (H5). The proof is deliberately
adversarial, not a happy path: a **lying** backend's forged "done" claim does not
survive the vendor boundary, and `lkg` never advances past an unverified commit
(INV-2). Routing stays a static native policy; the network gateway is gated on
[`docs/SUPPLY-CHAIN.md`](docs/SUPPLY-CHAIN.md) before it may enter the privileged
loop. The Mode-B container is built and health-checked in CI.

**Honest scope of the handoff proof:** what is proven is the *vendor-agnostic
contract* (the portable unit is files+ledger, not a vendor session). **Live**
ACP-to-ACP handoff needs two real ACP agents (not in this env) and stays gated
behind `charon doctor`.

**Tier 2b:** GHCR image-publish path (release-triggered, gated on tests, base
digest-pinned at release, SLSA provenance) + the web surface made honestly
read-only (it returns `501` rather than running the privileged loop in-process —
ADR-0002 §2.3). The live `POST /v1/runs` web/worker split is the recorded design
of record, built *with* its Tier-3 SLOP consumer (see
[`docs/PLAN-tier2.md`](docs/PLAN-tier2.md) §8).

**Web Ledger dashboard (read-only).** A minimal, single-operator web view of the
Work Ledger — project/run list, a run view (progress/cost/handoffs/checkpoints),
and a routing-config pane. Run it:

```
pip install 'charon[service]'
CHARON_SERVICE_TOKEN=$(openssl rand -hex 16) python -m charon.service   # http://127.0.0.1:8001
```

It is **read-only** (no run launch — `POST /v1/runs` is `501` by design),
**token-gated** (`CHARON_SERVICE_TOKEN`; the entrypoint refuses a non-loopback
bind without one), and serves **self-contained HTML with no external assets**
(zero egress). The container is the security boundary (INV-B4); for a VPS, front
it with a reverse proxy + HTTPS. Watch-the-agent-work (live diffs/stream) stays
CLI/TUI by design (ADR-0004 D7).

**Tier 3** (this release): **Ledger-native cost & budget accounting.** Each
checkpoint records a usage span (`tokens_in/out`, `cost_usd`, `latency_ms`);
cumulative spend is **derived** from the ledger (like progress), so it survives a
cross-vendor handoff and a reload without resetting (H3-for-cost). A
`--max-cost-usd` / `--max-tokens` cap stops a run *before* exceeding it — "always
working" never means "unbounded cost." Live token/cost come from real ACP
`session/usage` (gated on `charon doctor`); the mock proves the accounting
contract. *(Re-scoped from a consensus gate after adversarial review found the
gate's only consumer is L2 — built in Tier 4 with it; see
[`docs/REVIEW-LOG.md`](docs/REVIEW-LOG.md).)*

**Tier 4** (this release): autonomy **L2 (apply-with-consensus)** + the consensus
gate. At L2 a completed unit is applied only if a configured reviewer passes; a
**block, an error, or no reviewer all fail _closed_** (`blocked-consensus`, lkg
unchanged). L1 never consults the reviewer (unchanged); **L3** (full-auto) applies
regardless but records the verdict. **L2+ is refused outside the Mode-B
container** (`Fence.assert_environment` — set `CHARON_CONTAINER_VERIFIED=1` inside
it, or opt out loudly), enforcing ADR-0002 §2.3 in code, not just docs.

> **Consensus is _not_ a security boundary.** The reviewer is an automated check
> (an LLM, behind the gateway) that can be wrong or gamed. L2 consensus is
> *additive quality insurance* on top of executable acceptance — not a human
> review and not a security audit. For security-sensitive code, require human
> review outside Charon.

**Parallel independent units (PERF-4) are deferred** — adversarial review found
the thin design unsafe as drafted (escape-scan races on shared worktree parents,
a shared-budget overspend race, sticky backend subprocess state) and no consumer
needs the throughput yet. The binding fixes for when it is built are recorded in
[`docs/PLAN-tier4.md`](docs/PLAN-tier4.md) §6. The live web/worker service + GHCR
publish-on-tag land with the Tier-3 SLOP adapter (SLOP-side).

To configure multiple vendors from the CLI:

```bash
charon run --goal "..." --accept "test -f ok.txt" --backend mock-a,mock-b --autonomy L1
```

## License

MIT.
