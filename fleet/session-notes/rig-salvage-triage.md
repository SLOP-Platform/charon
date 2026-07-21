# RIG stranded-branch salvage triage

Repo: `Nnyan/charon-private` (local `/home/stack/charon-private`)
Current master: `51123ea` (handoff ki-adi-mundi).
Method: for each branch, `merge-base origin/master <branch>` → TRUE delta =
`<merge-base>..<branch>` (ignores the vs-current-master mass-delete noise). Supersession
verified by comparing branch-tip **file/blob content** against `origin/master` (a 0-line
diff or an identical blob SHA = master already contains the exact work) plus the master
commit log (matching `#PR` messages) and board state.

Key fact that explains the "misleading mass-deletes": four of the five branches share
merge-base `cf07e05` and are **21 commits behind** master. Diffing them against *current*
master shows ~150 files "deleted" — those files simply didn't exist yet when the branch was
cut. The TRUE delta is tiny by comparison.

---

## 1. fix/land-push-ci-and-scope (LAND-PUSH-HARDEN, 4 commits) — tip 2709346

- **merge-base:** `cf07e05` (#121 rig-ci first gate); master is **21 commits ahead**.
- **TRUE delta stat:** 6 files, +1009/-12
  - land-push.sh (+310), rig-ci-scope.sh (+71/-), rig-ci.yml (±28),
    land-push-ci-gate.test.sh (+504 new), rig-ci.test.sh (+108), land-safety.test.sh (empty).
- **What it does:** Hardens `land-push.sh` and the rig CI scope check — closes fail-open
  modes (the "11th fail-open mode", dead `find` guard), stops the CI gate emitting a FALSE
  GREEN receipt, scopes the board gate in state-less checkouts, fails CLOSED on
  red/pending CI and on an unresolvable diff base ("vacuous-green").
- **Supersession evidence:** Per-file blob comparison vs `origin/master`:
  - `land-push.sh` → **diff 0** (identical). Landed via `e9365cd` #124 ("enforce CI
    locally + stop phantom board REDs") and `caa2126` #134 (net-diff rebuild of #132).
  - `rig-ci.yml`, `land-push-ci-gate.test.sh`, `rig-ci.test.sh`, `land-safety.test.sh` →
    **all diff 0** (identical to master).
  - `rig-ci-scope.sh` → only **23 diff lines**, and they are the branch *lacking* two
    `CI_SUITES` entries (`sync-checkouts.test.sh`, `stranded-work.test.sh`) that master
    ADDED later via #128 / #134. i.e. master is a strict superset; the "diff" is
    stale-base noise, not intended branch work. All the branch's fail-closed logic is
    already present.
- **VERDICT: SUPERSEDED.** Every intended change is byte-identical on master (#124 + #134).
- **Recommend:** DROP. Delete the branch; no re-derivation needed.

---

## 2. fix/dogfood-eval-guard (2 commits) — tip c420ffe

- **merge-base:** `cf07e05`; master **21 ahead**.
- **TRUE delta stat:** 2 files, +483/-7 — dogfood-eval.sh (+94), dogfood-eval-guard.test.sh
  (+396 new).
- **What it does:** Guards the last unguarded destruction path in `dogfood-eval.sh` and
  adds a guard-test suite that actually fails on revert (review F1-F6).
- **Supersession evidence:** Both target files **diff 0** vs `origin/master`. Landed as
  `f908953` #125 ("guard three unguarded destruction sites"). Master's
  `fleet/tests/dogfood-eval-guard.test.sh` and `fleet/benchmark/dogfood-eval.sh` are
  byte-identical to the branch tip.
- **VERDICT: SUPERSEDED.**
- **Recommend:** DROP.

---

## 3. fix/branch-reaper-safety-v2 (2 commits) — tip 4c5ebc5

- **merge-base:** `cf07e05`; master **21 ahead**.
- **TRUE delta stat:** 2 files, +863/-94 — branch-reaper.sh (+490/-), branch-reaper.test.sh
  (+467).
- **What it does:** Real fail-closed guards + rig-awareness + canonical-glob validation
  for the branch reaper, and routes removal through leak-guard (never reap on an
  unvouchable remote ref).
- **Supersession evidence:** Both files identical to master by **blob SHA**
  (`branch-reaper.sh` = `17fd3fd` on both branch tip and `origin/master`; test file diff 0).
  Landed as `e4ae628` #123 (matching commit message). Master's branch-reaper.sh contains 8
  leak-guard references — the second commit's leak-guard routing is present too.
- **VERDICT: SUPERSEDED.**
- **Recommend:** DROP.

---

## 4. feat/droid-lifecycle-reap-v2 (1 commit) — tip 033448e

- **merge-base:** `e4ae628` (#123); master **20 ahead**.
- **TRUE delta stat:** 7 files, +1039/-9 — reap-orphans.sh (+272 new), fleet-droid.sh
  (+152), foreman.sh (+28), leak-guard.sh (+16), test_droid_reap.sh (+433 new),
  worktree-leak-guard.test.sh (+17), review-log DROID-LIFECYCLE-REAP.md (+130).
- **What it does:** Net-diff rebuild of #103 — droid-lifecycle orphan reaping
  (`reap-orphans.sh`) wired into fleet-droid/foreman with leak-guard integration and tests.
- **Supersession evidence:** All five code files (reap-orphans.sh, fleet-droid.sh,
  foreman.sh, leak-guard.sh, test_droid_reap.sh) **diff 0** vs master;
  `reap-orphans.sh` blob = `45e146a` on both. Landed as `0314d5d` #126 (identical commit
  message: "fix(droid-lifecycle-reap): net-diff rebuild of #103 onto master").
- **VERDICT: SUPERSEDED.**
- **Recommend:** DROP.

---

## 5. feat/substrate-first-gate-v2 (3 commits) — tip c182d7e

- **merge-base:** `e8d25d3` (handoff ahsoka-tano); master only **9 ahead** (freshest branch).
- **TRUE delta stat:** 32 files, +1662/-38. Core: `substrate_first_gate.py` (+793 new),
  `substrate-first-gate.sh` (+82 new), `substrate-first-gate.test.sh` (+395 new),
  `large-file-guard.test.sh` (+110 new). Plus rig-ci.yml (+8), rig-ci-scope.sh (±40),
  WORKFLOW.md, validate_board.sh (+28), EVAL-REGISTRY.md (+55), GATE-GAP-LEDGER.tsv (+1),
  ~19 `board/*.md` frontmatter touches (3-6 lines each), and a rename
  `rig-ci.test.sh → rig-ci-scope.test.sh`.
- **What it does:** Adds the **substrate-first gate** — fires the build-vs-adopt "prior
  question" at DECISION time (board-ticket create/change), not session start. v2 replaced
  the v1 hand-rolled ~285-line frontmatter/markdown parser (9 adversarial evasions found)
  with a pinned-PyYAML parser (`substrate_first_gate.py`), keeping only the novel
  cross-check slice. This is the mechanization of the now-TOP §0 doctrine ("adopt-first,
  hand-roll is last-resort").
- **Supersession evidence:**
  - Core gate files **ABSENT on master**: `fleet/checks/substrate-first-gate.sh`,
    `fleet/checks/substrate_first_gate.py`, `fleet/tests/substrate-first-gate.test.sh`
    (`git ls-tree origin/master` returns nothing). `git grep substrate-first` on master
    hits only handoff docs and the `GATEWAY-LITELLM-ADOPT.md` board ticket — concept
    referenced, gate never built. **No dedicated board ticket** for it either.
  - PARTIAL overlaps already on master (do NOT re-derive these): `large-file-guard.sh`
    landed via #129 (`68efdef`) — but the branch's `large-file-guard.test.sh` (dedicated
    test) is NOT on master (master covers it under `test_github_limits.sh`); minor.
    `EVAL-REGISTRY.md` exists on master (rows added by `5f196a6`) — the branch's +55 will
    partly conflict/overlap. The ~19 board frontmatter edits and rig-ci-scope.sh/WORKFLOW
    edits are supporting scaffolding the gate parses; some diverge from master's current
    board state (9-commit drift) and would need reconciliation on re-derive.
- **CAVEAT:** introduces a **PyYAML runtime dependency** (pinned) in the rig tool. This is
  rig tooling (`fleet/`), not the product's `dependencies=[]` surface, and it directly
  embodies the "adopt substrate" doctrine — but flag it for the operator since dependency
  posture is a standing sensitivity.
- **VERDICT: STILL-MISSING** (core ~1290-line gate genuinely absent; mechanizes the current
  top directive), **PARTIALLY-SUPERSEDED** on the periphery (large-file-guard impl,
  EVAL-REGISTRY rows already on master).
- **Recommend:** RE-DERIVE the core substrate gate (`.sh` + `.py` + `.test.sh`) onto current
  master via net-diff rebuild — same pattern used for #126/#134. Skip/reconcile the
  peripheral edits (large-file-guard test optional; EVAL-REGISTRY + board frontmatter must
  be rebased onto master's current versions, not the branch's stale copies). Confirm the
  PyYAML dependency with the operator first. Open a board ticket (none exists).

---

## Summary table

| Branch | Verdict | Recommend |
|---|---|---|
| fix/land-push-ci-and-scope | SUPERSEDED | DROP — all on master (#124 + #134) |
| fix/dogfood-eval-guard | SUPERSEDED | DROP — all on master (#125) |
| fix/branch-reaper-safety-v2 | SUPERSEDED | DROP — all on master (#123, blob-identical) |
| feat/droid-lifecycle-reap-v2 | SUPERSEDED | DROP — all on master (#126, blob-identical) |
| feat/substrate-first-gate-v2 | STILL-MISSING (core) / PARTIALLY-SUPERSEDED (edges) | RE-DERIVE core gate onto master; reconcile peripheral edits; confirm PyYAML dep; open board ticket |
