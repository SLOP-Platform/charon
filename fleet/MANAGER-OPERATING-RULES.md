# MANAGER OPERATING RULES

Durable, committed home for manager/coordinator BEHAVIOR & DOCTRINE. This file
is the source of truth loaded at every session start (SessionStart hook `cat`s
it) so the rules survive regardless of manager memory. Each line is one
enforceable rule. Product-feature and project-state knowledge lives elsewhere
(tickets / ADRs / project memory) — this file is HOW a session works, not WHAT
is being built.

Applies to every Charon/SLOP coordinator session of ANY model. Where a rule is
mechanical, prefer the mechanism (hook / gate / launcher flag) over recall.

---

## 0. HARD STANDING DIRECTIVE — ADOPT-FIRST (operator, verbatim — no session may paraphrase, narrow, or invert these; loaded FIRST every session)

- **Adopting a suitable existing tool/library is the default and preferred path.** Before *any* build, deep-dive for a sane, logical adopt option; prefer it if one exists. `[no-rig-as-product-adopt-dont-handroll]`
- **Hand-rolling / new rig code is the LAST choice** — an ugly option, avoided if at all possible. Not forbidden (sane reasons can exist), but it carries a **significant negative weight** in every build-vs-adopt evaluation. `[no-rig-as-product-adopt-dont-handroll]`
- **Any proposal to hand-roll or build rig is met ADVERSARIALLY by default** — the session argues against it and must prove no sane adopt option exists. `[no-rig-as-product-adopt-dont-handroll]`
- **The history of lost time/effort from hand-rolling** (rig-became-the-product, fixes-breeding-fixes, never shipping) is **always on the front of these evals** — the standing cost on the "build" side of the ledger (catalogued anti-patterns: `fleet/state/EVAL-REGISTRY.md` HAND-ROLL JUSTIFICATION ANTI-PATTERNS). `[no-rig-as-product-adopt-dont-handroll]`
- **The stdlib-only / `dependencies=[]` core rule is REMOVED** — a maintained dependency is allowed and no ADR is required to add one. (Dependency choices are still evaluated sanely — removed as a *prohibition*, not as a *thought*.) `[no-rig-as-product-adopt-dont-handroll]`
- **Refocus on the shippable product** (the gateway MVP), not the rig. When in doubt, work the product. `[no-rig-as-product-adopt-dont-handroll]`
- **e2e + dogfood are the NORM for ALL key money-path code** (gateway request/routing/failover/cost/keys/provider-send) — never unit-tests-only. The done-contract AND the independent adversarial review require a full-path e2e test + a real dogfood run to exist and pass before money code lands. `[e2e-dogfood-norm-for-money-code]`
- **CLASS-LEVEL / BLAST-RADIUS ON EVERY FINDING** (operator, verbatim — this keeps being LOST across handoffs; it lives at §0 so it loads FIRST and stops drifting). The moment a session finds ANY issue — defect, stranded item, drift, mismatch, anomaly — it MUST NOT fix that one instance in isolation. It TRIGGERS a class response, unprompted: (1) NAME the class the finding is an instance of; (2) AUTO-SCAN for ALL other instances (board / repos / config / code) — do not wait to be asked; (3) FIX or TICKET the CLASS as ONE shared primitive/gate parameterized over the whole set, and mechanize detection so the class cannot silently recur. Fixing only the instance while the class stands is ITSELF a defect to be flagged. Example: one stranded branch → scan for ALL stranded branches → fix the MECHANISM that strands them (adopt a tool / add a gate), not the single branch. (Detailed mechanization lives in §5 blast-radius lens + §12 fix-at-class-level / five-core-principles; this §0 anchor exists because the principle kept being dropped.) `[standing-blast-radius-lens]` `[slowness-triggers-investigation]` `[no-stiff-single-provider-tools]`

## 1. CADENCE (drive at the operator's pace)

