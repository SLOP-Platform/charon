# DSGN-WCI-reshape — Work-Composition Intelligence (post-REWORK reshape)

**Status:** RESHAPE draft for operator sign-off. NOT an ADR, NOT build-tickets. Stops at design.
**Supersedes for build purposes:** the pre-review WCI design (WCI-1..WCI-6) whose adversarial
review returned **REWORK** (findings B1–B4, M1, M3 captured in `DESIGN-QUEUE.md`).
**Does not overwrite** the prior design; this is the reshape artifact that answers each finding.

Grounding read for this pass (so claims are checkable, not asserted):
- Rig reference impl: `validate_board.sh`, `claim.sh`, `board.sh`, `done.sh` (the proven
  coordination model to productize — ADR-0010 D1).
- Product substrate already shipped: `src/charon/engine/board.py` (`claimable` predicate,
  `_overlap`), `src/charon/engine/scheduler.py` (`drain`/`_launch_round`/`_settle`/`_advance`),
  `src/charon/intake.py` (`analyze`, `_overlap`, reuse of `land.in_scope`), `src/charon/land.py`
  (`in_scope`, the nested-or-equal path matcher all three layers share).
- ADRs: 0006 (PERF-4 parallel units), 0007 (safe-landing-first; D3/D4 propose-default; D7 warm
  pool; D8 liveness), 0008/0011 (intake→ticket-plan; Phase 2 auto-decompose deferred), 0010
  (native substrate: `engine/board|claim|scheduler`, anti-dilution boundary, scanner matrix).
- Manager memories honored: `charon-work-composition-intelligence` (the 3 pillars),
  `charon-own-work-engine` (ACP warm-pool workers + `parallel.py` ThreadPool — do not reinvent the
  worker model), `charon-modular-agent-and-provider-agnostic` (no opencode/provider hardcoding;
  drive any ACP agent over the gateway), `product-vs-build-rig-boundary` (no fleet/SLOP/tracking.db
  leak into the product).

---

## 1. Problem / goal

Charon already runs work concurrently (PERF-4 `run_parallel` + `engine/scheduler.drain` over a
durable `engine/board.py`, propose-default landing via `land.py`). What it does **not** yet do is
*compose work intelligently*: it trusts whatever unit set it is handed. The operator's CORE
direction is to productize the fleet **manager's own scheduling doctrine** into the engine so that
the engine itself:

1. refuses to schedule **redundant / duplicate / contradictory / obsoleted** work,
2. extracts the **maximum safe concurrency** the dependency structure allows, and
3. **chunks** dependent work so the truly-dependent sliver is the only thing that blocks.

Live evidence the gap is real: even careful *manual* ticketing this session created an avoidable
block (TIER7B `depends_on HARD1` was a **merge-order** relation mislabeled as a **build
dependency**) — exactly the class of mistake the reconciler/chunker should catch.

The reshape's job is to keep that goal but make it survive the REWORK findings: stop claiming
safety the implementation can't deliver, keep the board's deterministic/replayable contract intact,
keep LLM judgment off the critical path, and be honest about how much is genuinely new.

---

## 2. The three pillars (restated cleanly)

**Pillar 1 — No redundant / contradictory work (the *Reconciler*).**
Before a drain *and* re-run on every merge, reconcile the pending board against current reality.
Split honestly into two halves:
- **Static half (already exists — a re-port, not new):** transitive-dep validity, owns-collision,
  duplicate-branch, orphan-marker, overlap→serialize. This is `validate_board.sh` +
  `board.claimable` + `intake.analyze` re-expressed as one reusable engine function. Deterministic.
- **Semantic half (the genuinely new part):** dedup / obsolescence / contradiction judgment that
  needs an LLM. **Advisory only, off the hot path** (see Pillar-1 decisions + B3).

**Pillar 2 — Maximize safe concurrency (the *Scheduler ordering*).**
The board's `claimable` predicate already extracts the ready set wave-by-wave. WCI's contribution
is a **better launch order within a wave** so the critical path drains first — implemented as a
**pre-sort**, never as a change to the claimability/serialization *rule* (see B2).

