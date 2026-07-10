# Design-Work Tracking + Relevance Audit (build-RIG)

**Date:** 2026-07-08 · **Scope:** `/home/stack/charon-private/fleet/*.md` + `fleet/board/` + `fleet/scratch/`
**Present state anchors:** product v0.3.6 · benchmark PIVOT to real-outcomes CONFIRMED (synthetic S0–S6 demoted to smoke-test) · pools redesign (~50→~4) = design-of-record UNBUILT · failover root-fix in flight · coordinator-doctrine-v2 APPROVED+committed, rollout UNTRACKED.
**Rule:** RECOMMEND ONLY. Nothing deleted, no tickets filed/modified, no commits. Dropping design work is the operator's call.

Key mechanism discovered: `fleet/state/done/` holds DONE markers for ~80 tickets. Any design doc whose build ticket has a done-marker is a RECORD now, not pending work. Verified against that directory throughout.

---

## Triage table — (B) design-only docs (the real targets)

| Doc | Class | Ticketed? | Relevance now | Disposition | Rationale |
|---|---|---|---|---|---|
| AUTH-GUI-DESIGN.md | B | YES → GUI-SVELTE-BUILD (owns "GUI-AUTH-1 per AUTH-GUI-DESIGN.md"), NOT done | current | **ALREADY-TICKETED** | Live design for an open build ticket; keep. |
| GUI-API-SURFACE.md | B | YES → GUI-SVELTE-BUILD (owns "close 2 read-side gaps GUI-API-SURFACE found"), NOT done | current | **ALREADY-TICKETED** | Feeds the open Svelte GUI build. |
| POOLS-REDESIGN-ADR-v2.md | B | YES → POOLS-SIMPLIFICATION + COST-RANK-AUTO + DRAIN-ROUTING (all open, none done) | current, design-of-record | **ALREADY-TICKETED** | The authoritative pools ADR; 3 open tickets implement it. Keep. |
| SR-6-DESIGN.md | B | YES → SR-6 (open) + SR-6-Phase2 (parked) | current | **ALREADY-TICKETED** | Prompt-cache injection design for open SR-6. Keep. |
| DSGN-WCI-reshape.md | B | YES → WCI + WCI-FOLLOWON (BOTH done) | BUILT | **ALREADY-TICKETED (done→record)** | Reshape shipped as engine work; now a record. No action. |
| DSGN-WCI-5-1-PROOF.md | B | Partial → DSGN-WCI-PROOF.md.**parked**; semantic_proof.py shipped under WCI-FOLLOWON (done) | BUILT | **MODIFY (close stale ticket)** | Proof design was built via WCI-FOLLOWON, yet DSGN-WCI-PROOF ticket still sits parked → close/annotate it. |
| SR-8-RECS.md | B | YES → SR-8 (done) | BUILT | **ALREADY-TICKETED (done→record)** | All 6 dead modules wired per recs. Record. |
| MODEL-BENCHMARK-SPEC.md | B | YES → TICKET-BENCHMARK-HARNESS (built; see scratch v2-scoring/harness-hardening reports) | BUILT but **superseded as ranker** | **MODIFY + SALVAGE** | Harness built+run, then synthetic S0–S6 DEMOTED to smoke-test by the confirmed pivot. Annotate "smoke-test only, superseded as ranking brain by BENCH-REGROUND-LIVE/BENCH-REDS-REPLAY/BENCH-OOB-GRADING". SALVAGE the work-class taxonomy + S6 frontend fixture (still the only frontend signal). |
| TICKET-BENCHMARK-HARNESS.md | B | YES (built) | output demoted by pivot | **ALREADY-TICKETED (done→record)** | Harness exists; keep as record, note demotion. |
| DURABLE-BRIDGE-DESIGN-v3.md | B | **NO board ticket** (Phase 0–1 BUILT in `~/.config/opencode/session-bridge/`; Phase 2 pending) | current, build-ready | **KEEP+ticket** | Live rig design; Phase 2 is designed+briefed but untracked on the board. **File a ticket.** |
| DURABLE-BRIDGE-PHASE-2-BRIEF.md | B | **NO board ticket** | current, build-ready | **KEEP+ticket** | This brief IS ready-to-file ticket content (push watcher + observability + wiring). Same gap as v3 above — one ticket covers both. |
| OBOL-PHASE-1-DESIGN.md | B | **NO ticket** (product-WCI deferred by decision: memory wci-rig-enforced-product-deferred) | valid, deferred | **KEEP (deferred, no ticket)** | Product-side obol store; intentionally parked until production-ready. Confirm it stays design-only vs. a tracking placeholder. |
| PLAN-PORTABLE-ORCHESTRATION-STORE.md | B | **NO ticket** (obol impl plan v2, DTC-reworked) | valid, deferred | **KEEP (deferred, no ticket)** | Companion impl plan to OBOL-PHASE-1; subsumes BRIDGE-DAEMON-PROPOSAL. Keep with obol. |
| SMART-ROUTING.md | B | Partial → SR-8 (done wired the 6 modules) + SR-* series | north-star, mostly built | **KEEP (reference/north-star)** | Grounding vision; still the routing north-star. No new ticket. |
| DTC-tier-abstraction.md | B | Partial → TIER-SELECT (done); tiers.json concept | partly superseded by POOLS-ADR-v2 | **SALVAGE → POOLS-REDESIGN** | Extract the durable ideas (canonical low/med/high vocab as truth; separate `tiers.json` file to avoid the strict `pools.json` dual-consumer crash) into the pools redesign, then drop. |
| PROPOSAL-1-COST-AWARE-ROUTING.md | B | Absorbed → POOLS-REDESIGN-ADR-v2 + COST-RANK-AUTO | superseded | **SALVAGE→DROP** | Content folded into pools redesign + cost-rank ticket; confirm nothing unique remains, then archive. |
| REDEPLOY-PLAN.md | B | operational (no board ticket) | version-stale (v0.3.3 vs live v0.3.6) | **MODIFY / SALVAGE→RUNBOOK** | Redeploy is a recurring op but this snapshot is stale; fold the durable steps into RUNBOOK.md, drop the version-specific body. |
| SETTINGS-GUARD-PROPOSAL.md | B | operator-apply (`~/.claude`, not a board ticket) | fix already applied (auto-compact ON) | **KEEP (operator action)** | The loud-guard itself is unbuilt; low value now. Operator's own settings change, never a droid ticket. |
| BRIDGE-DAEMON-PROPOSAL.md | B | (was pre-durable-bridge) | superseded | **DROP** | DURABLE-BRIDGE-DESIGN explicitly "supersedes/extends" it; the daemon shipped as the durable bridge. |
| BRIDGE-IMPROVEMENT-PLAN.md | B | BRIDGE-HARDEN (done) | superseded | **DROP** | Superseded by BRIDGE-HARDEN (done) + the durable-bridge redesign. |
| DTC-backchannel.md | B | — | superseded | **DROP** | droid→manager back-channel now exists as the bridge nudge/ack/board RPCs. |
| DURABLE-BRIDGE-DESIGN.md (v1) | B/A | — | superseded | **DROP** | Superseded by v3 (v1→v2→v3 chain). Keep only v3. |
| DURABLE-BRIDGE-DESIGN-v2.md | B/A | — | superseded | **DROP** | Superseded by v3. |
| POOLS-REDESIGN-ADR.md (v1) | B | — | superseded | **DROP** | v2 explicitly supersedes it (REWORK verdict). |
| POOLS-EDIT-PLAN.md | B | — | executed + superseded | **DROP** | The manual free/cheap stack it planned was hand-deployed (per OUTSTANDING-TICKETS); redesign supersedes the manual approach. |
| PROPOSAL-2-SESSION-COMMUNICATION.md | B | — | superseded | **DROP** | DURABLE-BRIDGE-DESIGN lists it as superseded/extended. |
| OPTIMIZATION-PASS.md | B/C | — | stale snapshot (2026-06-28 backlog) | **DROP** | Superseded by REMAINING-WORK-OPTIMIZED + later board state. |
| ADOPT-GATEWAY-FEATURES.md | B | Absorbed → SR-8 (done) + RFL-1..5 + pools tickets | mostly built/absorbed | **SALVAGE→DROP** | The concrete adopt-list became SR-8 (done) + RFL tickets; keep as reference until confirmed fully mapped, then archive. |

