# BLAST-TIER-ENFORCEMENT — design (2026-07-23, manager-authored for operator review)

> Deliverable for `BLAST-TIER-ENFORCEMENT-DESIGN` (P:1). DESIGN ONLY — spawns one-lens build tickets
> on operator approval; nothing here is built yet. Root fix for the recurring class this session kept
> hitting: **a norm/ADOPT-decision exists but nothing ENFORCES it, so it fires only when the operator
> asks** (adversarial review of hot-path code; adopt-first; hands-on trials). The cure is one shared
> **blast-tier** signal that three consumers read. Circularity + high blast → design-first.

## 0. The one shared substrate: `blast_tier(change) -> tier`

A single, machine-derivable classifier — ONE home, consumed by the gate AND the grader (the mistake
EVAL-TAXONOMY-ALIGN fixed was two copies of a taxonomy drifting; do not repeat it).

**Home:** `src/charon/blast_tier.py` (product owns it because product code — forwarder/proxy/balance —
is the highest tier; the rig imports the same module via `PYTHONPATH=src`, never a copy).

**Ordered tiers (low→high), with the review threshold at `hot-path`:**

| tier | rank | what it is | derived from |
|---|---|---|---|
| `doc` | 0 | markdown, notes, ADRs | `*.md`, `docs/`, session-notes |
| `tooling` | 1 | rig scripts, CI, tests, board | `fleet/*.sh`, `.github/`, `tests/` |
| `hot-path` | 2 | request/routing core | `src/charon/{forwarder,proxy_server,api,router,capability}*.py` |
| `money-path` | 3 | spend/balance/metering | `src/charon/{balance,meter,billing}*.py`; `work_class: money-path` |
| `security` | 4 | egress, keys, auth, ACLs | `src/charon/{egress,keys,secret,acl}*`; `security`-tagged |

**Rule:** `tier = max(path-pattern tier, work_class tier)` over all files in the change. `owns`-count
(`blast`, already computed in claim.sh) is a *severity multiplier within a tier*, not the tier itself.
Everything is a table lookup + a regex map living in ONE dict in `blast_tier.py`; no hand-maintained
per-file list. Threshold for mandatory review: **tier ≥ 2 (`hot-path`)**.

## 1. Consumer A — mandatory adversarial-review gate (executes EVAL-REGISTRY #61)

Registry #61 already ADOPTED "independent adversarial verification as a CI required-check" (2026-07-21)
and it was never built. This wires it, scoped by blast-tier.

**What's required:** a change with `blast_tier ≥ hot-path` MUST carry a recorded, independent adversarial
review of its head SHA before it can land/merge. No record → **BLOCK**.

**The record** (`docs/review-log/<id>.md` + a machine line, or `fleet/state/reviewed/<id>`):
`reviewed_sha=<sha>  author_model=<m>  reviewer=<operator|model-id>  verdict=<CONFIRMED-CLEAN|FIXES|BLOCK>  findings=<n>`

**"Independent" in a one-operator + droids fleet** (the hard question): the reviewer MUST NOT be the
author. Enforce `reviewer != author_model` (never self-review) OR `reviewer = operator`. A model may
review another model's high-blast work only if the reviewer model is itself *proven at that blast-tier*
(consumer C) — otherwise the review is required from the operator or the manager. This is the
bootstrapping answer to the circularity (§3).

**Enforcement (two gates, because GitHub native required-reviews is 403/paywalled on the private rig —
verified):**
- **land.sh pre-condition:** refuse to merge a `≥hot-path` branch whose head SHA has no matching review
  record. (Same shape as the AUTONOMOUS lever + gate refusal already in land.sh.)
- **CI required-check** (`rig-ci.yml` + product `ci.yml`): re-verify the record exists for the merged
  SHA, so a "green" without a review cannot land even outside land.sh.
- **Public product repo ONLY:** additionally use native branch-protection + CODEOWNERS (free on public)
  as defense-in-depth. Private rig relies on the marker+check.
- Reuse `ReviewerCircuitBreaker` (`src/charon/failover.py:73-142`) so a review→fix→review doom-loop
  TRIPS (fingerprint the approach, not the args) instead of looping.

**Adopt-first consult (recorded, AP-12/hand-roll-never-default apply):** GitHub required-reviews =
adopt on public, unavailable on private (paywall). CODEOWNERS = adopt on public. Danger = already
REJECTED (registry: redundant with Semgrep+gates). The marker+check is the ~novel thin slice the paywall
forces on the private rig — NOT a hand-roll of what a tool offers. Land the EVAL-REGISTRY rows before build.

