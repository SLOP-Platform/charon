---
doc: CG_PLAN_v2
version: 1
date: 2026-08-06
supersedes: none
aligns_with:
  - CG_MISSION.md (its §1 charter; adopt before build, compose before extend, delete after adopt)
  - CG_HARVEST_MAP.md (companion to §6 — check before building any Block-B item)
changelog:
  - "v1 (2026-08-06): initial CG rebuild spec v2 + Session-1 survival kit (the '_v2' in the filename is the PLAN generation, not this doc's revision number)"
---

# CG Rebuild — Spec & Session-1 Survival Kit (v2)

**Status:** spec, ready to execute. Supersedes the `CG_PLAN_v1` chat draft.
**Provenance:** written from an adversarial review of v1 + a grounded audit of `src/charon`
(four read-only passes classifying every capability present / half-built / missing).
**One-line thesis:** the code is not missing features — it is a museum of correctly-built
parts that were never wired together. The rebuild is ~60% wiring, ~40% new build.

---

## 0. The one risk this document exists to kill

The effort dies the moment a session starts, loses focus, forgets where it is, and hands
session 2 a half-remembered plan. Everything below is subordinate to one invariant:

> **Invariant S — cold-start reconstructability.** Any session, launched with *only the repo*
> and *zero memory of prior sessions*, reconstructs full state by reading the repo and running
> **one command**. Nothing load-bearing lives in a chat, a model's context, or a person's head.

Five things must therefore be a file or a command, never a memory:

| Question a fresh session asks | Answered by | Not by |
|---|---|---|
| Where are we? | `make status` (computed) | remembering |
| What do I do next? | the single issue labeled `next` | remembering |
| Why — what's the plan? | this document | remembering |
| What's the full scope, so nothing's forgotten? | §6 the capability map | remembering |
| How do I behave? | `AGENTS.md` (§8) | remembering |

Session 1's *only* job is to make those five true. It writes **no product code**. Its success
is tested by Invariant S (see §7 exit check). This is the only session whose failure is
unrecoverable, so it is deliberately tiny.

---

## 1. Locked objective

CG takes a project idea and returns merged, tested, durable work, choosing models and providers
so the user never has to. Two quantities are optimized, with a strict priority:

**Quality is a hard constraint, never traded.** "Rock solid" is non-negotiable; cost and speed
are optimized only *within* the set of outcomes that clear the quality bar (§4 defines the bar).

**Cost = amortized dollars-to-correct, attributed to the origin.**
```
cost(provider·model, task) =
    dollars of the original attempt
  + dollars of every later fix to that task
  charged back to the provider·model that produced the original
```
This auto-punishes cheap-but-buggy: a $0.10 model that needs five $0.40 fixes costs $2.10 and
loses to a $1.00 model that succeeded once. The metric is a *trailing* number — it keeps
accruing as long as fixes land, and it can reopen post-merge (§4).

**Wall-clock is minimized through decomposition only** (§5), not through model-speed routing.
Extra latency from a cheaper model or from verification is accepted. The one exception: a
**dependency chain is serial by construction** — the wall-clock floor is the slowest path
through the dependency DAG, and only *on that critical path* does provider latency matter.
Everywhere else, ignore speed and optimize cost.

---

## 2. Grading substrate — three signals, three targets

An outcome must route its signal to the correct target. Conflating them poisons the rankings.

| Signal | Meaning | Grades | Notes |
|---|---|---|---|
| **Quality** | did the produced work hold up? | the **(model, provider) pair** | same model differs across providers (quantization, silent routing) — the pair is the atom |
| **Availability** | was the provider serving / up? | the **provider** only | never the model |
| **Funding** | key hit $0 / 402 | **nobody** | operational/treasury event, excluded from *all* grades |
| **Rate-limit** | 429 / bucket exhausted | **nobody** | operational, excluded from grades |

Rules that fall out:
- Model A bad on Provider A but great on Provider B → two separate pair-grades; neither leaks.
- Provider runs out of funds → zero grade impact (model *or* provider). Treasury only.
- Provider frequently unavailable → demotes the **provider**, leaves the **model** untouched.

Half of this already exists in code: `QualityScorer` (per-provider reliability = the
*availability* signal) and `balance.py` auto-park on 402 (funding already separated
operationally). Missing: the *(model, provider)* **quality** grade and the routing of each
event's `outcome-class` to the right target.

---

## 3. One ledger, right fields, two views

Not two ledgers. **One append-only event table**; "treasury" and "blame" are two rollups.

**Per-event row (append-only, never mutated):**

