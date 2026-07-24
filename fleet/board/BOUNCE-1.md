repo: charon-private
tier: frontier
difficulty: 4
priority: 0
work_class: tests
branch: feat/bounce-1-egress-canary-realsut
owns: fleet/checks/egress-key-canary.sh, fleet/tests/egress-key-canary.test.sh
depends_on:
source: EGRESS-KEY-CANARY REJECTED (2026-07-24) — false assurance: the delivered canary used a
  HERMETIC model decoupled from real src/charon, so it could not exercise the actual header-forwarding
  exfil path. Re-briefed as BOUNCE-1 with a REAL-SUT mandate. Original ticket archived.
note: |
  REBUILD of the egress-key canary — the prior attempt was REJECTED for FALSE ASSURANCE (a hermetic
  stdlib fake decoupled from src/charon: it "passed" without ever running the real key-send code, so it
  proved nothing). The exfil lives IN the real header-forwarding path (src/charon), so a fake gateway
  CANNOT stand in for it. This rebuild MUST drive a REAL system-under-test.
  Context: the live exfil vector is now CLOSED on master (#181 egress allowlist + d944a26;
  gateway.py assert_base_allowed rejects a provider pointed at a non-preset base) — so this canary is
  the STANDING REGRESSION GUARD proving that stays closed, exercised against the real code, not a mock.
  [[security-is-a-ratchet-gate]] [[e2e-dogfood-norm-for-money-code]]
accept: |
  - fleet/checks/egress-key-canary.sh: stands up a REAL SUT — the actual src/charon gateway running in
    a Testcontainers-fronted container (NOT a stdlib fake / not a decoupled model) — plus a local sink
    that records the Authorization header it receives.
  - Drives the two-request exfil sequence against the REAL gateway:
    POST /charon/providers {name:evil, base_url:http://<sink>/v1, key_env:VICTIM_KEY, key:sk-throwaway}
    then POST /charon/models/import {provider:evil}; asserts the REAL VICTIM_KEY value NEVER reaches the
    sink (only the throwaway, or the request is refused 400/401 by the allowlist) = pass.
  - fail-on-revert (fleet/tests/egress-key-canary.test.sh): (a) against real fixed master -> GREEN
    (allowlist blocks it); (b) simulate reverting the #181 allowlist guard on the real SUT -> RED (key
    reaches sink) — proving the canary actually detects a live leak and is not a tautology; (c) restore
    -> GREEN. The RED case MUST come from the real send path, never a mocked internal.
  - NO hermetic/decoupled model anywhere in the assertion path (the exact rejection cause). If a fake is
    used for setup, the KEY-HANDLING assertion must still run through real src/charon code.
  - bash fleet/validate_board.sh GREEN. ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) —
    security/key-exfil canary; a false-GREEN re-rejects.
scope: |
  The canary + its real-SUT fault-seed proof only. Does NOT modify src/charon key handling. Rebuild of
  the rejected EGRESS-KEY-CANARY; same owned paths, real-SUT this time.
ds: |
  ## Dependencies & sequence
  P0. No prereq (PLANE-CANARY-REGISTRY already landed). Disjoint owns — parallelizable. The rejection
  taught the class lesson: a canary that cannot exercise the real vulnerable path is false assurance.
