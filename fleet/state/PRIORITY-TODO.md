# ⛔⛔⛔ STOP — READ THE 2026-08-02 HANDOFF FIRST ⛔⛔⛔
#
#   fleet/state/HANDOFF-2026-08-02-sifo-dyas.md
#
# It SUPERSEDES this file's queue for one session, carries the operator's U/V decisions with
# their reasoning, and contains the lessons from a session the operator judged UNPRODUCTIVE.
# Work ITS queue in order. Do not re-derive priorities from the sections below.
#
# KNOWN-WRONG in this file: section L claims SESSION-END-PUSH-GATE was dropped. FALSE — it
# landed via PR #130. Done-marker misattributed, ROADMAP row stale.

# BOOTSTRAP — COPY-PASTE THIS INTO THE NEXT SESSION

```
Read /home/stack/charon-private/fleet/state/PRIORITY-TODO.md FIRST (it is the carry-forward list and
opens with FIRST THINGS), then flip to fleet mode. Run the three section-0 commands before anything
else. Top of the queue is ZERO-COMMIT-SPIN — the fleet claims work and produces nothing.
```

**Why this block lives HERE and not only in a generated handoff:** `handoff.sh`/`end-session.sh`
normally emit it, and they ABORT before they can (the self-blocking allocator, queue item #3). A
bootstrap that only exists in a generator that cannot run is a bootstrap that does not exist.
Keep this block in this file until #3 lands.

---

# ⛔⛔⛔ FIRST THINGS — NEXT SESSION, IN ORDER, NON-NEGOTIABLE ⛔⛔⛔

**Operator directive 2026-08-02. Do these BEFORE anything else. Do NOT delete an item — mark it
`[DONE <sha/PR>]` or `[DROPPED — reason]`. An item that vanishes is the failure this file exists
to prevent.**

## 0 — RUN THESE THREE, EVERY SESSION, FIRST (they take ~2 minutes)
```
bash fleet/checks/stranded-work.sh          # all 5 work-loss shapes
bash fleet/checks/gate-integrity.sh scan    # inert / falsely-claimed / unproven gates
bash fleet/rescue-push.sh                   # at-risk branches (dry run)
```
Then confirm the cadence is ALIVE, not merely registered:
```
crontab -l | grep -c stranded-work-cron     # must be 1
cat fleet/state/.stranded-work.heartbeat    # must be < 20 min old
tail -5 fleet/state/cron-rescue.log         # rescue half must be running too
```
**A registered job that never executes reads as clean. That is the failure mode. Check leg B.**

## 0b — SURFACE THE OPERATOR ACTION LIST TO THE HUMAN, RIGHT AFTER GROUNDING

The tracked `fleet/hooks/session-start.sh` now prints it UNCONDITIONALLY at boot (verified
2026-08-02 by running the hook). **Report it to the operator in your first substantive reply** —
do not just let it scroll past.
```
bash fleet/pending.sh list          # if you need it again mid-session
```
WHY IT IS IN THE HOOK AND NOT ONLY IN PREFLIGHT: `preflight.sh:909` does print it, but that line
sits BEHIND the reconcile-merged output, which ran to hundreds of lines on 2026-08-02 and starved
every late leg — a 200s-capped preflight never reached it at all. **An action list the session does
not see is an action list that does not exist**: operator action #15 (~10 commissioned review
verdicts) went UNREAD for THREE sessions exactly this way.
TRIAGE IT, do not just print it — most entries are STALE. Retire what is closed and say which are
genuinely still open, because a noisy list is the mechanism by which the real ones get missed.

## 1 — REPORT PROGRESS ON THIS LIST EVERY 5 COMPLETED TASKS
Print: item · state · evidence (sha/PR/command output). No prose-only claims. If an item has not
moved in two reports, say so explicitly and why.

# ⚖️ HOW TO PRIORITISE — THE NINE LENSES (apply ALL of them, every time)

**Operator-directed 2026-08-02, made durable so it is not re-derived each session.** Blast radius
alone produces the wrong order. Rank by applying EVERY lens below, then say which one decided it.

| # | lens | the question it asks |
|---|---|---|
| 1 | **Unblocks execution** | does anything else become POSSIBLE? A fleet that produces nothing makes every other rank academic |
| 2 | **Prevention at source** | does it stop a CLASS recurring? Every day a source-fix is absent, more debt lands |
| 3 | **Hard dependency** | can X even start without Y? Build in the order the data flows |
| 4 | **Cost-to-value** | a ONE-LINE fix that unblocks the fleet outranks a week-long one that does not |
| 5 | **Compounding** | does NOT fixing it get worse on its own? (drafts grow monotonically; the name pool burns down; owns-overlap self-reinforces) |
| 6 | **Surfacing multiplier** | does it make ALL future problems visible, rather than fixing one instance? |
| 7 | **Irreversibility** | can work be permanently LOST? (this is why RESCUE was item 0 on 2026-08-01) |
| 8 | **Operator's explicit asks** | weighted AS STATED, not re-litigated. If your analysis conflicts with a stated priority, SAY SO and ask — do not silently override |
| 9 | **Money & hard rules** | money-path and standing HARD rules are elevated regardless of ticket size |

## THE TWO ORDERING MISTAKES THIS REPLACES
- **Ranking cleanup above prevention.** Draining a backlog while its source is unfixed refills it.
  Fix the source, then drain — otherwise both lanes run forever.
- **Ranking big-and-important above small-and-blocking.** A one-line prerequisite buried in a
  parenthetical (SESSION-END-GATE-REPAIR was, on 2026-08-02) stalls everything behind it while
  looking like a footnote.

## THE TEST TO APPLY BEFORE ACCEPTING ANY ORDER
For each item ask: **"if this lands, what STOPS happening?"** An item that prevents a class beats an
item that cleans one instance of it. Then: **"can the next item even start without it?"** If yes,
they are independent and can run in parallel tabs — say so, do not serialise by habit.

---

## 2 — THE QUEUE (ordered by the nine lenses above, not blast radius alone)

**PHASE 0 — RESTORE EXECUTION.** Nothing else can be *done by the fleet* until these land.
| # | ticket | deciding lens |
|---|---|---|
| **1** | `ZERO-COMMIT-SPIN` | **L1 unblocks execution.** The fleet CLAIMS work and produces NOTHING — live, 8 tickets, re-quarantining within minutes. Every other rank is academic while this holds. No session log and no gate result exist for the spinning ticket while the SAME droid logs normally elsewhere: **the session never starts** |
| **2** | `BOARD-VIEW-MISMATCH` | **L6 surfacing + L3 same code path as #1.** status.sh says `ready`, claim.sh silently skips for FIVE more reasons and `--only` is silently overridden. Diagnosing #1 needs this instrumented — one investigation, not two |

**PHASE 1 — CHEAP + PREVENTIVE.** All small, all high-leverage. Do them before anything large.
| # | ticket | deciding lens |
|---|---|---|
| **3** | `SESSION-END-GATE-REPAIR` | **L4 one line, L3 blocks #9, L5 the name pool is down to ~9.** `[ -e ]`->`[ -s ]` at `claim-jedi-name.sh:47`. Also restores the next-session BOOTSTRAP, which vanished with this gate |
| **4** | `NEVER-ANTHROPIC-ASSERTION` | **L4 one test + L9 hard rule.** opencode-zen now serves `claude-*` live. No chain uses them TODAY — that is exactly when to add the assertion, not after it regresses again |
| **5** | `SPILL-UP-CEILING-SSOT` | **L4 one key.** `SPILL_UP_COST_CEILING` is absent from the SSOT the launcher reads, so cost spill-up FAILS CLOSED on every tab, right now |
| **6** | `TOOLS-FULLY-WIRED-CAMPAIGN` — **LEDGER PHASE ONLY** | **L8 operator's #1 + L6 makes everything else measurable.** Define the bar (W1 reachable · W2 invoked on cadence · W3 **SEEN TO FAIL** · W4 findings reach a human · W5 unused capability enabled or explicitly declined) and build the row-per-tool ledger from the EXISTING audit. Cheap. Remediation is phase 3 — the ledger is not |
| **7** | `GRAPHIFY-AFFECTED-WIRE` | **L3 feeds #8 + L8 tools.** 0 call sites vs 114 for `update`. Build it first and WIRING-DONE-CONTRACT gets reachability for free instead of hand-rolling a second traversal |

