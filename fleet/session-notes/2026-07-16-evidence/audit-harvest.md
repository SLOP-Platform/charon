# AUDIT-HARVEST — last-two-sessions audits → work pool (2026-07-16)

READ-ONLY. No board mutation. Every status below CONFIRMED IN CODE, not from the audit's claim.

## Audits swept (mtime 07-14..07-16)
- fleet/state/WIRING-AUDIT-MATRIX.md (07-15 16:54)
- fleet/state/TOOL-WIRING-AUDIT.md (07-15 18:06)
- fleet/state/PERF-AUDIT.md (07-15 16:27) + /home/stack/charon-private/PERF-AUDIT.md (07-15 18:56)
- fleet/state/SG-BUCKET-AUDIT.md (07-15 22:12)
- fleet/state/GITHUB-RUNAWAY-POSTMORTEM.md (07-15 22:10)
- fleet/state/WORK-REORG-PROPOSAL.md (07-15 17:44)
- fleet/state/STRANDED-WORK-AUDIT.md (07-14 21:24)
- fleet/state/MSOT-BLAST-RADIUS-AUDIT.md (07-14 20:50)
- fleet/STARTUP-FRICTION-LOG.md (07-15 23:28)
- fleet/state/OPERATOR-ACTIONS.md, CONFIG-SOURCES.tsv
Older, not swept (premise superseded, >3d): REACHABILITY-AUDIT.md (07-13), CROSS-AUDIT-SYNTHESIS.md (07-13),
EVAL-REGISTRY-RECONCILE.md (07-13), CG-CRITICAL-AUDIT.md (07-13), CG-REMAINING-WORK.md (07-13),
BOARD-REDS-FIX-PACKET.md (07-10). ON-DEMAND-TOOL-LEDGER.tsv / GATE-GAP-LEDGER.tsv DO NOT EXIST yet
(their tickets ON-DEMAND-TOOL-AUDIT / GATE-CREATION-STANDARDIZE are open+unclaimed — that is why).

---

# OPEN-UNTICKETED (ranked by blast radius × unblock leverage)

