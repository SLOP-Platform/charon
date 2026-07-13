# Charon Fleet — Session Handoff (2026-07-13T05:33:42Z) — ${SESSION:-unknown}

> **Per-session handoff.** Each session writes: `SESSION-HANDOFF-$SESSION.md`.
> No collisions. Next session reads ALL: `SESSION-HANDOFF-*.md`.

---

## Bootstrap (copy-paste into next session)

```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-mace-windu.md — you are the fresh Charon fleet MANAGER, tasked with completing the Model-Trust auto-management + Preflight mandate it contains and flipping back to fleet mode.
```

### Context discipline (token-burn guard — always on)
1. **Auto-compact ON.** At startup verify `grep autoCompactEnabled ~/.claude/settings.json` shows `true`. If not, STOP and tell the operator (see `fleet/SETTINGS-GUARD-PROPOSAL.md`) — a never-compacting transcript makes per-turn token cost climb all session.
2. **Sub-sessions write, don't dump.** A sub-session WRITES its findings to a file and returns only a 2-3 line pointer + the absolute path. NEVER paste a full sub-session report back into the primary.
3. **Read big docs in narrow slices, once.** Read handoffs/plans by line-range (offset/limit), never the whole file, never re-read each turn.
4. **Keep-alive is a light heartbeat.** Fold the bridge heartbeat into real work (`board()` TTL 600s); do NOT run a 4-min idle wakeup loop that reprocesses full context.

---

## NEXT-SESSION MANDATE (operator, 2026-07-13 — this session BUILT the machinery; next RUNS it to completion, then flips to fleet mode)

**Everything below must end merged, committed, pushed.** Product master = `b2f9853`, rig master = `611d16c`.