| **7b** | `DIVERGED-BRANCH-TRIAGE` — **reporting half only** | **L4 cost-to-value + L6 surfacing.** 7 branches report at-risk EVERY cycle and always will (diverged; content SAFE on `rescue/*`). The cadence detector reports `n=8` every 20 min and **SEVEN are permanent — the brand-new work-loss alarm is ~87% noise on day one**, so a genuinely NEW stranded branch would be invisible in it. Add a distinct `diverged-parked` shape counted SEPARATELY. **Do NOT suppress them** — silence is how the class returns |

**PHASE 2 — STOP NEW DEBT AT SOURCE.** Every day these are absent, more debt lands. Prevention before cleanup.
| # | ticket | deciding lens |
|---|---|---|
| **8** | `WIRING-DONE-CONTRACT` | **L2 prevention at source.** done.sh proves MERGED, never REACHABLE. Landing this means the 9 inert checks, the 101 unrun proofs and the zero-importer LiteLLM plane **never recur** — it is why they happened at all |
| **9** | `PROOF-SUITES-ENFORCE` — **INFLOW GATE HALF** | **L2 + L5 compounding.** 101 suites declare red-proof and never execute, and the count ROSE 91->101 in one day. Gate the inflow FIRST; the burn-down is phase 3. Landing both together avoids the day-one RED that gets a gate switched off |
| **10** | `SESSION-CLOSE-COMPLETENESS-GATE` (+ `TASK-LIST-DURABILITY-GATE`) | **L2 + L7 irreversibility.** Assertions A-E: harness tasks have a durable home · the session VERIFIED its own claims · cadence leg-B fresh · no invisible tickets · no stale operator actions. Needs #3 or every assertion is dead code |

**PHASE 3 — DRAIN WHAT HAS ACCRUED.** Safe to do now that the sources are plugged.
| # | ticket | deciding lens |
|---|---|---|
| **11** | `PR-QUEUE-DRIVE` | **L5 compounding + L8.** 67 open PRs, **52 DRAFTS, up from 42 in one session** — the launcher opens a draft per ticket and nothing merges, so it grows with throughput. TOKEN-LEAN: reviewer tabs off-Claude, `--retries` FINITE, 1-2 tabs until #392 lands |
| **12** | `PR-AUTOMATION-EVAL` | **L2 stops it re-forming + L3 after the drain.** Draining by hand produces the measured friction the bar must be written from. Both halves, 5 disqualifying criteria, adversarial pass REQUIRED |
| **12b** | `DIVERGED-BRANCH-TRIAGE` — **triage half** | **L5 compounding, L7 does NOT apply (content is safe).** Per-branch merge decisions: superseded / still-wanted / dead. `feat/ft-limits-groq-reconcile` shows **706** local-only commits — verify that is a broken upstream ref before treating it as 706 pieces of work. **NEVER force-push to resolve a divergence** — the remote side holds commits the local lacks |
| **13** | `TOOLS-FULLY-WIRED-CAMPAIGN` — remediation · `INERT-CHECKS-WIRE` · `MONIT-INSTALL-OR-RETIRE` · land **PR #209** · `LITELLM-COST-ADOPT` · ruff/mypy/shellcheck chain | **L8 operator's #1, executed.** The ledger from #6 says what to fix; this is fixing it. monit must be INSTALLED-and-proven or RETIRED — a paper adoption blocks the search for a real one |

**PHASE 4 — DETECTION LAYER.** Register into it only what is already proven to fire.
| # | ticket | deciding lens |
|---|---|---|
| **14** | `FLEET-STATUS-BOARD` + `MISSING-CLASS-DETECTORS` + `THROUGHPUT-EXPECTATION-ALARM` | **L6 surfacing.** FSB watches the WATCHERS; it does NOT notice a worker that stopped producing or an artifact that stopped appearing. All three together, or the class is only a third closed. **Substrate check MANDATORY first** — dead-man's-switch and Prometheus/OTel have ZERO registry rows |

**PHASE 5 — MONEY & INTEGRITY.** Gated on a trustworthy meter, which is gated on the above.
| # | ticket | deciding lens |
|---|---|---|
| **15** | money: `SPEND-METRIC-TRUSTWORTHY` · `COST-PER-TASK-REPLAY` · `PRICING-FEED` · `ZEN-GO-ROUTING-POLICY` | **L9 money.** The meter is fiction BOTH ways (\$1,185/2 days vs ~\$1.34 real). \$/token is the WRONG UNIT — cost per ACCEPTED task. zen must serve FREE models only; it currently serves 60 incl. paid |
| **16** | `OWNS-OVERLAP-DISAMBIGUATE` · `DROID-IDENTITY-THIRD-PARTY` | **L2 + L9.** The reconciler asks an unanswerable question; our commits are attributed to a STRANGER's GitHub account |

**PARALLELISM:** phases are a dependency order, NOT a serialisation. Within a phase, items with
disjoint `owns:` should run in separate tabs simultaneously. #4, #5 and #7 are independent of each
other and of #3 — three tabs, not three days.

## 3 — LOOSE ENDS FROM 2026-08-02 (mine, unfinished — process these)
- **189 `pushed-no-pr`** branches · **57 `closed-pr-unlanded`** · **17 dirty worktrees**
  (tickets exist: PUSHED-NO-PR-TRIAGE, CLOSED-PR-UNLANDED-TRIAGE, DIRTY-WORKTREE-SWEEP)
- **`rescue/*` refs never triaged** — they hold the LOCAL side of 4 diverged branches. Do not
  delete until the divergence is resolved by hand
- **Stale operator-action markers never retired** — the list is at #32 and mostly closed, which
  is why #15 has gone unread for THREE sessions
- **7 tickets re-quarantined then cleared without diagnosing the cause** — see item 2

## 4 — HANDED TO ME, STILL NOT DONE (carried from the 2026-08-01 handoff)
- §C — 13 ticketed-but-inert, 10 never-ticketed, **101 unrun proof suites**
- §D — `import-linter` adopt-test; KS29/KS30 still `designed`
- §E — 5 `review-pool.sh` defects (a 6th found today); `--wait/--retries` STILL dropped by its
  own dispatch (`main_loop "$CMD"`)
- §F2 — doctrine loads from `.claude/settings.local.json`, machine-local and untracked. A fresh
  clone loads NOTHING
- §M2 — 4-LOM runs image `v0.6.1`; deployed gateway lacks everything landed since
- **#15 — Letta + memory-layer reviews: ~10 verdicts commissioned, completed, NEVER READ.**
  Survived 3 sessions. `grep -c Letta EVAL-REGISTRY` = 0
- **#17 — 4 GATE-3 tickets approved 2026-07-31, never staged:** SPAWN-VIA-CAPABILITY,
  ENGINE-CONVERGE, PRICING-FEED (now minted), ORCHESTRATION-RE-RUN

## 5 — NEEDS THE OPERATOR

