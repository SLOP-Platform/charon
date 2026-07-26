repo: charon
tier: strong
difficulty: 3
work_class: money-path
priority: 1
branch: fix/sw-p2-meter-observed
depends_on: GATEWAY-NONTOKEN-METERING
real-dep: GATEWAY-NONTOKEN-METERING — REAL BUILD PREREQ, not merge order. You cannot rank on observed
  spend until the meter actually RECORDS spend; that ticket owns the recording fix in gateway.py (it
  currently books $0 for non-token-billed responses). Ranking built on a meter that reports zero is
  ranking on zero. Owns are DISJOINT (that ticket owns src/charon/gateway.py; this one owns
  src/charon/balance.py) — deliberately so the two can be reviewed and landed independently.
dep-kind: build
owns: src/charon/balance.py, tests/test_observed_spend_rank.py
serial_justified: |
  One tracker plus its fail-on-revert proof. `balance.py` is where remaining/observed spend lives and is
  where the null originates; splitting the tracker fix from the test that proves ranking changed leaves
  the classic inert outcome — a field that now holds a number nobody reads.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Graded run — record into fleet/model-scorecard.tsv under work_class `money-path`. Own git worktree.
  Money-path code: the e2e + dogfood norm applies — a unit test alone is not sufficient evidence.
source: |
  Switchboard-convergence investigation, 2026-07-26 (manager session). Live meter figures read off the
  4-LOM gateway, image v0.6.0 build 289cf93 — do NOT re-derive.
note: |
  ## THE FACT
  The meter is INERT on the live gateway: **every provider reports `remaining_usd: null`**, and total
  `cost_usd` is **$0.000704 across 252M input tokens**. That number is not small, it is wrong — the
  meter is not measuring.

  ## WHY IT IS A SWITCHBOARD DEFECT, NOT A DASHBOARD DEFECT
  ADR-0011's INV-SW3 selects the **cheapest** capable available leg. With the meter inert, "cheap" is
  ranked on QUOTED prices from the catalog, never on OBSERVED spend. So:
  - a provider whose real effective cost diverges from its quote (minimum billing, cached-token pricing,
    energy billing, per-request floors) is ranked on fiction;
  - `remaining_usd: null` means the drain-then-park funding-class ordering
    (`forwarder.py:424+`, `order_chain_by_funding_class`) cannot tell a funded leg from an exhausted one,
    which is an INV-SW2 false-exhaustion vector in BOTH directions.
  This is the third leg of "cheapest-capable-with-context-and-available": availability and cost are both
  read off a meter that reports nothing.

  ## THE WORK
  - Find WHY `remaining_usd` is null for every provider — is nothing writing it, is it written and
    reset, or is the read path looking at the wrong object? State the answer with file:line and the ref
    you measured on. Do not assume; the $0.000704 says at least one write path IS alive.
  - Make observed spend accumulate per provider and survive a gateway restart (or state explicitly that
    it is intentionally in-memory and what that costs at restart).
  - Feed observed spend into cost ranking so a leg whose OBSERVED cost exceeds its quote is ranked on
    the observation. Where no observation exists yet, fall back to the quote — and make that fallback
    visible, not silent.
  - **HAZARD (already ruled on, do not re-litigate):** `routing_policy/cost_rank.py:88-89` and
    `pools.py:136` collapse an unpriced model to a fixed 1000 fallback, tie-broken by config insert
    order. That file is owned by `ADR0016-DEPLOY-PRICED-COMPLETENESS` — coordinate with it, do NOT edit
    cost_rank.py here.
accept: |
  DONE-CONTRACT (observable on the LIVE gateway, money-path — e2e + dogfood, not a unit test alone):
  - At least one funded provider reports a NON-null `remaining_usd` in `/charon/status`, and the value
    moves in the correct direction after real traffic. Publish the before/after.
  - Total `cost_usd` tracks token volume plausibly: state the new figure against the same ~252M-token
    baseline and explain any remaining gap. "$0.000704 -> some number" with no reconciliation is not done.
  - A leg whose OBSERVED cost exceeds its quoted cost is ranked BELOW a cheaper-in-practice leg —
    demonstrated on a real request, not only in a fixture.
  - `tests/test_observed_spend_rank.py`, FAIL-ON-REVERT and red-proofed by execution: observed spend
    changes the selected leg; revert the wiring -> the old (quote-only) leg is chosen -> RED. Report BOTH
    exit codes. Non-vacuous: zero providers examined is RED.
  - `charon.cli gate` GREEN + `pytest -q` GREEN from the worktree.
  - ADVERSARIAL REVIEW (reviewer != builder). Money path: a wrong meter routes spend, and an
    over-reported spend parks a funded provider (INV-SW2).

## Dependencies & sequence

- **Depends on: GATEWAY-NONTOKEN-METERING** (real build prereq — see `real-dep:`). That ticket in turn
  depends on `PROVIDER-PROBE-FIX` for gateway.py ownership; check that chain's state before claiming.
- **Wave:** wave 1, PHASE 2. Concurrent with SW-P2-CONTEXT-ADMIT, SW-P2-GRADE-PLANE-SETTLE,
  SW-ADR0016-SETTLE and (owns-disjoint) with all of PHASE 1.
- **Blocks: nothing.**
- **Concurrency safety:** `src/charon/balance.py` and `tests/test_observed_spend_rank.py` are owned by
  NO other live board ticket (verified against the full `owns:` set of `fleet/board/*.md`, 2026-07-26).
  `src/charon/gateway.py` is deliberately NOT owned here — it is contended by GATEWAY-NONTOKEN-METERING,
  WIRE-GRADING-PRIOR-LIVE and two parked tickets. If the fix genuinely requires a gateway.py edit,
  STOP and get the owns transferred rather than becoming a second writer.
- **Related, do NOT duplicate:** `GATEWAY-NONTOKEN-METERING` (energy/non-token billing shapes),
  `ADR0016-DEPLOY-PRICED-COMPLETENESS` (owns cost_rank.py), `PRICE-REFRESHER` / `PEAK-PRICING-AWARE`
  (quoted-price freshness — a different input to the same decision).
