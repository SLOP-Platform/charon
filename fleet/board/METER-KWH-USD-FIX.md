repo: charon
tier: strong
difficulty: 2
work_class: money-path
branch: feat/meter-kwh-usd-fix
owns: src/charon/gateway.py, tests/test_gateway_kwh_conversion.py
depends_on: GATEWAY-NONTOKEN-METERING, FT-WIRE-QUOTA
real-dep: GATEWAY-NONTOKEN-METERING (PR #155, open) owns gateway.py and INTRODUCES the exact bug
  this ticket fixes — this must land as a follow-up AFTER #155 merges, not concurrently. FT-WIRE-
  QUOTA also owns gateway.py (already sequenced behind GATEWAY-NONTOKEN-METERING); this ticket
  must sequence behind both to avoid a 3-way concurrent-writer collision on the same file.
dep-kind: build
work_class_note: MONEY bug — mis-meters non-dollar units as dollars. Note prominently; adversarial
  review before land.
note: |
  OBSERVED 2026-07-15: PR #155 (GATEWAY-NONTOKEN-METERING, branch feat/gateway-nontoken-metering,
  currently OPEN) adds ``_extract_non_token_cost`` / ``_NON_TOKEN_COST_FIELDS`` in gateway.py to
  parse non-token billing (NeuralWatt bills by energy kWh/request, not tokens). The field list
  is ``("total_cost", "energy_cost", "energy_kwh", "total_cost_usd")`` and the extractor does:
  ``fval = float(val); if fval > 0: return fval`` for WHATEVER field matched — including
  ``energy_kwh``. This books the raw kWh NUMBER directly as ``cost_usd`` with NO $/kWh
  conversion: a response reporting ``energy_kwh: 0.4`` (a plausible per-request energy figure)
  is recorded as a $0.40 cost, not converted through NeuralWatt's actual energy rate. Every OTHER
  field in the list (``total_cost``, ``energy_cost``, ``total_cost_usd``) is already
  dollar-denominated, so only ``energy_kwh`` is wrong — but it is silently wrong (no error, just
  a mis-metered ledger entry), same failure shape as [charon-meter-inert].
accept: |
  ``energy_kwh`` is no longer treated as a dollar amount. Either (a) convert it through a
  CONFIGURED $/kWh rate (e.g. a ``NEURALWATT_KWH_RATE`` / provider-pricing config entry) before
  returning it as ``cost_usd``, recording the source unit + rate used, or (b) if no rate is
  configured/available, DROP ``energy_kwh`` from ``_NON_TOKEN_COST_FIELDS`` entirely (never book
  an unconverted energy figure as a dollar cost) and track it separately (e.g. a raw
  ``energy_kwh`` field on the observation) until a real rate exists.
  FAIL-ON-REVERT (new tests/test_gateway_kwh_conversion.py): a fixture response carrying only
  ``energy_kwh: 0.4`` (no dollar field) with a configured rate of e.g. $0.10/kWh -> the meter
  records $0.04, NOT $0.40. Revert the conversion (or re-add the raw pass-through) -> the test
  asserts the wrong ($0.40) value and fails.
scope: |
  Money-path correctness fix on the metering path GATEWAY-NONTOKEN-METERING introduces. Blast
  radius: every NeuralWatt (or future kWh-billed provider) cost record in the ledger. Adversarial
  review required (money-adjacent).
ds: Sequence AFTER GATEWAY-NONTOKEN-METERING (#155) merges and AFTER FT-WIRE-QUOTA (both own
  gateway.py). Not launch-blocking otherwise — file now so it isn't lost once #155 lands.