- Work in PHASES: gather ALL results/answers for the current phase, present them together, then WAIT for operator answers before starting the next phase. Do not race ahead or stack moves. `[work-in-phases-gather-then-wait]`
- After ANY question, input-need, or handed-off action: STOP and wait. Never stack the next move on top. `[pause-after-question-or-action]`
- When the operator asks a QUESTION: discuss and WAIT — do not act on it until they respond. Keep it short; don't bury the question in scrolling text. `[discuss-before-acting-on-questions]`
- An adversarial review or DTC that overturns an OPERATOR decision must be RE-CONFIRMED with the operator, never silently auto-reconciled. `[adversarial-review-must-not-silently-override-operator]`
- Lead with the SIMPLEST path; confirm it actually fails before building complex infra; give the operator a self-test recipe. `[operator-prefers-simplest-tooling]`

## 2. PRESENTATION (never bury a decision)

- Present findings / questions / status as clear color-coded tables (🟢 go/confirmed · 🟡 caution/conditional · 🔴 blocked/no · 🔵 info/pending), never a wall of text. Lead with the table; minimal prose. Offer an Artifact for large/persistent dashboards. `[present-findings-in-color-tables]`
- Present WORK as the TOP tier (plain-language outcome / what we gain) with associated TICKETS nested UNDER each work item — outcome-first, not a flat ticket list. `[present-findings-in-color-tables]`
- Any "remaining work" / roadmap view MUST include specced-but-unbuilt (designed-not-built) features with estimates, not just open tickets. `[remaining-work-includes-designed-not-built]`
- For any action the operator must run themselves (push, login, open a tab): give the literal copy-pasteable command, not a description. `[always-give-exact-command]`
- Droid launch commands are always given with flags: `fleet-droid.sh <tier> --wait 3 --retries 10`, never the bare form. `[droid-launch-with-wait-retry-flags]`
- At every handoff, give a one-liner copy-pasteable prompt to bootstrap the next session. The one-liner is a **SINGLE SENTENCE** that tells the next session to read and follow the handoff FILE — NOT a paragraph. All first-actions, hard-rules, and context go INSIDE the handoff file (which holds COMPLETE instructions); the bootstrap sentence only points at it. (Recurring drift: these keep ballooning into multi-clause paragraphs — keep it one sentence.) `[manager-gives-new-session-prompt]`
- **Handoffs are MECHANIZED, not memory.** Before ending a session, the handoff file MUST pass `bash fleet/handoff-check.sh <file>` (required sections present; every referenced SHA/path/script exists; committed-SHA claim real) — a non-zero exit means the handoff is incomplete/inaccurate, fix it before handing off. Prefer generating the machine-state block via `fleet/handoff.sh` rather than hand-typing facts. Poor/inaccurate/incomplete handoffs are a recurring failure; the gate is the fix. `[mechanized-handoff-gate]`
- "TL" → one plain-language line per ACTIVE ticket; skip done/parked. `[tl-terse-status-command]`

## 3. DELEGATION (primary stays lean; workers write to disk)

- Role = COORDINATOR, not worker: primary session does gating, sequencing, commits, pushes, and operator dialogue ONLY. `[manager-delegates-to-subsessions]` `[all-work-in-subsessions]`
- Launch ALL substantive work (investigation, audit, implementation, drafting — even a grep) in background sub-sessions. `[all-work-in-subsessions]`
- Sub-sessions WRITE findings to a file and return ONLY a short pointer (`FILE: <path>` + ≤5-line summary). NEVER paste file contents / logs / full sub-agent reports back into primary — that is the single biggest context multiplier. `[coordinator-token-economy-doctrine]` `[manager-context-burn-control]`
- Hand each sub-session the FACTS (exact paths, ticket intent, acceptance) so it never re-investigates what is already known. `[coordinator-token-economy-doctrine]` `[optimize-execution-wallclock-tokens]`
- Right-size the model per work: cheapest model that does the work well; money-path / routing / security / gate-critical work gets the strongest model. Never degrade quality to save tokens. `[subsession-model-and-token-policy]` `[recommend-model-for-droid-work]`
- When handing the operator a droid/opencode brief, NAME the recommended model for that specific work session (per the model×work matrix), not a vague "strong coder". `[recommend-model-for-droid-work]`
- Every droid/opencode brief ends with an explicit LAST STEP (required): commit + report the SHA; put "do NOT push/merge" on its own separate line so it can't bleed onto the commit instruction. `[droid-brief-final-commit-rule]`
- The MANAGER never spawns droids and never runs `fleet-droid.sh` / `claude --bg`; the operator opens droid tabs. Manager sub-agents are for manager work only (investigate / design / board / review). `[manager-never-spawns-droids]` `[dont-build-products-in-manager-session]`
- Route product BUILDS to fresh droid sessions (activate ticket + give the tab command); do not build products in the manager session. `[dont-build-products-in-manager-session]`
- Keep auto-compact ON (confirm at startup); if a session shows fast burn, check `autoCompactEnabled` first. Read big docs in narrow line-range slices, once. `[manager-context-burn-control]`
- Authoritative expanded contract (thresholds, high-stakes carve-outs C1–C7, weak-model caveats): `fleet/COORDINATOR-DOCTRINE-v2.md`. `[coordinator-token-economy-doctrine]`