| Field | Purpose |
|---|---|
| `event_id`, `ts` | identity, ordering |
| `unit_id` | the work unit this event served |
| `actor_provider`, `actor_model`, `actor_fingerprint` | **who did it** — the missing axis today; the ledger currently records provider only |
| `event_kind` ∈ {original, remediation, review, test, integration} | what the spend was |
| `target_unit_id` (for remediation) | the unit being fixed → traces back to its origin actor |
| `cost_usd`, `tokens_in`, `tokens_out`, `wall_clock_ms` | the numbers |
| `outcome_class` ∈ {quality_pass, quality_fail, unavailable, funding, ratelimit, environment} | routes the signal per §2 |
| `defect_class` ∈ {spec, decomposition, implementation, environment} (when a defect) | routes *blame* per §5 / §7-grading |
| `escape_stage` ∈ {test, review, production} (when a defect) | weights severity — production escapes weigh most |

**Two views, both `GROUP BY` over the one table:**
- **Treasury** = `Σ cost_usd GROUP BY actor` (and by day/project) → drives caps & kill-switch.
- **Blame** = `Σ cost_usd of events whose `target_unit`'s origin = X GROUP BY X` → drives grading.

A higher-tier model that *fixes* a cheap model's bug spends real dollars (its own treasury row)
**and** those dollars count against the cheap model's blame rollup. One table, both truths, no
double-store.

**Storage:** the current per-task file ledger (`ledger.py`) is crash-safe and stays as the
per-run write path. What's missing is a **durable cross-task aggregate** the views read from —
grading needs weeks of history that survives branch deletion. That aggregate is the first brick
(§7).

---

## 4. "Done" is a lifecycle, not an event

"Done" cannot be marked synchronously. Three states; only the last means done.

```
  green ──land&clean──▶ landed ──confirmed by real work──▶ confirmed
                          │
                          └── issue traced to it ──▶ defective
                                                        │ reopens cost (§1)
                                                        │ demotes actor (§2 quality)
                                                        ▼
                                                   (re-enter as a fix)
```

| State | Definition | Built? |
|---|---|---|
| **green** | passes pre-merge gates (review + tests + acceptance command exits 0) | ✅ `acceptance.py` + re-derive-from-disk |
| **landed & clean** | merged; process cleaned up after itself (no stray worktrees/branches/temp); product-level e2e (red/green/dogfood) run on the integrated whole | ◐ unit cleanup ✅; product e2e report-only, no teeth ✗; global branch hygiene ✗ |
| **confirmed** | the change has been in place while the whole process ran **real work**, with no issue traced to it | ✗ absent |

**Two-signal grading (locked):**
- **Pre-merge** = admission + *tiering-correctness*. "Can you write code that passes the
  gate?" A failure suggests the actor was tiered too high — **but only if the defect is
  `implementation`.** A pre-merge failure caused by a bad spec (`spec`) or bad split
  (`decomposition`) or a flake (`environment`) must **not** demote the actor. Filter by
  `defect_class` before moving a tier, or the rankings learn garbage.
- **Post-merge** = durability. "Can you hold your standard?" A `production`-escape defect is the
  strongest demotion signal and reopens the task's cost (§1).

Pre-merge is only trustworthy if the actor **cannot author its own gate** (today the agent can
edit `tests/`, held only at land; the reviewer sees a SHA + note, not the diff). Making
acceptance actor-independent and the reviewer diff-aware are the highest-leverage teeth to add.

---

## 5. Decomposition policy

Splitting is the *only* wall-clock lever, and it has a break-even.

1. **Split only provably-independent units.** Independence is proven by the AST change-surface
   (`decompose_surface` / `semantic_proof`, already built and enforced as disjoint waves). No
   proof → serialize. This is a strength; keep it load-bearing.
2. **Honor the dependency DAG.** Some work is serial and must stay serial. The critical path
   sets the wall-clock floor (§1).
3. **Stop at break-even.** Split while `marginal wall-clock saved > marginal (agent overhead +
   expected integration-defect cost)`. Past that point, more agents *add* net work.
4. **Integration defects are `decomposition`-class.** A cross-unit semantic break passes every
   unit's own tests, so it grades **neither implementer** — it charges the decomposition tier.
   This is why §3 carries `defect_class` and why "just split more" is wrong: over-splitting
   manufactures decomposition defects, which are the remediation cost §1 is minimizing.

Calibration of the break-even (the numbers in `decompose_sizing.py`, currently seeded TODOs) is
deferred — the *principle* above is what the splitter optimizes; the constants get tuned from
ledger actuals once §3 is capturing them.

---

## 6. Capability map — what exists, what to wire, what to build

Legend: ✅ have · ◐ half-built/unwired · ✗ missing. This table is the **backlog memory** — the
scope of the whole effort, so nothing is rediscovered by accident.