**Pillar 3 — Dependency-minimizing chunking (the *Decomposer*, gated).**
When work carries a dependency, restructure it so only the dependent sliver waits. This is
ADR-0008 **Phase 2 auto-decompose**, which is *already deferred behind a conflict-rate tripwire*.
WCI does **not** unlock it. WCI's in-scope contribution to Pillar 3 is narrower and safe: (a)
distinguish **merge-order** edges from **build-dependency** edges in intake (the TIER7B class of
bug), and (b) define the **semantic-independence proof** that any future slice must pass before it
may run concurrently (see B1). Actual auto-slicing stays gated.

---

## 3. Reshape decisions

**R1 — WCI is a *composition layer*, not a new engine.** It adds reasoning *around* the existing
substrate; it never forks the worker model. Workers remain warm-pool **ACP agents** driven by
`AgentBackend` + `parallel.py` ThreadPool through the fenced `coordinator.run` (ADR-0007 D7/D8,
ADR-0010 D2). No process-per-unit, no `WorkerBackend` port, no `claude -p` (that is dev-rig only).

**R2 — One deterministic reconcile function; LLM strictly advisory.** Pillar 1's static half lands
as a pure, deterministic `engine` function (call it `reconcile_static`) reused by intake, by a
pre-drain preflight, and by the on-merge hook. The semantic half is a **separate advisory pass**
whose output is **annotations/flags on units**, never a mutation of `claimable`. The board stays
diffable/replayable; an LLM verdict can never gate a claim or stall a drain (B3).

**R3 — Agnostic by construction.** Semantic judgment is performed by an **agent the engine already
knows how to launch**, pointed at **Charon's own gateway** requesting a **tier id** as the model
(per `charon-modular-agent-and-provider-agnostic`). No provider SDK, no opencode coupling. The
reconciler-agent is "just another ACP unit" with a fixed system contract; swap the agent/provider
freely behind the gateway.

**R4 — Product-clean.** WCI ships in `src/charon/engine/` only, behind the same anti-dilution
boundary test as the rest of the engine (gateway path imports nothing from `engine.*`; stdlib-only
core). No `tracking.db`, no `fleet/`, no SLOP. Intake source stays the **general adapter seam**
(ADR-0011 D5), never a hardcoded tracker.

**R5 — Concurrency order is a pre-sort, claimability rule is untouched (resolves B2).**
`board.claimable` keeps `other.id < unit.id` as the **final, injective** serialization tiebreak —
it is what guarantees no-deadlock and deterministic replay on a board with no acyclicity guard.
WCI adds a **stable pre-sort key** (critical-path depth: longest dependency chain *to* a unit)
applied to `claimable_units()` ordering **only**, with **id as the final tiebreak**. Depth changes
*which ready unit a free worker picks first*, never *whether* a unit is claimable. Non-injective
depth can never create or break a cycle because it does not touch the rule, only the queue order.

**R5 determinism invariant (resolves F2).** The depth sort key MUST be a **pure deterministic
function of board graph state** — i.e., computed solely from the unit set and its `depends_on`
(/`merge_after`) edges (and `id` as the final tiebreak), with **no** dependence on wall-clock,
worker arrival order, RNG, map-iteration nondeterminism, or any in-flight runtime signal. Under this
invariant replay is preserved: re-running a drain from the same board log produces the identical
`claimable_units()` order, hence the identical launch/land sequence.

