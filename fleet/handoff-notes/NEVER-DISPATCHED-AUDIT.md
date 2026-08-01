# NEVER-DISPATCHED AUDIT

Read-only audit. Generated 2026-07-31. No tickets, branches, or state were modified.

## Scope and method

Universe: **350 tickets** — 133 in `fleet/board/*.md`, 217 in `fleet/board/archive/*.md`.

A ticket counts as NEVER-DISPATCHED only when **all** of these hold:

| Check | Source |
|---|---|
| no state marker | `fleet/state/{claims,submitted,done}/<ID>` absent (10 / 49 / 238 entries enumerated) |
| no local branch | `git branch -a --list '*<branch>*'` empty in **both** `/home/stack/charon-private` (678 refs) and `/home/stack/code/charon` (457 refs) |
| no remote branch | `git ls-remote --heads origin <branch>` empty in **both** repos (150 / 145 heads) |
| no PR ever | branch absent from the full `--state all` PR list of **Nnyan/charon-private** (321 PRs) and **SLOP-Platform/charon** (205 PRs); both lists are complete (`--limit 2000` not reached) |
| no agent log | no `fleet/state/agent-logs/*<ID>*` (246 files) |
| no agent brief | no `fleet/state/agent-briefs/*<ID>*` (257 files) |

Every one of the 41 findings was additionally re-verified with the literal per-ticket commands
(`git branch -a --list`, `git ls-remote --heads origin <branch>` against both repos) — all returned
empty; full transcript in the audit run log. Twelve further state directories
(`briefs`, `droid-logs`, `enqueued`, `needs-push`, `tabs`, `reviews`, `review-claims`, `review-done`,
`jobs`, `model-used`, `judgment`, `leaks`) were also swept for each ID; only one hit surfaced
(`DEADCODE-TOOLS-WIRE`, noted inline below).

Mint date = earliest `git log --diff-filter=A --format=%ad --date=short` across both the board and
archive paths for that ID. All 41 tickets are git-tracked, so every mint date is real (none UNKNOWN).

**Result: 41 of 350 tickets (11.7%) were minted but never dispatched.**

17 of the 41 carry no `priority:` field at all — recorded as `(none)`, not guessed.

---

## THREAD A — current + previous session (minted 2026-07-31 / 2026-08-01)

**11 tickets.**

