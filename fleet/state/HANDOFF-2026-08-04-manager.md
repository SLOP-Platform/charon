# HANDOFF — session closed 2026-08-04 (early AM)

> ## ⛔ READ `fleet/state/DECISIONS.md` FIRST. THIS FILE IS SECOND. ⛔
> The ledger holds **D-001 … D-014** — every operator decision from this session, with evidence.
> It **overrides every other file**, including `MANAGER-OPERATING-RULES.md` and `PRIORITY-TODO.md`,
> both of which now carry a pointer to it at the top.
>
> **The single most important decision: D-001 — THE FACTORY IS THE PRODUCT, NOT THE GATEWAY.**
> That answers a question the eval registry escalated on 2026-07-11 and that went unanswered for
> three weeks. Do not re-litigate it. Do not re-derive its consequences; they are written down.

---

# 0 — RUN FIRST (~2 min)
```
cat  fleet/state/DECISIONS.md                     # ALL operator decisions. Non-optional.
bash fleet/checks/stranded-work.sh
bash fleet/checks/gate-integrity.sh scan
bash fleet/rescue-push.sh
bash fleet/pending.sh list                        # triage, do not just print
```

---

# 1 — START HERE. FIRST FOUR ACTIONS, IN THIS ORDER.

### ① Merge PR #232 if its CI is green (product repo `SLOP-Platform/charon`)
Branch `feat/tool-enable-ratchet-v2`, head `d979629`. This is the D-004 tool enablement:
ruff `preview`+`S/BLE/ARG/C90`, mypy 3 flags, pytest-timeout, bandit — **all ratcheted**.
Its last CI run was pending at session close.
```
gh api repos/SLOP-Platform/charon/commits/d979629ee65ad97ab7e2eb34aec450ee8f0adad0/check-runs \
  --jq '.check_runs[]|"\(.name) \(.conclusion)"'
gh api -X PUT repos/SLOP-Platform/charon/pulls/232/merge -f merge_method=squash \
  -f sha=d979629ee65ad97ab7e2eb34aec450ee8f0adad0
```
**Then CLOSE PR #231** — it is the pre-rebase version of the same work and must not be merged.

### ② Transfer `charon-private` into the `SLOP-Platform` org (Q6 = APPROVED, option a)
**Deliberately NOT done at session close** — it rewrites remotes for ~190 worktrees and needs
verification time. It is a start-of-session job, not an end-of-session one.
```
gh api -X POST repos/Nnyan/charon-private/transfer -f new_owner=SLOP-Platform
```
- ✅ Verified SAFE: the repo has **zero Actions secrets and zero variables**, so nothing is lost.
- ⚠ **18 files hardcode `Nnyan/charon-private`** — including `fleet/_lib.sh`. Git redirects keep
  clones working, but fix these refs as part of the move.
- ⚠ **It only fixes ONE of three problems.** `SLOP-Platform` is on the **free** plan, so a
  **private** repo there still gets **no branch protection** and **still metered minutes**. What it
  DOES unlock is the 5 org-level self-hosted runners. See D-014 and §5-Q8.

### ③ Land `feat/shellcheck-ratchet` (rig) — it fixes two LIVE bugs
Commit `61c5316`, **not pushed, verified only by its agent — the manager did NOT verify it.**
Two real runtime bugs, not lint noise:
- `fleet/retire-done.sh:70` — `local` outside a function no-ops, then `set -u` kills **the entire
  retirement sweep** with `dst: unbound variable` **on every run**. That function has never worked.
- `fleet/handoff.sh:173,260,277,301,315` — unescaped backticks in `echo` are live command
  substitution (confirmed by executing it). **In the handoff generator itself.**
Blockers before landing: no `fleet/board/SHELLCHECK-RATCHET.md` exists (so the work-lease hook
refused; it used `WORK_LEASE_BYPASS`), and it edits `fleet/checks/rig-ci-scope.sh` which is
`owns:`-claimed by live ticket `HANDOFF-GATE-NONBYPASSABLE` (edit is additive-only).
**Mint the ticket first, then land. Verify its claims yourself — see §4.**

### ④ Implement D-012: fully-parked pool must return 503, not a silent 200
`src/charon/forwarder.py:481-487`. Operator decided this explicitly. **The outcome test must be
inverted in the same change** — `test_all_legs_parked_still_serves_a_real_200_and_never_strands`
currently asserts the behaviour being removed. Full requirements are in D-012.

