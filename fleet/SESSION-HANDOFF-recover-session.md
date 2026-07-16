# Charon Fleet — Session Handoff (2026-07-16T06:17:28Z) — recover-session

> **Per-session handoff.** Each session writes: `SESSION-HANDOFF-$SESSION.md`.
> No collisions. Next session reads ALL: `SESSION-HANDOFF-*.md`.

**Date:** 2026-07-16
**Session:** recover-session

---

## Bootstrap (copy-paste into next session)

```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-recover-session.md — you are the fresh Charon fleet MANAGER, carry it out, then flip to fleet mode.
```

### Context discipline (token-burn guard — always on)
1. **Auto-compact ON.** At startup verify `grep autoCompactEnabled ~/.claude/settings.json` shows `true`. If not, STOP and tell the operator (see `fleet/SETTINGS-GUARD-PROPOSAL.md`) — a never-compacting transcript makes per-turn token cost climb all session.
2. **Sub-sessions write, don't dump.** A sub-session WRITES its findings to a file and returns only a 2-3 line pointer + the absolute path. NEVER paste a full sub-session report back into the primary.
3. **Read big docs in narrow slices, once.** Read handoffs/plans by line-range (offset/limit), never the whole file, never re-read each turn.
4. **Keep-alive is a light heartbeat.** Fold the bridge heartbeat into real work (`board()` TTL 600s); do NOT run a 4-min idle wakeup loop that reprocesses full context.

---

## Provenance (anti-clobber — verify this matches the session/filename before trusting this handoff)

**Session:** recover-session
**Generated:** 2026-07-16T06:17:28Z
**Product HEAD:** ea07ee0 — current with origin/master
**Rig HEAD:** aafc52f — current with origin/master

---

## Done / committed@SHA (auto — what the previous session shipped)

> Mechanized: latest 5 SHAs on master (rig + product) + any session-specific branches' HEAD.
> Edit this section only if you need to highlight specific commits the next session must NOT regress.
```
rig master HEAD:    aafc52f
rig master subject: board: create BENCH-PROVISIONAL-SCORING deep-dive ticket; re-park BENCH-OOB-GRADING; fix flowchart work_class
product master HEAD:    ea07ee0
product master subject: docs(adr): ADR-0011 — The Switchboard (demand-routed provider selection, no pools/lists)

--- last 5 rig master commits ---
aafc52f board: create BENCH-PROVISIONAL-SCORING deep-dive ticket; re-park BENCH-OOB-GRADING; fix flowchart work_class
e66d596 board+friction: queue CHARON-FLOWCHART + LAUNCHER-CRASH-PARTIAL-DETECT; log restart boot frictions
151a833 board: queue this session's pre-existing-issue tickets + unblock BENCH-OOB-GRADING
a1952e6 feat(roadmap): wire end-session.sh to emit roadmap HTML + publish instructions
f0f33a6 chore(board): file MEMORY-INDEX-COMPACTION ticket; archive merged FIX-FT-CATALOG-CONTRACT-TESTS

--- last 5 product master commits ---
ea07ee0 docs(adr): ADR-0011 — The Switchboard (demand-routed provider selection, no pools/lists)
317e589 fix(dedup-actuals-delete): ruff E501 + public-clean leak in review-log (#160)
5dd929d refactor(providers): dedup provider URL/path construction into a shared helper (#159)
350a3e5 feat(forwarder): reconcile tool_repair wiring onto structured fail-loud contract (#158)
e1cb560 feat: consolidate check_arch.py import-graph builder onto graphify (#157)
```

---

## Next-action / in-flight (auto + manager narrative)

