# Charon — Session Handoff (2026-06-27, late)

Resume doc for a fresh MANAGER session. Read `MEMORY.md` + this + `/home/stack/charon-private/fleet/WORKFLOW.md` +
`docs/DECISIONS.md` first, then run `status.sh` / `board.sh` / `validate_board.sh`.

## FIRST ACTS (fresh session)
1. Read `MEMORY.md` + this + `/home/stack/charon-private/fleet/WORKFLOW.md`.
2. `status.sh` — **check the live droid tabs** (see ACTIVE SESSIONS). `board.sh` · `validate_board.sh`.
3. Gate any PRs that have landed (see GATING). Merge on green per the bar below.
4. Surface the next decision to the operator; do not launch droids yourself (operator opens tabs).

## ACTIVE SESSIONS TO MONITOR  ← the main job right now
Two droid builds were in flight at handoff; **watch for their PRs and gate them:**
- **INTAKE1** (#13) — `opus-2682803` building `feat/intake-import`. The `charon intake import`
  command + enrichment + external-id preservation. owns `cli.py`, `intake.py`, their tests.
  **Gate at the ESCALATED bar** (2 independent adversarial reviewers — it's a substantial
  product feature). Boundary MUST stay clean (no SLOP in `src/`).
- **HARD1** — `sonnet-2651915` building `feat/run-task-routing-test`. A test-only ticket: the
  `run_task(role=…)` end-to-end routing guard test. owns ONLY `tests/test_run_task_routing.py`.
  Single adversarial reviewer is fine.
- `sonnet-2677744` — idle/polling; will stand down (no more sonnet-eligible work) or grab the
  next ready sonnet ticket. Idle = no model burn.
- When both land + merge, the active board is empty (TIER7B is parked — see below).

Recovery note: the launcher now **auto-commits** any work a droid leaves uncommitted before
publishing (fixes the FR1 data-loss path) — so a NEEDS-PUSH from "no commits" should be rare. If a
PR's first commit is `chore(<id>): launcher auto-commit…`, review it harder for half-done work.

## GATING (the bar)
- Droid PRs are **adversarial-by-default** (see memory `adversarial-review-default-for-droid-prs`).
  Downgrade to a light CI-green/diff-clean confirm ONLY for trivial one-liners / doc-only, and SAY
  so. HIGH-blast-radius (core gateway/engine) → 2-voter / multi-lens.
- Merge autonomously on green CI + clean review (AUTONOMOUS lever is ON). Fleet PRs open as DRAFTS:
  `gh pr ready <n>` then `gh pr merge <n> --merge`, then `bash done.sh <ID>`.
- Push is via `land-push.sh <branch> <worktree>` / `land-needs-push.sh <id>` (raw `git push` is
  deny-listed for the manager).

## BUILD STATE — what landed THIS session
- **TIER-7 Ticket A** (ADR-0014) — agent/provider-agnostic tier routing via the gateway. Merged
  (#50, 2-voter passed). The engine consumes the gateway's vid→pool→failover behind the
  `ports/agent_launch.py` opencode renderer seam. Register rows D017–D019.
- **FR1** — first-run UX polish (mock banner [honest exit kept], gateway 502 hint, doctor exit-0,
  README units example). Merged (#51).
- **DEP1** — declared `httpx` as a dev test-dep (it was ambient-only on the 4-lom box → clean
  installs / forks failed 3 service tests). Merged (#53).
- **CI1** — CI workflows now pick the runner via the `CI_RUNNER` repo variable (A-Clean); forks
  fall back to hosted. Merged (#52). Register row D020. **Operator set `CI_RUNNER` this session.**
- **Launcher hardening** — `fleet-droid.sh`: `--wait` is now the DEFAULT (bare droid self-feeds);
  auto-commit-leftover guard (above); both in the rig.
- Earlier this session: TIER-1..6 (model-tier abstraction), the pytest-pythonpath worktree fix.

## PARKED / DEFERRED (will NOT auto-build)
- **TIER7B** = `board/TIER7B.md.parked` (renamed off the active board so no idle opus tab claims
  it). It's TIER-7 **Phase B**: per-stage multi-tier routing (router selects backend by tier;
  warm-agent-per-tier) + delete the orphaned `failover.select_live_entry`. Operator-DEFERRED.
  **To activate:** `mv board/TIER7B.md.parked board/TIER7B.md`. NOTE (WCI lens): its
  `depends_on: HARD1` is really a MERGE-order, not a true build-dep (disjoint owns) — when you
  activate it, drop the dep and just merge HARD1 first at the gate so they can build concurrently.
  The prompt (`prompts/tier-phase-b.md`) already says "HARD1 green on master first."

## DESIGN QUEUE (manager design passes — NOT droid builds) → `DESIGN-QUEUE.md`
- **DSGN-WRITEBACK** — close-the-loop: report completed work back to the source tracker (gated
  general `TicketSink`; mark in-review + work trail; other agent/human closes). Sequence AFTER
  INTAKE1 (needs its external-id preservation).
- **DSGN-WCI** — work-composition intelligence (CORE feature; 3 pillars). A design + adversarial
  review were done; verdict **REWORK** — reshape per the captured findings before ticketing.
Run each as design→adversarial-review→ADR→build-tickets→operator sign-off.

## PENDING OPERATOR ACTIONS
- **Preflight:** run `charon setup` interactively once (the only non-auto first-run step) — surfaces
  any first-run gap before the dogfood.
- **Dogfood** (the big goal): after INTAKE1 lands → write the OUT-OF-TREE SLOP exporter
  (`tracking.db`/`query.py` → markdown or plan JSON; httpx-free) → `charon intake import` → enrich
  the imported tickets with `accept:`+`owns:` so they're runnable → run a few via `charon work
  --backend acp`. The intake adapter is the gate; routing/TIER-7 is NOT required (mock + acp run
  today). SLOP tickets live in `/home/stack/code/mediastack/tracking/tracking.db` (~31 open).

## KEY DOCTRINE (memories — all in `MEMORY.md`)
- Discuss-before-acting on operator questions; keep it SHORT and WAIT (don't bury asks in walls).
- Delegate substantive work to BACKGROUND sub-sessions; primary stays responsive (gate/merge/talk).
- Adversarial-by-default reviews; always give MY recommendation; peer-review very-impactful ones.
- Charon is modular: engine NOT hardcoded to any agent (opencode) or provider — gateway is neutral.
- Product ships standalone: never leak the rig/SLOP/runner into `src/`.
- Production-readiness north-star: a stranger's fresh `pipx install` must work.
- Always give the literal command; droid launches = `fleet-droid.sh <tier>` once + a one-line of
  what it picks up; wrap operator-run commands in `*****` lines.