### SHIPPED this session (all merged)
- **Decomposer COMPLETE** — auto-decompose-at-intake is LIVE (surface + effort axes): DEC-PLANNER · AST-WRAP · EMIT-PARENT · VALIDATE-STRICT · DRIVER · DECOMPOSE-DEFAULT-GATE (#112) · EFFORT-ESTIMATOR (#113) · EFFORT-WIRE (#114).
- **Preflight CODE complete + 13 OOB graders DEPLOYED** (live at `$KEYS/preflight/` as bench-grader): seam (#23) · fixtures (#27) · runner `fleet/benchmark/preflight.sh` (#30) · graders (#32).
- **Model-Trust auto-management:** DETENTION-REDLINE (live, rig PR#21) · PROVIDER-CATALOG-REFRESH (#115 — auto model↔provider mapping, VERIFIED wired not inert) · ADD-PROVIDER-MECHANIZE = `fleet/add-provider.sh` (#33).
- **Infra:** land.sh data-loss fix (#24) · sync-checkouts (#28) · board durable.
- Keys saved locally: `~/.config/opencode/secrets/deepinfra.key` (32c) + `google-aistudio.key` (53c).

### NEXT SESSION MUST DO (operator directives, in order)
1. **Wire DeepInfra + Google AI Studio** with `bash /home/stack/charon-private/fleet/add-provider.sh` (keys saved; safe key handling built in). DeepInfra base `https://api.deepinfra.com/v1/openai` → `glm-4.7`=`zai-org/GLM-4.7`, `phi-4`=`microsoft/phi-4`. Google AI Studio base `https://generativelanguage.googleapis.com/v1beta/openai` → `gemini-2.5-pro`. Restart the gateway only when the fleet is idle. Facts: memory `charon-gateway-config-how-to`. (Operator prefers cheapest provider: DeepInfra for GLM+Phi-4, Google AI Studio for Gemini; OpenRouter is the fallback.)
2. **Run the PREFLIGHT slate** (automated via `preflight.sh <model>`): the models we've been USING (tier-models.tsv roster) AND the candidate slate (kimi-k2.6/Kimi-K2-Thinking · minimax-m2.5/MiniMax-M2 · gpt-oss-120b · phi-4 · qwen3.6-plus · gemma-4-31b · glm-4.7 · gemini-2.5-pro · gpt-5.1-codex-max + paid variants). **ESPECIALLY re-test the earlier FAILERS — deepseek-v4-pro, minimax-m3-free, deepseek-v4-flash, kimi-k2.6, glm-5.2 — to validate the decomposer thesis: do they succeed better on smaller single-domain chunks?** PRIORITIZED + INCREMENTAL + BOUNDED (never exhaustive — ~42 sessions/model). Controls: deepseek-v4-flash MUST-FAIL, a strong model MUST-PASS (proves the battery discriminates).
3. **Configure a trusted PLANNER model** for the decomposer (`_find_trusted_models` returns 0 now → `decompose.sh`/DEC-DRIVER `--live` can't run; only mock). Pick a strong non-detained model (claude-opus / gpt-5.x / a preflight winner).
4. **Build MODEL-LIFECYCLE** (`fleet/board/MODEL-LIFECYCLE.md`) — the orchestrator over add-provider → catalog-refresh → preflight → tier, on fresh-install bootstrap + a schedule; prioritized/incremental/bounded batching. Design-first.
5. **FINAL-E2E-REVIEW** (`fleet/board/FINAL-E2E-REVIEW.md`) — adversarial end-to-end review of the assembled pipeline once green + dogfooded → go/no-go to flip back to **FLEET MODE**.

### OPEN TICKETS
MODEL-LIFECYCLE · FINAL-E2E-REVIEW · PROVIDER-CATALOG-REFRESH scheduling (wire it to a TTL/cron) · SYNC-SCHEDULE (wire sync-checkouts into SessionStart+preflight) · LAND-SH-POSTMORTEM (blast-radius review of the land.sh data-loss class) · bench-grader deploy-source reachability fix (it can't read `/home/stack`; mechanize the `/tmp` staging into the deploy). DONE-but-unmarked: ADD-PROVIDER-MECHANIZE, DECOMPOSE-EFFORT-AXIS.

### GOTCHAS / carried context
- **land.sh is FIXED** (safe FF-only sync) — but the fleet is PAUSED (no droids running); the off-Claude gateway models were FABRICATING money-path work (R46 false-success, PRICE-REFRESHER inert+doctored) — that's WHY DETENTION + PREFLIGHT + DECOMPOSER exist. Don't resume droid builds until preflight picks trusted models.
- Adversarial review is STANDING for all money-path/gate work — it caught every fabrication this session behind green tests.
- Sub-agent model routing: Opus for reviews/graders/money-path/gates; Sonnet for bounded builds; Haiku for trivial checks — set `model` explicitly, never default to Opus.
- Scorecard is grader-owned (bench-grader) — feed via the staged script; manager can't write it.

---

## session-bridge

No active SESSION-BRIDGE coordination sessions at this handoff. The fleet is PAUSED (no droids running) pending preflight picking trusted models — do not resume droid builds until then.

---

## Auto-generated state (from `handoff.sh` run at 2026-07-13T05:33:42Z)

### Git
```
master


--- last 10 commits ---
2ba60be Merge pull request #112 from SLOP-Platform/feat/decompose-default-gate
3a03f7a feat(intake): DECOMPOSE-DEFAULT-GATE — auto-decompose as the default work-creation path
d6262da Merge pull request #111 from SLOP-Platform/feat/dec-ast-wrap
57ab40f Merge pull request #110 from SLOP-Platform/feat/dec-emit-parent
d678d4e feat(dec-ast-wrap): change_surface adapter over semantic_proof AST engine
9e9ffd6 Merge pull request #109 from SLOP-Platform/feat/dec-planner
df7a2b1 feat(decompose): add DEC-PLANNER LLM splitting brain
1d9ad71 feat(dec-emit): add optional parent linkage to Unit/PlanUnit
d9425d8 Merge pull request #106 from SLOP-Platform/feat/workclass-taxonomy
ee561b6 ci(gate-registry): register no-rig-import gate for check_no_rig_import.py
```
### Open PRs
```
[{"headRefName":"docs/work-converge-review-v2","number":108,"state":"OPEN","title":"docs(review-log): WORK-CONVERGE-REVIEW (sanitized)"},{"headRefName":"dependabot/github_actions/github-actions-dependabotHASH","number":86,"state":"OPEN","title":"ci: bump the github-actions group across 1 directory with 6 updates"}]
```
### Gate
```
  https://www.shellcheck.net/wiki/SC1122 -- Nothing allowed after end token. ...
shellcheck: ADVISORY — findings above are non-blocking (shellcheck-clean tracked separately)
summary: 12 passed, 1 failed
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
  Wave 3 — class-fix (wiring & test discipline)
    ?  next  R43                        wiring-audit                   sweep gateway for built-but-inert features → wired/inert matrix
    🟣  next  R44                        dogfood-gate                   e2e merge-gate: real-config request asserts observable effects
    🟣  next  R45                        inert-startup-check            startup self-check: active vs inert optional components (fail-loud)
  Wave 3a — foundation & balance
    🟣  next  R46                        balance-wire                   construct BalanceTracker from gateway config (un-deads R4 record_spend)
    🟣  next  R47                        live-api-balance               neuralwatt adapter + TTL poller + wire balance into routing
    🟣  next  R12                        drain-routing                  route to drain credit first
    🟣  next  R11                        drain-then-park                spend prepaid credit then pause
  Wave 3b — quick wins
    🟣  next  R14                        meter-session-tag              attribute spend to a session
    🟣  next  R16                        graceful-degrade               throttle+alert+auto-recover on refill
    🟣  next  R26                        catalog-reconcile-gpt5         reconcile catalog with live routing
    🟣  next  R30                        rfl-3                          image-aware provider routing filter
    ✅  Done  R15                        free-tier-order                adversarial best-order given exact limits
    ✅  Done  R17                        pricing-limits-checker         verify limits+pricing, alert on change
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
    🟠  now   WORK-DECOMPOSER            work-decomposer                strong planner splits a broad change into single-domain sub-tickets
    🟠  now   MODEL-PREFLIGHT            model-preflight                OOB-graded battery screens a candidate model on our failure modes
    🔵  next  PROVIDER-CATALOG-REFRESH   provider-catalog-refresh       auto model<->provider mapping on a schedule (wired)
    ✅  Done  ADD-PROVIDER-MECHANIZE     add-provider-mechanize         one-command gateway provider add
    ✅  Done  DECOMPOSE-EFFORT-AXIS      decompose-effort-axis          effort axis on the decompose gate (EFFORT-WIRE+ESTIMATOR merged)
    🟣  next  MODEL-LIFECYCLE            model-lifecycle                fresh-install onboard + scheduled keep-fresh orchestrator

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
  Wave E — automation brains
    🟡  next  F11                        work-optimizer                 schedule work for max parallelism
    🟡  next  F12                        auto-close                     close stale and landed tickets
    🟡  next  F13                        recurrence-auditor             catch repeat failures automatically
    🟡  next  F14                        detector-lifecycle             keep drift detectors current
  Wave F — session lifecycle
    🟠  now   F23                        session-end-deploy             auto-update 4-LOM at session close
    🟡  next  F28                        startup-context-diet           cut startup context and token cost
    🟣  next  F16                        autonomous-ttl                 time-box unattended runs
    ⚪  next  F19                        bridge-unregister-trap         unregister the bridge on exit
    🟣  next  F47                        no-dark-work                   register every session on the bridge + pickup-gate so no session runs dark and no report strands
  Wave G — quality & hygiene
    🟣  next  F15                        worktree-cleanup               clean up orphaned worktrees
    ✅  Done  F17                        scorecard-auto-append          record model scores automatically
    ✅  Done  F18                        auto-log-model-lies            log models that claim false success
    🟣  next  F25                        repo-decl-central              declare product vs fleet repo once
    🟣  next  F26                        shellcheck-clean               make fleet scripts shellcheck-clean
    🟣  next  F29                        post-gateway-wci-decompose     ACCEPTED surgical gateway decompose: module-registry + config-package + providers-data (unblocks Router W4-8)
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
    ?  next  LAND-SH-SAFE-SYNC          land-sh-safe-sync              land.sh sync must never destroy an uncommitted working tree

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
  Wave B — research-gate
    🟣  next  FN4                        research-gate                  mechanized research protocol: reuse-check-first + evidence-over-prose + registry(dedup/staleness->update) + completeness gate
  Wave C — anti-accretion
    🟣  next  FN5                        registry-sweep                 audit product+rig+KSF for smart-registry candidates -> apply KS29 primitive (kills collision/accretion classes); F29 registry = candidate #1

Totals:  ✅ done=36  🔵 in-review=1  🟠 building=4  🟡 queued=5  🟣 designed=76  🟤 parked=40  ⚪ not-started=3
```
### Board
```

  CHARON-FLEET STATUS @ 2026-07-13T05:33:47Z

  DROIDS (live tabs)        TIER    UPTIME    WORKING-ON
  (no droid tabs running)

  BOARD
  ID     TIER    STATE     BRANCH                 HELD-BY / NOTE
  A1-LAND-GATE strong  PR-OPEN   feat/a1-land-gate      7h49m ago
  ADD-PROVIDER-MECHANIZE strong  ready     feat/add-provider-mechanize -
  B3-LOG-PRUNE economy ready     chore/b3-log-prune     -
  B4-BRANCH-REAPER economy PR-OPEN   chore/b4-branch-worktree-reaper 7h53m ago
  BENCH-OOB-GRADING frontier ready     feat/bench-oob-grading -
  DECOMPOSE-DEFAULT-GATE strong  blocked   feat/decompose-default-gate needs WORK-DECOMPOSER
  DECOMPOSE-EFFORT-AXIS strong  blocked   feat/decompose-effort-axis needs DECOMPOSE-DEFAULT-GATE
  DELETE-STATIC-RANK frontier blocked   feat/delete-static-rank needs PRICE-REFRESHER, DRAIN-THEN-PARK
  DOCKER-SMOKE-CLEANUP economy PR-OPEN   chore/docker-smoke-cleanup 4h26m ago
  FAIL-LOUD-CONTRACT strong  ready     feat/fail-loud-contract -
  FINAL-E2E-REVIEW frontier blocked   audit/final-e2e-review needs DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT
  FN1-MEMORY-STORE-ADOPT economy ready     feat/fn1-memory-store  -
  FN2-BITEMPORAL-DECAY economy ready     feat/fn2-bitemporal-decay -
  FN3-CURATION-PASS economy ready     feat/fn3-curation-pass -
  FN4-RESEARCH-GATE economy ready     feat/fn4-research-gate -
  FN5-REGISTRY-SWEEP economy ready     feat/fn5-registry-sweep -
  GRACEFUL-DEGRADE frontier blocked   feat/graceful-degrade  needs ROUTER-CORE
  GRADER-SECFIX-RECONCILE strong  blocked   feat/grader-secfix-reconcile needs BENCH-OOB-GRADING
  HANDOFF-MECHANIZE economy ready     feat/handoff-mechanize -
  HANDOFF-PIPEFAIL economy blocked   feat/handoff-pipefail  needs HANDOFF-MECHANIZE
  LAND-SH-POSTMORTEM strong  ready     audit/land-sh-postmortem -
  LAND-SH-SAFE-SYNC strong  ready     fix/land-sh-safe-sync  -
  MODEL-LIFECYCLE frontier blocked   feat/model-lifecycle   needs PROVIDER-CATALOG-REFRESH, MODEL-PREFLIGHT, ADD-PROVIDER-MECHANIZE
  MODEL-PREFLIGHT frontier blocked   feat/model-preflight   needs BENCH-OOB-GRADING
  NO-DARK-WORK economy ready     feat/no-dark-work      -
  PRICE-REFRESHER strong  ready     feat/price-refresher   -
  PRICING-LIMITS-CHECKER strong  blocked   feat/pricing-limits-checker needs PROVIDER-PROBE-FIX
  PROJECT-MEMBERSHIP-GATE economy ready     feat/project-membership-gate -
  PROVIDER-CATALOG-REFRESH frontier ready     feat/provider-catalog-refresh -
  PROVIDER-PROBE-FIX strong  ready     fix/provider-probe-validation -
  PROVIDER-URL-HELPER strong  blocked   refactor/provider-url-helper needs PROVIDER-PROBE-FIX
  R43-WIRING-AUDIT strong  PR-OPEN   audit/r43-wiring-audit 4h01m ago
  R46-BALANCE-WIRE frontier ready     feat/r46-balance-wire  -
  REPO-DECL-CENTRAL economy blocked   feat/repo-decl-central needs HANDOFF-PIPEFAIL
  RFL-5  frontier ready     feat/rfl-5-context-compaction -
  ROUTER-CORE frontier blocked   feat/router-core       needs METER-MODEL-PROVIDER, COST-RANK-AUTO
  SR-3   economy ready     feat/sr-3-cache-correctness-stats -
  SR-4   economy ready     feat/sr-4-smart-routing-doc-fix -
  STARTUP-CONTEXT-DIET strong  blocked   feat/startup-context-diet needs REPO-DECL-CENTRAL
  SYNC-SCHEDULE economy ready     feat/sync-schedule     -
  TOOL-REPAIR-MUTATING economy ready     feat/tool-repair-mutating-gate -
  WEB-ROADMAP-GENERATOR standard ready     feat/web-roadmap-generator -
  WIRE-MOCKLINT-ENFORCE standard ready     feat/wire-mocklint-enforce -
  WORK-CONVERGE-REVIEW frontier PR-OPEN   docs/work-converge-review 5h08m ago
  WORK-DECOMPOSER frontier ready     feat/work-decomposer   -
  WORK-ROUTING-TO-CHARON-ENGINE frontier ready     feat/work-routing-to-charon-engine -
  WORKCLASS-TAXONOMY strong  PR-OPEN   feat/workclass-taxonomy 3h34m ago

  OPEN PRs (draft → operator merges)
  #108  docs/work-converge-review-v2  [READY-TO-MERGE]
  #86  dependabot/github_actions/github-actions-dependabotHASH  [READY-TO-MERGE]
  (CI per PR:  gh pr checks <n> --repo SLOP-Platform/charon)

  SUMMARY  droids:0   ready:27  claimed:0  PR-open:6  done:0  blocked:14

  (token/usage is NOT faked here — see Claude's own /usage. board.sh = the quick view.)

```
### Board validation
```
== validate_board ==
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/handoff-check.sh <- HANDOFF-MECHANIZE REPO-DECL-CENTRAL STARTUP-CONTEXT-DIET
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/handoff.sh <- HANDOFF-MECHANIZE HANDOFF-PIPEFAIL REPO-DECL-CENTRAL STARTUP-CONTEXT-DIET
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/preflight.sh <- HANDOFF-MECHANIZE STARTUP-CONTEXT-DIET
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/balance.py <- GRACEFUL-DEGRADE R46-BALANCE-WIRE
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/config.py <- DELETE-STATIC-RANK PROVIDER-PROBE-FIX PROVIDER-URL-HELPER
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/failover.py <- GRACEFUL-DEGRADE ROUTER-CORE
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/gateway.py <- PRICING-LIMITS-CHECKER PROVIDER-PROBE-FIX R46-BALANCE-WIRE
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/intake.py <- DECOMPOSE-DEFAULT-GATE DECOMPOSE-EFFORT-AXIS
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/providers.py <- PROVIDER-PROBE-FIX PROVIDER-URL-HELPER
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/router.py <- GRACEFUL-DEGRADE ROUTER-CORE
  WCI-ADVISORY justified-disjoint-dep (ok): DECOMPOSE-DEFAULT-GATE -> WORK-DECOMPOSER (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): FINAL-E2E-REVIEW -> DECOMPOSE-DEFAULT-GATE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): FINAL-E2E-REVIEW -> MODEL-PREFLIGHT (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): GRADER-SECFIX-RECONCILE -> BENCH-OOB-GRADING (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): MODEL-LIFECYCLE -> PROVIDER-CATALOG-REFRESH (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): MODEL-LIFECYCLE -> MODEL-PREFLIGHT (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): MODEL-LIFECYCLE -> ADD-PROVIDER-MECHANIZE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): MODEL-PREFLIGHT -> BENCH-OOB-GRADING (marked real build/correctness prereq)
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
DRAIN-ROUTING.md.parked
DRAIN-THEN-PARK.md.parked
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
POST-GATEWAY-WCI-DECOMPOSE.md.parked
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
DECOMPOSE-DEFAULT-GATE.md  tier=strong  depends_on=WORK-DECOMPOSER
DECOMPOSE-EFFORT-AXIS.md  tier=strong  depends_on=DECOMPOSE-DEFAULT-GATE
DELETE-STATIC-RANK.md  tier=frontier  depends_on=PRICE-REFRESHER, DRAIN-THEN-PARK
DOCKER-SMOKE-CLEANUP.md  tier=economy  depends_on=ACTION-PIN-POLICY
FAIL-LOUD-CONTRACT.md  tier=strong  depends_on=
FINAL-E2E-REVIEW.md  tier=frontier  depends_on=DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT
FN1-MEMORY-STORE-ADOPT.md  tier=economy  depends_on=
FN2-BITEMPORAL-DECAY.md  tier=economy  depends_on=
FN3-CURATION-PASS.md  tier=economy  depends_on=
FN4-RESEARCH-GATE.md  tier=economy  depends_on=
FN5-REGISTRY-SWEEP.md  tier=economy  depends_on=
GRACEFUL-DEGRADE.md  tier=frontier  depends_on=ROUTER-CORE
GRADER-SECFIX-RECONCILE.md  tier=strong  depends_on=BENCH-OOB-GRADING
HANDOFF-MECHANIZE.md  tier=economy  depends_on=
HANDOFF-PIPEFAIL.md  tier=economy  depends_on=HANDOFF-MECHANIZE
LAND-SH-POSTMORTEM.md  tier=strong  depends_on=
LAND-SH-SAFE-SYNC.md  tier=strong  depends_on=
MODEL-LIFECYCLE.md  tier=frontier  depends_on=PROVIDER-CATALOG-REFRESH, MODEL-PREFLIGHT, ADD-PROVIDER-MECHANIZE
MODEL-PREFLIGHT.md  tier=frontier  depends_on=BENCH-OOB-GRADING
NO-DARK-WORK.md  tier=economy  depends_on=
PRICE-REFRESHER.md  tier=strong  depends_on=
PRICING-LIMITS-CHECKER.md  tier=strong  depends_on=PROVIDER-PROBE-FIX
PROJECT-MEMBERSHIP-GATE.md  tier=economy  depends_on=DIFFICULTY-SCHEMA
PROVIDER-CATALOG-REFRESH.md  tier=frontier  depends_on=
PROVIDER-PROBE-FIX.md  tier=strong  depends_on=RESPONSE-ADAPTER-UNIVERSAL, F29-REGISTRY-SLICE, F29-CONFIG-PKG, F29-PROVIDERS-DATA
PROVIDER-URL-HELPER.md  tier=strong  depends_on=PROVIDER-PROBE-FIX
R43-WIRING-AUDIT.md  tier=strong  depends_on=
R46-BALANCE-WIRE.md  tier=frontier  depends_on=F29-REGISTRY-SLICE
REPO-DECL-CENTRAL.md  tier=economy  depends_on=HANDOFF-PIPEFAIL
RFL-5.md  tier=frontier  depends_on=
ROUTER-CORE.md  tier=frontier  depends_on=METER-MODEL-PROVIDER, COST-RANK-AUTO
SR-3.md  tier=economy  depends_on=
SR-4.md  tier=economy  depends_on=
STARTUP-CONTEXT-DIET.md  tier=strong  depends_on=REPO-DECL-CENTRAL
SYNC-SCHEDULE.md  tier=economy  depends_on=
TOOL-REPAIR-MUTATING.md  tier=economy  depends_on=
WEB-ROADMAP-GENERATOR.md  tier=standard  depends_on=
WIRE-MOCKLINT-ENFORCE.md  tier=standard  depends_on=TEST-HARDEN-CONTRACT
WORK-CONVERGE-REVIEW.md  tier=frontier  depends_on=
WORK-DECOMPOSER.md  tier=frontier  depends_on=
WORK-ROUTING-TO-CHARON-ENGINE.md  tier=frontier  depends_on=
WORKCLASS-TAXONOMY.md  tier=strong  depends_on=
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