| Ticket | Priority | Tier | Minted | Evidence of never-dispatched |
|---|---|---|---|---|
| `DEADCODE-TOOLS-WIRE` | 0 | strong | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/deadcode-tools-wire` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief; **caveat:** launch script `fleet/state/tabs/DEADCODE-TOOLS-WIRE.sh` staged 07-31 21:45 but never claimed |
| `FORWARDER-COST-ORDER-FALLBACK` | 0 | strong | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin fix/forwarder-cost-order-fallback` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `KSF-LOAD-BEARING` | 0 | frontier | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/ksf-load-bearing` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `LOOP-GUARD-REASON-WIRE` | 0 | economy | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin fix/loop-guard-reason-wire` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `MODEL-HARDCODE-PURGE` | 0 | strong | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin fix/model-hardcode-purge` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `SHARED-NAMESPACE-CONTENTION` | 0 | strong | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin fix/shared-namespace-contention` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `TOOL-COMPOSITION-LAYER` | 0 | frontier | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin design/tool-composition-layer` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `AUTO-DONE-ON-MERGE-MISS` | 1 | strong | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin fix/auto-done-on-merge-miss` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `NO-LOCAL-MASTER-COMMITS` | 1 | strong | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin fix/no-local-master-commits` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `PREFLIGHT-GATE-RUN-HELPER` | 1 | strong | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/preflight-gate-run-helper` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `STOP-WORKER-GRACEFUL-EXIT` | 1 | strong | 2026-07-31 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin fix/stop-worker-graceful-exit` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |

### Characterization — Thread A

This thread is almost entirely **rig-meta and CI-infra self-repair**: 5 of 11 are `rig-meta`
(`AUTO-DONE-ON-MERGE-MISS`, `NO-LOCAL-MASTER-COMMITS`, `PREFLIGHT-GATE-RUN-HELPER`,
`SHARED-NAMESPACE-CONTENTION`, `STOP-WORKER-GRACEFUL-EXIT`) and 2 more are `ci-infra`
(`DEADCODE-TOOLS-WIRE`, `LOOP-GUARD-REASON-WIRE`) — i.e. the session spent its minting energy
describing defects in the *build rig itself* (marker/done bookkeeping, namespace collisions between
concurrent agents, worker shutdown, loop-guard reasons) rather than product work. The genuinely
product-shaped items are the minority: one money-path (`FORWARDER-COST-ORDER-FALLBACK`, p0 — the
cost-ordered failover path), one refactor (`MODEL-HARDCODE-PURGE`, p0), and one design-review
(`TOOL-COMPOSITION-LAYER`, p0), plus `KSF-LOAD-BEARING` (p0, bugfix). Priority skews hot — 6 of 11
are p0 — so this is not a low-value backlog; it is a fresh, high-priority batch that was written
and then left at the gate when the session ended. `DEADCODE-TOOLS-WIRE` got as far as having a
launcher tab script written at 21:45 and still never produced a claim, branch, or PR.

**Oldest item age: 0 days** (oldest mint 2026-07-31, i.e. same-day — the whole thread is same-session).

---

## THREAD B — older sessions (minted 2026-07-30 or earlier)

**30 tickets.**

| Ticket | Priority | Tier | Minted | Evidence of never-dispatched |
|---|---|---|---|---|
| `LAUNCHER-CRASH-PARTIAL-DETECT` | 0 | strong | 2026-07-15 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/launcher-crash-partial-detect` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `HANDOFF-GATE-NONBYPASSABLE` | 0 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/handoff-gate-nonbypassable` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `RETIRE-FINAL-E2E-REVIEW` | 0 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin chore/retire-final-e2e-review` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `GATEWAY-GRADE-ORDER-MVP` | 1 | strong | 2026-07-20 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/gateway-grade-order-mvp` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `DISCOVERY-APPROVAL-WIRE` | 1 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/discovery-approval-wire` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `DISCOVERY-CADENCE` | 1 | economy | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/discovery-cadence` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `DISCOVERY-DIFF` | 1 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/discovery-diff` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `DISCOVERY-NORMALIZE` | 1 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/discovery-normalize` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `DISCOVERY-QUEUE` | 1 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/discovery-queue` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `INVENTORY-TABLE-SHARE` | 1 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/inventory-table-share` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `RECONCILE-HANDOFF-FRESHNESS` | 1 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/reconcile-handoff-freshness` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `RECONCILE-WIRING` | 1 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/reconcile-wiring` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `SINGLE-LEG-AUTOSWAP` | 1 | strong | 2026-07-23 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/single-leg-autoswap` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `WORK-ROUTING-TO-CHARON-ENGINE` | (none) | frontier | 2026-07-09 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/work-routing-to-charon-engine` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `FINAL-E2E-REVIEW` | (none) | frontier | 2026-07-12 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin audit/final-e2e-review` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `MODEL-PREFLIGHT` | (none) | frontier | 2026-07-12 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/model-preflight` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `DRAIN-THEN-PARK` | (none) | frontier | 2026-07-13 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/drain-then-park` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `POST-GATEWAY-WCI-DECOMPOSE` | (none) | standard | 2026-07-13 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin chore/post-gateway-wci-decompose` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `FT-WIRE-QUOTA` | (none) | strong | 2026-07-14 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/ft-wire-quota` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `CREATION-GATE-DECOMPOSE-WIRE` | (none) | strong | 2026-07-15 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/creation-gate-decompose-wire` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `DONE-SH-INTEGRITY-FIX` | (none) | strong | 2026-07-15 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/done-sh-integrity-fix` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `REPO-MAP-CONVERGE` | (none) | strong | 2026-07-18 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/repo-map-converge` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `CG-LAN-OPEN-UI` | (none) | strong | 2026-07-19 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/cg-lan-open-ui` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `GITEA-ACTIONS-CI-SPIKE` | (none) | strong | 2026-07-19 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin spike/gitea-actions-ci` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `MARKER-PROOF-MECHANIZE` | (none) | strong | 2026-07-19 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/marker-proof-mechanize` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `PRODUCT-GRADES-STORE` | (none) | strong | 2026-07-19 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/product-grades-store` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `WIRE-BRAIN-INTO-GATEWAY` | (none) | strong | 2026-07-19 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/wire-brain-into-gateway` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `REACHABILITY-AUDIT-LAND` | (none) | strong | 2026-07-20 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/reachability-audit-land` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `WIP-CLOSE-GATE` | (none) | strong | 2026-07-20 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/wip-close-gate` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |
| `PEAK-PRICING-AWARE` | (none) | strong | 2026-07-21 | no claims/submitted/done marker; no local branch (both repos); `git ls-remote --heads origin feat/peak-pricing-aware` empty (both repos); 0 PRs in Nnyan/charon-private and SLOP-Platform/charon (--state all); no agent-log, no agent-brief |