## 1. GH-SEAM-CHOKEPOINT — direct `gh`/`git fetch` bypasses the gh-cache seam (15 sites / 8 files)
Source: GITHUB-RUNAWAY-POSTMORTEM rec#1,#2,#4 + STARTUP-FRICTION-LOG 2026-07-16.
CONFIRMED: `fleet/handoff.sh:300` (`gh pr list --repo SLOP-Platform/charon --state open --json ...`)
and `fleet/status.sh:60` (`gh pr list --repo "$REPO_SLUG" --json ...`) still call gh DIRECTLY, uncached.
`fleet/handoff.sh:51` freshness_stamp does `git fetch` per repo (×2) with no TTL.
Full direct-gh surface (grep, excl. gh-cache.sh): fleet/_lib.sh, fleet/status.sh, fleet/handoff.sh,
fleet/reconcile-held-markers.sh, fleet/checks/base-integrity.sh, fleet/reconcile-merged.sh,
fleet/land.sh, fleet/submit.sh, fleet/done.sh = 15 call sites.
BOARD GREP (evidence of no coverage): only GITHUB-LIMITS-HARDENING.md and LAUNCHER-CRASH-PARTIAL-DETECT.md
mention `gh pr list`. GITHUB-LIMITS-HARDENING `owns: fleet/gh-cache.sh, fleet/done.sh,
fleet/checks/large-file-guard.sh, fleet/tests/test_github_limits.sh` and its accept covers ONLY
(a) done.sh search-API, (b) large-file guard, (c) land merge pacing. The other 8 files are UNOWNED.
LAUNCHER-CRASH-PARTIAL-DETECT matches only on incidental fork-bomb prose.
CLASS: "GitHub calls are re-implemented per consumer instead of routed through the ONE cached seam"
— identical shape to the `parked` predicate class (re-parsed per consumer → drifts).
WHY IT MATTERS: postmortem names handoff.sh "the highest remaining risk"; friction log records a REAL
boot hard-fail — GraphQL 0/5000 exhausted while REST core sat at 4999/5000, because `gh pr list --json`
is GraphQL-only. Quota exhaustion blocks ALL landing + boot for the rest of the hour.
FIX (compose, don't rebuild): route handoff.sh:300 + status.sh:60 + the other 6 through gh-cache.sh's
`branch_merged_pr`/batched path (built for exactly this); TTL-gate the handoff.sh:51 fetch; add
`CHARON_GH_BUDGET` decrement-before-any-gh circuit breaker (rec#2); lint rule forbidding direct
`gh pr list --head` in new code (rec#4); prefer REST (`gh api repos/OWNER/REPO/pulls`) over GraphQL.
owns: fleet/handoff.sh, fleet/status.sh, fleet/_lib.sh, fleet/reconcile-held-markers.sh,
fleet/checks/base-integrity.sh, fleet/reconcile-merged.sh, fleet/land.sh, fleet/submit.sh,
fleet/checks/gh-direct-call-guard.sh, fleet/tests/gh-seam.test.sh
D&S: depends_on: GITHUB-LIMITS-HARDENING (it owns gh-cache.sh + done.sh — do NOT co-own; this ticket
CONSUMES the seam that ticket hardens). TIER: strong.

## 2. INERT-INSTANCE-DETECT — 6 gateway modules constructed+stored, never invoked; detector is BLIND
Source: WIRING-AUDIT-MATRIX rows 9-14.
CONFIRMED TODAY (product master, `grep -rn '<mod>\.' src/charon/`): RequestInspector, SessionAffinity,
Observability, SpeculativeExecutor, ConsensusRouter, VirtualKeyManager = **0 call sites each**.
All 6 constructed at gateway.py:258-296 via `_module_inst`, stored on GatewayProxyServer
(proxy_server.py:559-566), never reached from `_handle()` → `forward_with_failover()`.
CONFIRMED DETECTOR BLINDSPOT: `python3 tools/check_inert_code.py` → **`check_inert_code: OK`** (GREEN),
and NONE of the 6 appear in tools/inert-code-disposition.json. The detector tracks symbol
reachability (import/construct), so construct+store LOOKS reachable — it cannot see
"constructed-and-stored-but-never-INVOKED".
WHY IT MATTERS (leverage): WORK-GATE-UNIVERSAL's **Gate B** ("no inert/unwired code ships … run
tools/check_inert_code.py + graphify wiring-gap check; REFUSE merge if not FULLY WIRED") is built
ON this detector. Gate B ships GREEN-BUT-BLIND unless the detector learns this pattern — i.e. the
universal work gate would certify inert code as wired. 6 live examples already in the tree.
BOARD GREP: `grep -rlni 'request_inspector|session_affinity|observability|speculative|consensus|virtual_key'
fleet/board/` → matches only ARCHIVED (R43-WIRING-AUDIT, R46-BALANCE-WIRE, DESTIFF-SPECULATIVE, T8,
WORK-OBSERVABILITY, OBS-CAPTURE, OBS-UI, SR-8, SR-4, CLIENT-CONNECT) + PARKED (TIER-RECS, RFL-3,
SR-6-Phase2, GUI-SVELTE-BUILD, DURABLE-BRIDGE-PHASE-2). NO open ticket owns the detector gap.
CLASS: one detector fix + one disposition pass ≫ 6 per-module wiring tickets. Disposition each of the
6 as wire|retire (WIRING-AUDIT-MATRIX §"INERT-to-WIRED Wiring Map" already specifies the ONE
intervention per module — reuse it, don't re-derive).
owns: tools/check_inert_code.py, tools/inert-code-disposition.json, tests/test_inert_instance_detect.py
D&S: depends_on: CAPABILITY-ACTUALS-DEADREF-CLEANUP (it already owns check_inert_code.py +
inert-code-disposition.json — HARD collision, must land first). TIER: strong.

## 3. SELFCHECK-CYCLE-GATE — reentrancy guard is a one-off with no test and no detector
Source: GITHUB-RUNAWAY-POSTMORTEM rec#3 + memory directive `fleet-selfcheck-forkbomb-class`.
CONFIRMED: guard EXISTS (`fleet/gate.sh:29` `export CHARON_GATE_ACTIVE=1`; `fleet/handoff.sh:312`
skips its embedded gate when set) — that half is ALREADY-FIXED. But:
(a) NO fail-on-revert test: `ls fleet/tests/ | grep -i 'reentr|forkbomb|gate_guard'` → nothing.
    The only match is handoff-mechanize.test.sh — which is the script that CAUSES the cycle
    (`:42` runs the real `$SRC/handoff.sh`). Revert the guard → nothing goes red.
(b) NO detector for the OTHER instances of the class: 12 files under fleet/tests/ shell out to real
    fleet scripts (deploy-session-end, leg-sandbox-isolation, reviewer-dogfood, test_land_safe_sync,
    dogfood-to-scorecard, budget-derive, done-gate, log-model-report, branch-reaper, foreman,
    capture-wiring, parked-claim-e2e); 4 invoke handoff/gate/preflight/foreman/land directly. Any of
    these becoming a gate-run edge re-arms the same bomb.
BOARD GREP: `grep -in 'reentran|fork-bomb|forkbomb|self-referen|CHARON_GATE_ACTIVE' fleet/board/*.md`
→ ONE hit, LAUNCHER-CRASH-PARTIAL-DETECT.md:16, incidental prose ("fork-bomb this session"), about
partial-work auto-commit — does NOT cover the cycle guard. No coverage.
WHY IT MATTERS: this exact cycle reached ~18,900 procs (load >2000, fork-starved boot) AND blew the
GitHub GraphQL cap. Memory directive is explicit: "reentrancy-guard EVERY self-referential loop".
FIX: fleet/checks/selfcheck-cycle.sh builds the script→test→script call graph and FAILS on any cycle
edge lacking a reentrancy guard; fail-on-revert test asserts handoff.sh→gate.sh does not re-enter
the suite (revert the gate.sh:29 export → RED).
owns: fleet/checks/selfcheck-cycle.sh, fleet/tests/selfcheck-cycle.test.sh
D&S: depends_on: (none). TIER: strong.

## 4. METER-DOC-RECONCILE — money-path docstrings assert the meter is inert; the code says it is LIVE
Source: WIRING-AUDIT-MATRIX row 7 + §"Key Architectural Notes" 1.
CONFIRMED LIVE: `grep -n 'provider=route.label' src/charon/forwarder.py` → **8 sites**
(581, 629, 655, 791, 797, 845, 869, 898). `all_model_provider_costs()` IS consumed:
forwarder.py:532 (`live = observer.all_model_provider_costs()`, cost-rank routing),
gateway.py:477, balance.py:534.
CONFIRMED STALE DOCS: `grep -n 'Wave-2|Wave 2' src/charon/proxy.py` → **10 lines across ~5 blocks**
(311, 314, 356, 360, 504, 507, 566, 569, 579, 586), incl. verbatim
"this ledger is EMPTY under real traffic today" and "WAVE-2 DEFERRED: this ledger WILL be read by
Wave-2 cost-rank routing" — both FALSE; forwarder.py:532 reads it now.
WHY IT MATTERS: this is the documented source of the standing "charon-meter-inert" belief and of the
still-PARKED `fleet/board/METER-MODEL-PROVIDER.md.parked` (a Wave-2 build ticket for work that has
ALREADY SHIPPED). Money-path code that lies about its own wiring is the `confirm-dont-trust-
documentation` + `document-model-self-report-lies` class. SECOND ACTION FOR MANAGER: re-scope or
retire METER-MODEL-PROVIDER.md.parked — its premise no longer holds.
BOARD GREP: no open ticket owns src/charon/proxy.py (METER-KWH-USD-FIX owns gateway.py +
tests/test_gateway_kwh_conversion.py; ADR0016-DEPLOY-PRICED-COMPLETENESS owns routing_policy/cost_rank.py).
owns: src/charon/proxy.py
D&S: depends_on: (none). TIER: economy.

## 5. FT-LIMITS-GROQ-RECONCILE — rig free-tier row self-flagged MISMATCH, unowned
Source: MSOT-BLAST-RADIUS-AUDIT row 8.
CONFIRMED: `fleet/state/FREE-TIER-LIMITS.tsv:5` →
`groq  free-groq|deepseek-v4-pro-groq|gpt-oss-120b-groq_MISMATCH_UNRECONCILED  unpublished ×5  unknown ×2  unverified`
BOARD GREP: `grep -rln 'FREE-TIER-LIMITS|groq' fleet/board/` → FT-CATALOG-SEED.md,
FREE-TIER-QUOTA-SPILL.md.parked, archive/PROXY-FAILOVER-FIX.md. FT-CATALOG-SEED's accept explicitly
states "**The product cannot read the build-rig FREE-TIER-LIMITS.tsv (product/rig boundary)**, so it
needs its OWN shipped seed" — `owns: src/charon/provider_presets/hosted.py,
src/charon/routing_policy/free_tier_catalog.py, tests/test_free_tier_catalog.py`. It is PRODUCT-side
by design and does NOT own the rig TSV. FREE-TIER-QUOTA-SPILL is parked. → rig row UNOWNED.
WHY IT MATTERS: memory directive `always-fix-catalog-mismatches` (#30) — "fix on sight". A live,
self-acknowledged disagreement makes groq free-tier routing/preflight decisions untrustworthy, and
groq is the largest free tier in the stack (14,400 RPD).
owns: fleet/state/FREE-TIER-LIMITS.tsv
D&S: depends_on: (none). TIER: economy.

## 6. AVAILABILITY-WRITETHROUGH — fleet parked-state and product enabled-flag never sync
Source: MSOT-BLAST-RADIUS-AUDIT row 6 (LATENT / unjoined).
Two unjoined stores: product `src/charon/config/models.py:103-109` `set_model_enabled` → models.json
`enabled`; fleet `fleet/state/PARKED-MODELS.tsv` (written by fleet/benchmark/auto-park-scan.sh) +
fleet/provider-exhaustion-ledger.tsv. No cross-repo sync exists.
BOARD GREP: SSOT-DRIFT-GATE's accept names ONLY tier→model membership, model-id normalization, and
board-vs-GitHub PR-state as the MSOTs it converges; availability is not among them. A drift GATE
would only DETECT the split — the missing write-through is a MECHANISM, not a gate row. GRACEFUL-
DEGRADE owns router.py/failover.py/balance.py (not config/models.py, not PARKED-MODELS.tsv).
WHY IT MATTERS: gateway routes to a model the rig has already parked as dead, or skips one the
product re-enabled. Directly degrades the "never out of workers while ≥1 viable" north-star.
owns: fleet/benchmark/auto-park-scan.sh, fleet/state/PARKED-MODELS.tsv, fleet/tests/availability-writethrough.test.sh
D&S: depends_on: SSOT-DRIFT-GATE (register availability as a fact row there; this ticket supplies the
write-through the gate then enforces). TIER: strong.

## 7. HANDOFF-ROOT-ARCHIVE — stale root HANDOFF.md actively misled crash recovery
Source: STARTUP-FRICTION-LOG "post-crash restart (2026-07-16)", self-marked "(OPEN: archive/date it)".
CONFIRMED: `/home/stack/charon-private/HANDOFF.md` mtime **Jul 10**, opens "You are the next Charon
Manager. This is a complete, self-contained handoff." — friction log records it as months-stale
(GitLab/mvp-routing era); real state lives in fleet/state/ + SESSION-HANDOFF-*.md.
BOARD GREP: STARTUP-CONTEXT-DIET owns fleet/MANAGER-OPERATING-RULES.md, fleet/handoff.sh,
fleet/handoff-check.sh, fleet/preflight.sh, fleet/START-SESSION.md — NOT the root HANDOFF.md.
No other ticket names it. Cost: minutes. Prevented: a recurring wrong-turn at crash recovery.
owns: HANDOFF.md (rig root)
D&S: depends_on: (none). TIER: economy.

## 8. GATEWAY-HOST-SSOT — 9 fleet files hardcode 10.0.1.60  [OVERLAP — manager call]
Source: MSOT-BLAST-RADIUS-AUDIT row 9 (LATENT).
Sites: fleet/access-check.sh:31-40, fleet/deploy.sh:170, fleet/add-provider.sh:45,47,
fleet/checks/gpt55-primary.sh:6, fleet/state/leg-canary-prototype.py:7, fleet/deploy-session-end.sh:9,
fleet/scratch/rollback-*.sh. Product src/charon/ has ZERO occurrences (clean per public-repo rule).
OVERLAP: REACHABILITY-GATE (open, strong) PART 1 audits "EVERY hardcoded absolute path in product +
rig … read or written across a boundary … (c) a fresh-install / different-host boundary" — a
different-host literal is arguably in scope. Recommend FOLDING this into REACHABILITY-GATE's audit
matrix rather than a net-new ticket. Flagged, not proposed, per check-for-an-existing-ticket-first.
TIER: economy if split out.

### Folded, NOT proposed as separate tickets (reuse-check)
- MSOT #5 tier alias hand-copy (grades.py:436-441 vs config/tiers.py:11-16) and MSOT #7 model-id↔pool-id
  alias map: both are LATENT facts → registry ROWS in SSOT-DRIFT-GATE's SSOT-REGISTRY.tsv, whose accept
  is "one row per canonical fact -> its ONE owning file + the reader files that must agree". Covered.

---

# ALREADY-FIXED (9) — confirmed in code, audit premise dead
1. foreman.sh → preflight wiring. TOOL-WIRING-AUDIT (07-16T01:05Z) called this P0 with
   "`grep -n foreman fleet/preflight.sh` returns zero matches" and accused commit 364b010 of a
   self-report lie. FALSE TODAY: `fleet/preflight.sh:590-598` defines `foreman_advisory()`;
   `:619` calls it in the `scan|"")` path. Fixed after that audit was written.
2. `fleet/tests/test_foreman_wire.sh` EXISTS (the same audit said it "does not exist").
3. check_catalog_case_quant.py gate wiring — TOOL-WIRING-AUDIT P0. FIXED: registered at
   `src/charon/gate_runner.py:21` (`(["python3", "tools/check_catalog_case_quant.py"], "catalog-case-quant")`)
   AND `tools/gates.json:176` (`"enforcer": "tools/check_catalog_case_quant.py"`). Memory directive
   #30's mechanized detector now runs on the gate path.
4. CONFIG-SOURCES.tsv missing → config-drift.sh silently no-ops. FIXED: fleet/state/CONFIG-SOURCES.tsv
   exists (07-15 18:19), 2 rows (local ~/.charon + 4lom gateway /data).
5. `parked` predicate re-parsed in claim.sh/status.sh/foreman.sh/launch-plan.sh/_lib.sh — master fa07ca0.
6. gate.sh↔handoff.sh fork-bomb reentrancy GUARD — gate.sh:29 / handoff.sh:312-317. (Guard only; the
   missing TEST + cycle detector are OPEN → item 3 above.)
7. preflight.sh scan 5m46.6s / reconcile-merged.sh O(PRs×files×awk-spawn) — rig-root PERF-AUDIT.md
   documents the landed index-once fix; claim.sh's sibling O(n²) also fixed (~13s → <0.3s on a
   2000-file fixture) with fleet/tests/test_claim_decompose_perf.sh as the fail-on-revert.
8. fleet/memory/session-preamble.sh EXISTS (TOOL-WIRING-AUDIT said "doesn't exist yet"). Built —
   its WIRING is what remains, and that is ON-DEMAND-TOOL-AUDIT's job (see ALREADY-TICKETED 5).
9. STRANDED-WORK-AUDIT Tier-1 #19 "BUILD-SERVER-EPHEMERAL-PORT — no ticket ever filed, land it".
   Wrong twice: the fix is ON MASTER (`tests/test_gateway.py:74` reads back `srv.server_address[1]`;
   `:146,:174,:195` and `test_gateway_tiers.py:85` use `port=0`; ZERO `8080` literals remain in
   test_gateway.py), and it WAS ticketed — `fleet/board/archive/TEST-PORT-FLAKE.md` (branch
   feat/test-ephemeral-ports) covers the identical defect. The stale worktree branch
   fix/build-server-ephemeral-port is 126 files / -17,570 lines vs master — do NOT land it.

# ALREADY-TICKETED (13) — board evidence cited
1. MSOT #1 tier→model membership DIVERGED (model_catalog.py tier_hint vs tier-models.tsv) →
   **SSOT-DRIFT-GATE**, accept verbatim: "Converge the diverged MSOTs … tier->model membership
   (model_catalog.py tier_hint vs tier-models.tsv)".
2. MSOT #3 model-id normalization DIVERGED → **SSOT-DRIFT-GATE**, accept verbatim: "model-id
   normalization (detect_model.py vs proxy._normalize_model_id)". (Divergence CONFIRMED still live:
   fleet/benchmark/lib/detect_model.py:106-114 does only `rsplit("/",1)[-1]` — no `.lower()`, no
   quant strip — while its docstring claims "Mirror charon's src/charon/proxy.py::_normalize_model_id
   EXACTLY". Ticketed, so no new ticket; worth PRIORITISING — it silently re-fragments the
   scorecard ledger that is the ranking source-of-record.)
3. MSOT #2 work-class taxonomy 4-way split → **EVAL-TAXONOMY-ALIGN** (owns fleet/capability/grades.py,
   fleet/state/EVAL-TAXONOMY.md); SSOT-DRIFT-GATE `depends_on: EVAL-TAXONOMY-ALIGN` with an explicit
   real-dep note. Correctly sequenced.
4. MSOT #4 product-path MSOT (~30 files / 18 override vars) → **REPO-DECL-CENTRAL** (owns fleet/_lib.sh,
   handoff.sh, retire-done.sh, handoff-check.sh, land-needs-push.sh).
5. **Built-but-unwired tool class** (dark-work-check.sh 0 callers CONFIRMED; launch-plan.sh +
   stale-check.sh 0 callers CONFIRMED; memory/search.py + session-preamble.sh 0 callers CONFIRMED) →
   **ON-DEMAND-TOOL-AUDIT** (frontier, OPEN, unclaimed). Its note is verbatim: "EXTEND, don't redo:
   fleet/state/TOOL-WIRING-AUDIT.md already found several under-wired tools
   (foreman/memory/config-drift/dark-work/launch-plan/catalog-detector) — fold those in", and its
   accept ends "Then: Board the top offenders' mechanization". This IS the class ticket for every
   TOOL-WIRING-AUDIT row. Do NOT file a duplicate wiring ticket — feed the audit instead.
   (NOTE: LAUNCH-PLAN-SH + STALE-CHECK-SH accepts DELIBERATELY say "Do NOT edit preflight.sh — it is
   owned elsewhere; make stale-check.sh standalone" — standalone-by-design, wiring is downstream.)
6. Inert/unwired code shipping FORWARD → **WORK-GATE-UNIVERSAL** Gate B. (Its detector blindspot is
   the OPEN item 2 above — Gate B is only as good as check_inert_code.py.)
7. done.sh per-owns-file `gh pr list --search` (search API 30/min) → **GITHUB-LIMITS-HARDENING**.
8. FOREMAN-WIRE's handoff.sh leg → **FOREMAN-WIRE** (open, claimed economy-388425). Its accept requires
   "preflight.sh scan AND fleet/handoff.sh run foreman.sh"; CONFIRMED `grep -c foreman fleet/handoff.sh`
   = **0** — the preflight half landed, the handoff half has not. In-flight, not a new ticket.
9. PROJECT-MEMBERSHIP-GATE public-clean leak (rig name / hostname / /home/stack paths into the PUBLIC
   repo, PR #130 closed unmerged, wrong repo) → **PROJECT-MEMBERSHIP-GATE** (open; WORK-REORG §3 says
   it needs an explicit `repo: charon-private` field on relaunch).
10. done.sh false-close + wrong-repo default → **DONE-SH-INTEGRITY-FIX**.
11. Decomposer 429 dead-end with ~20 providers idle → **DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD**.
12. Config-siloing (local `charon providers list` shows 3, gateway has 11 keyed) → CONFIG-SSOT-PROPAGATE
    (archived/merged) + SSOT-DRIFT-GATE.
13. BENCH-OOB-GRADING stale scope blocking the frontier chain (MODEL-PREFLIGHT → FINAL-E2E-REVIEW,
    GRADER-SECFIX-RECONCILE) → ticket exists (parked); WORK-REORG §2 prescribes a manager scope-review,
    not a build. Operator decision, not a new ticket.

# STALE / WRONG (7)
1. TOOL-WIRING-AUDIT foreman P0 + its "corrigendum" self-report-lie accusation of commit 364b010 —
   preflight.sh:590-619 has it; test_foreman_wire.sh exists. Audit was right AT WRITE TIME, dead now.
2. TOOL-WIRING-AUDIT catalog-detector P0 — wired (gate_runner.py:21, gates.json:176).
3. TOOL-WIRING-AUDIT config-drift "registry not found" no-op — CONFIG-SOURCES.tsv now exists.
4. PERF-AUDIT preflight-scan 5m46 offender — fixed (index-once).
5. STRANDED-WORK-AUDIT Tier-1 #19 ephemeral-port — see ALREADY-FIXED 9 (fix on master, was ticketed).
6. STRANDED-WORK-AUDIT Tier-1 #4,5,6,11,12,13,14,15,17 (fn2/fn3/fn4/fn5, eval-latency-gate,
   session-ctx-propagate, handoff-mechanize, no-dark-work, eval-taxonomy-align, eval-grader-provision)
   — WORK-REORG §1 confirms all MERGED (PRs #50,#51,#52,#53,#59,#68,#54,#55,#63,#64). Land-list dead.
7. STRANDED-WORK-AUDIT blocker `feat/leg-preflight-canary` "~55%, missing test + LEG-RANK.tsv" —
   WORK-REORG §1: `state/done/LEG-PREFLIGHT-CANARY` marker + merged PR #60.

# NOT A DEFECT — operational input for the manager
SG-BUCKET-AUDIT verdict: ready-to-claim depth = 3→4 across ALL tiers (frontier 0, economy 0, strong 2-3,
standard 1). **5 concurrent SG tabs WILL idle.** Its own stated biggest lever: land the 22 in-review
(`state/submitted/`) tickets — that frees FT-WIRE-QUOTA + REPO-DECL-CENTRAL and their chains — and
unpark/supersede BENCH-OOB-GRADING to free the frontier MODEL-PREFLIGHT → FINAL-E2E-REVIEW chain.
The 6 OPEN-UNTICKETED items above are themselves bucket refill: 3 strong + 3 economy, all zero-dep or
single-dep (per `keep-the-hopper-full`).