This invariant is **load-bearing, not cosmetic**, because depth is load-bearing on *which units
launch within a single drain when the synchronous per-tier capacity cap binds mid-round*.
`scheduler._launch_round` (scheduler.py:308) iterates `claimable_units()` in order and, **in that
same loop**, calls the per-tier capacity limiter `try_acquire` (scheduler.py:311); because
`try_acquire` binds **synchronously, in-loop, in `claimable_units()` order**, when the cap binds
partway through a wave it cleanly admits exactly the earlier-ordered prefix while the rest stay READY
for a later drain. So depth **does** decide per-drain launch *composition* under the capacity cap —
it just never decides *claimability* (the set is identical; only its order, and therefore which
prefix fits under the cap, changes). That outcome is replayable iff the key is the pure function
above; a nondeterministic key would silently make the under-cap launch prefix unreplayable. Stated
plainly: **depth reorders the claimable set, the synchronous `try_acquire` cap truncates that order
deterministically, and both must be a deterministic function of board state.**

**Scope — the replay claim is the synchronous capacity cap, NOT the concurrent budget gate.** The
`SharedBudget` gate is a different mechanism and is explicitly **out of scope** for this determinism
guarantee. `SharedBudget` is constructed in `drain` (scheduler.py:272), passed through `_execute`
(scheduler.py:330) and into the runner as `cost_gate=gate` (scheduler.py:354), and **consumed
concurrently on worker threads inside `coordinator.run` — NOT in `claimable_units()` order**. Under a
*budget* cap every claimable unit is still launched; losers return `status=="budget"` → RETRY →
READY, and which units win is **thread-timing-dependent, not board-state-deterministic**. That
budget-race ordering was already non-replayable pre-WCI; depth neither adds nor removes it, and the
depth-determinism invariant makes **no** claim about it.

**R6 — On-merge reconcile hooks the scheduler `_advance` seam, not `land.py` (resolves B4).**
The "re-run reconcile on every merge" trigger lives where board state already advances:
`scheduler._settle` → `_advance` (scheduler.py:390 — `_advance` lives only in the scheduler; board.py
is ~241 lines and has no line 390), on the **main thread** where
all board mutations are already serialized. `land.py` stays a pure gate (diff-scope / sensitive
path / acceptance / gitleaks) with **no scheduling knowledge** — wiring reconcile there would be a
layer violation. The reconcile is incremental (only units whose `owns`/deps intersect the just-done
unit), so there is **no O(N²) static pre-filter** to "tame" — the cost claim the review rejected is
dropped entirely.

**R7 — Path-disjointness is a *necessary, not sufficient* condition; no slice ships on it alone
(resolves B1).** `_overlap`/`assert_disjoint_waves` only compares declared paths — it proves
nothing about imports, calls, shared runtime state, or config. Therefore: (a) WCI **keeps the
conservative-serialize default** for anything not proven independent (intake D2.2 behavior
preserved); (b) any *future* slice that would run two sub-units concurrently must pass an explicit
**semantic-independence proof** (defined as an open contract in §5), not just disjoint `owns`; (c)
re-labeling an edge (e.g. `depends_on`→`merge_after`, WCI-4) is **concurrency-neutral by
construction**: it may record a different *intent* (land/merge-order vs build-prerequisite) but it
does **not**, on its own, change the claim-gate — a label flip can never downgrade a build-dep to
concurrent. The concurrent split, when it ever happens, is invented by the §5.1 semantic-independence
proof, **never by the label** (precise invariant + B1-symmetric proof in §7, F1). Path-slicing is
removed as a *safety* claim.