### Characterization — Thread B

Thread B is where the *substantive* undispatched work is buried, and it is dominated by three
clusters. First, **money-path / routing** (6 money-path + 2 routing): `DRAIN-THEN-PARK`,
`FT-WIRE-QUOTA`, `PEAK-PRICING-AWARE`, `GATEWAY-GRADE-ORDER-MVP`, `SINGLE-LEG-AUTOSWAP`,
`PRODUCT-GRADES-STORE` / `WIRE-BRAIN-INTO-GATEWAY` — the free-tier quota wiring, drain-then-park
funding-class behaviour, peak pricing, and the grade-ordered routing brain. That is the product's
core value proposition sitting entirely unstarted. Second, a **reconcile/marker gate cluster**
(`MARKER-PROOF-MECHANIZE`, `RECONCILE-WIRING`, `RECONCILE-HANDOFF-FRESHNESS`, `DONE-SH-INTEGRITY-FIX`,
`WIP-CLOSE-GATE`, `REPO-MAP-CONVERGE`) that is heavily self-referential — several of these depend on
each other, which is a large part of why none moved. Third, the **five-ticket DISCOVERY chain**
(`DISCOVERY-NORMALIZE` → `DISCOVERY-DIFF` → `DISCOVERY-QUEUE` → `DISCOVERY-APPROVAL-WIRE` →
`DISCOVERY-CADENCE`, all p1, all minted 2026-07-23) which was decomposed into a strict serial chain
and then never had its head dispatched, so the entire chain stalled. Only 3 of the 30 are design/spike
(`GITEA-ACTIONS-CI-SPIKE`, `TOOL-COMPOSITION-LAYER` is in Thread A, `POST-GATEWAY-WCI-DECOMPOSE`);
the rest is real build work. Notably 21 of 30 carry **no priority field at all**, which is a plausible
mechanical cause of non-dispatch if the launcher orders by priority.

**Oldest item age: 22 days** (minted 2026-07-09 — `WORK-ROUTING-TO-CHARON-ENGINE`).

---

## STILL BLOCKED vs DISPATCHABLE NOW

A dependency counts as satisfied when the dep ID appears in `fleet/state/done/` (238 entries) or
`fleet/board/archive/` (217 entries). Deps that are `OPEN-ON-BOARD`, `CLAIMED`, `SUBMITTED`, or
`NOT-FOUND` are treated as unsatisfied. In-flight states are shown explicitly so the operator can see
which blockers are close to clearing.

### Thread A

