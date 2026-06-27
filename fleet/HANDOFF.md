# Charon — Session Handoff (2026-06-27)

Resume doc for a fresh MANAGER session. Read this + `MEMORY.md` + `WORKFLOW.md` +
`docs/DECISIONS.md` first, then run `status.sh` / `board.sh` / `validate_board.sh`.

## BUILD STATE — native work-engine COMPLETE
- **Board is 100%** (22/22 tickets DONE): E0–E10, N1/N2/N4/N5, S1, T7/T8, FB1/FB3/FB4/FB5/FB6.
- The ADR-0010 native work-engine is built end-to-end: board+claim+scheduler+capacity, intake
  phases 1&2, scanner matrix, auto-land, engine integration, docs.
- Master is green; CI gate + the new `wheel-smoke` job pass.

## NEW THIS SESSION — doctrine + tooling (all in `charon-private/fleet/`)
- **Self-feeding launcher:** `fleet-droid.sh <tier> --wait <min> --retries <n> --patience <cycles>`.
  Open the pool once; idle tabs sleep and grab the next ticket on each merge; `--patience` makes a
  higher tier hold off poaching lower-tier work for N wait-cycles; drains to a clean exit.
- **Push-path FIX (critical):** the LAUNCHER now pushes + opens the PR + submits (plain shell,
  after the droid exits). The droid just commits + STOPs. (Root cause: closing the `git -C push`
  deny gap removed the droids' only push route — `--dangerously-skip-permissions` does NOT bypass
  `deny`. Deny-list stays closed; launcher push isn't a Claude tool call so it's exempt.)
- **Phantom-PR guard:** `submit.sh` verifies a real open PR before marking submitted; else flags
  `state/needs-push/<id>` (shown as `NEEDS-PUSH`). Recovery: `land-needs-push.sh <id>`.
- **AUTONOMOUS push lever:** `autonomous.sh on|off|status` toggles whether the manager may push
  (via the gated `land-push.sh`). OFF (default) = manager asks the operator to push. Closes the
  `git -C * push*` bypass too. (Allow-rule loads at session start — first push of a session may
  prompt once.)
- **Rig hardening (from the fragility audit, `AUDIT-2026-06-27.md`):** `validate_board.sh` now
  fails RED on real collisions (transitive-dep + done-aware) + orphan-marker check; `_lib.sh` has
  shared `canon`/`deps_done` (case-safe ids, multi-dep); `reject.sh` (un-submit inverse);
  `done.sh` refuses unless a MERGED PR exists; per-ticket review-log **fragments**
  (`docs/review-log/<id>.md`); the rollup `docs/REVIEW-LOG.md` is generated + git-ignored.

## DOCTRINE (in `WORKFLOW.md` + memory)
- Manager **gate-only**: gates+merges autonomously on green; never launches fleet build-droids.
- Manager **MAY spawn read-only reviewers**; on red/contested PRs auto-runs an adversarial review
  → presents verdict + raw facts → operator accepts / rejects / DTCs.
- Manager **delegates its own substantive work to sub-sessions** (keep the primary thread for
  comms + decisions); owns/reviews the result.
- Manager **never pushes by hand** — only via `land-push.sh` + the AUTONOMOUS lever.

## OPEN WORK (tracked task list)
- **TIER-1..7** (created) — model-tier abstraction, per `DTC-tier-abstraction.md` (canonical
  `low/med/high`, `opus/sonnet/haiku` as aliases, `tiers.json`, **operator wires models→tiers on
  the web page**, gateway pools). **DTC APPROVED by the operator 2026-06-27 — cleared to build;
  launch TIER-1 (wave A) when ready.** Waves: A={TIER-1} · B={TIER-2,TIER-3} · C={TIER-4,5,6,7}.
  NOTE the product/rig split: TIER-1/2/3/4/7 ship (product); TIER-5/6 are local fleet only.
- **#3** polish review: `rules.json`+`check_rules.py` and `done.sh` recording PR#+SHA (check
  still-relevant/no-conflict, then build) — SLOP→Charon adoptions.
- **#4** preflight: `pipx install .` / `charon --help` / setup smoke before the dogfood.
- **#5** scope the **tracking.db ↔ Charon intake adapter** (design note → ticket) — the dogfood
  needs it (SLOP tickets live in `mediastack/tracking/tracking.db`, 31 open, via `query.py`).
- **#6** revisit D005 (WorkerBackend port) + D015 (verified isolation) relevance.
- **#8** secret-scan helper: match CONTENT signatures, not filenames (the `test-keys.md` false
  alarm).
- **#11** minor: make the launcher enforce `diff⊆owns` pre-push (droid self-check went advisory;
  manager gate is the backstop).

## KEY DOCS
- `WORKFLOW.md` (the gate/lifecycle), `CONSOLIDATION-PLAN.md` (SLOP robot-mode upgrade +
  Charon↔SLOP cross-pollination), `AUDIT-2026-06-27.md` (fragility audit), `DTC-tier-abstraction.md`
  (tier design + tickets), `DTC-backchannel.md`.

## THE BIG GOAL — the dogfood
Fresh-install Charon → `charon setup` (operator, interactive) → verify the gateway → **point it at
the SLOP outstanding tickets** (`/home/stack/code/mediastack/tracking/tracking.db`) → test the
process → tweak. SLOP = the mediastack repo; its code/gates are GREEN, its robot-mode harness is
wedged (see `CONSOLIDATION-PLAN.md` Phase 0/1). Expect the first gap = the tracking.db→intake
adapter (#5).

## FIRST ACTS (fresh session)
1. Read `MEMORY.md` + this + `WORKFLOW.md` + `docs/DECISIONS.md`.
2. `status.sh` · `board.sh` · `validate_board.sh` (expect GREEN, board all DONE).
3. Confirm the push-path fix is live (a test droid commits → launcher publishes a PR). The fleet is
   autonomous-ready; `autonomous.sh on` for full hands-off.
4. **Run a blast-radius dependency audit of Charon-the-PRODUCT** (task #12): does anything in
   `src/charon/` assume the home build-rig / SLOP / `tracking.db` / `ms-*` / the self-hosted
   runner? Charon must `pipx install` + run on a stranger's box with none of it. Flag the
   fork-runner gap (workflows pinned to `[self-hosted, 4-lom]`) and any local leak. See memory
   `product-vs-build-rig-boundary` + apply the `standing-blast-radius-lens`.
5. Pick the thread: launch **TIER-1** (DTC approved), **or** dogfood prep (#4 preflight → #5
   adapter, kept as a GENERAL intake not tracking.db-hardcoded), **or** the SLOP consolidation.
   Operator-driven.