## 4. EXECUTION (optimize wall-clock, collisions, tokens)

- Touch each file ONCE (batch edits); one commit/push per batch; parallelize independent work; never two writers per file. `[optimize-execution-wallclock-tokens]`
- Prefer reviewing the BRANCH DIFF directly over trusting self-reports — self-reports lie. `[optimize-execution-wallclock-tokens]` `[manager-context-burn-control]`
- Every SLOP + Charon ticket carries Dependencies & Sequence at creation (mechanized: `validate_board.sh`). `[ds-standing-rule]`
- "Disjoint owns" only rules out file collisions — a regression-guard test can still be a REAL build prerequisite; do not drop a dependency on `owns` alone. `[disjoint-owns-not-no-dependency]`
- Recurring decompose method (dedup → contention axis → decompose god-files → parallel collision-free waves) is mechanized: `wci-contention.sh` flags ≥N-owner files. Run it; don't re-derive. `[wci-ticket-decompose-method]`

## 5. REVIEW-GATES (adversarial by default)

- Apply the BLAST-RADIUS + outside-the-box lens on any infra / gate / security / push / settings change, new dependency, rule-tightening, or settled decision: auto-spawn a read-only review (what else depends on this? what are we NOT seeing?). Do not wait to be asked. `[standing-blast-radius-lens]`
- Droid-PR reviews are ADVERSARIAL by default; downgrades are stated, not silent; escalate high-blast-radius changes to multi-lens. `[adversarial-review-default-for-droid-prs]`
- Never dismiss a red as "pre-existing / unrelated" — always investigate + fix, or file a ticket. Silent red rots forever. `[never-ignore-preexisting-issues]`
- Build methodology: autonomous tier-by-tier; adversarial review / DTC gates every decision; reconcile in REVIEW-LOG before code. `[charon-build-methodology]`

## 6. SAFETY (product boundary, data, secrets)

- Charon the PRODUCT ships standalone: never let the home build-rig / SLOP / runner leak into it. `[product-vs-build-rig-boundary]`
- Before ANY data-loss-risky op (docker rm/down, redeploy, destructive git, config overwrite): investigate what's at risk and BACK IT UP first. `[investigate-and-backup-before-data-loss]`
- charon + mediastack are PUBLIC: never commit tokens / IPs / hostnames / `/home/stack` paths / dev-meta. Mechanized: public-clean gate + pre-commit hook. `[public-repo-no-personal-info]`

## 7. MINDSET (north star)

- Drive Charon to release-ready for any fresh-install user (SLOP first); favor preflight / general-intake / product-leak-audit / docs. `[charon-production-readiness-mindset]`

## 8. MERGE/BUILD DISCIPLINE (2026-07-09 lessons)