> **Correction to the pre-fix R7(c).** The earlier wording ("Pillar 3 only re-labels edges … it
> never *invents* a concurrent split") was true of the label but glossed over the hazard the
> focused review surfaced: the *only* way a `merge_after` edge could fix a false-block is by relaxing
> the dep-done claim-gate so the pair runs concurrently — i.e. by inventing a split. If that
> relaxation keyed on owns-disjointness it would re-open the B1 hazard in reverse. F1 (§7) replaces
> the bare assertion with the exact invariant under which the claim stays true.

**R8 — Honest MVP scope (resolves M1).** The MVP is **Pillar 1 static reconciler (R2 static half) +
Pillar 2 pre-sort (R5)**. We state plainly: the static reconciler is **~70% a consolidation/re-port**
of `validate_board.sh` + `board.claimable` + `intake.analyze` + `validate.in_scope`. Its *new* value
is (i) running the same checks *continuously* (pre-drain + on-merge) rather than once at intake, and
(ii) a single reusable function instead of three parallel implementations. The **only genuinely new
intelligence** is the semantic dedup/contradiction pass (R2 advisory) and the eventual gated slice
(Pillar 3). Tickets must be sized against that truth, not against "build a smart scheduler."

**R9 — Injection hardening for the semantic pass (resolves M3).** Feeding untrusted ticket
text/diffs to an LLM judge re-opens the input-as-data boundary (ADR-0011 D1/D7). Mitigations: the
semantic pass runs as a **fenced unit** (same container/escape-scan posture as any worker, ADR-0007
invariants); its input is wrapped as **data, never instructions** (ticket text in a delimited,
non-parsed block, mirroring intake's fenced-block rule); its **only** output channel is a
**structured verdict** (`{unit_id, flag, confidence, reason}`) that is **advisory** — a hostile
verdict can flag/unflag a unit for human attention but **cannot** mutate `claimable`, land code, or
alter deps. Worst case is a misleading annotation a human reviews, not an exploit path. The verdict
schema is validated; free-form text outside it is discarded.

---

## 4. Prior-finding → resolution table

| Finding | What the review demanded | Reshape resolution | Checkable anchor |
|---|---|---|---|
| **B1** — drop path-slicing as a *safety* claim; disjoint `owns` ≠ semantic independence; require a semantic proof before any slice, or keep conservative-serialize | **R7** | `_overlap` (board.py:56, intake.py:587) only compares paths — confirmed; WCI keeps intake D2.2 conservative-serialize and defers slicing behind a §5 semantic-independence contract. **B1-symmetric (F1, §7):** the reverse hazard — `merge_after` relaxing the dep-gate on owns-disjointness — is closed by the §7 invariant (label flip is never a downgrade). |
| **B2** — depth is a PRE-SORT; **id stays the FINAL tiebreak** (don't replace lowest-id; depth isn't injective; board has no acyclicity guard) | **R5** | `board.claimable` keeps `other.id < unit.id` (board.py:234) untouched; depth only reorders `claimable_units()` (board.py:238) with id as last key |
| **B3** — move LLM-judges OFF the scheduling/land hot path; async/advisory; never gate `claimable`; preserve diffable/replayable board | **R2 / R9** | semantic pass emits annotations only; `claimable` (board.py:217) and `drain` (scheduler.py:262) stay LLM-free and deterministic |
| **B4** — relocate on-merge reconciler to the scheduler `_advance` seam (not `land.py`, a layer violation); the O(N²) static pre-filter doesn't tame cost | **R6** | hook `scheduler._advance` (scheduler.py:390), main-thread, incremental (only intersecting units); `land.py` stays a pure gate; O(N²) pre-filter dropped |
| **M1** — re-scope honestly: static reconciler is ~70% re-port of `intake.analyze` + `board.claimable` + `validate_board.sh`; only semantic dedup/contradiction is new | **R8** | confirmed overlap: `validate_board.sh` (dep/owns/dup/orphan) + `board.claimable` (owns-disjoint + lowest-id) + `intake.analyze` (overlap→serialize, intake.py:558) — MVP sized as consolidation, not new engine |
| **M3** — injection surface: untrusted ticket text/diffs to an LLM judge re-opens input-as-data (ADR-0011 D3) | **R9** | semantic pass is a fenced unit; input wrapped as data; structured advisory-only verdict; schema-validated, non-parsed input — mirrors ADR-0011 D1/D7 |

Out-of-scope (explicitly **not** unlocked by WCI): auto-decompose execution (ADR-0008 Phase 2,
conflict-rate gated), auto-land (ADR-0007 D5, gated), AIMD adaptive capacity (gated). WCI is a
*composition/ordering/advisory* layer; it does not extend trust or change who merges.

---

## 5. Open questions / risks (for the focused adversarial review to probe)

1. **Semantic-independence proof contract is undefined (highest risk).** R7 says "no concurrent
   slice without a semantic proof" but does not yet *define* that proof. Candidate signals: import
   graph reachability between sliced sub-units, shared-symbol analysis, shared-config touch, test
   co-failure. Until this contract is specified and itself reviewed, **Pillar 3 must remain
   edge-relabel + serialize-only** — auto-slicing stays parked. Is even *attempting* a definition in
   the next pass, or is Pillar 3 deferred wholesale to its own later ADR?

2. **Depth pre-sort value vs. cost.** R5's critical-path depth helps only if waves are wide enough
   that order matters and depth is cheap to compute on every `claimable_units()` call. On small
   boards it may be measurable noise. Needs a "is this worth it" measurement gate (ADR-0007 D7
   precedent: measure before committing) before ticketing Pillar 2 as more than a stable sort.

3. **Semantic pass cost / latency / determinism budget.** Even advisory, an LLM reconcile pass on
   every merge could be slow or noisy enough to be ignored (alert fatigue) or to cost real tokens
   per drain. Open: cadence (every merge? batched? only on owns/dep-intersecting merges?),
   caching by content hash, and how a *non-deterministic* advisory output coexists with a
   replayable board log (annotations must be timestamped/side-channel, not part of the replay
   state).

4. **Merge-order vs build-dependency disambiguation (the TIER7B bug).** Pillar 3's safe in-scope
   win depends on intake reliably telling these apart. It *is* a new explicit edge type
   (`depends_on` vs `merge_after`) on the unit schema. **RESOLVED by F1 (§7):** the edge ships as a
   conservative *label only* — `merge_after` is treated as a true `depends_on` for claimability
   (gate-relaxation parked with §5.1/WCI-6), so adding it does **not** ripple into a more-permissive
   `board.claimable`. The residual open question is whether the *label* alone (without the parked
   concurrency payoff) earns its schema cost in the MVP, or whether WCI-4 ships purely as an
   intake/audit annotation. See §7. **>> HELD per operator decision 2026-06-27 (§7.3): WCI-4 (label + payoff) does NOT ship in the MVP — held until §5.1 is approved; the `merge_after` schema field is not introduced in the WCI-1+WCI-2 MVP. The F1 safety result stays valid for the eventual ship. <<**

---

## 6. Proposed next step

1. **This reshape → focused adversarial review** (the trigger for writing it). Review should verify
   each B/M anchor against the cited code lines and pressure-test §5.1 (the undefined proof) and
   §5.3 (advisory-vs-replayable).
2. **If it passes:** a **thin ADR** (call it ADR-0015 — *Work-composition intelligence: reconcile +
   ordering layer*) capturing R1–R9 and the explicit out-of-scope list, slotted under ADR-0010
   (substrate) and ADR-0008/0011 (intake). Keep it small; it is a layer, not a new engine.
3. **Build-ticket breakdown sketch** (post-sign-off only):
   - **WCI-1 — `engine/reconcile.py::reconcile_static`**: consolidate `validate_board.sh` +
     `board.claimable` + `intake.analyze` checks into one deterministic function; wire as a
     pre-drain preflight. (Re-port per M1; no new intelligence.) dep: existing engine.
   - **WCI-2 — depth pre-sort** in `claimable_units()` ordering with id final tiebreak; behind the
     §5.2 measurement. (Small; rule untouched per B2.) **Determinism invariant (§7/F2):** the depth
     key MUST be a pure deterministic function of board graph state (preserves replay; depth is
     load-bearing on per-drain landing under a budget/capacity cap).
   - **WCI-3 — on-merge incremental reconcile hook** at `scheduler._advance` (intersecting units
     only). (Per B4.)
   - **WCI-4 — schema: merge-order vs build-dependency edge label** (per §5.4 + §7/F1).
     **>> HELD per operator decision 2026-06-27 — superseded for the MVP (§7.3): WCI-4 (label + payoff) does NOT ship in the MVP; it is held until §5.1 is approved. The `merge_after` schema field is NOT introduced in the MVP. The "ships as a conservative label now" plan below is retained as the eventual-ship design but does not apply to the WCI-1+WCI-2 MVP. <<**
     Ships as a **conservative label**: `merge_after` is treated as a true `depends_on` for claimability; the
     gate-relaxation (concurrency payoff) is **PARKED with WCI-6** behind the §5.1 proof. Safe to add
     now (never downgrades a build-dep); zero new concurrency until §5.1 exists. (Schema touch only.)
   - **WCI-5 — semantic advisory pass** as a fenced ACP unit over the gateway, structured
     advisory-only verdict, injection-hardened (per R3/R9). **The one genuinely-new piece** — gate
     it hardest. dep: WCI-1.
   - **WCI-6 — semantic-independence proof contract + auto-slice**: **PARKED** behind §5.1 +
     ADR-0008 Phase 2 conflict-rate tripwire. Not in this build wave.

   MVP wave = **WCI-1 + WCI-2** (+ WCI-3 if cheap). WCI-5 is the new-value spike, scoped and gated
   separately. WCI-6 stays parked.

**Gate:** operator sign-off on this reshape before any ADR or board ticket is created.

---

## 7. Reshape-fix pass (F1–F3)

The focused adversarial review of this reshape returned **REWORK** with three findings. This section
closes them. F2/F3 are folded into R5/R6 above; F1 (the real blocker) is resolved here in full.

| Fix | Severity | Where resolved | One-line resolution |
|---|---|---|---|
| **F1** | blocker | §7.1 (new invariant) + R7(c) correction + table B1 row + §5.4 + WCI-4 ticket | `merge_after` may relax the dep-gate ONLY via a positive independence certificate; a label flip on a disjoint-owns build-dep stays conservative-serialize. |
| **F2** | medium | R5 determinism invariant + WCI-2 ticket | depth sort key MUST be a pure deterministic function of board graph state; depth is load-bearing on per-drain landing under a cap (order only, never claimability). |
| **F3** | trivial | R6 prose | bogus `board.py:390` anchor removed; `_advance` lives only at `scheduler.py:390` (board.py is ~241 lines). |

### 7.1 F1 — `merge_after` safety invariant (B1-symmetric)

**The hazard the review proved.** Today two *independent* mechanisms serialize a unit pair:

- **M-dep** — the `depends_on` claim-gate: `_deps_done` (board.py:206, enforced at board.py:222)
  refuses to claim a unit until **every** `depends_on` is `DONE`.
- **M-owns** — the owns-collision gate (board.py:227–235): two units with *overlapping* `owns`
  serialize by lowest-id and never run while the other is `CLAIMED`.

A **build-dependent pair with DISJOINT `owns`** (the TIER7B↔HARD1 shape: HARD1's guard test must be
green on master before TIER7B rewrites the routing path, yet they share no files) is serialized
**only by M-dep** — M-owns cannot see it, because the paths don't overlap. The naive `merge_after`
proposal relabels that `depends_on` as `merge_after` and **relaxes M-dep** so the pair runs
concurrently, constraining only land/merge order. For a disjoint-owns pair that is the *only* gate:
both gates now open → the dependent unit builds against code not yet on the board → **silent
breakage**. This is exactly the B1 hazard (disjoint `owns` ≠ independence) **run in reverse**:
B1 = "don't *drop* a dep because owns are disjoint"; the reverse = "don't *relax the merge_after gate*
because owns are disjoint." Same fallacy, opposite direction.

This also exposed that the pre-fix R7(c) ("relabeling never invents a concurrent split") was
*self-contradictory with the feature's purpose*: the **only** way `merge_after` could fix a
false-block is **by** making the pair concurrent — i.e. by inventing a split. So either the label is
a pure no-op (fixes nothing) or it relaxes a gate (and must be proven safe). F1 makes the second
case safe and precise.

**The invariant.** Let `merge_after(A, B)` mean "B must *land/merge* after A." It may relax the
claim-gate — i.e. permit A and B to be `CLAIMED` concurrently — for the pair (A, B) **if and only if
at least one of the following holds at claim-time:**

> **(i) Proven independent.** The pair passes the §5.1 **semantic-independence proof** (import-graph
> reachability + shared-symbol + shared-config + co-failure signals — strictly *stronger* than
> owns-disjointness), **OR**
>
> **(ii) Owns-serialized anyway.** A and B have **overlapping `owns`**, so M-owns (board.py:227–235)
> already serializes them and relaxing M-dep changes nothing observable — they still cannot run
> concurrently.
>
> *Caveat (non-blocking, outside the F1 build-safety proof):* M-owns serializes an overlapping pair
> by **lowest id** (board.py:234), **not** by edge direction — so a future `merge_after(A, B)` with
> `B.id < A.id` would serialize B-before-A, **inverting** the intended merge order. This is an
> *ordering* concern, not a build-safety one (condition (ii) still makes relaxation a no-op for the
> concurrency/build-safety hazard), and it is moot in the MVP (no gate relaxation ships until §5.1).
> To be addressed when §5.1/WCI-4 lands.

**If neither (i) nor (ii) holds** — i.e. a `merge_after` is asserted (by hand-label or by intake)
between two units with **disjoint `owns`** that have **not** passed the §5.1 proof — the edge is
**conservatively demoted to a true `depends_on`**: `claimable` keeps gating it through `_deps_done`
exactly as today, yielding **serialize, not concurrent.** Concretely, the `claimable` predicate
treats a `merge_after` edge as dep-gating **unless** the pair carries an independent positive
concurrency certificate from (i) or (ii); the *label itself* is never such a certificate.

**B1-symmetric safety proof (why this closes the false-concurrency path).**

1. The dangerous path requires a pair for which **both** M-dep and M-owns end up open *without* a
   proof of independence. Enumerate how a `merge_after` edge can reach "M-dep open":
   - via **(ii)** owns-overlap → but then **M-owns is closed** (board.py:227–235 still serializes the
     pair). Both-open is impossible. ∎ for this branch.
   - via **(i)** the §5.1 proof → the pair is *certified* semantically independent, so concurrent
     execution is safe by construction (that is precisely what §5.1 must establish). Both-open is
     *intended and proven safe*. ∎ for this branch.
   - via **neither** → the edge is demoted to `depends_on`, so **M-dep stays closed**. Both-open is
     impossible. ∎ for this branch.
2. There is no fourth way for `merge_after` to open M-dep. Therefore **no pair can have both gates
   open without a positive independence certificate.** The disjoint-owns build-dep — the exact
   TIER7B↔HARD1 case — falls into the third branch and **stays serialized**.
3. **Relabel alone is never a downgrade.** Flipping `depends_on`→`merge_after` moves a pair from
   "M-dep closed" into the *third* branch (disjoint owns, no §5.1 proof) or the *second* (overlapping
   owns) — in **both** cases the pair remains serialized. To actually reach concurrency the pair must
   independently acquire a §5.1 certificate (branch i). Hence **the split is invented by the proof,
   never by the label** — which restores R7(c) as a *true* statement under a stated invariant rather
   than a bare assertion.

This is "B1-symmetric" because it applies B1's exact conservative rule — *owns-disjointness is
necessary-not-sufficient for concurrency; require a semantic proof* — to the **reverse** operation
(relaxing a gate) that the review showed `merge_after` would otherwise perform.

**MVP consequence (honest scoping).** Condition (i) depends on the §5.1 semantic-independence proof,
which is **parked** (WCI-6, ADR-0008 Phase-2 tripwire). Until §5.1 exists, (i) is never satisfiable,
so the *only* `merge_after` edges that relax the gate are condition-(ii) overlapping-owns pairs —
where relaxation is a **no-op for concurrency**. Therefore, **within the MVP, `merge_after` is
observationally identical to `depends_on` for every disjoint-owns pair: zero new concurrency, zero
false-concurrency path.** WCI-4 can ship *now* as a **safe conservative label** (it records
land-order *intent* for intake/audit/the TIER7B class of mislabel, and never downgrades a build-dep);
its **concurrency payoff is PARKED with WCI-6** behind §5.1. This is the resolution the review
permitted: not a wholesale park of WCI-4, but a park of its gate-relaxation half, with the schema
label shipping under a proven-safe invariant.
**>> SUPERSEDED for the MVP — operator decision 2026-06-27 (§7.3): WCI-4 is HELD (label + payoff) until §5.1 is approved; the `merge_after` schema field does NOT ship in the WCI-1+WCI-2 MVP. The "can ship now as a safe conservative label" finding remains a valid safety result for when WCI-4 eventually ships, but the operator chose to hold the label and its payoff so they arrive together with §5.1. <<**

**Re-review checklist for F1:**
- [ ] Invariant is stated as iff with the two positive conditions and the conservative-demote default.
- [ ] Proof enumerates all ways M-dep can open and shows both-gates-open ⇒ a §5.1 certificate exists.
- [ ] Disjoint-owns build-dep (TIER7B↔HARD1) is shown to stay serialized under a label flip.
- [ ] §5.1 is parked ⇒ MVP `merge_after` ≡ `depends_on` for disjoint-owns pairs (no new concurrency).
- [ ] `board.claimable` is not made more permissive by WCI-4 (label-only; gate-relax deferred).

### 7.2 F2 — depth pre-sort determinism (folded into R5)

Resolved in **R5** above: the depth key MUST be a **pure deterministic function of board graph
state** (unit set + edges + id tiebreak; no clock/RNG/arrival-order/iteration-order input), which
preserves replay. Acknowledged explicitly: depth is **load-bearing on per-drain launch under the
synchronous per-tier capacity cap** because `_launch_round` (scheduler.py:308) calls the capacity
limiter `try_acquire` (scheduler.py:311) **in-loop, in `claimable_units()` order**, so when that cap
binds mid-round it admits exactly the earlier-ordered prefix. Depth changes **order (and therefore
the under-cap launch prefix), never claimability** — the claimable *set* is identical; only its
truncation point under the cap moves. **Scope:** this replay guarantee covers the synchronous
`try_acquire` cap only. The concurrent `SharedBudget` gate (constructed at scheduler.py:272, threaded
to the runner at scheduler.py:354 as `cost_gate=gate`, consumed on worker threads inside
`coordinator.run`) is **not** consumed in `claimable_units()` order: under a budget cap every
claimable unit is launched and losers retry (`status=="budget"` → READY), so which units win is
thread-timing-dependent — already non-replayable pre-WCI and unaffected by depth. The
depth-determinism guarantee makes no claim about budget-race ordering.

### 7.3 F3 — bogus anchor (fixed in R6)

R6 prose previously cited `board.py:390`; `board.py` is ~241 lines and has no such line. `_advance`
exists only at **`scheduler.py:390`**. The R6 prose and the F-table above now state this. (The §4
B4 row already cited `scheduler.py:390` correctly and was left as-is.)

**Residual open question (for re-review):** does WCI-4 earn its schema cost in the MVP *given* that
its concurrency payoff is parked with §5.1/WCI-6? Options: (a) ship the conservative `merge_after`
label now for intake/audit value (records the TIER7B-class intent, never downgrades); (b) hold WCI-4
entirely until §5.1 lands so the label and its payoff arrive together. The F1 invariant makes (a)
*safe*; whether it's *worth it* pre-payoff is an operator/scoping call, not a safety question.

> **RESOLVED — operator decision 2026-06-27: HOLD WCI-4 (label + payoff) until §5.1 approved. MVP = WCI-1 + WCI-2 only. Do not introduce the `merge_after` schema field until §5.1 ships.** Option (b) chosen: the label AND its concurrency payoff arrive together once §5.1 (the semantic-independence proof) is approved. The F1 safety reasoning below/above remains valid for when WCI-4 eventually ships — it is not deleted, only marked as not shipping in the MVP.
