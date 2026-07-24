repo: charon
tier: strong
difficulty: 1
work_class: bugfix
priority: 2
branch: fix/litellm-cost-field
depends_on:
owns: src/charon/litellm_plane/metering.py, tests/test_litellm_cost_field.py
depends_on: GW-BRIDGE-2-METERING-SPEND
accept: |
  Fast-follow from the GW-BRIDGE-2 (#187) adversarial review: `litellm_cost()` reads `usage.cost`, but a
  real litellm `ModelResponse` carries per-request cost in `_hidden_params["response_cost"]`, not
  `usage.cost` — so against live litellm it reads 0.0 and the verify-only divergence cross-check is
  effectively blind. It CANNOT corrupt billing (the callback is non-authoritative by construction), so this
  is signal-quality only. Fix: read `_hidden_params["response_cost"]` (fall back to usage.cost), + a test
  that a ModelResponse-shaped object with response_cost yields a non-zero cross-check cost. Fail-on-revert.
scope: |
  Fix the litellm cost-extraction field so the verify-only divergence cross-check reads real per-request
  cost instead of 0.0. Signal-quality follow-up to GW-BRIDGE-2 (non-blocking; verify-only).
ds: |
  ## Dependencies & sequence
  - depends_on: GW-BRIDGE-2 merged (#187, done). owns metering.py (now free — GW-BRIDGE-2 landed).
