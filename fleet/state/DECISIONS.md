# DECISIONS — the operator decision ledger

**THIS FILE IS THE ONLY PLACE OPERATOR DECISIONS LIVE.** If a decision is not here, it is not a
decision. If another file contradicts this one, THIS FILE WINS and the other file is wrong and must
be corrected.

**Read this BEFORE `PRIORITY-TODO.md`, before any handoff, before any board query.** It is small on
purpose. It must stay small — that is the feature. `PRIORITY-TODO.md` grew to 891 lines,
`MANAGER-OPERATING-RULES.md` to 42KB, `MEMORY.md` to ~100 entries, and decisions got LOST INSIDE
THEM. Adding volume is how the real items get missed. Do not grow this file with facts,
measurements, analysis, or doctrine — only decisions, open questions, and commitments.

## Why this file exists (measured, 2026-08-03)

Six durable mechanisms already existed and all six failed to make a decision stick:

| decision / commitment | outcome | mechanism that was supposed to hold it |
|---|---|---|
| product-thesis question escalated 2026-07-11 | unanswered **~3 weeks** | `EVAL-REGISTRY.md` OPEN row |
| Letta + memory-layer reviews commissioned+completed | **never read**, 3 sessions | operator action #15 |
| 4 GATE-3 tickets approved 2026-07-31 | never staged | operator action #17 |
| tool-enablement Top-5 approved 2026-08-01 | "NOT YET DONE" | `TOOL-UTILIZATION-AUDIT.md` |
| "leave openrouter parked" (prior session) | **no durable record existed at all** | — |
| ~6 session commitments | dropped; operator had to catch them | harness task list (used zero times) |

**A mechanism that exists and does not prevent the failure is not a solution — it is a wish.**
Sessions have repeatedly told the operator "we already have memory, we don't need this." That answer
was WRONG, and the table above is the disproof. Do not repeat it.

Two independent commissioned reviews reached the same root cause (`fleet/handoff-notes/LETTA-REVIEW.md`,
`MEMORY-LAYER-REVIEW.md`), after actually RUNNING 9 memory products between them:

> **"Neither tool fixes the ROOT CAUSE: nothing in the system BLOCKS on an unfinished commitment.
> Both improve detection but don't enforce."**

⇒ The fix is not a better memory store. It is **lifecycle enforcement**: an unanswered question
BLOCKS its dependent work, and an active decision cannot be contradicted by a merge.

---

## STATES

- **`DECIDED`** — an operator ruling. Active until a newer `DECIDED` explicitly names and supersedes
  it. **No session may act contrary to an active `DECIDED`, and no session may re-litigate one.**
- **`ASKED`** — an open question for the operator. MUST name what it BLOCKS. Dependent work does not
  proceed while it is open, so the question cannot be silently skipped.
- **`SUPERSEDED`** — kept for provenance, moved to the bottom, excluded from the loaded view.

---

## DECIDED — active

### D-001 · THE FACTORY IS THE PRODUCT, NOT THE GATEWAY · 2026-08-03
**Operator, verbatim:** *"the factory is the product, not the gateway."*