### A — work pipeline
| # | Need | | Owner / gap |
|---|---|---|---|
| 1 | Idea → spec w/ acceptance | ◐ | `intake.py` structures markdown; doesn't author acceptance from a freeform idea |
| 2 | Decompose: collision-free gate | ✅ | AST-proven disjoint waves |
| 2b | Decompose: actual splitter | ◐ | `decompose_planner.py` unwired on CLI (refuse-and-suggest) |
| 3 | Schedule / dep-ordered queue | ✅ | `engine/board.py`, `scheduler.py` |
| 4 | Route tier → provider·model | ✅ | `router.py`+`api.py`+`pools.py` |
| 4b | Route **by difficulty** | ✗ | difficulty scored then dropped; tier defaults `"med"` |
| 5 | Execute: worktree isolation | ✅ | `gitutil`/`api` |
| 5b | Execute: container isolation | ✗ | env flag only; no container in tree |
| 5c | Execute: hang / no-commit | ◐ | no-commit handled; hang-during-init uncaught |
| 6 | Review: static scanners | ◐ | advisory/non-blocking by default |
| 6b | Review: diff-aware agentic | ✗ | reviewer sees SHA+note, not the diff |
| 7 | Acceptance: executable, from disk | ✅ | `acceptance.py` |
| 7b | Anti-gaming: independent author / red-first / mutation | ✗ | same checks re-run; mutmut off |
| 8 | Land: PR / owned-paths / CAS / conflict | ✅ | `land.py` |
| 8b | Land: re-test integrated result | ✗ | only scope/leak rechecked |
| 9 | Assemble units → product | ◐ | assumes disjoint owns; no semantic-merge |
| 9b | Product acceptance enforcement | ◐ | runs but report-only, no teeth |
| 10 | Deploy / release | ✗ | not a pipeline stage |
| 10b | Post-merge revert | ✗ | no `git revert` anywhere |

### B — invisible autopilot
| # | Need | | Owner / gap |
|---|---|---|---|
| 11 | Catalog (discover models) | ✅ | `catalog_refresh.py` wired |
| 12 | Availability | ✅ | balance/park + cooldown |
| 13 | Price | ✅ | metered supersedes quoted |
| 14 | Tier definition | ◐ | hard-coded, not benchmark-derived |
| 15 | Assignment tier→pair | ◐ | LLM/heuristic, not learned |
| 16 | Grade → promote/demote | ✗ | real modules, **no caller** |
| 16b | Defect taxonomy | ✗ | absent |
| 17 | Provider quality per (model,provider) | ◐ | reliability only, not capability |
| 18 | Explore / exploit | ✗ | absent |
| 19 | Benchmark cold-start seed | ◐ | `_SEED_PRIOR` exists, feeds empty matrix |

### C — blast radius (cross-cutting)
| # | Need | | Owner / gap |
|---|---|---|---|
| 20 | Durable state | ✅ | atomic files (no DB) |
| 21 | Crash-safe resumability | ✅ | `handoff`/`coordinator` |
| 22 | **Learning substrate** | ✗ | ledger has no model/fingerprint; no cross-task aggregate |
| 23 | Observability / `make status` | ◐ | console exists; no `make status` |
| 24 | Cost governor + kill switch | ◐ | monthly cap + per-run budget on separate paths; no unified kill |
| 25 | Runtime human escalation | ◐ | up-front approval ✅; nothing pages on repeated failure |
| 26 | Notifications | ✗ | log-only, no transports |
| 27 | Secrets / exfil | ✅ | per-provider base-bound; fixed on master |
| 28 | Sandbox / egress enforcement | ◐ | app-layer ✅; real boundary = separate infra, default-off |
| 29 | Cross-process rate-limit coordination | ✗ | quota engine unwired; in-process lock only |
| 30 | Reproducibility / replay | ◐ | spec captured; fingerprint missing |
| 31 | Traceability criterion→unit→test | ◐ | per-unit ✅; no product coverage map |
| 32 | Change management (idea drifts) | ✗ | not present |
| 33 | New-project onboarding / model screener | ✗ | preflight outside tree; assumes structured input |
| 34 | Flakiness quarantine | ✗ | not present |
| 35 | Per-stage failure taxonomy | ◐ | several failure modes uncaught |
| 36 | Meta-loop governance (CG builds CG) | ✗ | `gate_runner` is self-CI only |

### The loop these compose
```
route (seed + tiny explore) → run → green? (defect-class-filtered)
   → land & clean → confirmed by real work?
       → if defective: reopen cost + demote → re-rank
```
It closes with **three additions, all schema/wiring**: (a) `model`+fingerprint on the ledger,
(b) `defect_class` + `escape_stage` attribution, (c) the `landed → confirmed/defective`
transition driven by real runs. Everything else already exists, unconnected.

---

## 7. Session 1 — the survival kit (the answer to "can we get enough done first")

