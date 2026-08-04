repo: charon
tier: strong
priority: 1
difficulty: 3
work_class: money-path
branch: fix/parked-pool-503-v2
owns: src/charon/forwarder.py, tests/test_gateway_outcome.py
depends_on:
dep-kind: |
  DEPENDENCY DROPPED 2026-08-04 after adversarial review. This ticket was sequenced behind
  FORWARDER-COST-ORDER-FALLBACK on the assumption that both had to touch the same
  provider-ordering region. The review proved that commit (be71807) must NOT land, so the
  dependency is void and the 503 work stands alone on origin/master.
  WHY be71807 IS HELD (two independent, executed proofs — see the CHARON-PRICE-FEED blocker):
    1. It is a NO-OP against the live gateway. derived_cost_rank deliberately ignores the
       hand-typed cost_rank field (ADR-0016 step 6) and derives from cost_input/cost_output. Live
       /data/models.json on 4-LOM: 861 models, 10 with cost_input, 214 with the deprecated
       cost_rank, and NO deepseek-v4-flash leg priced. Every paid leg therefore derives rank 1000,
       ties, and the stable sort returns the chain unchanged. A probe on the live leg shape gave
       nv, or, ds, ng, cline — openrouter still ahead of deepseek, the 2026-08-01 incident order —
       and the identical probe against origin/master was byte-identical. Its review-log claimed
       the opposite.
    2. It is an active REGRESSION: the empty-meter sort clobbers order_chain_by_funding_class
       (forwarder.py:438), silently overriding the operator's drain-then-park directive. 12 of 16
       live providers are classified, so this is live. Probe served payg on the branch and prepaid
       on master.
  BRANCH RENAMED to fix/parked-pool-503-v2: origin/fix/parked-pool-503 still carries the two
  discarded commits and force-push is denied here, so the reworked single commit takes a fresh
  name per the friction list.
serial_justified: |
  The two owned surfaces are one behaviour change and its red-proof, not two
  independent workstreams. D-012 REQUIRES them in the SAME change — the existing test asserts the
  200 being removed, so splitting them lands either a forwarder change with a green test that
  contradicts it, or a test that fails against unchanged code. Splitting is the failure mode the
  decision explicitly names.
work_class_note: money-path — this is the code path that decides whether a request is billed
  upstream. Today a fully-parked pool serves a normal 200, which is how money leaks while every
  dashboard reads healthy.
note: |
  OPERATOR DECISION D-012 (fleet/state/DECISIONS.md, 2026-08-04), verbatim:
    "I don't want a situation where EVERYONE is parked but I understand it may be needed for some
     reason. CHange it to 503 don't allow it to leak."

  TODAY'S BEHAVIOUR: src/charon/forwarder.py:481-487 restores the FULL chain — parked legs
  INCLUDED — when every leg of a pool is parked, and serves a normal 200. Measured 2026-08-03:
  `kimi-k2.6` (5/5 legs parked) and `minimax-m2.5` (2/2 parked) both served 200 via openrouter.
  Parking is supposed to STOP spend; the never-strand fallback silently undoes it.

  REQUIRED BEHAVIOUR — all four, so the failure is DIAGNOSABLE and not merely loud. The operator
  explicitly accepted that some requests will now fail:
    1. terminal 503. Never a success-shaped body.
    2. the envelope NAMES EVERY LEG with its real per-leg status and a non-empty reason. Reuse the
       existing `all_providers_exhausted` shape, which already does exactly this — do not invent a
       second error shape.
    3. it must be DISTINGUISHABLE from "all legs were tried and failed". The reason here is
       "every leg is parked", which is an operator/config state, not an upstream failure.
    4. `X-Charon-*` headers must report the truth: attempts = 0 upstream calls made.

  ⛔ THE TEST MUST BE INVERTED IN THE SAME CHANGE ⛔
  tests/test_gateway_outcome.py::test_all_legs_parked_still_serves_a_real_200_and_never_strands
  currently ASSERTS THE 200, i.e. it cements the behaviour being removed. Invert it to assert the
  503 + the named-legs envelope + attempts=0, rename it accordingly, and keep a RED-PROOF. D-012
  says it plainly: a good test locking in a bad decision is exactly why that note exists. Landing
  the forwarder change while leaving the old assertion green is a FAILED delivery.

  DO NOT REGRESS THE NEVER-STRAND GUARANTEE for the case it was actually written for: a pool with
  at least one UNPARKED leg must still behave exactly as it does today. The change is scoped to
  the all-legs-parked case only.

  ACCEPTANCE: (a) all-legs-parked returns 503 with every leg named and reason "every leg is
  parked"; (b) attempts=0 in the X-Charon-* headers; (c) the parked reason is distinguishable from
  upstream-exhaustion in the envelope; (d) at-least-one-unparked still serves as before; (e) each
  new assertion carries a red-proof — revert the forwarder change and the test must go RED.
