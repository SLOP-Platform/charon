tier: frontier
difficulty: 4  # auto-seeded from tier (D1 hybrid)
work_class: money-path
branch: feat/r46-balance-wire
parked: true
depends_on: F29-REGISTRY-SLICE
real-dep: F29-REGISTRY-SLICE build — R46 constructs the BalanceTracker inside gateway.py build_server, which
  is EXACTLY the module-wiring F29-REGISTRY-SLICE rewrites (build_server + GatewayConfig module fields →
  MODULE_SPECS/modules dict). F29 MONOPOLIZES gateway.py + proxy_server.py for its wave; R46 must land after it
  so the BalanceTracker is registered through the new declarative module registry, not a hand-added kwarg the
  refactor then has to reconcile. Genuine shared-god-file build prereq, not merge-order.
owns: src/charon/gateway.py, src/charon/balance.py, tests/test_balance_wire.py
accept: |
  Roadmap R46 balance-wire — CONSTRUCT BalanceTracker from the gateway provider config so record_spend stops
  being a no-op (un-deads R4). VERIFIED CURRENT STATE (2026-07-12, do NOT re-research — file:line):
    - record_spend is ALREADY WIRED and live: forwarder.py:466-467 and :560-561 call
      srv.balance_tracker.record_spend(route.label, cost, model=requested) per response; proxy_response.py:38
      passes the upstream OpenAI `usage` block through (cost derived from it).
    - balance.py ALREADY builds _fixed_balances from any provider cfg with {"mode":"fixed","starting_usd":X}
      (balance.py:177-182) and decrements it in record_spend (balance.py:236-246).
    - THE ONLY MISSING LINK: gateway.py never CONSTRUCTS a BalanceTracker from real config —
      GatewayConfig.balance_tracker defaults None (gateway.py:94) and build_server merely passes cfg.balance_tracker
      through (gateway.py:329). So srv.balance_tracker is None in production and the whole decrement path is inert
      (memory: charon-meter-inert). This ticket builds it in build_server FROM the provider config and injects it.
  DO: in build_server, assemble a BalanceTracker from the gateway's provider config (each provider carrying
    {"mode":"fixed","starting_usd":<seed>} → a tracked decrementing balance; "mode":"poll" providers keep their
    existing poll adapters) and pass it to GatewayProxyServer so srv.balance_tracker is non-None in production.
  FAIL-ON-REVERT (add tests/test_balance_wire.py): given a gateway config with a mode:fixed provider seeded
    starting_usd=X, build_server yields a server whose balance_tracker.remaining(provider) == X, and after a
    forwarded response carrying usage cost c, remaining(provider) == X - c. Revert the build_server construction
    → srv.balance_tracker is None and remaining() is unreadable → test RED.
  GREEN-IS-NOT-PROOF: the existing balance/gateway suites all pass with balance_tracker=None (they exercise the
    INERT path), so their green proves NOTHING about wiring — REQUIRE (1) the new test above asserting a NON-None
    tracker built FROM CONFIG with a live decrement, and (2) a reviewer confirming build_server reads the real
    provider config (not a hardcoded/test-only tracker) and that the F29 module registry is the construction site.
  NO POLL ADAPTER FOR OPENCODE (confirmed, OPENCODE-GO-USAGE.md §1): OpenCode Zen has NO account/usage/balance
    endpoint on either /zen or /zen/go base (feature-request anomalyco/opencode#10448 still open) — opencode-zen /
    opencode-go are CONFIG-ONLY mode:fixed, byte-for-byte the same mechanism NeuralWatt spend-tracking uses; add
    NO bespoke adapter. Modeled balance is ADVISORY/observability only; it drifts from the provider's true balance
    (unreadable) — the AUTHORITATIVE exhaustion signal stays the reactive 401/429 (see DRAIN-THEN-PARK trigger).
scope: |
  Roadmap R46 (Router Wave 3a — foundation & balance), previously "designed" with no board file — this activates
  it as a staged ticket. This is need (B) "modeled balance seed" from the 2026-07-12 exhaustion-signal reconcile
  (fleet/state/EXHAUSTION-PARK-TICKETS.md). It ships the CONSTRUCTION MECHANISM only; the starting_usd VALUES are
  operator input (see ds). [[charon-meter-inert]] [[charon-drain-then-park-provider-class]] [[charon-work-engine-vision]]
ds: |
  ## Dependencies & sequence
  depends_on: F29-REGISTRY-SLICE (real-dep above — shared gateway.py build_server; F29 monopolizes gateway.py).
  Serial chain on the shared god-files: F29-REGISTRY-SLICE → R46-BALANCE-WIRE → DRAIN-THEN-PARK(R11)/GRACEFUL-DEGRADE(R16).
  concurrency: co-owns gateway.py with F29-REGISTRY-SLICE (sequenced behind it) and balance.py with R11/R16
    (sequence R46 before them — R46 wires the tracker their advisory-balance path reads). NOT parallel-safe with
    any gateway.py / balance.py owner. Disjoint from F29-CONFIG-PKG / F29-PROVIDERS-DATA (they can run concurrently).
  OPERATOR INPUT (param, NOT a hardcoded repo value): the starting_usd seed per provider = the operator's CURRENT
    remaining credit/quota, supplied at deploy and applied in the LIVE gateway provider config on the .60 box
    (deploy-drifted from repo — memory charon-deploy-drift-lessons). The ticket parameterizes the seed; the numbers
    are operator-provided (opencode-zen prepaid $?, neuralwatt overage $?, etc.). PARKED — un-park after F29-REGISTRY-SLICE lands.
note: PARKED — staged behind F29-REGISTRY-SLICE. Un-park + author at activation. Filed 2026-07-12 (exhaustion-signal reconcile).