> **Mechanized first-action snapshot:** the live machine state for the current handoff time
> (active worktrees, in-flight charon-run jobs + their CHARON_RUN_RESULT, and the latest
> provider-exhaustion-ledger tail) is auto-emitted under \`## Auto-generated state\` below.
> The \`### Manager's first actions\` subsection is the ONLY place the manager hand-types
> the next session's priority order — keep it terse (numbered, with one file/script per item).

### Manager's first actions (priority order — fill below)

1. **BOOT:** run boot checklist incl. NEW #7 PROCESS-HEALTH check (`ls /proc | grep -cE '^[0-9]+$'` abnormally high, or `ps -o cmd= -C bash | grep -cE 'fleet/(handoff|gate)'` >0 ⇒ orphaned FORK-BOMB from a crash — hit ~18.9k procs this session; fix is live, 9dfc85a). Then `bash fleet/foreman.sh` for tier STARVE/LOW. Verify the graphify map auto-refreshed at boot (GRAPHIFY-MAP-FRESHNESS #102 merged this session — the auto-updater is now live).
2. **UNBLOCK THE QUEUE (shallow — 1 economy ready).** The 11 new tickets are sequenced BEHIND in-review tickets that own the same files. To open them, land/redo the LEADERS: `GITHUB-LIMITS-HARDENING` (→ unblocks DONE-SH-INTEGRITY-FIX), `PROJECT-MEMBERSHIP-GATE` (#130 was CLOSED-not-merged → REDO like HANDOFF-PIPEFAIL; → unblocks CREATION-GATE-DECOMPOSE-WIRE), `GATEWAY-NONTOKEN-METERING` #155 (has the kWh→USD money bug → fix via METER-KWH-USD-FIX, then merge; → unblocks FT-WIRE-QUOTA + METER fix). Check each closed-PR leader for the "opencode-crash-mid-session" empty-commit pattern (LAUNCHER-CRASH-PARTIAL-DETECT).
3. **Merges left:** #135 FT-CATALOG-SEED (stale base ~7000 lines behind — needs a real rebase-reconcile, substantive) ; #155 NOT until its money fix lands. #154/#156/#102 already merged.
4. **BENCH-OOB-GRADING:** stays PARKED. Do NOT re-unpark without clearing BOTH gates (#26/#25 design review + #20 BENCH-PROVISIONAL-SCORING = the operator-led deep-dive ticket). I wrongly unparked it this session (corrected).
5. **Deferred sweeps to queue:** wiring-audit's 6 INERT + 1 PARTIAL modules (WIRING-AUDIT-MATRIX.md — decide wire-vs-remove each); the STRANDED-WORK-AUDIT + 4 `.decomposed` files; and build **CHARON-FLOWCHART** (operator wants a printable whole-system diagram — ticket queued).

---
---

## Gotchas (avoid re-discovering / DENIED)

> Mechanized: any pre-existing red that names gotcha-class info (e.g. `git push is DENIED`)
> is auto-prepended below. Fill the session-specific gotchas below the mechanized list.

- `git push` is DENIED to the manager (settings deny-list; verbal authority does NOT override it). The operator pushes.
- <session-specific gotcha 1>
- <session-specific gotcha 2>

---

## session-bridge (auto — live board)

> Mechanized: live `~/.charon/session-bridge.db` board snapshot at handoff time. If empty,
> the next session starts with a clean bridge (no coordination sessions in flight).

```
NAME                           REPO        STATUS      TICKET                       LAST_SEEN
REPO-DECL-CENTRAL droid        charon      in-progress REPO-DECL-CENTRAL            2026-07-16T06:16:56
fix capture wiring timeout str charon      in-progress CAPTURE-WIRING-TIMEOUT-FIX   2026-07-16T06:16:24
cal-kestis                     charon      done        CAPTURE-WIRING-TIMEOUT-FIX   2026-07-16T06:16:11
foreman-multi-trigger          charon      done        -                            2026-07-16T06:13:46
Implement graceful-degrade: pa charon      in-progress GRACEFUL-DEGRADE             2026-07-16T06:08:32
ahsoka-tano                    charon      done        ASSIGN-DISPATCH-PICK-FIX     2026-07-16T06:07:48
plo-koon                       charon      escalated   BENCH-OOB-GRADING            2026-07-16T06:05:09
```
> Coordination rule (read before claiming any work): review the board above for
> collisions (same files) and blockers (sessions blocked on THIS session's deliverable).
> If this session is BLOCKED on another session, surface it in `blockers=` on your `register()`.
> If you INHERIT a session from the board (the previous session timed out), pick a
> new Jedi name and do NOT re-register the old one.

---

## Auto-generated state
### Active worktrees (`git worktree list`)
```
/home/stack/code/charon                                                                         ea07ee0 [master]
/home/stack/charon-wt/order-a                                                                   16dbdc2 [feat/ordering-cost-primary]
/home/stack/code/charon-fleet-ADR0016-DEPLOY-PRICED-COMPLETENESS                                af1792b [feat/adr0016-priced-completeness-guard]
/home/stack/code/charon-fleet-API-DECOMPOSE-CYCLE-FIX                                           317e589 [feat/api-decompose-cycle-fix]
/home/stack/code/charon-fleet-BUILD-SERVER-EPHEMERAL-PORT                                       6460ace [fix/build-server-ephemeral-port]
/home/stack/code/charon-fleet-CATALOG-GATE-WIRE                                                 e8d9a98 [feat/catalog-gate-wire]
/home/stack/code/charon-fleet-DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD                              f29c114 [feat/decomposer-route-through-switchboard]
/home/stack/code/charon-fleet-GATE-REGISTRY-BACKFILL                                            9ca968f [fix/workflow-policy-backfill]
/home/stack/code/charon-fleet-GATEWAY-NONTOKEN-METERING                                         a53e37c [feat/gateway-nontoken-metering]
/home/stack/code/charon-fleet-GRACEFUL-DEGRADE                                                  317e589 [feat/graceful-degrade]
/home/stack/code/charon-fleet-PRICE-REFRESHER                                                   3314989 [feat/price-refresher]
/home/stack/code/charon-fleet-PROJECT-MEMBERSHIP-GATE                                           d0f1f25 [feat/project-membership-gate]
/home/stack/code/charon-fleet-REPO-DECL-CENTRAL                                                 748f6db [feat/repo-decl-central]
/home/stack/code/charon-fleet-WEB-ROADMAP-GENERATOR                                             47d62a9 [feat/web-roadmap-generator]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-deepseek-v4-flash-20260714T234305Z    b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/deepseek-v4-flash-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-deepseek-v4-pro-20260714T234305Z      b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/deepseek-v4-pro-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-free-mistral-code-20260714T234305Z    b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/free-mistral-code-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-gemma-4-31b-cb-20260714T234305Z       b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/gemma-4-31b-cb-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-glm-5.2-20260714T234305Z              b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/glm-5.2-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-kimi-k2.6-20260714T234305Z            b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/kimi-k2.6-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-minimax-m2.7-20260714T234305Z         b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/minimax-m2.7-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-minimax-m3-together-20260714T234305Z  b7aa4c8 [dogfood-eval/PROVIDER-URL-HELPER/minimax-m3-together-20260714T234305Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-deepseek-v4-flash-20260715T001840Z                  b7aa4c8 [dogfood-eval/RFL-3/deepseek-v4-flash-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-deepseek-v4-pro-20260715T001840Z                    b7aa4c8 [dogfood-eval/RFL-3/deepseek-v4-pro-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-free-mistral-code-20260715T001840Z                  b7aa4c8 [dogfood-eval/RFL-3/free-mistral-code-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-gemma-4-31b-cb-20260715T001840Z                     b7aa4c8 [dogfood-eval/RFL-3/gemma-4-31b-cb-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-glm-5.2-20260715T001840Z                            b7aa4c8 [dogfood-eval/RFL-3/glm-5.2-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-kimi-k2.6-20260715T001840Z                          b7aa4c8 [dogfood-eval/RFL-3/kimi-k2.6-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-minimax-m2.7-20260715T001840Z                       b7aa4c8 [dogfood-eval/RFL-3/minimax-m2.7-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-RFL-3-minimax-m3-together-20260715T001840Z                b7aa4c8 [dogfood-eval/RFL-3/minimax-m3-together-20260715T001840Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-flash-20260714T232603Z       b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-flash-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-pro-20260714T134749Z         b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-pro-20260714T134749Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-pro-20260714T232021Z         b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-pro-20260714T232021Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-pro-20260714T232300Z         b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-pro-20260714T232300Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-pro-20260714T232603Z         b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/deepseek-v4-pro-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-free-mistral-code-20260714T232603Z       b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/free-mistral-code-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-gemma-4-31b-cb-20260714T232603Z          b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/gemma-4-31b-cb-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-glm-5.2-20260714T232603Z                 b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/glm-5.2-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-kimi-k2.6-20260714T232603Z               b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/kimi-k2.6-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-minimax-m2.7-20260714T232603Z            b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/minimax-m2.7-20260714T232603Z]
/home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-minimax-m3-together-20260714T232603Z     b7aa4c8 [dogfood-eval/SECRET-HOTROTATE/minimax-m3-together-20260714T232603Z]
/home/stack/code/charon-fleet-rfl-5                                                             b89c01c [feat/rfl-5-context-compaction]
/home/stack/code/charon/.claude/worktrees/agent-a4294af67f9d41d80                               af8d795 [feat/wire-tool-repair]
/home/stack/code/charon/.claude/worktrees/agent-ab00727b804e8f8db                               45d8af7 [feat/public-clean-enforce]

/home/stack/charon-private                                 aafc52f [master]
/home/stack/charon-private-wt/ADD-PROVIDER-MECHANIZE       6a2b88a [feat/add-provider-mechanize]
/home/stack/charon-private-wt/ASSIGN-DISPATCH-PICK-FIX     73d9783 [feat/assign-dispatch-pick-fix]
/home/stack/charon-private-wt/B3-LOG-PRUNE                 b309161 [chore/b3-log-prune]
/home/stack/charon-private-wt/BROADEN-TIER-CHAINS          c34b958 [feat/broaden-tier-chains]
/home/stack/charon-private-wt/CAPTURE-WIRING-TIMEOUT-FIX   1f21e28 [feat/capture-wiring-timeout-fix]
/home/stack/charon-private-wt/CONFIG-SSOT-PROPAGATE        31ae0c7 [feat/config-ssot-propagate]
/home/stack/charon-private-wt/DONE-SH-REPO-AWARE           d5aee32 [fix/done-sh-repo-aware]
/home/stack/charon-private-wt/DROID-LIFECYCLE-REAP         488cab6 [feat/droid-lifecycle-reap]
/home/stack/charon-private-wt/ENV-REGISTRY-WIRE            93a5b7c [feat/env-registry-wire]
/home/stack/charon-private-wt/EVAL-DERIVED-BUDGETS         5bbc525 [feat/eval-derived-budgets]
/home/stack/charon-private-wt/EVAL-GRADER-PROVISION        26e3e84 [feat/eval-grader-provision]
/home/stack/charon-private-wt/EVAL-PIPELINE-CONSOLIDATE    3148c98 [feat/eval-pipeline-consolidate]
/home/stack/charon-private-wt/EVAL-PROMOTION-GATE          9f644a1 [feat/eval-promotion-gate]
/home/stack/charon-private-wt/EVAL-TAXONOMY-ALIGN          9d26d79 [feat/eval-taxonomy-align]
/home/stack/charon-private-wt/EVAL-TIER-CANON              457e295 [feat/eval-tier-canon]
/home/stack/charon-private-wt/FLEET-DEMAND-DRIVEN-ROUTING  342b7e2 [feat/fleet-demand-driven-routing]
/home/stack/charon-private-wt/FN1-MEMORY-STORE-ADOPT       676cb13 [feat/fn1-memory-store]
/home/stack/charon-private-wt/FN2-BITEMPORAL-DECAY         dc81372 [feat/fn2-bitemporal-decay]
/home/stack/charon-private-wt/FN3-CURATION-PASS            1cc7c3d [feat/fn3-curation-pass]
/home/stack/charon-private-wt/FN4-RESEARCH-GATE            8c659a3 [feat/fn4-research-gate]
/home/stack/charon-private-wt/FN5-REGISTRY-SWEEP           a040bc5 [feat/fn5-registry-sweep]
/home/stack/charon-private-wt/FOREMAN-MULTI-TRIGGER        d0ff7df [feat/foreman-multi-trigger]
/home/stack/charon-private-wt/FOREMAN-WIRE                 3b27d98 [feat/foreman-wire]
/home/stack/charon-private-wt/GATE-CREATION-STANDARDIZE    4c18f2a [feat/gate-creation-standardize]
/home/stack/charon-private-wt/GITHUB-LIMITS-HARDENING      1a10452 [feat/github-limits-hardening]
/home/stack/charon-private-wt/GRAPHIFY-MAP-FRESHNESS       23bdc81 [feat/graphify-map-freshness]
/home/stack/charon-private-wt/HANDOFF-MECHANIZE            67b250e [feat/handoff-mechanize]
/home/stack/charon-private-wt/LAND-SH-POSTMORTEM           55a547a [audit/land-sh-postmortem]
/home/stack/charon-private-wt/LAND-SH-SAFE-SYNC            ed1aa0d [fix/land-sh-safe-sync]
/home/stack/charon-private-wt/LAUNCH-PLAN-SH               989f8f4 [feat/launch-plan-sh]
/home/stack/charon-private-wt/LEG-F6-REALPATH-TEST         cfe45a5 [feat/leg-f6-realpath-test]
/home/stack/charon-private-wt/LEG-SANDBOX-HARDEN           09ce648 [feat/leg-sandbox-harden]
/home/stack/charon-private-wt/MEMORY-INDEX-COMPACTION      a349b0d [feat/memory-index-compaction]
/home/stack/charon-private-wt/MEMORY-WIRE-RETRIEVAL        d0a87b4 [feat/memory-wire-retrieval]
/home/stack/charon-private-wt/NO-DARK-WORK                 4cc09a6 [feat/no-dark-work]
/home/stack/charon-private-wt/ON-DEMAND-TOOL-AUDIT         d217c80 [audit/on-demand-tools]
/home/stack/charon-private-wt/PERF-AUDIT-CLAIM-DECOMPOSE   4060864 [fix/perf-audit-claim-decompose]
/home/stack/charon-private-wt/PRICING-LIMITS-CHECK-SH      d4ac0ef [feat/pricing-limits-check-sh]
/home/stack/charon-private-wt/R43-WIRING-AUDIT             c041b59 [audit/r43-wiring-audit]
/home/stack/charon-private-wt/REACHABILITY-GATE            ea7e1c5 [feat/reachability-gate]
/home/stack/charon-private-wt/RECONCILE-HELD-MARKERS       3eed5d4 [fix/reconcile-held-markers]
/home/stack/charon-private-wt/RECONCILE-MERGED-PERF        e879406 [fix/reconcile-merged-perf]
/home/stack/charon-private-wt/REPO-DECL-CENTRAL            ef9e27a [feat/repo-decl-central]
/home/stack/charon-private-wt/RIG-STATE-HYGIENE            a6549da [chore/rig-state-hygiene]
/home/stack/charon-private-wt/RULE-SYNC-AUDIT              2704958 [audit/rule-sync-register]
/home/stack/charon-private-wt/RULE-SYNC-GATE               b1e2c77 [feat/rule-sync-gate]
/home/stack/charon-private-wt/SALVAGE-STASH-CHARON-RUN     680c010 [feat/salvage-charon-run-timeout]
/home/stack/charon-private-wt/SESSION-END-PUSH-GATE        1088460 [feat/session-end-push-gate]
/home/stack/charon-private-wt/SSOT-DRIFT-GATE              8b57983 [feat/ssot-drift-gate]
/home/stack/charon-private-wt/STALE-CHECK-SH               16f33ec [feat/stale-check-sh]
/home/stack/charon-private-wt/TSV-APPEND-UNIFY             cf9d092 [feat/tsv-append-unify]
/home/stack/charon-private-wt/WEB-ROADMAP-GENERATOR        9d6b500 [feat/web-roadmap-generator]
/home/stack/charon-private-wt/WORK-GATE-UNIVERSAL          8cc56a4 [feat/work-gate-universal]
/home/stack/wt/coverage-meta-gate                          e7aaeea [feat/coverage-meta-gate]
```
### In-flight charon-run jobs (CHARON_RUN_RESULT)
```
dogfood-RFL-3-minimax-m2.7-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-free-mistral-code-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-gemma-4-31b-cb-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-deepseek-v4-flash-20260715T001840Z  ->  SUCCESS model=deepseek-v4-flash
dogfood-RFL-3-glm-5.2-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-kimi-k2.6-20260715T001840Z  ->  SUCCESS model=kimi-k2.6
dogfood-RFL-3-minimax-m3-together-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-deepseek-v4-pro-20260715T001840Z  ->  SUCCESS model=deepseek-v4-pro
```
### Provider-exhaustion-ledger tail (`provider-exhaustion-ledger.tsv`)
```
ts	job	model	event	note
2026-07-16T06:17:26Z	out	my-model	infra-fault-failover	rc=1; provider/local/infra symptom (5xx/reset/refused/deadline/db-lock/timeout/opaque) -- not a model verdict
2026-07-16T06:17:26Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-07-16T06:17:26Z	out	my-model	infra-fault-failover	rc=1; provider/local/infra symptom (5xx/reset/refused/deadline/db-lock/timeout/opaque) -- not a model verdict
2026-07-16T06:17:26Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-07-16T06:17:26Z	out	my-model	too-slow-failover	rc=124; budget=1800s; model streamed output but did not finish -- latency-is-a-failure-class, model-attributable
2026-07-16T06:17:26Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-07-16T06:17:26Z	out	my-model	infra-fault-failover	rc=3; provider/local/infra symptom (5xx/reset/refused/deadline/db-lock/timeout/opaque) -- not a model verdict
2026-07-16T06:17:26Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-07-16T06:17:26Z	out	my-model	error-failover	rc=1; non-limit, non-infra failure (genuine model-attributable result)
2026-07-16T06:17:26Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
```
### Git
```
master


--- last 10 commits ---
ea07ee0 docs(adr): ADR-0011 — The Switchboard (demand-routed provider selection, no pools/lists)
317e589 fix(dedup-actuals-delete): ruff E501 + public-clean leak in review-log (#160)
5dd929d refactor(providers): dedup provider URL/path construction into a shared helper (#159)
350a3e5 feat(forwarder): reconcile tool_repair wiring onto structured fail-loud contract (#158)
e1cb560 feat: consolidate check_arch.py import-graph builder onto graphify (#157)
371a288 land: feat/ft-catalog-seed
9004bcf Merge pull request #148 from SLOP-Platform/fix/ft-catalog-contract-tests
b9140b5 Merge pull request #152 from SLOP-Platform/feat/delete-static-rank
166eb73 Merge pull request #151 from SLOP-Platform/feat/fail-loud-contract
6978e1f test(delete-static-rank): FAIL-ON-REVERT contract + flip old-behavior tests
```
### Open PRs
```
[{"headRefName":"feat/web-roadmap-generator","number":161,"state":"OPEN","title":"feat(roadmap-html): wire end-session.sh to emit roadmap HTML + publish instructions"},{"headRefName":"fix/workflow-policy-backfill","number":156,"state":"OPEN","title":"docs(gate): record workflow-policy reconciliation — SHA-pin policy confirmed, gate wired and green"},{"headRefName":"feat/gateway-nontoken-metering","number":155,"state":"OPEN","title":"feat(gateway): parse non-token cost from response body"},{"headRefName":"feat/catalog-gate-wire","number":154,"state":"OPEN","title":"feat(gate): wire check_catalog_case_quant into gate registry and runner"},{"headRefName":"feat/wire-mocklint-enforce","number":146,"state":"OPEN","title":"feat(gate): promote rule (e) self-mirroring-mock to hard error, add gate-registry wiring check"},{"headRefName":"feat/ft-catalog-seed","number":135,"state":"OPEN","title":"chore(FT-CATALOG-SEED): launcher auto-commit — droid exited without committing (review for completeness)"},{"headRefName":"dependabot/github_actions/github-actions-911e50acf6","number":86,"state":"OPEN","title":"ci: bump the github-actions group across 1 directory with 6 updates"}]
```
### Gate
```
  https://www.shellcheck.net/wiki/SC1122 -- Nothing allowed after end token. ...
shellcheck: ADVISORY — findings above are non-blocking (shellcheck-clean tracked separately)
summary: 35 passed, 4 failed
```
### Roadmap (canonical — fleet/report.sh)
```
CHARON FLEET ROADMAP
====================

PROJECT 1 — ROUTER

  Wave 1 — sense (meter)
    ✅  Done  R1                         meter-model-provider                 real per-call cost sensor
    ✅  Done  R4                         meter-wire                           wire real cost into decisions
    ✅  Done  R5                         cost-rank-auto                       sort pools by metered cost
  Wave 2 — decide (brain)
    ✅  Done  R2                         router-core                          price-sorted order + smart failover
    ✅  Done  R3                         capability-matrix                    which providers serve what + quirks
    ✅  Done  R7                         capability-engine                    one brain for routing
    ✅  Done  R8                         latency-signal                       fail over slow providers
  Wave 3 — class-fix (wiring & test discipline)
    🟠  now   R43                        wiring-audit                         sweep gateway for built-but-inert features → wired/inert matrix — audit delivered (WIRING-AUDIT-MATRIX.md), PR #20 still DRAFT (not merged)
    🟣  next  R44                        dogfood-gate                         e2e merge-gate: real-config request asserts observable effects
    🟣  next  R45                        inert-startup-check                  startup self-check: active vs inert optional components (fail-loud)
  Wave 3a — foundation & balance
    ✅  Done  R46                        balance-wire                         construct BalanceTracker from gateway config (un-deads R4 record_spend) — merged PR #95 (b5d7948), verified live in gateway.load_config/_build_balance_tracker + test_gateway.py FAIL-ON-REVERT
    🟣  next  R47                        live-api-balance                     neuralwatt adapter + TTL poller + wire balance into routing
    ✅  Done  R12                        drain-routing                        route to drain credit first — merged PR #95 (b5d7948), forwarder.py funding-class reorder + balance.py drain accounting
    ✅  Done  R11                        drain-then-park                      spend prepaid credit then pause — merged PR #95 (b5d7948), sole-leg guard (forwarder.py _is_sole_leg) + funding-class re-arm table (balance.py park/unpark) + tests/test_drain_then_park.py
  Wave 3b — quick wins
    🟣  next  R14                        meter-session-tag                    attribute spend to a session
    🟣  next  R16                        graceful-degrade                     throttle+alert+auto-recover on refill
    🟣  next  R26                        catalog-reconcile-gpt5               reconcile catalog with live routing
    🟣  next  R30                        rfl-3                                image-aware provider routing filter
    ✅  Done  R15                        free-tier-order                      adversarial best-order given exact limits
    ✅  Done  R17                        pricing-limits-checker               verify limits+pricing, alert on change
  Wave 3c — bigger
    🟣  next  R10                        free-tier-quota-spill                spill when a tier caps
    🟣  next  R13                        pools-simplification                 cut the pool sprawl
  Wave 3d — deferred (not dropped)
    🟤  next  R9                         work-routing-to-charon               route fleet work through gateway
    🟣  next  R18                        provider-probe-fix                   fix provider key probe validation
  Wave 4 — provider integration
    🟣  next  R19                        provider-url-helper                  unify provider URL construction helper
    🟤  next  R20                        openrouter-flakiness-fix             flatten openrouter wrapped error fields
    🟤  next  R21                        longcat-provider                     add longcat provider integration
    🟤  next  R22                        cooldown-fix3                        audit cooldown retry-after edge cases
    🟤  next  R23                        provider-flatrate                    add flat-rate cheap providers
    🟤  next  R24                        sr-12                                restore opencode-zen provider preset
  Wave 5 — catalog & pricing
    🟤  next  R25                        catalog-sync-drift                   sync catalog and detect drift
    🟤  next  R27                        catalog-search-curate                search and curate model catalog
    🟤  next  R28                        nanogpt-primary-review               review nanogpt primary routing policy
  Wave 6 — RFL console
    🟣  next  R29                        rfl-5                                optional context compaction for long chats
    🟤  next  R31                        rfl-2                                chat playground and served-model view
    🟤  next  R32                        rfl-4                                console limit editor with hot-reload
  Wave 7 — SR routing
    🟣  next  R33                        sr-4                                 fix smart-routing doc inaccuracies
    🟣  next  R34                        sr-3                                 cache correctness and status counters
    🟤  next  R35                        gateway-routing-decompose            tracked gateway routing decompose trigger
    🟤  next  R36                        zen-drift-cleanup                    clean live zen model config drift
    🟤  next  R37                        sr-6-phase2                          bidirectional openai anthropic translation
    🟤  next  R38                        gpt5-pool-reorder                    reorder live gpt-5 pool order
  Wave 8 — capability & quality
    🟣  next  R39                        workclass-taxonomy                   classify tasks into work classes
    🟤  next  R40                        explore-promote                      risk-gated model explore and promote
    🟤  next  R41                        bench-oob-grading                    out-of-band benchmark grading integrity
    🟤  next  R42                        pff-p2                               opt-in cross-model substitution
  Model-Trust
    ✅  Done  DETENTION-REDLINE          detention-redline                    scorecard block-rate excludes a model from a work_class chain
    ✅  Done  WORK-DECOMPOSER            work-decomposer                      strong planner splits a broad change into single-domain sub-tickets
    ✅  Done  MODEL-PREFLIGHT            model-preflight                      OOB-graded battery screens a candidate model on our failure modes
    ✅  Done  PROVIDER-CATALOG-REFRESH   provider-catalog-refresh             auto model<->provider mapping on a schedule (wired)
    ✅  Done  ADD-PROVIDER-MECHANIZE     add-provider-mechanize               one-command gateway provider add
    ✅  Done  DECOMPOSE-EFFORT-AXIS      decompose-effort-axis                effort axis on the decompose gate (EFFORT-WIRE+ESTIMATOR merged)
    ✅  Done  MODEL-LIFECYCLE            model-lifecycle                      fresh-install onboard + scheduled keep-fresh orchestrator — merged PR #117 (69c115d)

PROJECT 2 — BRIDGE

  Wave A — substrate
    ✅  Done  B1                         phase-0-1-substrate                  lay the bridge foundation
  Wave B — active bridge
    🟣  next  B2                         phase-2-active                       push notifications across sessions
    ⚪  next  B3                         roci-coordinator                     run a durable session coordinator
    🟤  next  B8                         durable-bridge-phase-2               bridge daemon watch and renewal
  Wave C — portable engine
    🟣  next  B5                         obol-adr-0008                        one portable orchestration store
    🟣  next  B6                         work-engine-d10                      move the work engine in-tree
    🟣  next  B7                         work-converge-review                 one modular work tool (SLOP+Charon)
  Wave D — ranking
    🟤  next  B4                         benchmark-v2                         rank models by real outcomes
  Wave E — durable bridge & writeback
    🟤  next  B9                         dsgn-writeback                       design ticket write-back sink

PROJECT 3 — FLEET

  Wave A — droid isolation
    ✅  Done  F1                         worktree-leak-guard                  stop droid work leaking into main
    ✅  Done  F2                         auto-done-on-merge                   close tickets when PRs merge
    ✅  Done  F3                         needs-push-gate                      block exit with unpushed work
  Wave B — session gates
    ✅  Done  F4                         end-session-gate                     require clean board before exit
    ✅  Done  F5                         checkin-in-submit                    check in on every submit
    ✅  Done  F6                         deploy-key-derive                    derive deploy keys, never hardcode
    ✅  Done  F7                         board-correctness                    keep the board state valid
  Wave C — done validation
    ✅  Done  F8                         refuse-unverified-done               reject unmerged work as complete
    ✅  Done  F9                         done-unmerged-red                    flag unmerged tickets claiming completion
    ✅  Done  F10                        retire-done-ordering                 retire finished tickets in order
  Wave D — gate & reporting
    ✅  Done  F20                        report-renderer                      one canonical fleet status report
    ✅  Done  F21                        gate-exclude-goldens                 drop benchmark fixtures from the gate
    ✅  Done  F22                        done-close-archived                  record merge-proof on archived tickets
    ✅  Done  F24                        fleet-gate-repoint                   gate runs fleet tests not product ones
    ✅  Done  F27                        access-check                         probe+report host access at boot
    ✅  Done  F44                        web-roadmap-generator                self-refreshing web roadmap from ROADMAP.tsv
  Wave H — board & gate
    🟣  next  F45                        project-audit-gate                   fact-audit + re-sequence at project/wave start
    🟣  next  F30                        difficulty-schema                    enforce difficulty field on tickets
    🟣  next  F31                        wire-mocklint-enforce                enforce fabricated-mock lint in gate
    🟣  next  F43                        project-membership-gate              gate: new tickets fold into a project
    🟤  next  F32                        board-reds-triage                    triage pre-existing board reds
    🟤  next  F33                        workclass-backfill-review            review low-confidence workclass backfills
    🟣  next  F46                        parallelizability-gate               launch-time gate: block launching a splittable effort (size>=M AND >1 independent surface per owns/collision-map) as a single SERIAL job without --serial-justified=<reason>; mechanizes the wall-clock rule NOW in the rig
  Wave E — automation brains
    🟡  next  F11                        work-optimizer                       COMPOSE (not rebuild): wire F46 parallelizability-gate (merged, fleet PR #37) + decompose-sizing's makespan N* (product feat/decompose-sizing) into one launch-time scheduler; absorbs F12's auto-close-on-completion step; see WCI-CONSOLIDATION.md
    🟤  next  F12                        auto-close                           FOLDED into F11 (auto-close-on-completion is F11's final scheduler step, not a separate brain) — most of this is ALSO already covered live by F2 auto-done-on-merge (done); see WCI-CONSOLIDATION.md
    🟤  next  F13                        recurrence-auditor                   FOLDED — the concrete recurring-defect classes are now owned by REACHABILITY-GATE (cross-boundary hardcoded paths) + test_gate_registry_execution.py (orphaned gates, PR #119); generalized brain = Keystone KS21/KS29. No standalone scope remains; see WCI-CONSOLIDATION.md
    🟤  next  F14                        detector-lifecycle                   FOLDED — detector/gate freshness now covered by test_gate_registry_execution.py's fail-loud wiring proof (PR #119) + Keystone KS29 registry-primitive drift-check when built; see WCI-CONSOLIDATION.md
  Wave F — session lifecycle
    🟠  now   F23                        session-end-deploy                   auto-update 4-LOM at session close
    🟡  next  F28                        startup-context-diet                 cut startup context and token cost
    🟣  next  F16                        autonomous-ttl                       time-box unattended runs
    ⚪  next  F19                        bridge-unregister-trap               unregister the bridge on exit
    🟣  next  F47                        no-dark-work                         register every session on the bridge + pickup-gate so no session runs dark and no report strands
  Wave G — quality & hygiene
    🟣  next  F15                        worktree-cleanup                     clean up orphaned worktrees
    ✅  Done  F17                        scorecard-auto-append                record model scores automatically
    ✅  Done  F18                        auto-log-model-lies                  log models that claim false success
    🟣  next  F25                        repo-decl-central                    declare product vs fleet repo once
    🟣  next  F26                        shellcheck-clean                     make fleet scripts shellcheck-clean
    ✅  Done  F29                        post-gateway-wci-decompose           surgical gateway decompose: module-registry (PR #100/085e74f) + config-package (PR #99/6460ace) + providers-data (PR #98/5135e2e) — all 3 slices merged, unblocked Router W4-8
  Wave I — CI & actions
    🟣  next  F34                        docker-smoke-cleanup                 fix docker smoke cleanup trap
    🟣  next  F35                        sr-11                                mechanize actions version bumps
    🟤  next  F36                        sr-10                                enforce single-producer deploy hygiene
    🟤  next  F37                        test-exercises-change-guard          pre-push hook and fail-on-revert guard
  Wave J — handoff & doctrine
    🟣  next  F38                        handoff-mechanize                    mechanize handoff generation and checking
    ✅  Done  F39                        handoff-pipefail                     fix masked gate failure in handoff
    🟤  next  F40                        coordinator-doctrine-rollout         roll out coordinator doctrine v2
  Wave K — review policy
    🟤  next  F41                        atc                                  final adversarial audit of build waves
    🟤  next  F42                        frontier-review-policy               design frontier review policy spec
  Rig fixes
    ✅  Done  LAND-SH-SAFE-SYNC          land-sh-safe-sync                    land.sh sync must never destroy an uncommitted working tree — merged PR #24 (40ffdba)

PROJECT 4 — SECURITY

  Wave A — scrub & enforce
    ✅  Done  S1                         email-scrub                          remove operator email from repo
    ✅  Done  S2                         enforce-public-clean                 keep private info out of repo
    🟠  now   S4                         scrub-name+name-guard                remove leaked name, block its return
  Wave B — preflight & history
    🟣  next  S5                         guard-pre-flight                     catch secret leaks before push
    ⚪  next  S3                         history-purge                        erase secrets from git history
  Wave C — secrets & guardrails
    🟤  next  S6                         secret-hotrotate                     hot-rotate secrets without restart
    🟤  next  S7                         push-guard-gitc-harden               harden destructive git -C bypass

PROJECT 5 — BACKLOG

  Wave A — grader & keys
    🟣  next  K3                         grader-secfix                        harden the grader against tampering
    🟣  next  K4                         bench-oob-reds-replay                grade models on past failures
    🟤  next  K7                         chutes-commandcode-keys              get missing provider API keys
  Wave B — product UX
    🟣  next  K8                         tool-repair-mutating                 fix mutating tool-repair behavior
    🟤  next  K9                         gui-svelte-build                     rewrite console as svelte spa
    🟤  next  K10                        ux-polish                            batch first-run ux polish nits
    🟤  next  K11                        tier-recs                            setup wizard model recommendations
    🟤  next  K12                        cwd-config-verify                    verify blocked acp config path
  Wave C — connect & dogfood
    🟤  next  K13                        connect-omp-wsl                      fix omp config on wsl connect
    🟤  next  K14                        dogfood                              end-to-end out-of-tree dogfood run
    🟤  next  K15                        ohmypi-assess                        research omp integration feasibility
  Wave D — benchmark remnants
    🟤  next  K16                        bench-reds-replay                    replay real reds as benchmark tasks
    🟤  next  K17                        dtc-6                                parametrize repeating test functions

PROJECT 6 — KEYSTONE

  Wave A — foundation
    ✅  Done  KS1                        mvp-core                             stdlib core + 3 gates + module contract + reuse-check + verify-self (built/reviewed/fixed/verified)
    ✅  Done  KS2                        doctrine-gates                       no_vacuous/no_skip_game/no_pipe_mask/fail_loud/leak_guard (mechanize green-is-not-proof)
    🟣  next  KS8                        coverage-goal                        coverage_ssot tracks % + classifies every rule mechanized/guidance/GAP; FAIL on mechanizable-rule-with-no-gate; goal=100% where logical
  Wave B — capability
    🟣  next  KS3                        graphify-real                        real Graphify integration + `ksf module add graphify` (full pillar B)
    🟣  next  KS4                        inert-code-gate                      catch UNREGISTERED-inert via AST reachability (the real BalanceTracker case; NO half-measure)
  Wave C — apply & deploy
    🟣  next  KS5                        live-charon-dogfood                  point KSF at LIVE Charon as the final dogfood; surface real inert/dead code
    🟣  next  KS6                        deploy-github                        GitHub-clean (leak_guard) + push; decide repo home
  Wave D — propagate
    🟣  next  KS7                        slop-integration                     analyze+plan KSF adoption into SLOP/mediastack; reconcile with ms-enforce
  Wave E — gate library (pluggable, per-project logical)
    🟣  next  KS9                        lens-test-integrity                  static-only-is-a-gap + dead-code + test-behavior-not-structure + mutation-testing
    🟣  next  KS10                       lens-no-duplicate-impl               one-canonical-path / no duplicate implementations (structural anti-rediscovery)
    🟣  next  KS11                       lens-design-deep-modules             complexity cap + deep-modules / interface-simplicity (APoSD pillar D)
    🟣  next  KS12                       lens-code-quality                    type-discipline + lint/format clean (conditional: typed lang)
    🟣  next  KS13                       lens-security                        secrets-scan (gitleaks) + SAST (bandit/semgrep)
    🟣  next  KS14                       lens-supply-chain                    dependency-pin + CVE scan (trivy/pip-audit); pin CI actions/images
    🟣  next  KS15                       lens-robustness                      fresh-install/zero-data-never-500 + idempotency + test-independence (random order)
    🟣  next  KS16                       lens-artifact-integrity              hermetic standalone build+install+health + deterministic/reproducible build (deploy proof)
    🟣  next  KS17                       lens-change-discipline               ADR/decision-record (-> state-store) + migration-discipline (if DB) + surface-boundary
    🟣  next  KS18                       lens-anti-god-file                   file/module size caps (shrink-only ratchet) + god-file/contention detector (too-many-owners = decompose trigger) + single-responsibility; module-per-capability = feature-level decomposition
    🟣  next  KS19                       lens-fragility                       detect/block fragile code: hardcoded-single-entity, bare-except/error-swallow, brittle-parse-where-structured, known-bad-revert-patterns, over-mocking-internals, flaky sources (time/random/net), generic-500-on-known-condition
    🟣  next  KS20                       lens-anti-accretion                  gates are META-invariants over classes, registry-driven (add data not code); forbid per-instance gate proliferation; scale by registry entries (open-seam/anti-accretion) MUST RUN ON KSF ITSELF (dogfood) alongside size-cap(gate files) + single-entity-hardcode, so KSF cannot mint hardcoded/narrow/monolith/unwired gates without going RED
    🟣  next  KS21                       lens-code-tension                    structural tension proxies (cheap, meta): multiple-source-of-truth / single-canonical-owner; composition-conflict (same data re-ordered by multiple passes = the R8/R2 shape); config-vs-reality drift; incomplete-stub-in-done-surface. Deep semantic contradictions stay with adversarial review, NOT a fuzzy find-all-bugs gate
    🟣  next  KS22                       lens-firing-layer                    every registered/enforced gate/tool MUST be invoked in a real firing layer (CI/Makefile/pre-commit); wired-but-never-run = RED (meta-meta over the gate set). Both audits flagged it
    🟣  next  KS23                       lens-verification-delta              a SUCCESS/done claim requires a NON-EMPTY diff AND a test that fails on revert (revert-hunk-must-go-red); catches trust-the-report / unverified success
    🟣  next  KS24                       lens-drift                           declared != reality drift: config/catalog/pools vs live provider state; deployed artifact vs source checksum; dead/stale entries. Registry-driven (add a drift-check spec) ALGORITHM = desired-vs-observed reconciliation (k8s/Terraform pattern): content-hash/checksum, set-diff/bidirectional, subset/schema-conformance, graph-reachability, staleness-probe(TTL). = the registry primitive's discovery/drift leg (KS29)
    🟣  next  KS25                       lens-ai-judgment                     first-class INDEPENDENT adversarial-review layer for the semantic residue gates can't mechanize (contradictions-in-meaning, design quality, blast-radius). Findings are GATED (must resolve); silence is NEVER a pass (green-is-not-proof). DToC for high-blast. Two-owner firewall: reviewer != builder; dev-time judgment separate from any runtime agent. Generalizes SLOP-AI-Agent aspiration + Charon work-engine quality-brain
    🟣  next  KS28                       consolidate-pattern-guard            collapse the pattern-scanning gates (leak_guard, no_pipe_mask + KS13 security, KS19 fragility, revert-patterns) into ONE registry-driven pattern_guard meta-gate: one enforcer, patterns = data rows (pattern/severity/scope). Retire the hardcoded-pattern scripts. Dogfoods KS20 anti-accretion. Build all future pattern lenses as registry rows, not scripts
    🟣  next  KS31                       component-tool-adapters              KSF gate-plugins are thin ADAPTERS over best-in-class INDUSTRY tools (ruff/mypy/bandit/gitleaks/semgrep/vulture/radon/mutmut/hypothesis/schemathesis/trivy/pip-audit/actionlint/hadolint/shellcheck/sqlfluff) + the meta-layer (registry-wire, red-proof, firing, coverage, fail-loud). NEVER reimplement a tool. Each = a fully-supported plug-in working once enabled. Map KS9/11/12/13/14/15 to specific tools. Custom gates ONLY for novel classes tools don't cover (inert/verification-delta/drift/firing-layer/code-tension/grounding). Charon currently uses only 3 of ~15 (ruff/mypy/pip-audit) -> adoption flows through KS5 apply-to-Charon
    🟣  next  KS32                       build-vs-adopt-gate                  TOOL-FIRST gate: adding CUSTOM implementation for a new class requires a tool-eval record (best-in-class candidate + REAL test vs actual cases + verdict wrap/reject-because-X); missing record OR custom-when-a-tool-fits = RED. The tool-ecosystem analog of reuse-check. Registry-assisted (per-class tool registry).
  Wave F — agent grounding
    🟣  next  KS26                       component-agent-onboarding           mechanically ASSEMBLE a per-app agent GROUNDING bundle from live KSF artifacts: architecture+purpose one-pager, code-graph map (what exists + what it does), built-inventory+decisions (state-store), rules + role/job-description, how-to-learn (reconcile-first + lesson-ledger), how-to-ask-for-help (bridge/escalation). Freshness/drift-gated (map==code or the agent trains on lies). Role-filterable (runtime vs dev). Loaded at reconcile-first. Thin packaging over existing artifacts, NOT model fine-tuning. Portable per app (SLOP/Charon/future). This is what makes a 'dumb' agent competent
    🟣  next  KS27                       component-work-orchestration         DEFAULT-to-fan-out work planner: given an effort, auto-compute collision-free chunks (WCI: dedup->contention-axis->waves) from owns/surface + worktrees, launch one agent per chunk; SERIAL = explicit opt-out. The work-engine layer; mechanizes the wall-clock rule so it can't be forgotten
    🟣  next  KS29                       component-registry-primitive         ONE registry PRIMITIVE: declare a registry (schema+scope) -> auto conformance gate (entries valid) + discovery gate (fail-closed on unknown that should be in it) + drift check, for free. Instances: bad-patterns, config/thresholds, entrypoints(auto-derived), decisions, rules/doctrine, catalog/providers, lessons/reds. The single way to make a single-source-of-truth (mediastack registry+conformance-leg+discovery-leg, generalized)
    🟣  next  KS30                       enforcement-spine                    the 'gate of gates': ONE `ksf enforce` entry composing rule-registry(KS29) + coverage-SSOT(KS8: every rule mechanized-or-explicit-guidance, no silent GAP) + gate-runner + firing-layer(KS22, every mechanized rule actually runs) + fail_loud (any violation/unwired = non-zero, never masked). Knows the rules, verifies none are broken, fails LOUD. Runs on KSF itself (dogfood) + any target project. Guarantees the MECHANIZED set; pure-judgment rules explicitly flagged guidance -> judgment layer(KS25)+human. Must NEVER pretend to enforce a judgment rule (fake-green)

PROJECT 7 — FOUNDATION

  Wave A — memory
    🟣  next  FN1                        memory-store-adopt                   adopt basic-memory MCP store over memory/ + kill whole-dump hook + migrate ~50 notes
    🟣  next  FN2                        bitemporal-decay                     shared valid-from/until+last-referenced decay for memory facts AND model-signal ledgers (fixes routing-brain decay, gap B2)
    🟣  next  FN3                        curation-pass                        scheduled dedup/conflict-flag/decay-to-archive; approval-gated (borrow /sleep + bd compact)
  Wave B — research-gate
    🟣  next  FN4                        research-gate                        mechanized research protocol: reuse-check-first + evidence-over-prose + registry(dedup/staleness->update) + completeness gate
  Wave C — anti-accretion
    🟣  next  FN5                        registry-sweep                       audit product+rig+KSF for smart-registry candidates -> apply KS29 primitive (kills collision/accretion classes); F29 registry = candidate #1

PROJECT 8 — FLEET

  session-reliability
    🔵  next  SESSION-CTX-PROPAGATE      sub-agent context propagation        sub-agents inherit session context via PreToolUse hook (built feat/session-ctx-propagate, needs land)
    🟡  next  BASE-INTEGRITY-GATE        base-integrity launch gate           refuse building a ticket on a base missing its prereqs (root cause of wrong-base bug)
    🟡  next  COVERAGE-META-GATE         rule-coverage meta-gate (§11)        port mediastack enforcement_coverage; every gate-able rule must be a gate
    🟡  next  WORK-GATE-UNIVERSAL        decompose-sizing + E2E-wired gates   mechanize work-discipline across inline/subsession/detached/tab
    🟡  next  ENV-REGISTRY-WIRE          live env-registry at session start   surface CG-PROVIDERS to sessions/sub-agents; kill env-spelunking
    🟡  next  SSOT-DRIFT-GATE            SSOT drift merge-gate                converge diverged MSOTs incl board-vs-roadmap; msot-drift.sh
    ✅  Done  STRANDED-WORK-AUDIT        stranded near-done work audit        recover 18 built-unmerged items + FN #49-53
    🟡  next  SESSION-END-PUSH-GATE      session-end commit+push gate         refuse session close on uncommitted OR unpushed work (found this session)
  leg-followups
    🟡  next  LEG-F6-REALPATH-TEST       close vacuous F6 fail-on-revert      exercise the real urllib pin path

PROJECT 9 — SECURITY

  leg-followups
    🟡  next  LEG-SANDBOX-HARDEN         leg-preflight sandbox isolation      close cred-exfil vector (ns/seccomp) in canary exec

Totals:  ✅ done=46  🔵 in-review=1  🟠 building=3  🟡 queued=10  🟣 designed=71  🟤 parked=43  ⚪ not-started=3
```
### Board
```

  CHARON-FLEET STATUS @ 2026-07-16T06:17:41Z

  DROIDS (live tabs)        TIER    UPTIME    WORKING-ON
  strong-3156471            strong  01:00:09  DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD
  strong-3157102            strong  59:54     REPO-DECL-CENTRAL
  strong-3157719            strong  59:35     CAPTURE-WIRING-TIMEOUT-FIX
  frontier-3697177          frontier 42:06     GRACEFUL-DEGRADE
  economy-3721574           economy 41:54     API-DECOMPOSE-CYCLE-FIX

  BOARD
  ID     TIER    STATE     BRANCH                 HELD-BY / NOTE
  ADR0016-DEPLOY-PRICED-COMPLETENESS strong  PR-OPEN   feat/adr0016-priced-completeness-guard 3h27m ago
  API-DECOMPOSE-CYCLE-FIX economy claimed   feat/api-decompose-cycle-fix economy-3721574 · 3m
  ASSIGN-DISPATCH-PICK-FIX strong  PR-OPEN   feat/assign-dispatch-pick-fix 9m ago
  BENCH-OOB-GRADING frontier ready     feat/bench-oob-grading -
  BENCH-PROVISIONAL-SCORING strong  ready     feat/bench-provisional-scoring -
  CAPABILITY-ACTUALS-DEADREF-CLEANUP economy ready     feat/capability-actuals-deadref-cleanup -
  CAPTURE-WIRING-TIMEOUT-FIX strong  claimed   feat/capture-wiring-timeout-fix strong-3157719 · 9m
  CATALOG-GATE-WIRE economy PR-OPEN   feat/catalog-gate-wire 3h22m ago
  CHARON-FLOWCHART strong  ready     docs/charon-flowchart  -
  COVERAGE-META-GATE strong  ready     feat/coverage-meta-gate -
  CREATION-GATE-DECOMPOSE-WIRE strong  blocked   feat/creation-gate-decompose-wire needs PROJECT-MEMBERSHIP-GATE
  DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD strong  claimed   feat/decomposer-route-through-switchboard strong-3156471 · 17m
  DONE-SH-INTEGRITY-FIX strong  blocked   feat/done-sh-integrity-fix needs GITHUB-LIMITS-HARDENING
  DROID-LIFECYCLE-REAP strong  PR-OPEN   feat/droid-lifecycle-reap 41m ago
  ENV-REGISTRY-WIRE strong  DONE      feat/env-registry-wire -
  EVAL-TAXONOMY-ALIGN strong  DONE      feat/eval-taxonomy-align -
  FINAL-E2E-REVIEW frontier blocked   audit/final-e2e-review needs DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT
  FOREMAN-MULTI-TRIGGER economy PR-OPEN   feat/foreman-multi-trigger 3m ago
  FOREMAN-WIRE economy DONE      feat/foreman-wire      -
  FT-CATALOG-SEED economy PR-OPEN   feat/ft-catalog-seed   24h53m ago
  FT-WIRE-QUOTA strong  blocked   feat/ft-wire-quota     needs FT-QUOTA-ENGINE, FT-CONFIG-SURFACE, FT-CATALOG-SEED, FAIL-LOUD-CONTRACT, FORWARDER-RECONCILE, PROVIDER-PROBE-FIX, GATEWAY-NONTOKEN-METERING
  GATE-CREATION-STANDARDIZE frontier PR-OPEN   feat/gate-creation-standardize 3h42m ago
  GATE-REGISTRY-BACKFILL hygiene PR-OPEN   fix/workflow-policy-backfill 2h03m ago
  GATEWAY-NONTOKEN-METERING strong  PR-OPEN   feat/gateway-nontoken-metering 2h45m ago
  GITHUB-LIMITS-HARDENING strong  PR-OPEN   feat/github-limits-hardening 46m ago
  GRACEFUL-DEGRADE frontier claimed   feat/graceful-degrade  frontier-3697177 · 11m
  GRADER-SECFIX-RECONCILE strong  blocked   feat/grader-secfix-reconcile needs BENCH-OOB-GRADING
  GRAPHIFY-MAP-FRESHNESS strong  PR-OPEN   feat/graphify-map-freshness 45m ago
  LAND-SH-POSTMORTEM strong  PR-OPEN   audit/land-sh-postmortem 47h40m ago
  LAUNCH-PLAN-SH strong  PR-OPEN   feat/launch-plan-sh    2h40m ago
  LAUNCHER-CRASH-PARTIAL-DETECT strong  blocked   feat/launcher-crash-partial-detect needs DROID-LIFECYCLE-REAP
  MEMORY-INDEX-COMPACTION strong  PR-OPEN   feat/memory-index-compaction 40m ago
  METER-KWH-USD-FIX strong  blocked   feat/meter-kwh-usd-fix needs GATEWAY-NONTOKEN-METERING, FT-WIRE-QUOTA
  MODEL-PREFLIGHT frontier blocked   feat/model-preflight   needs BENCH-OOB-GRADING
  ON-DEMAND-TOOL-AUDIT frontier PR-OPEN   audit/on-demand-tools  2h05m ago
  PRICE-REFRESHER strong  ready     feat/price-refresher   -
  PRICING-LIMITS-CHECK-SH strong  PR-OPEN   feat/pricing-limits-check-sh 2h25m ago
  PROJECT-MEMBERSHIP-GATE economy PR-OPEN   feat/project-membership-gate 43h48m ago
  REACHABILITY-GATE strong  PR-OPEN   feat/reachability-gate 2h13m ago
  REPO-DECL-CENTRAL economy claimed   feat/repo-decl-central strong-3157102 · 21m
  SALVAGE-STASH-CHARON-RUN strong  DONE      feat/salvage-charon-run-timeout -
  SESSION-END-PUSH-GATE strong  PR-OPEN   feat/session-end-push-gate 16h47m ago
  SSOT-DRIFT-GATE strong  PR-OPEN   feat/ssot-drift-gate   2h05m ago
  STALE-CHECK-SH strong  PR-OPEN   feat/stale-check-sh    2h19m ago
  STARTUP-CONTEXT-DIET strong  blocked   feat/startup-context-diet needs REPO-DECL-CENTRAL
  STRANDED-WORK-AUDIT strong  ready     audit/stranded-work    -
  SYNC-SCHEDULE economy blocked   feat/sync-schedule     needs STARTUP-CONTEXT-DIET, FOREMAN-WIRE
  TSV-APPEND-UNIFY frontier PR-OPEN   feat/tsv-append-unify  1h54m ago
  WEB-ROADMAP-GENERATOR standard PR-OPEN   feat/web-roadmap-generator 31m ago
  WORK-GATE-UNIVERSAL strong  PR-OPEN   feat/work-gate-universal 2h15m ago
  WORK-ROUTING-TO-CHARON-ENGINE frontier ready     feat/work-routing-to-charon-engine -

  OPEN PRs (draft → operator merges)
  #161  feat/web-roadmap-generator  [draft]
  #156  fix/workflow-policy-backfill  [READY-TO-MERGE]
  #155  feat/gateway-nontoken-metering  [draft]
  #154  feat/catalog-gate-wire  [draft]
  #146  feat/wire-mocklint-enforce  [draft]
  #135  feat/ft-catalog-seed  [READY-TO-MERGE]
  #86  dependabot/github_actions/github-actions-911e50acf6  [READY-TO-MERGE]
  (CI per PR:  gh pr checks <n> --repo SLOP-Platform/charon)

  SUMMARY  droids:5   ready:8  claimed:5  PR-open:24  done:4  blocked:10

  (token/usage is NOT faked here — see Claude's own /usage. board.sh = the quick view.)

```
### Board validation
```
== validate_board ==
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/handoff-check.sh <- REPO-DECL-CENTRAL STARTUP-CONTEXT-DIET
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/handoff.sh <- REPO-DECL-CENTRAL STARTUP-CONTEXT-DIET
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/validate_board.sh <- CREATION-GATE-DECOMPOSE-WIRE PROJECT-MEMBERSHIP-GATE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/charon-run.sh <- CAPTURE-WIRING-TIMEOUT-FIX SALVAGE-STASH-CHARON-RUN
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/done.sh <- DONE-SH-INTEGRITY-FIX GITHUB-LIMITS-HARDENING
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/fleet-droid.sh <- DROID-LIFECYCLE-REAP LAUNCHER-CRASH-PARTIAL-DETECT
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/preflight.sh <- FOREMAN-WIRE SYNC-SCHEDULE
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/gateway.py <- FT-WIRE-QUOTA GATEWAY-NONTOKEN-METERING METER-KWH-USD-FIX
  WARN owns-path-missing: ADR0016-DEPLOY-PRICED-COMPLETENESS owns 'tests/test_priced_completeness.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BENCH-PROVISIONAL-SCORING owns 'fleet/state/BENCH-PROVISIONAL-SCORING-DESIGN.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CATALOG-GATE-WIRE owns 'tests/test_catalog_gate_wire.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CHARON-FLOWCHART owns 'docs/CHARON-FLOWCHART.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: COVERAGE-META-GATE owns 'fleet/checks/rule-coverage.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: COVERAGE-META-GATE owns 'fleet/state/RULE-REGISTRY.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: COVERAGE-META-GATE owns 'fleet/tests/rule-coverage.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CREATION-GATE-DECOMPOSE-WIRE owns 'fleet/tests/test_creation_gate_decompose.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DROID-LIFECYCLE-REAP owns 'fleet/reap-orphans.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DROID-LIFECYCLE-REAP owns 'fleet/tests/test_droid_reap.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FINAL-E2E-REVIEW owns 'fleet/state/FINAL-E2E-REVIEW.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FOREMAN-MULTI-TRIGGER owns 'fleet/foreman-cadence.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FOREMAN-MULTI-TRIGGER owns 'fleet/tests/test_foreman_triggers.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FT-CATALOG-SEED owns 'src/charon/routing_policy/free_tier_catalog.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FT-CATALOG-SEED owns 'tests/test_free_tier_catalog.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FT-WIRE-QUOTA owns 'src/charon/routing_policy/free_tier_gate.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FT-WIRE-QUOTA owns 'tests/test_free_tier_gate.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GATE-CREATION-STANDARDIZE owns 'fleet/state/GATE-GAP-LEDGER.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GATE-CREATION-STANDARDIZE owns 'fleet/checks/gate-creation-standard.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GATE-CREATION-STANDARDIZE owns 'fleet/GATE-CREATION-STANDARD.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GATE-CREATION-STANDARDIZE owns 'fleet/tests/test_gate_creation_standard.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GITHUB-LIMITS-HARDENING owns 'fleet/checks/large-file-guard.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GITHUB-LIMITS-HARDENING owns 'fleet/tests/test_github_limits.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GRADER-SECFIX-RECONCILE owns 'fleet/benchmark/grader-daemon.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GRADER-SECFIX-RECONCILE owns 'fleet/benchmark/graders/reds_replay.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GRADER-SECFIX-RECONCILE owns 'fleet/benchmark/selftest/test_grader_daemon.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GRAPHIFY-MAP-FRESHNESS owns 'fleet/checks/graphify-freshness.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GRAPHIFY-MAP-FRESHNESS owns 'fleet/tests/test_graphify_freshness.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: LAND-SH-POSTMORTEM owns 'fleet/state/LAND-SH-POSTMORTEM.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: LAUNCHER-CRASH-PARTIAL-DETECT owns 'fleet/tests/test_launcher_crash_partial.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: MEMORY-INDEX-COMPACTION owns 'fleet/hooks/memory-compact.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: METER-KWH-USD-FIX owns 'tests/test_gateway_kwh_conversion.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: MODEL-PREFLIGHT owns 'fleet/state/PREFLIGHT-CANDIDATES.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: ON-DEMAND-TOOL-AUDIT owns 'fleet/state/ON-DEMAND-TOOL-LEDGER.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PRICING-LIMITS-CHECK-SH owns 'fleet/pricing-limits-check.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PRICING-LIMITS-CHECK-SH owns 'fleet/state/provider-pricing-limits.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: REACHABILITY-GATE owns 'fleet/checks/no-unreachable-paths.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SESSION-END-PUSH-GATE owns 'fleet/tests/end-session-push.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SSOT-DRIFT-GATE owns 'fleet/checks/msot-drift.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SSOT-DRIFT-GATE owns 'fleet/tests/msot-drift.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SSOT-DRIFT-GATE owns 'fleet/state/SSOT-REGISTRY.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: STALE-CHECK-SH owns '/home/stack/charon-private/fleet/tests/stale-check.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: WORK-GATE-UNIVERSAL owns 'fleet/checks/work-gate.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: WORK-GATE-UNIVERSAL owns 'fleet/hooks/pretooluse-work-gate.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: WORK-GATE-UNIVERSAL owns 'fleet/tests/work-gate.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WCI-ADVISORY justified-disjoint-dep (ok): FINAL-E2E-REVIEW -> MODEL-PREFLIGHT (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): FT-WIRE-QUOTA -> FT-CATALOG-SEED (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): GRADER-SECFIX-RECONCILE -> BENCH-OOB-GRADING (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): MODEL-PREFLIGHT -> BENCH-OOB-GRADING (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): SSOT-DRIFT-GATE -> EVAL-TAXONOMY-ALIGN (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): SYNC-SCHEDULE -> STARTUP-CONTEXT-DIET (marked real build/correctness prereq)
  WCI-ADVISORY semantic: prompt-intent contradiction / hidden coupling is NOT machine-checked — eyeball overlapping or dep-linked tickets by hand.
  GREEN board structurally valid
```
### Parked tickets
```
ATC.md.parked
BENCH-REDS-REPLAY.md.parked
BOARD-REDS-TRIAGE.md.parked
CAPABILITY-ENGINE.md.parked
CATALOG-RECONCILE-GPT5.md.parked
CATALOG-SEARCH-CURATE.md.parked
CATALOG-SYNC-DRIFT.md.parked
CONNECT-OMP-WSL.md.parked
COOLDOWN-FIX3.md.parked
COORDINATOR-DOCTRINE-ROLLOUT.md.parked
COST-RANK-AUTO.md.parked
CWD-CONFIG-VERIFY.md.parked
DOGFOOD.md.parked
DSGN-WRITEBACK.md.parked
DTC-6.md.parked
DURABLE-BRIDGE-PHASE-2.md.parked
EXPLORE-PROMOTE.md.parked
FREE-TIER-QUOTA-SPILL.md.parked
FRONTIER-REVIEW-POLICY.md.parked
GATEWAY-CONTRACT-INJECT.md.parked
GATEWAY-ROUTING-DECOMPOSE.md.parked
GPT5-POOL-REORDER.md.parked
GUI-SVELTE-BUILD.md.parked
LONGCAT-PROVIDER.md.parked
METER-MODEL-PROVIDER.md.parked
METER-SESSION-TAG.md.parked
NANOGPT-PRIMARY-REVIEW.md.parked
OHMYPI-ASSESS.md.parked
OPENROUTER-FLAKINESS-FIX.md.parked
PFF-P2.md.parked
POOLS-SIMPLIFICATION.md.parked
PROVIDER-FLATRATE.md.parked
PUSH-GUARD-GITC-HARDEN.md.parked
RFL-2.md.parked
RFL-3.md.parked
RFL-4.md.parked
SECRET-HOTROTATE.md.parked
SR-10.md.parked
SR-12.md.parked
SR-6-Phase2.md.parked
TEST-EXERCISES-CHANGE-GUARD.md.parked
TIER-RECS.md.parked
UX-POLISH.md.parked
WORKCLASS-BACKFILL-REVIEW.md.parked
ZEN-DRIFT-CLEANUP.md.parked
```
### Live tickets (.md, not parked)
```
ADR0016-DEPLOY-PRICED-COMPLETENESS.md  tier=strong  depends_on=
API-DECOMPOSE-CYCLE-FIX.md  tier=economy  depends_on=
ASSIGN-DISPATCH-PICK-FIX.md  tier=strong  depends_on=
BENCH-OOB-GRADING.md  tier=frontier  depends_on=
BENCH-PROVISIONAL-SCORING.md  tier=strong  depends_on=
CAPABILITY-ACTUALS-DEADREF-CLEANUP.md  tier=economy  depends_on=
CAPTURE-WIRING-TIMEOUT-FIX.md  tier=strong  depends_on=
CATALOG-GATE-WIRE.md  tier=economy  depends_on=
CHARON-FLOWCHART.md  tier=strong  depends_on=
COVERAGE-META-GATE.md  tier=strong  depends_on=
CREATION-GATE-DECOMPOSE-WIRE.md  tier=strong  depends_on=PROJECT-MEMBERSHIP-GATE
DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD.md  tier=strong  depends_on=
DONE-SH-INTEGRITY-FIX.md  tier=strong  depends_on=GITHUB-LIMITS-HARDENING
DROID-LIFECYCLE-REAP.md  tier=strong  depends_on=FLEET-DEMAND-DRIVEN-ROUTING
ENV-REGISTRY-WIRE.md  tier=strong  depends_on=SESSION-CTX-PROPAGATE
EVAL-TAXONOMY-ALIGN.md  tier=strong  depends_on=
FINAL-E2E-REVIEW.md  tier=frontier  depends_on=DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT
FOREMAN-MULTI-TRIGGER.md  tier=economy  depends_on=
FOREMAN-WIRE.md  tier=economy  depends_on=
FT-CATALOG-SEED.md  tier=economy  depends_on=
FT-WIRE-QUOTA.md  tier=strong  depends_on=FT-QUOTA-ENGINE, FT-CONFIG-SURFACE, FT-CATALOG-SEED, FAIL-LOUD-CONTRACT, FORWARDER-RECONCILE, PROVIDER-PROBE-FIX, GATEWAY-NONTOKEN-METERING
GATE-CREATION-STANDARDIZE.md  tier=frontier  depends_on=
GATE-REGISTRY-BACKFILL.md  tier=hygiene  depends_on=
GATEWAY-NONTOKEN-METERING.md  tier=strong  depends_on=PROVIDER-PROBE-FIX
GITHUB-LIMITS-HARDENING.md  tier=strong  depends_on=
GRACEFUL-DEGRADE.md  tier=frontier  depends_on=ROUTER-CORE
GRADER-SECFIX-RECONCILE.md  tier=strong  depends_on=BENCH-OOB-GRADING
GRAPHIFY-MAP-FRESHNESS.md  tier=strong  depends_on=
LAND-SH-POSTMORTEM.md  tier=strong  depends_on=
LAUNCH-PLAN-SH.md  tier=strong  depends_on=
LAUNCHER-CRASH-PARTIAL-DETECT.md  tier=strong  depends_on=DROID-LIFECYCLE-REAP
MEMORY-INDEX-COMPACTION.md  tier=strong  depends_on=
METER-KWH-USD-FIX.md  tier=strong  depends_on=GATEWAY-NONTOKEN-METERING, FT-WIRE-QUOTA
MODEL-PREFLIGHT.md  tier=frontier  depends_on=BENCH-OOB-GRADING
ON-DEMAND-TOOL-AUDIT.md  tier=frontier  depends_on=
PRICE-REFRESHER.md  tier=strong  depends_on=
PRICING-LIMITS-CHECK-SH.md  tier=strong  depends_on=
PROJECT-MEMBERSHIP-GATE.md  tier=economy  depends_on=DIFFICULTY-SCHEMA
REACHABILITY-GATE.md  tier=strong  depends_on=
REPO-DECL-CENTRAL.md  tier=economy  depends_on=HANDOFF-PIPEFAIL
SALVAGE-STASH-CHARON-RUN.md  tier=strong  depends_on=
SESSION-END-PUSH-GATE.md  tier=strong  depends_on=
SSOT-DRIFT-GATE.md  tier=strong  depends_on=EVAL-TAXONOMY-ALIGN
STALE-CHECK-SH.md  tier=strong  depends_on=
STARTUP-CONTEXT-DIET.md  tier=strong  depends_on=REPO-DECL-CENTRAL
STRANDED-WORK-AUDIT.md  tier=strong  depends_on=
SYNC-SCHEDULE.md  tier=economy  depends_on=STARTUP-CONTEXT-DIET, FOREMAN-WIRE
TSV-APPEND-UNIFY.md  tier=frontier  depends_on=
WEB-ROADMAP-GENERATOR.md  tier=standard  depends_on=
WORK-GATE-UNIVERSAL.md  tier=strong  depends_on=
WORK-ROUTING-TO-CHARON-ENGINE.md  tier=frontier  depends_on=
```

**********************************************************************
(handoff.sh auto-state section ends here)
(generate session summary with summary.sh, then copy-paste below)
**********************************************************************

## Session summary — paste output of:
##
##   SESSION=$SESSION \
##   SESSION_MODEL=<model> \
##   PARTNERS="<other-sessions>" \
##   WAVE_NAME="<wave name>" \
##   WAVE_GOAL="<wave goal — why this wave exists>" \
##   BLOCKED="<what's blocking next wave>" \
##   NEXT_GOAL="<next wave goal>" \
##   NEXT_FILES="<files for next wave>" \
##   bash /home/stack/charon-private/fleet/summary.sh
##
## (summary.sh reads check-ins written by checkin.sh during the session)

## Key findings / decisions

- **Fork-bomb class fixed:** `handoff.sh`→`gate.sh`→(test suite)→`handoff-mechanize.test.sh`→`handoff.sh` is a concurrent, exponential cycle; orphaned by the crash it hit ~18.9k procs. Reentrancy guard (`gate.sh` exports `CHARON_GATE_ACTIVE`, `handoff.sh` skips its embedded gate when set — 9dfc85a, adversarially reviewed). SAME recursion also blew the GitHub GraphQL cap. See `fleet-selfcheck-forkbomb-class` memory + `GITHUB-RUNAWAY-POSTMORTEM.md`.
- **The Switchboard (ADR-0011) is canonical:** NO provider pool/list/slate — a NEED routes through router/forwarder → cheapest provider WITH the required context window AND available. The decomposer bypasses it (static GLM slate → dead-ended on 429 with ~20 providers idle). Ticketed DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD. NEVER "broaden the list" — route through the Switchboard.
- **Recovered work, nothing lost:** 4 crashed branches → merged (#157-160); reap WIP preserved (705c413); a `done.sh` false-close reverted.
- **"launcher auto-commit — droid exited" = opencode CRASH mid-session** (not lazy droids): crash-partial PRs (#102 has real work; #149/#93 near-empty). Ticketed LAUNCHER-CRASH-PARTIAL-DETECT.
- **#155 GATEWAY-NONTOKEN-METERING has a REAL money bug** (energy_kwh booked as cost_usd, no $/kWh conversion) — left DRAFT; ticketed METER-KWH-USD-FIX. Money review of the 4 merged PRs = all PASS.
- **Pre-existing rig-gate reds:** assign-dispatch + capture-wiring (ticketed ASSIGN-DISPATCH-PICK-FIX / CAPTURE-WIRING-TIMEOUT-FIX); curate is actually GREEN. Grader substrate provisioned by operator (bench-grader daemon live).

## Collision matrix

| File | Owner (live) | Owner (next) |
|---|---|---|
| fleet/fleet-droid.sh | DROID-LIFECYCLE-REAP (claimed) | LAUNCHER-CRASH-PARTIAL-DETECT (depends_on) |
| src/charon/gateway.py | GATEWAY-NONTOKEN-METERING (#155 draft) | METER-KWH-USD-FIX (depends_on) |
| benchmark/bench.sh + grade_state.record | BENCH-PROVISIONAL-SCORING (#20 parked) | BENCH-OOB-GRADING (#26 parked, build-after #20) |
| fleet/validate_board.sh | PROJECT-MEMBERSHIP-GATE | CREATION-GATE-DECOMPOSE-WIRE (depends_on) |
| fleet/done.sh | GITHUB-LIMITS-HARDENING | DONE-SH-INTEGRITY-FIX (depends_on) |

## Open questions

- **BENCH-OOB-GRADING park:** is the #26/#25 design review actually done? #20 (BENCH-PROVISIONAL-SCORING) is your operator-led deep-dive — until both clear, it stays parked (my assessment: park is still valid, #20 is open).
- **Merge on your OK:** rig #102 (code-map updater) + product #156 are ready. #155 (metering) needs the kWh→USD fix first.
- **Deferred sweeps for next session:** the wiring-audit inert modules (6 INERT + 1 PARTIAL in WIRING-AUDIT-MATRIX.md) + the STRANDED-WORK-AUDIT/.decomposed files still need queueing; and CHARON-FLOWCHART (printable whole-system diagram) is queued.

## Files modified this session

| File | Change |
|---|---|
| <path> | <description> |

## Cross-repo improvements to propose

<Improvements discovered this session that would benefit the other repo
(Charon → mediastack, or mediastack → Charon). Include: problem, concrete fix,
files touched, expected benefit.>

---

## Handoff file maintenance

- **Per-session files:** \`SESSION-HANDOFF-\$SESSION.md\`. Never reuse a session name.
  Each boot picks a fresh unused Jedi name from the board. No collisions.
- **Generate:**
  1. During session: \`SESSION=<name> bash fleet/checkin.sh <args>\` per ticket.
  2. At session end: run \`summary.sh\` to emit the session summary.
  3. Pipe handoff.sh into \`fleet/SESSION-HANDOFF-<name>.md\`, paste summary output
     below the auto-state section.
- **Commit:** commit the completed \`SESSION-HANDOFF-<name>.md\` to the charon-private fleet repo.
- **Read:** the next session reads ALL \`SESSION-HANDOFF-*.md\` files to ground itself.
