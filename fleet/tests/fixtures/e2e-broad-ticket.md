tier: frontier
difficulty: 4
work_class: money-path
branch: feat/e2e-fixture-broad
repo: charon
depends_on:
owns: src/charon/_e2e_fixture_gateway_wire.py, src/charon/_e2e_fixture_balance_decrement.py
accept: |
  FIXTURE ONLY (fleet/tests/fixtures/, not a real board ticket) — feeds fleet/decompose.sh
  in fleet/tests/test_decompose_e2e.sh (DEC-E2E). R46-shaped broad ticket: construct a
  BalanceTracker inside a gateway build_server from the provider config (the "config
  module" piece — GatewayConfig-style object) and wire it into a balance decrement path
  so record_spend actually decrements, modeled on fleet/board/R46-BALANCE-WIRE.md. Crosses
  2 modules — exactly the god-ticket shape the decomposer must split into single-domain,
  dependency-chained sub-tickets:
    - one sub-ticket owns ONLY the decrement-path module (foundational, no deps)
    - one sub-ticket owns ONLY the build_server/config-wiring module (depends_on the
      decrement-path sub-ticket, since it constructs the object the wiring passes in)
  Uses dedicated non-existent fixture paths (_e2e_fixture_*) rather than the real
  gateway.py/balance.py so this fixture can be emitted into the live board transiently
  by the test without colliding with real in-flight tickets that currently own those
  real files (GRACEFUL-DEGRADE, PRICING-LIMITS-CHECKER, PROVIDER-PROBE-FIX,
  R46-BALANCE-WIRE) — same convention as fleet/tests/test_dec_driver.sh's
  decdrv-fixture-alpha/beta files.
scope: |
  DEC-E2E fixture ticket. Not built, not landed, never executed as work — only ever read
  by fleet/decompose.sh via TICKET_FILE in the self-test.
note: DEC-E2E fixture (fleet/tests/test_decompose_e2e.sh). Not a board ticket.