| Ticket | Priority | depends_on status | Verdict |
|---|---|---|---|
| `DEADCODE-TOOLS-WIRE` | 0 | (none) | **DISPATCHABLE NOW** |
| `FORWARDER-COST-ORDER-FALLBACK` | 0 | (none) | **DISPATCHABLE NOW** |
| `KSF-LOAD-BEARING` | 0 | (none) | **DISPATCHABLE NOW** |
| `LOOP-GUARD-REASON-WIRE` | 0 | `SESSION-REPORT-WIRE`=DONE | **DISPATCHABLE NOW** |
| `MODEL-HARDCODE-PURGE` | 0 | `REVIEWER-TAB-POOL`=OPEN-ON-BOARD, `CAPTURE-WIRING-TIMEOUT-FIX`=SUBMITTED(in-flight) | **STILL BLOCKED** |
| `SHARED-NAMESPACE-CONTENTION` | 0 | (none) | **DISPATCHABLE NOW** |
| `TOOL-COMPOSITION-LAYER` | 0 | (none) | **DISPATCHABLE NOW** |
| `AUTO-DONE-ON-MERGE-MISS` | 1 | (none) | **DISPATCHABLE NOW** |
| `NO-LOCAL-MASTER-COMMITS` | 1 | `SYNC-SCHEDULE`=SUBMITTED(in-flight) | **STILL BLOCKED** |
| `PREFLIGHT-GATE-RUN-HELPER` | 1 | `WCI-CONTENTION-TEETH`=ARCHIVED, `SYNC-SCHEDULE`=SUBMITTED(in-flight), `MARKER-PROOF-MECHANIZE`=OPEN-ON-BOARD, `RECONCILE-WIRING`=OPEN-ON-BOARD, `REPO-MAP-CONVERGE`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `STOP-WORKER-GRACEFUL-EXIT` | 1 | (none) | **DISPATCHABLE NOW** |

### Thread B

