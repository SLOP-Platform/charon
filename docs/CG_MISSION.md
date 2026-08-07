---
doc: CG_MISSION
version: 3
date: 2026-08-07
supersedes: 2
aligns_with:
  - CG_PLAN_v2.md (this charter is proposed as its §1)
changelog:
  - "v3 (2026-08-07): adopt-first charter — thin-glue mission, objectives 0–7, adoption rules (landed PR #245)"
  - "v1–v2: earlier mission drafts, superseded"
---

# CG Mission & Adoption Charter
*(proposed as `CG_PLAN_v2 §1`, superseding the §3 "identity is unknown" language)*

## Mission
Charon is **thin glue that composes battle-tested tools** into a pipeline that takes intent
and returns merged, tested, durable work. It progressively **adopts mature products and wires
them together** instead of extending hand-written infrastructure.

The mission is not "small for its own sake." It is: **ship quality work cheaply, on a system a
single operator can hold** — and the way to get there is to own less. Reduction is the method;
**shipping is the point.** Any success measured only in deleted lines is measuring the wrong
thing (adversarial finding #1).

## The shrink test (bounded, not an obsession)
A change is questioned if it makes Charon **larger without deleting an equivalent amount of
custom infrastructure**. Two guards on this:
- Measure **total operability**, not Charon's line count. Shrinking Charon's code while adding
  six services you must now run, upgrade, and debug is a *loss* — the metric is how much the
  operator has to hold, across code *and* running systems (finding #2).
- There is a **floor**. Once Charon is thin — the composition layer plus the novel core below —
  the goal becomes **stability, not further cutting.** Do not chase deletions past "done to the
  bones." The ratchet drives toward the floor, then relaxes.

## What Charon owns
- Evaluation, Integration, Wiring, Composition, Migration, and Deletion of replaced code.
- **The outcome ledger and grading** — which (model, provider) produced each unit, at what
  cost-to-correct, graded by real outcomes. **No mature product provides this; it is CG's one
  deliberate build, not a candidate for adoption** (finding #4). "Shrink responsibilities" means
  shed *commodity* responsibilities, never the novel core.

## What Charon does NOT own
Workflow execution · queue implementation · policy implementation · memory/continuity
implementation · project/backlog management. Those belong to adopted products.

## Guiding principle
**Adopt before Build. Compose before Extend. Delete after Adopt.**
Every feature first asks:
1. Does a mature product already solve this?
2. Can Charon integrate it behind a thin, swappable boundary?
3. What custom code gets deleted if we adopt it — and what is the *net* line count, glue
   included? (An adoption whose adapter is bigger than what it deletes is a second custom
   system wearing a badge — finding #3.)

Only if no suitable product exists is new code written.

## Objectives (in order; each fully finished before the next)
0. **Drain the debt and make state honest** — you cannot delete-after-adopt custom code that is
   buried under un-landed PRs and a lying board. This is the precondition (finding #6).
1. **Fix execution continuity** — session-to-session focus and handoff (Invariant S, the
   playbook, the reconciled board). Tools do not fix discipline; a workflow engine adopted onto
   an undisciplined base just automates the chaos (finding #5).
2. **Establish one authoritative backlog** — and *migrate and delete* the others (GitHub issues,
   fleet board, tickets, needs-push). Adopting a tool without consolidating adds a backlog
   instead of replacing them (finding #6).
3. **Replace custom orchestration with a workflow engine** — this is the custom fleet
   (launcher, board, leases, retirement), and the tooling bugs found while draining are
   arguments *for* replacement, not fix-in-place tickets.
4. Replace custom queues with a battle-tested queue.
5. Replace custom policy with a policy engine.
6. Replace custom continuity with a continuity solution, **if it earns its place.**
7. Leave Charon as a thin composition layer over the novel core.

**No engine adoption (3+) begins until objectives 0–1 are proven on real work.** One migration
is fully complete — custom path deleted, replacement confirmed on real work — before the next
starts. Never two half-done migrations at once; each carries a rollback (finding #7).

## Adoption rules
- **Evaluate by hands-on fact, not document scanning.** Every serious candidate gets a real
  spike: deploy it, wire one thin slice of Charon through it, exercise the actual
  feature/capability, and measure the *real* integration and deployment/maintenance burden. Docs
  and marketing say what a tool claims; only running it shows what it costs to operate. **Every
  verdict — "X is overkill," "X is the fit" — must be backed by that hands-on evidence, not a
  surface read** (including the Temporal call below: confirmed by spike, not assumed).
- **One solution per slice.** One workflow engine, one queue, one policy engine — never two
  tools owning the same function. A single multi-purpose tool may span several slices; two tools
  may not share one.
- **Right-sized simplicity beats raw power.** The best tool for CG is the *simplest one that
  effectively covers the slice and a solo operator can integrate and maintain* — **not** the most
  capable. Reject overkill even when it is technically superior — **Temporal is the standing
  example: an excellent product, and very likely overkill for a setup this size (confirm by
  spike, don't assume); prefer Windmill / Prefect-class simplicity.** Complexity is
  a maintenance cost that fails the operability test, so a powerful-but-heavy tool can be the
  *wrong* adoption even when it is the "better" product.
- **The candidate lists are a starting point, not a shortlist.** Evaluate genuinely; a *great*
  fit here means **simple, effective, and easy to maintain — not maximal.** If none of the
  candidates clears that bar, **expand the search** rather than settle for a mediocre fit (which
  becomes permanent glue tax) or a heavyweight (which becomes permanent ops tax).
- **Strangler, not leap.** Adopt in parallel, prove the tool on real work (the §4
  "confirmed by real work" bar), *then* delete the custom path. Never delete-then-hope.
- **Weigh lock-in and exit cost — you are solo.** Prefer genuinely open, self-hostable tools
  that are swappable behind the thin boundary. Custom code you can fix at 2am; a relicense,
  abandonment, or unfixable upstream bug you cannot. Keep the glue boundary clean enough to swap
  the tool out (finding #8).

## Candidate adoption areas (starting candidates — evaluate, expand if needed)
| Slice | Candidates |
|---|---|
| Workflow / durable execution | Windmill · Prefect · Kestra · *(Temporal — powerful; likely overkill, confirm by spike)* |
| Project / backlog | Plane · OpenProject · Vikunja |
| Agent orchestration (the workforce) | Codex · Claude Code · OpenCode · Hermes |
| Continuity / memory | Forgetful · Graphiti · Mem0 · Zep |
| Policy | OPA · Cedar |
| Queue | Faktory · Dramatiq · Celery |
| Events | NATS · Redis Streams |

*(Note: "agent orchestration" is the workforce, not a subsystem — keep it distinct from the
workflow engine (slice 1) so the two don't fight over the same decisions.)*

## Success criteria
Charon is succeeding when **all** of these move together — architecture alone is not success:
- **Outcome:** work goes idea → merged, durable product, and the cost-per-accepted-task trend is
  down. (If this isn't happening, thinness is cosmetic.)
- **Ownership:** every major subsystem has exactly one authoritative owner (adopted or the novel
  core) — no duplicates, no half-migrations.
- **Operability:** the total the operator must hold — code *plus* running systems — is flat or
  falling, not just Charon's line count.
- **Direction:** new features arrive by adopting mature systems, and custom-infrastructure
  surface trends toward the floor — then holds there.