This answers the question `EVAL-REGISTRY.md` escalated on 2026-07-11 and that went unanswered for
three weeks (*"a product-thesis decision for the operator, not a tool-adoption research task…
escalate for a decision instead"*).

**What SG is for:** a tool the operator — **who does not write code** — can use to design, code, and
deploy projects and ideas; as automated as possible; fast, by slicing work across parallel
droid/model tabs; where quality is provable without the operator reading code; and where **nothing is
ever left incomplete.** The gateway exists only to make the factory cheap to run. It is not the
product.

**Immediate consequences (act on these, do not re-derive them):**
1. **`LiteLLM` full-gateway `REJECTED — KEEP-CUSTOM` is VOID.** It was `aligned` only against the
   now-inverted thesis *"the gateway core IS the differentiator"*, and it was explicitly
   **conditional on differentiation shipping** — which measurably did NOT ship (2026-08-03: 851 of
   861 models unpriced ⇒ cost-first ordering inoperative; park is a one-way door for 5 of 7
   providers; `tiers.json` absent from the gateway entirely).
2. The gateway becomes **thin config over an adopted routing substrate.** `litellm-proxy` is already
   installed on this box and entirely unused.
3. Of ~30k product `src/` lines, the only clearly-surviving PRODUCT slice is the **~2,100-line
   outcome-graded routing** (`capability/taxonomy`, `grades_import`, `recommend`, `lifecycle`) —
   grading models on REAL work outcomes and routing by grade. That is the one genuinely novel idea
   and it has been starved to maintain commodity code.
4. The **decomposer** (slice work so N agents don't collide) is FACTORY and also survives.
5. **Stop building rig.** Measured 2026-08-03: **378 shell scripts / 73,019 lines of bash** in
   `fleet/`, versus 30,259 lines of product `src/`. The rig is 2.4x the product and is what breaks.

### D-002 · TOOL SELECTION WAS TAINTED, NOT JUST THE VERDICTS · 2026-08-03
**Operator, verbatim:** *"We may not have selected the BEST tool b/c the lense we made the selection
was tainted. maybe most tools will survive an audit but some may not."*

A tainted lens corrupts **selection**, not merely the grade: if the filters were *"no heavy
dependencies"* and *"the gateway core is ours"*, whole categories of candidate were never
shortlisted. **A re-score MUST re-open the candidate set, not just re-grade the finalists.** Some
currently-adopted tools will not survive.

**The three tainted lenses, in the rig's own words:**
1. *"the gateway core IS the differentiator, not something you outsource"* — now inverted by D-001.
2. **Dependency-weight as a veto** — `EVAL-REGISTRY.md` itself calls this `drifted`: *"argued 'full
   embed = wrong stack' then jumped straight to 'hand-roll natively,' skipping the plugin-wrap middle
   option Charon already uses elsewhere."*
3. **"Under-scoped trial"** (the rig's own registered anti-pattern) — an eval that honestly runs the
   candidate but configures the **incumbent** differently. Fair on paper, rigged in setup.

**CORRECTED LENSES — score every re-evaluation on these:**
- **L1 Total cost of ownership**, including maintenance and operator/session time. Not feature parity.
- **L2 Delete-on-adopt** — how many of OUR lines does adopting this DELETE? Adding without deleting
  is a failure.
- **L3 Wall-clock to working**, for an operator who does not read code.
- **L4 Failure visibility** — does it surface its own breakage, or must we discover it by luck?
- **L5 Conditional verdicts must be re-checked against whether the condition actually held.**
- **L6 Both sides configured at full strength** (kills the under-scoped-trial anti-pattern).
- **Operator standing preference:** *"an 80% feature parity product that doesn't spawn more work
  beats a 100% featured product that eats up time and resources."*

### D-003 · THE REAL FAILURE IS ENFORCEMENT, NOT RECALL · 2026-08-03
Adopt **no** memory product to fix decision-loss. Both commissioned reviews ran 9 products and
concluded `ADOPT-CANDIDATES: NONE`, because **every one requires an explicit write call** — and the
measured failure is agents not writing things down and nothing blocking on unfinished work.

**Build instead:** this ledger + **lifecycle enforcement** — an `ASKED` row blocks its dependent
tickets; an active `DECIDED` cannot be contradicted by a merge; unanswered questions notify the
operator OUT-OF-BAND (they are not at the terminal 24x7). Enforcement is a GATE, not a rule to
recall. The rig's own doctrine already says *"prefer the mechanism over recall"* and nothing
implements it.

**Re-open under the corrected lenses (L2 especially):** **Forgetful** (MIT, 287 stars, self-hosted,
MCP-native, local embeddings) scored **B +2 — the highest of any target** — for
`plans+tasks state machines with acceptance criteria, dependency gating, optimistic locking and cycle
detection`, and the review called it *"the only mechanism in any target that addresses the
'26 branches stranded' shape of failure."* **It was then rejected for "avoids a new dependency" —
lens 2 above, exactly.** Under D-001 a work-tracking layer with dependency gating is not a
dependency to avoid; it is factory core.

### D-004 · TURN ON WHAT WE ALREADY OWN, BEFORE ADOPTING ANYTHING NEW · 2026-08-03
**Operator, verbatim:** *"we have already implemented a number of tools just not all their features
or fully wired."*

`TOOL-UTILIZATION-AUDIT.md` (2026-08-01, measured on this box): **~20% of owned tool capability is
switched on.** mypy **0 of 14** components (3 flags = 176 real bugs). ruff 150 of 962 rules
(`preview` + `S/BLE/ARG/C90` = 196 findings incl. **3 HIGH security**). pytest **1 of 8** plugins.
shellcheck **0 of 11** optional checks (`-o all` = **31,810** findings on the rig, **15 error-level in
`fleet-droid.sh` itself** — the script whose orphaned loops are a live complaint). `graphify affected`
(blast-radius) = **0 invocations**.

**Installed and entirely unused:** `mutmut`, `hypothesis`, `diff-cover`, `playwright`, `pylint`,
`yamllint`, `actionlint`, `vulture`, `deadcode`, **`litellm-proxy`**.

> The audit's own conclusion: **"The failure mode is not missing tools — it is DEFAULT CONFIGURATION
> ACCEPTED AS THE TOOL'S FULL SURFACE."**

Its Top-5 were **approved 2026-08-01 and never started.** Every quality mechanism this project needs
is already on the machine, switched off. **Enablement is config, not code — it is the cheapest
possible move and it comes FIRST.**

### D-005 · QUALITY THE OPERATOR CAN TRUST WITHOUT READING CODE · 2026-08-03
The operator cannot judge code and must not be asked to. Trust comes from four mechanisms, in order
of value — all four are already installed (D-004):
1. **Required status checks + merge queue** — nothing merges unless green; **the machine lands it**,
   not a session that forgot. This alone kills the "left hanging" class: 46 of 62 open PRs are
   currently inert DRAFTS.
2. **Mutation testing** (`mutmut`) — breaks the code and checks a test notices. This is the
   mechanical answer to "gates that can't go red", replacing `gate-integrity.sh`'s 113 hand-written
   unproven assertions.
3. **Diff coverage** (`diff-cover`) — every new line must be exercised. Kills shipped-and-inert.
4. **E2E acceptance tests written from the operator's own words** (`playwright`) — the only check
   that speaks the operator's language rather than the code's.

**A dashboard must come AFTER this.** A status page fed by unproven gates displays a green lie —
which is the exact failure class this project keeps hitting.

### D-006 · `test_gateway_outcome.py` IS OWED — operator asked, never delivered · logged 2026-08-03
**Operator, 2026-08-03:** *"I think i had even asked to implement test_gateway_outcome.py and that
never got deployed."* **Verified: correct.** `tests/test_gateway_outcome.py` does not exist and
`git log --all` shows it was **never committed on any branch.** The design survived
(`fleet/state/OUTCOME-TEST-BLUEPRINT.md`, deliberately git-tracked — its `.gitignore` negation
literally reads *"Operator asked for this file to be DURABLE"*). **The blueprint was preserved and
the implementation was dropped** — the class in one artifact.

**Build it, with the correction already on record (2026-08-02):** land **§3** of the blueprint,
**NOT §1**. §1 is a fake test — *"it passes on a gateway with no failover at all and reports 'runner
not found' as a behaviour failure."* Landing §1 would have produced a green signal proving nothing,
which is the failure mode D-005 exists to kill.

This is a **D-005 mechanism** (an outcome/acceptance test that asserts observable behaviour), so it
belongs in the first enablement lane, not the backlog.

### D-007 · THE CLASS: THIS PROJECT CONVERTS REQUESTS INTO RESEARCH AND DROPS THE IMPLEMENTATION · 2026-08-03
**Operator, 2026-08-03:** *"we lost the Behavior-Driven Development (BDD) and outcome-focused testing
work i think."* **Verified — the research survived and every piece of implementation was dropped:**

| piece | status |
|---|---|
| BDD evaluation (254 lines, DO NOT ADOPT verdict) | 🟢 **landed** on master (`2ee3513`, PR #434) |
| `eval/bdd-framework` branch, 3 commits ahead | 🟢 **not lost** — pre-squash originals of the above; stale, safe to delete |
| Hypothesis **ADOPT-NARROW** verdict (tested live, shrank a seeded off-by-one to `[10]`) | 🔴 **never implemented** — absent from `pyproject.toml`, **0 test files use it** |
| `OUTCOME-TEST-REWRITE` ticket | 🔴 **never minted** |
| `HYPOTHESIS-ADOPT-NARROW` ticket | 🔴 **never minted** |
| `KSF-FIXES-1-3` tickets | 🔴 **never minted** |
| `tests/test_gateway_outcome.py` | 🔴 **never committed on any branch** (D-006) |

**Generalize this — it is the single most expensive pattern in the project:** an operator request
reliably becomes a high-quality research artifact, a landed verdict, and **no working code.** The
analysis is not the deliverable. Nine memory products were installed and run; 76 registry rows were
written; ~393 review artifacts exist; and the operator still cannot get a feature built end to end.

**The mechanical fixes are already decided:** D-005 (a **merge queue lands it**, not a session that
forgot) and this ledger's blocking edge (an `ASKED` row stops dependent work; a `DECIDED` row cannot
be contradicted). **A verdict without a minted ticket and a landed diff is not done** — and no
session may report it as done.

### D-008 · LANGUAGE POLICY — REWRITE NOTHING; CHOOSE PER *NEW* COMPONENT · 2026-08-03
**Operator approved 2026-08-03 and asked for it LOUD.**

> ## 🔴 REWRITING WORKING CODE FOR LANGUAGE REASONS IS FORBIDDEN. 🔴
> It produces **zero** features and costs weeks. It is the purest form of the two-steps-back
> pattern. A session that proposes a Python→Go migration of working code is wrong; if the operator
> wants it, they must say so explicitly and overrule this line.

**Choose per NEW component:**

| component shape | language | why |
|---|---|---|
| long-running daemons, supervisors, watchdogs, CLIs | 🟢 **Go** | single static binary, real concurrency, compiler catches it before it runs — precisely where bash failed |
| web dashboard / any frontend | 🟢 **TypeScript** | do not render UI from Go or Python templates |
| outcome grading, analysis, data/ML-shaped work, glue | 🟢 **Python + mypy strict** | already here, small, best agent corpus; safety is one config change we already own (D-004) |
| anything | 🔴 **Rust** | slowest to write, agents get it wrong most often, nothing here needs its guarantees |
| **state, concurrency, or anything long-lived** | 🔴 **NEVER bash again** | measured: **1,696 `set -e`-suppressed sites** = 1,696 places a script continues after a command already failed. Bash cannot be ratcheted into safety — there is no type checker for it. |

**Bash is acceptable only for a script short enough to read on one screen that calls other programs
and exits.** The moment it must remember state, coordinate with another process, or run for a long
time, it must not be bash.

**Why this is mostly moot for existing code:** D-001 already deletes most of the Python rather than
rewriting it — ~6,500 lines of commodity gateway and ~6,700 lines of leaked orchestration go to
adopted substrate. The language question applies to the ~2,100-line outcome-grading slice plus the
decomposer, which work and are small. **The real language problem is 73,019 lines of bash, and its
answer is deletion onto an adopted engine, not translation into Go.**

#### D-008a · WHERE A SMALL GO SLICE *IS* WORTH IT (operator pushback, accepted)
Yes — some slices earn Go on their own merits even while everything else stays put. Ranked:

1. **The supervisor / reaper** — the process that keeps workers alive, enforces leases with fencing,
   reaps orphans, and itself never dies. **This is the single best Go candidate**: it must survive
   for days, handle signals, manage children, and never silently continue after an error. It maps
   directly onto the top operator complaint (orphaned invisible droids that claim tickets and lose
   work). ~500-1,000 lines.
   ⛔ **SEQUENCING — do NOT build this before Q-001 is answered.** If a workflow engine is adopted
   (Lane B), **the engine IS the supervisor**, and a hand-written Go one would rebuild the thing we
   are about to adopt — rig-as-product, again. If an engine IS adopted, the Go slice shrinks to a
   thin local agent that reports into it; still Go, much smaller.
2. **Concurrent fan-out with deadlines** (launching/supervising N workers, cancel-at-timeout,
   collect results). Go's context+goroutines make this correct by construction; bash does it with
   background jobs and `wait`, which produced the fork-bomb class and the
   `pgrep`-matched-a-droid-prompt incident.
3. **Fast pre-commit / gate runner** — runs on EVERY commit, so startup cost is felt every time.
   Go starts instantly; a Python interpreter + imports does not.
4. **Any binary copied to another machine** (4-LOM, the Wyse boxes) — a static binary just runs;
   Python needs an environment provisioned and kept in sync.

**NOT worth Go even though it looks like it might be:** the outcome-grading/scoring logic (wants
Python's ecosystem if grading gets smarter), one-shot analysis scripts (Python is faster to write),
and anything that mostly calls an LLM API and parses JSON (no benefit).

**Operator-facing rule of thumb:** *Go when it must stay alive, supervise, or be a binary you copy
to another machine. Python when it thinks, analyses, or runs once.*

---

## ASKED — open, and what each one BLOCKS

### D-009 · THE RE-REVIEW HAS THREE AXES, NOT ONE · 2026-08-03
**Operator:** *"when we re-review the tools and the other contenders we should also run an audit for
gaps that we did not get a tool for."* Accepted — this is a third axis and the one most likely to
explain how 73,019 lines of bash came to exist.

| axis | question | finds |
|---|---|---|
| **1 · re-score** | was the VERDICT right, under the corrected lenses (D-002)? | wrong rejections — e.g. LiteLLM full-gateway (now void), Forgetful (rejected for "avoids a new dependency") |
| **2 · re-open** | which candidates were never SHORTLISTED because of the tainted filter? | whole categories excluded by "no heavy dependencies" / "the gateway core is ours" |
| **3 · GAP AUDIT** | which capabilities have **NO tool at all** — nobody ever asked "is there a tool for this?" | **the hand-rolled column.** This is where the bash came from. |

**Method for axis 3 — mechanical, not a brainstorm:** enumerate every capability the factory needs,
then map each to exactly one of `adopted tool` / `hand-rolled` / `nothing`. Every `hand-rolled` row
is a gap where the tool question was never asked, and every `nothing` row is an unmet need. Starting
capability list (extend it, do not treat it as complete): decompose work into non-colliding slices ·
execute agents · isolate agents from each other · durable work queue (no orphans/retries/no loss) ·
single work ledger · prove quality without reading code · land automatically when green · deploy ·
route to cheap models · visualise the system · **decision durability** · secret handling ·
observability/alerting · cost accounting.

**Report per gap:** capability · what we do today (file:line or "nothing") · our LOC · does a tool
exist · what adopting it would DELETE (lens L2). A gap with no candidate is a legitimate build —
that is how the ~2,100-line novel slice earned its place.

### D-010 · LANE ORDER APPROVED (answers Q-001) · 2026-08-03
Operator approved the manager recommendation: **Lane A first** (turn on what we own — it makes every
later verdict measurable), **Lane C in parallel** (the three-axis re-evaluation; read-only so it
cannot collide), **Lane B last** and as a **cutover-with-deletion, never an addition**. Lane C
launched 2026-08-03. Q-001 is CLOSED.

### D-011 · THE DISPLAY TOOL — AND ITS SCHEDULE (answers Q-002) · 2026-08-03
Operator asked twice which tool, since n8n is wrong, and recalled monit. **They were right about
monit — for one of the three jobs.** "Realtime code map + broken gates + feature-not-done" is THREE
different jobs, which is why no single tool fits:

| job | right tool | status on this box |
|---|---|---|
| process liveness / restart / alert-when-down | 🟢 **monit** | ALREADY partly adopted — `fleet/watchdog/` generates monit config from `fleet/state/service-registry.tsv`. Finish wiring it; do NOT stretch it to gates. |
| status view over gates / tickets / PRs / work-loss | 🟢 **generated static HTML page** | STATUS-BOARD-V1, building 2026-08-03 |
| code map / dependency graph / blast radius | 🟢 **graphify** (owned) rendered to HTML | graph.json already built by 114 call sites; `affected` has **0** call sites |
| dashboards with HISTORY + alerting | 🟠 **Grafana** (+Prometheus) | LATER, only if trends/alerting are wanted |
| event glue to external services (Slack/email/phone) | 🟠 **n8n is legitimate HERE** | not needed yet |

**n8n is not wrong at everything — it is wrong at DISPLAY.** It is workflow automation ("when X, do
Y") with a visual editor. Rendering a status page in it means fighting the tool.

**Static page over Grafana for now, stated as a trade:** static = zero runtime, nothing to keep
alive, no auth, versioned in git, opens from disk; loses charts, history, alerting, and is
minutes-stale. Grafana = real dashboards + alerting; costs a server plus data sources to keep alive —
**and keeping services alive is precisely what keeps failing here.** Revisit after living with v3.

**SCHEDULE — each step gated on a NAMED precondition, not a date:**
- **v1 — NOW (2026-08-03).** Snapshot only, three states (green / red / **grey UNPROVEN**), real
  numbers including the ugly ones. Safe to build before the gates are trustworthy *precisely
  because* it renders UNPROVEN honestly rather than green.
- **v2 — after Lane A lands AND mutation testing (`mutmut`) is wired.** That is what answers
  "can this gate actually go red" mechanically, so grey tiles can legitimately become green. Until
  then most tiles stay grey, and that is correct.
- **v3 — after v2: auto-regenerate** from CI runs + the existing 20-min cron. THIS is the
  "realtime" step (minutes-fresh). Deliberately last: auto-publishing an untrustworthy page is worse
  than having no page, because the operator would believe it.
- **Grafana decision point — only after v3 has been lived with.**

⛔ The ordering rule behind all of it: **a dashboard over unproven gates is a GREEN LIE.** On record
here: 113 red-proof suites that never execute in CI, and a PASSING check reported as RED for weeks.

### D-012 · FULLY-PARKED POOL MUST RETURN 503, NOT A SILENT 200 · 2026-08-04
**Operator (answering Q1):** *"I don't want a situation where EVERYONE is parked but I understand it
may be needed for some reason. CHange it to 503 don't allow it to leak."*

Today `forwarder.py:481-487` restores the FULL chain — parked legs included — when every leg of a
pool is parked, and serves a normal **200**. That is how money leaks while everything looks healthy.
Measured 2026-08-03: `kimi-k2.6` (5/5 legs parked) and `minimax-m2.5` (2/2 parked) both served 200
via openrouter.

**CHANGE TO: a real 503.** Requirements, so the failure is diagnosable rather than merely loud —
the operator explicitly accepted that some requests will now fail:
- terminal **503**, never a success-shaped body;
- the envelope must NAME EVERY LEG with its real per-leg status and a non-empty reason (i.e. reuse
  the existing `all_providers_exhausted` shape, which already does this);
- it must be distinguishable from "all legs tried and failed" — the reason here is
  *"every leg is parked"*, which is an operator/config state, not an upstream failure;
- `X-Charon-*` headers must report the truth (attempts = 0 upstream calls made).

⚠ **`tests/test_gateway_outcome.py` MUST CHANGE WITH IT.** Its test
`test_all_legs_parked_still_serves_a_real_200_and_never_strands` currently asserts the 200 and
therefore CEMENTS the behaviour being removed. Invert it to assert the 503 + the named-legs envelope,
and keep a red-proof. A good test locking in a bad decision is exactly why this note exists.

### D-013 · TOOLS THAT ENFORCE NOTHING GET MOVED — NO NEED TO ASK · 2026-08-04
**Operator (answering Q2):** *"Move them. Tools that do nothing should be moved to where it makes
sense. NO need to ask me about that."*

MEASURED 2026-08-03/04: `semgrep`, `gitleaks` and `bandit` have **371–384 successful runs on
`Nnyan/charon-private`, and block nothing** — that repo is on a free plan and
`gh api repos/Nnyan/charon-private/branches/master/protection` returns
**403 "Upgrade to GitHub Pro or make this repository public"**, so no check can EVER be required
there. The product repo `SLOP-Platform/charon` DOES have protection but requires only `["gate"]`
(`strict:false`).

**STANDING AUTHORITY GRANTED:** a tool that is running but enforcing nothing may be relocated to
where it can enforce, without asking. Zero new tools, zero new LOC — it converts advisory theatre
into a gate. Generalise it: **"green runs" is not evidence of enforcement; being a REQUIRED check
is.** Verify with the `protection` endpoint, never by the presence of a passing workflow.

### D-014 · SELF-HOSTED RUNNERS EXIST — CI VOLUME IS NOT FREE · 2026-08-04
**Operator (answering Q3):** *"I think we can use them for SG and SLOP/mediastack. I believe we have
them on two servers for 6-7 runners. 4-LOM and BB-8."*

Consequence for the merge queue: a merge queue **re-runs checks against the updated base**, so it
INCREASES CI volume. On GitHub-hosted public runners that is free; on 4-LOM/BB-8 it is real
wall-clock on hardware that is also running the gateway and the fleet. **Therefore: enable the merge
queue WITH A CONCURRENCY CAP, not wide open**, and confirm which jobs are `runs-on: self-hosted`
before turning it on. Do not assume a job is GitHub-hosted.

### Q-001 · [CLOSED — see D-010] Re-score pass: which lane runs first? · asked 2026-08-03
**Blocks:** the whole adopt/delete programme (D-001..D-004).
Lane A = turn on what we own (config, days, cheapest). Lane B = delete the 73k-line bash rig onto
adopted substrate. Lane C = re-score the 76 EVAL-REGISTRY rows + 393 review artifacts under the
corrected lenses, re-opening the candidate set per D-002.
**Manager recommendation:** A first (it makes every later verdict measurable), C in parallel
(read-only, no collision), B last and as a cutover-with-deletion, never an addition.

### Q-002 · Live status dashboard — confirm shape · asked 2026-08-03
**Blocks:** nothing yet; scheduled after D-005 by decision.
Operator wants a realtime graphic web page showing broken gates / unfinished features / code map,
"something like n8n". **Answer: yes, entirely possible, and the data already exists** (gate results,
board tickets, PR states, `graphify` graph). n8n is an event-glue tool, not a dashboard — the cheap
shape is a generated page + the existing CI as the trigger. **Deliberately sequenced AFTER D-005**
per that decision: a dashboard over unproven gates shows a green lie.

---

## SUPERSEDED

*(none yet)*
