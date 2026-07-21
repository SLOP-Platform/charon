# BLOCKER BLAST-RADIUS AUDIT — Charon fleet board
Generated 2026-07-21 (read-only). Supersedes `fleet/state/WORK-REORG-PROPOSAL.md` (2026-07-15/16, now stale).
Evidence: `fleet/validate_board.sh` (dep graph + owns), `fleet/board/*.md` dep fields, `fleet/state/{done,submitted,loop-guard}/`,
`gh pr list` (rig Nnyan/charon-private + product SLOP-Platform/charon), `git ls-files`, `git log origin/master`.
No board mutation, no PR/land actions taken — PROPOSE ONLY.

State legend used below: DONE-MERGED (PR merged, ticket still live on board) · PR-OPEN (draft/open PR, built not merged) ·
UNBUILT (no branch/PR, owned file absent) · PARKED.

---

## RECOMMENDED UNBLOCK SEQUENCE (do these 5, in order — frees the most work fastest)

| # | Move | Effort | Frees / Effect |
|---|---|---|---|
| 1 | **Retire the 20 already-done-but-open tickets** (§2) — merged PRs still sitting live on the board | XS (bookkeeping) | Closes ~20 tickets; board finally reflects reality so the 3 real blockers are visible. Biggest cleanup win. |
| 2 | **Merge FT-CATALOG-SEED (product #135)** — non-draft, mergeable, contract-test sibling #148 already merged | XS | Unblocks FT-WIRE-QUOTA → METER-KWH-USD-FIX (2 tickets). |
| 3 | **Build GW-BRIDGE-1-DOWNGRADE-REHOST** — parked:false, ZERO deps, buildable now | M | Unblocks the entire litellm.Router adopt chain: GW-BRIDGE-2/3/4, GW-CUTOVER-LIVE-WIRE, GATEWAY-GRADE-ORDER-MVP (5 tickets). Highest blast radius on the board. |
| 4 | **Build SEMGREP-CI-REQUIRED-CHECK** — ZERO deps, buildable now | S–M | Unblocks the SAST chain: BANDIT-ADOPT, GITLEAKS-ADOPT, VULTURE-INVESTIGATE-RETIRE-INERT (3 tickets). |
| 5 | **Reconcile BENCH-OOB-GRADING scope vs merged EVAL-\*** — a review, not a build | S (review) | Resolves/retires the grader chain: GRADER-SECFIX-RECONCILE, MODEL-PREFLIGHT, MARKER-PROOF-MECHANIZE, FINAL-E2E-REVIEW (4 tickets). Much of BENCH-OOB's intent already shipped as EVAL-PIPELINE-CONSOLIDATE/GRADER-PROVISION/TAXONOMY-ALIGN. |

Bonus batch (not sequenced): the **8 rig draft PRs** (#93/#95/#96/#97/#105/#114/#116/#119) are built-but-draft — a review-and-merge sweep if CI-green (see §3).

---

## 1. BLOCKER BLAST-RADIUS RANKING

Blast radius = count of transitive downstream board tickets waiting on this blocker (dep targets already merged/done are pruned).

| Rank | Blocker | State | #downstream | Frees (transitive) |
|---|---|---|---|---|
| 1 | **GW-BRIDGE-1-DOWNGRADE-REHOST** | UNBUILT (parked:false, 0 deps — buildable now) | **5** | GW-BRIDGE-2-METERING-SPEND, GW-BRIDGE-3-STREAMING-SSE, GW-BRIDGE-4-PARK-COOLDOWN, GW-CUTOVER-LIVE-WIRE, GATEWAY-GRADE-ORDER-MVP |
| 2 | **BENCH-OOB-GRADING** | PARKED | **4** | GRADER-SECFIX-RECONCILE, MODEL-PREFLIGHT, MARKER-PROOF-MECHANIZE, FINAL-E2E-REVIEW (via MODEL-PREFLIGHT) |
| 3 | **SEMGREP-CI-REQUIRED-CHECK** | UNBUILT (0 deps — buildable now) | **3** | BANDIT-ADOPT, GITLEAKS-ADOPT, VULTURE-INVESTIGATE-RETIRE-INERT |
| 4 | **REPO-FIELD-REQUIRED** | UNBUILT | 2 | REPO-MAP-CONVERGE → MARKER-PROOF-MECHANIZE |
| 4 | **REPO-DECL-CENTRAL** | UNBUILT | 2 | REPO-MAP-CONVERGE → MARKER-PROOF-MECHANIZE |
| 4 | **GH-SEAM-CHOKEPOINT** | UNBUILT | 2 | REPO-MAP-CONVERGE → MARKER-PROOF-MECHANIZE |
| 4 | **FT-CATALOG-SEED** | PR-OPEN (product #135, mergeable) | 2 | FT-WIRE-QUOTA → METER-KWH-USD-FIX |
| 8 | **GW-CUTOVER-LIVE-WIRE** | UNBUILT (blocked by bridges) | 1 | GATEWAY-GRADE-ORDER-MVP |
| 8 | **FT-WIRE-QUOTA** | PARKED | 1 | METER-KWH-USD-FIX |
| 8 | **PROJECT-MEMBERSHIP-GATE** | UNBUILT (membership logic absent in validate_board.sh — verified) | 1 | CREATION-GATE-DECOMPOSE-WIRE |
| 8 | **REPO-MAP-CONVERGE** | UNBUILT | 1 | MARKER-PROOF-MECHANIZE |
| 8 | **DONE-SH-INTEGRITY-FIX** | UNBUILT | 1 | MARKER-PROOF-MECHANIZE |
| 8 | **CAPABILITY-ACTUALS-DEADREF-CLEANUP** | PR-OPEN (product #164 draft) | 1 | INERT-INSTANCE-DETECT |
| 8 | **REACHABILITY-GATE** | PR-OPEN (rig #96 draft) | 1 | REACHABILITY-AUDIT-LAND |
| 8 | **PRODUCT-GRADES-STORE** | PARKED | 1 | WIRE-BRAIN-INTO-GATEWAY |
| 8 | **SESSION-END-PUSH-GATE** | DONE-MERGED (#130) — dep already satisfied | (1) | WIP-CLOSE-GATE is effectively unblocked; retire this blocker |

Notes:
- GW-BRIDGE-1 is the single highest lever: it is *not itself blocked* (0 deps, parked:false), yet 5 tickets sit behind it. Building it is pure forward progress.
- MODEL-PREFLIGHT is `superseded_by: EVAL-PIPELINE-CONSOLIDATE/GRADER-PROVISION/DERIVED-BUDGETS` (all merged) and shows Done in report.sh roadmap — its code moved to the EVAL-\* successors. FINAL-E2E-REVIEW's dep on it is satisfiable by repointing at the EVAL-\* successors; folded into move #5.
- MARKER-PROOF-MECHANIZE sits behind a long rig-hygiene chain (DONE-SH-INTEGRITY-FIX + REPO-MAP-CONVERGE + BENCH-OOB-GRADING). Its deps FOREMAN-WIRE & GITHUB-LIMITS-HARDENING are already merged.

---

## 2. ALREADY-DONE-BUT-OPEN (supersession sweep) — 20 ticket-close candidates

Method mirrors the RIG-CI-GATE / 4-rig-branch find: PR merged on master but board `.md` still live. `(DM)` = also has a stale `state/done/` marker.

| Ticket | Evidence (PR / repo) | Confidence |
|---|---|---|
| RIG-CI-GATE | rig #121 merged (cf07e05) "first-ever CI gate for the rig" | HIGH |
| SESSION-END-PUSH-GATE | rig #130 merged (5ab316e, rebuild of #62) | HIGH |
| GITHUB-LIMITS-HARDENING | rig #129 merged (68efdef, rebuild of #101) | HIGH |
| SYNC-SCHEDULE | rig #128 merged (c792601) | HIGH |
| DROID-LIFECYCLE-REAP | rig #126 merged (0314d5d, rebuild of #103) | HIGH |
| FOREMAN-MULTI-TRIGGER | rig #106 merged | HIGH |
| TSV-APPEND-UNIFY | rig #99 merged | HIGH |
| ON-DEMAND-TOOL-AUDIT | rig #98 merged | HIGH |
| STALE-CHECK-SH | rig #94 merged | HIGH |
| LAUNCH-PLAN-SH | rig #92 merged | HIGH |
| BENCH-PROVISIONAL-SCORING | rig #107 merged (3714307) | HIGH |
| GRAPHIFY-MAP-FRESHNESS | rig #102 merged (DM) | HIGH |
| SALVAGE-STASH-CHARON-RUN | rig #83 merged (DM) | HIGH |
| ENV-REGISTRY-WIRE | rig #87 merged (DM) | HIGH |
| FOREMAN-WIRE | rig #86 merged (DM) | HIGH |
| EVAL-TAXONOMY-ALIGN | rig #63 merged (DM) | HIGH |
| REVIEWER-DOGFOOD-REDS | rig #65 merged (DM) | HIGH |
| DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD | product #168 merged | HIGH |
| GATEWAY-NONTOKEN-METERING | product #167 merged "non-token metering (rebuilt w/ #165)" | HIGH |
| METER-DOC-RECONCILE | product #174 merged "reconcile per-(model,provider) meter docs with live wiring" | MED |

6 of these (marked DM) carry a `state/done/` marker yet remain live board `.md` files — the clearest retire set.
**Count = 20 already-done-but-open candidates (19 HIGH, 1 MED).**

Explicitly NOT already-done (submitted marker is stale, work never landed — keep as real work):
- **PRICE-REFRESHER** — submitted marker 2026-07-16 but `src/charon/routing_policy/price_refresher.py` absent on master (rig + product); no merged PR. UNBUILT. (Its dependent DELETE-STATIC-RANK merged anyway as product #152 — dep effectively dropped.)
- **PROJECT-MEMBERSHIP-GATE** — submitted, but validate_board.sh has no membership/ROADMAP-fold logic (grep-verified). UNBUILT.
- **ADR0016-DEPLOY-PRICED-COMPLETENESS** — `tests/test_priced_completeness.py` absent. UNBUILT.
- **API-DECOMPOSE-CYCLE-FIX** — quarantined in `state/loop-guard/`, no fix commit on master. UNBUILT.

---

## 3. LOW-HANGING FRUIT

| Ticket | State | What's left | Effort | Why now |
|---|---|---|---|---|
| **FT-CATALOG-SEED** | product #135, **non-draft**, mergeable | review + merge | XS | Contract-test sibling #148 already merged; unblocks FT-WIRE-QUOTA → METER-KWH-USD-FIX. |
| **20 already-done-but-open (§2)** | merged, board still live | run retire/reconcile-merged sweep | XS | Board bookkeeping; ~20 tickets closed, real blockers become visible. |
| **LAND-SH-POSTMORTEM** | rig #47, **non-draft**, open | review + merge | XS | Process-safety adversarial audit already built; oldest open PR. |
| **SEMGREP-CI-REQUIRED-CHECK** | UNBUILT, 0 deps | build the gate + canary | S–M | Small unblocked ticket, outsized value: frees BANDIT + GITLEAKS + VULTURE (blast radius 3). |
| **8 rig draft PRs** (batch) | #93 PRICING-LIMITS-CHECK-SH, #95 WORK-GATE-UNIVERSAL, #96 REACHABILITY-GATE, #97 SSOT-DRIFT-GATE, #105 ASSIGN-DISPATCH-PICK-FIX, #114 HANDOFF-ROOT-ARCHIVE, #116 FT-LIMITS-GROQ-RECONCILE, #119 CAPTURE-WIRING-TIMEOUT-FIX | mark-ready + merge if CI-green (each has a hold-reason — verify first) | S each | All built and sitting as drafts; a green-CI review sweep converts built work into landed work. |
| **5 product draft PRs** | #172 GRACEFUL-DEGRADE, #169 CHARON-FLOWCHART, #164 CAPABILITY-ACTUALS-DEADREF-CLEANUP, #161 WEB-ROADMAP-GENERATOR | review + merge if green | S each | Same class on product side; #164 also unblocks INERT-INSTANCE-DETECT. |

---

## Appendix — dep edges already satisfied (dep target merged/done), so NOT blockers
CAPTURE-WIRING-TIMEOUT-FIX←SALVAGE(done) · GATEWAY-NONTOKEN-METERING←PROVIDER-PROBE-FIX(done) · GRACEFUL-DEGRADE←ROUTER-CORE(done) ·
GITHUB-LIMITS-HARDENING/REPO-DECL-CENTRAL/REPO-FIELD-REQUIRED←VERIFY-MERGED(done) · SSOT-DRIFT-GATE←EVAL-TAXONOMY-ALIGN(done) ·
SYNC-SCHEDULE←STARTUP-CONTEXT-DIET+FOREMAN-WIRE(done) · PROJECT-MEMBERSHIP-GATE←DIFFICULTY-SCHEMA(done) ·
LAUNCHER-CRASH-PARTIAL-DETECT←DROID-LIFECYCLE-REAP(merged) · WIP-CLOSE-GATE←SESSION-END-PUSH-GATE(merged) ·
FT-WIRE-QUOTA: 5 of 7 deps done (FT-QUOTA-ENGINE, FT-CONFIG-SURFACE, FAIL-LOUD-CONTRACT, FORWARDER-RECONCILE, PROVIDER-PROBE-FIX, +GATEWAY-NONTOKEN-METERING merged) — only FT-CATALOG-SEED (#135) remains.
