# Charon Fleet — Session Handoff — quinlan-vos (session END)

> Per-session handoff. Next session reads ALL `SESSION-HANDOFF-*.md`. This one is the ACTIVE priority.

## Bootstrap (paste into the next session)
```
Read fleet/SESSION-HANDOFF-quinlan-vos.md in full and follow it — push the EVAL-* fix-sequence to completion in autonomous mode, continuing quinlan-vos's work exactly where it stopped.
```

## Provenance
**Session:** quinlan-vos
**Generated:** 2026-07-15
**Rig branch:** `feat/live-lane-finalizer` (all this session's commits; NOT pushed — operator pushes)
**Rig HEAD:** `4299448` · **Product master:** `b7aa4c8`

---

## THE MISSION (why the next session exists)
Get Charon's **model-testing / evaluation system FULLY WORKING** — i.e. it VALIDLY discriminates *which model, on which leg, at which cost, for which skill, is trusted*, cheaply and without wasted tokens. An adversarial review this session (`fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md`, Opus, grounded file:line) found the current system has **3 BLOCKERs** that make its output largely invalid. The operator wants **ALL** the fix tickets done, **any issues that arise done too**, running **autonomous, max-parallel, no idle time**, until it fully works.

**Definition of "fully working" (acceptance):** all 8 EVAL-* tickets merged AND: (a) a budget-breaching run is DETAINed for latency, not passed; (b) the OOB grader actually runs so MUST-PASS/MUST-FAIL controls discriminate; (c) ONE taxonomy the product router can consume; (d) budgets DERIVED (p95/token-normalized), not 3/6/10 arbitrary; (e) per-(model×LEG) ranking via leg-pinning; (f) ONE consolidated adaptive pipeline (not 5 harnesses) producing per-(model×skill) ceilings; (g) promotion + live rows gated on the control-panel split. Prove each with its FAIL-ON-REVERT test.

---

## THE PRIORITY — EVAL fix-sequence (the wave plan, already D&S-sequenced, board GREEN)
Regenerate anytime with: `bash fleet/launch-plan.sh EVAL-LATENCY-GATE EVAL-TAXONOMY-ALIGN EVAL-GRADER-PROVISION LEG-PREFLIGHT-CANARY EVAL-DERIVED-BUDGETS EVAL-TIER-CANON EVAL-PIPELINE-CONSOLIDATE EVAL-PROMOTION-GATE`

- **Wave 1 (launch NOW, 4 parallel, collision-free)** — all strong, assign.py→deepseek-v4-pro (low-conf; use judgment):
  - `EVAL-LATENCY-GATE` (F1+F4+F-attr2) — charon-run emits self-describing rc=124 marker; dogfood-eval GATES on elapsed≥budget→DETAIN(latency); fix dead attribution strings. Small, highest leverage.
  - `EVAL-TAXONOMY-ALIGN` (F3, BLOCKER) — pick ONE taxonomy = product router semantic classes; repoint grades.py; write fleet/state/EVAL-TAXONOMY.md. **Everything downstream depends on this.**
  - `EVAL-GRADER-PROVISION` (F2, BLOCKER) — provision bench-grader pytest + fix snapshot perms so the OOB battery actually grades; build the MUST-PASS/MUST-FAIL control self-test. **Needs operator sudo** (bench-grader user) — see GRADER-PROVISION-NOTE.md the droid writes.
  - `LEG-PREFLIGHT-CANARY` (F6+F14) — build leg-preflight.sh from `fleet/state/leg-canary-prototype.py`; leg-pinning end-to-end; LEG-RANK.tsv; sandbox the exec; sweep skips non-HEALTHY legs.
- **Wave 2 (after TAXONOMY)**: `EVAL-DERIVED-BUDGETS` (F8), `EVAL-TIER-CANON` (F-tier).
- **Wave 3**: `EVAL-PIPELINE-CONSOLIDATE` (F9+F12 — the big one, one adaptive item-bank pipeline; decompose into build-chunks at start), then `EVAL-PROMOTION-GATE` (F10+F13).
- Also fold F15 (wire the product-side slow-axis hold `is_slow_provider`) into the GRACEFUL-DEGRADE / S8 build — inert today (`fleet/state/S8-GRACEFUL-DEGRADE-DESIGN.md`).

Every EVAL ticket's `accept:` cites its review §F-number; the full grounded fix + file:line is in the review file. Trust the review, not memory.

---

## HOW to execute (operator's explicit instructions)
- **Autonomous, no idle.** Keep concurrent collision-free work flowing up to review capacity; as a wave's deps clear, launch the next. `[keep-the-hopper-full]`
- **Max parallel, min wall-clock.** Drive launches from `fleet/launch-plan.sh` (decompose→parallelizability→assign, model-named, collision-free) + `fleet/stale-check.sh` to catch spun/stale sessions. This is the mechanized launch discipline — USE IT, don't hand-divide. `[LAUNCH-PLAN-GATE, built this session]`
- **Right-size every agent/model.** Delegate substantive builds to droid sessions / sub-sessions; the MANAGER only gates/sequences/commits/dialogues. Read-only research → Sonnet; design → Sonnet (Opus only high-stakes money-path); adversarial money-path verify → Opus. Never default to Opus. `[subsession-model-and-token-policy, background-job-launch-discipline]`
- **Sub-sessions return a FILE pointer + ≤5-line summary, never the full report.** `[coordinator-token-economy-doctrine]`
- **The manager never spawns droids** (operator opens tabs); manager sub-agents = manager work only. Product/rig BUILDS → droid tabs via the wave plan.
- **Verify, don't trust the SUCCESS line.** This session I twice stated a wrong "throttled" cause from a label, and the review found the too-slow path is dead code — confirm every claim against real logs/diffs. `[document-model-self-report-lies]`
- **Pair every detached run with a tracked waiter**; launch long bg jobs DIRECTLY via run_in_background (no nohup/&). `[background-job-launch-discipline]`

## Operator actions (queued in fleet/pending.sh — R/S/T + new)
1. `! git -C /home/stack/charon-private push -u origin feat/live-lane-finalizer` (push deny-listed to manager) — 12 commits this session.
2. **EVAL-GRADER-PROVISION needs bench-grader sudo** provisioning (pytest + perms) — the droid writes the exact commands to GRADER-PROVISION-NOTE.md.
3. Frontier tier still funding-blocked (nanogpt/openrouter). Optional scorecard conflict-marker cleanup (action T).
4. NVIDIA NIM cleanup (Task 10): fix add-provider.sh step4 --base-url false-FAIL + add-provider-interactive key-echo; add NIM limits to free_tier_catalog.

---

## What this session (quinlan-vos) delivered (context)
- **Fixed the reporting loop (the real "runners not reporting back")**: `finalize_live_capture` in dogfood-eval.sh (clean runs now land active scorecard rows) + `done.sh` prefixed-ref/loud-finalize. Committed, tested.
- **Ran the honest-battery sweep** (8 non-Anthropic models × 3 tickets) → live lane 13→~24 rows. BUT the review shows those grades are shaky (wrong taxonomy, no latency gate, 1 skill in 3 labels) — treat as provisional.
- **NVIDIA NIM added + verified** (restart fixed routing; Nemotron-3-Super/Ultra/Nano: healthy, 1.9-2.5s, 5/5 canary). Cleanup pending (Task 10).
- **Designed the eval architecture** the operator drove: leg-canary R0 → staged elimination ladder R1-R3 → per-(model×skill) ceiling → derived budgets → adaptive placement. Then adversarially reviewed it (found the 3 BLOCKERs) → this EVAL fix-sequence.
- **Built LAUNCH-PLAN-GATE** (fleet/launch-plan.sh + stale-check.sh) — use it.
- Parked minimax-m2.7 (dead leg, rc=124 hangs).

## DEFERRED behind the eval fixes (do NOT start until eval discriminates)
Tasks 5-8 on the manager task list: FREE-TIER epic (FT-QUOTA-ENGINE/CONFIG-SURFACE/CATALOG-SEED/WIRE-QUOTA + reuse PRICING-LIMITS-CHECKER/PROVIDER-CATALOG-REFRESH), issue-class registry (Task 8 — SLOP already built enforcement_taxonomy.py + tracking/query.py, PORT don't rebuild), work-context-fitness classifier (Task 7). These matter but the eval BLOCKERs jump ahead (review's call) — a working eval is the prerequisite for trusting any tier/free-tier/routing decision.

## Standing guards (never violate)
- `sg-never-anthropic` — no Claude/Anthropic id in any SG chain (enforce fleet/checks/no-anthropic-in-sg.sh). All EVAL/canary/candidate ids NON-Anthropic.
- Scorecard is bench-grader-owned; NEVER git-track model-scorecard.tsv; outcomes flow only via the grader-daemon spool.
- Session-end: branch-check before any commit; run fleet/handoff-check.sh before ending.
- Money-path (logging/detention/routing/grading) → adversarially verify, real FAIL-ON-REVERT tests, never trust green alone.

## Gotchas
- **This session's sweep grades are SHAKY** — the review shows they're on the wrong taxonomy (F3), with no latency gate (F4), and all 3 tasks probe ONE skill (F5). Do NOT trust the per-tier assign.py picks until the EVAL fixes land; they're provisional.
- **The too-slow attribution path is DEAD CODE** (F1) — every rc=124 hang is mislabeled `provider-throttled`. I twice stated a wrong "throttled" cause from the label this session; the log actually showed rc=124. VERIFY causes against real logs, never the classifier label.
- **The MODEL-PREFLIGHT synthetic battery has NEVER validly discriminated** (F2) — controls fail-closed on grader infra. Don't trust any preflight "detain" until EVAL-GRADER-PROVISION lands.
- **Per-provider ranking is impossible through the main harness today** (F6) — base pool ids route cheapest-available. Only leg-suffixed ids (`nvidia/…`, `-ds`, `-cb`) pin a leg. LEG-PREFLIGHT-CANARY fixes this end-to-end.
- **minimax-m2.7 is PARKED** (dead leg, rc=124 hangs; NIM/together legs untried) — re-probe via LEG-PREFLIGHT-CANARY, don't blind-send it.
- **EVAL-GRADER-PROVISION + the scorecard cleanup need bench-grader sudo** — operator actions; the manager can't sudo.
- **NVIDIA add reported FAILED but actually 90% worked** (116 models in config, routing verified post-restart) — the FAIL was the step-4 self-test's base_url resolution; add-provider-interactive.sh echoes the key (rotate-and-fix, Task 10).

## Session-bridge
Register on startup with an unused Jedi name + `repo="charon"` via `mcp__session-bridge__register` if the bridge is up (coordinator = Roci 10.0.1.51 via SSH tunnel; NEVER start a local daemon). Heartbeat folded into real work (`board()` ~600s TTL); unregister at session end. This session (quinlan-vos) registered at start; worked solo (no partner droids — operator opens droid tabs for the EVAL waves). Bridge state is advisory; the board (`fleet/status.sh`) is the source of truth.
