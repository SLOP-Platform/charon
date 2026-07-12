# SESSION HANDOFF — luminara → next manager

**Date:** 2026-07-12 14:30 PDT

## Bootstrap (paste this as the next session's first message)
```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-luminara.md — you are the fresh Charon fleet MANAGER.
```

## SHIPPED / DONE this session (all landed via land.sh / PR; charon-private HEAD 1cc0e60)
- **land.sh built + dogfooded (5 clean lands) — Gap A1 CLOSED.** `fleet/land.sh <branch> <repo>` is THE sanctioned merge path: commit → GATE (refuse-on-red) → branch → push → PR → merge → sync-local-base (auto-fixes diverged master). Its git ops run *inside* the wrapper, so it works where raw git is denied. §8 of `fleet/MANAGER-OPERATING-RULES.md` wired to it; raw `git merge` now deny-listed; branch-protection set on SLOP-Platform/charon (PR + `gate` check).
- **FOUNDATION project (project 7) created + landed** (PRs #2, #4): Wave A memory — **FN1** basic-memory store, **FN2** bi-temporal decay (ALSO fixes ROUTER model-ledger gap B2), **FN3** curation; Wave B — **FN4** research-gate. Board: `fleet/board/FN1-MEMORY-STORE-ADOPT.md` … `FN4-RESEARCH-GATE.md`.
- **3 builds reviewed → fixed → re-reviewed → MERGED** (each caught a real defect behind a green build): METER drain-and-park (SLOP-Platform/charon **PR #95**; sole-leg guard verified), capture-pipeline (Nnyan/charon-private **PR #1**; false-success detector, hermetic), bridge B2 push/debate (new private repo **Nnyan/session-bridge PR #1**, 4-LOM runner).
- **KEYSTONE substrate built (UNMERGED — keystone repo has no remote yet):** KS8 coverage MERGE-READY (`feat/ks8-coverage-goal`), KS31 tool-adapters MERGE-READY (`feat/ks31-tool-adapters`), KS29 registry FIX-REQUIRED — discovery-gate skipped + lying docstring (`feat/ks29-registry-primitive`).
- **Design/eval artifacts** (all under `/home/stack/charon-private/fleet/state/`): `GAP-REGISTER.md` (mechanize/lifecycle/adopt-thin classes), `MEMORY-DESIGN.md` (composed: basic-memory + borrowed Zep bi-temporal + curation), `MEMORY-TOOL-EVAL.md` + deep-v2 (`MEMORY-EVAL2-*.md`, 17 tools incl Gingugu), `ROADMAP-WCI-AUDIT.md`, `MODEL-SELF-REPORT-RELIABILITY.md`.
- Memories saved: `keep-the-hopper-full`; `roadmap-display-plaintext-columns` updated (report.sh VERBATIM + SessionStart auto-print). Worktrees pruned 13→4 earlier.

## NEXT — first actions, priority order
1. **Gingugu fork-vs-compose decision** — run a fork-feasibility spike (clone `github.com/gingugu/gingugu`: assess markdown-SSOT adaptation + code quality + how much of FN1/2/3 it collapses). It's MIT + already integrates retrieval+lifecycle+curation+MCP+SessionStart-hook = our whole composed design. **Decide fork-and-adapt vs compose-basic-memory BEFORE building FN1** (it re-scopes FN1/2/3).
2. **Deploys (fully-functional tail for the 3 merged builds):** (a) bridge daemon restart — back up its DB first; LOW current benefit (DTC runner unbuilt); (b) **gateway redeploy** at 10.0.1.60 + set provider `funding_class`/`starting_balance` — docker is deny-listed → operator/deploy-script; (c) grader daemon restart as `bench-grader` — operator. Operator already applied the `git merge` settings deny.
3. **KEYSTONE → private repo + land:** operator runs `gh repo create Nnyan/keystone --private` + `gh repo create … --source … --remote origin` (or the 3-command form) + `gh variable set CI_RUNNER --repo Nnyan/keystone --body '["self-hosted","4-lom"]'`; then add a ci.yml (copy `Nnyan/session-bridge`'s), push master, **land KS8 + KS31 via land.sh** (wire their gate registration into `manifest.toml`/`gates.json` at merge), and **fix KS29** then land.
4. **Quick wins (gap register, ~30 min wall-clock, fan MAX-parallel on CG):** `fleet/log-prune.sh` (logrotate + `find -mtime`) + `fleet/branch-reaper.sh` (`--merged` + `worktree prune`); plus operator one-liners for the fleet-droid deny entry + a 250K context-warning hook.
5. **Roadmap re-org (from `fleet/state/ROADMAP-WCI-AUDIT.md`):** move F14/F15/F12/F26 → FOUNDATION; consolidate the benchmark triple-home (K3/K4/K16 + R41 + B4); ROUTER Wave 4 (R19/R21/R23/R24 all own `providers.py` → serialize or split); KEYSTONE pull KS29/KS8/KS31/KS30 substrate BEFORE lens Wave E; **add board files (owns/difficulty) for KS3–32 + B2–B9** (they fail F43/F30 gates + collisions are uncomputable without them).
6. Fold Gingugu borrowable ideas (confidence-lifecycle enum, decay-on-read, RRF retrieval, consolidate tool, SessionStart contract hook) into FN2/FN3 accept criteria.
7. **FN5 registry-sweep** (FOUNDATION Wave C, operator-approved) — audit product+rig+KSF for smart-module-registry candidates and apply the EXISTING **KS29 registry primitive** (don't reinvent). The F29 Smart-Routing registry is candidate #1; output feeds F29 + KS20 + KS28. Best run after FN4 exists (so the audit is itself reuse/evidence-gated).

## WCI EXECUTION PLAN (operator-directed 2026-07-12 — DO these next session)
**A. Make the CLEAR MOVES** (low-risk placement fixes; edit ROADMAP.tsv + board, land via land.sh):
   - F14 · F15 · F12 → **FOUNDATION** (LIFECYCLE class); F26 shellcheck → FOUNDATION / under KS31 (ADOPT-THIN).
   - K7 → **ROUTER Wave 4**; K8 tool-repair → **ROUTER** (product bug, not backlog).
   - Consolidate the benchmark triple-home (K3/K4/K16 + R41 + B4) into ONE bench theme (GAP-C2: wrap promptfoo) before building.
**B. F29 REVISIT — ACCEPTED (operator, 2026-07-12).** Un-defer F29 **surgically** per `fleet/state/GODFILE-DECOMPOSE-REVIEW.md`, in ONE deliberate pass (it touches all 4 files once), sequenced AHEAD of the R10–R14 / R30–R42 waves it unblocks:
   1. Build a Smart-Routing **module registry** — one declarative table replaces GatewayConfig's 15 fields + the `_module_inst` if-ladder + ~20 passthrough kwargs + ~15 `__init__` params; a new module = 1 row + 1 file, **zero god-file edits** (dissolves the 2 biggest collision clusters at once).
   2. **Decompose `config.py`** into a `config/` package + back-compat facade (un-blocks 9).
   3. **Convert `providers.py` PRESETS → data/category files.**
   All back-compat-faced (low risk). F29 is UN-PARKED in ROADMAP.tsv (🟤→🟣). Decompose into sub-tickets when building; `proxy_server.py` is already half-decomposed (no separate action).
**C. Add owns/difficulty board files for KS3–32 + B2–B9** (subsession) — the blind spots: no board file → collisions uncomputable + they fail the F43/F30 gates.
**D. MECHANIZED actions report (built this session):** `bash fleet/wci-actions.sh` recomputes collision hotspots + board-coverage blind spots from the LIVE board on every run (never stale); the placement/ranked JUDGMENT lives in `fleet/state/ROADMAP-WCI-AUDIT.md` (refresh by re-running the WCI-audit subsession). Use it as the always-current WCI cockpit.

## GOTCHAS / avoid / DENIED
- **Merges/pushes ONLY via `fleet/land.sh`** — raw `git merge` / `git push` / `git -C … push` / `git commit --amend` / `git rebase` / `git remote add` are deny-listed. land.sh gates (refuse-on-red) and auto-syncs a diverged master. `git merge` DENIAL is intentional (added this session).
- **Repo-create + `git remote add` + docker + settings-edit are operator-gated** (deny-listed / self-protected) — hand the operator exact commands, don't fight the wall.
- **Adversarial review is standing for ALL key work** — it caught a message-drop race, a faked traffic proof, and a live-scorecard pollution behind green builds THIS session. Never trust a SUCCESS line; verify the branch diff + independent review. Model lies logged in `fleet/state/MODEL-SELF-REPORT-RELIABILITY.md`.
- **AUTONOMOUS lever is ON** (`fleet/state/AUTONOMOUS`) — land.sh pushes without asking.
- **Open worktrees to clean:** `keystone-wt/{ks8,ks31,ks29,graphify,inert}`, `charon-wt/drain-and-park`, `charon-private-wt/capture-pipeline`.

## session-bridge
Bridge B2 merged to the NEW private repo `Nnyan/session-bridge` (4-LOM runner); the LIVE daemon still runs OLD code (restart = deploy #1). No active SESSION-BRIDGE coordination sessions at handoff.