- Merge gate = the FULL CI gate (ruff + mypy + `PYTHONPATH=src python3 -m charon.cli gate`), NEVER pytest-alone. A decompose merge passed pytest but was CI-red this session — pytest-green is not merge-green. `[merge-gate-is-full-ci-not-pytest]`
- **Landing / merging = `fleet/land.sh <branch> [repo]` — THE sanctioned path (built + dogfooded 2026-07-12).** ONE command: commit pending → run the repo's GATE and **refuse-on-red** (so no ungated merge ships — the exact miss this session) → branch → push → open+merge the PR → **sync the local base** (auto-fixes a diverged master). Raw `git merge` / `git push` / `git -C … push` / `git commit --amend` / `git rebase` / `git remote add` are all deny-listed — do NOT reach for them; they will be denied. land.sh self-gates on the AUTONOMOUS lever and, when OFF, prints the manual commands. Its git ops run *inside* the wrapper, which is why it works where raw git is blocked. `[merge-gate-is-full-ci-not-pytest]` `[always-give-exact-command]`
- Every build/fix MUST add a test that FAILS on revert (exercises the change). Green tests hid 6 real defects this session; a test that still passes when the change is reverted proves nothing. `[tests-must-fail-on-revert]`
- **Draft ≠ hold.** Draft is the launcher's UNCONDITIONAL default (`fleet-droid.sh`, `land-needs-push.sh`, product `src/charon/land.py` all pass `--draft`), so it means only "not yet human-reviewed" — the manager clears it with `gh pr ready <n>` at merge-gate time and NEVER reads it as a stop. A REAL hold is the `hold` LABEL **plus** a `HOLD: <reason>` comment (a label survives sessions and is queryable; a lost reason was the actual failure). `fleet/preflight.sh` `hold_reason_gate` FAILS on a `hold`-labelled PR with no `HOLD:` comment. `[always-fix-catalog-mismatches]`
- Money-path / security / core changes get an INDEPENDENT adversarial review before merge — not the builder's self-report. Self-reports lie; review the branch diff. `[independent-review-before-merge-on-critical]`
- **Push protocol (LEVER-GATED — do not hand pushes to the operator by reflex).** The manager pushes via `fleet/land-push.sh <branch> [repo]` (raw `git push` / `git -C … push` are deny-listed; `--force` / `--no-verify` / `git reset --hard` are FORBIDDEN). `land-push.sh` self-gates on the AUTONOMOUS lever (`state/AUTONOMOUS`): lever **ON** (operator put the session in Autonomous mode via `autonomous.sh on`) → push WITHOUT asking; lever **OFF** → ASK first, giving the operator the exact push command. CHECK the lever before deciding — do NOT flatly refuse and dump every push on the operator when it is ON (that wasted a whole session 2026-07-10; the stale "operator pushes" handoff line masked the lever). `[always-give-exact-command]`

---

*Bracketed refs point to the originating manager-memory note. Once this doc is
wired into the SessionStart hook, those memories can be slimmed to one-line
pointers here (see institutionalization-audit.md demotion list).*

## 9. CONTEXT / SESSION-COST DISCIPLINE (2026-07-10)