| Ticket | Priority | depends_on status | Verdict |
|---|---|---|---|
| `LAUNCHER-CRASH-PARTIAL-DETECT` | 0 | `DROID-LIFECYCLE-REAP`=DONE, `SESSION-REPORT-WIRE`=DONE, `LOOP-GUARD-REASON-WIRE`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `HANDOFF-GATE-NONBYPASSABLE` | 0 | `RECONCILE-WIRING`=OPEN-ON-BOARD, `MERGE-DROP-RATCHET`=DONE, `REVIEWER-TAB-POOL`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `RETIRE-FINAL-E2E-REVIEW` | 0 | `PLANE-CANARY-WIRE`=DONE | **DISPATCHABLE NOW** |
| `GATEWAY-GRADE-ORDER-MVP` | 1 | `GW-CUTOVER-LIVE-WIRE`=DONE | **DISPATCHABLE NOW** |
| `DISCOVERY-APPROVAL-WIRE` | 1 | `DISCOVERY-QUEUE`=OPEN-ON-BOARD, `ADD-PROVIDER-MECHANIZE-COMPLETE`=SUBMITTED(in-flight) | **STILL BLOCKED** |
| `DISCOVERY-CADENCE` | 1 | `DISCOVERY-APPROVAL-WIRE`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `DISCOVERY-DIFF` | 1 | `DISCOVERY-NORMALIZE`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `DISCOVERY-NORMALIZE` | 1 | `DISCOVERY-SOURCE-ADAPTERS`=SUBMITTED(in-flight) | **STILL BLOCKED** |
| `DISCOVERY-QUEUE` | 1 | `DISCOVERY-DIFF`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `INVENTORY-TABLE-SHARE` | 1 | `INVENTORY-TABLE`=DONE, `DISCOVERY-NORMALIZE`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `RECONCILE-HANDOFF-FRESHNESS` | 1 | `RECONCILE-GATE-WIRED`=DONE | **DISPATCHABLE NOW** |
| `RECONCILE-WIRING` | 1 | `RECONCILE-BOARD-PR-DONE`=DONE, `RECONCILE-OWNS-TRACKED`=DONE, `RECONCILE-GATE-WIRED`=DONE, `RECONCILE-REVIEW-GATE`=SUBMITTED(in-flight), `MARKER-PROOF-MECHANIZE`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `SINGLE-LEG-AUTOSWAP` | 1 | `INVENTORY-TABLE`=DONE | **DISPATCHABLE NOW** |
| `WORK-ROUTING-TO-CHARON-ENGINE` | (none) | (none) | **DISPATCHABLE NOW** |
| `FINAL-E2E-REVIEW` | (none) | `DECOMPOSE-DEFAULT-GATE`=DONE, `MODEL-PREFLIGHT`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `MODEL-PREFLIGHT` | (none) | `BENCH-OOB-GRADING`=SUBMITTED(in-flight) | **STILL BLOCKED** |
| `DRAIN-THEN-PARK` | (none) | `R46-BALANCE-WIRE`=ARCHIVED | **DISPATCHABLE NOW** |
| `POST-GATEWAY-WCI-DECOMPOSE` | (none) | `GATEWAY-PROGRAM`=NOT-FOUND (dep is prose: "do NOT start until routing_policy/ interface has stabilized & Wave-1 merged") | **STILL BLOCKED (dep ID not resolvable — UNKNOWN whether the prose gate has cleared)** |
| `FT-WIRE-QUOTA` | (none) | `FT-QUOTA-ENGINE`=DONE, `FT-CONFIG-SURFACE`=DONE, `FT-CATALOG-SEED`=SUBMITTED(in-flight), `FAIL-LOUD-CONTRACT`=DONE, `FORWARDER-RECONCILE`=DONE, `PROVIDER-PROBE-FIX`=DONE, `GATEWAY-NONTOKEN-METERING`=SUBMITTED(in-flight) | **STILL BLOCKED** |
| `CREATION-GATE-DECOMPOSE-WIRE` | (none) | `PROJECT-MEMBERSHIP-GATE`=SUBMITTED(in-flight), `PRIORITY-CONSOLIDATION`=DONE | **STILL BLOCKED** |
| `DONE-SH-INTEGRITY-FIX` | (none) | `GITHUB-LIMITS-HARDENING`=SUBMITTED(in-flight), `VERIFY-MERGED-REPO-AWARE`=DONE | **STILL BLOCKED** |
| `REPO-MAP-CONVERGE` | (none) | `VERIFY-MERGED-REPO-AWARE`=DONE, `REPO-FIELD-REQUIRED`=SUBMITTED(in-flight), `REPO-DECL-CENTRAL`=DONE, `SYNC-SCHEDULE`=SUBMITTED(in-flight), `GH-SEAM-CHOKEPOINT`=DONE | **STILL BLOCKED** |
| `CG-LAN-OPEN-UI` | (none) | (none) | **DISPATCHABLE NOW** |
| `GITEA-ACTIONS-CI-SPIKE` | (none) | (none) | **DISPATCHABLE NOW** |
| `MARKER-PROOF-MECHANIZE` | (none) | `DONE-SH-INTEGRITY-FIX`=OPEN-ON-BOARD, `GITHUB-LIMITS-HARDENING`=SUBMITTED(in-flight), `FOREMAN-WIRE`=DONE, `REPO-MAP-CONVERGE`=OPEN-ON-BOARD, `BENCH-OOB-GRADING`=SUBMITTED(in-flight) | **STILL BLOCKED** |
| `PRODUCT-GRADES-STORE` | (none) | (none) | **DISPATCHABLE NOW** |
| `WIRE-BRAIN-INTO-GATEWAY` | (none) | `PRODUCT-GRADES-STORE`=OPEN-ON-BOARD | **STILL BLOCKED** |
| `REACHABILITY-AUDIT-LAND` | (none) | `REACHABILITY-GATE`=SUBMITTED(in-flight) | **STILL BLOCKED** |
| `WIP-CLOSE-GATE` | (none) | `SESSION-END-PUSH-GATE`=SUBMITTED(in-flight) | **STILL BLOCKED** |
| `PEAK-PRICING-AWARE` | (none) | `PRICING-LIMITS-CHECK-SH`=SUBMITTED(in-flight) | **STILL BLOCKED** |

### Summary

- **DISPATCHABLE NOW: 17** (8 in Thread A, 9 in Thread B)
- **STILL BLOCKED: 24**

Dispatchable-now, ordered by priority then mint date:

