repo: charon
tier: strong
difficulty: 5
work_class: money-path
branch: feat/gateway-litellm-adopt
parked: true
note: |
  DRAFT — operator-APPROVED direction (2026-07-21), staged not-yet-live. `parked: true` so no droid
  auto-claims it. This is the FIRST leg of the operator-approved gateway MVP: adopt LiteLLM for the
  commodity plane FIRST (sequence B), THEN build the outcome-grade overlay (GATEWAY-GRADE-ORDER-MVP).
  Basis: scratchpad/GATEWAY-MVP-ADOPT-VS-BUILD.md deep-dive + docs/adr/0017-outcome-graded-gateway.md
  + MANAGER-OPERATING-RULES.md §0 (adopt-substrate-first; the stdlib-only/AP-1 basis is REMOVED).
  UN-PARK is BLOCKED on sequencing against LIVE work: FT-WIRE-QUOTA currently owns src/charon/forwarder.py
  + src/charon/gateway.py (live) and CG-LAN-OPEN-UI owns proxy_server.py + gateway.py — un-parking this
  now would owns-collide. Land FT-WIRE-QUOTA (or fold its free-tier gate into this adopt) before making
  this live. Supersedes the hand-rolled money-path assumption in the parked WIRE-BRAIN-INTO-GATEWAY draft.
depends_on:
owns: src/charon/proxy_server.py, src/charon/forwarder.py, src/charon/litellm_router.py, tests/test_litellm_router.py
serial_justified: |
  The money-path is ONE seam, not independent legs: proxy_server.py is the hand-rolled http.server
  request loop (proxy_server.py:20,207,454), forwarder.py is the hand-rolled failover/cooldown/order
  path, and litellm_router.py is the single wrapper that replaces both by delegating to litellm.Router.
  Splitting them recreates a build-against-a-half-swapped-money-path defect (the classic partial-wire
  hazard). test_litellm_router.py is the fail-on-revert proof for that one seam. Touch-a-file-ONCE
  [[optimize-execution-wallclock-tokens]].
