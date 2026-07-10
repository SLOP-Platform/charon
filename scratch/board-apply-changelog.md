# Board-apply changelog — single board-writer pass (2026-07-08)

Executed by the single board-writer sub-session. NOTHING committed or pushed — manager lands via land-push.
Final `validate_board.sh`: **GREEN** (exit 0). Started from 5 pre-existing GUI-SVELTE-BUILD reds; ends GREEN.

---

## TASK 1 — Unblock Phase-1 (park + rebase setup)

Pre-check: session-bridge board = only the stalled manager session (satele-shan), NO droid/claim active.
`state/claims/` empty. Safe — sequencing decision, not a live race.

**Un-parked (→ live .md):**
- PROXY-FAILOVER-FIX (now the SOLE live owner of `src/charon/proxy_server.py`; board GREEN on that file).

**Parked the 8 live proxy_server.py owners (→ .md.parked), each with a `rebase-after: PROXY-FAILOVER-FIX` note:**
- GUI-SVELTE-BUILD (mandatory), DRAIN-ROUTING, INC-401-FAILOVER, RFL-2, RFL-3, RFL-4, SR-13, SR-6.

**UNANTICIPATED SIDE-EFFECT + resolution:** parking those 8 orphaned 7 downstream `depends_on` edges
(new bad-dep reds). Resolved:
- Parked 3 more LIVE dependents (blocked by the parked deps anyway; also own config.py/gateway.py in the
  same cluster), each with a `rebase-after: PROXY-FAILOVER-FIX` note:
  **COST-RANK-AUTO** (dep DRAIN-ROUTING), **GPT5-POOL-REORDER** (dep INC-401-FAILOVER),
  **POOLS-SIMPLIFICATION** (dep DRAIN-ROUTING + COST-RANK-AUTO).
- Pruned the single dangling parked-dep id from 4 DONE tickets (historical proxy_server.py merge-order
  seq, already satisfied; added a `dep-pruned:` annotation to each; no restore needed on un-park):
  **REQUEST-NORMALIZER** (dropped INC-401-FAILOVER), **RFL-1** (dropped SR-13),
  **SR-7** (dropped SR-6 → SR-2,SR-5), **SR-8** (dropped SR-6 → SR-2,SR-7).

**REBASE-AFTER-MERGE list (un-park + rebase on top once PROXY-FAILOVER-FIX merges) — 11 tickets:**
GUI-SVELTE-BUILD, DRAIN-ROUTING, INC-401-FAILOVER, RFL-2, RFL-3, RFL-4, SR-13, SR-6,
COST-RANK-AUTO, GPT5-POOL-REORDER, POOLS-SIMPLIFICATION.

**Operator launch command (board is GREEN — ready):**
```
bash /home/stack/charon-private/fleet/fleet-droid.sh strong --wait 3 --retries 10
```
(tier `strong` per the ticket. fleet-droid.sh does not itself gate on validate — manager runs
validate_board.sh as the preflight gate, which is GREEN.)

---

## TASK 2 — Design-audit dispositions

**Filed 2 new .parked tickets (board schema + D&S):**
- DURABLE-BRIDGE-PHASE-2.md.parked — Phase 2 (push watcher + observability + wiring cleanup); prompt
  points at fleet/DURABLE-BRIDGE-PHASE-2-BRIEF.md (note: add a `## Dependencies & sequence` section to
  the brief before un-park, or D&S check REDs; owns are bridge daemon paths — re-confirm at activation).
- COORDINATOR-DOCTRINE-ROLLOUT.md.parked — doctrine-v2 rollout into rig injected-rules + SLOP AGENTS.md.
  **owns = TBD-CONFIRM** (no injected-rules file exists in the rig yet; searched — none found). prompt=TBD.

