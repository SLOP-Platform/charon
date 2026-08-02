# RESCUE-TRIAGE-PRODUCT — triage of the 14 rescued charon branches

Date: 2026-08-01. Lane: `repo: charon` (the PRODUCT checkout). Runs fully parallel
to RESCUE-TRIAGE-RIG and PR-QUEUE-DRIVE — separate trees.

Method, per the ticket's DONE CONTRACT: for every branch, answer (a) is the change
ALREADY on master by another route (proven with shas / `git cherry` / `git patch-id`
/ file content on master, never "looks similar"), and (b) does it still CONTRIBUTE
anything master lacks today. Then exactly one verdict: PR-OPENED / CLOSED-DEAD /
HELD-WITH-REASON, each with evidence. "Close it as dead" is a valid outcome.

Verification tools used: `git cherry origin/master origin/<b>` (patch-id parity),
`git show <sha> | git patch-id --stable` vs master's commit pool, `git merge-tree
--write-tree` (true-merge simulation for conflict/corpse assessment), `git diff`
of file content on master vs branch, `gh pr list/ view` for PR existence and
previously-merged PR numbers.

Summary of dispositions:

| # | Branch | Commits | Verdict |
|---|--------|---------|---------|
| 1 | chore/remove-stdlib-only-prohibition | 1 | CLOSED-DEAD — already on master (56a00a1) |
| 2 | feat/connect-omp-wsl | 1 | PR-OPENED (recommended) |
| 3 | feat/cwd-config | 26 | HELD-WITH-REASON — superseded per subject area; CWD-CONFIG slice needs re-cut |
| 4 | feat/diff-cover-mutmut-adopt | 3 | PR-OPENED (recommended) |
| 5 | feat/gateway-litellm-live-wire | 2 | CLOSED-DEAD — historical STOP probe, superseded by GW-BRIDGE adoption |
| 6 | feat/ordering-cost-primary | 1 | HELD-WITH-REASON — cost ordering on master; slow-trigger slice only |
| 7 | feat/wire-tool-repair | 1 | CLOSED-DEAD — explicitly superseded (#158/350a3e5) |
| 8 | fix/provider-key-exfil-v2 | 1 | CLOSED-DEAD — landed via #181 |
| 9 | fix/provider-key-exfil-v2-round5 | 2 | CLOSED-DEAD — strict ancestor of round6; landed via #181 |
| 10 | fix/provider-key-exfil-round6 | 3 | CLOSED-DEAD — most complete, but distinctive content documented defeated; fix landed via #181 |
| 11 | fix/spend-metric-trustworthy | 1 | PR-OPENED (recommended) |
| 12 | pr164 | 1 | CLOSED-DEAD — content is already-merged PR #164 |
| 13 | sub/ft-catalog-seed-contract-fixtures | 2 | HELD-WITH-REASON — fold into OPEN PR #135 |
| 14 | sub/ft-catalog-seed-fix-v2 | 3 | HELD-WITH-REASON — fix landed as 7128b31; fold into OPEN PR #135 |

---

## 1. chore/remove-stdlib-only-prohibition — CLOSED-DEAD

- Commits: 1 (`ca7d046092`)
- Question (a): **Already on master.** The single commit's stable patch-id
  (`cf71596536`) is byte-identical to master commit
  `56a00a1b5b` ("chore(adopt-first): remove the
  stdlib-only / dependencies=[] PROHIBITION"), which is contained by `origin/master`.
  `git cherry origin/master origin/chore/remove-stdlib-only-prohibition` prints `-` for
  the commit (patch-id already present upstream). File-for-file stat is identical
  (14 files, 85+/215- on both).
- Question (b): **No.** Same content already on master.
- Verdict: **CLOSED-DEAD.** Delete the branch. Reopening would re-merge a commit that
  is already in master's history.

## 2. feat/connect-omp-wsl — PR-OPENED (recommended)

- Commits: 1 (`5660fe6e90`)
- Question (a): **Not on master.** `git cherry` reports `+`. Master's
  `src/charon/connect.py` has `is_wsl` detection and `has_npm`/`has_bun` fields, but
  does NOT contain `_is_wsl_interop`, the native-binary check (`native_bun`/
  `native_npm`), or the `has_unzip`/`sudo apt-get install unzip` prereq branch inside
  `_install_omp`. `tests/test_connect_omp.py` (327 lines) does not exist on master.
- Question (b): **Yes.** It delivers WSL-interop rejection for the `omp` install path:
  when running under WSL, a Windows-interop `bun`/`npm` (which would install to a
  location the WSL agent cannot execute) is rejected and a native `unzip` prereq is
  emitted. Master only warns about the Windows/WSL PATH split; it does not detect and
  reject interop binaries.
- Merge risk: `git merge-tree` against origin/master = 0 conflicts.
- Public-clean: only `src/charon/connect.py` + `tests/test_connect_omp.py` change
  relative to master; no rig paths/hostnames/tokens in the diff.
- Verdict: **PR-OPENED** (recommended). PR body: delivers WSL-interop rejection for
  `omp` install + native bun/npm/unzip prereq + 327 lines of tests. Nothing else on
  this branch is already on master.
- NOTE: the same commit is also a component of `feat/cwd-config` (see #3); opening
  this standalone 1-commit branch is the clean vehicle for that slice.

## 3. feat/cwd-config — HELD-WITH-REASON

- Commits: 26 (largest rescued body in either repo). Branch tip
  `ffde252fea`.
- Per-subject-area (a) analysis — the branch is an accumulator; subject-by-subject,
  with hard evidence, its content is almost entirely already on master:
  - WCI-MVP (`d31573cb`, "static reconciler + depth pre-sort") → patch-id matches
    master `ec20f02dab`. LANDED.
  - OBS-UI (`fe5211bf`, work/board panel) → merged as PR #78
    (`mergedAt 2026-07-02T04:33:28Z`). LANDED.
  - CONSOLE-PROVIDER-MGMT, OBS-CAPTURE, CLIENT-CONNECT-GUI, ADR-0015, ORCH-ROUTE-
    PROXY, global-fallback-provider, DTC gate infra, public-clean-lint →
    consolidated into master commit `c9fedf5` ("feat: Batch 1 — console mgmt, obs
    capture, client connect, ADR-0015, routing proxy, DTC infra, OBS-UI, fallback
    provider"), contained by origin/master. The branch's `src/charon/console_work.py`
    is byte-identical to master's; `tools/check_gate_registry.py`,
    `tools/check_security.py`, `tools/check_test_patterns.py` all exist on master.
  - SETUP-KEY-UX (`17e7a14`) → master `cli.py` already defines `_mask_key` (line 448)
    and `_probe_key` (line 499). LANDED.
  - 25 of 26 commits are `-`/matched or content-identical on master; only the
    CWD-CONFIG slice below is genuinely unlanded.
- Question (b) — surviving slice: **CWD-CONFIG** (`ffde252`, "write per-run
  opencode.json to cwd, remove OPENCODE_CONFIG_CONTENT"). Master's
  `src/charon/adapters/acp.py` has zero `opencode.json`/`config_json` references and
  master's `ports/agent_launch.py` still injects `OPENCODE_CONFIG_CONTENT` (env var),
  which opencode 1.17.11 does NOT honor in ACP mode. Only branches
  `feat/cwd-config` and `feat/global-fallback-provider` contain the
  write-to-`<worktree>/opencode.json` logic. This is a real, live, unlanded
  improvement.
- Merge risk: `git merge-tree --write-tree origin/master origin/feat/cwd-config` = 36
  conflicts (add/add and content across the whole Batch-1 surface). The branch as
  carried is NOT a clean openable unit — opening it would dump 25 already-merged
  commits' worth of merge conflicts into the queue.
- Verdict: **HELD-WITH-REASON.** The branch as a 26-commit unit is superseded per
  subject area (evidence above). Its one live slice — the CWD-CONFIG
  write-per-run-opencode.json-to-cwd change (commit `ffde252` + its 3 test files)
  — should be RE-CUT onto a fresh small branch off latest origin/master and opened
  as its own ~6-file PR (agent_launch.py, acp.py, api.py, 3 test files). Do NOT open
  the 26-commit branch.

## 4. feat/diff-cover-mutmut-adopt — PR-OPENED (recommended)

- Commits: 3 (`8e7c79c`, `eeb6122`, `404881d`)
- Question (a): **Not on master.** `git cherry` reports `+` for all three. Master has
  NO `tools/diff_cover_gate.py`, NO `tools/mutmut_diff_gate.py`, NO
  `tests/test_diff_cover_mutmut_gate.py`, and no `diff-cover`/`mutmut` dev-deps in
  pyproject.toml.
- Question (b): **Yes.** Adds two fail-closed diff-scoped gates — a diff-coverage gate
  (every new/changed line exercised) and a diff-scoped mutation-testing gate — wired
  into `tools/gates.json` (both `ci_step: true`), `src/charon/gate_runner.py`, CI
  workflow steps, plus 258 lines of gate tests and the pyproject dev-deps. Master has
  no mutation/diff-coverage gate at all.
- Merge risk: `git merge-tree` = 0 conflicts. Clean.
- Public-clean: the only additions relative to master are the 2 gate tools, the test
  file, gate_runner.py wiring, ci.yml steps, pyproject deps, and gates.json entries.
  The internal-path strings grep surfaces there are pre-existing on master's
  `tools/gates.json` (2 entries, unchanged by this branch) — not new leaks.
- Verdict: **PR-OPENED** (recommended).

## 5. feat/gateway-litellm-live-wire — CLOSED-DEAD

- Commits: 2 (`42a7440`, `5ebe5c0`)
- Question (a): **Superseded.** The branch's own commit message is the verdict:
  "STOP, do not half-migrate the money-path" — it is a live-wire evidence probe
  (DOGFOOD transcript + `tools/dogfood_litellm_live_probe.py`) whose purpose was to
  halt a half-migration. The migration it was probing subsequently landed on master
  through the GW-BRIDGE series: `1828e98` (GW-BRIDGE-1), `a5f24c4` (GW-BRIDGE-2),
  `8895452` (GW-BRIDGE-3), `7e16e4a` ("adopt litellm.Router (library)"), all
  contained by origin/master, plus `tools/dogfood_litellm_router.py` which is the
  evolved successor of this branch's probe.
- Question (b): **No.** It is a historical STOP-flag, not product code. Master's
  litellm adoption supersedes it.
- Verdict: **CLOSED-DEAD.** The STOP was heeded and the real migration landed.

## 6. feat/ordering-cost-primary — HELD-WITH-REASON

- Commits: 1 (`16dbdc2871`)
- Question (a): **Mostly on master.** "Option A cost-primary ordering" is already
  implemented on master: `src/charon/proxy_server.py` orders chains with
  `order_pool_by_live_cost` (forwarder.py:549-550) and cooldown ordering
  (`order_by_cooldown`, R7/R8 composite sort at proxy_server.py:653-660). `git cherry`
  reports `+` only because the branch's forwarder is pre-Batch-1; the Option A
  ordering semantics live on master via a different implementation.
- Question (b): **Marginal.** The one genuinely-unlanded slice is the slow-provider-
  as-failover-trigger: master defines `is_slow_provider` (proxy_server.py:663) but
  NEVER calls it — the forwarder loop has no `slow` failover append. This branch
  wires it (forwarder.py "Option A: slow provider is a FAILOVER trigger").
- Merge risk: `git merge-tree` = 1 conflict (`tests/test_routing_proxy.py`).
- Verdict: **HELD-WITH-REASON.** Cost ordering is already on master; do NOT open a PR
  titled "cost-primary ordering" when master has it. If the slow-provider-failover-
  trigger is wanted, re-cut that ~6-line slice + its test onto a fresh branch off
  master rather than opening this pre-Batch-1 branch as-is.

## 7. feat/wire-tool-repair — CLOSED-DEAD

- Commits: 1 (`af8d7951c0`)
- Question (a): **Explicitly superseded.** Master's `tests/test_forwarder_tool_repair.py`
  carries the docstring "FORWARDER-RECONCILE (supersedes untracked
  feat/wire-tool-repair, af8d795)". Master commit `350a3e5` ("feat(forwarder):
  reconcile tool_repair wiring onto structured fail-loud contract (#158)") landed the
  same wiring via the F29 `modules=` registry seam (`getattr(srv, "tool_repair",
  None)`, forwarder.py:780-783). The branch's test file is a 42-line-diff older
  variant of the identical test that exists on master.
- Question (b): **No.** Master's forwarder already repairs malformed tool_calls on the
  served-response path.
- Verdict: **CLOSED-DEAD.** Master's own test docstring names this exact branch.

## 8-10. fix/provider-key-exfil-v2 / -v2-round5 / -round6 — ALL CLOSED-DEAD

- Commits: v2 = 1 (`a04edc7d85`),
  v2-round5 = 2 (+ `0811e04453`),
  round6 = 3 (+ `1c2dab90d9`).
- Variant structure: these are NOT three independent takes — they are a strict
  linear progression. `a04edc` is an ancestor of `1c2dab`; `0811e0` is an ancestor of
  `1c2dab`. round6 is the superset carrying all three commits. `git cherry` shows the
  same leading sha across all three.
- Question (a): **The fix is already on master.** Master commit `db62c61`
  ("fix(security): interim exposure reduction for provider-key exfil
  (survived-review subset) (#181)") landed: `test_provider_key_exfil.py` (822 lines)
  that is **byte-identical** to round6's, the `netutil.keyed_request`/`open_keyed`
  egress choke point with redirect-refusal and SSRF base validation,
  `test_redirect_failover.py`, `test_ssrf_base_validation.py`, and the
  convention-over-enforcement design. Master's `netutil.py` module docstring names
  this exact cluster's approaches as DEFEATED: "round 5's hand-rolled AST gate was
  beaten by an EXECUTED bare-name urlopen sender; and round 6's Semgrep denylist was
  beaten by 16 transport spellings plus three mutations of the request object." The
  secrets surface then advanced past the cluster: `0a1ec20` (SECRET-HOTROTATE #200,
  `force_refresh`) is a later, more capable version than anything in the cluster.
- Question (b): **No.** The cluster's distinctive additional content is the
  mechanical-enforcement machinery (`tools/check_key_egress.py`, Semgrep rules in
  `tools/semgrep-key-egress.yml`, `tests/fixtures/key_egress/`, `test_key_egress_gate.py`)
  that master's own documentation records as defeated, and which master deliberately
  did not adopt. The survived-review subset the cluster produced is already in master.
- Credential-egress note: the ticket says "the chosen variant must be the most
  COMPLETE one". That is round6. But round6's completeness is precisely its defeated
  Semgrep enforcement layer, which master's netutil docstring records as beaten.
  Choosing round6 would resurrect a documented-defeated mechanism, not the smallest
  diff. The fix itself (the choke point + redirect/SSRF tests) already landed via #181.
- Verdict: **CLOSED-DEAD × 3.** Delete all three. Do not open any of them — a PR would
  re-merge `test_provider_key_exfil.py` that is already byte-identical on master and
  re-raise a defeat documented in master's own source. (The live FIX-PROVIDER-KEY-EXFIL
  ticket continues to own the exfil fix; this lane only decides dispositions.)
- NOTE: master's netutil docstring references `credproxy` (credential-injecting
  reverse proxy) as the remaining phase — that is the current frontier, not any of
  these three branches.

## 11. fix/spend-metric-trustworthy — PR-OPENED (recommended)

- Commits: 1 (`3940004df6`)
- Question (a): **Not on master.** Master's `src/charon/spend_limits.py` (from
  `bca6233` "Wave B1") has no `_unpriced_count`, no `record_unpriced`, no
  `unpriced_count` property, and no `_reload_limit` (reload cap from disk). `git
  cherry` reports `+`. `tests/test_spend_metric.py` does not exist on master.
- Question (b): **Yes.** It makes the spend metric trustworthy two ways: (i) tracks
  unpriced calls separately instead of conflating them with priced spend, and (ii)
  reloads `monthly_limit_usd` (and unpriced count) from the persisted state file so a
  live limit change is honored without a restart. Adds 41 lines to spend_limits.py +
  208 lines of tests.
- Merge risk: `git merge-tree` = 0 conflicts. Clean.
- Public-clean: no rig paths/hostnames/tokens in the diff (verified).
- Verdict: **PR-OPENED** (recommended).

## 12. pr164 — CLOSED-DEAD

- Commits: 1 (`44164c60ff`)
- Question (a): **It IS already-merged PR #164.** The branch is named after PR #164.
  PR #164 ("refactor(inert): drop stale refs to deleted charon.capability.actuals
  (CAPABILITY-ACTUALS-DEADREF-CLEANUP)", head `feat/capability-actuals-deadref-cleanup`)
  is state MERGED (`mergedAt 2026-07-24T15:24:56Z`), landing as master commit
  `bb98480` with the same title. The branch's `src/charon/decompose_sizing.py` is
  byte-identical to master's. Its review-log fragment
  (`docs/review-log/CAPABILITY-ACTUALS-DEADREF-CLEANUP.md`) is the same 103-line file
  that landed. The 16-line diff in `tests/test_check_inert_code.py` is master's later
  `roster_issues` tuple evolution (5-tuple vs 4-tuple) — the branch's underlying
  change is already present.
- Question (b): **No.** Nothing this branch carries is absent from master.
- Verdict: **CLOSED-DEAD.** It is a stale mirror of an already-merged PR. Delete.

## 13-14. sub/ft-catalog-seed-contract-fixtures / sub/ft-catalog-seed-fix-v2 — HELD-WITH-REASON

- Commits: contract-fixtures = 2 (`e647748`, `9f4b7e2`);
  fix-v2 = 3 (`e647748`, `75063d5`, `7c4db59`).
- Both fork from the same launcher auto-commit `e647748`
  ("chore(FT-CATALOG-SEED): launcher auto-commit") and from `feat/ft-catalog-seed`
  (itself an ancestor of both). `feat/ft-catalog-seed` is OPEN as **PR #135**
  (`headRefName feat/ft-catalog-seed`, `state OPEN`), carrying the free-tier catalog
  seed content (`free_tier_catalog.py` + `hosted.py` 3 new presets
  `github_models`/`featherless`/`ollama_cloud` + `test_free_tier_catalog.py`).
- Question (a): The fix commit `75063d5` ("fix(contract-tests): forward-compat
  PRESETS assertion for FT-CATALOG-SEED") already landed on master as `7128b31`
  ("fix(contract-tests): forward-compat PRESETS assertion for FT-CATALOG-SEED") —
  `git cherry` prints `-` for it, and master's `tests/test_provider_presets.py` is
  byte-identical to fix-v2's. The remaining 1-line change (adding the 3 presets to
  the contract-test registry in `test_provider_response_contract.py`) is a
  forward-compat fixture that only makes sense once the parent's presets land.
- Question (b): The only surviving delta is that 1-line contract-fixture addition,
  which depends on the parent PR #135's still-unmerged presets.
- Verdict: **HELD-WITH-REASON.** Do not open either as a standalone PR (a 1-line
  fixture does not warrant a PR). Fold the 1-line contract-fixture registry addition
  into the OPEN PR #135 when it merges. fix-v2's substantive content is already on
  master as `7128b31`; contract-fixtures adds only the fixture line.

---

## Cross-cutting notes

- **No forced pushes / raw pushes / rebases of other lanes' branches were performed.**
  This lane is read-then-dispose over the 14 branches; the only writes are the
  dispositions recorded above and this evidence file.
- **Public-clean:** PR-OPENED candidates (connect-omp-wsl, diff-cover-mutmut-adopt,
  spend-metric-trustworthy) carry no rig paths, internal hostnames, absolute local
  paths, or tokens in their diffs vs master.ngs
  grep surfaces in feat/diff-cover-mutmut-adopt's gates.json are pre-existing on
  master (2 entries), not introduced by the branch.
- **Stale base:** all three PR-OPENED candidates fork well behind master head
  (`54e0dc8`). When opening, refresh via GitHub's `update-branch` API first (per the
  ticket's constraint — do NOT use `gh run rerun`, which replays the cached stale
  merge ref). connect-omp-wsl, diff-cover-mutmut-adopt, and spend-metric-trustworthy
  all merge-tree cleanly, so update-branch should be conflict-free.
- **Not this lane's scope:** the live FIX-PROVIDER-KEY-EXFIL ticket owns the exfil
  fix itself; this lane only disposes of the three rescued variants. FT-CATALOG-SEED's
  content is owned by its own ticket/PR #135 — this lane only disposed of the two
  sub-variants.