accept: |
  WHAT THIS ADOPTS: replace the hand-rolled stdlib money-path with an imported `litellm.Router`
  (LIBRARY only — no proxy/FastAPI/Prisma/uvicorn stack), covering: OpenAI-compatible request
  forwarding, provider failover, cooldown/retry/allowed_fails, cost metering, and mechanical pool
  ordering. Deletes ~650-750 LOC of hand-rolled money-path (ADR-0017 grades this PROVEN — spike PASS).

  GROUND TRUTH (confirmed against the live product tree — do NOT re-litigate):
    - EVAL-REGISTRY row (2026-07-21) flips the prior UNRESOLVED LiteLLM-Router verdict to ADOPT: the
      non-decision rested on the stdlib-only/AP-1 basis REMOVED by MANAGER-OPERATING-RULES §0, plus an
      AP-5/AP-7 "port it natively in ~N lines" alternative that now carries NEGATIVE weight.
    - litellm.Router imports as a library alone (MIT, no fastapi/prisma/uvicorn required for the Router).
    - The pricing DATA source (model_prices_and_context_window.json) is already git-vendored + adopted
      (PR #97) — this ticket adopts the ROUTER, reusing that data source, not re-vendoring it.

  PRESERVE (non-negotiable — the external contract must not change):
    - The gateway's OpenAI-compatible external interface (endpoints, request/response shape) is
      BYTE-COMPATIBLE for clients — this is a client-agnostic OpenAI endpoint [[gateway-client-agnostic]].
    - The existing config/providers surface (providers.json, add_provider path, chain/pool config) keeps
      working — litellm.Router is configured FROM the existing config, not a parallel one.
    - SG NEVER routes through Anthropic [[sg-never-anthropic]] — the adopted Router's model list is
      derived from the existing roster and must preserve that guard.

  ACCEPTANCE TESTS (observable, fail-on-revert — ALL go RED when the adopt is reverted):
    (1) OPENAI-CONTRACT PRESERVED: a fixture OpenAI request through the litellm.Router path returns the
        same external response SHAPE as the pre-adopt path (assert the wire contract, not internals).
        Revert to the hand-rolled path -> the test still passes ONLY if the contract is identical -> the
        proof is that the Router path is exercised (assert litellm.Router is the code path taken).
    (2) FAILOVER PRESERVED: first provider errors -> request fails over to the next chain leg via the
        Router's cooldown/allowed_fails, same as the hand-rolled failover.py did. Revert -> RED.
    (3) MECHANICAL ORDERING PRESERVED: the configured cheapest-capable chain order is honored by the
        Router's ordering. Revert -> RED.
    (4) LOC DELETED: assert the hand-rolled money-path modules shrank by the promised ~650-750 LOC (the
        adopt is real, not an additive wrapper left beside dead code) — a guard against
        "wrapper-added-but-hand-roll-kept".
    (5) NEVER-ANTHROPIC GUARD SURVIVES: the Router's resolved model set contains no Anthropic leg for SG
        work. Revert the guard -> RED.

  GREEN-IS-NOT-PROOF: a test that asserts "litellm.Router was constructed" proves nothing. Test (1)'s
  external-contract byte-compat and test (4)'s LOC-delete are the minimum bar. Reviewer: confirm the
  Router is constructed ONCE (not per-request) and that the provider keys never leave the custody path
  [[security-is-a-ratchet-gate]].
scope: |
  Adopt `litellm.Router` as the gateway commodity plane (OpenAI forwarding, provider failover,
  cooldown/retry, cost metering, mechanical pool ordering), replacing the hand-rolled stdlib http.server
  money-path (proxy_server.py:20,207,454 + forwarder.py) and deleting ~650-750 LOC, while PRESERVING the
  OpenAI-compatible external interface and the existing config/providers surface. Library-only import (no
  proxy/FastAPI/Prisma stack). This is the commodity-plane adopt that UNBLOCKS the outcome-grade overlay
  (GATEWAY-GRADE-ORDER-MVP). Money path — adversarial review by default + never-strand invariant required.
  [[charon-strategy-outcome-graded-gateway]] [[adopt-substrate-build-only-novel-slice]]
  [[gateway-client-agnostic]] [[sg-never-anthropic]] [[confirm-dont-trust-documentation]]
  [[security-is-a-ratchet-gate]] [[standing-blast-radius-lens]] [[gates-must-actually-run]]
ds: |
  ## Dependencies & sequence

  depends_on: NONE. This is FIRST in the operator-approved MVP sequence — the commodity-plane adopt.
    It is the prerequisite that GATEWAY-GRADE-ORDER-MVP (the novel outcome-grade overlay) wires into.

  GATEWAY-GRADE-ORDER-MVP depends_on THIS (hard build prereq): the grade-ordering overlay hooks into
    litellm.Router's routing decision, so it must be built AFTER the Router exists — not against the
    deleted hand-rolled forwarder. Land THIS first, then the overlay becomes claimable.

  SEQUENCE RATIONALE (adopt-first, per §0): adopt the WHOLE commodity plane, build ONLY the novel ~30%
    (outcome-grade overlay + neutral grade store). Building the overlay against the hand-rolled forwarder
    first would be throwaway once the Router lands — hence adopt precedes overlay.

  UN-PARK GATE (live-collision — must be resolved before this goes live): FT-WIRE-QUOTA (LIVE) owns
    src/charon/forwarder.py + src/charon/gateway.py; CG-LAN-OPEN-UI (parked) owns proxy_server.py +
    gateway.py. Sequence or fold those before un-parking, or the board owns-collides. This is why the
    ticket ships parked despite the direction being operator-approved.

  reads-only (no owns claim): src/charon/gateway.py (external wiring + the empty CapabilityMatrix build
    at gateway.py:484 — read, coordinated with FT-WIRE-QUOTA, not owned here),
    model_prices_and_context_window.json (already-vendored pricing data the Router reuses),
    the existing providers.json / add_provider config surface (consumed, preserved).

  BLAST RADIUS: proxy_server.py + forwarder.py ARE the request hot path (money path) — every gateway
    request flows through them. A regression degrades EVERY request. REQUIRES adversarial review by
    default [[adversarial-review-default-for-droid-prs]] + the OpenAI-contract-preserved proof (accept #1)
    + never-strand. The provider-key custody path must not regress [[security-is-a-ratchet-gate]].

  wave: DRAFT — un-park after the operator sequences the FT-WIRE-QUOTA / CG-LAN-OPEN-UI collision.
    repo: charon (product). FIRST in the gateway-MVP sequence.