**Yes — if Session 1 externalizes the map, the protocol, and the first brick, and builds nothing
else.** Externalizing the *whole* backlog into fully-specced issues would overrun one session,
and a half-finished Session 1 is itself lost WIP (recursive failure). So the scope is bounded.

**Session 1 deliverables (and nothing else):**
1. **This document**, committed. (The plan + the map + the protocol, durable.)
2. **`AGENTS.md`** at repo root — §8 content, lifted verbatim. Read at every session start.
3. **Interim `make status`** — §9 definition. Reads git + forge (clearly labeled interim;
   upgraded to read the event-store once §3's aggregate exists). Resolves the v1 bootstrap
   paradox where `status` depended on a store four phases away.
4. **The first issues only**, one issue ≈ one PR, each with a written acceptance command,
   **exactly one labeled `next`**. Not the whole backlog — just enough that `next` points at
   real work. The remaining scope lives as §6 (the map), converted to issues *as* each is
   picked up, under the protocol.
5. **One milestone open.**

**The mandatory first `next`:** *"Stand up the unified event-ledger schema (§3) — add
`actor_model` + `actor_fingerprint` + `outcome_class` + `defect_class`/`escape_stage`, and a
durable cross-task aggregate the treasury/blame views read from."* This is first because it is
the one item that, if skipped, forces replaying every run before grading or routing can learn
(§1/§2/§3 all depend on it). Everything else queues behind it.

**Why it fits one session:** items 1–3 are writing (bounded), item 4 is a handful of issues, not
36. No code, no build, no rig work.

**Why it survives loss:** it makes Invariant S (§0) true and testable.

**Exit check (this *is* Invariant S, mechanized):**
> A fresh session, given only the repo and no memory, runs `make status`, reads `AGENTS.md`,
> and begins the `next` issue **without asking a question**. If it must ask where things stand
> or what to do, Session 1 failed and is redone before any build begins.

---

## 8. `AGENTS.md` (ready to place at repo root)

```
# Session protocol — read this first, every session.

1. Run `make status`. Work the single issue labeled `next`. Nothing else.
2. One unit per session. Open a PR and land it green, or push it to a `wip/<name>`
   branch and close the PR — NEVER delete unlanded work (an ephemeral container has no
   reflog to recover it). If it will not land this session: push wip/, close the PR,
   split the issue, label the next `next`, note why.
3. Commit early and often. Context exhaustion arrives without warning; unsaved reasoning
   is lost, WIP commits are not.
4. Done is the issue's acceptance command exiting zero. Not your judgement. And "done"
   for a change to CG itself is the three-state lifecycle: green → landed & clean →
   confirmed by a real run (docs/CG_PLAN_v2.md §4).
5. Anything discovered that is not the next action becomes an issue. File it; do not fix it.
6. Before stopping: label the next issue, confirm no stray branches/worktrees, and that
   `make status` reflects reality.

The full plan is docs/CG_PLAN_v2.md. The capability map (what exists / what to wire / what
to build) is §6 — consult it before deciding anything is missing; most gaps are unwired,
not absent.
```

---

## 9. Interim `make status` (ready to place)

Prints, from git + the forge (not memory): current branch, open-PR count, the single `next`
issue, and main's CI result. Explicitly interim — labeled as such in its own output — and
replaced by an event-store-backed version once §3's aggregate lands.

```make
status:  ## interim: computed session state (git + forge). Upgraded post-§3.
	@echo "== CG status (INTERIM — reads git+forge, not the event store) =="
	@echo "branch:   $$(git rev-parse --abbrev-ref HEAD)"
	@echo "worktrees:"; git worktree list
	@echo "next issue:"; gh issue list --label next --limit 5 2>/dev/null || echo "  (gh unavailable)"
	@echo "open PRs:  $$(gh pr list --state open --limit 100 2>/dev/null | wc -l)"
	@echo "main CI:   $$(gh run list --branch master --limit 1 2>/dev/null || echo n/a)"
```
(Adjust the forge commands to the operator's rig; the contract is *what it prints*, computed,
never hand-written.)

---

## Appendix — deferred by explicit decision

These are acknowledged, filed, and intentionally not done now (recorded so they are not
forgotten, not so they block):

- **Decomposition break-even constants** (§5) — tuned from ledger actuals, not up front.
- **Provider-data completeness** (§2) — start from the benchmark seed; rankings evolve as work
  runs. One non-negotiable minimum: a *tiny* explore rule (route a small fraction of low-stakes
  units to the cheapest untried pair), or "learn as we go" only ever learns about incumbents.
- **Wall-clock optimization beyond decomposition** (§1) — not pursued, except a slow provider on
  the critical path.
- **Container isolation, egress enforcement, credential custody** (#5b/#28) — separate infra;
  keep default-off until deployed.
```
