# Charon Fleet — Session Handoff (2026-07-15T06:45:40Z) — rey-durron

> **Per-session handoff.** Each session writes: `SESSION-HANDOFF-$SESSION.md`.
> No collisions. Next session reads ALL: `SESSION-HANDOFF-*.md`.

**Date:** 2026-07-15
**Session:** rey-durron

---

## Bootstrap (copy-paste into next session)

```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-rey-durron.md — you are the fresh Charon fleet MANAGER, carry it out, then flip to fleet mode.
```

### Context discipline (token-burn guard — always on)
1. **Auto-compact ON.** At startup verify `grep autoCompactEnabled ~/.claude/settings.json` shows `true`. If not, STOP and tell the operator (see `fleet/SETTINGS-GUARD-PROPOSAL.md`) — a never-compacting transcript makes per-turn token cost climb all session.
2. **Sub-sessions write, don't dump.** A sub-session WRITES its findings to a file and returns only a 2-3 line pointer + the absolute path. NEVER paste a full sub-session report back into the primary.
3. **Read big docs in narrow slices, once.** Read handoffs/plans by line-range (offset/limit), never the whole file, never re-read each turn.
4. **Keep-alive is a light heartbeat.** Fold the bridge heartbeat into real work (`board()` TTL 600s); do NOT run a 4-min idle wakeup loop that reprocesses full context.

---

## Provenance (anti-clobber — verify this matches the session/filename before trusting this handoff)

**Session:** rey-durron
**Generated:** 2026-07-15T06:45:40Z
**Product HEAD:** c492e2b — current with origin/master
**Rig HEAD:** 50495cd — current with origin/master

---

## Done / committed@SHA (auto — what the previous session shipped)

> Mechanized: latest 5 SHAs on master (rig + product) + any session-specific branches' HEAD.
> Edit this section only if you need to highlight specific commits the next session must NOT regress.
```
rig master HEAD:    50495cd
rig master subject: Merge pull request #54 from Nnyan/feat/handoff-mechanize
product master HEAD:    c492e2b
product master subject: Merge pull request #136 from SLOP-Platform/diag/decomposer-planner

--- last 5 rig master commits ---
50495cd Merge pull request #54 from Nnyan/feat/handoff-mechanize
c03d811 Merge pull request #71 from Nnyan/feat/config-drift-gate
c324dbf feat(fleet): config-drift detection + visibility gate (siloed provider/model config)
8434fd0 Merge pull request #70 from Nnyan/feat/eval-tier-canon
9974b59 Merge pull request #66 from Nnyan/feat/eval-derived-budgets

--- last 5 product master commits ---
c492e2b Merge pull request #136 from SLOP-Platform/diag/decomposer-planner
1a7c6df fix(planner): SG-never-Anthropic guard in _select_planner_model
aa8f6a1 fix(recommend): resolve preset base_url in _find_trusted_models
b7aa4c8 Merge pull request #126 from SLOP-Platform/chore/gitignore-tooldirs
1a1f88f chore: gitignore local dev-tool caches (.ksf/, graphify-out/)
```

---

## Next-action / in-flight (auto + manager narrative)

