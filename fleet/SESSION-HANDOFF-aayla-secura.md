# Charon Fleet — Session Handoff (2026-07-14T12:25:15Z) — aayla-secura

> **Per-session handoff.** Each session writes: `SESSION-HANDOFF-$SESSION.md`.
> No collisions. Next session reads ALL: `SESSION-HANDOFF-*.md`.

---

## Bootstrap (copy-paste into next session)

```
Read fleet/SESSION-HANDOFF-aayla-secura.md in narrow slices then run fleet/status.sh + fleet/validate_board.sh, register an unused Jedi name with repo=charon, and continue the P0 SG-active work (strong tier stood up via minimax-m3 + deepseek-v4-pro, next = fund frontier legs and build the S8 hold-lifecycle)
```

---

## Provenance (anti-clobber — verify this matches the session/filename before trusting this handoff)

**Session:** aayla-secura
**Generated:** 2026-07-14T12:25:15Z
**Product HEAD:** b7aa4c8 — current with origin/master
**Rig HEAD:** b32a9e9 — current with origin/master

---

## Auto-generated state (from `handoff.sh` run at 2026-07-14T12:25:15Z)

### Git
```
master

 M docs/adr/0003-capability-routed-agent-orchestration-harness.md
?? tools/inert_to_graph.py

--- last 10 commits ---
b7aa4c8 Merge pull request #126 from SLOP-Platform/chore/gitignore-tooldirs
1a1f88f chore: gitignore local dev-tool caches (.ksf/, graphify-out/)
8639bff Merge pull request #125 from SLOP-Platform/feat/classify-listbody-and-token-drift
fadead2 Merge pull request #124 from SLOP-Platform/feat/auto-park-on-402
b8e62d0 fix(balance): serialize + uniquely-name parked-set persist (concurrency BLOCKER)
4b5df92 fix(proxy): preserve billing-pattern detection for list-shaped error bodies
860e924 feat(gateway): auto-park on deterministic 402, persist + auto-rearm
5afc280 Merge pull request #123 from SLOP-Platform/feat/test-isolation-fix
b7366b6 Merge pull request #122 from SLOP-Platform/feat/decompose-sizing
906467a Merge pull request #121 from SLOP-Platform/feat/forwarder-transient-retry
```
### Open PRs
```
[{"headRefName":"feat/tool-repair-mutating-gate","number":132,"state":"OPEN","title":"fix(tool-repair): make allow_mutating a real gate via is_mutating marker"},{"headRefName":"feat/sr-4-smart-routing-doc-fix","number":131,"state":"OPEN","title":"docs(SR-4): review-log — already complete on charon-private master (commit 50af47c)"},{"headRefName":"feat/project-membership-gate","number":130,"state":"OPEN","title":"feat(PROJECT-MEMBERSHIP-GATE): gate that every live ticket is folded into a ROADMAP row"},{"headRefName":"fix/provider-probe-validation","number":129,"state":"OPEN","title":"fix(gateway): treat successful /models probe as sufficient provider validation"},{"headRefName":"feat/gate-integrity-inert","number":128,"state":"OPEN","title":"fix(inert): create inert_to_graph.py sans orphan @covers; remove stale ActualRow/ActualsLedger from disposition"},{"headRefName":"feat/gate-perf-product","number":127,"state":"OPEN","title":"perf(test): cut test-suite wall-clock ~16x (serve_forever poll + xdist + DNS)"},{"headRefName":"dependabot/github_actions/github-actions-911e50acf6","number":86,"state":"OPEN","title":"ci: bump the github-actions group across 1 directory with 6 updates"}]
```
### Gate
```
  https://www.shellcheck.net/wiki/SC1122 -- Nothing allowed after end token. ...
shellcheck: ADVISORY — findings above are non-blocking (shellcheck-clean tracked separately)
summary: 18 passed, 0 failed
```
### Roadmap (canonical — fleet/report.sh)
```
CHARON FLEET ROADMAP
====================

PROJECT 1 — ROUTER

  Wave 1 — sense (meter)
    ✅  Done  R1                         meter-model-provider           real per-call cost sensor
    ✅  Done  R4                         meter-wire                     wire real cost into decisions
    ✅  Done  R5                         cost-rank-auto                 sort pools by metered cost
  Wave 2 — decide (brain)
    ✅  Done  R2                         router-core                    price-sorted order + smart failover
    ✅  Done  R3                         capability-matrix              which providers serve what + quirks
    ✅  Done  R7                         capability-engine              one brain for routing
    ✅  Done  R8                         latency-signal                 fail over slow providers
    🟣  next  DECOMPOSE-MODEL-WIRING     decompose-model-wiring         wire decompose_planner/surface/recommend + tests (chunk of WORK-DECOMPOSER)
  Wave 3 — class-fix (wiring & test discipline)
    🟠  now   R43                        wiring-audit                   sweep gateway for built-but-inert features → wired/inert matrix — audit delivered (WIRING-AUDIT-MATRIX.md), PR #20 still DRAFT (not merged)
    🟣  next  R44                        dogfood-gate                   e2e merge-gate: real-config request asserts observable effects
    🟣  next  R45                        inert-startup-check            startup self-check: active vs inert optional components (fail-loud)
    🟣  next  DEDUP-GRAPHS-LEDGERS       dedup-graphs-ledgers           delete ActualsLedger/ActualRow per inert triage (after GATE-INTEGRITY-A)
    🟠  now   R43-WIRING-AUDIT           r43-wiring-audit               READ-ONLY sweep: built-but-inert features → wired/inert matrix
  Wave 3a — foundation & balance
    ✅  Done  R46                        balance-wire                   construct BalanceTracker from gateway config (un-deads R4 record_spend) — merged PR #95 (b5d7948), verified live in gateway.load_config/_build_balance_tracker + test_gateway.py FAIL-ON-REVERT
    🟣  next  R47                        live-api-balance               neuralwatt adapter + TTL poller + wire balance into routing
    ✅  Done  R12                        drain-routing                  route to drain credit first — merged PR #95 (b5d7948), forwarder.py funding-class reorder + balance.py drain accounting
    ✅  Done  R11                        drain-then-park                spend prepaid credit then pause — merged PR #95 (b5d7948), sole-leg guard (forwarder.py _is_sole_leg) + funding-class re-arm table (balance.py park/unpark) + tests/test_drain_then_park.py
  Wave 3b — quick wins
    🟣  next  R14                        meter-session-tag              attribute spend to a session
    🟣  next  R16                        graceful-degrade               throttle+alert+auto-recover on refill
    🟣  next  R26                        catalog-reconcile-gpt5         reconcile catalog with live routing
    🟣  next  R30                        rfl-3                          image-aware provider routing filter
    ✅  Done  R15                        free-tier-order                adversarial best-order given exact limits
    ✅  Done  R17                        pricing-limits-checker         verify limits+pricing, alert on change
    🟣  next  FAIL-LOUD-CONTRACT         fail-loud-contract             ADR-0016 #5: structured providers_tried + bounded Retry-After in forwarder.py terminal
    🟣  next  FORWARDER-RECONCILE        forwarder-reconcile            retroactive ticket for the untracked feat/wire-tool-repair work
  Wave 3c — bigger
    🟣  next  R10                        free-tier-quota-spill          spill when a tier caps
    🟣  next  R13                        pools-simplification           cut the pool sprawl
  Wave 3d — deferred (not dropped)
    🟤  next  R9                         work-routing-to-charon         route fleet work through gateway
    🟣  next  R18                        provider-probe-fix             fix provider key probe validation
  Wave 4 — provider integration
    🟣  next  R19                        provider-url-helper            unify provider URL construction helper
    🟤  next  R20                        openrouter-flakiness-fix       flatten openrouter wrapped error fields
    🟤  next  R21                        longcat-provider               add longcat provider integration
    🟤  next  R22                        cooldown-fix3                  audit cooldown retry-after edge cases
    🟤  next  R23                        provider-flatrate              add flat-rate cheap providers
    🟤  next  R24                        sr-12                          restore opencode-zen provider preset
  Wave 5 — catalog & pricing
    🟤  next  R25                        catalog-sync-drift             sync catalog and detect drift
    🟤  next  R27                        catalog-search-curate          search and curate model catalog
    🟤  next  R28                        nanogpt-primary-review         review nanogpt primary routing policy
  Wave 6 — RFL console
    🟣  next  R29                        rfl-5                          optional context compaction for long chats
    🟤  next  R31                        rfl-2                          chat playground and served-model view
    🟤  next  R32                        rfl-4                          console limit editor with hot-reload
  Wave 7 — SR routing
    🟣  next  R33                        sr-4                           fix smart-routing doc inaccuracies
    🟣  next  R34                        sr-3                           cache correctness and status counters
    🟤  next  R35                        gateway-routing-decompose      tracked gateway routing decompose trigger
    🟤  next  R36                        zen-drift-cleanup              clean live zen model config drift
    🟤  next  R37                        sr-6-phase2                    bidirectional openai anthropic translation
    🟤  next  R38                        gpt5-pool-reorder              reorder live gpt-5 pool order
  Wave 8 — capability & quality
    🟣  next  R39                        workclass-taxonomy             classify tasks into work classes
    🟤  next  R40                        explore-promote                risk-gated model explore and promote
    🟤  next  R41                        bench-oob-grading              out-of-band benchmark grading integrity
    🟤  next  R42                        pff-p2                         opt-in cross-model substitution
  Model-Trust
    ✅  Done  DETENTION-REDLINE          detention-redline              scorecard block-rate excludes a model from a work_class chain
    ✅  Done  WORK-DECOMPOSER            work-decomposer                strong planner splits a broad change into single-domain sub-tickets
    ✅  Done  MODEL-PREFLIGHT            model-preflight                OOB-graded battery screens a candidate model on our failure modes
    ✅  Done  PROVIDER-CATALOG-REFRESH   provider-catalog-refresh       auto model<->provider mapping on a schedule (wired)
    ✅  Done  ADD-PROVIDER-MECHANIZE     add-provider-mechanize         one-command gateway provider add
    ✅  Done  DECOMPOSE-EFFORT-AXIS      decompose-effort-axis          effort axis on the decompose gate (EFFORT-WIRE+ESTIMATOR merged)
    ✅  Done  MODEL-LIFECYCLE            model-lifecycle                fresh-install onboard + scheduled keep-fresh orchestrator — merged PR #117 (69c115d)

PROJECT 2 — BRIDGE

  Wave A — substrate
    ✅  Done  B1                         phase-0-1-substrate            lay the bridge foundation
  Wave B — active bridge
    🟣  next  B2                         phase-2-active                 push notifications across sessions
    ⚪  next  B3                         roci-coordinator               run a durable session coordinator
    🟤  next  B8                         durable-bridge-phase-2         bridge daemon watch and renewal
  Wave C — portable engine
    🟣  next  B5                         obol-adr-0008                  one portable orchestration store
    🟣  next  B6                         work-engine-d10                move the work engine in-tree
    🟣  next  B7                         work-converge-review           one modular work tool (SLOP+Charon)
  Wave D — ranking
    🟤  next  B4                         benchmark-v2                   rank models by real outcomes
  Wave E — durable bridge & writeback
    🟤  next  B9                         dsgn-writeback                 design ticket write-back sink

PROJECT 3 — FLEET

  Wave A — droid isolation
    ✅  Done  F1                         worktree-leak-guard            stop droid work leaking into main
    ✅  Done  F2                         auto-done-on-merge             close tickets when PRs merge
    ✅  Done  F3                         needs-push-gate                block exit with unpushed work
  Wave B — session gates
    ✅  Done  F4                         end-session-gate               require clean board before exit
    ✅  Done  F5                         checkin-in-submit              check in on every submit
    ✅  Done  F6                         deploy-key-derive              derive deploy keys, never hardcode
    ✅  Done  F7                         board-correctness              keep the board state valid
  Wave C — done validation
    ✅  Done  F8                         refuse-unverified-done         reject unmerged work as complete
    ✅  Done  F9                         done-unmerged-red              flag unmerged tickets claiming completion
    ✅  Done  F10                        retire-done-ordering           retire finished tickets in order
  Wave D — gate & reporting
    ✅  Done  F20                        report-renderer                one canonical fleet status report
    ✅  Done  F21                        gate-exclude-goldens           drop benchmark fixtures from the gate
    ✅  Done  F22                        done-close-archived            record merge-proof on archived tickets
    ✅  Done  F24                        fleet-gate-repoint             gate runs fleet tests not product ones
    ✅  Done  F27                        access-check                   probe+report host access at boot
    ✅  Done  F44                        web-roadmap-generator          self-refreshing web roadmap from ROADMAP.tsv
  Wave H — board & gate
    🟣  next  F45                        project-audit-gate             fact-audit + re-sequence at project/wave start
    🟣  next  F30                        difficulty-schema              enforce difficulty field on tickets
    🟣  next  F31                        wire-mocklint-enforce          enforce fabricated-mock lint in gate
    🟣  next  F43                        project-membership-gate        gate: new tickets fold into a project
    🟤  next  F32                        board-reds-triage              triage pre-existing board reds
    🟤  next  F33                        workclass-backfill-review      review low-confidence workclass backfills
    🟣  next  F46                        parallelizability-gate         launch-time gate: block launching a splittable effort (size>=M AND >1 independent surface per owns/collision-map) as a single SERIAL job without --serial-justified=<reason>; mechanizes the wall-clock rule NOW in the rig
    🟠  now   A1-LAND-GATE               a1-land-gate                   REFUSE-ON-RED gate in land.sh / land-push.sh + branch-protection note — see board/A1-LAND-GATE.md
    🟣  next  FINAL-E2E-REVIEW           final-e2e-review               adversarial E2E process-integrity gate before fleet resume on Charon Gateway
    🟠  now   GATE-INTEGRITY-A           gate-integrity-a               inert-side: determinism + orphan-covers + dispose ActualsLedger/ActualRow
    🟣  next  GATE-INTEGRITY-B           gate-integrity-b               coverage-side: ensure charon gate is full-green after A's inert fix
    🟠  now   GATE-PERF                  gate-perf                      xdist worker-crash isolation + poll_interval fix on product repo
    🟠  now   LAND-SH-POSTMORTEM         land-sh-postmortem             adversarial review of the destructive-op-without-guard class exposed by land.sh
    🟣  next  REACHABILITY-GATE          reachability-gate              cross-cutting audit + root-cause + gate for the recurring hardcoded-path class
  Wave E — automation brains
    🟡  next  F11                        work-optimizer                 COMPOSE (not rebuild): wire F46 parallelizability-gate (merged, fleet PR #37) + decompose-sizing's makespan N* (product feat/decompose-sizing) into one launch-time scheduler; absorbs F12's auto-close-on-completion step; see WCI-CONSOLIDATION.md
    🟤  next  F12                        auto-close                     FOLDED into F11 (auto-close-on-completion is F11's final scheduler step, not a separate brain) — most of this is ALSO already covered live by F2 auto-done-on-merge (done); see WCI-CONSOLIDATION.md
    🟤  next  F13                        recurrence-auditor             FOLDED — the concrete recurring-defect classes are now owned by REACHABILITY-GATE (cross-boundary hardcoded paths) + test_gate_registry_execution.py (orphaned gates, PR #119); generalized brain = Keystone KS21/KS29. No standalone scope remains; see WCI-CONSOLIDATION.md
    🟤  next  F14                        detector-lifecycle             FOLDED — detector/gate freshness now covered by test_gate_registry_execution.py's fail-loud wiring proof (PR #119) + Keystone KS29 registry-primitive drift-check when built; see WCI-CONSOLIDATION.md
  Wave F — session lifecycle
    🟠  now   F23                        session-end-deploy             auto-update 4-LOM at session close
    🟡  next  F28                        startup-context-diet           cut startup context and token cost
    🟣  next  F16                        autonomous-ttl                 time-box unattended runs
    ⚪  next  F19                        bridge-unregister-trap         unregister the bridge on exit
    🟣  next  F47                        no-dark-work                   register every session on the bridge + pickup-gate so no session runs dark and no report strands
    🟣  next  SYNC-SCHEDULE              sync-schedule                  scheduled worktree sync cadence for multi-checkout rigs
  Wave G — quality & hygiene
    🟣  next  F15                        worktree-cleanup               clean up orphaned worktrees
    ✅  Done  F17                        scorecard-auto-append          record model scores automatically
    ✅  Done  F18                        auto-log-model-lies            log models that claim false success
    🟣  next  F25                        repo-decl-central              declare product vs fleet repo once
    🟣  next  F26                        shellcheck-clean               make fleet scripts shellcheck-clean
    ✅  Done  F29                        post-gateway-wci-decompose     surgical gateway decompose: module-registry (PR #100/085e74f) + config-package (PR #99/6460ace) + providers-data (PR #98/5135e2e) — all 3 slices merged, unblocked Router W4-8
    🟣  next  B3-LOG-PRUNE               b3-log-prune                   fleet/log-prune.sh: age+size cap on fleet logs (idempotent, hard-scope to log files)
    🟠  now   B4-BRANCH-REAPER           b4-branch-reaper               fleet/branch-reaper.sh: reap merged branches + stale worktrees (DRY-RUN default)
  Wave I — CI & actions
    🟣  next  F34                        docker-smoke-cleanup           fix docker smoke cleanup trap
    🟣  next  F35                        sr-11                          mechanize actions version bumps
    🟤  next  F36                        sr-10                          enforce single-producer deploy hygiene
    🟤  next  F37                        test-exercises-change-guard    pre-push hook and fail-on-revert guard
  Wave J — handoff & doctrine
    🟣  next  F38                        handoff-mechanize              mechanize handoff generation and checking
    ✅  Done  F39                        handoff-pipefail               fix masked gate failure in handoff
    🟤  next  F40                        coordinator-doctrine-rollout   roll out coordinator doctrine v2
  Wave K — review policy
    🟤  next  F41                        atc                            final adversarial audit of build waves
    🟤  next  F42                        frontier-review-policy         design frontier review policy spec
  Rig fixes
    ✅  Done  LAND-SH-SAFE-SYNC          land-sh-safe-sync              land.sh sync must never destroy an uncommitted working tree — merged PR #24 (40ffdba)

PROJECT 4 — SECURITY

  Wave A — scrub & enforce
    ✅  Done  S1                         email-scrub                    remove operator email from repo
    ✅  Done  S2                         enforce-public-clean           keep private info out of repo
    🟠  now   S4                         scrub-name+name-guard          remove leaked name, block its return
  Wave B — preflight & history
    🟣  next  S5                         guard-pre-flight               catch secret leaks before push
    ⚪  next  S3                         history-purge                  erase secrets from git history
  Wave C — secrets & guardrails
    🟤  next  S6                         secret-hotrotate               hot-rotate secrets without restart
    🟤  next  S7                         push-guard-gitc-harden         harden destructive git -C bypass

PROJECT 5 — BACKLOG

  Wave A — grader & keys
    🟣  next  K3                         grader-secfix                  harden the grader against tampering
    🟣  next  K4                         bench-oob-reds-replay          grade models on past failures
    🟤  next  K7                         chutes-commandcode-keys        get missing provider API keys
    🟣  next  GRADER-SECFIX-RECONCILE    grader-secfix-reconcile        reconcile two divergent grader lineages into one canonical (security wins)
    🟣  next  REVIEWER-DOGFOOD-REDS      reviewer-dogfood-reds          dogfood reviewer against curated reds corpus; capture regressions
  Wave B — product UX
    🟣  next  K8                         tool-repair-mutating           fix mutating tool-repair behavior
    🟤  next  K9                         gui-svelte-build               rewrite console as svelte spa
    🟤  next  K10                        ux-polish                      batch first-run ux polish nits
    🟤  next  K11                        tier-recs                      setup wizard model recommendations
    🟤  next  K12                        cwd-config-verify              verify blocked acp config path
  Wave C — connect & dogfood
    🟤  next  K13                        connect-omp-wsl                fix omp config on wsl connect
    🟤  next  K14                        dogfood                        end-to-end out-of-tree dogfood run
    🟤  next  K15                        ohmypi-assess                  research omp integration feasibility
  Wave D — benchmark remnants
    🟤  next  K16                        bench-reds-replay              replay real reds as benchmark tasks
    🟤  next  K17                        dtc-6                          parametrize repeating test functions

PROJECT 6 — KEYSTONE

  Wave A — foundation
    ✅  Done  KS1                        mvp-core                       stdlib core + 3 gates + module contract + reuse-check + verify-self (built/reviewed/fixed/verified)
    ✅  Done  KS2                        doctrine-gates                 no_vacuous/no_skip_game/no_pipe_mask/fail_loud/leak_guard (mechanize green-is-not-proof)
    🟣  next  KS8                        coverage-goal                  coverage_ssot tracks % + classifies every rule mechanized/guidance/GAP; FAIL on mechanizable-rule-with-no-gate; goal=100% where logical
  Wave B — capability
    🟣  next  KS3                        graphify-real                  real Graphify integration + `ksf module add graphify` (full pillar B)
    🟣  next  KS4                        inert-code-gate                catch UNREGISTERED-inert via AST reachability (the real BalanceTracker case; NO half-measure)
  Wave C — apply & deploy
    🟣  next  KS5                        live-charon-dogfood            point KSF at LIVE Charon as the final dogfood; surface real inert/dead code
    🟣  next  KS6                        deploy-github                  GitHub-clean (leak_guard) + push; decide repo home
  Wave D — propagate
    🟣  next  KS7                        slop-integration               analyze+plan KSF adoption into SLOP/mediastack; reconcile with ms-enforce
  Wave E — gate library (pluggable, per-project logical)
    🟣  next  KS9                        lens-test-integrity            static-only-is-a-gap + dead-code + test-behavior-not-structure + mutation-testing
    🟣  next  KS10                       lens-no-duplicate-impl         one-canonical-path / no duplicate implementations (structural anti-rediscovery)
    🟣  next  KS11                       lens-design-deep-modules       complexity cap + deep-modules / interface-simplicity (APoSD pillar D)
    🟣  next  KS12                       lens-code-quality              type-discipline + lint/format clean (conditional: typed lang)
    🟣  next  KS13                       lens-security                  secrets-scan (gitleaks) + SAST (bandit/semgrep)
    🟣  next  KS14                       lens-supply-chain              dependency-pin + CVE scan (trivy/pip-audit); pin CI actions/images
    🟣  next  KS15                       lens-robustness                fresh-install/zero-data-never-500 + idempotency + test-independence (random order)
    🟣  next  KS16                       lens-artifact-integrity        hermetic standalone build+install+health + deterministic/reproducible build (deploy proof)
    🟣  next  KS17                       lens-change-discipline         ADR/decision-record (-> state-store) + migration-discipline (if DB) + surface-boundary
    🟣  next  KS18                       lens-anti-god-file             file/module size caps (shrink-only ratchet) + god-file/contention detector (too-many-owners = decompose trigger) + single-responsibility; module-per-capability = feature-level decomposition
    🟣  next  KS19                       lens-fragility                 detect/block fragile code: hardcoded-single-entity, bare-except/error-swallow, brittle-parse-where-structured, known-bad-revert-patterns, over-mocking-internals, flaky sources (time/random/net), generic-500-on-known-condition
    🟣  next  KS20                       lens-anti-accretion            gates are META-invariants over classes, registry-driven (add data not code); forbid per-instance gate proliferation; scale by registry entries (open-seam/anti-accretion) MUST RUN ON KSF ITSELF (dogfood) alongside size-cap(gate files) + single-entity-hardcode, so KSF cannot mint hardcoded/narrow/monolith/unwired gates without going RED
    🟣  next  KS21                       lens-code-tension              structural tension proxies (cheap, meta): multiple-source-of-truth / single-canonical-owner; composition-conflict (same data re-ordered by multiple passes = the R8/R2 shape); config-vs-reality drift; incomplete-stub-in-done-surface. Deep semantic contradictions stay with adversarial review, NOT a fuzzy find-all-bugs gate
    🟣  next  KS22                       lens-firing-layer              every registered/enforced gate/tool MUST be invoked in a real firing layer (CI/Makefile/pre-commit); wired-but-never-run = RED (meta-meta over the gate set). Both audits flagged it
    🟣  next  KS23                       lens-verification-delta        a SUCCESS/done claim requires a NON-EMPTY diff AND a test that fails on revert (revert-hunk-must-go-red); catches trust-the-report / unverified success
    🟣  next  KS24                       lens-drift                     declared != reality drift: config/catalog/pools vs live provider state; deployed artifact vs source checksum; dead/stale entries. Registry-driven (add a drift-check spec) ALGORITHM = desired-vs-observed reconciliation (k8s/Terraform pattern): content-hash/checksum, set-diff/bidirectional, subset/schema-conformance, graph-reachability, staleness-probe(TTL). = the registry primitive's discovery/drift leg (KS29)
    🟣  next  KS25                       lens-ai-judgment               first-class INDEPENDENT adversarial-review layer for the semantic residue gates can't mechanize (contradictions-in-meaning, design quality, blast-radius). Findings are GATED (must resolve); silence is NEVER a pass (green-is-not-proof). DToC for high-blast. Two-owner firewall: reviewer != builder; dev-time judgment separate from any runtime agent. Generalizes SLOP-AI-Agent aspiration + Charon work-engine quality-brain
    🟣  next  KS28                       consolidate-pattern-guard      collapse the pattern-scanning gates (leak_guard, no_pipe_mask + KS13 security, KS19 fragility, revert-patterns) into ONE registry-driven pattern_guard meta-gate: one enforcer, patterns = data rows (pattern/severity/scope). Retire the hardcoded-pattern scripts. Dogfoods KS20 anti-accretion. Build all future pattern lenses as registry rows, not scripts
    🟣  next  KS31                       component-tool-adapters        KSF gate-plugins are thin ADAPTERS over best-in-class INDUSTRY tools (ruff/mypy/bandit/gitleaks/semgrep/vulture/radon/mutmut/hypothesis/schemathesis/trivy/pip-audit/actionlint/hadolint/shellcheck/sqlfluff) + the meta-layer (registry-wire, red-proof, firing, coverage, fail-loud). NEVER reimplement a tool. Each = a fully-supported plug-in working once enabled. Map KS9/11/12/13/14/15 to specific tools. Custom gates ONLY for novel classes tools don't cover (inert/verification-delta/drift/firing-layer/code-tension/grounding). Charon currently uses only 3 of ~15 (ruff/mypy/pip-audit) -> adoption flows through KS5 apply-to-Charon
    🟣  next  KS32                       build-vs-adopt-gate            TOOL-FIRST gate: adding CUSTOM implementation for a new class requires a tool-eval record (best-in-class candidate + REAL test vs actual cases + verdict wrap/reject-because-X); missing record OR custom-when-a-tool-fits = RED. The tool-ecosystem analog of reuse-check. Registry-assisted (per-class tool registry).
  Wave F — agent grounding
    🟣  next  KS26                       component-agent-onboarding     mechanically ASSEMBLE a per-app agent GROUNDING bundle from live KSF artifacts: architecture+purpose one-pager, code-graph map (what exists + what it does), built-inventory+decisions (state-store), rules + role/job-description, how-to-learn (reconcile-first + lesson-ledger), how-to-ask-for-help (bridge/escalation). Freshness/drift-gated (map==code or the agent trains on lies). Role-filterable (runtime vs dev). Loaded at reconcile-first. Thin packaging over existing artifacts, NOT model fine-tuning. Portable per app (SLOP/Charon/future). This is what makes a 'dumb' agent competent
    🟣  next  KS27                       component-work-orchestration   DEFAULT-to-fan-out work planner: given an effort, auto-compute collision-free chunks (WCI: dedup->contention-axis->waves) from owns/surface + worktrees, launch one agent per chunk; SERIAL = explicit opt-out. The work-engine layer; mechanizes the wall-clock rule so it can't be forgotten
    🟣  next  KS29                       component-registry-primitive   ONE registry PRIMITIVE: declare a registry (schema+scope) -> auto conformance gate (entries valid) + discovery gate (fail-closed on unknown that should be in it) + drift check, for free. Instances: bad-patterns, config/thresholds, entrypoints(auto-derived), decisions, rules/doctrine, catalog/providers, lessons/reds. The single way to make a single-source-of-truth (mediastack registry+conformance-leg+discovery-leg, generalized)
    🟣  next  KS30                       enforcement-spine              the 'gate of gates': ONE `ksf enforce` entry composing rule-registry(KS29) + coverage-SSOT(KS8: every rule mechanized-or-explicit-guidance, no silent GAP) + gate-runner + firing-layer(KS22, every mechanized rule actually runs) + fail_loud (any violation/unwired = non-zero, never masked). Knows the rules, verifies none are broken, fails LOUD. Runs on KSF itself (dogfood) + any target project. Guarantees the MECHANIZED set; pure-judgment rules explicitly flagged guidance -> judgment layer(KS25)+human. Must NEVER pretend to enforce a judgment rule (fake-green)

PROJECT 7 — FOUNDATION

  Wave A — memory
    🟣  next  FN1                        memory-store-adopt             adopt basic-memory MCP store over memory/ + kill whole-dump hook + migrate ~50 notes
    🟣  next  FN2                        bitemporal-decay               shared valid-from/until+last-referenced decay for memory facts AND model-signal ledgers (fixes routing-brain decay, gap B2)
    🟣  next  FN3                        curation-pass                  scheduled dedup/conflict-flag/decay-to-archive; approval-gated (borrow /sleep + bd compact)
    🟠  now   FN1-MEMORY-STORE-ADOPT     fn1-memory-store-adopt         adopt basic-memory MCP store + kill whole-dump SessionStart hook + migrate ~50 notes
    🟠  now   FN2-BITEMPORAL-DECAY       fn2-bitemporal-decay           shared valid-from/until+last_referenced decay (memory facts + model-signal ledgers)
    🟠  now   FN3-CURATION-PASS          fn3-curation-pass              scheduled on-demand dedup/conflict-flag/decay-to-archive pass (approval-gated)
  Wave B — research-gate
    🟣  next  FN4                        research-gate                  mechanized research protocol: reuse-check-first + evidence-over-prose + registry(dedup/staleness->update) + completeness gate
    🟠  now   FN4-RESEARCH-GATE          fn4-research-gate              mechanized research protocol: reuse-check + evidence + registry + completeness
  Wave C — anti-accretion
    🟣  next  FN5                        registry-sweep                 audit product+rig+KSF for smart-registry candidates -> apply KS29 primitive (kills collision/accretion classes); F29 registry = candidate #1
    🟠  now   FN5-REGISTRY-SWEEP         fn5-registry-sweep             audit product+rig+KSF for smart-registry candidates (KS29 primitive)

Totals:  ✅ done=45  🔵 in-review=0  🟠 building=14  🟡 queued=2  🟣 designed=82  🟤 parked=43  ⚪ not-started=3
```
### Board
```

  CHARON-FLEET STATUS @ 2026-07-14T12:25:19Z

  DROIDS (live tabs)        TIER    UPTIME    WORKING-ON
  (no droid tabs running)

  BOARD
  ID     TIER    STATE     BRANCH                 HELD-BY / NOTE
  A1-LAND-GATE strong  PR-OPEN   feat/a1-land-gate      38h41m ago
  ADD-PROVIDER-MECHANIZE strong  PR-OPEN   feat/add-provider-mechanize 7h24m ago
  B3-LOG-PRUNE economy ready     chore/b3-log-prune     -
  B4-BRANCH-REAPER economy PR-OPEN   chore/b4-branch-worktree-reaper 38h45m ago
  BENCH-OOB-GRADING frontier ready     feat/bench-oob-grading -
  DECOMPOSE-MODEL-WIRING frontier ready     feat/decompose-model-wiring -
  DEDUP-GRAPHS-LEDGERS strong  blocked   feat/dedup-actuals-graphs needs GATE-INTEGRITY-A
  DELETE-STATIC-RANK frontier blocked   feat/delete-static-rank needs PRICE-REFRESHER, DRAIN-THEN-PARK
  FAIL-LOUD-CONTRACT strong  ready     feat/fail-loud-contract -
  FINAL-E2E-REVIEW frontier blocked   audit/final-e2e-review needs DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT
  FN1-MEMORY-STORE-ADOPT economy PR-OPEN   feat/fn1-memory-store  5h11m ago
  FN2-BITEMPORAL-DECAY economy PR-OPEN   feat/fn2-bitemporal-decay 4h49m ago
  FN3-CURATION-PASS economy PR-OPEN   feat/fn3-curation-pass 4h30m ago
  FN4-RESEARCH-GATE economy PR-OPEN   feat/fn4-research-gate 3h55m ago
  FN5-REGISTRY-SWEEP economy PR-OPEN   feat/fn5-registry-sweep 3h32m ago
  FORWARDER-RECONCILE strong  blocked   feat/forwarder-reconcile needs FAIL-LOUD-CONTRACT
  GATE-INTEGRITY-A strong  PR-OPEN   feat/gate-integrity-inert 5h53m ago
  GATE-INTEGRITY-B strong  blocked   feat/gate-integrity-coverage needs GATE-INTEGRITY-A
  GATE-PERF strong  PR-OPEN   feat/gate-perf-product 6h55m ago
  GRACEFUL-DEGRADE frontier ready     feat/graceful-degrade  -
  GRADER-SECFIX-RECONCILE strong  blocked   feat/grader-secfix-reconcile needs BENCH-OOB-GRADING
  HANDOFF-MECHANIZE economy PR-OPEN   feat/handoff-mechanize 2h54m ago
  HANDOFF-PIPEFAIL economy blocked   feat/handoff-pipefail  needs HANDOFF-MECHANIZE
  LAND-SH-POSTMORTEM strong  PR-OPEN   audit/land-sh-postmortem 5h48m ago
  LAND-SH-SAFE-SYNC strong  PR-OPEN   fix/land-sh-safe-sync  5h44m ago
  MODEL-PREFLIGHT frontier blocked   feat/model-preflight   needs BENCH-OOB-GRADING
  NO-DARK-WORK economy PR-OPEN   feat/no-dark-work      2h39m ago
  PRICE-REFRESHER strong  ready     feat/price-refresher   -
  PRICING-LIMITS-CHECKER strong  blocked   feat/pricing-limits-checker needs PROVIDER-PROBE-FIX
  PROJECT-MEMBERSHIP-GATE economy PR-OPEN   feat/project-membership-gate 1h56m ago
  PROVIDER-CATALOG-REFRESH frontier ready     feat/provider-catalog-refresh -
  PROVIDER-PROBE-FIX strong  PR-OPEN   fix/provider-probe-validation 5h25m ago
  PROVIDER-URL-HELPER strong  blocked   refactor/provider-url-helper needs PROVIDER-PROBE-FIX
  R43-WIRING-AUDIT strong  PR-OPEN   audit/r43-wiring-audit 34h52m ago
  REACHABILITY-GATE strong  ready     feat/reachability-gate -
  REPO-DECL-CENTRAL economy blocked   feat/repo-decl-central needs HANDOFF-PIPEFAIL
  REVIEWER-DOGFOOD-REDS strong  ready     feat/reviewer-dogfood-reds -
  RFL-5  frontier ready     feat/rfl-5-context-compaction -
  SR-4   economy PR-OPEN   feat/sr-4-smart-routing-doc-fix 1h33m ago
  STARTUP-CONTEXT-DIET strong  blocked   feat/startup-context-diet needs REPO-DECL-CENTRAL
  SYNC-SCHEDULE economy blocked   feat/sync-schedule     needs STARTUP-CONTEXT-DIET
  TOOL-REPAIR-MUTATING economy PR-OPEN   feat/tool-repair-mutating-gate 1h24m ago
  WEB-ROADMAP-GENERATOR standard ready     feat/web-roadmap-generator -
  WIRE-MOCKLINT-ENFORCE standard blocked   feat/wire-mocklint-enforce needs TEST-HARDEN-CONTRACT, GATE-INTEGRITY-B
  WORK-CONVERGE-REVIEW frontier PR-OPEN   docs/work-converge-review 36h00m ago
  WORK-ROUTING-TO-CHARON-ENGINE frontier ready     feat/work-routing-to-charon-engine -

  OPEN PRs (draft → operator merges)
  #132  feat/tool-repair-mutating-gate  [draft]
  #131  feat/sr-4-smart-routing-doc-fix  [draft]
  #130  feat/project-membership-gate  [draft]
  #129  fix/provider-probe-validation  [draft]
  #128  feat/gate-integrity-inert  [draft]
  #127  feat/gate-perf-product  [draft]
  #86  dependabot/github_actions/github-actions-911e50acf6  [READY-TO-MERGE]
  (CI per PR:  gh pr checks <n> --repo SLOP-Platform/charon)

  SUMMARY  droids:0   ready:12  claimed:0  PR-open:20  done:0  blocked:14

  (token/usage is NOT faked here — see Claude's own /usage. board.sh = the quick view.)

```
### Board validation
```
== validate_board ==
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/handoff-check.sh <- HANDOFF-MECHANIZE REPO-DECL-CENTRAL STARTUP-CONTEXT-DIET
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/handoff.sh <- HANDOFF-MECHANIZE HANDOFF-PIPEFAIL REPO-DECL-CENTRAL STARTUP-CONTEXT-DIET
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/preflight.sh <- HANDOFF-MECHANIZE STARTUP-CONTEXT-DIET
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/config.py <- DELETE-STATIC-RANK PROVIDER-URL-HELPER
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/forwarder.py <- FAIL-LOUD-CONTRACT FORWARDER-RECONCILE
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/gate_runner.py <- GATE-INTEGRITY-B WIRE-MOCKLINT-ENFORCE
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/gateway.py <- PRICING-LIMITS-CHECKER PROVIDER-PROBE-FIX
  INFO owns hand-off (dep-sequenced/historical, ok): tests/test_forwarder_fail_loud.py <- FAIL-LOUD-CONTRACT FORWARDER-RECONCILE
  WARN owns-path-missing: B3-LOG-PRUNE owns '/home/stack/charon-private/fleet/log-prune.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FAIL-LOUD-CONTRACT owns 'tests/test_forwarder_fail_loud.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FINAL-E2E-REVIEW owns 'fleet/state/FINAL-E2E-REVIEW.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FN2-BITEMPORAL-DECAY owns '/home/stack/charon-private/fleet/memory/bitemporal.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FN3-CURATION-PASS owns '/home/stack/charon-private/fleet/memory/curate.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FN4-RESEARCH-GATE owns '/home/stack/charon-private/fleet/research.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FN5-REGISTRY-SWEEP owns '/home/stack/charon-private/fleet/state/REGISTRY-CANDIDATES.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FORWARDER-RECONCILE owns 'tests/test_forwarder_fail_loud.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FORWARDER-RECONCILE owns 'tests/test_forwarder_tool_repair.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GRADER-SECFIX-RECONCILE owns 'fleet/benchmark/grader-daemon.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GRADER-SECFIX-RECONCILE owns 'fleet/benchmark/graders/reds_replay.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GRADER-SECFIX-RECONCILE owns 'fleet/benchmark/selftest/test_grader_daemon.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: LAND-SH-POSTMORTEM owns 'fleet/state/LAND-SH-POSTMORTEM.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: NO-DARK-WORK owns '/home/stack/charon-private/fleet/dark-work-check.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PRICING-LIMITS-CHECKER owns 'fleet/pricing-limits-check.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PRICING-LIMITS-CHECKER owns 'fleet/state/provider-pricing-limits.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PROVIDER-URL-HELPER owns 'src/charon/config.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: R43-WIRING-AUDIT owns '/home/stack/charon-private/fleet/state/WIRING-AUDIT-MATRIX.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: REACHABILITY-GATE owns 'fleet/checks/no-unreachable-paths.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: REVIEWER-DOGFOOD-REDS owns 'fleet/benchmark/reviewer-dogfood.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: REVIEWER-DOGFOOD-REDS owns 'fleet/state/REDS-CORPUS.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: RFL-5 owns 'src/charon/context_shaper.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: RFL-5 owns 'tests/test_context_shaper.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WCI-ADVISORY justified-disjoint-dep (ok): DEDUP-GRAPHS-LEDGERS -> GATE-INTEGRITY-A (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): FINAL-E2E-REVIEW -> MODEL-PREFLIGHT (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): GATE-INTEGRITY-B -> GATE-INTEGRITY-A (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): GRADER-SECFIX-RECONCILE -> BENCH-OOB-GRADING (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): MODEL-PREFLIGHT -> BENCH-OOB-GRADING (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): PROVIDER-URL-HELPER -> PROVIDER-PROBE-FIX (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): SYNC-SCHEDULE -> STARTUP-CONTEXT-DIET (marked real build/correctness prereq)
  WCI-ADVISORY semantic: prompt-intent contradiction / hidden coupling is NOT machine-checked — eyeball overlapping or dep-linked tickets by hand.
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: A1-LAND-GATE (difficulty=3, 3 owned surfaces) — decompose (fleet/decompose.sh A1-LAND-GATE) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: DECOMPOSE-MODEL-WIRING (difficulty=4, 6 owned surfaces) — decompose (fleet/decompose.sh DECOMPOSE-MODEL-WIRING) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: DEDUP-GRAPHS-LEDGERS (difficulty=3, 2 owned surfaces) — decompose (fleet/decompose.sh DEDUP-GRAPHS-LEDGERS) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: FAIL-LOUD-CONTRACT (difficulty=3, 2 owned surfaces) — decompose (fleet/decompose.sh FAIL-LOUD-CONTRACT) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: FORWARDER-RECONCILE (difficulty=3, 3 owned surfaces) — decompose (fleet/decompose.sh FORWARDER-RECONCILE) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: GRACEFUL-DEGRADE (difficulty=4, 3 owned surfaces) — decompose (fleet/decompose.sh GRACEFUL-DEGRADE) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: GRADER-SECFIX-RECONCILE (difficulty=3, 3 owned surfaces) — decompose (fleet/decompose.sh GRADER-SECFIX-RECONCILE) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: MODEL-PREFLIGHT (difficulty=4, 3 owned surfaces) — decompose (fleet/decompose.sh MODEL-PREFLIGHT) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: PRICING-LIMITS-CHECKER (difficulty=3, 3 owned surfaces) — decompose (fleet/decompose.sh PRICING-LIMITS-CHECKER) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: PROVIDER-CATALOG-REFRESH (difficulty=4, 2 owned surfaces) — decompose (fleet/decompose.sh PROVIDER-CATALOG-REFRESH) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: PROVIDER-URL-HELPER (difficulty=3, 4 owned surfaces) — decompose (fleet/decompose.sh PROVIDER-URL-HELPER) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: REACHABILITY-GATE (difficulty=3, 2 owned surfaces) — decompose (fleet/decompose.sh REACHABILITY-GATE) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: REVIEWER-DOGFOOD-REDS (difficulty=3, 2 owned surfaces) — decompose (fleet/decompose.sh REVIEWER-DOGFOOD-REDS) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: RFL-5 (difficulty=5, 2 owned surfaces) — decompose (fleet/decompose.sh RFL-5) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: STARTUP-CONTEXT-DIET (difficulty=3, 5 owned surfaces) — decompose (fleet/decompose.sh STARTUP-CONTEXT-DIET) or justify ('serial_justified: <reason>')
  WCI-ADVISORY parallelizability: SPLITTABLE-SERIAL: WEB-ROADMAP-GENERATOR (difficulty=3, 2 owned surfaces) — decompose (fleet/decompose.sh WEB-ROADMAP-GENERATOR) or justify ('serial_justified: <reason>')
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
A1-LAND-GATE.md  tier=strong  depends_on=
ADD-PROVIDER-MECHANIZE.md  tier=strong  depends_on=
B3-LOG-PRUNE.md  tier=economy  depends_on=
B4-BRANCH-REAPER.md  tier=economy  depends_on=
BENCH-OOB-GRADING.md  tier=frontier  depends_on=
DECOMPOSE-MODEL-WIRING.md  tier=frontier  depends_on=WORK-DECOMPOSER
DEDUP-GRAPHS-LEDGERS.md  tier=strong  depends_on=GATE-INTEGRITY-A
DELETE-STATIC-RANK.md  tier=frontier  depends_on=PRICE-REFRESHER, DRAIN-THEN-PARK
FAIL-LOUD-CONTRACT.md  tier=strong  depends_on=
FINAL-E2E-REVIEW.md  tier=frontier  depends_on=DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT
FN1-MEMORY-STORE-ADOPT.md  tier=economy  depends_on=
FN2-BITEMPORAL-DECAY.md  tier=economy  depends_on=
FN3-CURATION-PASS.md  tier=economy  depends_on=
FN4-RESEARCH-GATE.md  tier=economy  depends_on=
FN5-REGISTRY-SWEEP.md  tier=economy  depends_on=
FORWARDER-RECONCILE.md  tier=strong  depends_on=FAIL-LOUD-CONTRACT
GATE-INTEGRITY-A.md  tier=strong  depends_on=
GATE-INTEGRITY-B.md  tier=strong  depends_on=GATE-INTEGRITY-A
GATE-PERF.md  tier=strong  depends_on=
GRACEFUL-DEGRADE.md  tier=frontier  depends_on=ROUTER-CORE
GRADER-SECFIX-RECONCILE.md  tier=strong  depends_on=BENCH-OOB-GRADING
HANDOFF-MECHANIZE.md  tier=economy  depends_on=
HANDOFF-PIPEFAIL.md  tier=economy  depends_on=HANDOFF-MECHANIZE
LAND-SH-POSTMORTEM.md  tier=strong  depends_on=
LAND-SH-SAFE-SYNC.md  tier=strong  depends_on=
MODEL-PREFLIGHT.md  tier=frontier  depends_on=BENCH-OOB-GRADING
NO-DARK-WORK.md  tier=economy  depends_on=
PRICE-REFRESHER.md  tier=strong  depends_on=
PRICING-LIMITS-CHECKER.md  tier=strong  depends_on=PROVIDER-PROBE-FIX
PROJECT-MEMBERSHIP-GATE.md  tier=economy  depends_on=DIFFICULTY-SCHEMA
PROVIDER-CATALOG-REFRESH.md  tier=frontier  depends_on=
PROVIDER-PROBE-FIX.md  tier=strong  depends_on=RESPONSE-ADAPTER-UNIVERSAL, F29-REGISTRY-SLICE, F29-CONFIG-PKG, F29-PROVIDERS-DATA
PROVIDER-URL-HELPER.md  tier=strong  depends_on=PROVIDER-PROBE-FIX
R43-WIRING-AUDIT.md  tier=strong  depends_on=
REACHABILITY-GATE.md  tier=strong  depends_on=
REPO-DECL-CENTRAL.md  tier=economy  depends_on=HANDOFF-PIPEFAIL
REVIEWER-DOGFOOD-REDS.md  tier=strong  depends_on=
RFL-5.md  tier=frontier  depends_on=
SR-4.md  tier=economy  depends_on=
STARTUP-CONTEXT-DIET.md  tier=strong  depends_on=REPO-DECL-CENTRAL
SYNC-SCHEDULE.md  tier=economy  depends_on=STARTUP-CONTEXT-DIET
TOOL-REPAIR-MUTATING.md  tier=economy  depends_on=
WEB-ROADMAP-GENERATOR.md  tier=standard  depends_on=
WIRE-MOCKLINT-ENFORCE.md  tier=standard  depends_on=TEST-HARDEN-CONTRACT, GATE-INTEGRITY-B
WORK-CONVERGE-REVIEW.md  tier=frontier  depends_on=
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

<Surprises, discoveries, design decisions the next session needs to know.
Gatekeeper decisions — e.g. "we chose Option B over Option A because…".>

## Collision matrix

| File | Owner (live) | Owner (next) |
|---|---|---|
| <filename> | <current ticket> | <next dependent ticket> |

## Open questions

<Anything that needs operator input before the next session can proceed.>

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

## Session summary — aayla-secura (2026-07-14)

### P0 SG-ACTIVE — DELIVERED (strong tier)
**Strong tier stood up: `minimax-m3` + `deepseek-v4-pro` named trusted via the HONEST battery**
(genuine fail-on-revert tickets, not the harness's linters). Meets the ≥1 (target ≥2) per-tier
threshold for STRONG. Economy = `gemma-4-31b` (conditional — cerebras free leg hangs on multi-file).
**Frontier = FUNDING-BLOCKED**: Claude/GPT/Gemini only reach SG via nanogpt (weekly-cap hit) +
openrouter (drained) — both exhausted; needs time (cap reset) or $ (fund openrouter / add a direct leg).

### What landed
- **Honest battery**: `test-quality-gate.py` (RED-proof: accept-check must fail on unmodified master);
  3 tickets tightened to real fail-on-revert (PROVIDER-URL-HELPER, SECRET-HOTROTATE, RFL-3);
  TOOL-REPAIR-MUTATING demoted to smoke-only (was passed by all → zero signal).
- **Outcome→scorecard logging LIVE**: wired charon-run/done/fleet-droid → grader-daemon → scorecard
  `source=live` lane (**4 → 31 rows**). 3 adversarial-review flaws found+fixed+**re-verified**
  (filename-collision MERGE-drop; provider-fault-blamed-on-model; unvalidated capture rows).
- **S4**: fleet-droid consults `assign.py` real-outcome ranking (falls back to static). Adversarially clean.
- **Board reconcile**: 6 stale-but-done tickets archived; GATE-INTEGRITY split A+B; RED fixed → GREEN.
  Confirmed the **auto-decompose gate (DECOMPOSE-DEFAULT-GATE) IS BUILT** on master.
- **Harness fixes**: `charon-run.sh` honors `CHARON_RUN_TIMEOUT_S` (was hardcoded 1800 → 30-min churn);
  `dogfood-to-scorecard.sh` emits FIXES (not detention-BLOCK) for genuine-attempt-with-fixable-miss.
- **Grounding**: TOOL-INVENTORY.md + `reuse-check.sh` (ksf) + EVAL-REGISTRY (consult-first). LiteLLM
  plugin-wrap = UNRESOLVED (not rejected). ADR-0003 fabricated LiteLLM rationale corrected. Provider
  roster consolidated → CG-PROVIDERS.md + CG-MODEL-CANDIDATES.md (40 models / 20 providers).
- **Parked** (PARKED-MODELS.tsv): phi-4 (leg opaque rc=3), claude-opus-4-8 + gpt-5.5 (leg-exhausted).
- Rig committed (b32a9e9). Dogfood eval worktrees reaped.

### Next wave / open (operator actions)
1. `! git -C /home/stack/charon-private push` (git push is deny-listed to the manager).
2. `sudo -u bench-grader bash fleet/state/scorecard-append-pathc-*121812.sh` (SECRET-HOTROTATE MERGE rows — newest pathc append).
3. **Frontier**: fund/recover provider legs (nanogpt cap reset OR openrouter/direct $) to preflight Claude/GPT/Gemini.
4. Ready product droids: GATE-INTEGRITY-A→B, FORWARDER-RECONCILE, DEDUP-GRAPHS-LEDGERS, DECOMPOSE-MODEL-WIRING.
5. Product primary stray edits (route via PR/droid, not manager direct-commit): `docs/adr/0003...` correction + `tools/inert_to_graph.py`.

### Next big build: S8 hold-lifecycle = GRACEFUL-DEGRADE (the north-star engine gap)
Unify the 3 hold mechanisms (park/cooldown/circuit) into ONE ACTIVE→HOLDING→PROBING→ACTIVE lifecycle;
add slow-axis + active re-prober + the ≥1-viable invariant (S10) with UP-escalation, then S11 tool-confirmed
adversarial acceptance. Full plan: fleet/state/CROSS-AUDIT-SYNTHESIS.md + memory charon-north-star-engine-mechanism.

### Gotchas
- Aggregator legs (nanogpt/openrouter) exhausted → frontier untestable until recovery/funding.
- Scorecard is bench-grader-owned; outcomes flow ONLY via the grader-daemon (must be running).
- **Detached runs need a PAIRED waiter** — sub-agents that "arm a monitor then end" orphan their run (recurred 3x).
- Non-blocking logging follow-ups → GRADER-SECFIX-RECONCILE: Flaw-2 regex over-broad (matches model output),
  Flaw-3 provenance anchor defeatable by same-uid forger; + charon-run attribution mislabel (kill→all-exhausted).

## Session-bridge
The session-bridge MCP (`mcp__session-bridge__*`) was DOWN/disconnected for most of this session
(daemon on Roci reached via the coordinator tunnel; the local proxy path in `.claude.json` was on a
stale socket — fixed to `coordinator-charon.sock`, takes effect next restart). Register on startup with
an unused Jedi name + `repo="charon"` via `mcp__session-bridge__register` if the bridge is up; heartbeat
folded into real work (`board()` ~600s TTL); unregister at session end. Coordinator host = Roci (10.0.1.51),
locked. PARTNERS this session = none (worked solo; droids launched by operator).
