repo: charon
tier: economy
difficulty: 1
priority: 1
work_class: ci-infra
branch: feat/litellm-ci-deps
depends_on:
owns: .github/workflows/ci.yml
work_class_note: |
  Systemic CI gap: litellm was NOT installed in CI, so EVERY litellm-plane test was
  pytest.importorskip-SKIPPED — the whole commodity-plane money path (streaming SSE relay,
  park/cooldown, metering bridge) had ZERO real CI coverage. The gateway declares litellm as
  the OPTIONAL `[router]` extra in pyproject.toml (ADR-0017 adopt, commit 7e16e4a); the ci.yml
  gate installed only `.[dev,service]`, never `[router]`. [[gates-must-actually-run]]
  [[e2e-dogfood-norm-for-money-code]] [[no-stiff-single-provider-tools]]
accept: |
  Make the ci.yml `gate` job install the `[router]` extra so the litellm-plane tests RUN in CI
  instead of importorskip-skipping. Keep litellm an OPTIONAL extra (NOT a core runtime dep) — the
  commodity plane stays opt-in until GW-CUTOVER; CI just installs the extra at test time. Change is
  scoped to the install step only.
  PROVE IT: with litellm installed, the previously-gated litellm-plane tests un-skip and run —
  16 tests across test_gw_bridge3_streaming.py (7), test_litellm_router_adopt.py (1),
  test_gw_bridge2_metering.py (1), test_litellm_router_e2e.py (4, module-level importorskip),
  test_litellm_router_downgrade_guard_e2e.py (3, module-level importorskip). All 16 pass with
  litellm 1.93.0; no real failure was hidden by the skips.
