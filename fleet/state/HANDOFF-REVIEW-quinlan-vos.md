# Adversarial Review — SESSION-HANDOFF-quinlan-vos.md

Reviewer: adversarial read-only sub-session, 2026-07-15. Mandate: assume the handoff is flawed;
find anything that makes a FRESH next session flounder, do the wrong thing, or miss a dependency.
Grounded against live files + `validate_board.sh` (GREEN) + `launch-plan.sh` (Wave 1 = 4 launchable,
Waves 2/3 refused on deps — MATCHES the handoff exactly).

## VERDICT: FIX-NEEDED
The wave STRUCTURE is sound — board is GREEN, launch-plan reproduces the handoff's Wave 1/2/3 split,
Wave 1's four tickets are genuinely collision-free (disjoint `owns`), every EVAL ticket has a concrete
DO + FAIL-ON-REVERT citing its review §F-number, and the acceptance (a)–(g) maps 1:1 to the seven code
tickets. But there are **two HIGH self-sufficiency/dependency gaps** that will stall or mis-execute the
keystone of the whole sequence, plus several MED/LOW drifts. Not airtight; fixable in minutes.

---

## BLOCKER
(none — nothing makes the wave un-launchable; Wave 1 launches clean.)

## HIGH

### H1 — The keystone TAXONOMY-ALIGN droid cannot find the product files it must reconcile (cross-repo, unstated)
`EVAL-TAXONOMY-ALIGN` (the "everything downstream depends on this" BLOCKER, F3) tells the droid to
"Cross-check src/charon (matrix.py, taxonomy.py)". Those files **do not exist in the rig repo**
(`/home/stack/charon-private` has NO `src/charon/` tree at all). They live in a SEPARATE repo:
`/home/stack/code/charon/src/charon/routing_policy/matrix.py` and
`/home/stack/code/charon/src/charon/capability/taxonomy.py` (confirmed present there).
The review header calls them "product src/charon/…" but gives no path; the ticket drops even "product";
the handoff never names `/home/stack/code/charon` anywhere (Provenance lists "Product master: b7aa4c8"
but not the on-disk location). A fresh droid working in the rig tree runs `ls src/charon` → nothing →
either flounders or **invents a taxonomy without reading the real product router classes** — which
re-commits the exact F3 BLOCKER (grade the wrong taxonomy) this ticket exists to kill. Because every
downstream EVAL ticket keys on EVAL-TAXONOMY.md, a wrong choice here poisons the whole cascade.
**Fix:** in the handoff AND the EVAL-TAXONOMY-ALIGN ticket, state that the product router files are in
the product repo at `/home/stack/code/charon/src/charon/{routing_policy/matrix.py,capability/taxonomy.py}`
and that the droid must read them cross-repo before choosing the canonical classes.

### H2 — EVAL-DERIVED-BUDGETS has a real build-dep on LEG-PREFLIGHT-CANARY's LEG-RANK.tsv that its `depends_on` omits
DERIVED-BUDGETS' DO requires token/tok_s normalization: "derive the wall-clock ceiling per run as
tokens / the leg's measured tok_s from R0 (**LEG-RANK**)" — LEG-RANK.tsv is produced by
LEG-PREFLIGHT-CANARY, and its FAIL-ON-REVERT explicitly tests the tok_s-normalization half. Yet
`depends_on: EVAL-TAXONOMY-ALIGN` only. LEG-PREFLIGHT-CANARY is the heaviest Wave-1 ticket; if it lags,
DERIVED-BUDGETS (deps satisfied by TAXONOMY alone) becomes launchable in Wave 2 with **no LEG-RANK.tsv
to read** → the normalization half has no input and the droid either blocks or fakes it. The p95-time
half works without it, so it's a partial stall, not a full block.
**Fix:** add `LEG-PREFLIGHT-CANARY` to EVAL-DERIVED-BUDGETS `depends_on` (dep-kind: build), OR state in
the ticket that normalization degrades gracefully (emit budgets without tok_s scaling) if LEG-RANK is absent.

## MED

### M1 — LEG-PREFLIGHT-CANARY ticket points at a reference impl that does not exist
The ticket says "Reference impl: scratchpad nim-canary.py". No `nim-canary.py` exists anywhere on the
box. The real prototype is `fleet/state/leg-canary-prototype.py` (present) — which the HANDOFF names
correctly, but droids build from the TICKET, not the handoff. A droid chasing `scratchpad nim-canary.py`
wastes a cycle or reimplements from scratch.
**Fix:** correct the ticket's reference to `fleet/state/leg-canary-prototype.py`.

