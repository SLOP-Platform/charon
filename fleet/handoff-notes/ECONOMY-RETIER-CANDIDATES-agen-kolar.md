# Economy re-tier candidates — analysis only (agen-kolar, 2026-07-24)

**Scope:** find live `strong`+ tickets that are genuinely economy-sized. **Read-only.** No board file,
ticket, or ROADMAP row was touched. This is a proposal for the board owner to apply (or not).

**Method:** `fleet/board.sh` for tier+state; per-ticket `tier:/difficulty:/work_class:/owns:` scan
across all 100 strong-tier + 6 frontier board files; `fleet/claim.sh --dry-run` probes for
claimability facts; diff of `origin/master...origin/feat/tier-classifier` for the unlanded re-tiers.

---

## 0. Claimability facts (measured, not assumed)

`fleet/claim.sh` tier rule: a droid claims at-or-below its tier. So **only a READY (claimable)
ticket's tier change moves the economy depth today** — re-tiering a `PR-OPEN` or `blocked` ticket
changes nothing an economy tab can pick up.

READY tickets right now (11 total):

| id | tier | note |
|---|---|---|
| 4LOM-CANARY-SERVICE | strong | d3, owns=4 |
| CENTRAL-WORK-ROUTING-HUB | frontier | d5 |
| **CONTRIBUTING-HOOK-INSTALL-FIX** | **economy** | d1, owns=CONTRIBUTING.md — **untracked/new**, created by the board owner concurrently |
| DROID-BRIDGE-REGISTER | strong | d3 |
| FIX-PROVIDER-KEY-EXFIL | strong | d2, **security** |
| FORGE-PRIMARY-GITEA | strong | d4, owns=7 |
| GATE-REENTRANCY-GUARD | strong | d3, **gate logic** |
| GITEA-ACTIONS-CI-SPIKE | strong | d3, `parked: true`, spike |
| LENS-REGISTRY-AND-REPORT | strong | d3, owns=3 |
| **LITELLM-CI-DEPS** | strong | **d1, owns=1** |
| STRANDED-WORK-AUDIT | strong | d3, owns=2 |

`claim.sh --dry-run economy` now returns **CLAIMED CONTRIBUTING-HOOK-INSTALL-FIX** — i.e. economy
depth is **already 1, not 0**, as of the board owner's in-flight (uncommitted) ticket. The starve
reported at task start is being fixed by the board owner independently of any re-tier.

---

## 1. Candidate table

**Genuine candidates: 1.**

| ticket | current | proposed | owns: size | difficulty | one-line justification |
|---|---|---|---|---|---|
| `LITELLM-CI-DEPS` | strong | **economy** | 1 (`.github/workflows/ci.yml`) | 1 | Add the `[router]` extra to one CI install step; acceptance is a named, countable fact (16 enumerated tests un-skip and pass), the diff is one line in one file, and any error is loud (CI red) rather than silent. |

**Guardrail if applied:** the `owns:` is exactly `.github/workflows/ci.yml`. Any diff outside that
one file — especially touching `pyproject.toml` to make litellm a core dep, or "fixing" a test that
un-skips into a failure — is an automatic reject. State that in the brief.

**Caveat, stated plainly:** this is CI-gate *configuration*, adjacent to the gate/enforcement
exclusion. It clears the bar because it changes what the gate *installs*, not what the gate
*enforces*, and it strictly *increases* coverage (16 previously-importorskip-skipped litellm-plane
tests start running). It is also already economy under the mechanized rubric on
`feat/tier-classifier` — proposing it is agreement with a landed-pending rule, not a novel call.
If the board owner wants zero tolerance on anything touching `ci.yml`, dropping this candidate
leaves **zero** and that is a defensible position.

---

## 2. Considered and rejected

### Hard exclusions (never economy)

