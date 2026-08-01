# BLOCKED-BLAST-RADIUS — are the board's blocked tickets *really* blocked?

READ-ONLY analysis, 2026-07-31. Repo `/home/stack/charon-private`.
Board = `fleet/board/*.md` (132), archive = `fleet/board/archive/*.md` (218),
markers = `fleet/state/{claims,submitted,done,needs-push}/<ID>`.

"BLOCKED" is taken from the rig's own predicate, `fleet/board.sh:14` -> `fleet/_lib.sh:32
deps_done()`, which is reached only when the ticket has no `done` / `submitted` / `needs-push` /
`claims` marker. `deps_done()` returns true ONLY if `fleet/state/done/<dep>` exists — archive
membership does not count, which is itself a false-block source (see §E).

**26 board tickets are in state=BLOCKED** (57 tickets carry a non-empty `depends_on:`).

## HEADLINE

| Category | Count |
|---|---|
| FALSELY BLOCKED (every dep SATISFIED/PHANTOM) | **0 tickets** — but 1 falsely-blocking *edge*, see §B |
| SOFT BLOCKED (merge-order / owns-collision only — buildable today) | **12** |
| HARD BLOCKED (>=1 open true build/correctness prereq) | **14** |
| PHANTOM dep references (dangling IDs) | **0** — see §E |

Of the 14 HARD-blocked tickets, **13 are gated by a prereq that is already BUILT and sitting in an
open PR** (`fleet/state/submitted/<dep>`), or by another soft-blocked ticket. Exactly **one** hard
prereq is genuinely unbuilt: `PRODUCT-GRADES-STORE`, which is a `parked: true` draft.

So the board's blocking is overwhelmingly a **merge/landing backlog**, not a build backlog:
12 soft-blocked tickets are buildable right now, and the top 5 blast-radius blockers are all PR-OPEN.

---

## A) TOP BLOCKERS BY BLAST RADIUS

Transitive count over OPEN (non-DONE) board tickets only. Evidence: `depends_on:` edges parsed from
`fleet/board/*.md`; state from `fleet/state/*` markers.

| Blocking ticket | State | Transitively blocks N | Which tickets |
|---|---|---|---|
| SYNC-SCHEDULE | PR-OPEN (`fleet/state/submitted/SYNC-SCHEDULE`) | **7** | HANDOFF-GATE-NONBYPASSABLE, MARKER-PROOF-MECHANIZE, NO-LOCAL-MASTER-COMMITS, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING, REPO-MAP-CONVERGE |
| GITHUB-LIMITS-HARDENING | PR-OPEN (`fleet/state/submitted/GITHUB-LIMITS-HARDENING`) | **7** | DONE-SH-INTEGRITY-FIX, HANDOFF-GATE-NONBYPASSABLE, MARKER-PROOF-MECHANIZE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, PREFLIGHT-VERIFY-MERGED-GHCACHE, RECONCILE-WIRING |
| BENCH-OOB-GRADING | PR-OPEN (`fleet/state/submitted/BENCH-OOB-GRADING`) | **7** | FINAL-E2E-REVIEW, HANDOFF-GATE-NONBYPASSABLE, MARKER-PROOF-MECHANIZE, MODEL-PREFLIGHT, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING |
| REPO-FIELD-REQUIRED | PR-OPEN (`fleet/state/submitted/REPO-FIELD-REQUIRED`) | **6** | HANDOFF-GATE-NONBYPASSABLE, MARKER-PROOF-MECHANIZE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING, REPO-MAP-CONVERGE |
| DISCOVERY-SOURCE-ADAPTERS | PR-OPEN (`fleet/state/submitted/DISCOVERY-SOURCE-ADAPTERS`) | **6** | DISCOVERY-APPROVAL-WIRE, DISCOVERY-CADENCE, DISCOVERY-DIFF, DISCOVERY-NORMALIZE, DISCOVERY-QUEUE, INVENTORY-TABLE-SHARE |
| DONE-SH-INTEGRITY-FIX | BLOCKED (soft) | **5** | HANDOFF-GATE-NONBYPASSABLE, MARKER-PROOF-MECHANIZE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING |
| REPO-MAP-CONVERGE | BLOCKED (soft) | **5** | HANDOFF-GATE-NONBYPASSABLE, MARKER-PROOF-MECHANIZE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING |
| RECONCILE-REVIEW-GATE | PR-OPEN (`fleet/state/submitted/RECONCILE-REVIEW-GATE`) | **5** | HANDOFF-GATE-NONBYPASSABLE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING, REVIEW-DISPENSATION-CANARY |
| DISCOVERY-NORMALIZE | BLOCKED (hard) | **5** | DISCOVERY-APPROVAL-WIRE, DISCOVERY-CADENCE, DISCOVERY-DIFF, DISCOVERY-QUEUE, INVENTORY-TABLE-SHARE |
| MARKER-PROOF-MECHANIZE | BLOCKED (hard) | **4** | HANDOFF-GATE-NONBYPASSABLE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING |
| DISCOVERY-DIFF | BLOCKED (hard) | 3 | DISCOVERY-APPROVAL-WIRE, DISCOVERY-CADENCE, DISCOVERY-QUEUE |
| CI-SUITES-CANARY | PR-OPEN | 3 | HANDOFF-GATE-NONBYPASSABLE, MODEL-HARDCODE-PURGE, REVIEWER-TAB-POOL |
| RECONCILE-WIRING | BLOCKED (hard) | 3 | HANDOFF-GATE-NONBYPASSABLE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER |
| REVIEWER-TAB-POOL | BLOCKED (soft) | 2 | HANDOFF-GATE-NONBYPASSABLE, MODEL-HARDCODE-PURGE |
| DISCOVERY-QUEUE | BLOCKED (hard) | 2 | DISCOVERY-APPROVAL-WIRE, DISCOVERY-CADENCE |
| ADD-PROVIDER-MECHANIZE-COMPLETE | PR-OPEN | 2 | DISCOVERY-APPROVAL-WIRE, DISCOVERY-CADENCE |
| **WCI-CONTENTION-TEETH** | **MERGED + ARCHIVED, no done marker** | 2 | PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER |
| MODEL-PREFLIGHT | BLOCKED (hard) | 1 | FINAL-E2E-REVIEW |
| LOOP-GUARD-REASON-WIRE | CLAIMED | 1 | LAUNCHER-CRASH-PARTIAL-DETECT |
| GATEWAY-NONTOKEN-METERING | PR-OPEN | 1 | FT-WIRE-QUOTA |

**Unblock-first levers (all three are MERGES, not builds):**
1. **SYNC-SCHEDULE** (PR-OPEN ~194h per `fleet/board/NO-LOCAL-MASTER-COMMITS.md:9`) — 7 open tickets.
2. **GITHUB-LIMITS-HARDENING** (PR-OPEN) — 7 open tickets; it and SYNC-SCHEDULE together are the
   whole `fleet/preflight.sh` + `fleet/done.sh` single-writer traffic jam.
3. **BENCH-OOB-GRADING** (PR-OPEN) — 7 open tickets; the only one of the three carrying a genuine
   *correctness* edge (MODEL-PREFLIGHT -> FINAL-E2E-REVIEW).

Bonus 4th: **DISCOVERY-SOURCE-ADAPTERS** (PR-OPEN) — merging it cascades the entire 6-ticket
P1 discovery leg from HARD-BLOCKED to buildable, one ticket at a time.

---

## B) FALSELY BLOCKED (unblock now)

**No ticket has ALL deps satisfied**, so strictly zero rows. But there is one **falsely-blocking dep
edge** and one **stale merge-order edge**, both of which are board corruption in effect:

| Ticket | Priority | Dep | Why it is not a real block |
|---|---|---|---|
| PREFLIGHT-GATE-RUN-HELPER | 1 | WCI-CONTENTION-TEETH | Dep is **merged and archived** — `fleet/board/archive/WCI-CONTENTION-TEETH.md` exists, its PR landed (`git log`: `3c8919b Merge pull request #268 from Nnyan/feat/wci-contention-teeth`), and it was retired by the auto-done archive sweep (`1c974cc board-hygiene: auto-done-mark archives from landing wave`). **But `fleet/state/done/WCI-CONTENTION-TEETH` does not exist** (`ls fleet/state/done | grep -i WCI` -> only `WCI`, `WCI-FOLLOWON`). `deps_done()` (`fleet/_lib.sh:35`) tests only the done marker, so this dep can never satisfy. Same dangling edge also sits on PREFLIGHT-GATE-REGISTRY (`fleet/board/PREFLIGHT-GATE-REGISTRY.md`, currently CLAIMED so not surfaced as blocked). **FIX: write the missing done marker.** |
| REVIEWER-TAB-POOL | 0 | CI-SUITES-CANARY | The `real-dep:` justification (`fleet/board/REVIEWER-TAB-POOL.md:8`) claims *"CI-SUITES-CANARY owns fleet/checks/rig-ci-scope.sh"* — **that is false today**. `fleet/board/CI-SUITES-CANARY.md:8` reads `owns: fleet/tests/ci-suites-canary.test.sh` only. Zero owns overlap, so the merge-order rationale no longer holds. The ticket's own `ds:` says `depends_on: none to start`. **Stale edge — verify and drop.** |

---

## C) SOFT BLOCKED (buildable now, merge later) — 12

Every remaining dep is an owns-collision / single-writer merge-ordering constraint. These can be
CLAIMED AND BUILT today; they must only rebase-and-merge behind the named ticket.

| Ticket | Priority | Merge-order dep(s) | Shared surface (evidence) |
|---|---|---|---|
| **REPO-MAP-CONVERGE** | 0 | REPO-FIELD-REQUIRED (PR-OPEN), SYNC-SCHEDULE (PR-OPEN) | Its own `ds:` (`fleet/board/REPO-MAP-CONVERGE.md`) states verbatim these are *"SHARED-OWNS single-writer sequencing, not preference"* — `validate_board.sh` w/ REPO-FIELD-REQUIRED, `preflight.sh` w/ SYNC-SCHEDULE. Other 3 deps SATISFIED (`fleet/state/done/{VERIFY-MERGED-REPO-AWARE,REPO-DECL-CENTRAL,GH-SEAM-CHOKEPOINT}`). **Blast radius 5 — highest-value soft unblock.** |
| **DONE-SH-INTEGRITY-FIX** | 0 | GITHUB-LIMITS-HARDENING (PR-OPEN) | `real-dep:` (`:13`): *"owns fleet/done.sh … Rebase onto its merge; don't run as a concurrent second writer"*. VERIFY-MERGED-REPO-AWARE SATISFIED (`fleet/state/done/VERIFY-MERGED-REPO-AWARE`). **Blast radius 5.** |
| **HANDOFF-GATE-NONBYPASSABLE** | 0 | RECONCILE-WIRING, REVIEWER-TAB-POOL | `ds:` says verbatim *"Wave-1, **no build prereq**"*. `real-dep:` (`:9`) = shared `fleet/land.sh` GATE_PARTS surface w/ RECONCILE-WIRING; REVIEWER-TAB-POOL shares `fleet/checks/rig-ci-scope.sh` (both `owns:` it). MERGE-DROP-RATCHET SATISFIED. |
| **REVIEWER-TAB-POOL** | 0 | CI-SUITES-CANARY (PR-OPEN) | See §B — merge-order at best, and the claimed owns overlap no longer exists. |
| **MODEL-HARDCODE-PURGE** | 0 | REVIEWER-TAB-POOL, CAPTURE-WIRING-TIMEOUT-FIX (PR-OPEN) | `real-dep:` (`:8`): *"both must settle before the purge edits those files"* — `fleet/review-pool.sh` and `fleet/charon-run.sh`. Confirmed by `owns:` lines on all three tickets. Pure file-contention. |
| **LAUNCHER-CRASH-PARTIAL-DETECT** | 0 | LOOP-GUARD-REASON-WIRE (CLAIMED) | Both `owns: fleet/fleet-droid.sh` (`fleet/board/LAUNCHER-CRASH-PARTIAL-DETECT.md:8`, `fleet/board/LOOP-GUARD-REASON-WIRE.md`). `ds:` only justifies the DROID-LIFECYCLE-REAP edge, which is SATISFIED (`fleet/state/done/DROID-LIFECYCLE-REAP`); SESSION-REPORT-WIRE also SATISFIED. |
| **NO-LOCAL-MASTER-COMMITS** | 1 | SYNC-SCHEDULE (PR-OPEN) | `real-dep:` (`:9-10`) states verbatim: *"MERGE-ORDER only, **zero owns overlap**"*. |
| **PREFLIGHT-GATE-RUN-HELPER** | 1 | SYNC-SCHEDULE, MARKER-PROOF-MECHANIZE, RECONCILE-WIRING, REPO-MAP-CONVERGE | All four are shared single-owners of `fleet/preflight.sh`. Its own `ds:` says *"depends_on: WCI-CONTENTION-TEETH **only** … THE SHARED FILE IS THE WHOLE CONSTRAINT"* — and WCI-CONTENTION-TEETH is already merged (§B). |
| **ORDER-A-COST-PRIMARY-LAND** | 1 | FORWARDER-COST-ORDER-FALLBACK (CLAIMED) | `real-dep:` (`:12`): *"shared src/charon/forwarder.py — … order-a rebases onto it"*. GW-CUTOVER-LIVE-WIRE SATISFIED (`fleet/state/done/GW-CUTOVER-LIVE-WIRE`). |
| **CREATION-GATE-DECOMPOSE-WIRE** | 2 | PROJECT-MEMBERSHIP-GATE (PR-OPEN) | `real-dep:` (`:12`): *"owns validate_board.sh … Rebase onto its merge, don't run concurrently"*. Both `owns:` lines name `fleet/validate_board.sh`. PRIORITY-CONSOLIDATION SATISFIED. |
| **WIP-CLOSE-GATE** | 2 | SESSION-END-PUSH-GATE (PR-OPEN) | Both `owns: fleet/end-session.sh`. Its `ds:` says verbatim *"depends_on: **none to START**"* (the caveat is a design decision — the meta-gate ADOPT deep-dive — not a board dep). |
| **REACHABILITY-AUDIT-LAND** | 2 | REACHABILITY-GATE (PR-OPEN) | Both `owns: fleet/state/REACHABILITY-AUDIT.md`. **Edge is arguably INVERTED**: this ticket's `ds:` says *"Sequence: land the audit (this ticket) → REACHABILITY-GATE PART-3 builds the gate from it … File-adjacent but not colliding … Coordinate so both do not stage the .md."* |

---

## D) HARD BLOCKED — 14

| Ticket | Priority | Open true prereq | Prereq state | Evidence |
|---|---|---|---|---|
| MARKER-PROOF-MECHANIZE | 0 | REPO-MAP-CONVERGE | BLOCKED (soft — §C) | `real-dep:` (`:18`): *"Its repo-map check establishes the `repo:`-resolution the marker gate must reuse … a marker gate that resolved the wrong repo would fail valid markers."* Its other 4 deps are merge-order or SATISFIED. |
| RECONCILE-WIRING | 1 | RECONCILE-REVIEW-GATE | PR-OPEN | `real-dep:`: *"**build dep**: wires fleet/checks/reconcile-review-gate.sh into the firing layers (land.sh BLOCK point); **the check must exist first**. dep-kind: build."* MARKER-PROOF-MECHANIZE edge is `dep-kind: build/rebase` (merge-order). |
| REVIEW-DISPENSATION-CANARY | 0 | RECONCILE-REVIEW-GATE | PR-OPEN | `ds:`: *"RECONCILE-REVIEW-GATE (the check reused — **real build prereq**)"*. PLANE-CANARY-REGISTRY SATISFIED. |
| DISCOVERY-NORMALIZE | 1 | DISCOVERY-SOURCE-ADAPTERS | PR-OPEN | `dep-kind: build` (`fleet/board/DISCOVERY-NORMALIZE.md:9`). D1->D2 of the FREE-PROVIDER-DISCOVERY leg; consumes D1's RawOffer type. |
| DISCOVERY-DIFF | 1 | DISCOVERY-NORMALIZE | BLOCKED | `dep-kind: build`. Diffs D2's normalized snapshot. |
| DISCOVERY-QUEUE | 1 | DISCOVERY-DIFF | BLOCKED | `dep-kind: build`. Consumes D3's NEW/CHANGED/GONE. |
| DISCOVERY-APPROVAL-WIRE | 1 | DISCOVERY-QUEUE; ADD-PROVIDER-MECHANIZE-COMPLETE | BLOCKED; PR-OPEN | `dep-kind: build`. Actuates approved `discovery-review.tsv` rows via `fleet/add-provider.sh`. |
| DISCOVERY-CADENCE | 1 | DISCOVERY-APPROVAL-WIRE | BLOCKED | `dep-kind: build` — *"Sequenced last — it schedules D1-D5's now-built modules."* |
| INVENTORY-TABLE-SHARE | 1 | DISCOVERY-NORMALIZE | BLOCKED | `dep-kind: build` — upserts D2's normalized rows. INVENTORY-TABLE SATISFIED (`fleet/state/done/INVENTORY-TABLE`). |
| FT-WIRE-QUOTA | 2 | FT-CATALOG-SEED | PR-OPEN | `real-dep:` block: *"Also **needs** FT-QUOTA-ENGINE (the engine), FT-CONFIG-SURFACE (the limits shape) and **FT-CATALOG-SEED (the seed) merged first**"*; owns are disjoint (`provider_presets/hosted.py` + `free_tier_catalog.py`) so this is a build, not a collision. GATEWAY-NONTOKEN-METERING edge is `gateway.py` merge-order. Other 4 deps SATISFIED. |
| MODEL-PREFLIGHT | 2 | BENCH-OOB-GRADING | PR-OPEN | `real-dep:` (`:8`): *"preflight grading MUST run out-of-band … In-band grading reproduces the S0-S6 invalidity this fixes. **True correctness prereq.**"* |
| FINAL-E2E-REVIEW | 2 | MODEL-PREFLIGHT | BLOCKED | `real-dep:` (`:9`): *"cannot review it until it is built + dogfooded"*. DECOMPOSE-DEFAULT-GATE SATISFIED. |
| PEAK-PRICING-AWARE | 2 | PRICING-LIMITS-CHECK-SH | PR-OPEN | `real-dep:` (`:10`): *"this ticket **CONSUMES** that data … **True build/correctness prereq** though owns are disjoint."* |
| WIRE-BRAIN-INTO-GATEWAY | 2 | PRODUCT-GRADES-STORE | READY but **`parked: true`** | `ds:`: *"depends_on: PRODUCT-GRADES-STORE — **hard prereq** (the provider this ticket consumes). BLOCKED until it lands."* + *"there is NOTHING PRODUCT-SIDE TO CONNECT TO yet"*. `fleet/board/PRODUCT-GRADES-STORE.md` carries `parked: true`. **The only hard prereq on the board that is neither built nor in a PR.** |

Note: 13 of these 14 are gated behind work that is already built (PR-OPEN) or behind a
soft-blocked sibling. Merging the §A levers collapses most of this table.

---

## E) PHANTOM dependency references

**Zero true phantoms.** Every one of the 98 dep edges across the 57 tickets with a `depends_on:`
resolves to a board file, an archive file, or a `fleet/state/done/` marker (case-insensitively, per
`fleet/_lib.sh:8 canon()`).

Two **board-integrity defects** of the same family were found, and they behave as phantoms to the
rig's own predicate:

1. **`WCI-CONTENTION-TEETH` — merged + archived, done marker MISSING.**
   - present: `fleet/board/archive/WCI-CONTENTION-TEETH.md`
   - absent: `fleet/state/done/WCI-CONTENTION-TEETH`
   - merged: `3c8919b Merge pull request #268 from Nnyan/feat/wci-contention-teeth`;
     archived by `1c974cc board-hygiene: auto-done-mark archives from landing wave`
   - effect: `deps_done()` can never satisfy this edge, permanently blocking
     `PREFLIGHT-GATE-RUN-HELPER` and `PREFLIGHT-GATE-REGISTRY`.
   - class: the archive sweep moved the board file without writing the done marker. Worth a
     one-line reconciliation check (does every `board/archive/<id>.md` have `state/done/<id>`?) —
     this is the same "marker is not proof" class `MARKER-PROOF-MECHANIZE` and
     `DONE-SH-INTEGRITY-FIX` exist to close.

2. **`CI-SUITES-CANARY` -> `REVIEWER-TAB-POOL`: `real-dep:` cites an `owns:` that no longer exists.**
   `REVIEWER-TAB-POOL.md:8` asserts CI-SUITES-CANARY owns `fleet/checks/rig-ci-scope.sh`;
   `CI-SUITES-CANARY.md:8` owns only `fleet/tests/ci-suites-canary.test.sh`. Justification text
   drifted from the `owns:` field it cites. A P0 ticket (blast radius 2) is held by it.

Contradicted-edge watch (not corruption, but worth reconciling):
- `MARKER-PROOF-MECHANIZE.md:22` declares a merge-order edge on BENCH-OOB-GRADING over
  "`preflight.sh` (unprefixed)". `PREFLIGHT-GATE-RUN-HELPER.md`'s `ds:` states this was verified
  (`find . -name preflight.sh`) to be `fleet/benchmark/preflight.sh`, a **different file** —
  *"No edge needed or declared."* Same claim, opposite conclusion, on two live tickets.
- `REPO-MAP-CONVERGE.md`'s `ds:` asserts *"BENCH-OOB-GRADING is parked"*;
  `fleet/board/BENCH-OOB-GRADING.md` carries `parked: false` and a `submitted` marker. Stale prose.