- **[RANKED WITH #10] A SECOND GITHUB IDENTITY THE OPERATOR CONTROLS.** `charon-bot` is NOT ours —
  `gh api users/charon-bot` resolves to a real third party ("Mr. Charon", created 2018-11-05), and
  the operator has confirmed they never had such an account. So operator action #23 was never
  actionable. TWO things follow, and they are separable:
    (a) CODE, ticketed as `DROID-IDENTITY-THIRD-PARTY` (P0, queue #10) — stop stamping droid
        commits as `charon-bot@users.noreply.github.com`, which maps to THAT PERSON'S account on a
        PUBLIC repo. Fix the default to an address resolving to nobody (`@fleet.local`, the shape
        the launcher already uses). This does NOT need the operator.
    (b) OPERATOR — create a bot account you control, if we still want reviewer!=builder (GitHub
        refuses request-changes on your own PRs) AND a second 5000-point API quota pool
        (see action #31; GraphQL was the binding constraint all of 2026-08-02).
  (a) is unblocked and should just be done. (b) is a real decision — a second identity is
  optional, the misattribution fix is not.

- **MONTHLY SPEND CAP — HOLD.** `monthly_limit_usd` is GLOBAL (not per-provider) and `0.0`
  (uncapped). Do NOT pick a number yet: the meter reads \$1,185 for two days of August against
  ~\$1.34 of measured real spend, and has no per-provider breakdown. Capping against a meter that
  is wrong in both directions either throttles everything instantly or does nothing. Set it AFTER
  `SPEND-METRIC-TRUSTWORTHY` lands.

- **~~opencode-zen / opencode-go registration~~ — DONE, NOTHING NEEDED.** VERIFIED 2026-08-02 on
  the live gateway: both entries carry `base_url` AND `key_env`, the secret is in
  `/data/secrets.json`, and both ROUTE — opencode-go serves 2 models (`deepseek-v4-flash-go`,
  `minimax-m2.5-go` — the latter is in the live strong chain), opencode-zen serves 60.
  **Operator action #18 is STALE** and should be retired; its claim that opencode-go has "only
  funding_class, NO base_url and NO key_env" is no longer true.

- **⚠ NEW RISK, needs a decision:** `opencode-zen` exposes `claude-*` models
  (`opencode-zen/claude-opus-4-1`, `claude-fable-5`, `claude-haiku-4-5`, ...). The standing HARD
  rule is **SG never routes via Claude/Anthropic**, and that rule is on record as one that KEEPS
  REGRESSING. No current tier chain includes them, so we are clean TODAY — but they are now
  reachable through a live provider, which is precisely the setup for a silent regression. Either
  exclude `claude-*` from opencode-zen at the pool layer, or add an assertion that no tier chain
  may contain an Anthropic-served model. Recommend the assertion — it survives catalog refreshes.

## 6 — THE RULE THAT GOVERNS ALL OF IT
**Wiring is proven by making the check FAIL on a deliberate violation.** Registration is not
proof. "Merged" is not proof. A green that has never been red proves nothing. Two shapes caused
6 of 8 PR bounces on 2026-08-02: a safety property asserted only in prose, and a suite that
passes against a mock of the component under test.

---

# ⚠️ FRICTION FROM 2026-08-02 — DO NOT REPEAT THESE

**Every item below cost real time in the last session. Each is stated as a COMMAND or a RULE, not
advice. Read this before you touch anything.**

## F1. GROUND ON THE TOOL INVENTORY BEFORE LAUNCHING ANYTHING
I launched droids with `run_in_background` for HOURS. They were children of my own session:
invisible to the operator and dead the moment the session ends. The operator had to tell me
THREE times. `fleet/TOOL-INVENTORY.md` and `fleet/spawn-tab.sh` existed the whole time.
**The ONLY correct launch commands:**
```
bash fleet/spawn-tab.sh <name> '<#hex>' bash fleet/fleet-droid.sh <economy|strong|frontier> --wait 2 --retries 0
bash fleet/reviewer-tab.sh --tier <strong|frontier> --wait 5 --retries 0
```
`reviewer-tab.sh` is a LAUNCHER-OF-A-LAUNCHER — it spawns its own tab and exits. Do NOT wrap it
in `spawn-tab.sh` (double-spawn). Its CLI is `--tier strong`, NOT a bare `strong`.
**Verify a tab is REAL, not a child of your session:**
```
for p in $(pgrep -f 'bash .*fleet-droid\.sh'); do echo "$p ppid=$(ps -o ppid= -p $p|tr -d ' ')"; done
```
VERIFIED 2026-08-02: a real detached tab shows a `bash`/`timeout` parent from the WT spawn chain,
NOT pid 1. The test is: does the ppid chain trace back to YOUR shell? If yes it dies with you.
(My first draft of this rule said 'ppid 1 = detached' — that is WRONG and would fail every time.)

## F2. THE HANDOFF'S CLAIMS ARE STALE — VERIFY EVERY ONE BEFORE ACTING
Five load-bearing claims were WRONG last session; each cost a wrong decision:
| claim | reality | command that would have caught it |
|---|---|---|
| "PR #356 merged" | still OPEN | `gh pr view 356 --json state` |
| "monit already adopted by the rig" | NOT INSTALLED anywhere | `command -v monit` |
| "charon-bot account EXISTS" (implying ours) | it is a STRANGER's account | `gh api users/charon-bot` |
| "$30.86 spent today" | meter is fiction both ways | read `/data/spend.json` on 4-LOM |
| "fleet/state/* gitignored breaks CI" | negations already existed; files were never `git add`ed | `git check-ignore -v <path>` |
**RULE: a claim in a handoff is a HYPOTHESIS. Confirm from the system before you build on it.**

## F3. MEASUREMENT PATTERNS THAT LIE (I fell for all four)
```
pgrep -c -f 'review-pool.sh'        # WRONG: matches the string inside droid PROMPTS, and counts
                                    # parent+child as 2. Tab count != process count.
git merge-base --is-ancestor B M    # WRONG for this repo: we SQUASH-merge, so a merged branch is
                                    # NEVER an ancestor. Use PR state, not ancestry.
curl -s ... | head -c 60 && echo OK # WRONG: head exits 0 on EMPTY input, so this prints OK for a
                                    # dead endpoint. Check the body, not the exit code.
grep -c PARKED <file>               # Confirm the hit is in the FIELD you mean, not in prose.
```

## F4. 4-LOM IS DOCKER — NOT systemd, NOT a plain env file
I gave the operator a confidently wrong procedure (systemd unit, `/data/charon/gateway.env`).
Neither exists. Ground truth:
```
ssh -i ~/.ssh/4lom stack@10.0.1.60
docker ps                                   # container: charon-gateway-1
docker inspect charon-gateway-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
docker exec charon-gateway-1 ls -l /data    # config volume: charon_charon-config -> /data
```
**Provider secrets live in `/data/secrets.json` (mode 0600) INSIDE the container.** Back it up
before ANY write — it is the live credential store for every provider.

## F5. GRAPHQL IS THE BINDING CONSTRAINT — REST IS FREE
GraphQL hits 0/5000 AT THE RESET BOUNDARY (the fleet drains it instantly) while REST core sits
UNTOUCHED at 5000/5000. `gh pr list` is GraphQL; `gh api repos/.../pulls` is REST.
```
gh api rate_limit --jq '.resources.core, .resources.graphql'
```
When GraphQL is dry, `land-push` cannot verify CI and refuses. For a BOARD-ONLY change that is a
verification gap, not a red — `--force` is the logged escape. For CODE, wait.

## F6. EXACT COMMAND FORMS THAT COST ME RETRIES
```
bash fleet/land-push.sh <ref>:<ref> <repo> [--force]   # bare branch name is REFUSED; flag goes LAST
bash fleet/done.sh <id>                                # there is NO --pr flag
bash fleet/board-lock.sh commit --session <s> -m '<msg>' -- <paths>   # plain `git commit` is refused
bash fleet/work-lease.sh acquire <TICKET>              # do this INSTEAD of WORK_LEASE_BYPASS=1
( ... ) | crontab -                                    # the trailing '-' is MANDATORY; without it
                                                       # crontab REPLACED the table and silently
                                                       # killed the detector for 8 hours
```
Ticket frontmatter that passes the gate FIRST TRY (copy `fleet/board/RESCUE-PUSH-TOOL.md`):
`substrate:` (>=60 chars real reasoning, or `N/A` + `substrate-novel:`) · a
`## Dependencies & Sequence` section · block scalars for prose containing `: ` or a backtick ·
NO column-0 line before the first `##` · `work_class` from the CANONICAL set
(`bugfix ci-infra design-review docs frontend generalist greenfield-feature money-path refactor
rig-meta routing tests` — **`fix` is NOT valid**).

## F7. THE BOARD HAS TWO VIEWS AND THEY DISAGREE
`status.sh` says `ready`; `claim.sh` silently skips for FIVE more reasons (loop-guard quarantine,
`/PARKED/` prose match, tier rank, own/other pass, claimed/submitted/done sets). `--only` is
applied BEFORE them, so a hard pin is silently overridden.
```
ls fleet/state/loop-guard/          # quarantined = INVISIBLE to claim.sh
bash fleet/loop-guard.sh clear <id> # but FIX THE CAUSE or it re-quarantines in minutes
```
Ticketed as BOARD-VIEW-MISMATCH (#2) and ZERO-COMMIT-SPIN (#1).

## F8. CHECK THE SECOND LEG OF EVERY CADENCE
A registered cron job that never executes reads as clean. Both halves must be proven:
```
crontab -l | grep -c stranded-work-cron      # leg A: registered
cat fleet/state/.stranded-work.heartbeat     # leg B: EXECUTED (must be <20 min old)
tail -5 fleet/state/cron-rescue.log          # never redirect cron to /dev/null — I did, and the
                                             # failure was invisible for hours
```

---
# ⛔⛔⛔ START HERE — OPERATOR DIRECTIVE 2026-08-02 — TOOL UTILIZATION IS PRIORITY #1 ⛔⛔⛔

**This section SUPERSEDES the 2026-08-01 first-six below (which is now COMPLETE — see §DONE-0802).
Operator, verbatim: *"I want the TOOLS under utilized to be the NUMBER 1 PRIORITY before anything
else."* Queued by BLAST RADIUS. Do not start §A-§M until this section is moving.**

## WHY THIS IS #1 — measured on this box 2026-08-02, not read from docs

| measurement | value | source |
|---|---|---|
| tool surface actually switched on | **~20%** | `fleet/state/OWN-TOOLS-CAPABILITY-AUDIT.md` |
| tools audited / with unused capability | **52 / 37** | same |
| fleet checks INERT (wired NOWHERE) | **9** | same |
| **claimed-but-absent guarantee ALREADY CODED AGAINST** | **1** (Faktory exactly-once) | same |
| suites declaring red-proof but NOT in CI_SUITES | **101** (floor 88, and RISING — was 91 the same day) | `gate-integrity.sh scan` G5 |
| `graphify affected` (blast-radius query) call sites | **0** (vs 114 for `update`) | same audit |
| gate-integrity findings | **39** (3 new / 36 baseline) | live scan |

**The failure is not missing tools. It is default configuration accepted as a tool's full surface,
and checks that read as protection while being wired to nothing.**

## THE QUEUE — BLAST RADIUS ORDER (highest leverage first)

| # | ticket | why it is at this rank |
|---|---|---|
| **1** | `GRAPHIFY-AFFECTED-WIRE` | the blast-radius query ITSELF. 0 call sites. Until it is wired we cannot mechanically answer "what else does this change break" — every other prioritisation on this list is done by hand |
| **2** | `INERT-CHECKS-WIRE` (P0) | 9 inert checks + 2 documented wiring gaps (`land.sh:361-362`) + the Faktory guarantee code already depends on. An inert check is WORSE than no check: it reads as protection |
| **3** | `PROOF-SUITES-ENFORCE` (P0) | 101 suites assert "this guard has been seen to fail" and are NEVER EXECUTED. Until this lands, every red-proof claim in the rig is unverified — so every gate's green is worth less than it looks |
| **4** | `RUFF-PREVIEW-ON` -> `RUFF-ARG-C90-ON` | 12 defects (7 autofix) + 184 findings incl **3 HIGH-severity security**. Chained: both own `pyproject.toml` |
| **5** | `MYPY-STRICTNESS-3-FLAGS` | 176 real bugs. Explicitly SKIP `disallow_untyped_defs` (1952 = churn) |
| **6** | `SHELLCHECK-OPTIONAL-CHECKS-ON` | 15 error-level findings invisible today, AND fixes a fake-done: `SHELLCHECK-BLOCKING` is archived + done-marked while `gate.sh:127` still prints ADVISORY and never increments `$FAIL`. It owned 2 paths; NEITHER EXISTS |

**Rule for every one of these:** wiring is proven by making the check FAIL on a deliberate
violation. Registration is not proof. "Merged" is not proof. A gate must be SEEN to fail.


## F9. CONFIRM YOUR OWN HANDOFF BEFORE YOU HAND IT OVER

The golden rule is CONFIRM EVERYTHING, NEVER TRUST DOCUMENTATION — and it applies to the document
you are writing, not just the one you inherited. Last session wrote 688 lines of handoff and had
to be asked before verifying any of it. Two claims in THIS file were wrong on first draft:
  - "a ppid of 1 = detached" — WRONG. Real detached tabs show a bash/timeout parent from the WT
    spawn chain. Corrected in F1 above, but only because it was actually run.
  - "monit already adopted" — inherited, repeated, then disproved by one `command -v`.
**BEFORE HANDING OFF: run every command you wrote down, and mark each claim VERIFIED <date> or
delete it.** An unverified procedure in a handoff is not guidance, it is a trap with your name on
it. The next session will trust it exactly as much as you trusted the last one.

VERIFIED 2026-08-02 (each actually executed, not reasoned about):
```
bash fleet/checks/stranded-work.sh          rc=1   (findings present = correct, not failure)
bash fleet/checks/gate-integrity.sh scan    rc=0
bash fleet/rescue-push.sh                   rc=0
crontab -l | grep stranded-work-cron        1 entry; heartbeat fired 23:00:07 then 07:40:12
bash fleet/loop-guard.sh clear <id>         cleared 8; SPEND-METRIC re-quarantined in minutes
bash fleet/land-push.sh <ref>:<ref> <repo>  bare name REFUSED; --force must come LAST
bash fleet/done.sh <id>                     no --pr flag exists
bash fleet/board-lock.sh commit --session … plain `git commit` on the board is REFUSED
docker exec charon-gateway-1 ls -l /data    secrets.json 0600 present; NO systemd, NO gateway.env
gh api rate_limit                           graphql 0/5000 at reset; REST core 5000/5000
```


## F10. REVIEWER POOLS SPIN AND DRAIN THE API QUOTA — LAUNCH THEM WITH A STAND-DOWN

MEASURED 2026-08-02: a reviewer tab reached `cycle 461/0` in minutes while launched with
`--wait 5`. So `--wait` is IGNORED — that is the known review-pool.sh defect (`main_loop "$CMD"`
silently drops `--wait/--retries`), and `--retries 0` means NEVER stand down. Each cycle runs
`syncing review queue` = a `gh` GraphQL call.
**This was the GraphQL drain.** Killing the pools took graphql from **0/5000 to 3784/5000
immediately.** It is why land-push could not verify CI all session and why every board push
needed the logged `--force`.
RULES until PR #392's REST+ETag cutover lands:
  - launch reviewers with a FINITE retry budget, never `--retries 0`
  - keep the pool SMALL (1-2), and check `gh api rate_limit` before scaling
  - if `cycle N/0` climbs fast, the wait is being dropped — kill them, do not wait it out
```
pgrep -f 'bash .*review-pool\.sh' | xargs -r kill      # stop a spinning pool
gh api rate_limit --jq '.resources.graphql'             # confirm recovery
```

## F11. THE SESSION TASK LIST IS NOT DURABLE — IT DIES WITH THE SESSION
Last session tracked 24 items in the harness task list; 15 were still open at close and NONE of
them would have survived. Anything that matters must become a BOARD TICKET or a line in this
file. The harness list is a working set, not a record.
Converted at close 2026-08-02: SPILL-UP-CEILING-SSOT · LAND-PUSH-WORKTREE-STATE ·
SUBSTRATE-OWNS-WORD-BOUNDARY · LAUNCHER-LEAKGUARD-NONFATAL · BRIDGE-RESTORES-DISABLED-MODELS ·
MODELS-JSON-STRUCTURAL-LIMITS.

---

# ⛔⛔ UNTRACKED WORK PILEUP — MEASURED 2026-08-02 ⛔⛔

`bash fleet/checks/stranded-work.sh` (landed today, PR #361) reports **269 findings**. This is
work that was DONE and then silently stopped existing to the rest of the fleet:

| shape | count | ticket | pri |
|---|---|---|---|
| `pushed-no-pr` | **189** | `PUSHED-NO-PR-TRIAGE` | P1 |
| `closed-pr-unlanded` | **57** | `CLOSED-PR-UNLANDED-TRIAGE` | P1 |
| `dirty-worktree` | **17** | `DIRTY-WORKTREE-SWEEP` | P1 — **lowest-hanging, start here** |
| `unpushed-branch` | 8 | mostly `backup/*` (by design) | — |
| `pr-no-checks` | 1 | folded into the landing lanes | — |

**`closed-pr-unlanded` was tracked by NOTHING before today** — a PR closed while its branch still
carries unlanded commits is either a deliberate bounce, a squash artefact, or silently discarded
work, and they are indistinguishable without looking. Treat unclassifiable as discarded.

**Do NOT open 189 PRs.** That converts an invisible backlog into an unreviewable one. Batch by
owning ticket — e.g. the FIVE `fix/provider-key-exfil-*` branches are ONE fix.

## RUN THIS FIRST, EVERY SESSION
```
bash fleet/checks/stranded-work.sh          # all five loss shapes
bash fleet/checks/gate-integrity.sh scan    # inert / falsely-claimed / unproven gates
bash fleet/rescue-push.sh                   # at-risk branches (dry run)
```

---
# ⛔⛔ START HERE — THE VERY FIRST THINGS THE NEXT SESSION DOES ⛔⛔

**Operator directive, 2026-08-01 session close. Do these BEFORE anything else in this file.
Launch them in TABS. They are one causal chain: the work-loss class recurs every session because
its fixes keep being lost to the class itself.**

| # | item | state at close | why first |
|---|---|---|---|
| **0** | **RESCUE: push the 47 local-only branches** | 96 commits exist ONLY on this box | non-destructive, reversible, one call each. Do this BEFORE building anything — the last two sessions built the fix and lost it |
| **1** | `feat/stranded-work-detect-v2` | 1 unique commit, **NO remote** | the stranded-work detector is itself stranded |
| **2** | `feat/session-end-push-gate-v2` | 3 unique commits, **NO remote** | the push gate was built and never pushed; roadmap still says `not-started` |
| **3** | `HANDOFF-NAME-ALLOCATOR` | **archived + DONE, still broken** | verify the FIRING LAYER — a fix marked complete that never fixed it |
| **4** | `SESSION-END-GATE-REPAIR` | **LIVE, UNCLAIMED** | ticketed, never scheduled; `end-session.sh` aborts before its work-loss check EVERY run |
| **5** | **Adopt a tool to run the gate CONTINUOUSLY in the background** | nothing exists | a close-gate never fires when a session dies on a token limit, crashes, or is killed — which is most of them. **LAUNCH THIS IN A TAB FIRST, IN PARALLEL WITH 0** — it is research and does not block |
| **6** | **GATE DEFECT blocking a real push** | `fix/shared-namespace-contention` cannot be pushed | `land-push` refuses it as *"code owned by NO live board ticket"* — but the ticket IS on origin/master (`f8266ef`) and owns exactly those 4 files. **A gate that blocks legitimate work is how `--force` habits start.** Same stale-base class as RIG-CI-BASE-DEFAULT-BRANCH (fixed today for a different scope) |

| **7** | **`KILL-PATH-WORK-GUARD` (P0, minted)** | 3 kill paths, ZERO work checks | `stop-worker.sh` has 0 refs to `git status`/`diff`/`commit`. A killed droid left **+222 lines** uncommitted at this close; `OPERATOR-ACTIONS.md` held 7 escalations uncommitted. **Every kill path must check + commit BEFORE signalling.** |
| **8** | **SWEEPS MUST BE MECHANIZED** | hand-composed queries missed a whole loss class | `validate_board.sh` ALREADY reports `uncommitted-work` and found the 222-line file unprompted — it just was not run AS the sweep. Meanwhile a hand-written "ahead of upstream" query missed **47 branches / 96 commits**. Make the sweep a TOOL that is RUN, never a query typed in the moment |

### Ordering rationale — why RESCUE is 0 and the gate is not

Asked directly at close: *"should #5 be the FIRST action?"* **No — but launch it in parallel.**

- **0 is the only IRREVERSIBLE item.** 96 commits exist on one disk. A failure or a stray
  `reset --hard` loses them permanently. The gate protects FUTURE work; it does nothing for the 96
  already at risk.
- **Cost asymmetry:** rescue is ~47 pushes, minutes. The gate is an adopt-trial plus wiring, hours.
  Doing the cheap irreversible thing first is strictly correct.
- **This exact ordering is what the last two sessions got wrong** — they built the fix first, then
  lost it to the class (§L). Rescue-then-build breaks that loop; build-then-rescue repeats it.
- **BUT item 5 is INVESTIGATION, so it is not sequential.** Launch it in a tab immediately,
  concurrently with the rescue. Nothing about it blocks, and by the time rescue and items 1-4 are
  done the adopt-verdict should be ready to wire.

Net: **0 and 5 start together; 5 finishes last.**

### Item 5 — the requirement, stated properly
A session-close gate is structurally insufficient: **the sessions that lose work are the ones that
never reach their close.** This session came within a token limit of exactly that. So the check must
run on a CADENCE, independent of any session's lifecycle.

Investigate ADOPT-FIRST (per §0 doctrine — do NOT hand-roll a daemon first):
- ~~the rig already runs **monit**~~ **FALSE — CORRECTED 2026-08-02**: `command -v monit` fails here AND on 4-LOM, no `/etc/monit*`, and its SSOT `fleet/state/service-registry.tsv` did not exist. monit was a PAPER adoption. cron was adopted instead and is now live
- systemd user timers / cron
- a git hook (`post-commit` / `pre-push`) for the commit-time half
- `fleet/watchdog/discover-services.sh` + `generate-monit-config.sh` already exist and may take it

It must cover **ALL** loss classes (the narrow "ahead of upstream" check is exactly what missed 96
commits): branches ahead of remote · **branches with NO upstream at all** · dirty worktrees ·
stashes · detached HEADs. And it must FAIL LOUD — see §J, where the existing gate is marked done and
silently never fires.

### Also at the head of the queue
- **`fix/shared-namespace-contention` — REVIEWED, PUSH BLOCKED.** 25 commits ahead of its remote;
  24 are master merges, the real work is tip `6e8247b` (split claim from check, idempotent re-claim,
  orphan reap, namespaced scratch) + `fleet/tests/scratch-namespace.test.sh`. 88 files, +2209.
  `land-push` REFUSES with *"touches CODE owned by NO live board ticket"* for
  `fleet/claim-jedi-name.sh`, `fleet/spawn-worker.sh` and both tests — **but
  `fleet/board/SHARED-NAMESPACE-CONTENTION.md` IS on origin/master (f8266ef) and owns exactly those
  four files.** So this is a GATE DEFECT, not a real ownership gap — almost certainly the branch's
  own stale copy of the board being read, the same stale-base class as RIG-CI-BASE-DEFAULT-BRANCH.
  Diagnose the gate; do NOT `--force` past it.

---

# PRIORITY TODO — OUTSTANDING WORK (authored 2026-08-01, session saba-sebatyne)

> **THIS FILE IS THE CARRY-FORWARD LIST.** It exists because the recurring failure is not bad work
> — it is good work that gets FORGOTTEN between sessions. Operator directive 2026-08-01:
> *"I want ALL these findings made DURABLE so the next sessions can NOT miss it."*
>
> **RULES FOR THE NEXT SESSION:**
> 1. Read this file at start. It is referenced from SESSION-HANDOFF-saba-sebatyne.md.
> 2. Do NOT delete an item. Mark it `[DONE <sha/PR>]` or `[DROPPED — reason]`. An item that just
>    vanishes is the failure this file prevents.
> 3. Items 1-5 are ALREADY APPROVED by the operator. They do not need re-litigating — they need
>    doing, and each must be DOGFOODED, not merely switched on.

---

## A. TOP 5 TOOL ENABLEMENTS — APPROVED, NOT STARTED

Source of truth + measurements: `fleet/state/TOOL-UTILIZATION-AUDIT.md`.
Only ~20% of installed tool capability is switched on. Operator: *"we tend to turn on a small
selection and then the other stuff gets forgotten or rots"* — so do ALL FIVE, and gate each.

| # | action | measured payoff | status |
|---|---|---|---|
| A1 | `preview = true` in `[tool.ruff.lint]` | **12 defects** inside families we ALREADY select, 7 auto-fixable | TODO |
| A2 | `extend-select = ["S","BLE","ARG","C90"]` | **184** findings, **3 HIGH-severity security** | TODO |
| A3 | mypy `check_untyped_defs` + `warn_unreachable` + `warn_return_any` | **176 real bugs**. SKIP `disallow_untyped_defs` (1952 = churn) | TODO |
| A4 | `shellcheck -o all` on the rig | **15 error-level** findings invisible today | TODO |
| A5 | `graphify affected` (blast-radius) | graph built by 114 `update` sites, query has **0** invocations | TODO |

Each needs: enable → burn down or explicitly baseline → **fail-on-revert test** → wire into a gate
so it cannot rot back off. A2 relates to ticket `RUFF-SEC-RULES-ON` (already minted).

---

## B. MONEY PATH — P0, and the picture CHANGED today

- **B1. `CATALOG-REFRESH-PERSIST`** — CLAIMED + RUNNING in a tab as of session end. Bar was raised
  to fully-wired + dogfooded (persist to disk, cadence observable, propagate to EVERY consumer,
  fail-loud, gate). **Verify it actually landed; do not trust the claim marker.**
- **B2. `SPEND-METRIC-TRUSTWORTHY`** — RE-SCOPE APPROVED but NOT YET APPLIED to the ticket.
  **Finding:** opencode already has per-session cost + token accounting via
  `GET http://127.0.0.1:<port>/api/session`. Measured 2026-08-01: **$1.3372 real spend across 50
  sessions** while the gateway reported `usage.cost_usd = $0.000226`. The gateway meter is fiction
  in BOTH directions (a prior session saw it inflate to a fictional ~$223 via a fabricated
  `est_cost` floor). **Re-scope from "fix the gateway counter" to "ingest the number that already
  exists".** A worker on this was running at session end.
- **B3. PR #207 `FORWARDER-COST-ORDER-FALLBACK` — BOUNCED** (comment posted). It is a strict no-op:
  the live catalog has **10 of 861 models priced**, so the sort key is degenerate; the chain is
  already sorted with the identical key at startup; and `proxy_server.py:674` full-sorts by EWMA
  latency immediately after, discarding cost order (reproduced: openrouter 6x costlier tried
  first). Also ships a FALSE claim that an unpriced leg "sorts last" — the 1000 sentinel equals a
  blended $10/M model, so priced legs above it get demoted BELOW unpriced ones.
  **Consequence: `PRICE-REFRESHER` is the money-path critical path, NOT the ordering ticket.**
  Cost ordering over an unpriced catalog cannot work no matter how correct the sort.
- **B4.** `minimax-m3-free` billed **$0.1542** and **$0.1009** despite `-free` in its name — likely
  a withdrawn free tier, i.e. catalog rot, not a billing bug. Covered by B1.

---

## C. THE 13 "TICKETED BUT STILL INERT" + 10 NEVER-TICKETED

Operator made these HIGH PRIORITY, to be pushed through like the PR backlog.
Full dispatch queue with per-item blockers: see the triage in the session handoff.

**Launched and running at session end:** `LITELLM-CAPABILITY-ADOPTION` (covers 3 items by
disposition), `BASH-INERT-COVERAGE`, `DEADCODE-TOOLS-WIRE`, `PRICE-REFRESHER`.

**BIGGEST UNLOCK — 4 stranded `state/submitted/` markers block 4 of the 13.** One
(`PRICE-REFRESHER`) was pure orphan and has been cleared. These four have LIVE remote branches =
real stranded PRs. Land or close them:
`PRICING-LIMITS-CHECK-SH` (@d4ac0ef) · `REACHABILITY-GATE` (@ea7e1c5) ·
`INERT-WIRING-ENFORCEMENT-DURABLE` (@bbb8421) · `CI-SUITES-CANARY`.

**Three need REOPEN, not a claim** — tickets minted 2026-08-01:
- `GW-CUTOVER-REOPEN` — the **whole litellm plane is merged, marked done, and has ZERO production
  importers**. `GW-CUTOVER-LIVE-WIRE` is in `state/done/` as merged #181; `grep -rn litellm_plane
  src/` finds only a tools/ script and tests. Largest single instance of the built-but-inert class.
- `RUFF-SEC-RULES-ON` — both BANDIT tickets closed green while `pyproject.toml:52` never gained
  `S`/`BLE`. (See also A2 — same work.)
- `GATE-INTEGRITY-C` — **NOT a bug**: `preflight.sh:802-806` documents `scan … || true` as a
  deliberate advisory ramp "until it has ridden a few PRs". It has. Live run: 37 findings, 1 new /
  36 baseline. A scheduled promotion coming due.

**Other confirmed-inert, unfixed:** `reachability-gate` is registered in `tools/gates.json:224-228`
with an enforcer file that **does not exist** — the registry emits a GREEN RECEIPT for an absent
gate. 16 `|| return 0` fail-open guards in preflight.sh. `ActualsLedger`, `pricing_limits_checker.py`
(528 lines), `stale-check.sh`, `reuse-check.sh` — all zero callers.

**Orphaned test suites — worse than first reported:** **91 suites declare themselves red-proofs but
are absent from `CI_SUITES`**, against a ratchet floor of 88, **and the count is RISING**.
Approved approach: **D+B** — (D) gate the INFLOW first so new unregistered suites are blocked, then
(B) ratchet the existing 91 down in batches, folding triage into each batch. `BASH-INERT-COVERAGE`
was running and may overlap; let it land first.

---

## D. WIRING / ENFORCEMENT

- **D1. `WIRING-DONE-CONTRACT`** — APPROVED, ticket NOT yet minted. Make wiring a mechanized
  DONE-CONTRACT rather than a mechanized action: a ticket cannot reach DONE unless its code is
  proven reachable from a real entrypoint (graphify call graph + inert-check + plane-canary,
  fail-closed). Deliberately NOT an auto-wirer — code generation into a money path that can be
  silently wrong is a worse version of the problem.
- **D2. `import-linter` adopt-test** — APPROVED, not started. Test it against REAL cases from the
  13 inert items, not fixtures.
- **D3. KS29 / KS30** — remain `designed` on the roadmap. Decide from what D1 catches in its first
  week rather than as a design bet.
- **D4-CORRECTION (2026-08-02):** D4's diagnosis is right AND it carries a FIX that was quoted only
  half the time — "use `exclude` + a whitelist ratchet generated only AFTER known inertness is
  fixed". That ratchet IS the answer to the confidence-80 blind spot, and it is **already built**:
  `DEADCODE-TOOLS-WIRE` is live with **open draft PR #209**. Land it; do not re-derive it.
- **SEC.C CORRECTION (2026-08-02):** the claim "16 `|| return 0` fail-open guards in preflight.sh"
  is **FALSE**. Measured: `|| return 0` = **1**; `|| true` = **38**, and those 38 are cleanup and
  the deliberate "never block session boot" idiom. A first review of preflight repeated the error
  worse ("39 fail-open guards") by conflating the two constructs. **There is exactly ONE
  leg-level fail-open.** Do not launch an audit against a miscount.
- **D4.** Dead-code tools do NOT answer the wiring question. Measured: vulture flags `litellm_plane`
  with 7 hits at confidence 60 but **0 at confidence 80** (the recommended tuning would blind us to
  the one case that mattered); neither vulture nor deadcode ever says "this module has no
  importers". Confidence measures PROVABILITY, not IMPORTANCE. Do not tune confidence up; use
  `exclude` + a whitelist ratchet **generated only AFTER known inertness is fixed**, or it freezes
  the bugs in permanently.

---

## E. PIPELINE / RIG DEFECTS (from the 10-defect chain)

- **E1.** `AUTO-DONE-ON-MERGE-MISS` — FIXED, committed `9b69739`, **NOT pushed** (branch
  `fix/auto-done-on-merge-miss`, 83 commits behind master, needs update-branch).
  Root cause was NOT what #339 assumed: `reconcile-merged.sh` was **repo-blind** — `REPO_SLUG` came
  from the product checkout only, so all **196 `repo: charon-private` tickets** were structurally
  unreachable. #339's own file `reconcile-board-pr.sh` was a REINVENTION that never fired.
  **PR #339 should be CLOSED, not merged.** 19/19 tests, 11 FAIL on revert.
- **E2.** PR #346 `REVIEWER-TAB-POOL` — **BOUNCED** (comment posted). It would make the pool review
  NOTHING: switches B1 to a `CHARON-AUTHOR-DROID` PR-body marker that **0 of 16 PRs carry and no
  code writes**, with fail-closed skip. All five known review-pool defects untouched, one worsened.
- **E3.** PR #342 — **BOUNCED** (comment posted). The drift-correction PR reintroduces drift on rows
  stamped `aligned`.
- **E4.** `review-pool.sh` five defects, ALL still open: done-marker on INFRA failure (permanently
  retires PRs — 16 hit this today, quarantined to `fleet/state/review-quarantine-saba/`) ·
  stale model chain · `--wait/--retries` never parsed · `queue_gen` not idempotent/unlocked ·
  GraphQL burn. `PR-QUEUE-REST-ETAG` is BUILT (40/40 tests, 8-way red-proof, zero-quota steady
  state) and the CUTOVER into `review-pool.sh` is now IN SCOPE and approved — **not yet done**.
- **E5.** `work-lease.sh` never searches the worktree's own board despite its doc saying it does.
- **E6.** `retire-done.sh` archives working-tree-only; retirement is one `git reset` from vanishing.
- **E7.** `end-session.sh` is built-but-inert on master (R-G). Outside any ticket's owns.

---

## F. OPERATOR ACTIONS (need the human)

- **F1.** `charon-bot` PAT — APPROVED. The account EXISTS but all 16 open PRs show
  `user.login = Nnyan`, so GitHub refuses `request-changes` on our own PRs and B1 cannot key on
  `user.login` (it is a constant matching no droid id). Needs a PAT + collaborator access on both
  repos.
- **F2. DURABILITY GAP:** `MANAGER-OPERATING-RULES.md` (which now carries §14) is loaded at
  SessionStart from **`/home/stack/code/charon/.claude/settings.local.json`** — a machine-local,
  typically untracked file. The doctrine is durable in git; the LOADING of it is not. A fresh clone
  or another box will not load it. `fleet/hooks/session-start.sh` has ZERO references to it.
  **Harden into the tracked hook.**
- **F3.** Ledger corrections require the `bench-grader` user (read-only to manager sessions BY
  DESIGN). Template: `fleet/state/scorecard-correct-saba-20260801.sh`.

---

## G. DECIDED THIS SESSION — DO NOT RE-LITIGATE

- **Session comms:** opencode's HTTP control plane is ADOPTED (2026-07-26, verified post-doctrine).
  MCP was rejected as a control plane on a proven capability gap. **The bespoke session-bridge
  (3,073 LOC) was slated for retirement on 2026-07-26 and is STILL dual-running** — ~10 sidecars,
  3 daemons (one stale since Jul 26), an SSH tunnel, MCP entries in both client configs, and 12 rig
  scripts still reading the bridge DB proven to show 2 of 8 workers. **Finish the retirement.**
  All 4 comms verdicts are now registered in EVAL-REGISTRY.
- **TUI workers:** use `POST /api/session` to reset context per ticket — no respawn needed, keeps
  bridge visibility. Headless droids already get a fresh session per ticket (`opencode run` is
  one-shot); only TUI workers accumulate.
- **Model grading:** prelim leaderboard seed → superseded by REAL-WORK grades → promotion/demotion.
  ONE design, not two. Grading IS live (7 of 8 models graded); the audit claiming otherwise is
  stale. Grades must key on **model × provider** — speed is mostly a provider property, quality is
  model × provider (quantization, hardware, hidden prompts). Ticket `GRADE-MODEL-PROVIDER-PAIR`
  was claimed and running. `BROKER-BARE-TIER-LEGS` is HELD UNMERGED pending it.
- **Catalog is LIVE DATA** — see MANAGER-OPERATING-RULES.md §14. Model names rot, free status rots,
  and EVERY static list must be API-refreshed at EVERY consumer.

---

## H. HOUSEKEEPING

- `MEMORY.md` index is at 173 lines, over the 140 target — compaction deferred.
- 3 stale claims held by dead droids (this session's own manager-built work):
  `BROKER-BARE-TIER-LEGS`, `LAUNCHER-GATE-SETE-KILL`, `PR-QUEUE-REST-ETAG`. The reaper correctly
  HOLDS rather than releasing them (committed but not merge-proven). Retire once merged.
- `rig-ci` is RED on every open PR. Root cause identified: **`fleet/state/*` is gitignored, so
  files the gates depend on (`tier-drift-red.txt`, `service-registry.tsv`) never reach the CI
  checkout.** Not yet fixed — this is why the merge gate has effectively been off.
- 5 pre-existing tickets had unparseable YAML frontmatter (fixed). `BOARD-FRONTMATTER-GATE` is
  built (61 assertions, 4-way red-proof) to catch it at WRITE time; **committed, not pushed**.

---

## I. STARTUP FRICTION — what cost time THIS session, so it does not cost the next one

Operator directive 2026-08-01: *"use all your session start-up issues as a guide to make sure the
friction you had is not carried forward."* Each item below is real, measured, and fixable.

**I1. The handoff was unreadable in one pass.** `SESSION-HANDOFF-tenel-ka.md` was **1,286 lines /
~58,000 tokens** against a 25,000-token read cap. It had to be paged and grepped, and the
machine-generated state (worktree lists, PR dumps, roadmap) dwarfed the human-authored part.
→ **FIX:** keep the hand-written brief SHORT and put generated state behind a pointer. The
next session should read `fleet/state/PRIORITY-TODO.md` (this file) FIRST — it is the carry-forward
list — and treat the handoff as provenance, not as the task list.

**I2. Ticket→code chicken-and-egg cost ~6 round trips per ticket.** The substrate gate rejects in
sequence, one reason per push: missing `substrate:` → missing D&S → unparseable YAML → tool has no
EVAL-REGISTRY row → row is `drifted` and needs `substrate-retest:` → registry row may not land in
the SAME push as the ticket citing it ("not self-service") → `substrate:` tool name must not appear
in the ticket's own `owns:`. Each cost a full validate+push cycle.
→ **FIX:** author tickets with ALL of these present from the start:
`substrate:` (≥60 chars of real reasoning, or `N/A` + `substrate-novel:`), a
`## Dependencies & Sequence` section, block scalars (`key: |`) for ANY prose containing `: ` or a
backtick, and land any new EVAL-REGISTRY row in a SEPARATE, EARLIER push.

**I3. `work-lease` refuses a worktree whose branch maps to no board ticket** — so the ticket must
land on master BEFORE the code can be committed. Not a bug, but it must be sequenced deliberately:
mint + push the ticket first, then create the worktree.

**I4. `board-lock` pins a base sha.** Any plain-`git` commit on master (e.g. a doctrine edit) moves
HEAD under the lock and the next board commit refuses with `BASE MOVED UNDER THE BOARD LOCK`.
→ **FIX:** `board-lock.sh release <session> && board-lock.sh acquire <session>`. Also note
non-board commits on master need `board-hygiene` or `land:` in the message or work-lease refuses.

**I5. GitHub GraphQL quota was exhausted (5,000/hr) in under an hour** by 7 reviewer tabs, which
also blocked `gh pr review` and `land-push`'s CI verification. REST core sat untouched at 5000/5000.
→ **FIX:** `fleet/pr-queue.sh` (REST + ETag, zero-quota steady state) is BUILT and pushed; the
cutover into `review-pool.sh` is approved and pending. Until then keep reviewer tabs at
`REVIEW_POOL_WAIT=300` and no more than 1-2.

**I6. `rig-ci` is RED on EVERY open PR**, so the merge gate is effectively off and every merge is a
judgement call. Root cause found: **`fleet/state/*` is gitignored**, so files the gates require
(`tier-drift-red.txt`, `service-registry.tsv`) never reach the CI checkout. NOT yet fixed.

**I7. Name-pool burn.** Every `handoff.sh` / `handoff-check.sh` invocation allocates a Jedi name and
leaves a stub, burning names without a real session (operator action #19). Pool is ~69.

**I8. `end-session.sh` is self-blocking** (operator action #20): it creates its own target file,
then its allocator refuses the name as in-use, so it aborts BEFORE the work-loss check every run.
`SESSION-END-GATE-REPAIR` was claimed by a tab this session — verify whether it landed.

**I9. A sub-agent reported a file path it never wrote.** The tool-utilization audit was reported at
a scratchpad path that did not exist; the content survived only because it was in the manager's
context. → **FIX:** ALWAYS verify a sub's claimed deliverable exists and is non-empty before
relying on it, and prefer writing durable artifacts into `fleet/state/` (with a `.gitignore`
negation) rather than `/tmp`.

**I10. `/tmp` scratchpad does not survive.** Anything a session needs to carry forward must be in
the repo with a `!fleet/state/<file>` negation in `.gitignore` — `fleet/state/*` is blanket-ignored.

---

## J. SESSION-END SELF-BLOCKING — HIT AGAIN 2026-08-01, ESCALATE

**Operator, at session close: *"we keep hitting this stub file exists / self-blocking defect every
session end — is it scheduled to be FIXED?"* Answer: ticketed, NOT scheduled, and one prior fix is
already marked DONE while the defect persists.**

Measured at THIS session's close:

| ticket | state | reality |
|---|---|---|
| `SESSION-END-GATE-REPAIR` | **LIVE, UNCLAIMED** | ticketed, never scheduled |
| `SESSION-CLOSE-COMPLETENESS-GATE` | LIVE, unclaimed | blocked on the above |
| `HANDOFF-NAME-ALLOCATOR` | **archived + DONE** | **and the allocator STILL BLOCKS** — another merged-but-inert instance |

**The defect, reproduced live:** `handoff.sh` with `SESSION=saba-sebatyne` refused —
*"that name is already in use (live file present)"* — because the session's own 29-byte claim-marker
stub `fleet/SESSION-HANDOFF-<name>.md` is in `claim-jedi-name.sh`'s exclusion set. `end-session.sh`
hits the identical shape: it CREATES its target file, then calls `handoff.sh`, whose allocator sees
that 0-byte file and refuses. **The one gate meant to prevent work loss at session close aborts
before it runs its work-loss check, every single time.**

**J1. Fix the allocator to EXEMPT the caller's own target file** (or have `end-session.sh` write to
a temp path and `mv` into place). Both `end-session.sh` and `handoff.sh` are affected — fix the
allocator, not one call site, or the other keeps failing.

**J2. Verify `HANDOFF-NAME-ALLOCATOR`'s "DONE" claim.** It is archived with a done marker and the
symptom is still live. Either it fixed a different sub-case or it never fired — check the FIRING
LAYER, not the ticket state. This is the class the whole session was about.

**J3. Until J1 lands, session close MUST do the work-loss check by hand.** This session did:
```
git worktree list --porcelain | awk '/^worktree /{print $2}' | while read w; do ... done
```
**It found real stranded work** (see K), which is exactly what the broken gate would have missed.

**J4. Name-pool burn (operator action #19) is the same root.** Every `handoff.sh` /
`handoff-check.sh` invocation allocates a name and leaves a stub, burning names without a real
session. Same allocator, same exclusion-set behaviour.

---

## K. STRANDED WORK FOUND AT SESSION CLOSE — verify before assuming lost or safe

- **`fix/shared-namespace-contention` is 25 COMMITS AHEAD of its remote** (remote branch exists;
  PR #345 is open). This is the largest single body of unpushed work on the box. **Verify what those
  25 commits contain and land or explicitly drop them.** Do not assume PR #345 represents them.
- `fix/auto-done-on-merge-miss` — 1 commit ahead, unpushed (see E1).
- Rig master had 36 dirty files at close — mostly untracked board/archive churn and this session's
  in-flight worktrees; not lost, but not clean either.
- ~16 rig worktrees carry 1-4 dirty files each; several belong to tabs that were still running.
  **Re-run the work-loss check at the START of the next session** — tabs kept working after this
  handoff was written, so this list is a floor, not a ceiling.

---

## L. ⛔ ROOT/CLASS: 96 UNPUSHED COMMITS ON 47 LOCAL-ONLY BRANCHES — AND THE FIX IS ITSELF STRANDED

**Operator, 2026-08-01: *"we hit this most end of session (look at the last 3) but we never fix it
in a mechanical way to stop the ROOT/CLASS and not do whack-a-mole."* Measured at this close:**

```
charon-private:  25 local-only branches carrying 38 unpushed commits
charon:          22 local-only branches carrying 58 unpushed commits
TOTAL:           47 branches / 96 commits that exist ONLY on this box
```
(Excludes `backup/*`. "Local-only" = NO upstream ref at all — never pushed, not merely behind.)

**WHY IT RECURS — the fixes for this class were BUILT and then LOST TO THIS CLASS:**

| branch | unique commits | remote |
|---|---|---|
| `feat/stranded-work-detect-v2` | 1 | **NONE** |
| `feat/session-end-push-gate-v2` | 3 | **NONE** |

The stranded-work detector is stranded. The session-end push gate was built and never pushed.
`SESSION-END-PUSH-GATE` still reads `not-started` on the roadmap. Each session rediscovers the
problem, builds a fix, and loses the fix the same way — that IS the whack-a-mole.

Single largest at-risk item: **`feat/cwd-config` — 26 unique commits, never pushed.**

### L1. THE MECHANICAL FIX — do this INSTEAD of another manual sweep

A session-close gate is necessary but NOT sufficient, because a gate that is itself an unpushed
local branch does nothing. Required, in this order:

1. **RESCUE FIRST, before building anything.** Push all 47 local-only branches to remote (they cost
   nothing parked there and are then recoverable from any box), or explicitly delete the ones that
   are genuinely dead. Do NOT build the gate first — the last two sessions did and the gate was lost.
2. **Land `feat/session-end-push-gate-v2` and `feat/stranded-work-detect-v2` IMMEDIATELY.** They
   already exist. Landing them is cheaper than rebuilding them a fourth time.
3. **The gate must cover ALL loss classes, not just "ahead of upstream"** — that narrow check is why
   this was missed repeatedly. The full set, all measured at this close:
   - branches AHEAD of their remote (found: `fix/shared-namespace-contention` **25 commits**)
   - branches with **NO upstream at all** (found: 47 / 96 commits — the class that kept being missed)
   - uncommitted dirty worktrees (~16 rig worktrees, 1-4 files each)
   - stashes (1 in the rig)
   - detached-HEAD worktrees (2 in the rig)
4. **Run it on a CADENCE, not only at close.** A session that ends abruptly, hits a token limit, or
   crashes never reaches its close gate. A timer/preflight leg catches what a close gate cannot.
5. **FAIL LOUD and BLOCK.** `end-session.sh` currently aborts before its work-loss check every run
   (see §J) — so today the gate exists, is marked done, and never fires. Verify the FIRING LAYER.

### L2. Why "just push everything" is the right first move
These branches are already on disk. Pushing is non-destructive and reversible, costs one API call
each, and converts an invisible single-point-of-failure into recoverable remote state. Triage can
happen later at leisure. Losing 96 commits to a disk failure or a stray `reset --hard` cannot be
undone at all. **Rescue is cheap; reconstruction is not.**

---

## M. RESCUED WIP + 4-LOM DEPLOY DRIFT (found during session close-out)

**M1. `CATALOG-REFRESH-PERSIST` WIP was rescued from a killed droid.**
`src/charon/routing_policy/catalog_refresh.py` in the PRODUCT MAIN CHECKOUT carried
**+222/-40 uncommitted lines** when its tab was killed at close. Saved as a tracked patch:
`fleet/state/RESCUE-catalog-refresh-persist-WIP.patch` (17,518 bytes).
**Next session: apply it onto branch `fix/catalog-refresh-persist`, review it against the raised
bar in the ticket (persist to disk, cadence observable, propagate to EVERY consumer, fail-loud,
gate), then land.** Do NOT assume it is complete — the droid was interrupted mid-work.
Note it was left on the MAIN CHECKOUT rather than a worktree, which is itself worth checking.

**M2. 4-LOM gateway is running an OLD build.**
Live `/charon/status` reports `build_sha 9659998` = *"land: release v0.6.1"*. Master has moved far
past that. So the deployed gateway does NOT contain this session's landed fixes, and any reasoning
about live behaviour must account for the deployed build, not master.
Live state at close: **4,365 pools, 12 providers**, health endpoint 401 without a bearer token
(expected — an unauthenticated `/charon/status` answers 302 with a ZERO-BYTE body, which curl
reports as success; always test that the body PARSES).
**Next session: decide whether to redeploy.** Relevant known trap: config/state live on the `/data`
volume and the RUNNING process REWRITES `spend.json` — a disk edit is inert until restart and can
be clobbered by the live process.