| ticket | tier | why rejected |
|---|---|---|
| FIX-PROVIDER-KEY-EXFIL | strong, READY | security surface (provider key exfil). The classifier UP-tiers this to `frontier`; agreed. |
| BANDIT-PREEXISTING-FINDINGS | strong, d2 | security findings triage. |
| GATE-REENTRANCY-GUARD | strong, READY, d3 | gate/enforcement logic + fork-bomb class. Strongest scrutiny. |
| SESSION-END-PUSH-GATE / HANDOFF-GATE-NONBYPASSABLE / META-GATE-FINDINGS-ZERO / WIP-CLOSE-GATE / WORK-GATE-UNIVERSAL / SSOT-DRIFT-GATE / REACHABILITY-GATE | strong | gate/enforcement logic. |
| LOOP-GUARD-INFRA-FAULT-EXEMPT | strong, d2 | loop-guard = enforcement; an exemption rule is exactly where a cheap model widens the hole. |
| GATEWAY-NONTOKEN-METERING, DEGRADE-ALERT, PRICING-LIMITS-CHECK-SH, INVENTORY-TABLE-SHARE, PRICE-REFRESHER, ORDER-A-COST-PRIMARY-LAND, PEAK-PRICING-AWARE, FT-WIRE-QUOTA, GW-CUTOVER-LIVE-WIRE, SINGLE-LEG-AUTOSWAP, WIRE-GRADING-PRIOR-LIVE, DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD, ADR0016-DEPLOY-PRICED-COMPLETENESS, ADD-PROVIDER-MECHANIZE-COMPLETE, DISCOVERY-PIPELINE, FLOW-CANARY-FIX-FREEFIRST | strong, d2–5 | money path (cost/spend/routing/provider selection). Excluded regardless of difficulty. |
| REAPER-APPLY-WIRING, DROID-LIFECYCLE-REAP, LAUNCHER-CRASH-PARTIAL-DETECT, WORK-LEASE-WORKTREE-RESOLVE | strong | data-loss surface (a bad reaper deletes committed work). Money-adjacent by the rig's own note. |
| BLAST-TIER-ENFORCEMENT-DESIGN, UNIFIED-RECONCILIATION-GATE-DESIGN, REVIEW-RECONCILE-GATE-DESIGN, MERGE-QUEUE-EVAL, REVIEW-WORKLOOP-ATTEMPT3, WORKLOOP-INTEGRITY-STACK-SPIKE, PRICE-TRACKED-INVENTORY-AUTOSWAP, SUBAGENT-WORKTREE-SANDBOX | strong | `design-review` — the deliverable IS judgement; acceptance is prose by construction. |
| BOARD-REDS-TRIAGE, LAND-SH-POSTMORTEM, STRANDED-WORK-AUDIT | strong | triage/postmortem/detector-design — requires judgement about what counts as a red, and STRANDED's acceptance is a five-shape contract with never-false-green semantics. |
| GITEA-ACTIONS-CI-SPIKE | strong, READY | `parked: true`; a spike whose deliverable is a PASS/FAIL *recommendation* — prose acceptance + host access on BB-8. |

### Rejected on size/difficulty (not hard-excluded, just not economy-sized)

4LOM-CANARY-SERVICE (d3, owns=4, systemd + attribution + SessionStart wire),
DROID-BRIDGE-REGISTER (d3, edits the shared launcher, adversarial review required),
FORGE-PRIMARY-GITEA (d4, owns=7, rewrites the sanctioned push path),
LENS-REGISTRY-AND-REPORT (d3, owns=3, three wirings + anti-staleness),
CENTRAL-WORK-ROUTING-HUB (frontier, d5).

### Rejected as "no depth gain"

Every remaining d1–d2 strong ticket that would plausibly qualify — ASSIGN-DISPATCH-PICK-FIX,
CAPTURE-WIRING-TIMEOUT-FIX, CONFIG-SSOT-CANARY-REGISTER, MEMORY-INDEX-COMPACTION,
DOGFOOD-SCORECARD-TIMESTAMP-FIX, LANDING-GATE-REGISTER, UNIFIED-PLANE-CANARY-FRAMEWORK,
CLAIM-LADDER-HEALTH, RFL-3-CAPTURE-FIX, STUCK-TICKET-LOUD-VISIBILITY — is **PR-OPEN or blocked**.
Re-tiering them changes no claimable depth today, and every one of them is already covered by the
unlanded classifier (§4) or is dep-blocked. Proposing them would be board churn, not throughput.

---

## 3. Structural verdict

**Yes — the board is structurally short of economy work. This is the operator's "legitimately no
work" case and it is the honest answer.**

Evidence:

- 100 of 106 non-economy live tickets are `strong`; the tier distribution by `work_class` is
  dominated by `rig-meta` (≈40), `ci-infra` (≈20) and `money-path`/`routing` (≈20). Nearly the whole
  live board is **gate-enforcement, reconciliation wiring, canary/registry plumbing, and the money
  path** — three of the four hard-exclusion classes by construction.
