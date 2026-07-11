# HANDOFF — 2026-07-10 (session plo-koon) — Charon fleet MANAGER

## Bootstrap (paste as the next session's first message)
```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-plo-koon.md — you are the fresh Charon fleet MANAGER
```

## STATE — WHAT SHIPPED AND LANDED THIS SESSION

Everything below is **merged to master and pushed** (I pushed/merged via `land-push.sh` — the AUTONOMOUS lever is ON; see push protocol in GOTCHAS). No pending pushes/merges remain.

- **Fleet master `beef03e`** (Nnyan/charon-private):
  - **F22** — `done.sh` no longer aborts on archive-only tickets (`set -e`/`meta` fix) + fail-on-revert tests; closed the **4 P1 done-unmerged reds** (3 `--override` fleet-infra, TIER-SELECT `--merged-sha c4c4189`).
  - **F21 + F24** — fleet gate is now `fleet/gate.sh` (runs the fleet `*.test.sh` + ADVISORY shellcheck), not product pytest/ruff; benchmark excluded via root `conftest.py`. Gate GREEN (10 tests).
  - **F23 Phase 1** — session-end deploy harness (`fleet/deploy-session-end.sh`, advisory/tag-if-behind, no-hang timeouts) + tests; wired into `fleet/end-session.sh`. Live no-op smoke test green.
  - **Doctrine** — MANAGER-OPERATING-RULES §9 (token-economy is DEFAULT) + §8 (push is LEVER-GATED, not operator-only). Streamed **F25** (repo-decl-central) + **F26** (shellcheck-clean).
- **Product master `700a45d`** (SLOP-Platform/charon): **PR #94 merged** — S1/S2/S4 public-clean enforce; review artifact stripped (`45d8af7`) per convention.

## FIRST ACTIONS — NEXT (priority order)

0. Run `/home/stack/charon-private/fleet/preflight.sh`; register on the session-bridge under a NEW Jedi name.
1. `bash /home/stack/charon-private/fleet/report.sh` to confirm state (F20/F21/F22/F24 done, F23 building, F25/F26 designed). Nothing to merge — it all landed.
2. **STARTUP-CONTEXT-DIET (F28) — OPERATOR ASK, do early.** Audit everything a session ingests at boot + the work process; cut context/token cost (slim MANAGER-OPERATING-RULES, roll up old handoffs, tighten preflight, demote verbose memories to pointers), set a STARTUP BUDGET + a regression check. Rigor is NOT trimmed. Ticket: `fleet/board/STARTUP-CONTEXT-DIET.md`.
3. **WORK-CONVERGE-REVIEW (B7) — OPERATOR ASK, dedicated review session.** Compare how SLOP (mediastack) vs Charon (fleet rig) get work done; take best-of-both; design ONE MODULAR, PORTABLE "get-work-done" tool reusable across projects (engine vs project-specific config) so there is never >1 way. Feeds B5/B6. Ticket: `fleet/board/WORK-CONVERGE-REVIEW.md`.
4. **F23 Phase 2 (CD)** — CI builds a **git-describe** image (`vX.Y.Z-N-gSHA`) on every GREEN master push; extend `/home/stack/charon-private/fleet/deploy.sh` tag-guard to accept it; harness compares describe versions + deploys latest-if-behind; GHCR retention; gateway reports its running version. Spans the PUBLIC product repo → **PR to SLOP-Platform/charon** (keep deploy IP/host/keys in the rig, NEVER the product repo).
5. **B2 durable-bridge Phase 2 — NOW UNBLOCKED.** Roci SSH prereq ALREADY MET: `ssh rocinante` works (user stack, key `~/.ssh/mediastack`). Designs: `/home/stack/charon-private/fleet/DURABLE-BRIDGE-REVIEW-v2.md`, `/home/stack/charon-private/fleet/state/BRIDGE-ROBUSTNESS-INVESTIGATION.md`.
6. **F25** repo-decl-central, **F26** shellcheck-clean (rig-only, designed). Then remaining backlog per `report.sh`.

## GOTCHAS (avoid re-discovering / DENIED)

- **Push is LEVER-GATED, not operator-only.** Push via `/home/stack/charon-private/fleet/land-push.sh <branch> [repo]` (raw `git push` / `git -C … push` are deny-listed; `--force`/`--no-verify`/`reset --hard` FORBIDDEN). It self-gates on `state/AUTONOMOUS`: ON → push without asking; OFF → ask first + give the operator the command. CHECK the lever — do NOT reflexively hand pushes over (that wasted this session before the fix).
- **Roci SSH: use `ssh rocinante`** (aliased in `~/.ssh/config`: user stack, key mediastack) — NOT bare `ssh stack@10.0.1.51` (no key → denied). Rootless SSH was already set up.
- **Two repos**: PRODUCT `/home/stack/code/charon` (public SLOP-Platform/charon); FLEET `/home/stack/charon-private` (private Nnyan/charon-private). Rig tools must state WHICH repo they mean (root of a bug-class — F25).
- `done.sh`: done-merge gate checks the PRODUCT repo, so FLEET-infra tickets need `--override "<reason>"`. Archived tickets now close (F22).
- Fleet gate = `fleet/gate.sh` (fleet bash tests + ADVISORY shellcheck). shellcheck non-blocking (F26 cleans the ~40 style/false-positive findings).
- Charon Gateway LIVE at `10.0.1.60:8080` (4-LOM). Route sub-work via `opencode run --model charon/<curated-id>`; `free-groq` unusable (8k TPM). 4-LOM SSH needs `-i ~/.ssh/4lom`.

## OPEN OPERATOR ACTIONS

- **None blocking.** All pushes/merges landed this session. Optional: review the F23 Phase-2 plan before I open the product-CI PR (it touches public CI/GHCR).

## SESSION-BRIDGE

Was `plo-koon` (unregistered at first close; session continued for merges). Next session registers under a NEW Jedi name (stale sessions auto-purge after 600s).

## Key findings / decisions

- **Push authority already existed** (land-push.sh + AUTONOMOUS lever ON) — a stale "operator pushes" handoff line masked it and cost a session; fixed in §8 doctrine.
- **Roci SSH already set up** — `ssh rocinante` works; B2 prereq met (earlier "denied" was wrong invocation).
- **F23 design DECIDED**: deploy only if master advanced + CI green; advisory on failure; git-describe version; build on every green master push. `deploy.sh` already does /data backup + health-verify + auto-rollback.
- Product/fleet split is load-bearing but implicitly coupled → wrong-repo bug class (F25).

## Open questions

None blocking. F23 Phase-2 build-trigger + version form confirmed (every green push, git-describe).
