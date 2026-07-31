# REVIEW: UNIFIED-RECONCILIATION-GATE-DESIGN (PR #178)

> **Reviewer:** independent session `REVIEW-RECONCILE-GATE-DESIGN`
> **Design author:** manager session (PR #178, branch `design/unified-reconciliation-gate`)
> **Date:** 2026-07-23
> **Method:** adversarial — every claim ground-truthed against live repo at
> `/home/stack/charon-private-wt/REVIEW-RECONCILE-GATE-DESIGN` (origin/master @ 2dd78d9)
> and `/home/stack/code/charon` (product repo). No design prose accepted at face value.

---

## Verdict summary

**RECOMMENDATION: APPROVE-FOR-OPERATOR** with 2 NEEDS-REVISION items the operator must resolve
before build tickets are spawned. No BLOCKER.

---

## Item 1: Are the 3 v1 reconcilers buildable as designed?

### 1.1 board↔PR↔done (§1.1)

**CONFIRMED-SOUND** with one revision note.

**Ground truth:**
- `reconcile-merged.sh` already implements `ticket_for_pr()` at lines 127-180 with exact branch
  match as priority 1 and owns-overlap as priority 2. The two AMBIGUOUS exit paths (single-file
  multi-owner at ~:163-167, multi-file multi-owner union at ~:174-178) both return 1 (no close).
  The CREATION-PR GUARD at ~:194-222 correctly prevents false-closing on creation PRs.
- The design's ordered disambiguation ladder (branch→title→sha→manual) is a backwards-compatible
  extension to the existing AMBIGUOUS paths — buildable as a modification to `ticket_for_pr()`.
- A real AMBIGUOUS case is reproducible: any merged PR touching files `owns:`-ed by ≥2 tickets
  whose branch matches neither. The design's ladder deterministically resolves all three branches
  (R-A matched, R-B unmatched, R-C stale).

**Revision note:** The design does not specify how PR title / commit-message extraction works
for timer-based reconcile runs where `gh` context is absent. Timer cadence fires without a PR
event context; the secondary signal (title match) needs a stored PR-metadata cache or a
`done.sh` reverse index. Add a fallback plan to §1.1 or to the RECONCILE-SUBSTRATE build ticket
(#1).

### 1.2 owns-tracked (§1.2)

**CONFIRMED-SOUND.**

**Ground truth:**
- `.gitignore:10` — `fleet/state/*` IS blanket gitignored. Confirmed via `git check-ignore`
  against a hypothetical new file.
- All 33 current `fleet/state/` files ARE tracked (force-added or explicitly negated via `!`
  rules at `.gitignore:12-83`). A NEW file in `fleet/state/` would be gitignored — the exact
  R-E class the design describes.
- The design does NOT claim to auto-edit `.gitignore` — it correctly surfaces the choice.
- The durable design catalog listed in §1.2 actual-source maps to real files on disk.

### 1.3 gate-wired (§1.3)

**CONFIRMED-SOUND.**

**Ground truth:**
- `fleet/preflight.sh:841` dispatch chain IS real and accepts new checks in the pattern
  `bash "$HERE/reconcile-merged.sh"` (the existing precedent).
- `fleet/land.sh:151-161` has pre-condition guard blocks.
- Product repo `.github/workflows/ci.yml` exists and runs gates.
- Product repo `tools/check_*.py` has 12 files — the cross-repo claim is honest.
- `tools/check_reconcile_gate.py` does not exist yet (expected — it is a build ticket).
- The design correctly cross-references both repos.

---

## Item 2: Fail-closed taxonomy (F2 fix, §2.2)

**NEEDS-REVISION.** The fix is correctly identified but incompletely scoped.

**Ground truth:**
- BLAST-TIER-ENFORCEMENT-DESIGN.md §0 (lines 17-30) defines a regex-map-based tier lookup.
  It does NOT include any "unknown defaults to highest plausible tier" rule. The map is
  inherently fail-open for paths not matching any regex pattern.
- The reconciliation gate design §2.2 correctly identifies this gap and proposes the fix as
  a contract on the BLAST-TIER module. Build ticket #6 (RECONCILE-FAIL-CLOSED-TAXONOMY)
  carries this.
- **The fix is not built, not even designed in the BLAST-TIER doc** — it is a NEW requirement
  the reconciliation gate imposes. The design should be explicit that this changes the
  BLAST-TIER contract, not merely adopts existing behavior.

**Residual fail-open path found:** The design specifies tier patterns for `src/charon/`,
`docs/`, `fleet/`, `tests/`, `.github/` — but NOT for root-level files (new `Makefile`,
`Dockerfile`, `config.yaml`, `.env.example`, etc.). A root-level file matching no pattern
falls to tier 0 by default. The design should either (a) add a blanket rule "root-level
unknown = `tooling` (tier 1)" or (b) explicitly list the root-level patterns. This is a
small gap but a real fail-open class.

**Operator action before build:** Explicitly approve whether the fail-closed rule as
applied to root-level files should be `hot-path` (conservative) or `tooling` (pragmatic).

---

## Item 3: Adopt-first honesty (§4.1)

**CONFIRMED-SOUND.** The hand-rolled reconciliation logic is justified.

**Ground truth:**
- EVAL-REGISTRY.md has 22 evaluation rows for external tools plus 12 HAND-ROLL
  JUSTIFICATION ANTI-PATTERNS (AP-1 through AP-12). No EVAL-REGISTRY row claims a tool
  that reconciles "ownership boards" or "charon-specific desired-vs-actual state".
- The design defers the harness choice (ao, Windmill, etc.) to WORKLOOP-INTEGRITY-STACK-SPIKE
  (§4.2) — this is honest and avoids premature commitment.
- The drift primitives (set-diff/bidirectional, content-hash/checksum, subset/schema-conformance,
  graph-reachability, staleness-probe-TTL) are documented in KS24/KS29 references
  (`fleet/state/REGISTRY-CANDIDATES.md` cross-references KS29 extensively, e.g., lines 5, 51, 54,
  58-59, 83, 109, 122, 135, 200-211). These ARE registered, not invented for this design.
- The stass-allie WLS-7 validation claim is NOT directly verifiable from repo contents (the
  handoff docs exist but the WLS-7 artifact itself is not in-tree). Mark this claim
  **unverifiable from repo** — the reviewer trusts the author's representation. If this is a
  concern, the operator should confirm WLS-7 finding independently.

---

## Item 4: Deferred/parked correctness (§2.3, §5)

### 4.1 Grading consumer (Consumer B) — PARKED

**CONFIRMED-SOUND** with one observation.

**Ground truth:**
- `fleet/capability/grades.py` EXISTS (770 lines, fully implemented). It reads from
  `fleet/model-scorecard.tsv` via `ScorecardGradesProvider.grade()` (line 658-713).
- `fleet/model-scorecard.tsv` DOES NOT EXIST (gitignored per `.gitignore` rule, not
  generated). So `grades.py` returns 0 real-outcome grades in practice.
- The design's claim "grades.py returns 0 real-outcome grades for all 6 models" is
  CORRECT — the code exists but the data is absent.
- The review-gate axis (§2.1) operates on review-log markers (`docs/review-log/<id>.md`
  + `fleet/state/reviewed/<id>`), NOT on grades. v1 does not depend on grades.py.

**Observation for operator:** `grades.py` is NOT "empty" — it is a built, tested consumer
waiting on data capture. The distinction matters for scheduling: if the scorecard-capture
pipeline were repaired, grades.py would immediately produce real grades without code changes.
The design's "parked" framing is slightly imprecise — the CODE is done, the DATA is parked.
This is a minor wording note, not a correctness issue.

### 4.2 R44 e2e-observable-effects — DEFERRED (§5)

**CONFIRMED-SOUND.** v1 reconcilers check structural drift (merged/owned/wired/reviewed).
None of the RED conditions (R-A through R-L) require proving a feature is exercised at
runtime. The deferral is sound.

---

## Item 5: Enforcement gaps (§3.3)

### 5.1 `git -C` land.sh bypass

**CONFIRMED-SOUND.** The bypass IS flagged, not fake-closed.

**Ground truth:**
- The `git -C` push bypass is ALREADY CLOSED (`Bash(git -C * push*)` denied in
  `settings.local.json` per PUSH-GUARD-GITC-HARDEN.md.parked reconciled-state note).
- Remaining `git -C <path>` destructive ops (reset, rebase, amend, remote add) ARE NOT
  denied — tracked as parked ticket `PUSH-GUARD-GITC-HARDEN.md.parked`.
- The design §3.3 correctly describes the seam and says "do NOT pretend land.sh is a
  closed gate on the rig until the Gitea migration lands." This matches reality.
- The design proposes flagging in GATE-GAP-LEDGER; currently the gap lives in the parked
  ticket, not the ledger. Minor tracking-location difference — not a substantive issue.

### 5.2 Is timer enforcement wireable today?

**NEEDS-REVISION.** No timer infrastructure exists in the fleet today.

**Ground truth:**
- preflight.sh dispatch: YES, wireable today (line 841 chain).
- land.sh pre-conditions: YES, wireable today (lines 151-161 pattern).
- **Timer (cadence check): NO.** No cron, systemd timer, or foreman heartbeat infrastructure
  exists in the fleet. `fleet/foreman.sh` exists but is report-only advisory
  (preflight.sh:722-732), not a timer runner. The design proposes building
  `fleet/checks/reconcile-timer.sh` but leaves the scheduling mechanism unspecified.
- The design acknowledges this (§3.1 "timer (cadence check)" as a build item). The question
  "is it wireable today" has a partial answer: preflight+land.sh yes, timer no.

**Operator action:** Accept the timer mechanism as a new build dependency (e.g., RECONCILE-WIRING
ticket #7 must include scheduling infrastructure), or explicitly accept that v1 has only
preflight+land.sh enforcement.

---

## Item 6: Blast radius / completeness (§6)

### 6.1 Build backlog decomposition

**CONFIRMED-SOUND.** The 8-ticket decomposition is clean and one-lens-per-reconciler.

**Ground truth:**
- Each ticket covers exactly one concern: substrate, board-PR-done, owns-tracked, gate-wired,
  review-gate, fail-closed-taxonomy, wiring, dogfood.
- Sequence dependencies are stated: #1 (substrate) blocks #2-4; #5-6 depend on BLAST-TIER module.
- No missing reconciler class found. The "norm-exists-but-unenforced" class (EVAL-REGISTRY #61)
  is addressed by the folded review-gate axis (§2.1 → build ticket #5).

**Minor note:** The design frames §1 as "3 cheap, high-value reconcilers" then folds in
review-gate (§2.1) and fail-closed-taxonomy (§2.2) as additional build tickets (#5, #6).
Effectively v1 has 5 reconcilers/axes, not 3. The framing is slightly misleading — but the
content is transparently listed, so this is not a substantive issue.

### 6.2 Internal contradictions

**CONFIRMED-SOUND.** No contradictions found.

- The gitignore self-referencing (design doc itself is `fleet/state/*` gitignored) is correctly
  acknowledged and called out as the R-E test fixture. Self-consistent.
- The design says reconcilers are "one row in a registry" but the registry doesn't exist yet
  (#1). Sequence dependency is stated — consistent.
- The design says it "must run on itself" (§4.3 KS20) and creates a dedicated dogfood ticket (#8).
  Consistent.

---

## Overall verdict

**APPROVE-FOR-OPERATOR**

| Item | Verdict |
|------|---------|
| 1. Three v1 reconcilers buildable | CONFIRMED-SOUND (1 revision: timer-context PR title extraction) |
| 2. Fail-closed taxonomy | NEEDS-REVISION (root-level unknown path gap) |
| 3. Adopt-first honesty | CONFIRMED-SOUND (1 claim unverifiable from repo: WLS-7 validation artifact) |
| 4. Deferred/parked correctness | CONFIRMED-SOUND |
| 5. Enforcement gaps | CONFIRMED-SOUND (1 revision: timer not wireable today) |
| 6. Completeness | CONFIRMED-SOUND |

**Two NEEDS-REVISION items the operator must resolve:**

1. **Root-level unknown path fail-open (§2.2):** Approve whether a root-level file
   matching no tier pattern defaults to `hot-path` (conservative) or `tooling` (pragmatic).
   Update the design §2.2 or the BLAST-TIER contract accordingly before build tickets are
   spawned.

2. **Timer enforcement not wireable today (§3.1/§5):** Accept that v1 has preflight+land.sh
   only (no timer), or add scheduling infrastructure as a dependency of RECONCILE-WIRING (#7).
   Document the decision in the design §3 before build.

**Unverified claim (trust but flag):** WLS-7 validation artifact not found in repo — the
claim that stass-allie WLS-7 validated the implement-as-pattern posture is unverifiable
from tree contents. Operator should confirm WLS-7 finding independently if this is critical.

No BLOCKER. Proceed to build ticket spawning after resolving the two revisions.
