# Open-PR backlog audit — 2026-07-16

READ-ONLY audit. Repos:
- PRODUCT: `/home/stack/code/charon` → `SLOP-Platform/charon` (NOT Nnyan/charon — does not resolve)
- RIG: `/home/stack/charon-private` → `Nnyan/charon-private`

Master heads: PRODUCT `6805be1`; RIG `c0059c3` (session notes only, no code).

---

## 1. Headline findings

1. **RIG has NO CI AT ALL.** All 17 RIG PRs report `no checks reported`. RIG gate risk is
   entirely at **land-time (local gates)**, not CI. This inverts the usual strand analysis.
2. **PRODUCT: 6 of 7 PRs are RED on `gate`.** Only #166 is green. `wheel-smoke` passes on all 7.
3. **PRODUCT has ZERO file collisions.** Every product PR touches a disjoint file set.
   Product merge order is therefore driven purely by red/green, not collisions.
4. **PR #86 is a textbook strand victim** — a fix already on master cures it. Rebase = green.
5. **The RIG gate-tighteners are mostly INERT on merge** (they add gate scripts but do not
   wire them into land/done/preflight). Only #101 and the new DIET branch auto-run.
6. **Master PRODUCT `check_arch.py` is GREEN** (verified by running it) — so #170's
   circular-import failure is exposed by #170's own gate tightening, not pre-existing red.

---

## 2. PRODUCT PRs (SLOP-Platform/charon)

| PR | Title (short) | Draft | Mergeable | State | gate | Files |
|----|---------------|-------|-----------|-------|------|-------|
| 170 | API-DECOMPOSE-CYCLE-FIX | yes | MERGEABLE | BLOCKED | **FAIL** | `docs/review-log/API-DECOMPOSE-CYCLE-FIX.md`, `src/charon/decompose.py`, `tools/check_arch.py` |
| 169 | docs charon-flowchart | yes | MERGEABLE | BLOCKED | **FAIL** | `docs/CHARON-FLOWCHART.md`, `docs/review-log/CHARON-FLOWCHART.md` |
| 166 | startup-context-diet review-log | yes | MERGEABLE | **CLEAN** | **PASS** | `docs/review-log/STARTUP-CONTEXT-DIET.md` |
| 164 | CAPABILITY-ACTUALS-DEADREF-CLEANUP | yes | MERGEABLE | BLOCKED | **FAIL** | `docs/review-log/…md`, `src/charon/decompose_sizing.py`, `tests/test_check_inert_code.py`, `tools/check_inert_code.py`, `tools/inert-code-disposition.json` |
| 161 | WEB-ROADMAP-GENERATOR | yes | MERGEABLE | BLOCKED | **FAIL** | `docs/review-log/WEB-ROADMAP-GENERATOR.md` |
| 135 | FT-CATALOG-SEED | no | MERGEABLE | BLOCKED | **FAIL** | `docs/review-log/FT-CATALOG-SEED.md`, `src/charon/provider_presets/hosted.py`, `src/charon/routing_policy/free_tier_catalog.py`, `tests/test_free_tier_catalog.py` |
| 86 | dependabot: bump github-actions group | no | MERGEABLE | BLOCKED | **FAIL** | `.github/workflows/{ci,heavy,release,windows-exe}.yml` |

None are `BEHIND`/`DIRTY`. `BLOCKED` here = failing required `gate` check (+ draft status), not staleness.

### Attributed failure causes (from raw job logs — not guessed)

- **#170 — GATE TIGHTENER, genuinely red.** `[check-arch] FAILED (exit 1)`:
  `circular-import: charon.config → charon.config.keyprobe → charon.providers → charon.config`.
  The cycle is in files #170 does **not** touch. Master's own `check_arch.py` runs **clean**
  (verified locally). #170 edits `tools/check_arch.py` — its own review log admits it:
  *"The graph-builder fix also reveals a pre-existing logical cycle"* and *"exits clean WITH
  the fix modulo the out-of-scope config cycle."* So #170 tightens the arch gate and exposes a
  latent config cycle it declines to fix. **It cannot merge until the config cycle is fixed or
  explicitly allowlisted.** Once merged it will red-line any branch with a latent cycle.
- **#169 — PUBLIC-CLEAN VIOLATION (genuine, self-inflicted).** Leaks `/home/stack` three times:
  `docs/CHARON-FLOWCHART.md:363`, `docs/review-log/CHARON-FLOWCHART.md:30` and `:112`
  (the `:112` one also leaks an opencode tool-output path). Fix the docs; trivial.
