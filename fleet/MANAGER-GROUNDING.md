# CHARON FLEET — MANAGER SESSION GROUNDING (top-to-bottom)

Written 2026-07-25 by session `agen-kolar` for a fresh frontier model taking the MANAGER role.
Everything here is path-explicit. Where I am unsure, I say so — see **§14 GAPS**.

**Read `/home/stack/charon-private/fleet/BRIEF-PREAMBLE.md` too — it is binding on every sub-session you launch.**

> ### ⚠️ CORRECTIONS APPLIED AFTER ADVERSARIAL REVIEW (verdict: SHIP-WITH-FIXES, 10 wrong claims)
> Review: `/home/stack/charon-private/fleet/handoff-notes/GROUNDING-DOC-REVIEW-agen-kolar.md`
>
> 1. **`gate.sh` fork loop is BOUNDED on `origin/master`** (`gate.sh:56-63`, `JOBS` cap + `wait -n`).
>    My "unbounded at `:44-50`" was measured on a **local checkout 13 commits behind** and is FALSE.
>    This also resolves §14's "both cannot be right" — **the concurrency fix DID work.**
>    **Lesson: I cited line numbers without saying which ref. Always `git fetch` and state the ref.**
> 2. **SLOP's ticket DB is `/home/stack/code/mediastack/tracking/tracking.db`** — the path I gave in §3
>    (`mediastack/tracking.db`) exists but is **0 bytes**.
> 3. **The DENIED-git list is PROJECT-SCOPED to `/home/stack/code/charon`.** `charon-private` has no
>    `.claude/` and the global deny-list is empty — so §5's denials are not universal. Verify in your
>    own context rather than assuming.
> 4. **§5's "sub-sessions are NOT bound by these" contradicts `MANAGER-OPERATING-RULES.md:87`.** Treat
>    the rules file as authoritative; delegation is not a licence to bypass a deny-list.
> 5. **`BRIEF-PREAMBLE.md:42-45` is now the stale text on `guard-branch`** (it landed in PR #267, so it
>    IS on master). Fix the preamble, not this doc.
> 6. **Add to §2 grounding:** `git fetch` + a divergence check (`git rev-list --left-right --count
>    origin/master...HEAD`) and `gh auth status`. **This box is diverged right now** — error 1 above is
>    exactly what that omission causes.
>
> Verified CORRECT by execution: `land.sh:395/399/404`, `guard-branch` at `work-lease.sh:408` +
> `fleet-droid.sh:619` (PR #267 genuinely merged), `env-registry.sh:54-56`, `availability.py:197`,
> the gateway 302, all hosts/remotes, and `--push`/`--push-only` at `fleet-droid.sh:558-559`.

---

## 0. ONE-LINER TO START A SESSION

```
Read and fully follow /home/stack/charon-private/fleet/MANAGER-GROUNDING.md then the latest /home/stack/charon-private/fleet/SESSION-HANDOFF-*.md — you are the fresh Charon fleet MANAGER, carry it out, then flip to fleet mode.
```

The handoff is *state*; this file is *how the job works*. Read this first, handoff second.

---

## 1. WHAT THIS PROJECT IS

**Charon** is a locally-run, OpenAI-compatible **gateway** ("SG" = the Charon Gateway) that routes
LLM requests to the **cheapest capable provider that is actually available**, with failover,
cost metering, and spend caps. That gateway is **the shippable product**.

Around it sits a **build rig** (the "fleet") that uses the gateway to build itself: a board of
tickets, droid worker sessions that claim tickets and run off-Claude through the gateway, and a
manager session (you) that gates, sequences, reviews and lands.

**The north star:** a solo operator runs real work through the gateway, work outcomes grade the
models, and routing improves from real outcomes — not synthetic benchmarks.

**Two repos, and the boundary is load-bearing:**

| Repo | Path | Visibility | Role |
|---|---|---|---|
| PRODUCT | `/home/stack/code/charon` | **PUBLIC** (`github.com/SLOP-Platform/charon`) | The gateway. Must ship standalone |
| RIG | `/home/stack/charon-private` | private (`github.com/Nnyan/charon-private`) | Board, droids, gates, tooling |

**Never let rig paths, hosts, IPs or `/home/stack` strings into the product repo.** A public-clean
guard exists (`/home/stack/code/charon/tools/hooks/pre-commit`) — see §5.

---

## 2. FIRST 15 MINUTES — SESSION GROUNDING PROCESS

Do these in order. Do not skip 4 or 5; they are how you avoid inheriting stale beliefs.

1. **SessionStart hooks already ran** and printed: `MANAGER-OPERATING-RULES.md`, the tool inventory,
   the roadmap, repo sync status. Read them — do not re-derive.
2. `bash /home/stack/charon-private/fleet/pending.sh list` — **the operator decision list.** Persists
   across sessions, labels never reused. This is what the operator is waiting on. **Read it first.**
3. Read the newest `/home/stack/charon-private/fleet/SESSION-HANDOFF-*.md` (by mtime).
4. `bash /home/stack/charon-private/fleet/foreman.sh` — board health: tier starvation, collisions,
   quarantines, and *why*. Run it before assuming the board is healthy.
5. **Process-health check** (a crashed session once left a fork bomb at ~18,900 procs):
   `ls /proc | grep -cE '^[0-9]+$'` and `cat /proc/loadavg`. Abnormally high ⇒ investigate before working.
6. `gh api rate_limit --jq .resources` — GraphQL exhaustion silently breaks `gh pr list --json`.
7. Read `/home/stack/charon-private/fleet/STARTUP-FRICTION-LOG.md` (boot problems, newest on top).
   **Append your own at session end.**

---

## 3. WHERE EVERYTHING IS

### Hosts
| Host | Address | Role |
|---|---|---|
| **Tardis** (this box) | local WSL2 | Manager, droids, board, bench-grader. **All local sudo happens here** |
| **4-LOM** | `10.0.1.60` | Runs the gateway. `ssh -i ~/.ssh/4lom stack@10.0.1.60`. Data on `/data` |
| **Gitea (c1-10p)** | `http://10.0.1.52:3000` | Self-hosted git. Repo `stack/charon-private` is **PRIVATE** — anonymous curl 404 is expected, not a fault |
| **rocinante** | via SSH tunnel | Hosts the **session-bridge daemon** |

### Gateway (SG)
- Endpoint: **`http://10.0.1.60:8080`** — OpenAI-compatible. **Never `localhost`.**
- `/charon/status` → live pool/capped state. **Unauthenticated it returns HTTP 302 with a 0-byte body**, NOT 401. Any `== 401` check misses it.
- Client is swappable via `$CHARON_AGENT_CMD` (default `/home/stack/charon-private/fleet/charon-run.sh` → `opencode` CLI → `charon/<model>`).
- **The manager stays on Claude; droid WORK runs off-Claude through the gateway. Never route droid work to Anthropic.**

### Git remotes
- Rig: `origin` = `https://github.com/Nnyan/charon-private.git`; `gitea` = `http://10.0.1.52:3000/stack/charon-private.git`
- Product: `origin` = `github.com/SLOP-Platform/charon`
- **Operator decision (2026-07-24): Gitea becomes PRIMARY**, GitHub an async mirror, so a GitHub outage never blocks landing. Ticket `FORGE-PRIMARY-GITEA`. Not yet done.

### Key directories
- Board tickets: `/home/stack/charon-private/fleet/board/*.md` (one file per ticket); archive `.../board/archive/`
- Roadmap: `/home/stack/charon-private/fleet/state/ROADMAP.tsv`
- **`/home/stack/charon-private/fleet/state/` is GITIGNORED** — anything written there is untracked and one `git clean` from gone. Rescued artifacts live in `/home/stack/charon-private/fleet/handoff-notes/`.
- Reviews/audits: `/home/stack/charon-private/fleet/state/reviews/` (gitignored — copy out anything durable)
- Worktrees: rig `/home/stack/charon-private-wt/<NAME>`; product `/home/stack/code/charon-wt-<NAME>` or `charon-fleet-<NAME>`

### SLOP
**SLOP = the mediastack project at `/home/stack/code/mediastack`.** Its tickets live in
`/home/stack/code/mediastack/tracking.db` (SQLite). It is a **sibling project sharing doctrine**
with Charon — several rules here were ported from it (anti-accretion, single-entity-hardcode audit,
independent-review floor). Charon is the PUBLIC product; SLOP is separate. Cross-pollinate rules,
do not mix code.

---

## 4. KEYS AND TOKENS

- **Gateway bearer token: DERIVE IT, never trust the env.**
  `CHARON_GATEWAY_TOKEN` in the shell is **documented STALE** (`/home/stack/charon-private/fleet/env-registry.sh:54-56`).
  The live value is `/home/stack/.config/opencode/opencode.json` → `provider.charon.options.apiKey`,
  read by `bearer_token()` in `env-registry.sh`. **A `set-if-unset` export is a NO-OP** because
  `availability.py:197` *prefers* the stale variable — you must overwrite unconditionally.
- `~/.ssh/4lom` — key for 4-LOM.
- Bench-grader runs as its own unix user; its ledger `/home/stack/charon-private/fleet/model-scorecard.tsv` is grader-owned. **You cannot edit it — the operator runs `sudo -u bench-grader …`.**
- **Never print or commit a token.** The product repo is public.

---

## 5. APPROVED PATHS — PUSHING, LANDING, AND WHAT IS DENIED

### DENIED to the manager (settings deny-list; verbal authority does not override)
`git push` · `git merge` · `git rebase` · `git reset --hard` · `git remote add` · `git config` ·
`--force` · `--no-verify`. **Sub-sessions are NOT bound by all of these** — delegate a rebase to a sub.

### The sanctioned paths
| Need | Command |
|---|---|
| Publish a branch (no merge) | `bash /home/stack/charon-private/fleet/land-push.sh <branch> <repo-or-worktree>` |
| Full land (commit→gate→PR→merge→sync→done-mark) | `bash /home/stack/charon-private/fleet/land.sh <branch> <worktree>` |

- **`land.sh` DOES create the PR** (`:395` create, `:399` ready, `:404` merge). An old handoff claimed otherwise; that is false and cost many sessions.
- `land.sh` needs HEAD on the branch; use `land-push.sh` for a named branch.
- **`land.sh` runs `validate_board.sh` for the RIG — not the test suite.** So rig merges are currently **not test-gated**. A fix exists unlanded on `fix/land-gate-rig-suite` (flip `LAND_RIG_TESTS` at `land.sh:320`). **Do not arm it while reds stand — it halts all rig landing.**
- `rc=8` = base-sync refused (usually the main checkout is dirty). The merge is still valid.
- **AUTONOMOUS lever**: `/home/stack/charon-private/fleet/state/AUTONOMOUS` exists ⇒ ON ⇒ you may push without asking. Check it (`bash fleet/autonomous.sh status`) before deciding.

### Committing
- **`git add` aborts entirely if ANY pathspec fails** — nothing stages, and a later commit can silently capture only what was already staged.
- **Always `git commit -- <paths>` (pathspec-limited).** Bare `git commit` takes the **whole index** — `land.sh:341-342` does exactly this and swept another lane's staged work. Always check `git diff --cached --name-only` first.

---

## 6. HOW WORK FLOWS

```
ticket on the board  →  droid claims it (claim.sh, flock-serialised)
                     →  worktree + branch created (guard-branch refuses unmapped branches)
                     →  work runs OFF-CLAUDE through the gateway (charon-run.sh → opencode)
                     →  commit (work-lease hook enforces ticket mapping)
                     →  manager reviews adversarially  →  land.sh  →  auto-done-mark
```

- **Every branch must map to a board ticket** via a `branch:` field. `work-lease.sh guard-branch`
  (landed PR #267, at `work-lease.sh:408`, wired `fleet-droid.sh:619`) refuses unmapped branches
  **at dispatch**. **Create the ticket BEFORE firing a sub that will commit** — five branches needed
  `WORK_LEASE_BYPASS=1` in one session because tickets came after the work.
- Tiers: `economy` / `strong` / `frontier`. **Tier is a capability FLOOR** — escalate up, never below.
- Every ticket carries **Dependencies & Sequence**, `owns:`, and fail-on-revert acceptance.

---

## 7. LAUNCHING SG TABS (the operator does this, not you)

**Standing rule: the MANAGER never spawns droids.** You make work claimable and give the operator the
exact command; they open the tab.

**Pull mode (classic):**
```
bash /home/stack/charon-private/fleet/fleet-droid.sh strong --wait 3 --retries 10
```
Always give the flags. Tiers: `economy` | `strong` | `frontier`.

⚠️ **Launch from an interactive WSL bash shell.** From PowerShell→bash (non-login, non-interactive)
neither `.bashrc` nor `.profile` runs, so `~/.local/bin` is off PATH and `opencode` is not found —
every session dies rc=127 and gets misreported as model exhaustion. A fix (PATH export + a
`command -v opencode` preflight + gateway preflight before the claim loop) is on
`fix/DROID-CLIENT-PREFLIGHT-PATH` @ `8f0a4e5`, **pushed but not landed**.

**PUSH / IDLE mode (new, on that same branch, not yet landed):**
A droid can now **idle until the manager dispatches work to it**, instead of polling the board.
- Opt-in flags `--push` / `--push-only`; hybrid **degrades loudly to pull** if the bridge is unreachable.
- It **registers on the session-bridge**, and idles blocking on `board()` — **the poll IS the heartbeat**, so liveness is free.
- Dispatch carries a **ticket id only**, so every existing gate still runs and no dark work is possible.
- The bridge is a **REMOTE daemon on `rocinante`** via SSH tunnel → `~/.charon/coordinator-charon.sock`.
  **`/tmp/charon-bridge.sock` does not exist and its absence is NOT evidence the bridge is down** — a design pass concluded exactly that and was wrong.

**Before telling the operator to launch:** run `foreman.sh` and prove work is claimable with a
dry-run (`CLAIM_ONLY=<id> bash fleet/claim.sh --dry-run <tier> probe own-only`), and check
`fleet/state/POOL-PAUSED` does not exist (it halts all claiming).

---

## 8. BEING THE MANAGER — THE ROLE

**You are a COORDINATOR, not a worker.** You gate, sequence, commit, push, and talk to the operator.

- **Launch ALL substantive work in background sub-sessions** — investigation, audit, implementation, even a broad grep.
- Subs **write findings to a file and return a pointer + ≤6 lines**. Never let a sub paste logs or diffs back — that is the single biggest context multiplier.
- Hand each sub the FACTS (exact paths, prior findings, "do not re-derive") so it does not re-investigate.
- **One writer per file. Ever.** Use separate worktrees; each has its own git index.
- Money-path / security / gate-critical changes get an **independent adversarial review before merge**. Self-reports lie — review the diff.
- **Never dismiss a pre-existing red** as "not mine". Fix it or ticket it.
- **Fix the CLASS, not the instance.** On any finding: name the class, auto-scan for other instances *unprompted*, fix or ticket the class as one shared primitive.
- **Adopt-first.** Before building anything, check whether we already have it. Hand-rolling carries heavy negative weight and must be argued adversarially.

---

## 9. RULES WE WORK BY (the ones that bite)

1. **GREEN IS NOT PROOF.** Red-proof by execution; non-vacuous (zero items = RED); fail-loud (non-zero exit, never masked by `| tail`, `| head`, `|| true`, or a missing `set -o pipefail`).
2. **Slowness is a failure class.** Never bump a timeout — root-cause it.
3. **Anti-accretion.** Extend an existing gate; a new per-instance script is forbidden.
4. **Latency, security and money-path changes need e2e + dogfood**, not unit tests alone.
5. **Present decisions in colour-coded tables**, not walls of text. Outcome first, tickets nested under it.
6. **Give literal copy-pasteable commands** for anything the operator must run, naming the host.
7. **Work in phases: gather → present → WAIT.** Do not stack the next move on an unanswered question.
8. **Bundle = GROUP by lens at the same priority, tickets kept SEPARATE** so agents work in parallel. Merging tickets into fat serial ones is the anti-pattern.
9. **Batch reports**: 3+ sub completions before summarising, not one-by-one.
10. **Token-lean by default** — but never trim rigor (adversarial review, fail-on-revert tests, live verification). Economy means cutting *your own narration*.

---

## 10. REPORT FORMATS THE OPERATOR EXPECTS

**Status / findings — colour-coded table, minimal prose:**
🟢 go/confirmed · 🟡 caution/conditional · 🔴 blocked/no · 🔵 info/pending

**Roadmap** — `bash /home/stack/charon-private/fleet/report.sh` output **VERBATIM**. Never summarise,
prepend, or reformat it. Print it at session end.

**"TL"** → one plain-language line per ACTIVE ticket; skip done/parked.

**Decisions** → `bash /home/stack/charon-private/fleet/pending.sh add "<item>"`; clear with
`pending.sh done <LABEL>`. Labels are never reused, so "answer W" can only ever mean one thing.
**Put decisions on the list the moment they arise** — do not rely on the operator catching prose.

**Recommendations** — always give your pick with **gains / losses**, not a neutral survey.

---

## 11. PRIORITIES AND WORK ORDER

**Project priority (default sequencing):** ROUTER > BRIDGE > FLEET > SECURITY > BACKLOG.
Overrides that jump the queue: (1) acute security incident, (2) a dependency blocking higher work,
(3) a hard deadline, (4) a broken rig/gate blocking all work.

**Priority field:** integer **0..5, LOWER = more urgent** (`/home/stack/charon-private/fleet/state/PRIORITY-LADDER.md`).
The board already carries ~38 P0s — do not reflexively stamp 0; a board where everything is P0 has no priority.

**The current bottleneck is LANDING, not building.** ~21 branches were built and pushed but unmerged;
~34 of ~40 blocked board edges wait on them. **Landing is the highest-leverage act available.**

---

## 12. KNOWN ISSUES AND CHALLENGES

| Issue | Detail |
|---|---|
| **Rig merges are NOT test-gated** | `land.sh` runs `validate_board.sh` only. Fix unlanded on `fix/land-gate-rig-suite` |
| **Gate reds** | 68 pass / 10 fail on master; **8 fail standalone on an idle box** = real, not flakes |
| **`gate.sh:44-50` unbounded fork loop** | 78 suites at once on 16 cores → `fork: Resource temporarily unavailable`, non-deterministic results |
| **33 never-run test files** | Named `test_*.sh`, which `gate.sh`'s `*.test.sh` glob never matches. 7 guard money/security/data-loss |
| **`fleet/state/` is gitignored** | Every review, audit and resume note is untracked. Copy anything durable to `fleet/handoff-notes/` |
| **Bridge daemon unsupervised** | Remote on `rocinante`; monit not installed (gated on `WATCHDOG-RESTART-CMDS-VERIFY`) |
| **Grader** | Has **never validly discriminated** — needs `bench-grader` sudo provisioning. Model rankings are therefore suspect |
| **Scorecard corruption** | 42 of 46 lifetime BLOCK enqueues were **infra faults, not model failures**. One merged row cleared; P1 ticket covers the rest |
| **Economy tier starved** | Legitimately — the board is nearly all gate/money-path work. Idle economy tabs are CORRECT, not a fault |
| **`preflight.sh` is a god-file** | 906 lines, 8 inline gates, 6 owners. Decomposition approved: extract each to `fleet/checks/<gate>.sh` **after** the `_gate_run` helper lands |

---

## 13. THINGS CAUGHT THAT I WOULD HAVE MISSED

Read this section as a list of *how* to be wrong here, not just *what* was wrong.

1. **`git cherry` gives FALSE NEGATIVES.** Work lands by **re-derivation**, not cherry-pick, so dead branches still report unique commits. Six branches looked live and were fully landed. **Prove liveness by CONTENT** (diff owned files vs master + look for an archived `status: done` ticket).
2. **"X does not exist" is only true if you checked the right ref.** Two sessions declared `work-lease.sh guard-branch` missing by grepping *master* while it lived on an unlanded branch. A sub refused my wrong correction and was right.
3. **A `set-if-unset` env export can be a silent no-op** — `availability.py:197` prefers the stale variable, so the "fix" would have changed nothing.
4. **The gateway returns 302, not 401** — any `== 401` preflight misses the failure entirely.
5. **A missing client got reported as model exhaustion**, marking four healthy models BLOCK. The conflation, not the missing binary, was the defect.
6. **Empty ≠ error.** A well-formed but empty `{}` snapshot read as "nothing capped" and handed over the full chain. Closing "could not ask" did not close "asked, answer was empty".
7. **A test fixture used `{"pools":{}}` to mean "nothing capped"** — the same defect living inside the tests meant to prove it.
8. **A budget breach silently disabled a gate**: `parallelizability-gate.sh` needs ~21.7s against a hardcoded 15s, so it reported failure-to-run and the board still printed GREEN.
9. **`optional:true` turned a gate whose enforcer does not exist into a SKIP that reports OK** — an affirmative green for work never done.
10. **Documentation asserted security behaviour from dead code** — `ADR-0019:166` listed two never-executed modules as key-bearing egress sites.
11. **`git commit` takes the whole index** — a lane's staged work was swept by another lane's commit.
12. **Relaying numbers between subs compounds errors.** I did it three times (a tier direction, a gate count, `guard-branch`). **Re-derive anything you are handed, and state which ref you measured.**

---

## 14. MY GAPS — WHAT I AM LEAST CONFIDENT ABOUT

Stated plainly so you do not inherit false confidence:

- **The true gate red count.** I reported 76/2, then 68/10. The later figure came from three stable runs on an idle box and is more trustworthy — but I never reconciled the two, and `gate.sh`'s fork-loop makes counts environment-dependent. **Measure it yourself before acting.**
- **Whether `gate.sh`'s concurrency fix actually worked.** One sub claimed to bound it (landed PR #265); another later found the unbounded loop at `:44-50`. Both cannot be right.
- **How much of the scorecard is salvageable.** 42/46 BLOCKs were infra. I do not know whether `grades.py`/`assign.py` derive live from rows (removal suffices) or cache rankings (a recompute is needed). **Unresolved and it matters.**
- **SLOP.** I know it is `/home/stack/code/mediastack` with `tracking.db`, and that doctrine flows both ways. I did not work in it this session and cannot vouch for its current state.
- **Gitea readiness.** Branch protection there is the real fix for the un-gated merge problem (GitHub's free tier 403s on it for private repos). I verified the 403; I did **not** verify Gitea CI can run the suite.
- **Whether the idle-push droid works end to end.** Its own tests pass (and caught two real bugs), but `droid-bridge.test.sh` last ran 41/1 with the single failure being a *test* bug whose fix was not re-run.
- **The six retired gateway modules.** I am confident they had zero invocation sites; I am less confident nothing external (a config file, an operator runbook) still expects them.

---

## 15. GENERATING A HANDOFF

1. During the session: `SESSION=<name> bash /home/stack/charon-private/fleet/checkin.sh <args>` per ticket.
2. Generate machine state: `SESSION=<name> bash /home/stack/charon-private/fleet/handoff.sh` → write to `/home/stack/charon-private/fleet/SESSION-HANDOFF-<name>.md`. **Prefer generating over hand-writing** — the GENERATED-STATE block is machine-queried and cannot be hand-asserted.
3. **MANDATORY:** `bash /home/stack/charon-private/fleet/handoff-check.sh fleet/SESSION-HANDOFF-<name>.md` must exit **0**. It verifies required sections, that every referenced SHA/path/branch exists, a `**Session:**` provenance stamp (anti-clobber), and that behavioural claims about rig scripts cite a real `file:line`.
   **Do not pipe it through `| tail` — that masks the exit code.** (I did exactly this and read a FAIL as rc=0.)
4. Commit the handoff. Append to `/home/stack/charon-private/fleet/STARTUP-FRICTION-LOG.md`.
5. Print the roadmap: `bash /home/stack/charon-private/fleet/report.sh`.
6. **Copy anything durable out of `fleet/state/` into `fleet/handoff-notes/`** — `state/` is gitignored.
7. Session names: pick a NEW unused Jedi name — `bash /home/stack/charon-private/fleet/claim-jedi-name.sh`. Never reuse.

---

## 16. TOOL INDEX (full paths)

| Purpose | Path |
|---|---|
| Operator decision list | `/home/stack/charon-private/fleet/pending.sh` |
| Board health / starvation | `/home/stack/charon-private/fleet/foreman.sh` |
| Board validity (**the rig merge gate**) | `/home/stack/charon-private/fleet/validate_board.sh` |
| Full rig test suite | `/home/stack/charon-private/fleet/gate.sh` |
| Session preflight | `/home/stack/charon-private/fleet/preflight.sh` |
| Claim a ticket | `/home/stack/charon-private/fleet/claim.sh` |
| Ticket↔branch lease + `guard-branch` | `/home/stack/charon-private/fleet/work-lease.sh` |
| Launch a droid | `/home/stack/charon-private/fleet/fleet-droid.sh` |
| Off-Claude runner | `/home/stack/charon-private/fleet/charon-run.sh` |
| Publish a branch | `/home/stack/charon-private/fleet/land-push.sh` |
| Full land | `/home/stack/charon-private/fleet/land.sh` |
| Quarantine control | `/home/stack/charon-private/fleet/loop-guard.sh` |
| Roadmap (verbatim) | `/home/stack/charon-private/fleet/report.sh` |
| Handoff generate / verify | `/home/stack/charon-private/fleet/handoff.sh` · `handoff-check.sh` |
| Autonomous lever | `/home/stack/charon-private/fleet/autonomous.sh` |
| Gateway token derivation | `/home/stack/charon-private/fleet/env-registry.sh` (`bearer_token()`) |
| File-contention detector | `/home/stack/charon-private/fleet/wci-contention.sh` |
| Code map | `graphify explain "X"` / `graphify path "A" "B"` (`~/.local/bin/graphify`) |
| Doctrine (behaviour) | `/home/stack/charon-private/fleet/MANAGER-OPERATING-RULES.md` |
| Sub-session rules (binding) | `/home/stack/charon-private/fleet/BRIEF-PREAMBLE.md` |
| Rescued session artifacts | `/home/stack/charon-private/fleet/handoff-notes/` |

**Not yet on master (pushed, unlanded):** `fleet/board-lock.sh` (`fix/board-write-lock` @ `6ef1fb1`, PUSHED),
`LAND_RIG_TESTS` (`fix/land-gate-rig-suite` @ `506caa1`, PUSHED), the droid PATH/token/push-mode fixes
(`fix/DROID-CLIENT-PREFLIGHT-PATH`).
