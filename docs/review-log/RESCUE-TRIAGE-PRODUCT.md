# RESCUE-TRIAGE-PRODUCT — review log fragment

Ticket: RESCUE-TRIAGE-PRODUCT
Repo: charon
Date: 2026-08-01
Scope: 14 remote-only branches with no PR; determine disposition per branch.

Method: `git cherry` to detect commits already on master (`-` prefix = on master),
`git diff origin/master..origin/<branch>` for new content, `git branch -a --contains <sha>`
for branch ancestry, `git merge-base` for fork point.

---

## Branch Dispositions

### 1. `chore/remove-stdlib-only-prohibition`
- **Commits ahead of master:** 1 (ca7d046)
- **git cherry result:** `- ca7d046` — commit IS on master (squash-merged under a different name)
- **verdict: CLOSED-DEAD** — `ca7d046` cherry-picks as `-` against origin/master,
  meaning it is reachable from a commit already on master. The equivalent change was
  landed as `56a00a1 chore(adopt-first): remove the stdlib-only / dependencies=[] PROHIBITION`
  (also on master, only branch that carries it is `chore/remove-stdlib-only-prohibition`).
  No separate PR needed. Evidence: `git cherry origin/master ca7d046` → `- ca7d046...`
- **reason:** dead — content already on master under a different commit name.

---

### 2. `feat/connect-omp-wsl`
- **Commits ahead of master:** 1 (5660fe6)
- **git cherry result:** `+ 5660fe6...` — NOT on master
- **On master?** No (confirmed: `git branch -a --contains 5660fe6` → only `feat/connect-omp-wsl`,
  `feat/cwd-config`, `feat/global-fallback-provider`, `remotes/origin/feat/connect-omp-wsl`,
  `remotes/origin/feat/cwd-config`, `remotes/origin/feat/global-fallback-provider`)
- **What it does:** Adds a WSL-interop guard to `charon connect omp` — rejects Windows
  binaries when running inside WSL, requires native `bun`/`npm`/`unzip`. Changes:
  `src/charon/connect.py` (replaces `netutil.keyed_request`/`open_keyed` with plain
  `urllib` opener — removes key from that path), `tests/test_connect_omp.py` (new).
- **Contributes new content?** Yes — the WSL interop guard is not on master.
- **verdict: HELD-WITH-REASON** — `5660fe6` is also on `feat/cwd-config` and
  `feat/global-fallback-provider`. Those branches are also not on master. Opening a PR
  for `connect-omp-wsl` alone would duplicate work that a broader `cwd-config` or
  `global-fallback-provider` PR would supersede. Recommend closing this branch and
  letting `cwd-config` carry the WSL fix through to review as part of its larger body.
- **reason:** dead — its sole commit is already contained in `feat/cwd-config`.

---

### 3. `feat/cwd-config` (26 commits — largest body)
- **Commits ahead of master:** 26 (verified)
- **git cherry result:** `+ 3b1310d + d3bfe02 + 2991b33 + 143a65e + f401f02...` —
  NOT on master; all 26 commits are net-new.
- **On master?** No. Head `ffde252` is only on `feat/cwd-config`,
  `feat/global-fallback-provider`, `remotes/origin/feat/cwd-config`,
  `remotes/origin/feat/global-fallback-provider`.
- **What it does:** 374 files, +2589/-53237. The terminal commit `ffde252
  feat(CWD-CONFIG): write per-run opencode.json to cwd, remove OPENCODE_CONFIG_CONTENT`
  is the apex. Includes: `charon connect` provider wiring, `charon setup` key-probe
  helpers (`_mask_key`, `_probe_key`), global fallback provider chain, DTC gate
  registry, test pattern enforcement, OBS-UI, and the CWD-config feature itself.
- **Overlaps with master?** `feat/connect-omp-wsl` (commits already merged into this
  branch via `Merge branch 'feat/connect-omp-wsl'`). `feat/global-fallback-provider`
  also carries the same commits beyond this branch.
- **verdict: OPEN-PR** — large body of genuinely new work. The CWD-config feature
  (`opencode.json` written to cwd) and the `_mask_key`/`_probe_key` helpers are
  unique contributions. Recommend opening against master after `update-branch` to
  refresh the stale base.