---

# 2 — LANE ORDER (D-010, operator-approved). Do not re-plan this.
- **Lane A — turn on what we own.** ~20% of tool capability is switched on. PR #232 is the first
  piece. Remaining, wired in blast-radius order (Q4 answered): **`diff-cover`** (new lines only) →
  **`mutmut` scoped to the money path** → **`hypothesis` on failover only**. All three are
  INSTALLED with **zero references**. `playwright` has NO role here — no browser surface; do not
  wire it to tick a box.
- **Lane C — the three-axis re-evaluation. ✅ DONE this session**, report in §6. Its conclusion is
  the most important sentence produced today.
- **Lane B — delete the 73k-line bash rig onto adopted substrate. LAST, and as a
  cutover-with-deletion, never an addition.**

---

# 3 — WHAT LANDED THIS SESSION (all verified on origin/master)

| what | sha | repo |
|---|---|---|
| gate-parity flake: 30.7s → 3.8s (a PASSING check was being reported RED) | `0a92635` | rig |
| **root cause of the rig-wide `rig-ci` red**: ONE missing `priority:` field failed EVERY open rig PR | same | rig |
| `PLAN-ABC` price-feed→caps→tier design | `2ea63cd` | rig |
| **`DECISIONS.md` ledger** + LOUD pointers from RULES and PRIORITY-TODO | `8632e52` | rig |
| D-008 language policy + D-008a small-Go slices | `011a1cc` | rig |
| D-009 three-axis re-review (incl. the operator's gap audit) | `7a33b8f` | rig |
| **`tests/test_gateway_outcome.py`** — 342 lines, 4 tests/5 cases, **8 red-proofs** | `17d893d` | product |
| TOOL-ENABLE-RATCHET ticket + grader-daemon deregistered from the watchdog | `eb25d28` | rig |
| STATUS-BOARD-V1 ticket | `491e8e3` | rig |
| D-012 / D-013 / D-014 | `ab8b4c4` | rig |
| closed 2 SUPERSEDED PRs (`#220`, `#206`) — blob-verified identical to master | — | product |

**Processes retired:** 5 orphan `fleet-droid` loops (2 days old, ppid=1, invisible, one was claiming
tickets minutes after they were minted) · the `PRICEFEED` opencode tab · the 10-day coordinator
tunnel to rocinante (**0 consumers** — verified before killing) · `grader-daemon` (10 days up, last
wrote the scorecard ~36h earlier, killed by the operator with sudo AND deregistered so the watchdog
cannot restart it).

**Work rescued before the reap:** `7dbdafa` on `feat/price-feed-modelsdev` — INCOMPLETE models.dev
price-source WIP from the interrupted PRICEFEED tab. **Unverified, do not land as-is**; its
acceptance test is priced-entry count ~10 → >1000.

---

# 4 — ⚠️ THE FRICTION LIST — READ THIS BEFORE YOU TOUCH THE RIG ⚠️
Every item cost this session real time. They are all reproducible.

**Landing / git**
1. **`land.sh` opens a PR but does NOT merge it.** It reports `MERGE FAILED … refusing to report
   DONE`. You must merge via `gh api -X PUT …/pulls/N/merge -f merge_method=squash`.
2. **A rebased branch cannot be pushed** (non-FF, and force-push is denied). **Give it a fresh
   branch name** — that is how `-v2` came to exist.
3. **`git rebase`, `git merge --ff-only`, `git push`, `crontab -l` are DENIED to the manager.**
   Use `land.sh`/`land-push.sh`/`worktree-commit-and-land.sh`, or the GitHub Contents API for a
   single-file change.
4. **`worktree-commit-and-land.sh` requires the board lock and never releases it.** It will
   deadlock you against yourself on the next call. **Release explicitly after every land.**
5. **`board-lock.sh commit` releases the lock and THEN commits**, so its own pre-commit hook refuses
   the commit as unlocked. The sanctioned board-write path cannot satisfy its own guard.
6. **`work-lease` refuses any branch with no board ticket carrying a matching `branch:` field.**
   ⇒ **MINT THE TICKET BEFORE CREATING THE BRANCH.** Three commits tonight needed
   `WORK_LEASE_BYPASS` purely because of ordering.
7. **`sync-checkouts.sh` will not fast-forward while tracked files are dirty — even when they are
   byte-identical to the target.** Local rig master is stuck **behind origin**, which means
   **a landed board ticket is INVISIBLE to board-reading gates.** Not cosmetic. Verify with
   `git ls-files --error-unmatch <ticket>`.
8. **Three-dot vs two-dot diff:** `git diff master...branch` shows everything since the merge base,
   so a branch whose content already landed via squash **looks** unlanded. To test "is this already
   on master", compare **blob hashes**: `git rev-parse <sha>:<file>` vs `git rev-parse origin/master:<file>`.

**Processes**
9. **`pgrep -f '<name>.sh'` matches OTHER processes' argument lists.** It reported 6 droids when
   there were 5 — because a `shellcheck` run had `fleet-droid.sh` in its arguments. **Use PIDs.**
10. **`kill -0` returns non-zero under EPERM**, so a process owned by another user reads as **dead
    when it is alive**. **Confirm with `ps -p`.**
11. **The droids ignored SIGTERM.** They needed `kill -9`.
12. **Stopping a tab's session does not stop the tab.** The opencode server stayed up and reverted to
    an idle prompt — indistinguishable from working, finished, or hung.
13. **Orphan droids poll the board and claim brand-new tickets within minutes.** One claimed a ticket
    ~11 minutes after it was minted, for work already finished, from the **main rig checkout**.
    ⇒ Do not mint tickets while unaccounted-for workers are alive.

**Verification**
14. **Verify every subagent claim.** Three real defects tonight survived a confident self-report:
    mypy never run (10 errors), a stale lint baseline that broke CI, and an undeclared dependency.
15. **A probe must isolate the thing it tests.** My first two probes were invalid — one tripped a
    second unbaselined rule, another was a malformed test file that made *pytest* error. Both
    produced misleading results.
16. **pytest `exit=4` is a USAGE error, not a test failure** — it means pytest could not start.
    Tonight: `addopts=--timeout=60` with `pytest-timeout` undeclared, so CI never installed it.
    **Any plugin wired into config MUST be declared in `[project.optional-dependencies]`.**
17. **Per-file lint baselines go stale the instant a new file lands.** `tests/test_gateway_outcome.py`
    landed after the baseline was generated and instantly redded the gate on 29 asserts. **Use
    directory globs for categorically-wrong rules** (`"tests/**" = ["S101", …]`), per-file entries
    only for genuine one-off debt. Fixed: 217 → 97 entries.
18. **"Green runs" is not enforcement.** semgrep/gitleaks/bandit had 371–384 green runs that blocked
    nothing. Verify with the `branches/master/protection` endpoint, never with a passing workflow.

---

# 5 — OPEN QUESTIONS FOR THE OPERATOR

### Q8 · How far to go on the rig repo's home? (follows ②; supersedes the old Q5)
Moving it into the org while private unlocks the runners only. To also get enforceable checks and
unmetered CI you must either **make it public** — which needs a scrub, **129 `fleet/*.sh` files
contain `10.0.1.60` or `/home/stack` paths** — or **pay for Team** (~$4/mo, 1 seat).
**Manager rec: do ② now, decide public-vs-paid as a deliberate choice, not at 2am.**

### Q9 · Draft-PR sweep: adopt, don't build (rec given, not yet approved)
GitHub's **auto-merge + merge queue + required checks IS the sweep**. `allow_auto_merge` is
**already true** on the product repo; there is **no `merge_group` in any workflow**; and
`docs/review-log/MERGE-QUEUE-EVAL.md:3` already carries an **ADOPT — configuration-only** verdict
that was never applied. The bigger fix is at source: **stop opening PRs as drafts.**
⚠ Sequence AFTER Lane A — auto-merging on unproven gates auto-lands a green lie.

**Already answered, recorded, do not re-ask:** Q1→503 (D-012) · Q2→move non-enforcing tools, no
need to ask again (D-013) · Q3→runners on 4-LOM+BB-8 (D-014) · Q4→blast-radius order · Q6→move to
org, option (a) · Q7→**self-hosted runners for the RIG ONLY**; product CI stays GitHub-hosted
because it is public and free, and **self-hosted runners on a public repo let fork PRs execute code
on your hardware.**

---

# 6 — LANE C RESULT (the most important finding of the session)

> ### "The dominant failure is not a wrong verdict — it is a right verdict never executed."

**10 of ~34 registry rows are VOID-AS-DELIVERED** — decided correctly, then never done. **Only ONE
row in the entire registry (PyYAML) has a verified NEGATIVE delta on our own line count.** Every
other "adoption" added code.

| adopted | promised | actual |
|---|---|---|
| merge queue | ADOPT, "configuration-only" | never applied |
| LiteLLM Router (ADR-0017) | "deletes 650–750 LOC" | **+1,063 LOC, ZERO importers** |
| OpenTelemetry (rejected) | "product ships `observability.py`" | that module was **retired as inert** ⇒ observability/alerting is now **NOTHING**, which makes D-003's out-of-band notify **unimplementable** |
| monit | assumed adopted | **NOT INSTALLED** — `fleet/watchdog/` is 880 lines generating config for a missing binary |
| Hypothesis | ADOPT-NARROW | installed, **0 refs** |

**Biggest deletion target (Lane B):** the durable work queue — **~6,000 LOC** across
`work-lease.sh`, `lease-enqueue.sh`, `faktory/`, `board-lock.sh`, `reconcile-stale-claims.sh`,
`branch-reaper.sh` plus product `engine/` — while **faktory is not installed**, nothing listens on
its port, and `claim.sh` references the "ONLY sanctioned path that starts work" **zero times**.
Durable-execution engines were **never scored for this role**.

**Gap audit — capabilities with NO tool and NO code:** observability/alerting (**0** — blocks D-003),
lifecycle enforcement / blocking-on-unfinished-work (**0** — the top unmet need), dependency upkeep
(**0**). Agent isolation: **189 live worktrees, zero process/FS isolation.**

Also: **`src/charon/ledger.py` is not wired into `forwarder.py` or `proxy_server.py` at all** — found
while building the outcome test. Another inert module.

---

# 6b — ⚠️ AUTHORITATIVE NUMBERS (measured 2026-08-04 by STATUS-BOARD-V1 — these SUPERSEDE any
# figure quoted elsewhere in this file, in DECISIONS.md, or in the 08-02 handoff)

| metric | authoritative | what was previously quoted |
|---|---|---|
| stranded work, ALL shapes | **350** (290 pushed-no-PR · 48 closed-PR-unlanded · 6 unpushed · 4 dirty-worktree · 1 pr-no-checks · 1 stash) | 287 — that was only the pushed-no-PR shape |
| draft PRs | **44 of 61** | 46 of 62 |
| red-proof suites not enforced in CI | **114** | 113 |
| parked providers | **7 of 17** | 7 ✓ |
| models with no usable price | **830 of 861** | 851 |
| **test files CI actually runs** | 🔴 **20 of 139** | *not previously known* |
| product gate | 1 of 12 checks failing | — |
| defects in our own safety machinery | 52 | — |
| guards with no working proof | 34 | — |

**PASSING tiles: ZERO.** The agent's words: *"that is the truth tonight."* That is the correct
output for a first version, not a failure of it.

**119 of 139 test files never execute in CI** is a new finding and arguably the most important number
on the board — it means the test suite is largely decorative, and it reframes Lane A.

# 7 — IN FLIGHT AT CLOSE
- **`STATUS-BOARD-V1` — ✅ BUILT.** Commit `73c57cc` on `feat/status-board-v1`, **not pushed**.
  Worktree `/home/stack/charon-private-wt/STATUS-BOARD-V1`; page at
  `fleet/status-board/board.html`. 18 tiles, 48 hermetic assertions in CI_SUITES, can-it-fail proven
  by **six** separate reverts each verified RED, hermeticity proven by replacing curl/gh/wget/nc/ssh
  with refusing stubs (48/48, none invoked), plus a positive control so it cannot be satisfied by
  greying everything out. It caught **three of its own bugs** against real data — including a
  first-digit extraction that read "114 suites" as **5**, and a regex that reported "71 of 82
  failing" when the truth was 1 of 12. **Manager did NOT independently verify; do that before
  landing.**
- 🔴 **OWNS COLLISION — serialize these two.** BOTH `feat/status-board-v1` and
  `feat/shellcheck-ratchet` edit `fleet/checks/rig-ci-scope.sh` (each adds one `CI_SUITES` entry),
  and that file is `owns:`-claimed by live ticket **`HANDOFF-GATE-NONBYPASSABLE`**. Land them ONE AT
  A TIME and re-run the second's test after the first lands, or they will conflict.
- **PR #232** — CI pending at close (see ①). **PR #231 must be closed, not merged.**
- **`feat/shellcheck-ratchet`** `61c5316` — committed, unpushed, unverified by the manager (see ③).
- **`feat/price-feed-modelsdev`** `7dbdafa` — incomplete WIP, do not land as-is.
- **24 PRs classified DONE-NOT-PROMOTED** with a conflict-aware merge order, held back deliberately
  so in-flight sub branches were not stranded. Anchors first: **rig `371 → 444`** then
  `317 342 343 432 439 441 442`; **product `211 → 209 → 208 → 224 → 219 → 226`** then the other 9.
  Conflict pairs: 371↔444 (`.gitignore`); 211↔209 (`gate_runner.py`/`tools/gates.json`);
  209↔208 (`forwarder.py`); 224↔211 (`catalog_refresh.py`); 226↔219 (`providers.py`).
- **Single highest-leverage unblock:** `fleet/tests/stranded-work.test.sh` **Q2/Q3 bitrot** is
  pre-existing, unrelated to any diff, and is currently failing **4 rig PRs** (423, 430, 443, 445).
- **8 diverged `rescue/*` branches** the cron re-reports every 20 minutes with "MERGE BY HAND" —
  nobody ever does. They accumulate forever.

# 8 — CARRIED FORWARD (was the harness task list; it dies with the session)
1. `INERT-CODE-DISPOSITION-BACKLOG` — 18 dead symbols; its brief FORBIDS blanket-`keep`.
2. `fix/soleleg-guard-blocks-autopark` `8fb725a` — auto-park was dead code for 17/17 providers.
   Operator condition: red/green/**dogfood** before landing.
3. **Park is a ONE-WAY DOOR** for 5 of 7 parked providers — auto-unpark only fires from a balance
   poll >0, and only `deepseek`/`openrouter`/`nanogpt` have poll adapters (`balance.py:134-137`).
   The other five can **never** re-arm. 7 providers are parked right now (`/data/balance_park.json`).
4. **CORRECTION to the 2026-08-02 handoff:** it says park is a no-op and `/charon/status` has no
   `parked` field. **Both FALSE.** The parks took effect and persisted; the never-strand fallback is
   why parked providers still served. "Assume nothing is parked" is **inverted** — over-parking is
   the live problem.
5. **Price feed is the root money blocker:** **10 of 861** registry entries have `cost_input`, so
   `derived_cost_rank` returns its neutral 1000 for 851 of them ⇒ cost-first ordering is inoperative
   for ~99% of the catalog. `models.dev/api.json` is public, no key, **5,613 priced models, 17/17 of
   our providers covered** (aliases: `opencode-zen→opencode`, `google-aistudio→google`,
   `nanogpt→nano-gpt`, `together→togetherai`).
6. **Tier routing is built but starved** — `tier_pools()` compiles `tiers.json`, and
   **`/data/tiers.json` does not exist**. Meanwhile the fleet hand-maintains provider-PINNED tier
   chains in `tier-models.tsv`, violating the standing never-pin rule in its own config.
7. **Pool layer is 88% ceremony:** 4,380 pools, **3,846 single-member** (no failover possible), 29
   listing the same provider twice.
8. `NEVER-ANTHROPIC-ASSERTION` — ticketed, UNBUILT. `claude-opus-5`/`claude-sonnet-5` pools already
   list `opencode-zen`, and both opencode providers carry 10 Claude models each. **Must land before
   Lane B/C cut over** — a price-ranked candidate pool can surface an Anthropic leg no hand-written
   chain would have named.
9. Owed but never minted (D-007 class): `HYPOTHESIS-ADOPT-NARROW`, `KSF-FIXES-1-3`. Mint them —
   safe now that the orphan droids are dead.
10. Correct the `TOOL-ENABLE-RATCHET` ticket's `branch:` field to `feat/tool-enable-ratchet-v2`.
11. Follow-up on the ratchet: replace per-file ignores with a **COUNT ratchet** (the rig's
    `shellcheck-ratchet.sh` already does this correctly — copy its shape). Per-file baselines do not
    catch a NEW violation of a rule already baselined in that same file (manager-verified).
12. Triage the 3 HIGH-severity bandit findings — recorded in the baseline, currently not enforced.
13. Cheapest unmet need in the whole estate: **out-of-band alerting** (ntfy or Healthchecks.io — one
    container or one `curl`). D-003 mandates it; the capability is currently **nothing**.