> **Mechanized first-action snapshot:** the live machine state for the current handoff time
> (active worktrees, in-flight charon-run jobs + their CHARON_RUN_RESULT, and the latest
> provider-exhaustion-ledger tail) is auto-emitted under \`## Auto-generated state\` below.
> The \`### Manager's first actions\` subsection is the ONLY place the manager hand-types
> the next session's priority order — keep it terse (numbered, with one file/script per item).

### Manager's first actions (priority order — operator-set 2026-07-15)

**NORTH STAR (operator):** get **SG (the Smart Gateway) FULLY dogfood-e2e-ready to run tickets end-to-end via a manager session** (manager drives non-Claude work THROUGH the gateway; Claude only where a ticket is reserved). The sequence below walks toward that. See `[[charon-work-engine-vision]]`, `[[route-work-to-charon-not-claude]]`, `[[charon-headless-review-loop]]`.

0. **Ground first (LESSONS below — do these or repeat my pain):**
   - `git -C /home/stack/charon-private pull --ff-only origin master` AND `git -C /home/stack/code/charon pull --ff-only origin master` — local masters DRIFT (land.sh base-sync skips when master is checked out in the main worktree). A stale product checkout made a *landed* fix look broken all session (LESSON 2).
   - Verify `charon providers list` runs (CLI shim was dead this session; fixed — LESSON 4).

1. **RFL-5** — Claude-RESERVED, so the **MANAGER builds it itself via a background Agent sub-session** (Opus). Off-Claude fleet must SKIP it (it is `parked: true` in `board/RFL-5.md`). Build `src/charon/context_shaper.py` + `tests/test_context_shaper.py` per `prompts/rfl-5.md` + board scope: stdlib TF + reservoir context-compaction, **OPT-IN per-request, OFF by default, MUST NOT mutate user messages by default, stateless (in-request on the messages array), disclose when applied, module ONLY** (no proxy wiring). Adversarial-review → land. See `[[claude-reserved-tickets-manager-builds]]`.

2. **Planner-Fix** (product KEY code) — `src/charon/decompose_planner.py::_select_planner_model` picks the FIRST trusted model (`glm-4.5`) → returns unparseable JSON, so `decompose.sh` fails on real tickets. Fix to **CHEAPEST-STRONGEST** per Charon's routing rule (reuse cost-rank + capability grades; KEEP the non-Anthropic guard landed in #136). Then **re-dogfood**: `fleet/decompose.sh <a ticket whose owns are EXISTING multi-file code>` and confirm a valid *disjoint* split before trusting it. (Net-new-file / single-module tickets do NOT decompose — serial-justify those.)

3. **Phase-2 CONFIG-SSOT-PROPAGATE** (task, `[[config-ssot-git-manifest]]`) — build the git-manifest SSOT + propagation. Phase-1 detection is **LANDED (#71 `fleet/config-drift.sh`)** and already shows the drift (local has only `zai`; 4-LOM has 10 incl `nvidia`). **NEEDS OPERATOR DECISION before the write-path build:** how the gate writes to the live 4-LOM deploy — `docker exec` a config write into container `charon-gateway-1`'s `/data` volume, vs write-volume-then-redeploy. Manifest likely belongs in the PRIVATE rig (do not publish the operator's active-provider set). **Also fix:** `fleet/state/CONFIG-SOURCES.tsv` may be gitignored/absent → gate degraded; verify + add a `!`-negation like `RULE-REGISTRY.tsv` / `ROADMAP.tsv`.

4. **Then the normal sequence:** land EVAL-PIPELINE-CONSOLIDATE when the frontier tab PRs it → unblocks **EVAL-PROMOTION-GATE (Wave-3)** → **COVERAGE-META** land (branch `feat/coverage-meta-gate` @ `e7aaeea`, LOCAL-UNPUSHED, reviewed PASS-with-findings; close the 3 fake-green hatches — exempt-until has no cap, `guidance` bypasses the denominator, 11/17 mechanized rows are existence-only — or file a follow-up) → **stranded batch-land** (`scratchpad/stranded-batchland-plan.md`: 21 green-ready in 5s, EXCLUDE `price-refresher`=FABRICATED) → grader chmod fast-follow → remaining mechanization (WORK-GATE-UNIVERSAL, SSOT-DRIFT-GATE, ENV-REGISTRY-WIRE, REACHABILITY-GATE, FAIL-LOUD-CONTRACT).

---

## Delivered this session (rey-durron)

**Merged (11 PRs):** rig #63 EVAL-TAXONOMY-ALIGN, #64 EVAL-GRADER-PROVISION, #65 REVIEWER-DOGFOOD-REDS, #66 EVAL-DERIVED-BUDGETS, #67 pyc-hygiene, #68 SESSION-CTX-PROPAGATE, #69 BASE-INTEGRITY-GATE, #70 EVAL-TIER-CANON, #71 config-drift-gate (Phase-1), #54 HANDOFF-MECHANIZE · product #136 decomposer fix (`providers.resolve` + SG-never-Anthropic planner guard). **EVAL Wave-2 DONE** (DERIVED-BUDGETS + TIER-CANON); EVAL-PIPELINE-CONSOLIDATE building on frontier tab now.

**Infra/state changes the next session inherits:**
- **SubagentStart hook LIVE** in `~/.claude/settings.json` (backed up `*.bak-sessionctx-*`); live-dogfood confirmed a sub-agent receives the `session-ctx-preamble.sh` pointer index.
- **charon CLI shim FIXED** — editable install pointed at deleted `/home/stack/code/charon-sr-7`; repointed `~/.local/lib/python3.12/site-packages/_editable_impl_charon.pth` → `/home/stack/code/charon/src`.
- **Local `~/.charon` models imported** — `zai` (8) + `nanogpt` (612) → `_find_trusted_models` returns 620. (Decomposer planner now runs but picks glm-4.5 — see Planner-Fix.)
- **Loop-guard swept** — ~11 ready tickets were quarantined from earlier broken-env spins and starving the tabs; cleared.
- New memories: `[[canonical-session-operating-rhythm]]`, `[[token-lean-review-and-droids]]`, `[[config-ssot-git-manifest]]`, `[[4lom-host-access]]`, `[[claude-reserved-tickets-manager-builds]]`.

## LESSONS LEARNED THIS SESSION (mechanize / avoid re-hitting)
1. **land.sh false-DONE on DRAFT PRs** — `gh pr merge` fails on a draft but land.sh still prints `land: DONE`. I nearly recorded false lands. ALWAYS `gh pr ready <N>` first for droid PRs, and VERIFY `state==MERGED` after. → build a land.sh merge-exit check (queued).
2. **Local master drift hides landed fixes** — a landed fix (#136) looked broken because the local product checkout was stale. `git pull --ff-only` both masters at session start AND fold it into every push batch; land.sh's base-sync SKIPS when master is checked out in the main worktree.
3. **loop-guard never auto-clears** — env breakage (broken CLI / stale masters) makes droids zero-commit → quarantine → tabs starve even after the env is fixed. When tabs starve, `ls fleet/state/loop-guard/` and sweep ready tickets.
4. **charon CLI shim can silently die** — a stale editable-install `.pth` breaks `charon` everywhere (claim.sh `charon tier ranks`, provider ops) with no loud error. Check `charon providers list` at boot.
5. **Config siloing is real & invisible** — `charon providers add` writes only the local config_dir; 4-LOM's docker `/data` is a separate silo → NVIDIA stranded there. (→ Phase-2.)
6. **Decomposer needs a STRONG planner** — first-trusted selection picks a weak model; the whole decompose protocol is only as good as the planner model (cheapest-STRONGEST).
7. **Agent sub-sessions die on `/quit`** — for survive-a-handoff work use detached `setsid claude -p` (heavier: re-pays full SessionStart context, disconnected) or just defer to the fresh session. Operator's call this session: keep using Agent sub-sessions, defer builds to handoff.

## Operator actions / open decisions
- **[A] Phase-2 write-path decision** (blocks the propagation build): `docker exec`-write into 4-LOM's live `/data`, or write-volume+redeploy?
- **[B] Optional:** to give the decomposer a strong local planner now, `charon providers add nvidia` + `models import nvidia` locally — but prefer doing it via the Phase-2 manifest so it doesn't re-silo. NVIDIA is on 4-LOM: `nvidia | https://integrate.api.nvidia.com/v1 | NVIDIA_API_KEY`.