## 2. Consumer B — multi-axis real-outcome grade + blast-tier routing

**Finding (built-but-not-captured):** the scorecard schema is already 16 cols
(`… score · time_s · cost_usd · corrections · note · tokens_in · tokens_out · stage`) but every live row
writes `MERGE/pass/100` and leaves `time_s/cost_usd/corrections/tokens = -`. So detail is a CAPTURE gap,
not a schema gap.

**(a) Populate what exists** — `done.sh` (final), `charon-run.sh` (provisional; it already knows
first→last model, latency, exit), and a NEW `reject.sh` capture path (today reject.sh writes NOTHING —
a bounce leaves zero grading signal, the exact gap behind this whole thread).

**(b) Add the axes a scalar score hides** (structured tags — prefer new trailing columns over overloading
`note`, since the schema already grows and grades.py fail-opens legacy rows):
- `fail_class` ∈ {correctness, method (ignored the brief), false-success, latency}
- `blast_tier` of the work (from §0)
- `defect_severity` (from review findings)
- `trust_of_green` — did the model's PASS SURVIVE adversarial review. **The single most routing-critical
  axis** — a PASS that review overturned is worse than an honest BLOCK. Produced directly by consumer A.

**(c) Grade PER (model, work_class, blast_tier)**, not per (model, work_class). Keep grades.py's Wilson
lower-bound smoothing — feed it richer, tier-partitioned inputs. A model's high score on `doc` work says
NOTHING about its `hot-path` trust.

**(d) assign.py blast-tier eligibility filter** (new step before the score sort): a model is eligible for
a ticket of `blast_tier T` only if it has ≥N clean, **review-survived** samples at tier ≥ T (positive
Wilson lower-bound on the tier-partitioned grade). Below that → EXCLUDED, fail-closed (matches the
existing "tier unknown → excluded" rule). So a model that shipped a silent hot-path bug can still be
routed to docs, never to `claim.sh`/money-path until it earns it.

**(e) Dual-ledger on "passed the gate but review caught a bug":** feed BOTH — a model trust ding
(false-success/trust_of_green) AND a **gate-blindness finding** (the automated gate is blind to that
defect class → a coverage backlog telling us which check to strengthen). PRIORITY-CONSOLIDATION's
blocking-overcount passed `validate_board` GREEN — that's a `validate_board` blind-spot, logged.

## 3. Circularity (a grade substrate graded/routed by itself)

- The blast-tier design + build is **operator/manager work**, not model-graded auto-routed work.
- Grading-substrate tickets are themselves top blast-tier → require review (consumer A) AND are excluded
  from auto-routing to unproven models (consumer B's filter, applied to itself).
- **Bootstrap:** until any model has review-survived high-blast samples, ALL `≥hot-path` work routes to
  the operator/manager or the single most-proven model, reviewed independently. The system earns trust
  outward from low blast, never assumes it.

## 4. Backfill THIS session's two real outcomes (with the axes, not scalars)

| ticket | model | verdict | fail_class | blast_tier | trust_of_green | note |
|---|---|---|---|---|---|---|
| WORKLOOP-attempt-1 | minimax-m3-free | BLOCK | method + false-success | doc | n/a (bounced) | source-only (AP-12), hand-roll-default 3/4; self-reported done |
| PRIORITY-CONSOLIDATION | minimax-m3-free | FIXES | correctness + false-success | **hot-path** (claim.sh) | **FAILED** — passed validate_board, review caught blocking-overcount | landed after manager review-fix |

Signal: minimax-m3-free = **not trusted at hot-path** (1 silent hot-path bug + 1 method bounce, both
self-reported SUCCESS). Fine for `doc`/`tooling` until it earns higher tiers.

## 5. Build decomposition (one-lens tickets, spawned on approval — sequence)

1. `BLAST-TIER-MODULE` — `src/charon/blast_tier.py` + tests (the shared substrate; blocks the rest).
2. `REVIEW-GATE-MARKER` — record format + land.sh pre-condition + rig/product CI required-check + circuit-breaker reuse.
3. `SCORECARD-CAPTURE-POPULATE` — done.sh/charon-run.sh/reject.sh write the already-modeled columns.
4. `GRADE-MULTI-AXIS` — fail_class/blast_tier/defect/trust_of_green columns + grade-per-blast-tier in grades.py.
5. `ASSIGN-BLAST-TIER-ROUTE` — assign.py eligibility filter.
6. `GRADE-BACKFILL` — the two rows above, via the new capture paths (after 3–4 exist).

Each carries its own EVAL-REGISTRY consult + adversarial review (dogfooding consumer A). Do NOT mass-build.
```
```
