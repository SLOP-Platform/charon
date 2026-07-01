## Verdict

The optimized backlog plan is mostly sound, but one baked-in assumption does not hold as written: `OBS-CAPTURE` cannot reliably derive a **per-unit** `.charon/<id>/agent.log` path from `acp._start(worktree, env)` alone across the current runners.

## 1. Owns-Disjointness

- Confirmed for the optimized buildable wave set.
- `OBS-CAPTURE` owns `src/charon/adapters/acp.py`, `src/charon/ports/backend.py`, `src/charon/adapters/mock.py`, `src/charon/coordinator.py`, `src/charon/decompose.py` (expanded per operator decision §Option 2 below).
- `OBS-UI` owns `src/charon/proxy_server.py` and `src/charon/console_work.py`.
- `CLIENT-CONNECT-GUI` owns `src/charon/connect.py`.
- `ORCH-ROUTE` owns `src/charon/api.py` and `src/charon/ports/agent_launch.py`.
- `WCI` owns `src/charon/engine/{reconcile,scheduler,board}.py`.
- `ADR-0015`, `DSGN-WCI-PROOF`, `OHMYPI-ASSESS`, and `ATC` own no product `src/` files.

Evidence checked: the parked boards under `<workspace>/<private-rig-repo>/fleet/board/*.md.parked` match the collision matrix in `<workspace>/<private-rig-repo>/fleet/OPTIMIZATION-PASS.md`.

Deferred backlog overlaps still exist, but they are outside the optimized concurrent wave set and are already intentionally unscheduled:

- `CLIENT-CONNECT-GUI` and `CONNECT-OMP-WSL` both own `src/charon/connect.py`.
- `SETUP-KEY-UX`, `UX-POLISH`, and `TIER-RECS` all touch `src/charon/cli.py`.

## 2. depends_on Edges

- Confirmed: `WCI <- ADR-0015` is a real build/correctness dependency, not a merge-order-only edge. `WCI` explicitly builds against the signed ADR.
- Confirmed: `WCI-FOLLOWON` correctly carries `depends_on: WCI` and separately documents the `DSGN-WCI-PROOF` sign-off gate in `real-dep:`. That is the minimal correct encoding given `DSGN-WCI-PROOF` is a design pass, not a build done-marker.
- Confirmed: `ATC <- all build work` is justified. It audits merged code and must run last.
- No missing hard build dependency was found among `OBS-CAPTURE`, `OBS-UI`, `CLIENT-CONNECT-GUI`, or `ORCH-ROUTE`.

## 3. Wave Ordering

- Wave 1 remains the right maximal-concurrency set for the optimized tickets.
- Wave 2 = `WCI` after `ADR-0015` is correct.
- Wave 3 = `WCI-FOLLOWON` after `WCI` plus approved `DSGN-WCI-PROOF` is correct.
- Wave 4 = `ATC` last is correct.

No unjustified serialization was found inside the optimized wave plan.

## 4. Baked-In Assumptions

### A. `OBS-CAPTURE` log-path derivation from `worktree`

Refuted as currently written.

What the source actually shows:

- `src/charon/adapters/acp.py:88` defines `AcpBackend._start(self, worktree, env)` and only receives the repo worktree path plus env.
- Per-unit state is created elsewhere:
  - `src/charon/api.py:73-108` builds worktrees under `<state_dir>/work/<task_id>/repo` or `<state_dir>/sandbox/<task_id>/repo`.
  - `src/charon/engine/scheduler.py:269-290` builds scheduler worktrees under `<state_dir>/sandbox/<id>/a<attempt>/repo`.
  - `src/charon/ledger.py:135-152` creates the durable unit state under `<state_dir>/<task_id>`.

That means there is no single stable contract today that lets `acp.py` recover the durable per-unit ledger dir from `worktree` alone across both code paths. The prompt currently says both:

- build a per-unit log under `.charon/<id>/agent.log`, and
- avoid threading a new seam by deriving it from `worktree` only.

Those two claims do not line up with the current source.

Operator call needed:

- Option 1: narrow `OBS-CAPTURE` to a repo-local log path derivable from `worktree` alone.
- Option 2: keep the per-unit durable log requirement, but add an explicit state-dir/log-path seam, which may require re-sequencing if it touches `engine/scheduler.py`.

I did **not** auto-edit the ticket metadata because the correct fix is a scope decision, not a wording-only cleanup.

### B. `ORCH-ROUTE` Step 0

Confirmed as a reasonable in-ticket gate, not obviously a separate spike.

Evidence checked:

- `src/charon/ports/agent_launch.py:104-120` already centralizes the `OPENCODE_CONFIG_CONTENT` injection path.
- `tests/test_agent_launch_routing.py` and `tests/test_run_task_routing.py` prove Charon's side of that seam and its stub-agent behavior.

The remaining unknown is specifically live `opencode acp` behavior, and the prompt already says to stop and report if Step 0 fails. That is a sound verify-then-build framing.

### C. `OBS-UI` off the hot path

Confirmed achievable without touching the per-request gateway forwarding path.

Evidence checked:

- `src/charon/proxy_server.py:402-418` already handles local GET console/status routes before request forwarding.
- The request-forwarding path starts later at `src/charon/proxy_server.py:466`.

So a read-only work panel can be added as another console/status-style route and keep the hot path unchanged.

## 5. D&S Completeness

Confirmed for the optimized tickets reviewed here:

- `ADR-0015`
- `DSGN-WCI-PROOF`
- `OBS-CAPTURE`
- `OBS-UI`
- `CLIENT-CONNECT-GUI`
- `ORCH-ROUTE`
- `OHMYPI-ASSESS`
- `WCI`
- `WCI-FOLLOWON`
- `ATC`

Each has a `## Dependencies & sequence` section in its prompt, and the section content matches the current intended wave structure.

## Result

The backlog plan should be treated as **sound except for the `OBS-CAPTURE` scope assumption**. That ticket needs an operator decision before the optimized plan can honestly keep claiming "derive the per-unit log path from the worktree".

---

## Operator decision (2026-06-28)

**Chose Option 2 (state_dir seam).** OBS-CAPTURE's board, prompt, and the OPTIMIZATION-PASS collision matrix have been updated accordingly. Summary of changes:

| File | Change |
|---|---|
| `board/OBS-CAPTURE.md.parked` | `owns:` expanded to 5 source + 1 test file |
| `prompts/obs-capture.md` | Scope rewritten to describe the state_dir seam (5 files, ~5 lines each) |
| `OPTIMIZATION-PASS.md` | Collision matrix + verdict text updated |

The plan is now internally consistent. No collision with WCI; the scheduler path is not touched.