- Of the 11 currently-claimable tickets, **5** are gate / security / push-spine, **4** are
  difficulty-3+ multi-surface mechanisms, **1** is a parked spike, and **1** (LITELLM-CI-DEPS) is
  genuinely economy-sized. There is no reservoir of mis-tiered cheap work being withheld.
- The cheap work the board *did* have has largely been done: five of the six existing `economy`
  tickets (API-DECOMPOSE-CYCLE-FIX, FN-MEMORY-RETIRE-ADOPT, FT-CATALOG-SEED,
  FT-LIMITS-GROQ-RECONCILE, HANDOFF-ROOT-ARCHIVE, PROJECT-MEMBERSHIP-GATE, ROUTER-LEDGER-DECAY,
  SYNC-SCHEDULE, WEB-ROADMAP-GENERATOR, LITELLM-COST-FIELD-FIX) are **PR-OPEN**, i.e. built and in
  the land queue. Economy tabs are not starved because work was mis-routed; they are starved because
  they *cleared* their queue and the remaining board is infra.

**Recommendation:** do not manufacture economy work. Idle economy tabs are the correct state while
the board is in a gate-hardening/reconciliation phase. If the operator wants economy capacity used,
the honest lever is the **land queue** (a large majority of the board is PR-OPEN awaiting review and
merge), not a re-tier pass.

---

## 4. Overlap check vs. `feat/tier-classifier` (built, unlanded)

The branch (`origin/feat/tier-classifier`, commits `f83d877` board pass + `0a759a8` rule +
`f1f162c` RED gate) carries **36 re-tiers**, of which **13 are strong→economy**:

ASSIGN-DISPATCH-PICK-FIX, CAPTURE-WIRING-TIMEOUT-FIX, CHARON-FLOWCHART,
CONFIG-SSOT-CANARY-REGISTER, DOGFOOD-SCORECARD-TIMESTAMP-FIX, DONE-SH-INTEGRITY-FIX,
LANDING-GATE-REGISTER, **LITELLM-CI-DEPS**, MEMORY-INDEX-COMPACTION, REACHABILITY-AUDIT-LAND,
RETIRE-FINAL-E2E-REVIEW, REVIEW-DISPENSATION-CANARY, UNIFIED-PLANE-CANARY-FRAMEWORK.

**OVERLAP: total.** My single candidate, `LITELLM-CI-DEPS`, is already in that set — apply the
classifier **or** the candidate, never both. (The classifier's own commit message calls out the
"litellm tag proof", so this ticket was its worked example.)

Two facts the board owner should carry:

1. **Landing the classifier adds exactly ONE claimable economy ticket, not 4.** The 12→16 economy
   count is a *board-wide* count; of the 13 strong→economy re-tiers, **12 are PR-OPEN or blocked**
   and only LITELLM-CI-DEPS is READY. The classifier also *removes* 6 tickets from economy
   (API-DECOMPOSE-CYCLE-FIX, CAPABILITY-ACTUALS-DEADREF-CLEANUP, FN-MEMORY-RETIRE-ADOPT,
   FT-LIMITS-GROQ-RECONCILE, LITELLM-COST-FIELD-FIX, PROJECT-MEMBERSHIP-GATE, ROUTER-LEDGER-DECAY,
   WEB-ROADMAP-GENERATOR up-tiered; FT-CATALOG-SEED → frontier), all currently PR-OPEN. Net effect
   on *claimable* economy depth today: **+1**.
2. **One dissent from the classifier's output, for the record:** `CHARON-FLOWCHART` →
   economy via the rule `docs d<4`. Its acceptance requires deriving a whole-system flowchart from
   code + the wiring-audit matrix and marking INERT vs WIRED — that is synthesis and judgement, not
   mechanical docs. It is PR-OPEN so nothing is at stake today, but if the rule ever routes a fresh
   `docs` ticket of that shape to an economy model, expect a plausible-but-wrong diagram. Consider a
   `docs` sub-signal (derived-from-code vs. transcribed) before the rule drives live routing. Note
   the classifier module itself documents that the routing consumer is **designed, not wired** — only
   the `validate_board.sh` drift check is live — so this is a future-risk note, not a live defect.

---

## 5. Bottom line

- Apply-or-not decision for the board owner: **one** proposal (`LITELLM-CI-DEPS` strong→economy),
  and it is subsumed by landing `feat/tier-classifier`. Preferring the classifier is the better
  move — it is the mechanized rule rather than a hand edit, and it fixes the same row.
- The board is **structurally** short of economy work. Idle economy tabs are correct right now.