### M2 — "tier" is defined two incompatible ways across two different-owner tickets; handoff doesn't flag it
EVAL-TIER-CANON (Wave 2) defines tier as a **cost-band INPUT** ($/Mtok thresholds: "the COST band is the
meaningful one"). EVAL-PIPELINE-CONSOLIDATE's F9 basis states "tiers become an **OUTPUT** of the ramp"
(tier = the difficulty band where a model's per-skill ceiling lands, "resolving the conflation"). These
are owned by different droids (TIER-CANON owns tier-models.tsv/assign.py; PIPELINE owns the runner) and
run in different waves; nothing reconciles them, and validate_board explicitly warns semantic
contradiction is not machine-checked. Risk: two live notions of "tier" — the exact conflation F-tier set
out to fix.
**Fix:** handoff should call out that TIER-CANON (cost-band) and PIPELINE/F9 (ceiling-band) must agree —
declare cost-band the canonical routing axis and have PIPELINE treat difficulty-band as a secondary
annotation, or vice-versa, but pin it in EVAL-TAXONOMY/TIER-CANON.md so PIPELINE inherits it.

### M3 — Wave 3 is hard-blocked on operator action U (bench-grader pytest); "no idle" hits a wall the handoff underplays
EVAL-GRADER-PROVISION cannot reach "done" autonomously — its MUST-PASS control needs pytest that only
the operator can `sudo`-install (action U). EVAL-PIPELINE-CONSOLIDATE `depends_on` GRADER-PROVISION, and
EVAL-PROMOTION-GATE depends on PIPELINE. So the ENTIRE Wave 3 (the two biggest tickets) is gated behind
one operator sudo. The handoff flags U as "pending" but frames the run as "autonomous, no idle" without
flagging that U is on the critical path to ~half the remaining work.
**Fix:** elevate action U to "do FIRST — unblocks Wave 3"; have the GRADER-PROVISION droid write
GRADER-PROVISION-NOTE.md as its first act so the operator can provision in parallel with Wave 1.

## LOW

### L1 — F15 fold has no home in the ticket it's folded into
Handoff says "fold F15 (wire is_slow_provider) into the GRACEFUL-DEGRADE / S8 build". `GRACEFUL-DEGRADE.md`
exists but contains no F15 / is_slow / S8 mention — so the fold is verbal only and will be lost when that
ticket is built (not in this wave, so low).
**Fix:** add an F15 line to GRACEFUL-DEGRADE's accept, or a note in S8-GRACEFUL-DEGRADE-DESIGN.md.

### L2 — minor count / pending-list drift
Handoff Provenance/action says "12 commits this session"; branch is 16 ahead of origin/master (some may
predate the session — benign but inconsistent). Handoff operator-action #4 (NVIDIA NIM cleanup / Task 10)
is in prose but is NOT a labeled item in `fleet/pending.sh` (which has R/S/T/U); an autonomous session
keying off pending.sh won't see it.
**Fix:** reconcile the commit count; add Task 10 as a pending label (or state it's droid-buildable, not operator-only).

---

## Checks that PASSED (not manufacturing issues)
- **Board GREEN**, launch-plan Wave 1 = {LATENCY-GATE, TAXONOMY-ALIGN, GRADER-PROVISION, LEG-PREFLIGHT-CANARY}
  all → deepseek-v4-pro/strong; Waves 2/3 refused on the correct deps. Exactly what the handoff claims.
- **Wave 1 collision-free** — the four tickets' `owns` are disjoint (grades.py, dogfood-eval.sh reused by
  later-wave tickets only, all serial via deps; validate_board confirms historical/ok).
- **HEAD "discrepancy" is benign**: handoff records Rig HEAD `4299448` (the board commit) because the
  handoff text was written before it committed ITSELF as `f012d0d` (the current HEAD, the handoff commit).
  Normal, not stale.
- **To-be-created files are correctly dangling**: EVAL-TAXONOMY.md, GRADER-PROVISION-NOTE.md,
  PREFLIGHT-CANDIDATES.md, LEG-RANK.tsv, item-bank/, budget-derive.py etc. are all in ticket `owns` lists
  (validate_board WARN owns-path-missing = expected). leg-canary-prototype.py, PREFLIGHT-DESIGN-V2.md,
  S8-GRACEFUL-DEGRADE-DESIGN.md, CONTROLS-STATUS.md all present.
- **Each EVAL ticket faithfully captures its review §F-fix** with a real FAIL-ON-REVERT (spot-checked
  F1/F4 → LATENCY-GATE, F3 → TAXONOMY-ALIGN, F2 → GRADER-PROVISION, F6/F14 → LEG-PREFLIGHT-CANARY,
  F8 → DERIVED-BUDGETS, F-tier → TIER-CANON, F9/F12 → PIPELINE, F10/F13 → PROMOTION). No omitted fixes.
- **Operator sudo gates flagged**: bench-grader provisioning (U), push (R), funding (S) all in pending.sh
  and the handoff's Operator-actions block.

## Tacit knowledge the author has that isn't written (the "as if continuing" gap)
1. The product repo is at `/home/stack/code/charon` — the rig is `/home/stack/charon-private`; the eval
   grades a taxonomy that lives in the OTHER repo (H1). Never stated.
2. LEG-RANK.tsv is the tok_s source DERIVED-BUDGETS needs (H2) — obvious to the author, absent from the dep graph.
3. Which of the "WORKCLASS-TAXONOMY work already on master" commits is canonical (ba0f9d5 work_class,
   6b668e1 tiered taxonomy) — the droid must reconcile against these but isn't pointed at them.
