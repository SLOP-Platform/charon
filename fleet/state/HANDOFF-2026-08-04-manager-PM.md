# HANDOFF — session closed 2026-08-04 (PM). Supersedes HANDOFF-2026-08-04-manager.md.

> ## ⛔ READ `fleet/state/DECISIONS.md` FIRST. THIS FILE IS SECOND. ⛔
> The ledger holds **D-001 … D-016**. It overrides every other file. **D-001: THE FACTORY IS THE
> PRODUCT, NOT THE GATEWAY.** Do not re-litigate it, do not re-derive its consequences.
>
> The previous handoff's §1 (four actions) is **DONE — all four**. Its §4 friction list is still
> valid; §5 of THIS file extends it with what that list did not warn me about.

---

# 0 — RUN FIRST (~3 min)
```
cat  fleet/state/DECISIONS.md                     # every operator decision. Non-optional.
bash fleet/checks/stranded-work.sh
bash fleet/rescue-push.sh
bash fleet/pending.sh list                        # triage, do not just print
```

---

# 0b — ANSWERS TO THE OPERATOR'S CLOSING QUESTIONS (2026-08-04) — all now ticketed

| operator question | answer | where it lives |
|---|---|---|
| "what is the fix for the D-007 pattern (and any other pattern that keeps happening)?" | **They are ONE pattern.** D-003 already diagnosed it: *"nothing in the system BLOCKS on an unfinished commitment."* The fix is lifecycle enforcement, DECIDED and NEVER BUILT. | ticket **`LIFECYCLE-ENFORCEMENT`** (p0) |
| "should we automate/mechanize the deploy? this is constantly lagging" | **Yes.** Root cause: no signal connects "merged" to "running"; the host has no git checkout so ordinary staleness checks are blind; the status board has no deployed-version tile. | ticket **`DEPLOY-MECHANIZE`** (p0) |
| "is the next session going to investigate the River postgres container?" | **Yes** — and it unblocks THREE things (Lane C AXIS 2's top trial, D-008a's Go supervisor, TAB-RELIABILITY). | ticket **`RIVER-QUEUE-TRIAGE`** |
| "did the product re-eval (including candidates) happen?" | **NO. It did not happen this session.** The operator set A→B→C ordering; Lane A consumed the session, Lane B never started, so Lane C AXIS 2 was never reached. Still ~50 tools + ~10 re-test rows, all `UNVERIFIED`. **Do not report it as done.** | §6c + `LANE-C-REEVAL-2026-08-04.md` §AXIS 2 |
| "surface the need for me to create a new identity loudly and often" | Filed as **`Q-010` in `DECISIONS.md`** — the ledger is cat'd at SessionStart and `ASKED` rows are defined to BLOCK dependent work. | **`Q-010`** |

## ⛔ THE RECURRING-PATTERN ANSWER, IN ONE PLACE — read this before proposing any process fix ⛔
Every recurring failure in this estate is the SAME shape: *a thing was started and nothing refused
to proceed without it finished.*
- D-007 research→no code · deploy drift · landed-but-never-worked · 291 stranded branches ·
  questions unanswered for 3 weeks — all one root cause.
- There are already ~393 review artifacts, 76 registry rows and 9 installed memory products, and the
  operator still cannot get a feature built end to end.
- **⇒ More documentation, better handoffs and better memory CANNOT fix this. Only a blocking GATE
  can.** DECISIONS.md says it outright: *"A mechanism that exists and does not prevent the failure is
  not a solution — it is a wish."*
- If a session's answer to a recurring failure is a document telling future sessions to be careful,
  that session has reproduced the failure.

---

# 1 — ⛔ THE SINGLE MOST IMPORTANT FACT ON THIS PAGE ⛔

## ✅ THE D-012 MONEY FIX IS DEPLOYED AND SERVING — closed 2026-08-04