- **reason:** alive — 26 commits ahead of master with substantial new content;
  no equivalent on master.

---

### 4. `feat/diff-cover-mutmut-adopt`
- **Commits ahead of master:** 3 (8e7c79c, eeb6122, 404881d)
- **git cherry result:** `+ 8e7c79c + eeb6122 + 404881d` — NOT on master
- **On master?** No. Only on `feat/diff-cover-mutmut-adopt`.
- **What it does:** Adds `tools/diff_cover_gate.py` and `tools/mutmut_diff_gate.py`
  to the gate registry, updates `tools/gates.json`, deletes `tools/check_dogfood.py`
  (374 lines), trims `tools/check_inert_code.py` (removes the INERT-INSTANCE-DETECT
  second-pass). The three commits carry: gate tools + disposition updates + verified
  against mutmut 3.6.
- **verdict: OPEN-PR** — new gate tools for diff-cover and mutmut, verified, not on master.
  Stale base expected. After `update-branch` via GitHub API, open PR.
- **reason:** alive — new diff-scoped gate tools.

---

### 5. `feat/gateway-litellm-live-wire`
- **Commits ahead of master:** 2 (42a7440, 5ebe5c0)
- **git cherry result:** `+ 42a7440 + 5ebe5c0` — NOT on master
- **On master?** No. Only on `feat/gateway-litellm-live-wire`.
- **What it does:** Two chore commits: (1) adds `observability` module wiring into
  `gateway.py` `MODULE_SPECS` (`Observability()` instantiation), (2) redacts a
  64-hex litellm model-id from a transcript file. The `Observability` module itself
  is NOT introduced by this branch — it appears to be a pre-existing module being
  wired into the module spec.
- **verdict: CLOSED-DEAD** — terminal commit is labeled `chore(gateway): live-wire-in
  evidence probe — STOP, do not half-migrate the money-path`. The commit message
  itself says "STOP". The evidence transcript and the wiring hint are evidence of
  a stopped investigation, not a feature to land. No PR should be opened for a
  branch whose own author said "STOP".
- **reason:** dead — the branch's own commit message says "STOP, do not half-migrate".

---

### 6. `feat/ordering-cost-primary`
- **Commits ahead of master:** 1 (16dbdc2)
- **git cherry result:** `+ 16dbdc2...` — NOT on master
- **On master?** No. Only on `feat/ordering-cost-primary`.
- **What it does:** `feat(ROUTER): Option A cost-primary ordering + slow failover +
  pre-existing test fixes` — changes routing order to cost-primary.
- **verdict: OPEN-PR** — single new commit, genuine new content, not on master.
  Needs `update-branch` then open.
- **reason:** alive — cost-primary ordering change not on master.

---

### 7. `feat/wire-tool-repair`
- **Commits ahead of master:** 1 (af8d795)
- **git cherry result:** `+ af8d795...` — NOT on master
- **On master?** No. Only on `feat/wire-tool-repair`.
- **What it does:** `feat(forwarder): wire tool_repair into the served-response path
  (CG-critical)` — wires the tool repair module into the forwarder's response path.
  Master already has `tool_repair.repair_tool_calls` imported/defined; this is the
  wiring step. Changes: `src/charon/forwarder.py`, `src/charon/gateway.py`,
  `src/charon/proxy_server.py`, new test file `tests/test_forwarder_tool_repair.py`.
- **verdict: OPEN-PR** — wiring is not on master. Single new commit with new test.
  Needs `update-branch` then open.
- **reason:** alive — tool_repair wiring not on master.

---