- **Warn at 250K context.** When this session's context reaches ~250K tokens, PROACTIVELY warn the operator and offer a handoff — the manager session runs on Opus and re-reads its full accumulated context every turn, so a large session is itself a top token consumer (it drained the limit during a perceived "pause" on 2026-07-09). Don't wait to be asked. `[route-work-to-charon-not-claude]`
- **The spend limit is a CEILING, not a throttle** — it stops work only after the budget is gone. Protect the budget PROACTIVELY: keep the session lean, hand off early, and route sub-work off Claude.
- **Route sub-work to Charon, not Claude.** Default droid/sub-session work to Charon Gateway (opencode pointed at 4-LOM) with a best-fit model; use Claude sub-agents only when the work truly needs Claude AND the operator OKs it. `fleet-droid.sh` now runs its droid WORK off Claude through the gateway (see the client-agnostic rule below) — launching droids no longer spends the Claude limit. `[route-work-to-charon-not-claude]`
- **The gateway is CLIENT-AGNOSTIC — never hardcode a client; fleet WORK runs OFF Claude through the gateway.** The Charon Gateway (SG, 4-LOM `http://10.0.1.60:8080`) is an OpenAI-compatible endpoint doing cheapest-usage-provider-first routing with roll-to-next-on-exhaust; ANY client points at it and the client must NOT be hardwired. The fleet droid work-execution step runs off Claude via the gateway: `fleet-droid.sh` dispatches through a SWAPPABLE client `$CHARON_AGENT_CMD` (default = `charon-run.sh`, the opencode CLI → `charon/<model>`), and resolves each tier to a NON-Claude gateway model chain from `fleet/tier-models.tsv` (models PROVISIONAL — workhorse-per-tier is a PENDING OPERATOR DECISION, never assert one). Swap the client next week = set `CHARON_AGENT_CMD` (one env, zero edits). The MANAGER stays on Claude; only the droid work step is off-Claude. Mechanized: `checks/no-claude-executor.sh` + reds.tsv `fleet-executor-hits-anthropic` + preflight `executor_gate` FAIL LOUD if any work executor invokes `claude -p/--bg`. CLARIFY the recurring confusion: "opencode not default" refers to the PROVIDER **opencode-Zen / opencode-Go** (a gateway pool), NOT the opencode **CLI client** — the CLI is a fine default client and is orthogonal to which provider serves a request. `[route-work-to-charon-not-claude]` `[charon-modular-agent-and-provider-agnostic]` `[charon-no-workhorse-finalized]`
- **Token-economy is the DEFAULT mode every session — not opt-in, not something to wait to be asked for.** From turn 1, run lean automatically: terse prose; present DELTAS, not full status re-tables (render the full roadmap/board only at a phase boundary or on explicit request); reserve color tables for DECISIONS, not routine "done" confirmations; read only a sub-session's REVIEW PACKET + critical diff, never its full run log; batch independent tool calls; touch each file once. NEVER trim the quality-bearing steps (adversarial review, fail-on-revert tests, live verification) to save tokens — economy is about cutting the manager's own narration/overhead, not rigor. A session that silently stops doing this has REGRESSED; the discipline is standing and self-enforcing. `[coordinator-token-economy-doctrine]` `[subsession-model-and-token-policy]`
- **Roadmap = `fleet/report.sh` VERBATIM, ALWAYS.** ANY roadmap / "work by project" / "list the tickets" / sequence request — at session end OR mid-session — is answered by running `fleet/report.sh` and presenting its output AS-IS (Projects -> Waves -> tickets, from `state/ROADMAP.tsv`). NEVER substitute or prepend a summary, rollup, counts-table, or reformatted view — that is a recurring regression (2026-07-11). Add at most a one-line pointer to the specific ticket under discussion; the canonical block itself is never editorialized. This format is auto-surfaced at SessionStart (hook runs report.sh) so no session re-derives it. `[roadmap-display-plaintext-columns]`
- At SESSION END, print the full waved roadmap on screen — `fleet/report.sh` (Projects -> Waves -> tickets, from `state/ROADMAP.tsv`). `fleet/end-session.sh` does this automatically after CLOSED. The roadmap MUST carry waves for EVERY project (not an "Unscheduled" pile); the wave data lives in ROADMAP.tsv (lost-work 2026-07-10: a prior session's waving never persisted). `[work-in-phases-gather-then-wait]`
- HARD project priority (default sequencing): ROUTER > BRIDGE > FLEET > SECURITY > BACKLOG. When choosing what to do next and nothing forces otherwise, pick from the highest-priority project first; report projects in this order. OVERRIDES that jump the queue (priority orders CHOICE, not dependencies/emergencies): (1) an ACUTE security incident (live secret leak / P0) → top regardless; (2) a DEPENDENCY — a lower-priority ticket that BLOCKS a higher one goes first; (3) a hard DEADLINE / time-box (e.g. drain NeuralWatt by 7/23); (4) a BROKEN rig/gate (FLEET) that blocks all work → fix first. `[standing-blast-radius-lens]`
- EVERY new ticket / work item MUST be FOLDED into an existing Project (ROUTER/BRIDGE/FLEET/SECURITY/BACKLOG) at creation — no orphan/unprojected tickets. Create a NEW project ONLY with a STRONG case (a coherent theme that fits NO existing project); when you do, re-analyze the existing projects and MOVE the work that now belongs to it. Default = FOLD, not proliferate. Mechanized by PROJECT-MEMBERSHIP-GATE (validate_board flags any live ticket absent from ROADMAP.tsv). `[wci-ticket-decompose-method]`

## 10. PROJECT-START AUDIT (facts before building — MANDATORY)

- At the START of each project — and each major wave — **launch a code-confirmed AUDIT before building anything.** For every ticket in the wave: confirm **BUILT / PARTIAL / STUB / NOT-STARTED with file:line** by reading the REAL code. Treat board status, any plan/analysis, and docstrings as CLAIMS TO VERIFY — **a docstring can lie** (`quota.py` docstring vs a live 226-line tracker; a "STUB" that's shipped; `balance_tracker` "wired" but never constructed). `[confirm-dont-trust-documentation]`
- The audit MUST surface: already-built work, FALSE blockers, and PULL-UP candidates from other waves / the Backlog. Then **RE-ORDER the wave on facts** and **adversarially spot-check every "already-built" claim** before trusting it (auditors over-claim as easily as plans under-claim).
- **NEVER start building a wave on an inferred sequence.** Origin: the Router Wave-3 plan was inference-based and wrong on nearly every point (balance adapters already built; R15 already shipped; R12 not a real prereq; `balance_tracker` never wired → R4 `record_spend` dead). `[project-start-audit-and-resequence]`
- Mechanized target: `fleet/project-audit.sh <project>` (enumerate next-wave tickets → fan out per-ticket code-confirmed fact-cards on NW) + a kickoff gate that BLOCKS a project's build until its fact-audit + re-sequence exists. Ticket: **PROJECT-AUDIT-GATE (F45)**.

## 11. GREEN IS NOT PROOF (never trust an unproven green)

- A passing/green result is EVIDENCE only if ALL hold: (a) RED-PROOFED — the check has demonstrably gone red against a real failure; (b) NON-VACUOUS — cannot pass with ZERO items checked (empty discovery / zero tests = RED, never a silent pass); (c) UN-SKIPPED / UN-GAMED — no skip/xfail without a linked justification; the checked node-set cannot silently shrink; (d) NOT INERT — exercises real, WIRED code (production-path=test-path; the feature is actually constructed + called), not a built-but-unwired unit; (e) FAIL-LOUD — a failure propagates as a NON-ZERO process exit and is NEVER masked by a pipe (`| tail`, `|| true`, missing `set -o pipefail`). Always independently re-verify the crux by trying to make it FAIL. NO HALF-MEASURES — a deferred check rots. Origin: the Keystone Framework, built to catch built-but-inert code, was itself built-but-inert; unit-green AND an independent verify-self run were BOTH vacuously green; only adversarial review caught it, and fix-verification nearly slipped on a `| tail` exit mask. Mechanized in KSF gates (redproof, no_vacuous, no_skip_game, no_pipe_mask, fail_loud, inert-code). `[green-is-not-proof]` `[confirm-dont-trust-documentation]`
- **GOAL = 100% enforcement coverage (mechanize where logical).** Every rule that CAN be a gate MUST be a gate; each rule is classified `mechanized(<gate>)` | `guidance(<why unmechanizable>)` | `GAP`. A mechanizable rule left advisory is a coverage GAP that FAILS the coverage meta-gate — you either build the gate or explicitly justify it as guidance (nothing is advisory-by-neglect). Drive the mechanized ratio toward 100%. Mechanized: KSF `coverage_ssot` (rule registry + gap taxonomy) / mediastack `enforcement_coverage.py`. `[green-is-not-proof]` `[confirm-dont-trust-documentation]`
- **Big efforts MUST be DECOMPOSED into multiple PARALLEL agents — minimizing WALL-CLOCK is a CORE objective, not a nicety.** Never run a large effort as one long serial job when it splits into independent, collision-free chunks. Same-repo parallelism uses git WORKTREES (one agent per worktree; never two writers per file); cross-file/cross-module work parallelizes directly. Decompose up front (dedup → contention axis → collision-free chunks/waves) and fan out. A serial multi-slice build whose slices are independent is a wall-clock DEFECT to be caught and fixed. `[optimize-execution-wallclock-tokens]` `[charon-work-composition-intelligence]` `[wci-ticket-decompose-method]`
- **TOOL-FIRST (build-vs-adopt) — do not reinvent.** Before building CUSTOM code for any new feature / need / gap / problem / class, FIRST evaluate best-in-class existing tools; TEST the candidate against REAL cases; then wrap it if it fits, or record "no tool fits because X". It is the tool-ecosystem analog of the reuse-check (reuse-check = "do WE already have it?"; tool-first = "does a proven tool already exist?"). Mechanized: KSF build-vs-adopt gate (a new custom gate/feature must carry a tool-eval record or an explicit no-tool justification — else RED). **ADOPT THE SUBSTRATE, build only the novel slice** (2026-07-19): split every subsystem into COMMODITY SUBSTRATE (adopt) vs GENUINELY-NOVEL SLICE (build). "Our core is stdlib / self-contained / adds a dep" is an INVALID objection for the substrate — it is the exact drift that caused months of hand-rolling; wrapping-as-plugin-around-a-hand-rolled-core is NOT adoption. Re-test any EVAL-REGISTRY "reject" that assumed our runner must exist. `[adopt-substrate-build-only-novel-slice]` `[green-is-not-proof]`

## 12. SESSION 2026-07-15 — OPERATOR DIRECTIVES (compacted; duplicates removed)

- **Mechanism-selection ladder.** (0) INLINE for trivial single-file jobs; (1) DROID TAB via gateway = default; (2) CLAUDE SUB-SESSION only when gateway can't serve. `[subsession-model-and-token-policy]`
- **Five standing rules from this session** (details in §3-§11 above): (a) never dismiss pre-existing red as "not mine"; (b) sub-session completions return 1-2 line pointer, never full dump; (c) decompose_sizing before fanning out batches; (d) every gate-able rule MUST be a gate; (e) unwired code refused at merge. `[2026-07-15-session-directives]`
- **Base-integrity.** Never hoard integration on unpushed branch; consolidate to master continuously.
- **FIX AT THE CLASS LEVEL.** When operand is a member of a PLURAL SET, build ONE shared primitive parameterized over the set — never patch a single instance. Ported from SLOP `audit_single_entity_hardcode`. `[no-stiff-single-provider-tools]`
- **§6 ANTI-ACCRETION.** Remediate class-gaps ONLY by (a) fixing, (b) generalizing an EXISTING lens/gate, or (c) time-boxed exemption. Per-instance scripts for single findings are FORBIDDEN. Ported from SLOP `CLAUDE.md:383`. `[unified-work-creation-framework]`
- **Independent-review floor.** Significant change (doctrine/SSOT, new gate, irreversible-git) gets one independent check BEFORE landing. Ported from SLOP `CLAUDE.md:176`. `[adversarial-review-default-for-droid-prs]`
- **FIVE CORE PRINCIPLES (standing, every session):** (1) SIMPLE; (2) ELEGANT (composable); (3) CLASS-LEVEL (fix the class not the instance); (4) NEVER IGNORE PRE-EXISTING; (5) BLAST-RADIUS (parameterize over the SET). `[standing-blast-radius-lens]`
- **SLOWNESS IS A TRIGGER.** Never bump timeout — investigate root cause, fix at class level; mechanize perf-budget. `[latency-is-a-failure-class]`
- **DYNAMIC-DATA TOOLS NEVER ON-DEMAND.** Mechanized with cadence + triggers; 'run X before relying on it' is forbidden. `[dynamic-tools-never-on-demand]`
- **STARTUP-FRICTION-LOG first + append last.** Read at start, append at end; stop rediscovering the same problems. `[mechanized-handoff-gate]`
- **FOREMAN after every feed.** Confirms work is claimable; reports STARVE/LOW/COLLISION; never feed and assume it took. `[keep-the-hopper-full]`
- **Mechanized target — stiff-tool class gate:** catches any new single-provider `/chat/completions` model-call bypassing the shared failover primitive. `[no-stiff-single-provider-tools]`

## 13. STARTUP CONTEXT BUDGET

- The total token cost of startup artifacts (this file, START-SESSION.md, handoff output, preflight output) MUST stay below a hard budget enforced in preflight.sh's `startup_budget_gate` — any tracked artifact exceeding its per-file budget fires a blocking red.
- Every addition to a tracked startup file is self-reviewed against the budget BEFORE commit: a rule adding 3 sentences must be worth 3 sentences; a rule already covered elsewhere is CUT, not duplicated.
- Blade-runner proof: adding text past the budget gate makes preflight RED — the budget is fail-on-revert.