- **#166 — GREEN.** Docs-only, single file, no collisions. Safest merge in the repo.
- **#164 — INFRA FLAKE, not a real failure.** `[pytest] FAILED (exit 1)` with
  `FileNotFoundError: [Errno 2] No such file or directory: '/tmp/pytest-of-stack/pytest-53'`
  at `tmp_path` fixture setup — the runner's pytest tmp dir vanished mid-run (self-hosted
  runner tmp reaping). **Re-run the job before touching the code.**
- **#161 — PUBLIC-CLEAN VIOLATION (genuine).** `docs/review-log/WEB-ROADMAP-GENERATOR.md:5`
  contains rig name `charon-private`. One line. Trivial fix.
- **#135 — GENUINE TEST FAILURE.** `tests/test_provider_response_contract.py:132`:
  presets `['featherless', 'github_models', 'ollama_cloud']` have no declared raw-shape
  fixture — must be added to `_OPENAI_SHAPE_PRESETS`. This is the contract gate working as
  designed: #135 seeds new presets without declaring their wire shapes.
- **#86 — STRAND VICTIM. Rebase cures it.** Fails public-clean with
  `hex token shape (>=40 chars)` on the dependabot-bumped action SHA pins
  (`actions/checkout@9c091bb…`, `actions/setup-python@ece7cb06…`).
  **But master already fixed exactly this**: commit `0a962dc` (2026-07-15)
  *"fix(public-clean): allow dependabot action-SHA pins in workflows"*, and
  `tools/check_public_clean.py:36` explicitly says the design goal is not to force
  *"every dependabot bump to re-author the exceptions ledger (false-positive)"*.
  #86's last CI run is **2026-07-13** — two days BEFORE the fix landed.
  **Action: rebase #86 onto master and re-run. No code change needed.**

---

## 3. RIG PRs (Nnyan/charon-private)

All: `no checks reported` (no CI in this repo). All `MERGEABLE`/`CLEAN` except #62 and #47.
All are drafts except #62 and #47.

