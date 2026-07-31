repo: charon-private
tier: frontier
difficulty: 4
work_class: refactor
priority: 0
branch: feat/ksf-load-bearing
depends_on:
owns: fleet/state/KSF-CLASS-REGISTER.md, fleet/state/KSF-LOAD-BEARING-PLAN.md
serial_justified: |
  ONE precondition set. "Installable", "gate_runner finds gates", "inert_code is not noise" and
  "KSF gates itself in CI" are the four things that together make KSF capable of gating ANYTHING
  outside itself. Any three without the fourth still leaves a framework that cannot be adopted:
  installable-but-noisy is still unregisterable, and fixed-but-uncied still never runs.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree.
  Model note: opencode silently falls back to the DEAD gpt-5.4 pool for any model not in
  opencode.json's charon provider list (36 of 2567 gateway models). Verified listed AND funded
  2026-07-31: deepseek-v4-pro, gpt-oss-120b-groq, grok-build-0.1, minimax-m2.7, big-pickle.
source: |
  Operator approved FRAMEWORK-CONVERGE, then approved restructuring it into this after the
  two-lane KSF audit (2026-07-31) returned "right idea, not yet load-bearing".
note: |
  ## WHY THIS REPLACED FRAMEWORK-CONVERGE
  FRAMEWORK-CONVERGE would have converged SG + rig + SLOP onto KSF. The audit says do not:
  converging three repos onto an unready substrate is the same class of mistake the operator has
  spent months unwinding. This ticket makes KSF load-bearing FIRST. Convergence is re-decided
  afterwards, against evidence.

  ## FACTS (verified 2026-07-31 — audit reports are the source; confirm, do not re-derive)
  Source: `/tmp/ksfaudit/KSF-SURFACE-AUDIT.md`, `/tmp/ksfaudit/KSF-CLASS-CORPUS.md`
  (COPY BOTH into `fleet/handoff-notes/` as your first act — they live in /tmp and will be lost.)

  - KSF at `/home/stack/code/keystone`: 2,557 LOC, 16 commits, last commit 2026-07-12,
    28/28 tests pass in 11s, single contributor.
  - **Not installable.** `pip show keystone-framework` -> not found. Charon VENDORS 5 of 9 gates
    into `tools/_vendor/ksf_gates/` with rewritten imports. Audit verdict: *"KSF is not consumed —
    it's forked per-repo."*
  - **`gate_runner.py:22` hardcodes `ksf/gates/`** so it finds ZERO charon gates; the real
    mechanism runs through a separate adapter (`tools/check_coverage_ssot.py`) that bypasses
    gate_runner entirely.
  - **`inert_code` performance hypothesis REFUTED.** It runs in 0.066s (keystone) and 4.464s
    (charon, 31K LOC). It is unregistered because of NOISE: **200+ false positives**, because
    `_resolve_call()` at `inert_code.py:269` is best-effort and cannot trace re-exports.
  - **KSF has never gated anything in CI.** The keystone GitHub Actions workflow runs `pytest`
    only, never `ksf gate`.
  - Zero cross-repo visibility: isolated `.ksf/keystone.db` per repo, no federation.
  - Prune candidates: `leak_guard` (too broad — RFC1918/home paths; gitleaks' job, not structural),
    `wiring_alignment` (too narrow — string-matches `import <module>` in tests/; imported != tested).

  ## FRAMING (hypothesis — TEST IT, overturn loudly if wrong)
  The manager believes these four fixes are the whole gap between "gates only itself" and "can gate
  three repos", and that they are individually small. **Unverified.** The resolver-precision fix in
  particular may be hard: tracing re-exports correctly is the difference between 200 false
  positives and a usable gate, and if it cannot be made precise the honest answer may be that
  `inert_code` should be scoped down (e.g. opt-in per-directory) rather than fixed. Say so if that
  is what you find.

  ## WHAT TO DO
  1. **Make KSF installable** — a real package charon/rig/SLOP depend on, replacing the vendored
     fork. One implementation, N consumers. The vendor header's objection (a local-path dependency
     on a sibling checkout "would break") is a real constraint — solve it properly.
  2. **Fix `gate_runner`'s hardcoded `ksf/gates/` path** so a consumer's gates are actually found,
     and retire the bypass adapter if it becomes redundant.
  3. **Fix `inert_code` resolver precision** (or scope it down — see FRAMING). Success criterion is
     empirical: run it against charon and report the false-positive count. **It must flag
     `src/charon/litellm_plane/` (imported ONLY by tests) and must NOT drown that signal in noise.**
     That single case is the benchmark — it is the largest inert subsystem we own and the gate
     currently misses it entirely.
  4. **Make KSF gate ITSELF in CI** — `ksf gate` in keystone's own workflow, not just `pytest`.
     A gate framework whose gates never run in CI is the defect it exists to catch.
  5. **Adopt the class register.** Land `/tmp/ksfaudit/KSF-CLASS-CORPUS.md` as
     `fleet/state/KSF-CLASS-REGISTER.md`: 15 deduplicated classes from 30+ incidents, ranked by
     frequency x blast radius, with 10 classes hit 3+ times and NO gate. This is the requirements
     spec for any framework we converge on, and it OUTLIVES the KSF question.

  ## EXPLICITLY OUT OF SCOPE
  - Do NOT converge SG/rig/SLOP onto KSF. That is re-decided after this lands.
  - Do NOT add new gates for the 10 uncovered classes. Register them in the class file; building
    them is separate, sequenced work.
  - Do NOT prune `leak_guard`/`wiring_alignment` in this ticket — propose it, with evidence.

  ## DONE CONTRACT
  - Installable KSF proven by a consumer importing it WITHOUT a vendored copy — paste the import
    and the version.
  - `gate_runner` finds a consumer repo's gates — paste the run.
  - `inert_code` against charon: before/after false-positive counts, and `litellm_plane` present in
    the after-list. Red-proof the resolver fix against an externally-specified break.
  - `ksf gate` running in keystone CI — paste the workflow diff and a green run.
  - `fleet/state/KSF-CLASS-REGISTER.md` landed.

D&S — Deps & Sequence:
  - Depends on: nothing. The audit is done; both reports exist.
  - Blocks: any future convergence decision (formerly FRAMEWORK-CONVERGE), and the 10 uncovered
    classes, which cannot be gated by a framework that does not run.
  - Sequence: land BEFORE re-opening the convergence question.