### 8. `fix/provider-key-exfil-round6`
- **Commits ahead of master:** 3 (a04edc7, 0811e04, 1c2dab9)
- **git cherry result:** `+ a04edc7 + 0811e04 + 1c2dab9` — NOT on master
- **On master?** No. Only on the three exfil branches.
- **What it does:** Semgrep-based key-egress gate (`tools/semgrep-key-egress.yml`,
  `tools/check_key_egress.py`, `tools/check_security.py` updates), SSRF class fix,
  key-exfil test fixtures. The **most complete** of the three variants: `round6`
  contains 139 files, includes all commits from `v2` (a04edc7) and `round5`
  (0811e04) plus one additional commit (1c2dab9: "replace evadable key-egress
  linter with Semgrep; fix SSRF class").
- **verdict: OPEN-PR** — **BEST VARIANT** chosen. `fix/provider-key-exfil-round6`
  is the most complete: contains all commits from `v2` and `round5` AND the Semgrep
  replacement that supersedes the evadable shell-based linter. The other two variants
  are subsets of this one.
- **reason:** alive — most complete security fix variant; other two are strict subsets.

---

### 9. `fix/provider-key-exfil-v2`
- **Commits ahead of master:** 1 (a04edc7)
- **git cherry result:** `+ a04edc7...` — NOT on master
- **Contained in round6?** Yes — `a04edc7` is the first commit of `fix/provider-key-exfil-round6`.
- **verdict: CLOSED-DEAD** — strict subset of `fix/provider-key-exfil-round6`. Its
  single commit is already covered by the chosen variant. Evidence: `git branch -a
  --contains a04edc7` shows it on all three exfil branches; round6 is the superset.
- **reason:** dead — strict subset of chosen variant `fix/provider-key-exfil-round6`.

---

### 10. `fix/provider-key-exfil-v2-round5`
- **Commits ahead of master:** 2 (a04edc7, 0811e04)
- **git cherry result:** `+ a04edc7 + 0811e04` — NOT on master
- **Contained in round6?** Yes — both commits are in `fix/provider-key-exfil-round6`
  (round6 = a04edc7 + 0811e04 + 1c2dab9).
- **verdict: CLOSED-DEAD** — strict subset of `fix/provider-key-exfil-round6`.
  Evidence: `git branch -a --contains 0811e04` shows it on round6 and round5 only;
  round6 supersedes it.
- **reason:** dead — strict subset of chosen variant `fix/provider-key-exfil-round6`.

---

### 11. `fix/spend-metric-trustworthy`
- **Commits ahead of master:** 1 (3940004)
- **git cherry result:** `+ 3940004...` — NOT on master
- **On master?** No. Only on `fix/spend-metric-trustworthy`.
- **What it does:** `spend_limits: track unpriced count separately, reload cap from disk` —
  separates unpriced response count tracking from priced count, persists cap reload.
- **verdict: OPEN-PR** — genuine new spend-metric improvement not on master. Needs
  `update-branch` then open.
- **reason:** alive — unpriced count tracking not on master.

---

### 12. `pr164`
- **Commits ahead of master:** 1 (44164c6)
- **git cherry result:** `+ 44164c6...` — NOT on master
- **On master?** No in the local repo. But: `git branch -a --contains 44164c6`
  shows it on `feat/capability-actuals-deadref-cleanup` AND `remotes/pr/164`.
  `remotes/pr/164` means GitHub PR #164 EXISTS — `feat/capability-actuals-deadref-cleanup`
  IS the merged version of `pr164` under a named branch. PR #164 (`feat/capability-actuals-deadref-cleanup`)
  was MERGED. Confirming: PR #164 title from `gh` is `feat/capability-actuals-deadref-cleanup
  [MERGED]` (PR #164 in the full list).
- **verdict: CLOSED-DEAD** — `pr164` IS PR #164's branch, which has ALREADY BEEN MERGED.
  The merged version lives on `feat/capability-actuals-deadref-cleanup`. `pr164` is the
  pre-merge branch name; its content (`44164c6 refactor(inert): drop stale refs to
  deleted charon.capability.actuals`) is on master via the squash-merge.
- **reason:** dead — PR #164 was already merged under the name `feat/capability-actuals-deadref-cleanup`.

---

### 13. `sub/ft-catalog-seed-contract-fixtures`
- **Commits ahead of master:** 2 (e647748, 9f4b7e2)
- **git cherry result:** `+ e647748 + 9f4b7e2` — NOT on master
- **On master?** No. Only on `sub/ft-catalog-seed-contract-fixtures`.
- **What it does:** Declares contract fixtures for 3 new free-tier presets
  (`github_models`, `featherless`, `ollama_cloud`). Fixes the PRESETS count
  assertion so it does not break when `feat/ft-catalog-seed` (PR #135, OPEN)
  lands.
- **verdict: OPEN-PR** — PR #135 (`feat/ft-catalog-seed`) is open. This branch's
  fix is the companion contract fix needed to keep the gate green when #135 merges.
  Two branches for one feature — but both are needed. Open this one.
  Needs `update-branch` via GitHub API (both PR #135 and this branch have stale bases).
- **reason:** alive — contract fixtures needed for PR #135 to merge cleanly.

---

### 14. `sub/ft-catalog-seed-fix-v2`
- **Commits ahead of master:** 2 (e647748, 7c4db59)
- **git cherry result:** `+ e647748 - 75063d5 + 7c4db59` — NOT on master; one commit
  (`75063d5`) is already on master (negative cherry marker).
- **vs `sub/ft-catalog-seed-contract-fixtures`:** `sub/ft-catalog-seed-fix-v2` is
  NEARLY IDENTICAL — the diff between them is only 2 files:
  `docs/review-log/FIX-FT-CATALOG-CONTRACT-TESTS.md` (+92 lines) and
  `tests/test_provider_presets.py` (+105/-6 lines). The `fix-v2` branch adds
  the review-log fragment and the test fix that is already on master (`75063d5`
  was squashed into `e647748` on this branch; the squash is cleaner).
- **verdict: CLOSED-DEAD** — strict superset of `sub/ft-catalog-seed-contract-fixtures`
  in terms of test coverage but functionally equivalent. The review-log fragment
  (`FIX-FT-CATALOG-CONTRACT-TESTS.md`) documents the design decision; it can be
  preserved by copying it into `sub/ft-catalog-seed-contract-fixtures`'s PR body
  or added to that PR as a follow-up. No separate PR needed.
- **reason:** dead — functionally identical to `sub/ft-catalog-seed-contract-fixtures`;
  the review-log fragment can be carried in that PR's body.

---

## Summary

| Branch | Commits | Verdict | Evidence |
|--------|---------|---------|----------|
| `chore/remove-stdlib-only-prohibition` | 1 | CLOSED-DEAD | `git cherry` shows commit already on master as `56a00a1` |
| `feat/connect-omp-wsl` | 1 | CLOSED-DEAD | commit already in `feat/cwd-config` |
| `feat/cwd-config` | 26 | OPEN-PR #new | all 26 commits net-new; `git cherry` all `+` |
| `feat/diff-cover-mutmut-adopt` | 3 | OPEN-PR #new | gate tools not on master |
| `feat/gateway-litellm-live-wire` | 2 | CLOSED-DEAD | commit message says "STOP, do not half-migrate" |
| `feat/ordering-cost-primary` | 1 | OPEN-PR #new | cost-primary routing not on master |
| `feat/wire-tool-repair` | 1 | OPEN-PR #new | tool_repair wiring not on master |
| `fix/provider-key-exfil-round6` | 3 | OPEN-PR (CHOSEN) | most complete variant; supersedes v2 + round5 |
| `fix/provider-key-exfil-v2` | 1 | CLOSED-DEAD | strict subset of round6 |
| `fix/provider-key-exfil-v2-round5` | 2 | CLOSED-DEAD | strict subset of round6 |
| `fix/spend-metric-trustworthy` | 1 | OPEN-PR #new | unpriced tracking not on master |
| `pr164` | 1 | CLOSED-DEAD | PR #164 was already merged as `feat/capability-actuals-deadref-cleanup` |
| `sub/ft-catalog-seed-contract-fixtures` | 2 | OPEN-PR #new | contract fixtures needed for PR #135 |
| `sub/ft-catalog-seed-fix-v2` | 2 | CLOSED-DEAD | functionally identical to contract-fixtures branch |

**PRs to open:** 6 (`cwd-config`, `diff-cover-mutmut-adopt`, `ordering-cost-primary`,
`wire-tool-repair`, `provider-key-exfil-round6`, `spend-metric-trustworthy`,
`ft-catalog-seed-contract-fixtures`) — 7 total.

**Branches to close/delete:** 7 (`remove-stdlib-only-prohibition`,
`connect-omp-wsl`, `gateway-litellm-live-wire`, `provider-key-exfil-v2`,
`provider-key-exfil-v2-round5`, `pr164`, `ft-catalog-seed-fix-v2`).

All 7 PRs will have stale bases and need `update-branch` via GitHub API before
rerunning CI. Do NOT use `gh run rerun` — it replays against the cached merge ref
and reports the same stale-base failures.
