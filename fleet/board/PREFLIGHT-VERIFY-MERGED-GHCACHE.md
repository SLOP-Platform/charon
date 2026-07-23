repo: charon-private
tier: strong
difficulty: 3
work_class: refactor
priority: 1
branch: fix/preflight-verify-merged-ghcache
depends_on: GITHUB-LIMITS-HARDENING
serial_justified: atomic coupled change — verify_merged in _lib.sh must call gh-cache.sh's batched lookup; splitting the two files lands a half-wired state (a call to a nonexistent helper, or an unused helper) and breaks the verdict-preservation contract. One surface, not two.
owns: fleet/_lib.sh, fleet/gh-cache.sh
work_class_note: |
  Latency class-fix (slowness IS a failure class). Preflight ≈117s warm / >120s cold (TIMES OUT). Root:
  `verify_merged` (fleet/_lib.sh:217,223) issues a raw per-marker `gh pr view` / `gh pr list --head` — an
  N+1 run over ~198 done-markers × 3 consumers (retire-done 37.9s, done_merge_gate 34.9s, reconcile) ≈ 73s
  = 62% of wall-clock. ADOPT-FIRST breach: `fleet/gh-cache.sh` was built for EXACTLY this ("retire-done did
  per-ticket gh calls — hundreds per sweep; this makes it a handful") but verify_merged never adopted it.
  Evidence: fleet/state/PREFLIGHT-ADVERSARIAL-REVIEW.md (independent adversarial review, this session).
  [[latency-is-a-failure-class]] [[slowness-triggers-investigation]] [[no-rig-as-product-adopt-dont-handroll]]
accept: |
  Route verify_merged's PR/branch merge proofs through the EXISTING batched, TTL-cached gh-cache.sh —
  do NOT hand-roll a new cache, do NOT add a new dependency. VERDICT-PRESERVING: same merge-truth data,
  fewer calls. Concretely:
    1. In fleet/_lib.sh, change `_vm_pr_merged` (the `gh pr view … --json mergedAt` at ~:217) and
       `_vm_branch_merged` (the `gh pr list --head … --state merged` at ~:223) to consult gh-cache.sh's
       cached merged-PR set instead of a fresh per-call `gh`:
         - branch proof → gh-cache's `branch_merged_pr` (or equivalent batched lookup);
         - PR-number proof → membership test "N ∈ the cached merged-set".
       One warm list per repo (TTL-shared) must serve all ~198×3 checks.
    2. If gh-cache.sh lacks a needed lookup (e.g. a by-number membership helper), ADD it to gh-cache.sh
       (its home), keep it batched/cached — never revert to per-marker gh in _lib.sh.
    3. Preserve EXACT verdict semantics: a marker that verified merged before MUST still verify merged;
       one that did not, must not. No change to any destructive-action / retire semantics in this slice.
  PROVE IT (fail-on-revert): add/extend a test asserting verify_merged makes O(1) gh list calls per repo
  (not O(markers)) AND returns identical merged/not-merged verdicts on a fixture set. Run the existing
  suites the reviewer named — needs-push-gate, verify-merged, test_github_limits.sh — all GREEN.
  TARGET: preflight warm ≈117s → ≈45s (measure before/after, record the numbers in the PR body).
  COMPLETION SELF-CHECK: if verify_merged still issues a gh call per marker, or any named suite is red, or
  the before/after timing is not recorded, INCOMPLETE — do not submit.
scope: |
  Kill the verify_merged per-marker gh N+1 by adopting the in-repo gh-cache.sh batched cache (verdict-
  preserving) — cuts preflight ~117s→~45s. Merge-gate code: preserve exact merge-truth semantics + prove
  with a fail-on-revert test and the verify-merged/needs-push/github-limits suites.
ds: |
  ## Dependencies & sequence
  - depends_on: (none). owns fleet/_lib.sh + fleet/gh-cache.sh — no other live ticket owns either (checked).
  - MERGE-CRITICAL: verify_merged gates retire/done correctness — semantics MUST be preserved; this is a
    perf-only refactor. Independent review before merge (operator: key/critical code gets adversarial review).
