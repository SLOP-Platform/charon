# BOARD-WRITE-LOCK — status / resume note (session agen-kolar, 2026-07-24)

Ticket: `fleet/board/BOARD-WRITE-LOCK.md` (repo charon-private, branch `fix/board-write-lock`, P0).
Worktree: `/home/stack/charon-private-wt/BOARD-WRITE-LOCK` (off `origin/master` dfdcc22).
Lease: acquired normally via the MAIN checkout's `work-lease.sh acquire BOARD-WRITE-LOCK`.
**`WORK_LEASE_BYPASS=1` was NOT used.**

Status: **mechanism BUILT, tested, and red-proofed by execution.** Not landed, not reviewed.

---

## 1. Board-mutation choke points — enumerated by grep, not guessed

Guarded set = `fleet/board/**` (171 active tickets) + `fleet/state/ROADMAP.tsv` (the only
git-tracked shared file under the otherwise-gitignored `fleet/state/*`; see `.gitignore`
`!fleet/state/ROADMAP.tsv`).

**The finding that decides the whole design: there is essentially NO script choke point.**

| Path | What it does to board state | Locked before? |
|---|---|---|
| `fleet/retire-done.sh:51` | `git -C "$FLEET" mv board/$id.md board/archive/$id.md` — **the only script that mutates a tracked board file**, and it STAGES the rename into the shared main-checkout index | no |
| `fleet/decompose.sh:194` (`BOARD_DIR`) | writes NEW sub-ticket files into `fleet/board/` | no |
| `fleet/state/ROADMAP.tsv` | **zero writers.** `report.sh` / `roadmap-html.sh` / `wci-actions.sh` only READ it. Every mutation is a direct agent file write | no |
| `fleet/done.sh`, `release.sh`, `reject.sh`, `claim.sh`, `loop-guard.sh`, `submit.sh`, `reap-orphans.sh`, `reconcile-*.sh` | write `fleet/state/{done,claims,submitted,needs-push,loop-guard}/…` — **gitignored runtime markers, not board files**. `claim.sh:207` already flocks `state/lock` | n/a |
| `fleet/board.sh`, `validate_board.sh`, `foreman.sh`, `_lib.sh`, `project-audit.sh`, `launch-plan.sh` | read-only over the board | n/a |

So: **agents edit board files with Edit/Write, and there is no function to flock.**
Confirmed by grep for `sed -i|>>|tee|mv|cp` against `board/`/`ROADMAP.tsv` across `fleet/*.sh`
— one hit total (retire-done.sh:51).

### The two commit-time defects (both real, both 2026-07-24)

* **`fleet/land.sh:341-342`** — `git add "${LAND_STAGE[@]}" && git commit -q -m "$MSG"`.
  LAND-DIRTY-SCOPE correctly scoped the **`git add`** but left the **`git commit` BARE**, and a
  bare `git commit` takes the **whole index**. Combined with retire-done.sh leaving a staged
  rename in that same shared index, this is exactly how a lane's `git mv` was swept.
  **This is the concrete sweeper and it is still live.** One-line fix:
  `git commit -q --only -m "$MSG" -- "${LAND_PATHS[@]}"`.
* `fleet/work-lease.sh:196` `is_sanctioned_msg()` — the main-checkout `commit-msg` gate
  **explicitly whitelists** any message containing `board-hygiene`, with **no lock and no
  pathspec scope**. That whitelist is the open door.

---

## 2. Enforcement approach chosen — and why the alternatives were rejected

**Chosen: the COMMIT is the choke point, enforced by the `pre-commit` hook, keyed on a
per-commit token that only the locked path can mint.**

`board-lock.sh commit` runs `BOARD_LOCK_COMMIT=<token> git commit --only -- <paths>`. The hook
(a child of that `git commit`) inherits the env var and compares it to the `token:` field of the
live holder record. Any other route — an agent's own `git add` + `git commit` — has no token and
is **REFUSED (exit 4)** with the exact command to use instead.

Why this and not the others:

* *Advisory lock + "please call acquire"* — **rejected**: that is verbatim the convention that
  already failed twice. An unenforceable rule is what this ticket exists to replace.
* *Lock the edit, not the commit* — **impossible**: agents edit with Edit/Write; there is no call
  to intercept (see §1).
* *Commit-time concurrent-modification detection only (no lock)* — **rejected as insufficient**:
  it catches (b) master-moved but not (a) index-sweeping, because the sweeper's own index looks
  perfectly consistent to it.
* *Env-token in the agent's shell across tool calls* — **rejected**: this harness does not persist
  shell state between Bash calls. Hence a durable holder RECORD (`state/board-lock`) plus a token
  scoped to the single `git commit` invocation, so it cannot leak into a later ad-hoc commit.

Properties delivered: `flock -w` on **`fleet/state/lock` — the SAME lock file** claim.sh:207 /
work-lease.sh / lease-enqueue.sh / review-pool.sh / sync-checkouts.sh use (no second lock forked);
fail-closed on flock timeout or a missing `flock` binary (exit 70); HEAD pinned at `acquire` and
compared at `commit` so "master moved under me" is **refused (exit 3)**, never silently proceeded;
`git commit --only -- <paths>` so a foreign staged entry is neither swept nor consumed; stale
bounded by `BOARD_LOCK_STALE_S` (900s) with **dead holder → loud reclaim** (no deadlock) and
**live holder → refuse, explicit `steal --force` required** (never silently stealable); every
reclaim/steal/bypass appended to `state/board-lock.log`.

