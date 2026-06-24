# Charon — Tier 1 build plan (pre-review draft)

> Implements ADR-0001 (thin orchestrator), bounded by ADR-0002 (project
> boundary), keeping the Work Ledger / H-predicate / invariant spec from
> ADR-0003 (the renumbered "four-planes" ADR-NNNN). Name chosen: **Charon** —
> the ferryman who carries work across the boundary (cross-vendor handoff).

## 0. Scope contract (what "Tier 1 done" means)

Tier 1 = ADR-0001 §9 Tier 1 + ADR-0002 §5 Tier 1: **repo + standalone CLI + CI +
continuity core + one execution adapter behind the ACP-shaped port + L0/L1
fence.** Mode A (standalone) works end-to-end against a *mock* backend; the real
ACP adapter is implemented to spec but its live end-to-end is gated on a real ACP
agent being present (not guaranteed in this env — stated honestly, not faked).

Out of Tier 1 (scaffolded as ports/stubs, built later): real gateway routing
(Tier 2), cross-vendor handoff live test (Tier 2 — needs 2nd backend), consensus
plane (Tier 3), autonomy L2/L3 (Tier 4), HTTP service + GHCR image (ADR-0002
Tier 2).

## 1. Identity & boundary (ADR-0002)

- New repo `/home/user/code/charon`, `git init`, **MIT**, src-layout
  (`src/charon/`).
- Package `charon`; CLI command `charon`; version SoT = `pyproject.toml`,
  re-derived at runtime via `importlib.metadata.version("charon")` (no second
  copy of the version string).
- **Zero SLOP knowledge** (INV-B1/B5). CI boundary check greps the tree for
  `slop`/`mediastack` imports/references → fails the build if present.
- Three public surfaces (ADR-0002 §2.4): **CLI** (Tier 1), **Python API**
  (`charon.api`, Tier 1), **HTTP service** (`charon.service`, scaffolded Tier 1 /
  live Tier 2). Everything else private.

## 2. Architecture — ports & adapters (ADR-0001 §2, ADR-0003 §3)

Built (the gap only):
1. `coordinator.py` — loop authority: dispatch unit → observe checkpoint →
   evaluate acceptance → decide continue/handoff/stop.
2. `ledger.py` — Work Ledger, ONE per task; structured JSON + git refs.
3. `handoff.py` — H1–H6 predicates; rehydrate from `ledger + disk` only.
4. `fence.py` — autonomy ladder L0–L3; privileged ops default-deny.

Ports (`charon/ports/`):
- `AgentBackend` (ACP-shaped): `dispatch(unit, tier, budget, ledger_ref)→Outcome`,
  `health()→Health`, `capabilities()→CapSet`, `kill()`.
- `Router` (predictive, task-level): `route(unit, exclude=set())→(tier,backend,budget)`.
- `Reviewer` (consensus): `review(unit, outcome)→Findings` — port only in Tier 1.

Adapters (`charon/adapters/`):
- `MockBackend` — deterministic, drives the full loop in tests/demo with no live
  agent. The Tier-1 proof vehicle.
- `AcpBackend` — real ACP stdio/NDJSON JSON-RPC client (initialize / session.new /
  session.prompt / session.update notifications / session.cancel). Speaks the
  protocol; needs a real ACP agent binary to run live.

## 3. Executable acceptance (`acceptance.py`) — first artifact (ADR-0003 §12)

An acceptance criterion is an **executable check**: `{id, cmd, expect_exit:0}`.
`verified` = checks whose cmd exits 0 against current disk. `remaining =
acceptance \ verified`, **machine-derived** (INV-6) by running the checks. No
prose acceptance admitted (Prediction 2 mitigation). Checks run in the target
repo worktree.

## 4. Work Ledger format (`ledger.py`)

One dir per task: `<state>/ledger/<task-id>/ledger.json` holding `goal`,
`acceptance[]`, `checkpoints[]` (append-mostly), `provider_history[]`, `lkg_ref`.
Derived (never stored as truth): `done`, `verified`, `remaining`. `lkg_ref` is a
git SHA in the **target** repo; INV-2 forbids it advancing past an unverified
commit. The ledger is the sole progress truth (INV-1); backend sessions are
satellites.

## 5. Fence & autonomy ladder (`fence.py`)

`authorize(op, level)` default-deny. L0 propose-only (diffs written, never
applied) · L1 apply-reversible (commit in worktree, `lkg_ref` rollback, no
delete/deploy) · L2 apply-with-consensus (Tier 3) · L3 full-auto-within-fence
(Tier 4). Worktree-per-backend bounds blast radius; rollback is `git`-clean.

## 6. CLI surface (Tier 1)

- `charon init` — scaffold `.charon/` config in a target project.
- `charon run --goal G --accept "CMD" [--accept ...] [--backend mock|acp]
  [--autonomy L0|L1] [--budget N]` — create Ledger, run coordinator to acceptance
  or exhaustion.
- `charon ledger show <task-id>` — derived remaining/verified/lkg.
- `charon resume <task-id>` — rehydrate + continue (same-backend Tier 1).
- `charon version`.

## 7. Install / deploy — "best way locally" (ADR-0002 §2.3)

- **Mode A primary:** `pipx install git+https://github.com/SLOP-Platform/charon`
  (isolated, on PATH). `pip install -e .` for dev.
- `Makefile`: `make install` / `make test` / `make lint` / `make demo`.
- `install.sh` one-liner: ensure pipx present → pipx install. Honest about
  spawning CLI agents.
- `Dockerfile` + `docker-compose.yml` for Mode B service (scaffold; GHCR later).

## 8. CI from first commit (ADR-0002 §4)

GitHub Actions: ruff · mypy · pytest · version-consistency · **SLOP-import
boundary check** · Mode-A-in-isolation smoke (clean venv → `charon --help` +
`charon run --backend mock` demo). CI lands with the first commit, not later.

## 9. Tests (the proof, not the claim)

Prove against physics, each able to go red: H1 (incomplete ledger → not
handoff-eligible), H2 (no mid-trajectory handoff), H3 (idempotent rehydration:
two backends derive same `remaining`), H5 (committed work survives kill),
INV-1/2/5/6, fence default-deny (L0 refuses apply), acceptance derivation
(remaining shrinks as checks pass), mock end-to-end (`run` reaches acceptance),
boundary check (planted `import slop` → CI fails).

## 10. Docs

README (HONEST per ADR-0002 §4 — discloses autonomous privileged loop + agent
spawning), QUICKSTART, the three ADRs copied in (renumber ADR-NNNN → 0003; keep
0001/0002). WALK-BACK not applicable (new repo, additive).

## 11. Non-goals / honesty register

- No live ACP agent in this env → ACP adapter shipped + unit-tested at the
  framing level; live end-to-end is a Tier-1-follow-up, not claimed done.
- Router is a predictive **static default policy** in Tier 1 (port present);
  bandit/success-rate feedback is Tier 4.
- Consensus is a port + no-op pass-through in Tier 1; real cross-model review is
  Tier 3.