### (A) records of DONE work / (C) reference — classified by title+skim, no triage needed
- **(A) records:** HANDOFF-2026-07-0{4,4-v2,5,6,8}.md, all SESSION-*.md (SESSION-A/B/…, SR-6/7/8, RFL, TIER-SELECT, DRAIN-BALANCE, TOOL-REPAIR, STRIP-REASONING…), SLOP-HANDOFF.md, AUDIT-2026-06-27.md, all `scratch/*-report.md` and `*-review.md` (build/review records), OUTSTANDING-TICKETS.md, REMAINING-WORK-OPTIMIZED.md.
- **(C) reference/analysis/process (no build implied):** README, BOOTSTRAP, BRIEF-TEMPLATE, JOIN-PROMPT, START-SESSION, WORKFLOW, RUNBOOK, CROSS-SESSION-REVIEW-PROTOCOL, PROPOSED-SEQUENCE, DESIGN-QUEUE (meta index), COORDINATOR-DOCTRINE-v2 (approved doctrine — but see rollout gap below), BENCHMARK-VALIDITY-REVIEW (drove the pivot — now acted on), all DURABLE-BRIDGE-REVIEW{,-v2,-v3}, POOLS-REDESIGN-REVIEW, EVAL-RelayFreeLLM, RELAYFREELLM-COMPARISON, X-POST-EVAL, SESSION-BRIDGE-PRODUCT-EVAL, PAID-PLANS-REVIEW, MODEL-ROLE-EVALUATION, MODEL-WORK-MATRIX, MISSING-MODELS-PROVIDERS, OPENCODE-MODEL-LIST-GAP, FREE-TIER-ROUTING, CI-ACTION-BUMP-INVESTIGATION, MODEL-BENCHMARK-SPEC §0 taxonomy, scratch research-* and pools-analysis/attribution.