| # | Ticket | Priority | Tier | Minted | Thread |
|---|---|---|---|---|---|
| 1 | `RETIRE-FINAL-E2E-REVIEW` | 0 | strong | 2026-07-23 | B |
| 2 | `DEADCODE-TOOLS-WIRE` | 0 | strong | 2026-07-31 | A |
| 3 | `FORWARDER-COST-ORDER-FALLBACK` | 0 | strong | 2026-07-31 | A |
| 4 | `KSF-LOAD-BEARING` | 0 | frontier | 2026-07-31 | A |
| 5 | `LOOP-GUARD-REASON-WIRE` | 0 | economy | 2026-07-31 | A |
| 6 | `SHARED-NAMESPACE-CONTENTION` | 0 | strong | 2026-07-31 | A |
| 7 | `TOOL-COMPOSITION-LAYER` | 0 | frontier | 2026-07-31 | A |
| 8 | `GATEWAY-GRADE-ORDER-MVP` | 1 | strong | 2026-07-20 | B |
| 9 | `RECONCILE-HANDOFF-FRESHNESS` | 1 | strong | 2026-07-23 | B |
| 10 | `SINGLE-LEG-AUTOSWAP` | 1 | strong | 2026-07-23 | B |
| 11 | `AUTO-DONE-ON-MERGE-MISS` | 1 | strong | 2026-07-31 | A |
| 12 | `STOP-WORKER-GRACEFUL-EXIT` | 1 | strong | 2026-07-31 | A |
| 13 | `WORK-ROUTING-TO-CHARON-ENGINE` | (none) | frontier | 2026-07-09 | B |
| 14 | `DRAIN-THEN-PARK` | (none) | frontier | 2026-07-13 | B |
| 15 | `CG-LAN-OPEN-UI` | (none) | strong | 2026-07-19 | B |
| 16 | `GITEA-ACTIONS-CI-SPIKE` | (none) | strong | 2026-07-19 | B |
| 17 | `PRODUCT-GRADES-STORE` | (none) | strong | 2026-07-19 | B |

### Notable blocking structure

- **The DISCOVERY chain is self-blocking end to end.** `DISCOVERY-NORMALIZE` waits on
  `DISCOVERY-SOURCE-ADAPTERS` (SUBMITTED — in flight, closest to clearing); `DISCOVERY-DIFF` waits on
  `NORMALIZE`; `DISCOVERY-QUEUE` waits on `DIFF`; `DISCOVERY-APPROVAL-WIRE` waits on `QUEUE`;
  `DISCOVERY-CADENCE` waits on `APPROVAL-WIRE`. Landing `DISCOVERY-SOURCE-ADAPTERS` unblocks the chain
  head and nothing else will.
- **Fourteen distinct blockers are already SUBMITTED**, i.e. in flight rather than unstarted: `SYNC-SCHEDULE`,
  `BENCH-OOB-GRADING`, `GITHUB-LIMITS-HARDENING`, `REPO-FIELD-REQUIRED`, `RECONCILE-REVIEW-GATE`,
  `CAPTURE-WIRING-TIMEOUT-FIX`, `PROJECT-MEMBERSHIP-GATE`, `REACHABILITY-GATE`, `SESSION-END-PUSH-GATE`,
  `PRICING-LIMITS-CHECK-SH`, `FT-CATALOG-SEED`, `GATEWAY-NONTOKEN-METERING`, `ADD-PROVIDER-MECHANIZE-COMPLETE`,
  `DISCOVERY-SOURCE-ADAPTERS`. Merging that submitted queue would convert a large share of the
  STILL-BLOCKED column to dispatchable in one pass.
- **`REVIEWER-TAB-POOL` blocks two p0 tickets** (`HANDOFF-GATE-NONBYPASSABLE`, `MODEL-HARDCODE-PURGE`)
  and is itself only OPEN-ON-BOARD — it is not in this never-dispatched set, but it is the single
  highest-leverage unblock for p0 work.
- **`POST-GATEWAY-WCI-DECOMPOSE` — UNKNOWN.** Its `depends_on:` names `GATEWAY-PROGRAM`, which exists
  nowhere in `fleet/state/done/`, `fleet/board/`, or `fleet/board/archive/`. The rest of the field is
  prose, not a ticket ID. Whether its gate has cleared cannot be determined mechanically.