**Un-parked bench pivot tickets (→ live .md):**
- BENCH-REGROUND-LIVE (dep-root, depends_on empty).
- BENCH-OOB-GRADING — its hard `depends_on: BENCH-PROVISIONAL-SCORING` (#20, still parked) was CONVERTED
  to `build-after: BENCH-PROVISIONAL-SCORING` (a hard depends_on to a parked ticket would trip the
  validator). RESTORE the depends_on when #20 un-parks. Also blocked on operator decision Q1 (substrate).
- Kept parked: BENCH-PROVISIONAL-SCORING, BENCH-AGGREGATE-N, BENCH-DIFFICULTY-CAL, BENCH-REDS-REPLAY.
- **Authored 2 missing prompt files** (they did NOT exist → would have caused missing-prompt reds):
  `prompts/bench-reground-live.md` + `prompts/bench-oob-grading.md`, grounded in the ticket scope +
  authoritative `/home/stack/charon-private/scratch/pivot-implementation-plan.md` (§0/§1/§7 and §3).
  Both carry a `## Dependencies & sequence` section + last-step commit rule. RIG-ONLY.

**Archived 9 recommend-DROP docs (→ fleet/archive/, each with a `> ARCHIVED 2026-07-08 — superseded by X` banner):**
BRIDGE-DAEMON-PROPOSAL, BRIDGE-IMPROVEMENT-PLAN, DTC-backchannel, DURABLE-BRIDGE-DESIGN (v1),
DURABLE-BRIDGE-DESIGN-v2, POOLS-REDESIGN-ADR (v1), POOLS-EDIT-PLAN, PROPOSAL-2-SESSION-COMMUNICATION,
OPTIMIZATION-PASS.

**Salvaged-then-archived (audit enumerates 5 salvage docs, NOT 6 — see attention note):**
- DTC-tier-abstraction → salvaged canonical low/med/high vocab + separate-tiers.json idea INTO
  POOLS-REDESIGN-ADR-v2.md ("Salvaged design ideas" section); archived.
- PROPOSAL-1-COST-AWARE-ROUTING → salvaged cost-aware-routing north-star INTO POOLS-REDESIGN-ADR-v2.md;
  confirmed no unique unabsorbed mechanism; archived.
- ADOPT-GATEWAY-FEATURES → confirmed absorbed into SR-8 (done) + RFL-1..5; provenance in banner; archived.
- REDEPLOY-PLAN → salvaged durable /data-volume + release/deploy/rollback steps INTO RUNBOOK.md
  ("Release + redeploy runbook" section); archived (stale v0.3.3→v0.3.4 body dropped).
- MODEL-BENCHMARK-SPEC → **KEPT as a record** (audit disposition), annotated at top "smoke-test only,
  superseded as ranker"; salvage note preserves the §0 work-class taxonomy + S6 frontend fixture.

**Closed:**
- DSGN-WCI-PROOF.md.parked → `> CLOSED 2026-07-08 — shipped via WCI-FOLLOWON` banner; moved to
  fleet/archive/ (no board .closed/.done suffix convention exists).

---

## TASK 3 — Scope updates on PROXY-FAILOVER-FIX (now live)

- P3 scope GENERALIZED (decision #4): balance-aware demotion → RESOURCE-AVAILABILITY monitoring =
  balance (paid: nanogpt/openrouter) + quota/rate-remaining (free tiers); "use free-tier resources up
  to their daily/weekly/monthly limits, spill when exhausted"; ALERT when nanogpt AND openrouter both
  run low (capability catch — closed pools have no other backstop).
- Added PRIORITY NOTE (decision #2): P2 (cross-model/tier substitution) is THE priority durable fix for
  closed-pool resilience (P1 stops the stall but doesn't restore service; P2 keeps requests flowing).

---

## TASK 4 — Catalog reconcile

- Filed CATALOG-RECONCILE-GPT5.md.parked (owns src/charon/model_catalog.py; work_class=bugfix;
  route=droid/product). Confirmed the mismatch: model_catalog.py line ~48 = `gpt-5.5` tier_hint="high",
  but the live in-window incumbent is `gpt-5.4` (an incumbent-under-test, not a finalized workhorse; routed via nanogpt/openrouter config, not the catalog). Scope
  flags the OPEN QUESTION (determine source of truth via git history + live config intent BEFORE editing;
  do not blindly rename). prompt=TBD.
- Updated CATALOG-SYNC-DRIFT (#30) scope with the STANDING RULE: catalog/routing/config mismatches must
  ALWAYS be fixed; the drift detector must surface them automatically.

---

## COUNTS
- Parked (live → .parked): 11  (8 owners + 3 downstream dependents)
- Un-parked (.parked → live): 3  (PROXY-FAILOVER-FIX, BENCH-REGROUND-LIVE, BENCH-OOB-GRADING)
- Filed (new .parked): 3  (DURABLE-BRIDGE-PHASE-2, COORDINATOR-DOCTRINE-ROLLOUT, CATALOG-RECONCILE-GPT5)
- Archived: 14  (9 DROP + 4 salvage + 1 closed DSGN-WCI-PROOF)
- Closed: 1  (DSGN-WCI-PROOF)
- Salvaged sources: 5  (4 archived + MODEL-BENCHMARK-SPEC kept-as-record)
- Scope-edited: 2  (PROXY-FAILOVER-FIX, CATALOG-SYNC-DRIFT)
- Done-ticket deps pruned: 4  (REQUEST-NORMALIZER, RFL-1, SR-7, SR-8)
- Prompts authored: 2  (bench-reground-live, bench-oob-grading)

## FINAL BOARD: GREEN (validate_board.sh exit 0). No new reds vs the cleared GUI-SVELTE-BUILD set.

## NEEDS MANAGER/OPERATOR ATTENTION
1. Parked cluster is 11, not 8 — parking the 8 owners forced parking 3 downstream dependents
   (COST-RANK-AUTO, GPT5-POOL-REORDER, POOLS-SIMPLIFICATION) and pruning stale deps from 4 DONE tickets.
   All un-park together in the rebase-after-merge follow-up.
2. Bench prompts were MISSING — I authored minimal ones from the pivot plan. REVIEW them before launch.
   BENCH-OOB-GRADING depends_on #20 was softened to build-after (restore when #20 un-parks) + it is
   still Q1-blocked (do not build yet).
3. Salvage count: audit enumerates 5 salvage docs, not 6. All 5 handled (4 archived, MODEL-BENCHMARK-SPEC
   kept-as-record per audit). Flag if a 6th was intended.
4. 3 new .parked tickets carry prompt=TBD / brief-without-D&S / owns=TBD — resolve BEFORE un-park or the
   validator will RED (missing-prompt / D&S / owns). COORDINATOR-DOCTRINE-ROLLOUT needs operator to
   confirm the rig injected-rules + SLOP AGENTS.md paths.
5. Nothing committed/pushed. Some fleet docs were untracked (plain mv); board tickets + tracked docs used
   git mv. Manager lands the whole batch via land-push.
