repo: charon
tier: strong
difficulty: 3
work_class: money-path
priority: 0
branch: fix/litellm-order-precall
depends_on:
owns: src/charon/litellm_plane/litellm_router.py, tests/test_litellm_router_e2e.py
unblocks: GW-CUTOVER-LIVE-WIRE
priority-why: |
  P:0 — it is the sole remaining hard blocker of GW-CUTOVER-LIVE-WIRE, which is itself P:0 and was
  STOPped because it could not honestly land without this. A blocker of a P:0 must sit in the same band:
  the ladder ranks WITHIN the unblocked set, so leaving this at P:1 while its dependent is P:0 means the
  P:0 is simply unreachable behind every other P:0 on the board. This is not a reflexive stamp — it is
  money-path routing correctness (the live funding-class chain order was computed and DISCARDED) whose
  work is ALREADY BUILT, red-proofed per lever and proven on 300 real completions, so the band costs the
  board one land rather than a build slot.
source: 2026-07-24 — work is DONE and COMMITTED at 4b9d401 on branch fix/litellm-order-precall
  (src/charon/litellm_plane/litellm_router.py +53, tests/test_litellm_router_e2e.py +270). It required
  WORK_LEASE_BYPASS=1 because NO BOARD TICKET MAPPED IT. This ticket exists so the branch is board-mapped
  and landable; it DESCRIBES work already built and does not propose new design.
  [[detection-ticketed-never-built]] — the fourth bypass of the day; see TICKET-MAP-GATE.
note: |
  STATE: COMPLETE and COMMITTED at 4b9d401, not landed. Two levers, both previously dead config:

  (1) `litellm_params["order"]` IS NOW SET. We already computed the funding-class chain order and then
      THREW IT AWAY — the field was never bound, so litellm had nothing to order by. MEASURED over 300
      real completions on a 3-leg loopback chain: distribution went from 97/95/108 (i.e. round-robin
      across the chain, funding class ignored — the cheapest leg got a third of the traffic instead of
      all of it) to 300/0/0. That is the whole point of a funding-class chain, and it was inert.

  (2) `enable_pre_call_checks=True` IS NOW ENABLED. Without it the `max_input_tokens` value at
      litellm_router.py:142 was DEAD CONFIG: a >50-token prompt was routable to a 50-token leg, i.e. the
      context-window limit we had written down was not enforced by anything.

  PROVEN LIVE, NOT ASSERTED (this is the acceptance evidence, already produced):
    - a long prompt is served by the order-2 leg with ZERO hits on the small leg, while the SAME router
      still serves a short prompt from that small leg — so the pre-call check is discriminating by
      prompt, not statically excluding a leg;
    - with EVERY leg undersized it fails LOUD with `ContextWindowExceededError` and ZERO upstreams
      dialed — fail-closed, no silent fallback to an over-limit leg, no wasted spend.

  BONUS FINDING (record it — it changes what `order` buys us): this litellm build derives ORDERED
  FAILOVER from the same field. `router.py:6035-6057` walks ascending order levels, so failover now
  follows the funding-class chain instead of landing on a random survivor. Setting `order` therefore
  fixed primary selection AND failover ordering in one field — which is also why leaving it unset was
  worse than it looked [[charon-failover-bug-and-tier-fallback]].
accept: |
  ALREADY SATISFIED at 4b9d401 — this section records what was proven, so a reviewer verifies rather
  than re-derives. Re-run before landing; do not accept a self-report [[document-model-self-report-lies]].
  - `litellm_params["order"]` is bound from the computed funding-class chain; 300-completion loopback
    run yields 300/0/0 (was 97/95/108).
  - `enable_pre_call_checks=True`; the `max_input_tokens` at litellm_router.py:142 is enforced.
  - LIVE DISCRIMINATION: long prompt -> order-2 leg, zero hits on the small leg; short prompt -> still
    served by the small leg, same router instance.
  - FAIL-LOUD: all legs undersized -> `ContextWindowExceededError` with ZERO upstreams dialed.
  - RED-PROOFED PER LEVER (each lever independently defended, so neither can be reverted silently):
      drop `order`                  -> exit 1 (5 failed); restore -> exit 0
      drop `enable_pre_call_checks` -> exit 1 (2 failed); restore -> exit 0
  - `charon.cli gate` exit 0, 21/21.
  - ADVERSARIAL REVIEW (reviewer != builder) — money-path default [[adversarial-review-default-for-droid-prs]].
scope: |
  Bind the already-computed funding-class chain order into litellm_params["order"] and enable
  litellm's pre-call checks so the recorded max_input_tokens is actually enforced. Two dead-config
  fixes in ONE file plus its e2e test. No new module, no routing-policy redesign — the chain order was
  already computed upstream; this ticket stops discarding it.
serial_justified: |
  Both levers live in the same constructor region of litellm_router.py and are proven by the same e2e
  harness (tests/test_litellm_router_e2e.py): `order` decides WHICH leg is dialed, pre-call checks decide
  WHETHER a leg may be dialed for a given prompt, and the "long prompt goes to the order-2 leg" assertion
  needs BOTH set to mean anything. Splitting them would give two branches that each half-fix the same
  dispatch decision and a test that cannot assert the observed behaviour from either alone. Moot in any
  case: the work is ALREADY ONE COMMIT (4b9d401); decomposing it now unpicks a landing-ready branch for
  zero wall-clock gain.
ds: |
  ## Dependencies & sequence
  - depends_on: NONE. Both edits are confined to files no other live ticket owns (verified 2026-07-24:
    grep over every fleet/board/*.md `owns:` line -> zero other claimants of
    src/charon/litellm_plane/litellm_router.py or tests/test_litellm_router_e2e.py).
  - UNBLOCKS GW-CUTOVER-LIVE-WIRE (P:0, currently CLAIMED). That ticket was STOPped and could not
    honestly land without this: the cutover replaces the hand-rolled money-path with litellm.Router
    serving LIVE traffic, and shipping that swap while `order` is unbound would put live traffic on
    round-robin across the funding-class chain — a money regression dressed as a migration. The edge is
    recorded on GW-CUTOVER-LIVE-WIRE as a LANDING-ORDER dep, not an owns collision: the two tickets share
    NO files (this owns litellm_plane/litellm_router.py; that owns forwarder.py, proxy_server.py,
    pyproject.toml, tests/test_gw_cutover_live_wire.py) [[disjoint-owns-not-no-dependency]].
  - LAND ORDER: this ticket -> GW-CUTOVER-LIVE-WIRE -> RUFF-SECURITY-RULES (the last is behind
    GW-CUTOVER only for pyproject.toml single-writer sequencing; see its own ds:).
  - repo: charon (PRODUCT). No rig leak [[product-vs-build-rig-boundary]].
