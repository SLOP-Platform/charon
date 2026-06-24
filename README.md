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
pipx install git+https://github.com/SLOP-Platform/charon

# or for development
git clone https://github.com/SLOP-Platform/charon && cd charon
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

**Tier 1** (this release): standalone repo, CLI, CI, the continuity core (Ledger,
fence, ports), proven end-to-end on the mock backend; real ACP adapter shipped
to-spec (validate with `charon doctor`). Cross-vendor handoff logic is built and
unit-tested; **live** cross-vendor handoff, the gateway, the consensus gate, and
L2/L3 unattended operation are Tier 2–4.

## License

MIT.
