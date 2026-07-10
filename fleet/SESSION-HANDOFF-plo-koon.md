# HANDOFF — 2026-07-10 (session plo-koon) — Charon fleet MANAGER

## Bootstrap (paste as the next session's first message)
```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-plo-koon.md — you are the fresh Charon fleet MANAGER
```

## STATE — WHAT SHIPPED THIS SESSION (all COMMITTED, pending your merge + push)

- **Branch `feat/f22-done-close-archived-fix` @ `ec63918`** —
  - `db72099` **F22**: `done.sh` no longer aborts on archive-only tickets (`meta()` ran `awk` on the absent active-board file; `set -e` killed it before the archive fallback/override). Fix + fail-on-revert cases g1g/g1h.
  - `deb89b3` closed the **4 P1 done-unmerged reds** (item 3): BRIDGE-HARDEN / PREFLIGHT / DS-PLAN-REVIEW via `--override` (fleet-infra, no product source); TIER-SELECT via `--merged-sha c4c4189` (ancestor of product master).
  - `b7dfd2f` **F23 Phase 1** session-end deploy harness (advisory, tag-if-behind) + tests; `cd62631` my no-hang review-fix (`timeout`+BatchMode on all lookups + t6). Suite 20/20, end-session 16/16, all fail-on-revert; live no-op smoke test against real 4-LOM green.
- **Branch `feat/f21-gate-exclude-goldens` @ `21aad09`** —
  - `f325d04` **F21**: root `conftest.py` excludes `fleet/benchmark` from gate collection.
  - `b67435e`+`7d663df` **F24**: fleet gate is now `fleet/gate.sh` (runs the 8 `fleet/tests/*.test.sh` + **advisory** shellcheck), not product `pytest`/`ruff src tests`. Gate now GREEN + meaningful (9 pass). `handoff.sh` edit is minimal (gate block only).
  - `b06b266` streamed **F25** (`fleet/board/REPO-DECL-CENTRAL.md`) + **F26** (shellcheck-clean).
- **master @ `b7d3228`** — MANAGER-OPERATING-RULES §9: token-economy is the DEFAULT mode every session. COMMITTED, **NOT pushed**.
- **Product PR #94** (SLOP-Platform/charon) OPEN — S1/S2/S4 public-clean-enforce (from prior session).

## FIRST ACTIONS — NEXT (priority order)

0. Run `/home/stack/charon-private/fleet/preflight.sh`; register on the session-bridge under a NEW Jedi name.
1. Confirm the operator merged the 3 branches + pushed master (see OPEN OPERATOR ACTIONS). Then **reconcile ROADMAP**: F20–F26 rows are split across master/`feat/f22`/`feat/f21` — after merges, `/home/stack/charon-private/fleet/state/ROADMAP.tsv` should read F20 done, F21 done, F22 done, F23 building, F24 done, F25 designed, F26 designed; re-run `/home/stack/charon-private/fleet/report.sh`.
2. **F23 Phase 2 (CD)** — decided this session: CI builds a **git-describe** image (`vX.Y.Z-N-gSHA`) on **every GREEN master push**; extend `fleet/deploy.sh` tag-guard to accept it; harness compares describe versions + deploys latest-if-behind; GHCR retention (keep last N dev images); gateway reports its running version (visible, not hidden). Spans the PUBLIC product repo → **PR to SLOP-Platform/charon** (higher blast radius).
3. **F25** repo-decl-central and **F26** shellcheck-clean (rig-only, designed).
4. Remaining backlog per `report.sh`: F11–F19, S-program, Bridge B2–B6, K1–K7.

## GOTCHAS (avoid re-discovering / DENIED)

- `git push` is **DENIED** to the manager (settings deny-list) — the OPERATOR pushes/merges. Never push.
- **Two repos**: PRODUCT = `/home/stack/code/charon` (public SLOP-Platform/charon); FLEET = `/home/stack/charon-private` (private Nnyan/charon-private). Rig tools that reason about "a repo" must say WHICH — the root of a bug-class this session (F25).
- `done.sh`: the done-merge gate checks the PRODUCT repo, so FLEET-infra tickets need `--override "<reason>"` (recorded, surfaced by preflight). Archived tickets now close correctly (F22).
- Fleet gate = `fleet/gate.sh` (fleet bash tests + ADVISORY shellcheck), NOT product pytest/ruff. shellcheck is advisory because `fleet/*.sh` have ~40 style/false-positive findings (F26 cleans them).
- Charon Gateway is LIVE at `10.0.1.60:8080` (4-LOM). Route sub-work via `opencode run --model charon/<curated-id>`. `free-groq` is unusable (8k TPM < opencode's prompt). 4-LOM SSH works ONLY with `-i ~/.ssh/4lom` (plain ssh is DENIED).
- ROADMAP.tsv was edited on 3 branches — keep future state edits on master to avoid this.
- `handoff.sh` is co-owned by unmerged HANDOFF-MECHANIZE / HANDOFF-PIPEFAIL — watch merge order (F24's edit is minimal).

## OPEN OPERATOR ACTIONS

1. **Merge + push** (all committed, pending):
   - `git -C /home/stack/charon-private push -u origin feat/f22-done-close-archived-fix` → merge to master
   - `git -C /home/stack/charon-private push -u origin feat/f21-gate-exclude-goldens` → merge to master
   - `git -C /home/stack/charon-private push origin master` (token-economy rule `b7d3228`)
   - Product PR #94 on SLOP-Platform/charon → merge (strip `tools/PUBLIC-CLEAN-ENFORCE-REVIEW.md` if that's the repo convention).
2. (Optional, unblocks B2 later) rootless SSH to Rocinante `10.0.1.51` as bridge coordinator — still DENIED to this session.

## SESSION-BRIDGE

Registered as `plo-koon` (repo charon); unregistered at close. Next session registers under a NEW Jedi name (stale sessions auto-purge after 600s).

## Key findings / decisions

- **F23 deploy design DECIDED**: deploy only if master advanced + CI green; advisory on failure (register red, still close); git-describe version form; build on every green master push. `deploy.sh` already does /data backup + health-verify + auto-rollback.
- The product/fleet split is load-bearing but its coupling is implicit (product path hardcoded across ~7 rig files) → the recurring wrong-repo bug class (item-3 false reds, F21/F24). Centralize in `_lib.sh` (F25).
- Charon-built sub-session diffs get adversarial review: F23 shipped a real no-hang defect its stubbed tests could not catch (bare ssh, no timeout) — caught + fixed. Never trust the SUCCESS line.

## Files modified this session

master: `MANAGER-OPERATING-RULES.md`. feat/f22: `done.sh`, `tests/done-gate.test.sh`, `deploy-session-end.sh`, `end-session.sh`, `tests/deploy-session-end.test.sh`, `reds.tsv`, `state/ROADMAP.tsv`. feat/f21: `conftest.py`, `gate.sh`, `handoff.sh`, `tests/gate.test.sh`, `board/REPO-DECL-CENTRAL.md`, `state/ROADMAP.tsv`.

## Open questions

None blocking. Phase-2 build-trigger + version form already confirmed (every green push, git-describe).