| PR | Title (short) | Draft | State | Files |
|----|---------------|-------|-------|-------|
| 107 | BENCH-PROVISIONAL-SCORING (auto-commit) | yes | CLEAN | `.gitignore`, `docs/review-log/BENCH-PROVISIONAL-SCORING.md`, `fleet/board/REVIEWER-DOGFOOD-REDS.md`, `fleet/state/BENCH-PROVISIONAL-SCORING-DESIGN.md` |
| 106 | FOREMAN-MULTI-TRIGGER | yes | CLEAN | `docs/review-log/FOREMAN-MULTI-TRIGGER.md`, `fleet/foreman-cadence.sh`, `fleet/handoff.sh`, `fleet/tests/test_foreman_triggers.sh` |
| 105 | assign dispatch pick fix | yes | CLEAN | `docs/review-log/ASSIGN-DISPATCH-PICK-FIX.md`, `fleet/capability/assign.py` |
| 104 | MEMORY-INDEX-COMPACTION | yes | CLEAN | `docs/review-log/MEMORY-INDEX-COMPACTION.md`, `fleet/board/REVIEWER-DOGFOOD-REDS.md`, `fleet/hooks/memory-compact.sh`, `fleet/tests/memory-compact-hook.test.sh` |
| 103 | DROID-LIFECYCLE-REAP | yes | CLEAN | `docs/review-log/DROID-LIFECYCLE-REAP.md`, `fleet/fleet-droid.sh`, `fleet/foreman.sh`, `fleet/reap-orphans.sh`, `fleet/tests/test_droid_reap.sh` |
| 101 | GITHUB-LIMITS-HARDENING + large-file-guard | yes | CLEAN | `docs/review-log/GITHUB-LIMITS-HARDENING.md`, `fleet/checks/large-file-guard.sh`, `fleet/done.sh`, `fleet/gh-cache.sh`, `fleet/tests/test_github_limits.sh` |
| 99 | TSV-APPEND-UNIFY | yes | CLEAN | `docs/review-log/TSV-APPEND-UNIFY.md`, `fleet/capability/auto_append.py`, `fleet/capability/tests/test_tsv_append_unify.py`, `fleet/model-scorecard.sh` |
| 98 | ON-DEMAND-TOOL-AUDIT | yes | CLEAN | `docs/review-log/ON-DEMAND-TOOL-AUDIT.md`, `fleet/state/ON-DEMAND-TOOL-LEDGER.tsv` |
| 97 | SSOT-DRIFT-GATE | yes | CLEAN | `.gitignore`, `docs/review-log/SSOT-DRIFT-GATE.md`, `fleet/checks/msot-drift.sh`, `fleet/state/SSOT-REGISTRY.tsv`, `fleet/tests/msot-drift.test.sh` |
| 96 | REACHABILITY-GATE | yes | CLEAN | `.gitignore`, `docs/review-log/REACHABILITY-GATE.md`, `fleet/checks/no-unreachable-paths.sh`, `fleet/state/.reachability-allowlist`, `fleet/state/REACHABILITY-AUDIT.md` |
| 95 | WORK-GATE-UNIVERSAL | yes | CLEAN | `docs/review-log/WORK-GATE-UNIVERSAL.md`, `fleet/checks/work-gate.sh`, `fleet/hooks/pretooluse-work-gate.sh`, `fleet/tests/work-gate.test.sh` |
| 94 | STALE-CHECK-SH | yes | CLEAN | `docs/review-log/STALE-CHECK-SH.md`, `fleet/tests/stale-check.test.sh` |
| 93 | PRICING-LIMITS-CHECK-SH | yes | CLEAN | `.gitignore`, `docs/review-log/PRICING-LIMITS-CHECK-SH.md`, `fleet/pricing-limits-check.sh`, `fleet/state/provider-pricing-limits.tsv` |
| 92 | LAUNCH-PLAN-SH | yes | CLEAN | `fleet/tests/launch-plan.test.sh` |
| 90 | GATE-CREATION-STANDARDIZE | yes | CLEAN | `docs/review-log/GATE-CREATION-STANDARDIZE.md`, `fleet/GATE-CREATION-STANDARD.md`, `fleet/checks/gate-creation-standard.sh`, `fleet/state/GATE-GAP-LEDGER.tsv`, `fleet/tests/test_gate_creation_standard.sh` |
| 62 | SESSION-END-PUSH-GATE | no | **DIRTY / CONFLICTING** | `docs/review-log/SESSION-END-PUSH-GATE.md`, **`fleet/capability/__pycache__/availability.cpython-312.pyc`**, `fleet/end-session.sh`, `fleet/tests/end-session-push.test.sh` |
| 47 | LAND-SH-POSTMORTEM | no | **DIRTY / CONFLICTING** | `.gitignore`, `docs/review-log/LAND-SH-POSTMORTEM.md`, `fleet/state/LAND-SH-POSTMORTEM.md` |
| **DIET** (branch `feat/startup-context-diet`, `fee3eb8`, **no PR yet**) | STARTUP-CONTEXT-DIET | — | — | `fleet/MANAGER-OPERATING-RULES.md`, `fleet/START-SESSION.md`, `fleet/handoff.sh`, `fleet/preflight.sh` |

### The two conflicting PRs — deeply stale, need refresh-branch rebuild

- **#62 — 184 commits behind**, merge-base `57a28d4`. Conflict: `fleet/end-session.sh`
  *changed in both*. Also **commits a tracked `.pyc`**
  (`fleet/capability/__pycache__/availability.cpython-312.pyc`) — junk that must be dropped,
  and which is exactly what #101's `large-file-guard`/hygiene gates exist to catch.
- **#47 — 216 commits behind**, merge-base `c6f6e42`. Conflict: `.gitignore` *changed in both*
  (real `<<<<<<<` marker in merge-tree).

Both match the recorded `gate-hardening-strands-open-branches` class: the manager cannot
`git merge` master in. Per that memory: rebuild the net-diff onto master via
checkout-paths and land from a detached HEAD (mechanize as `refresh-branch.sh`).

---

## 4. FILE-COLLISION MATRIX

### PRODUCT — **no collisions.** Every file is touched by exactly one PR.

### RIG — 3 collision groups

