# TRIAGE — LANE 1: substrate / coverage / semgrep cluster

Reviewer: agen-kolar (sub-session, lane 1 of 4). Date: 2026-07-24.
Scope: only the 6 branches + 3 worktrees assigned. Nothing deleted. `fleet/board/*` and
`fleet/state/ROADMAP.tsv` untouched.

## HEADLINE

**All six branches are the `feat/work-lease-gate` trap repeated three times over.** Every
cluster (substrate-first gate, coverage meta-gate, semgrep CI) **already landed on master** —
verified not by reading tickets but by byte-comparing the branch's own owned files against
`origin/master` (`git diff <branch>:<file> origin/master:<file>` → empty) and by finding each
ticket in `fleet/board/archive/` with `status: done`.

Net: **0 SALVAGE, 1 PUSH (prior-art preservation only), 6 REAP-recommended, 0 NEEDS-TICKET.**
The one PUSH and the one REAP are the *same* branch: `feat/substrate-first-gate-v2` is
superseded in substance but carried one never-landed artifact, so it was **published first so
the reap is non-destructive**.

## DISPOSITION TABLE

| branch | unique commits (vs origin/master) | uncommitted edits | superseded-by | disposition | evidence |
|---|---|---|---|---|---|
| `feat/substrate-first-gate` | 1 (`981c287`), 204 behind | none (no worktree) | master (landed via `feat/substrate-first-gate-fresh`); also strictly contained in `-v2` | **REAP** | `981c287` is an ancestor of `-v2`. `fleet/checks/substrate-first-gate.sh` on `-v2` is **byte-identical to origin/master**; master additionally carries `fleet/checks/substrate_first_gate.py` (the v2 rewrite) which this v1 lacks. `fleet/board/archive/SUBSTRATE-FIRST-GATE.md` → `status: done`, `branch: feat/substrate-first-gate-fresh`. Pure ancestor of a superseded branch. |
| `feat/substrate-first-gate-v2` | 3 (`981c287`, `5e9de6c`, `c182d7e`), 204 behind | **none** (worktree clean, 0 stashes) | master for all core content | **PUSH (done) → then REAP** | `substrate-first-gate.sh` **SAME** as master. `substrate_first_gate.py` present on master (evolved past the branch's version). `fleet/tests/land-push-ci-gate.test.sh`: master has a **better** fix for the same B5 failure (seeds the sibling copies in the SEED commit so they land on origin/master instead of being copied per-fixture) → `c182d7e` superseded. Residual: see §RESIDUAL below. Pushed to preserve that residual, then reapable. |
| `fix/substrate-first-owns-base-ref` | **0** | none (worktree clean) | already merged | **REAP** | `git rev-list --left-right --count origin/master...` = `78 0` — **zero unique commits**; tip `8e60ea5` is literally a master merge commit (`Merge pull request #233`). Listed by `git branch --merged origin/master`. Remote ref `origin/fix/substrate-first-owns-base-ref` **already deleted** by the fetch prune. `fleet/board/archive/SUBSTRATE-FIRST-OWNS-BASE-REF.md` exists; `chore/retire-substrate-gateparity` says "landed #231 + wired". |
| `feat/coverage-meta-gate` | 1 (`e7aaeea`), 437 behind | none (worktree clean, 0 stashes) | `feat/coverage-meta-gate-rederive` → master | **REAP** (no push needed) | `fleet/checks/rule-coverage.sh` **SAME** as master; `fleet/tests/rule-coverage.test.sh` **SAME** as master. Its `RULE-REGISTRY.tsv` has 90 rows vs master's 105 — master is a **superset**. Already published: `origin/feat/coverage-meta-gate` exists at `e7aaeea`, so reaping the local ref loses nothing even without a push. |
| `feat/coverage-meta-gate-rederive` | 5 (`258ea60`,`2cf51bd`,`6664542`,`fa4ab38`,`a4bf57b`), 186 behind | none (no worktree) | master | **REAP** | `rule-coverage.sh` **SAME**, `rule-coverage.test.sh` **SAME**, `RULE-REGISTRY.tsv` **SAME** (105 rows, `diff` of the key column = empty). Wiring landed too: `origin/master:fleet/preflight.sh` runs the gate every preflight (lines 319-346, auto-registers tracked red `rule-coverage-gap`) and `rig-ci-scope.sh` lists `rule-coverage.test.sh`. `fleet/board/archive/COVERAGE-META-GATE.md` archived with `branch: feat/coverage-meta-gate-rederive`. The other 4 commits are board hygiene for that now-archived ticket. |
| `feat/semgrep-ci-v2` | 3 (`c47ee13`,`bc79a9f`,`2a50f55`), 185 behind | none (no worktree) | master | **REAP** | **All five owned files byte-identical to origin/master**: `.github/workflows/semgrep.yml`, `fleet/checks/semgrep.sh`, `fleet/semgrep-rules/charon-policy.yml`, `fleet/tests/semgrep-canary.test.sh`, `fleet/tests/fixtures/semgrep-known-bad.py`. Includes the version-determinism pin (`2a50f55`) — master has it. `fleet/board/archive/SEMGREP-CI-REQUIRED-CHECK.md` archived. |

### What was pushed

```
origin/feat/substrate-first-gate-v2 == c182d7e55efc0755f284f5d17a91cee0c2d36730  (ls-remote PROVEN)
```

Pushed with `bash fleet/land-push.sh feat/substrate-first-gate-v2 \
/home/stack/charon-private-wt/SUBSTRATE-GATE-V2 --gate true`.
**`--gate true` was deliberate**: this is a 204-behind branch whose real gate would be stale and
would red on unrelated drift. This is **publish-for-preservation, not landing** — no PR was
opened, nothing was merged. land-push warned `no PR exists … ALLOWING the push
UNVERIFIED-BY-CI` and that is the intended posture here.

## RESIDUAL: the one piece of `-v2` that never landed

`feat/substrate-first-gate-v2` is the only branch in this lane carrying content absent from
master:

| file | state | status |
|---|---|---|
| `fleet/tests/large-file-guard.test.sh` | +110 lines, **ABSENT on master** | red-proof suite for `fleet/checks/large-file-guard.sh` |
| `fleet/tests/rig-ci-scope.test.sh` | rename of `rig-ci.test.sh` +57, **ABSENT on master** (master still has `rig-ci.test.sh`) | red-proof suite for `fleet/checks/rig-ci-scope.sh` |

**This is NOT a NEEDS-TICKET — a live P1 ticket already owns exactly these two paths.**
`origin/master:fleet/board/META-GATE-FINDINGS-ZERO.md`:

```
priority: 1
branch: feat/meta-gate-findings-zero
owns: fleet/GATE-CREATION-STANDARD.md, fleet/tests/large-file-guard.test.sh, fleet/tests/rig-ci-scope.test.sh
depends_on: GITHUB-LIMITS-HARDENING, HANDOFF-GATE-NONBYPASSABLE
```

**Do not "salvage" the `-v2` versions into that ticket.** The ticket's own `real-dep` blocks say
why, and they are correct: `GITHUB-LIMITS-HARDENING` is actively changing `large-file-guard.sh`
(routing gh calls through `gh-cache.sh`) and `HANDOFF-GATE-NONBYPASSABLE` is changing
`rig-ci-scope.sh`. A red-proof written against the pre-change behaviour is "a test that passes
for the wrong reason". The `-v2` files were written against the **old** behaviour, so they are
**prior art / reference only**, not droppable-in code.

**Recommended action (board-owner's call, another sub owns the board):** append one `prior-art:`
line to `META-GATE-FINDINGS-ZERO.md` so the builder does not start from zero:

```
prior-art: |
  origin/feat/substrate-first-gate-v2 (c182d7e) carries a 110-line
  fleet/tests/large-file-guard.test.sh and a rig-ci.test.sh -> rig-ci-scope.test.sh rename
  (+57). Both were written against the PRE-change behaviour of their SUTs, so per this
  ticket's own real-dep blocks they are REFERENCE ONLY — reuse the hermetic mktemp fixture
  shape and the red-proof marker wording, re-derive the assertions against final behaviour.
  Branch published 2026-07-24 for exactly this reason; safe to reap the local ref.
```

## PRIOR-ART CROSS-CHECK

`origin/master:fleet/session-notes/rig-salvage-triage.md` (§5) triaged `-v2` previously and
concluded **STILL-MISSING** — "core gate files ABSENT on master". **That conclusion is now
stale and this review supersedes it**: the gate landed afterwards via
`feat/substrate-first-gate-fresh`, and master carries both `substrate-first-gate.sh` (identical)
and the newer `substrate_first_gate.py`. Anyone re-reading that note should not re-derive the gate.

## TICKET PROPOSALS

**None.** No branch in this lane contains live work lacking a board ticket. The only unlanded
content (§RESIDUAL) is already owned by the live P1 `META-GATE-FINDINGS-ZERO`; the proposal
above is a one-line `prior-art:` amendment to an **existing** ticket, not a new ticket.

## OUT-OF-LANE OBSERVATIONS (flagged, not acted on)

1. `feat/semgrep-ci-v2` and local `feat/semgrep-ci-required-check` are the **same SHA**
   (`2a50f55`) — a duplicate local alias. Only `-v2` was in my lane; the twin is also dead by
   the same evidence.
2. `origin/feat/semgrep-ci-required-check` is a **stale remote branch** at `f42fadc` (2 commits,
   missing the `2a50f55` version-pin). Master already has the pinned content. Safe remote reap,
   but out of my lane.
3. `/home/stack/wt/coverage-meta-gate` is the only owned worktree **outside** the standard
   `/home/stack/charon-private-wt/` root — worth normalising when reaped.

## METHOD / CONSTRAINTS HONOURED

- Nothing deleted. Worktrees left in place, all three clean (`status --porcelain -uall` empty,
  `stash list` empty on each) — so **no SALVAGE commit was needed and the work-lease bypass was
  never used**.
- Supersession proven by content, not by ticket text: per-file
  `git diff <branch>:<f> origin/master:<f>` across every file each branch touched, plus
  `git branch --merged`, `git log origin/master..<branch>`, `git cherry -v`.
  (`git cherry` reported "+" for all of these — a **false negative**, since the branches are
  185-437 behind and landed via re-derive rather than cherry-pick. Patch-id equivalence alone
  would have wrongly marked all six as live work; the byte-compare is what settled it.)
- No writes to `fleet/board/*` or `fleet/state/ROADMAP.tsv`. No protected branch/worktree touched.