## Live tabs at handoff (survive /quit — do NOT relaunch blindly)
- One **frontier** tab was building **EVAL-PIPELINE-CONSOLIDATE** (will PR — review+land it, unblocks EVAL-PROMOTION-GATE); a 2nd frontier + two strong + one economy tab were up. Check live before launching more: `ps -ef | grep fleet-droid` (the PIDs are stale post-handoff). Claimable depth: strong/frontier healthy, economy thin (HANDOFF-PIPEFAIL now unblocked by #54).

---

## Gotchas (avoid re-discovering / DENIED)

> Mechanized: any pre-existing red that names gotcha-class info (e.g. `git push is DENIED`)
> is auto-prepended below. Fill the session-specific gotchas below the mechanized list.

- `git push` **AND** `git -C <path> push` are BOTH DENIED to the manager (verified this session — the push-guard gap is closed). SANCTIONED push paths (do NOT ask the operator to push): **`land.sh <branch> <repo> [--gate …]`** (commit→gate→branch→push→PR→merge, for feature work) and **`land-push.sh <branch> [repo] [--gate …]`** (gate→push an already-committed branch/master; self-gates on AUTONOMOUS). This handoff commit was pushed with `land-push.sh master /home/stack/charon-private`.
- **land.sh prints `land: DONE` even when `gh pr merge` FAILED on a draft PR** — false success. For droid PRs: `gh pr ready <N>` first, then verify `gh pr view <N> --json state` == MERGED.
- **Local masters DRIFT** — land.sh base-sync skips when master is checked out in the main worktree. `git pull --ff-only` BOTH repos at boot and after each land batch, or landed fixes look broken.
- **PRICE-REFRESHER is FABRICATED** (PR #104 CLOSED) despite green CI — do NOT land it.
- **Board↔GitHub done-marker drift** — retire-done reports ~33 `HELD (not merge-verified)` markers (SR-*, DTC-*, ADR-*, etc.); pre-existing, needs a reconcile pass (not this session's tickets).
- **4-LOM ssh** needs `ssh -i ~/.ssh/4lom stack@10.0.1.60` (bare ssh uses the wrong key + fails). CG config lives in docker container `charon-gateway-1` at `/data` (`CHARON_HOME=/data`). See `[[4lom-host-access]]`.
- **Stale fleet worktrees** — ~30 `charon-fleet-dogfood-*` + a few `charon-fleet-*` product worktrees at old SHAs; F15 worktree-cleanup should sweep them (I removed only my own landed `/home/stack/wt/*`; kept `coverage-meta-gate` unlanded + the active EVAL-PIPELINE-CONSOLIDATE droid worktree).
- **`fleet/state/CONFIG-SOURCES.tsv`** (config-drift registry) may be gitignored/absent → config-drift.sh degraded; verify + `!`-negate in `.gitignore`.

---

## session-bridge (auto — live board)

> Mechanized: live `~/.charon/session-bridge.db` board snapshot at handoff time. If empty,
> the next session starts with a clean bridge (no coordination sessions in flight).

```
(no active bridge sessions in the last 30 min)
```
> Coordination rule (read before claiming any work): review the board above for
> collisions (same files) and blockers (sessions blocked on THIS session's deliverable).
> If this session is BLOCKED on another session, surface it in `blockers=` on your `register()`.
> If you INHERIT a session from the board (the previous session timed out), pick a
> new Jedi name and do NOT re-register the old one.

---

## Auto-generated state
### Active worktrees (`git worktree list`)
```
/home/stack/code/charon                                                                         c492e2b [master]
/home/stack/charon-wt/order-a                                                                   16dbdc2 [feat/ordering-cost-primary]
/home/stack/code/charon-fleet-BUILD-SERVER-EPHEMERAL-PORT                                       6460ace [fix/build-server-ephemeral-port]
/home/stack/code/charon-fleet-FAIL-LOUD-CONTRACT                                                c472fee [feat/fail-loud-contract]
/home/stack/code/charon-fleet-FN1-MEMORY-STORE-ADOPT                                            c301670 [feat/fn1-memory-store]
/home/stack/code/charon-fleet-FN2-BITEMPORAL-DECAY                                              efe1a60 [feat/fn2-bitemporal-decay]
/home/stack/code/charon-fleet-FN3-CURATION-PASS                                                 42473fa [feat/fn3-curation-pass]
/home/stack/code/charon-fleet-FT-CATALOG-SEED                                                   e647748 [feat/ft-catalog-seed]
/home/stack/code/charon-fleet-FT-CONFIG-SURFACE                                                 6b257b5 [feat/ft-config-surface]
/home/stack/code/charon-fleet-FT-QUOTA-ENGINE                                                   ff5479f [feat/ft-quota-engine]
/home/stack/code/charon-fleet-GATE-INTEGRITY-A                                                  968db47 [feat/gate-integrity-inert]
/home/stack/code/charon-fleet-GATE-PERF                                                         21e45bb [feat/gate-perf-product]
/home/stack/code/charon-fleet-PRICE-REFRESHER                                                   3314989 [feat/price-refresher]
/home/stack/code/charon-fleet-PROJECT-MEMBERSHIP-GATE                                           d0f1f25 [feat/project-membership-gate]
/home/stack/code/charon-fleet-PROVIDER-PROBE-FIX                                                cf6c2fa [fix/provider-probe-validation]
/home/stack/code/charon-fleet-SR-4                                                              21003f8 [feat/sr-4-smart-routing-doc-fix]
/home/stack/code/charon-fleet-TOOL-REPAIR-MUTATING                                              69eb5a6 [feat/tool-repair-mutating-gate]
/home/stack/code/charon-fleet-WORK-CONVERGE-REVIEW                                              2fccd83 [docs/work-converge-review]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-deepseek-v4-flash-20260714T234305Z    b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/deepseek-v4-flash-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-deepseek-v4-pro-20260714T234305Z      b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/deepseek-v4-pro-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-free-mistral-code-20260714T234305Z    b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/free-mistral-code-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-gemma-4-31b-cb-20260714T234305Z       b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/gemma-4-31b-cb-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-glm-5.2-20260714T234305Z              b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/glm-5.2-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-kimi-k2.6-20260714T234305Z            b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/kimi-k2.6-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-minimax-m2.7-20260714T234305Z         b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/minimax-m2.7-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-minimax-m3-together-20260714T234305Z  b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/minimax-m3-together-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-deepseek-v4-flash-20260715T001840Z                  b7aa4c8 [dogfood-eval/RFL-3/deepseek-v4-flash-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-deepseek-v4-pro-20260715T001840Z                    b7aa4c8 [dogfood-eval/RFL-3/deepseek-v4-pro-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-free-mistral-code-20260715T001840Z                  b7aa4c8 [dogfood-eval/RFL-3/free-mistral-code-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-gemma-4-31b-cb-20260715T001840Z                     b7aa4c8 [dogfood-eval/RFL-3/gemma-4-31b-cb-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-glm-5.2-20260715T001840Z                            b7aa4c8 [dogfood-eval/RFL-3/glm-5.2-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-kimi-k2.6-20260715T001840Z                          b7aa4c8 [dogfood-eval/RFL-3/kimi-k2.6-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-minimax-m2.7-20260715T001840Z                       b7aa4c8 [dogfood-eval/RFL-3/minimax-m2.7-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-minimax-m3-together-20260715T001840Z                b7aa4c8 [dogfood-eval/RFL-3/minimax-m3-together-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-flash-20260714T232603Z       b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-flash-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-pro-20260714T134749Z         b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-pro-20260714T134749Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-pro-20260714T232021Z         b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-pro-20260714T232021Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-pro-20260714T232300Z         b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-pro-20260714T232300Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-pro-20260714T232603Z         b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-pro-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-free-mistral-code-20260714T232603Z       b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/free-mistral-code-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-gemma-4-31b-cb-20260714T232603Z          b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/gemma-4-31b-cb-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-glm-5.2-20260714T232603Z                 b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/glm-5.2-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-kimi-k2.6-20260714T232603Z               b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/kimi-k2.6-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-minimax-m2.7-20260714T232603Z            b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/minimax-m2.7-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-minimax-m3-together-20260714T232603Z     b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/minimax-m3-together-20260714T232603Z]
/home/stack/code/charon-fleet-rfl-5                                                             249b727 [feat/rfl-5-context-compaction]
/home/stack/code/charon/.claude/worktrees/agent-a4294af67f9d41d80                               af8d795 [feat/wire-tool-repair]
/home/stack/code/charon/.claude/worktrees/agent-ab00727b804e8f8db                               45d8af7 [feat/public-clean-enforce]
/home/stack/wt/decomposer-diag                                                                  1a7c6df [diag/decomposer-planner]

/home/stack/charon-private                               50495cd [master]
/home/stack/charon-private-wt/ADD-PROVIDER-MECHANIZE     6a2b88a [feat/add-provider-mechanize]
/home/stack/charon-private-wt/B3-LOG-PRUNE               b309161 [chore/b3-log-prune]
/home/stack/charon-private-wt/EVAL-DERIVED-BUDGETS       5bbc525 [feat/eval-derived-budgets]
/home/stack/charon-private-wt/EVAL-GRADER-PROVISION      26e3e84 [feat/eval-grader-provision]
/home/stack/charon-private-wt/EVAL-PIPELINE-CONSOLIDATE  8434fd0 [feat/eval-pipeline-consolidate]
/home/stack/charon-private-wt/EVAL-TAXONOMY-ALIGN        9d26d79 [feat/eval-taxonomy-align]
/home/stack/charon-private-wt/EVAL-TIER-CANON            457e295 [feat/eval-tier-canon]
/home/stack/charon-private-wt/FN1-MEMORY-STORE-ADOPT     676cb13 [feat/fn1-memory-store]
/home/stack/charon-private-wt/FN2-BITEMPORAL-DECAY       dc81372 [feat/fn2-bitemporal-decay]
/home/stack/charon-private-wt/FN3-CURATION-PASS          1cc7c3d [feat/fn3-curation-pass]
/home/stack/charon-private-wt/FN4-RESEARCH-GATE          8c659a3 [feat/fn4-research-gate]
/home/stack/charon-private-wt/FN5-REGISTRY-SWEEP         a040bc5 [feat/fn5-registry-sweep]
/home/stack/charon-private-wt/HANDOFF-MECHANIZE          67b250e [feat/handoff-mechanize]
/home/stack/charon-private-wt/LAND-SH-POSTMORTEM         55a547a [audit/land-sh-postmortem]
/home/stack/charon-private-wt/LAND-SH-SAFE-SYNC          ed1aa0d [fix/land-sh-safe-sync]
/home/stack/charon-private-wt/LEG-F6-REALPATH-TEST       cfe45a5 [feat/leg-f6-realpath-test]
/home/stack/charon-private-wt/NO-DARK-WORK               4cc09a6 [feat/no-dark-work]
/home/stack/charon-private-wt/R43-WIRING-AUDIT           c041b59 [audit/r43-wiring-audit]
/home/stack/charon-private-wt/SESSION-END-PUSH-GATE      1088460 [feat/session-end-push-gate]
/home/stack/wt/base-integrity-gate                       023890a [feat/base-integrity-gate]
/home/stack/wt/config-drift                              c324dbf [feat/config-drift-gate]
/home/stack/wt/coverage-meta-gate                        e7aaeea [feat/coverage-meta-gate]
/home/stack/wt/eval-grader-provision2                    38af193 [feat/eval-grader-provision2]
/home/stack/wt/eval-latency-gate                         bd0ec76 [feat/eval-latency-gate]
/home/stack/wt/eval-taxonomy-align2                      8d04bd7 [feat/eval-taxonomy-align2]
/home/stack/wt/leg-preflight-canary                      4f798d2 [feat/leg-preflight-canary]
/home/stack/wt/reviewer-dogfood-reds                     cf53c81 [feat/reviewer-dogfood-reds]
/home/stack/wt/session-ctx-propagate                     2ea3c23 [feat/session-ctx-propagate]
```
### In-flight charon-run jobs (CHARON_RUN_RESULT)
```
dogfood-RFL-3-minimax-m2.7-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-free-mistral-code-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-gemma-4-31b-cb-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-deepseek-v4-flash-20260715T001840Z  ->  SUCCESS model=deepseek-v4-flash
dogfood-RFL-3-glm-5.2-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-kimi-k2.6-20260715T001840Z  ->  SUCCESS model=kimi-k2.6
dogfood-RFL-3-minimax-m3-together-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-deepseek-v4-pro-20260715T001840Z  ->  SUCCESS model=deepseek-v4-pro
```
### Provider-exhaustion-ledger tail (`provider-exhaustion-ledger.tsv`)
```
ts	job	model	event	note
2026-07-15T06:32:36Z	out	my-model	infra-fault-failover	rc=1; provider/local/infra symptom (5xx/reset/refused/deadline/db-lock/timeout/opaque) -- not a model verdict
2026-07-15T06:32:36Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-07-15T06:32:36Z	out	my-model	infra-fault-failover	rc=1; provider/local/infra symptom (5xx/reset/refused/deadline/db-lock/timeout/opaque) -- not a model verdict
2026-07-15T06:32:36Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-07-15T06:32:36Z	out	my-model	too-slow-failover	rc=124; budget=1800s; model streamed output but did not finish -- latency-is-a-failure-class, model-attributable
2026-07-15T06:32:36Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-07-15T06:32:36Z	out	my-model	infra-fault-failover	rc=3; provider/local/infra symptom (5xx/reset/refused/deadline/db-lock/timeout/opaque) -- not a model verdict
2026-07-15T06:32:36Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-07-15T06:32:36Z	out	my-model	error-failover	rc=1; non-limit, non-infra failure (genuine model-attributable result)
2026-07-15T06:32:36Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
```
### Git
```
master

 M docs/adr/0003-capability-routed-agent-orchestration-harness.md
?? tools/inert_to_graph.py

--- last 10 commits ---
c492e2b Merge pull request #136 from SLOP-Platform/diag/decomposer-planner
1a7c6df fix(planner): SG-never-Anthropic guard in _select_planner_model
aa8f6a1 fix(recommend): resolve preset base_url in _find_trusted_models
b7aa4c8 Merge pull request #126 from SLOP-Platform/chore/gitignore-tooldirs
1a1f88f chore: gitignore local dev-tool caches (.ksf/, graphify-out/)
8639bff Merge pull request #125 from SLOP-Platform/feat/classify-listbody-and-token-drift
fadead2 Merge pull request #124 from SLOP-Platform/feat/auto-park-on-402
b8e62d0 fix(balance): serialize + uniquely-name parked-set persist (concurrency BLOCKER)
4b5df92 fix(proxy): preserve billing-pattern detection for list-shaped error bodies
860e924 feat(gateway): auto-park on deterministic 402, persist + auto-rearm
```
### Open PRs
```
[{"headRefName":"feat/ft-catalog-seed","number":135,"state":"OPEN","title":"chore(FT-CATALOG-SEED): launcher auto-commit — droid exited without committing (review for completeness)"},{"headRefName":"feat/ft-config-surface","number":134,"state":"OPEN","title":"feat(config): add free_tier block to add_provider for QuotaTracker wiring"},{"headRefName":"feat/ft-quota-engine","number":133,"state":"OPEN","title":"feat(quota): free-tier engine with weekly/monthly windows + calendar reset + persistence"},{"headRefName":"feat/tool-repair-mutating-gate","number":132,"state":"OPEN","title":"fix(tool-repair): make allow_mutating a real gate via is_mutating marker"},{"headRefName":"feat/sr-4-smart-routing-doc-fix","number":131,"state":"OPEN","title":"docs(SR-4): review-log — already complete on charon-private master (commit 50af47c)"},{"headRefName":"feat/project-membership-gate","number":130,"state":"OPEN","title":"feat(PROJECT-MEMBERSHIP-GATE): gate that every live ticket is folded into a ROADMAP row"},{"headRefName":"fix/provider-probe-validation","number":129,"state":"OPEN","title":"fix(gateway): treat successful /models probe as sufficient provider validation"},{"headRefName":"feat/gate-integrity-inert","number":128,"state":"OPEN","title":"fix(inert): create inert_to_graph.py sans orphan @covers; remove stale ActualRow/ActualsLedger from disposition"},{"headRefName":"feat/gate-perf-product","number":127,"state":"OPEN","title":"perf(test): cut test-suite wall-clock ~16x (serve_forever poll + xdist + DNS)"},{"headRefName":"dependabot/github_actions/github-actions-911e50acf6","number":86,"state":"OPEN","title":"ci: bump the github-actions group across 1 directory with 6 updates"}]
```
### Gate
```