| File | PRs | Severity | Notes |
|------|-----|----------|-------|
| `.gitignore` | **107, 97, 96, 93, 47** | **LOW (textual) / 5-way** | All five append a *semantically disjoint* negation line after the blanket `fleet/state/*` rule: `!fleet/state/BENCH-PROVISIONAL-SCORING-DESIGN.md` (107), `!fleet/state/SSOT-REGISTRY.tsv` (97), `!fleet/state/REACHABILITY-AUDIT.md` + `!fleet/state/.reachability-allowlist` (96), `!fleet/state/provider-pricing-limits.tsv` (93), `!fleet/state/LAND-SH-POSTMORTEM.md` (47). Same tail region → **2nd and later merges will textually conflict**. Resolution is always **keep both lines** — never pick a side. Merging one *unblocks* nothing but *dirties* the other four. |
| `fleet/handoff.sh` | **106, DIET** | **LOW — hunks disjoint** | DIET's hunks are at lines 80–190; #106's single hunk is at line 341. Git should auto-merge. See budget-gate caveat below. |
| `fleet/board/REVIEWER-DOGFOOD-REDS.md` | **107, 104** | **LOW** | Both are launcher auto-commit PRs appending red rows to a shared board file. Append-region conflict likely; resolution = keep both rows. |

No other RIG file is touched by more than one PR.

---

## 5. GATE-TIGHTENERS — order-critical analysis

Per `gate-hardening-strands-open-branches`: a PR that tightens a gate fails every
pre-existing open branch. **But this only bites if the gate actually RUNS.** I checked
whether each new gate wires itself into `land.sh` / `done.sh` / `preflight.sh`:

Currently only ONE check is wired at all: `fleet/preflight.sh:272,278 → checks/no-claude-executor.sh`.

| PR | Adds gate | Self-wires? | Strand risk |
|----|-----------|-------------|-------------|
| 90 | `fleet/checks/gate-creation-standard.sh` (meta-gate) + GATE-GAP-LEDGER | **NO** | **INERT on merge.** Ships the script; nothing invokes it. Safe to merge early. |
| 95 | `fleet/checks/work-gate.sh` + `fleet/hooks/pretooluse-work-gate.sh` | **NO** (no land/done/preflight edit) | **INERT** — but it ships a **PreToolUse hook**. It goes live the moment the operator wires it into `settings.json`. That wiring is *not* in this PR. Low merge risk, deferred activation risk. |
| 96 | `fleet/checks/no-unreachable-paths.sh` + allowlist | **NO** | **INERT on merge.** |
| 97 | `fleet/checks/msot-drift.sh` + SSOT-REGISTRY | **NO** | **INERT on merge.** |
| 101 | `fleet/checks/large-file-guard.sh` | **YES — edits `fleet/done.sh`** | **ORDER-CRITICAL.** Rewrites done.sh's merged-PR/owns matching onto a batched `gh-cache` index (kills the 30 req/min SEARCH-API burn) and adds large-file-guard. Changes done-gate behaviour for **every** ticket. Merge this on a quiet board and re-verify siblings' `done.sh` runs afterwards. Note #62's tracked `.pyc` is precisely the kind of thing this will now flag. |
| 93 | `fleet/pricing-limits-check.sh` | **NO** | **INERT on merge.** |
| **DIET** | **startup byte-budget gate in `fleet/preflight.sh`** | **YES — preflight runs every session** | **MOST ORDER-CRITICAL.** Auto-registers a **blocking P1 red** `startup-budget-exceeded` when any startup file exceeds budget. |
| 170 (PRODUCT) | tightens `tools/check_arch.py` | **YES — `gate` is a required CI check** | **ORDER-CRITICAL + currently self-red.** Once merged, every branch with a latent import cycle goes red. Must merge LAST in PRODUCT, and only after the `charon.config ↔ charon.providers` cycle is fixed/allowlisted. |
| 164 (PRODUCT) | edits `tools/check_inert_code.py` + disposition json | **YES — `gate`** | Mildly order-critical; changes inert-code gate surface. Merge after the flake re-run, before 170. |

### DIET budget-gate headroom (measured on `origin/feat/startup-context-diet`)

| File | bytes | budget | headroom |
|------|-------|--------|----------|
| `MANAGER-OPERATING-RULES.md` | 24487 | 26000 | **1513** |
| `START-SESSION.md` | 2617 | 3200 | **583** |
| `handoff.sh` | 16505 | 17500 | **995** |
| `handoff-check.sh` | 6238 | 6600 | **362** |
| `preflight.sh` | 35375 | 36000 | **625** |
| TOTAL budget | — | 89500 | — |

**Verdict on the DIET↔#106 interaction:** #106 adds **~223 bytes** to `handoff.sh`.
Post-DIET handoff.sh would be 16505 + 223 = **16728 < 17500**. **#106 fits, with 772 bytes
to spare.** So DIET-then-106 is safe — but the margin is thin, and headroom across all five
files is only 362–1513 bytes. **Any future PR touching these five files can trip the gate.**
Anything that must grow `handoff.sh`/`preflight.sh` should merge BEFORE DIET, or plan to
raise the budget in the same commit.

