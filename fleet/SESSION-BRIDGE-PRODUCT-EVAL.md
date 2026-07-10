# Session-Bridge → Product Feature? — Evaluation

**Date:** 2026-07-04 · **Verdict: PARTIAL** (extract the primitive via `obol`; keep the raw bridge internal)

## What the session-bridge is (confirmed)
- `proxy.py` (~260 lines incl. tool schemas): thin stdio JSON-RPC forwarder → Unix socket
  `BRIDGE_SOCKET` (default `/tmp/charon-bridge.sock`). No secrets, no logic.
- `daemon.py` (24 KB): single asyncio process, sole SQLite writer at `~/.charon/session-bridge.db`.
- Tools: `register/board/update/unregister/claim/release/nudge`. NO auth.
- Model = N **independent, human-attended, LLM-driven opencode sessions** (Jedi-named droids in
  tmux tabs) that register, see a shared board, atomically claim tickets, and message each other
  (typed nudges: review-request/verdict, scope-proposal, handoff, …).

## Findings tied to the product boundary

1. **Two hard leaks in the raw code.** `register`/`board`/`claim` hardcode a **repo enum
   `"charon"|"mediastack"`** — a direct SLOP leak into what would be product code. Paths are
   `/tmp/charon-bridge.sock` and `~/.charon/…`, `/home/stack`-flavored. Ships as-is = boundary
   violation.

2. **The SESSION model is the build-rig worker model, which the product explicitly rejects.**
   ADR-0010's DTC correction states the product's engine workers are **warm ACP agents driven by
   `AgentBackend`/`coordinator.run` — never `claude -p`/opencode droids.** The bridge coordinates
   exactly the droid sessions ADR-0010 says are *not* the product worker model. It is the plumbing
   for how we BUILD Charon, not a product capability.

3. **The product already has the coordination substrate in-tree.** `src/charon/engine/board.py`
   (294), `claim.py` (285, epoch-fenced), `scheduler.py` (455) — shipped per ADR-0010 D1/D2 over
   PERF-4's ledger/PID-lock primitives. Board/atomic-claim/derived-readiness/disjoint-owns already
   exist natively. Promoting the raw bridge would be a **second, contradictory** coordination
   architecture — the exact anti-pattern ADR-0007's review flagged.

4. **`obol` already claims this ground.** PLAN-PORTABLE-ORCHESTRATION-STORE (ADR-0008 Phase 1)
   names BRIDGE-DAEMON-PROPOSAL as "the session-messaging daemon this store **subsumes/extends**,"
   and its §0 is a stdlib-only, zero-leak, per-project, XDG-pathed, no-repo-column redesign. The
   raw bridge is a **working prototype of obol**, not an independent product candidate. (obol v1
   was DTC-REJECTed; v2 in progress, design-only.)

5. **Security: not shippable as-is.** No auth, world-known socket + DB paths, board exposes ticket
   ids/blockers/messages. Public-shippable needs: AF_UNIX 0600 local-only (no network default);
   the Windows AF_INET-loopback path needs a per-daemon token (obol open-decision #5); per-project
   isolation (obol: one daemon/project, no cross-tenant column); typed payloads only, no prompts/
   secrets on the board; size caps.

## Verdict rationale
- **KEEP-INTERNAL** the raw session-bridge: SLOP/home leaks, no security, and a worker model the
  product explicitly disowns. It stays the build-rig coordination plane (and obol's reference).
- **PRODUCTIZE the *primitive*, not the bridge** — poll-don't-push typed inbox + atomic
  epoch-fenced claim + derived readiness + quorum review — via the **already-chosen vehicles**:
  the in-tree engine (ADR-0010, shipped) and `obol` (ADR-0008 Phase-1, stdlib, opt-in, config-driven).
  No new track; the bridge's *design lessons* graduate, its *code* does not.

## What "productize via obol" takes (already scoped in the plan)
Finish obol v2 DTC (7 blockers/3 rulings resolved on paper), strip the repo enum, config-drive all
paths, add the Windows-transport token, land the hermetic test suite as the CI gate. All design-only
today; gated behind ADR-0007 D10 tripwires for the autonomous parts.
