tier: strong
difficulty: 3
work_class: money-path
branch: feat/fail-loud-contract
repo: charon
owns: src/charon/forwarder.py, tests/test_forwarder_fail_loud.py
depends_on:
accept: |
  ADR-0016 step #5 (docs/adr/0016-demand-driven-capability-match.md, "Fail-loud contract" section + "Build
  decomposition" row 5). HARDEN the existing terminal `all_providers_exhausted` synthesis into a structured,
  legible contract so the caller sees WHICH providers were tried, WHY each failed, and WHEN each returns.
  VERIFIED CURRENT STATE (2026-07-12, do NOT re-research — file:line; the ADR's cited "forwarder.py:372-393"
  has DRIFTED to ~forwarder.py:471-497):
    - The terminal synth exists: forwarder.py:475 builds the error with `retry_after=srv.retry_after_hint(...)`
      and forwarder.py:478 sets `"type": "all_providers_exhausted"`.
    - The 4xx-vs-exhaustion distinction ALREADY exists: forwarder.py:486-497 relays a raw upstream error
      transparently (genuine 400/401-bad-key/403 = NOT retry-worthy, no synthesized Retry-After) while only
      capacity/exhaustion failures synthesize the terminal error. PRESERVE this distinction.
    - Per-provider failover reasons are tracked (X-Charon-Failover-Reasons headers already emitted).
    - THE GAP: the terminal body does NOT yet carry a structured `providers_tried` array — the operator must
      read logs to learn why each provider failed and when it re-arms.
  DO (owns forwarder.py terminal block only): extend the `all_providers_exhausted` synthesis so the OpenAI-
    compatible error envelope carries, per the ADR body schema:
      - `requested_model`, `no_provider_reason`, `retry_after_s`
      - `providers_tried`: an array of {provider, status, reason, class (funding class), rearm (re-arm
        condition)} for each capable provider that was attempted/skipped in this request.
    HTTP status: 503 (transient — chain may recover) when the chain had members but all exhausted/parked; 502
    when NO route was configured at all. Bound `Retry-After` to [1, max_cooldown_s] (soonest chain member to
    recover) — the code already computes a hint via retry_after_hint / max_cooldown_s (forwarder.py:475,490);
    reuse it, do NOT invent a new unbounded value. Retain existing headers X-Charon-Provider / -Failovers /
    -Failover-Reasons. The funding-class + re-arm strings come from the provider's cost_class / class taxonomy
    (prepaid→operator top-up, free-daily/weekly→auto reset, metered→top-up) — reuse the classification already
    used by the exhaustion taxonomy (proxy.py _is_billing_error / _EXHAUSTION_STATUSES); do NOT hand-duplicate it.
  FAIL-ON-REVERT (add tests/test_forwarder_fail_loud.py): drive a request whose entire capable chain returns
    exhaustion signals (401 CreditsError / 429 / 402 mocks). ASSERT HTTP 503, body `type:"all_providers_exhausted"`,
    a `providers_tried` array with one entry per attempted provider each carrying provider+status+reason+class+rearm,
    and a `Retry-After` within [1, max_cooldown_s]. Second invariant: a genuine 401-bad-key / 400 is RELAYED
    transparently (NOT wrapped into the synthesized envelope, NO synthesized Retry-After). Revert the structured
    array → body lacks `providers_tried` → test RED. Revert the relay distinction → the 4xx test RED.
  GREEN-IS-NOT-PROOF: the existing forwarder suite passes with the OLD flat terminal error (it only asserts the
    `type` string), so its green proves NOTHING about the structured contract — REQUIRE (1) the new test asserting
    a populated `providers_tried` with all five fields, (2) the bounded-Retry-After assertion, (3) the 4xx-relay
    distinction assertion, and (4) a reviewer confirming reasons/classes are sourced from the real per-attempt
    failover record, not fabricated placeholders.
  ADVERSARIAL REVIEW REQUIRED (money-path / terminal error surface): a misleading terminal error hides why spend
    stalled. Reviewer confirms the 4xx-relay vs exhaustion-synth distinction is intact (no silent downgrade).
scope: |
  ADR-0016 "Demand-driven capability match" step #5 — the second small NEW piece (a HARDENING, not a rewrite).
  Failures become legible: the caller sees which providers were tried, why, and when they come back, without
  reading logs. Distinct from a relayed 4xx (preserved). [[charon-silent-downgrade-leak]] [[document-model-self-report-lies]]
ds: |
  ## Dependencies & sequence
  depends_on: (none) — owns only forwarder.py's terminal synth block + its new test. No live board ticket owns
    forwarder.py (verified 2026-07-12), and F29-REGISTRY-SLICE owns gateway.py/proxy_server.py, NOT forwarder.py.
  concurrency: RUNS NOW. Parallel-safe with LIVE-PRICE-PULL (disjoint files) and with the F29/R46/gateway.py
    serial chain (no shared file). Per ADR "Collision notes": #3 (new file) and #5 (forwarder terminal) are
    disjoint from the gateway.py/balance.py chain → run concurrently.
  repo: charon (product).
note: ADR-0016 #5. Hardens the existing terminal synth (forwarder.py:471-497). READY, runs now (concurrent with
  LIVE-PRICE-PULL). Filed 2026-07-12.