---

## 6. Board — blocked tickets and what unblocks them

From `bash fleet/status.sh` (RIG). Blocked tickets and their needs:

| Ticket | Needs | Unblocked by |
|--------|-------|--------------|
| `DONE-SH-INTEGRITY-FIX` | GITHUB-LIMITS-HARDENING | **RIG #101** |
| `LAUNCHER-CRASH-PARTIAL-DETECT` | DROID-LIFECYCLE-REAP | **RIG #103** |
| `SYNC-SCHEDULE` | STARTUP-CONTEXT-DIET, FOREMAN-WIRE | **DIET branch** (FOREMAN-WIRE already DONE) |
| `CREATION-GATE-DECOMPOSE-WIRE` | PROJECT-MEMBERSHIP-GATE | PROJECT-MEMBERSHIP-GATE (PR-OPEN, 50h — **not in my audit list**) |
| `METER-KWH-USD-FIX` | GATEWAY-NONTOKEN-METERING, FT-WIRE-QUOTA | not in audit scope (GATEWAY-NONTOKEN-METERING PR-OPEN) |
| `FT-WIRE-QUOTA` | FT-QUOTA-ENGINE, FT-CONFIG-SURFACE, **FT-CATALOG-SEED**, FAIL-LOUD-CONTRACT, FORWARDER-RECONCILE, PROVIDER-PROBE-FIX, GATEWAY-NONTOKEN-METERING | **PRODUCT #135** is one of seven — long pole, do not expect quick unblock |
| `GRADER-SECFIX-RECONCILE` | BENCH-OOB-GRADING | BENCH-OOB-GRADING (ready, no PR) |
| `MODEL-PREFLIGHT` | BENCH-OOB-GRADING | BENCH-OOB-GRADING (ready, no PR) |
| `FINAL-E2E-REVIEW` | DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT | downstream of BENCH-OOB-GRADING |

**Highest unblock leverage: RIG #101** (frees DONE-SH-INTEGRITY-FIX) and **RIG #103**
(frees LAUNCHER-CRASH-PARTIAL-DETECT). **BENCH-OOB-GRADING is the biggest blocker in the
system** — it gates 3 tickets and has no PR open at all.

---

## 7. RECOMMENDED MERGE ORDER

### PRODUCT
- **Wave 1:** #166 (green, docs-only, no collisions).
- **Wave 2 (cheap fixes):** #161 (strip `charon-private` from 1 line), #169 (strip `/home/stack` ×3).
- **Wave 3 (no code change):** #86 — rebase onto master to pick up `0a962dc`, re-run.
- **Wave 4:** #164 — re-run the flaked job first; only debug if it fails again.
- **Wave 5:** #135 — needs real work: declare raw-shape fixtures for
  `featherless`/`github_models`/`ollama_cloud`.
- **Wave 6 (LAST):** #170 — gate tightener, must resolve the config↔providers cycle first.

### RIG
- **Wave 1 (no collisions, inert):** #92, #94, #98, #99, #103, #105, #106.
  (#103 unblocks LAUNCHER-CRASH-PARTIAL-DETECT.)
- **Wave 2 (.gitignore group — serialize, keep-both on each conflict):** #93 → #96 → #97 → #107.
  Expect a trivial `.gitignore` conflict on each after the first. #107 also collides with
  #104 on `REVIEWER-DOGFOOD-REDS.md`.
- **Wave 3:** #104 (after #107; keep both board rows).
- **Wave 4 (order-critical, auto-wired):** #101 (edits done.sh — re-verify siblings after).
- **Wave 5 (order-critical, auto-wired):** DIET branch (open a PR first; budget gate goes live
  on every preflight). Merge **after** #106 so handoff.sh growth is already accounted for,
  though 106 fits either way.
- **Wave 6 (inert gate scripts — safe anywhere, parked last for review bandwidth):**
  #90, #95, #96/#97 already landed in wave 2.
- **Separate track (needs refresh-branch rebuild, not merge):** #62 (184 behind, end-session.sh
  conflict, drop the `.pyc`), #47 (216 behind, .gitignore conflict).

### Cross-repo note
PRODUCT #166 and the RIG DIET branch are the same ticket (STARTUP-CONTEXT-DIET) split across
repos: #166 is the review-log fragment, DIET is the implementation. #166 is green and free to
land now; it does not depend on DIET.