---

## 3. New file vs extending `work-lease.sh` — the reasoning

`work-lease.sh` was the preferred host and I did **not** use it. **Proof, not preference:**

`WORK-LEASE-WORKTREE-RESOLVE` **owns** `fleet/work-lease.sh` (+ `fleet/hooks/*`,
`fleet/tests/work-lease.test.sh`) and is **actively claimed** — `fleet/state/claims/WORK-LEASE-WORKTREE-RESOLVE`
exists, worktree `/home/stack/charon-private-wt/WORK-LEASE-RESOLVE`, branch
`fix/work-lease-worktree-resolve` @ `5d951e8`, carrying **+57/-8 in work-lease.sh** with hunks at
`@@ -190`, `@@ -201`, `@@ -224`, `@@ -241`, `@@ -255`, `@@ -272`, `@@ -287` — i.e. **at BOTH ends of
`cmd_pre_commit`** and through `cmd_install`/`cmd_ensure`, which is precisely where board-lock
subcommands and their dispatch arm would have to go. Every insertion point conflicts.
BRIEF-PREAMBLE §9: never two writers on one file. (Its lease heartbeat is ~6h stale, so the lane
is idle, but the ticket is LIVE on the board and its branch is unlanded.)

→ `fleet/board-lock.sh` is a new file **by necessity, and it is explicitly transitional**: the
ticket's D&S carries the follow-up to fold its subcommands into `work-lease.sh` once
`fix/work-lease-worktree-resolve` lands, so the rig ends with ONE lease script. It already avoids
the real accretion cost — it forks **no second lock and no second store**.

`fleet/hooks/pre-commit` (also owned by that ticket, but **untouched** by its branch) takes the
one wiring line; the ticket therefore declares `depends_on: WORK-LEASE-WORKTREE-RESOLVE` with a
`real-dep:` justification recording it as a shared-file hand-off, not a build prereq.

---

## 4. Red-proof by EXECUTION (all run, not read)

`fleet/tests/board-write-lock.test.sh` (matched by `fleet/gate.sh`'s `*.test.sh` glob; hermetic
under `mktemp -d`, real git repo, real hook symlink, real `board-lock.sh` copied verbatim) —
**PASS, 26 assertions.** Reverting each mechanism turns it RED (each executed):

| Revert | Result |
|---|---|
| `cmd_pre_commit(){ return 0; }` | RED, 6 failures |
| `git commit --only -- "$@"` → bare `git commit` | RED, 2 failures — incl. *"the foreign staged path was SWEPT into the board commit"* |
| drop the `[ -f "$HOLD" ]` conflict branch | RED, 10 failures |
| `flock -w` → proceed unlocked | RED, 8 failures — *"not fail-closed"* |

**Two concurrent writers, exit codes both ways:** winner `acquire` → **0**; loser
`commit --session B` → **1** (`BOARD-LOCK CONFLICT`, names the holder), and the loser's edit is
asserted **still on disk, uncommitted, uncorrupted**. Bare board `git commit` → git **1**, gate
arm itself → **4**. flock genuinely held by another process → **70**, and the same commit → **0**
once released (non-vacuous). Master moved under holder → **3**.
`shellcheck -S warning` clean on all three new/changed shell files.

---

## 5. What remains

1. **Land the branch** (after `fix/work-lease-worktree-resolve`, per the declared dep) and get the
   adversarial review (reviewer != builder) the ticket requires.
2. **`fleet/land.sh:341-342` is still a live index-sweeper** — the actual cause of loss (a). Not
   fixed here: `fleet/land.sh` is owned by `HANDOFF-GATE-NONBYPASSABLE` **and** `RECONCILE-WIRING`.
   Needs its own ticket. One line: `git commit -q --only -m "$MSG" -- "${LAND_PATHS[@]}"`
   (for `--commit-dirty`, enumerate the dirty set via `git status --porcelain -z` first so the
   pathspec form is used on that arm too).
3. **CI registration**: add `board-write-lock.test.sh` to `CI_SUITES` in
   `fleet/checks/rig-ci-scope.sh` — owned by `HANDOFF-GATE-NONBYPASSABLE`, so deferred. The test
   IS reachable today via `gate.sh`'s glob.
4. **Fold into `work-lease.sh`** once the contending branch lands (see §3).
5. Full `fleet/gate.sh` sweep was **not** run (session budget). The new test was run directly and
   passes; `fleet/validate_board.sh` still shows a **pre-existing, not-mine** RED:
   `owns-collision LIVE fleet/preflight.sh <- MARKER-PROOF-MECHANIZE PREFLIGHT-GATE-RUN-HELPER
   RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE`. The one RED this ticket introduced
   (gate-parity SPLITTABLE) was fixed with a `serial_justified:` line.
