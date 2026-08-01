repo: charon
tier: strong
priority: 2
difficulty: 3
work_class: ci-infra
branch: spike/gitea-actions-ci
parked: true
note: DRAFT — operator-approved direction (2026-07-19), sequenced AFTER the CG auth fix.
owns: (spike — throwaway; touches .gitea/workflows on a test repo + one act_runner on BB-8)
depends_on:
serial_justified: single spike, one runner + one workflow port; not decomposable.
accept: |
  GOAL (decisive spike, ~half a day): prove whether the product's CI gate runs GREEN on
  Gitea Actions, so CI can move OFF GitHub Actions (the dependency that blocked the whole
  2026-07-19 session via a GitHub Actions runner-API outage). PASS -> proceed to full
  cutover; FAIL with a specific incompatibility -> keep GitHub CI, decision made on evidence.

  WHY (see [[git-hosting-gitea-primary]]): Gitea = primary git home (staging live on
  c1-10p, product repo already migrated to stack/charon). Gitea Actions is GitHub-Actions-
  COMPATIBLE and runs on YOUR boxes via act_runner — removes GitHub cost/limits/outage
  exposure. The gate is plain ruff/mypy/pytest + shell/python (low marketplace-action
  dependence), so porting risk is low but MUST be proven, not assumed.

  DO:
  1. Install act_runner on BB-8 (10.0.1.61 — capable box, passwordless sudo, NOT co-hosting
     the gateway). Register it with the Gitea instance (http://10.0.1.52:3000). Label it so
     Gitea Actions targets it. Confirm it appears + online in Gitea admin.
  2. Port the product CI workflow (.github/workflows/ci.yml) to .gitea/workflows/ (or confirm
     Gitea reads .github/workflows directly). The gate is `python3 -m charon.cli gate`
     (ruff/mypy/pytest/public-clean/security/inert/etc) + wheel-smoke. Name every step that
     differs from GitHub Actions.
  3. Run it on a test PR / push in Gitea against stack/charon. Capture: does the FULL gate go
     green? Which steps needed changes (runner image, action versions, secrets handling,
     python setup)? Measure wall-clock (BB-8 is the i3-N305; note if slower than 4-LOM's
     GitHub runs).
  4. Prove a RED works too: a deliberately-broken commit must make the Gitea gate FAIL (a
     never-seen-to-fail gate is not a gate — [[gates-must-actually-run]]).

  DELIVERABLE / verdict: PASS (gate + wheel-smoke green on Gitea, RED proven) -> recommend
  full cutover + the migration steps (repoint the runner boxes from GitHub runners to
  act_runner; drop/minimize GitHub CI; Gitea = code+CI primary, GitHub = downstream public
  code mirror). PARTIAL/FAIL -> the exact incompatibility, and whether it's fixable or a
  reason to keep GitHub CI. Do NOT big-bang the cutover in the spike — prove, then report.

  This is a SPIKE: throwaway allowed; do not push production CI config to master; report,
  don't land.
scope: |
  CI infrastructure only. Ties off the session's biggest pain (GitHub Actions outage
  blocked everything). Pivots the half-done GitHub-runner-pool work (4-LOM/BB-8, blocked on
  GitHub's own outage) toward act_runner — the cleaner allocation. [[charon-host-inventory]]
  [[adopt-substrate-build-only-novel-slice]] (Gitea Actions = adopted, not hand-rolled CI).
ds: |
  ## Dependencies & sequence
  depends_on: land the CG auth fix first (don't split focus). Then this. Independent of the
  gateway MVP. BB-8 already has GitHub-runner dirs prepped — for Gitea, install act_runner
  instead (or alongside). repo: charon-private tracks the spike; the CI config itself is
  product (public) and must stay product-neutral.