`v0.6.2` cut and tagged on `6bb8805` (PR #236, all four required checks green), release workflow
**success**, image published, deployed and VERIFIED:
`charon-gateway-1  ghcr.io/slop-platform/charon:v0.6.2  Up (healthy)` and a live completion
returned **200 in 1.95s**. The fully-parked-pool money leak is closed IN PRODUCTION, not just on
master. The gap it closed was 14 commits / one full day of leaking after the fix had merged.

### ⛔ BEFORE YOU DEPLOY: THE COMPOSE FILE WILL ROLL PRODUCTION BACK ⛔
`/home/stack/charon/docker-compose.yml` on the deploy host pins **`charon:v0.3.3`** while the running
container was **v0.6.1**. Someone deployed by hand and never updated compose. **A plain
`docker compose up` DOWNGRADES the live gateway by three minor versions**, silently reverting every
money-path fix since v0.3.3 — including D-012. **Update the compose image pin to v0.6.2 FIRST, then
pull, then up.** Recorded in `DEPLOY-MECHANIZE`.

### The original problem, for context

The gateway runs as a **container**, not from a checkout:
`ghcr.io/slop-platform/charon:v0.6.1`, up 3 days at session close. Verified: there is **no charon
git checkout at all** on the gateway host.

**master is 14 commits ahead of `v0.6.1`**, and those 14 include `1d675bc` — D-012, the change that
makes a fully-parked pool return a terminal 503 instead of a silent billed 200.

⇒ **Until a new release is cut and the container is pulled, a fully-parked pool still serves 200 and
still spends money.** Measured on 2026-08-03: `kimi-k2.6` (5/5 legs parked) and `minimax-m2.5` (2/2)
both served 200. Nothing has changed that in production.

This is the deploy-drift class already on record ("deployed image ≠ source"). **Cutting the release
is operator action A — see §7.**

---

# 2 — WHAT LANDED (all merge-verified on origin, in order)

**Product `SLOP-Platform/charon`** — master `4bb3253` + PR #235 in flight
| what | PR | squash |
|---|---|---|
| D-012 fully-parked pool → terminal 503 (money path) | **#233** | `1d675bc` |
| 3 security scanners relocated **and made REQUIRED** | **#234** | `4bb3253` |
| hard-pin ubuntu-latest + scrub internal hostnames | **#235** | *open at close, 3/5 green* |

**Rig `Nnyan/charon-private`** — master `8989a6e`
| what | PR / sha |
|---|---|
| shellcheck ratchet + **2 live runtime bugs** | **#447** |
| STATUS-BOARD-V1 operator page (18 tiles, 48 assertions) | **#448** |
| board: 5 tickets minted, 5 retired, 1 parked with evidence | `ec06b33`…`8989a6e` |

## ✅ D-013 IS GENUINELY CLOSED — verified the only way D-013 accepts
```
gh api repos/SLOP-Platform/charon/branches/master/protection --jq '.required_status_checks.contexts'
→ ["gate","bandit","gitleaks","semgrep"]
```
Those three had **371–384 green runs on the rig blocking nothing**. They now block merges. PR #235
is the first PR they gated, and gitleaks/semgrep went green on it independently.

---

# 3 — TWO ADVERSARIAL REVIEWS SAID **BLOCK**. BOTH WERE RIGHT. THIS IS THE HEADLINE.

Every money/key-code change this session was adversarially reviewed. **Neither would have been
caught by CI**, and both were green locally before review.

### 3a — D-012 (money path)
| sev | defect |
|---|---|
| HIGH | the cherry-picked cost-order commit is a **NO-OP on the live gateway** — its review-log claimed a fix that measurably does not occur |
| HIGH | that same commit **silently overrode drain-then-park**, the operator's funding-class directive |
| MED | the 503 **refused free cache hits** — D-012 stops *spend*, not zero-cost traffic |
| MED | `bt is None` **failed open** — the money leak's back door |
| MED | an `all()`→`any()` mutation left all 2,395 tests green ⇒ acceptance (d) had **no valid red-proof** |

Final: cherry-pick dropped, **17 mutations each observed RED**, gate 22/22. I re-ran one mutation
myself and confirmed the tree restored clean.

### 3b — the security gates (about to become merge-blocking)
| sev | defect |
|---|---|
| CRITICAL | `diff_filter.py` could not tell a diff header from an added line starting with `++ ` → **every later hunk of that file silently discarded**, all three gates. Control PR → exit 1; same PR + one `++ ` line → **exit 0, "0 introduced by this diff"** |
| CRITICAL | gitleaks reported **green on a scan that read nothing** — it returns 1 for *scan error* as well as *leaks found*. A filename with any non-ASCII byte hid a live-shaped AWS key |
| HIGH | bandit scoped to `src/`+`tools/` only — **162 of 309** tracked `.py` files invisible |
| HIGH | the canaries **never exercised `--diff`** — the only path CI runs. That is *why* the criticals passed 10/10 |
| HIGH | stale base sha → the gate **blamed other lanes' findings** on innocent PRs |

The `++ ` bug was not adversarial: **any PR adding a doc or patch line beginning with `++ ` silently
lost coverage.** I reverted the fix myself and watched canary 6a red with the exact false-green
signature before accepting it.

> **DO NOT SKIP ADVERSARIAL REVIEW ON MONEY OR GATE CODE.** Cost ~250k subagent tokens across both.
> Both would otherwise have landed green and *looked* fine.

---

# 4 — 🔧 THE LANDING RUNBOOK — READ BEFORE YOU TRY TO LAND ANYTHING 🔧
**This section is the main improvement over the handoff I received.** The previous friction list told
me the pieces but never the ORDER, and I burned a large part of this session rediscovering it. The
sequence below is exact and worked ~12 times in a row.

### 4a · Landing CODE on a feature branch
```
# 1. MINT THE TICKET FIRST AND LAND IT ON MASTER. Not optional, not reorderable.
#    work-lease refuses any branch with no board ticket carrying a matching `branch:` field,
#    and it reads the board from the WORKTREE'S CHECKOUT — so the ticket must be on master
#    BEFORE the branch is created, or you deadlock. I hit this three times.
# 2. create the worktree off CURRENT origin/master (never an old base — see 5.1)
git -C <repo> worktree add /path/WT -b <branch> origin/master
# 3. acquire the lease FROM INSIDE the worktree
bash fleet/work-lease.sh acquire <TICKET>
# 4. commit normally (git commit works; the hooks gate it)
# 5. land
bash fleet/land.sh <branch> /path/WT
# 6. land.sh OPENS A PR BUT DOES NOT MERGE (exit 7). Merge it yourself:
gh api -X PUT repos/SLOP-Platform/charon/pulls/<N>/merge -f merge_method=squash
# 7. mark done + retire
bash fleet/done.sh <TICKET>
```

### 4b · Landing BOARD files (tickets, ledger, docs) — completely different path
```
bash fleet/board-lock.sh acquire <session>        # ⛔ REQUIRED FIRST — see 5.2
bash fleet/worktree-commit-and-land.sh --session <session> -m '<msg>' -- <board paths>
bash fleet/board-lock.sh release <session>        # it NEVER releases; you must
bash fleet/sync-checkouts.sh
```
- The commit message **MUST** start with `land:` or contain `board-hygiene`, or it refuses.
- `board-lock.sh commit` will refuse and redirect you to `worktree-commit-and-land.sh`. Just start
  with the latter.
- **Release the lock every time.** It is not released on success.

### 4c · Board ticket frontmatter that actually passes
- `tier:` must be one of: `economy frontier haiku high low med opus sonnet strong`. Not `standard`.
- **Any prose field containing `": "` MUST be a block scalar** (`key: |`), or the YAML gate rejects
  it. This bites `dep-kind`, `serial_justified`, `parked_reason`, `real-dep`.
- `difficulty >= 3` + more than one `owns:` path ⇒ **SPLITTABLE**; needs `serial_justified: |`.
- A `depends_on` whose `owns` are disjoint needs `real-dep: <reason>` **and** `dep-kind: build`.
- Validate before every attempt: `bash fleet/validate_board.sh` → must print `GREEN`.

### 4d · Before you write ANY new ticket — the reuse-check that saved me twice
```
grep -l '<the file you intend to own>' fleet/board/*.md
```
Twice this session the board caught me minting a ticket for work **already owned by a live ticket**
(`LAND-PATH-FAIL-LOUD` → owned by `NO-LOCAL-MASTER-COMMITS` + `BOARD-LOCK-STAGED-COMMIT-FIX`;
`TAB-RELIABILITY` → `fleet-droid.sh` owned by two live tickets). **Fold your evidence into the
owning ticket instead of minting a competitor.** Fragmenting work across duplicate tickets is how
this board got to 165 live entries.

---

# 5 — ⚠️ NEW FRICTION — things the previous friction list did NOT warn me about ⚠️
Numbered to continue that list (which remains valid; especially #1 land.sh-does-not-merge, #2
rebased-branch-needs-a-fresh-name, #9b never-wait-on-`pgrep -f`, #14 verify-every-subagent-claim).

19. **`worktree-commit-and-land.sh` REQUIRES the board lock and exits 2 in TOTAL SILENCE without
    it** — no stdout, no stderr, after creating and removing a scratch worktree. Through a pipe the
    caller sees rc=0 and an empty log, which reads as a successful no-op. **Cost me 3 invocations,
    2 of which I believed had landed until I checked origin.** Traced with `bash -x`.
    → Evidence landed into `BOARD-LOCK-STAGED-COMMIT-FIX`. Still broken.
20. **A branch cut from an older master reds the board gate on tickets retired since.** The gate runs
    against the WORKTREE'S board, not master's. Symptom: `gate-parity`/`owns-collision` REDs naming
    tickets you know are archived. Fix: rebuild on current `origin/master` under a **fresh branch
    name** (force-push is denied). This is what `-v2` names are for.
21. **`git checkout -- .` in a worktree silently wipes edits to tracked files.** I lost a
    `rig-ci-scope.sh` edit and a regenerated baseline this way and had to redo both. Restore
    named paths only.
22. **Backticks inside a `git commit -m "…"` are COMMAND SUBSTITUTION.** My commit message
    containing `` `-o all` `` executed it. Use `-F <file>` for any message with backticks.
    (Ironic: this is the exact bug #447 fixed in `handoff.sh`.)
23. **`gh api -f strict=false` sends the STRING "false"** → HTTP 422. Use
    `--input <(echo '{"strict":false,...}')` for any typed field.
24. **A cron rewrites the TRACKED file `fleet/state/OPERATOR-ACTIONS.md`** (the `#30 STRANDED WORK:
    N finding(s)` line) in the main rig checkout. `sync-checkouts.sh` then refuses to fast-forward,
    so local master goes stale within minutes and **a landed board ticket becomes invisible to
    board-reading gates**. I discarded that file ~6 times today. It is also how master reached 15
    commits behind at session start.
25. **`fleet/work-lease.sh holds` is broken** — `line 195: $1: unbound variable`. There is currently
    no working way to list held leases. Release explicitly by name.
26. **The public-clean exemption ledger goes stale when you FIX the underlying line.**
    `tools/.public-clean-exceptions.json` pins exempted lines verbatim; removing a line makes its
    exemption stale and `test_shipped_exceptions_match_tracked_file_content` fails. Prune the
    ledger in the same commit. (Working as designed — but it will stop your land.)
27. **The leak-guard blocks internal hostnames in the PUBLIC product repo** — correctly. Writing
    "4-LOM" into a workflow comment refused my commit, which then surfaced **8 pre-existing
    hostname leaks already on master**. Never put host/IP/path identifiers in product-repo files.

---

# 6 — 🔴 CARRIED FORWARD — LIVE DEFECTS AND UNFINISHED WORK 🔴

### 6a · Landed-but-never-worked — THE most expensive class here
This is the sibling of D-007 ("research lands, implementation drops"): **code that landed, was
marked DONE, and never functioned.** Two confirmed today:
1. **`retire-done.sh` — fixed this session (#447).** Its `local` outside a function killed the
   ENTIRE retirement sweep under `set -u` on **every run since it was written**. That is why merged
   tickets kept phantom `owns:` claims and redded the board. It fired live mid-session.
2. **`DROID-LIFECYCLE-REAP` is marked DONE and archived — and the reaper does not reap.** 5 orphan
   `fleet-droid` loops were alive ~2 DAYS at the previous close, `ppid=1`, one claiming tickets.
   ⇒ **Before building anything for TAB-RELIABILITY, VERIFY THE LANDED REAPER ACTUALLY RUNS.**
3. **Still broken, evidence landed into its owning ticket:** `retire-done.sh`'s *staging* branch
   tests `$dst` BEFORE the `mv`, so it can never fire; every retirement leaves the tree dirty
   (→ `NO-LOCAL-MASTER-COMMITS`, whose blocker `SYNC-SCHEDULE` is **DONE**, so it is unblocked).

**Generalise: a DONE marker is not evidence the thing works. Run it.**

### 6b · ⛔ TAB RELIABILITY — OPERATOR-SET HIGH PRIORITY FOR NEXT SESSION ⛔
Operator, verbatim 2026-08-04: *"lets make tab reliablity a HIGH priority for the next session this
is a KEY feature or SG that needs to be fixed."*
Ticket **`TAB-RELIABILITY`** (priority 0) is on the board with the full measured evidence.
- Core defect: **a tab that is working, finished, hung, or dead is indistinguishable from outside.**
- The DETECTION tooling is itself broken (`pgrep -f` matches other processes AND itself; `kill -0`
  reads alive-as-dead under EPERM; `work-lease.sh holds` crashes).
- It deliberately does **not** own `fleet-droid.sh` (two live tickets do) and sequences behind
  `LAUNCHER-CRASH-PARTIAL-DETECT` for the heartbeat it must consume.
- ⚠️ **D-008a sequencing: if a durable-execution engine is adopted, THE ENGINE IS THE SUPERVISOR.**
  Do not hand-build a scheduler that Lane B is about to adopt. Note: a **`river-pg` Postgres
  container has been running since 2026-08-01** — someone began a River (durable queue) trial and
  it is undocumented. Find out what it is before scoring the queue role.

### 6c · Lane A status
| item | state |
|---|---|
| tool-enablement ratchet (#232), shellcheck (#447) | ✅ landed |
| status board (#448), scanners required (#234) | ✅ landed |
| **diff-cover / mutmut** | **IN FLIGHT at close — see §8** |
| hypothesis (ADOPT-NARROW, 0 refs) | not started; ticket `HYPOTHESIS-FAILOVER-EVAL` exists |

### 6d · Money path
- **`FORWARDER-COST-ORDER-FALLBACK` is now PARKED with two executed proofs** (in the ticket): it is
  a no-op against the live catalog **and** it silently overrides drain-then-park. **Do not land it
  until the price feed exists.**
- **The price feed is the confirmed root money blocker.** Live `/data/models.json`: **861 models, 10
  with `cost_input`**, 214 carrying the DEPRECATED `cost_rank` that `derived_cost_rank` ignores
  (ADR-0016 step 6). ⇒ cost-first ordering is inoperative for ~99% of the catalog.
  `models.dev/api.json` is public, no key, 5,613 priced models, 17/17 providers covered.
  WIP exists but is unverified: `feat/price-feed-modelsdev` `7dbdafa`.
- **`park_cooldown.py::park_cooldown_filter_chain` has the same restore-the-parked-chain behaviour**
  D-012 outlaws, cemented by two tests. Zero `src/` callers ⇒ no live leak. **Not changed
  deliberately** — its sole-leg guard also covers *cooldown* (transient, free to retry), and
  splitting park from cooldown is an operator decision, not a silent override. **NEEDS A RULING.**

### 6e · Smaller, all ticketed or listed in §7
- shellcheck ratchet: **any NEW `.sh` file self-baselines** ⇒ enforces nothing where new debt
  arrives. Candidate fix: hold ERROR/WARNING codes at hard zero for files not already in baseline.
- **Local `semgrep` is broken** (`opentelemetry` ImportError) ⇒ its canary is only provable in CI.
  The wrapper correctly failed CLOSED. CI installs a clean pinned semgrep and passes.
- **54 open PRs, 44 drafts** (rig 30/23, product 24/21). The prior handoff's conflict-aware merge
  order still applies; several will now be blocked by the four new required checks.
- 291 pushed-no-PR stranded branches; ~348 stranded findings all shapes.
- Stray untracked `state/judgment/` in the product checkout — investigate, do not blind-delete.

---

# 7 — ACTIONS REQUIRED **OF THE OPERATOR** (nothing else can do these)

**A. 🔴 CUT A RELEASE — the D-012 money fix is not deployed.** master is 14 commits past `v0.6.1`;
the gateway container is `v0.6.1`. Until a release is built and pulled, the parked-pool leak is
live. This is the highest-value action on the list.

**B. Create a second GitHub identity you control** — then, and only then, is
`require_code_owner_reviews` worth enabling.
Why it is NOT worth enabling today: `CODEOWNERS` lists `@Nnyan` as the sole owner,
`required_approving_review_count` is **0**, and `enforce_admins` is **false**. GitHub forbids
self-approval, so every PR touching `/.github/` or `/tools/` would need an approval nobody can
give — and you'd bypass it as admin anyway, which means it enforces nothing against the real threat
(agent-authored PRs merged under your admin token). ⚠️ Note `charon-bot` is a REAL THIRD PARTY's
account (operator action #33) — it must be an account you create.
Command, once that exists (also set `enforce_admins: true` or it does nothing):
```
gh api -X PATCH repos/SLOP-Platform/charon/branches/master/protection/required_pull_request_reviews \
  --input <(echo '{"require_code_owner_reviews":true,"required_approving_review_count":1}')
```

**B2. 🔴 CLOSE THE ORG RUNNER GROUP TO PUBLIC REPOS — new finding, 2026-08-04.**
```
gh api orgs/SLOP-Platform/actions/runner-groups --jq '.runner_groups[]|{name,visibility,allows_public_repositories}'
→ {"name":"Default","visibility":"all","allows_public_repositories":true}
```
There are **5 ONLINE self-hosted runners** in that group (`4-lom`, `4-lom-2`, `4-lom-3`, `bb-8`,
`bb-8-2` — all labelled `self-hosted,charon-ci`), and the org contains the **PUBLIC** repo
`SLOP-Platform/charon`. So the public repo IS PERMITTED to run jobs on hardware that also runs the
gateway and the fleet. Today nothing exercises it — I hard-pinned every product workflow to
`ubuntu-latest` in #235 and verified no `runs-on` requests a self-hosted label — but that is a
CONVENTION in workflow files a PR can change, not a control.
**VERIFIED SAFE TO CLOSE:** the org's other repos are `SLOP` (public) and `mediastack` (private),
and the RIG repo is `Nnyan/charon-private` — NOT in this org — so it cannot be using these runners
either. Nothing measurable depends on public-repo access.
Defence in depth, one setting, closes it regardless of what any workflow says:
```
gh api -X PATCH orgs/SLOP-Platform/actions/runner-groups/<id> \
  --input <(echo '{"allows_public_repositories":false}')
```
(get `<id>` from the runner-groups listing above). This is the org-level enforcement of D-016.

**C. Do NOT set `CI_RUNNER` on the public product repo.** Verified unset at repo AND org level; the
misleading comments instructing it are removed in PR #235. Self-hosted runners are RIG ONLY (D-016).

**D. Rule on `park_cooldown.py`** (§6d): may park be split from cooldown in the sole-leg guard?

**D2. `LITELLM-COST-ADOPT` — a droid's VERDICT was found orphaned; the ticket is still LIVE.**
`state/judgment/mace-windu-LITELLM-COST-ADOPT.md` was sitting UNTRACKED in the PRODUCT checkout (the
judgment dir lives in the RIG). I moved it to `fleet/state/judgment/`. Its verdict, unverified by
me: *"No code change needed. Close ticket: ADOPTED-WIRED-EVIDENCE-FILED. The $1,185 vs $1.34 concern
is two different ledgers (universal cap floor vs observer metered spend), not a bug."* The ticket has
NO done marker and is still on the active board. **Verify that verdict, then close it or act on it.**
This is the D-007 class in miniature: the work was done and the filing was dropped. It also explains
the repeated `done.sh` warning "NO model-used provisional found … scorecard will NOT record this
outcome" — droid capture refs are diverging from what `done.sh` looks for.

**E. Q8 still open** — rig repo public (needs scrubbing 129 `fleet/*.sh` files containing internal
IPs/paths) vs paid Team (~$4/mo). The org transfer is deferred behind this; deciding first means
migrating once.

**F. Approved but NOT started this session** (deliberately — ran out of session, no new agents
launched at close):
  - **security-scanner consolidation** (operator-approved): retire the OVERLAPPING parts of
    `tools/check_security.py` (`shell=True`/`eval`/`exec` → bandit; secrets/IPs → gitleaks+semgrep);
    **KEEP** its bare-except/broad-except check — that is Charon-specific policy no adopted tool
    covers. Note `src/charon/scanners.py` runs `ruff --select S` as a 4th overlapping surface.
  - **`pyproject.toml` decomposition** (operator-approved, "your rec and order approved"):
    move `[tool.ruff]` → `ruff.toml`, mypy → `mypy.ini`, coverage → `.coveragerc`, pytest →
    `pytest.ini`. **13 live tickets own `pyproject.toml`**; this collapses ~6 of those claims onto
    separate files that can be edited in parallel.
    ⚠️ **Ruff IGNORES `[tool.ruff]` in `pyproject.toml` entirely once `ruff.toml` exists** — the
    move must be COMPLETE or settings silently vanish. Needs its own red-proof.

---

# 8 — IN FLIGHT AT CLOSE
- **PR #235** (`fix/public-repo-runner-pin`, product): hard-pin + hostname scrub. At close:
  `gitleaks` ✅ `semgrep` ✅ `wheel-smoke` ✅, `gate`/`bandit` still running. **Merge it if green:**
  `gh api -X PUT repos/SLOP-Platform/charon/pulls/235/merge -f merge_method=squash`
  then `bash fleet/done.sh PUBLIC-REPO-RUNNER-PIN`.
- **`feat/diff-cover-mutmut-v2`** (product, worktree `/home/stack/charon-wt/DIFF-COVER-MUTMUT`):
  Lane A diff-cover + mutmut gates. See §9 for its exact state at close.
  ⚠️ The ORIGINAL `feat/diff-cover-mutmut-adopt` (3 commits on origin) has **NO PR and ZERO CI runs
  ever** — treat every claim on it as unproven. The ticket is already repointed at `-v2`.
## 8a — `feat/diff-cover-mutmut-v2` FINAL STATE (committed `bddc1a5`, PUSHED, no PR)
Pushed deliberately so it cannot be lost; **no PR on purpose** — it is INCOMPLETE and must not merge.
Gate ran GREEN at push. Scratch worktrees DCM-FIXTURE / DCM-STRANDED were deleted (throwaway).

| | state |
|---|---|
| **diff-cover** | gate logic **DONE**, wiring **INCOMPLETE**. Red→green EXECUTED on a real diff: RED rc=1 in **35.2s** (`1 of 2 added line(s) in src/ are never executed`), GREEN rc=0 in **38.6s** after adding only the covering test. |
| **mutmut** | **INCOMPLETE — recommend NOT a PR gate.** Its fail-closed path is executed (rc=1, 17.6s). Blocker: inside mutmut's own `mutants/` sandbox the suite is RED (5 failures — sandbox has no `.git` and re-enters gate scripts), and the baseline alone is **78s before a single mutant runs**. **Recommendation: move mutmut to a NIGHTLY cadence and land diff-cover alone as the check.** Latency is a failure class here. |

**Measured, useful regardless:** whole-tree coverage today is **87.0% of `src`** (11603/13339 stmts) —
the gate prints it and never gates on it. `pytest -n auto --cov=src` = **36s** vs `coverage run -m
pytest` = **99s**, so `pytest-cov` is a required dependency.

**Facts about mutmut 3.6.0 proven by execution — they CONTRADICT the ticket text, trust these:**
no `--paths-to-mutate` flag exists (scoping is `[tool.mutmut] only_mutate` read from CWD's
pyproject); **`mutmut run` exits 0 even when mutants survive**; mutant keys are
`pkg.mod.x_func__mutmut_N`, and `mutmut run <glob>` filters on them — which is how this gate scopes
to changed FUNCTIONS rather than changed files.

**Discarded from the stranded branch, with reasons:** it rewrote the repo's real `pyproject.toml` at
runtime (corrupts an owns-claimed file and leaves it corrupt if killed); no function-level scoping;
`changed==0 → return 0` was a plain FAIL-OPEN; it used the 99s coverage path.

⚠️ **NOT DONE / UNVERIFIED — do not assume any of this works:**
`tests/test_diff_cover_mutmut_gate.py` **does not exist**, so there is NO red-proof for either gate,
and `gates.json` currently FORWARD-REFERENCES that missing file. `ci.yml` untouched (will need
`fetch-depth: 0`). The fail-closed paths for unresolvable base / unparseable XML / missing tool /
untracked `src/**.py` are implemented but **NOT executed**. A REENTRY-GUARD (both gates exit 0 with
`WORK-UNITS: 0` under `PYTEST_CURRENT_TEST`) exists because `test_gate_contract.py` runs every
registered gate script and without it the suite **fork-bombs itself** — not yet red-proofed.
**`pyproject.toml` was NOT touched** (13 live tickets own it). Still owed: a `quality = [...]`
optional-dependency group.

**NEXT ACTION for whoever picks this up:** write `tests/test_diff_cover_mutmut_gate.py` (red→green +
the four unexecuted fail-closed paths + the reentry guard), add the `quality` extra, wire `ci.yml`
with `fetch-depth: 0`, and decide mutmut in-or-out against the 78s number.