---

## STEP 4 surfacing

**(a) Design-only, build-ready, NO ticket (should have one):**
1. **Durable bridge Phase 2** — DURABLE-BRIDGE-DESIGN-v3 (Phase 0–1 built) + DURABLE-BRIDGE-PHASE-2-BRIEF give a complete, review-passed build spec, but there is **no board ticket**. BRIDGE-HARDEN (done) covered the OLD `server.py`, not this. Highest-value tracking gap.

**(b) Tickets referencing a now-stale design:**
1. **DSGN-WCI-PROOF.md.parked** — its design (DSGN-WCI-5-1-PROOF) was already built via WCI-FOLLOWON (done). Stale-parked; close or annotate.
2. **MODEL-BENCHMARK-SPEC / TICKET-BENCHMARK-HARNESS (built)** — synthetic S0–S6 demoted to smoke-test by the confirmed pivot; the 6 **BENCH-\*** pivot tickets (REGROUND-LIVE, REDS-REPLAY, OOB-GRADING, AGGREGATE-N, DIFFICULTY-CAL, PROVISIONAL-SCORING) are **all parked** even though the pivot is CONFIRMED. Pivot direction is untracked-as-active.

**(c) Doctrine-v2 rollout gap (known):** COORDINATOR-DOCTRINE-v2.md is committed + APPROVED, but its ROLLOUT has no board ticket. File one.

**(d) Good ideas inside droppable/demoted docs — preserve before archiving:**
- DTC-tier-abstraction: canonical `low/med/high` as the one truth (aliases only) + separate `tiers.json` to avoid the strict `pools.json` loader crash → into POOLS-REDESIGN.
- MODEL-BENCHMARK-SPEC: work-class taxonomy + **S6 frontend fixture** (only frontend signal we have) → keep for the pivot's live-outcomes grading.
- REDEPLOY-PLAN: the volume/secrets-on-`/data` verification steps → into RUNBOOK.
- PLAN-PORTABLE-ORCHESTRATION-STORE / OBOL: derived-readiness + epoch-fenced claim primitives → preserved by keeping obol design intact.

---

## Recommended actions (prioritized) — operator confirms each

1. **FILE:** `DURABLE-BRIDGE-PHASE-2` board ticket from DURABLE-BRIDGE-PHASE-2-BRIEF (push watcher + observability + wiring cleanup). Build-ready, review-passed, currently untracked.
2. **FILE:** `COORDINATOR-DOCTRINE-ROLLOUT` ticket (doctrine-v2 approved, rollout untracked — the known gap).
3. **DECIDE (pivot tracking):** un-park the active pivot tickets (BENCH-REGROUND-LIVE + BENCH-OOB-GRADING at minimum) and annotate MODEL-BENCHMARK-SPEC/HARNESS as "smoke-test only, superseded as ranker." Salvage the S6 frontend fixture + work-class taxonomy first.
4. **CLOSE/ANNOTATE:** DSGN-WCI-PROOF.md.parked (its design shipped via WCI-FOLLOWON, done).
5. **SALVAGE then DROP:** DTC-tier-abstraction → POOLS-REDESIGN; PROPOSAL-1-COST-AWARE-ROUTING → POOLS-REDESIGN/COST-RANK; ADOPT-GATEWAY-FEATURES → confirm mapped to SR-8/RFL then archive; REDEPLOY-PLAN steps → RUNBOOK.
6. **DROP (superseded, operator-confirm archive):** BRIDGE-DAEMON-PROPOSAL, BRIDGE-IMPROVEMENT-PLAN, DTC-backchannel, DURABLE-BRIDGE-DESIGN (v1), DURABLE-BRIDGE-DESIGN-v2, POOLS-REDESIGN-ADR (v1), POOLS-EDIT-PLAN, PROPOSAL-2-SESSION-COMMUNICATION, OPTIMIZATION-PASS.
7. **KEEP as-is (deferred by decision, confirm still deferred):** OBOL-PHASE-1-DESIGN + PLAN-PORTABLE-ORCHESTRATION-STORE (product obol) and SMART-ROUTING (north-star). SETTINGS-GUARD-PROPOSAL stays an operator-only settings note.

---

## Coverage note
Full triage completed for the entire (B) design-only set (28 docs). (A) records and (C) reference/process docs classified by title + skim (not line-by-line). Board cross-referenced against `state/done/` markers and parked/active status. Not independently re-verified: the exact on-disk build state of the durable-bridge daemon files (relied on the Phase-2 brief's own "Phase 0–1 BUILT" statement) and whether every ADOPT-GATEWAY-FEATURES sub-item maps to a shipped SR-8/RFL ticket (recommended a confirm-then-archive rather than blind drop).
