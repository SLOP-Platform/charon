repo: charon
tier: frontier
priority: 0
difficulty: 4
work_class: routing
branch: fix/gw-cutover-reopen
owns: src/charon/gateway.py, tests/test_gw_cutover_reopen.py
serial_justified: One wiring decision — either the live route points at litellm_plane or the plane is deleted; the test proves which.
substrate: |
  LiteLLM — ADOPT, and that adoption ALREADY LANDED as code; what never landed is the wiring.
  This ticket does not re-open the adopt-vs-build question (settled: LiteLLM won, the plane was
  built and merged). It closes the gap between "merged" and "firing". No new tool is introduced
  and nothing is hand-rolled — the whole point is to stop hand-rolling by actually routing through
  the adopted substrate.
substrate-retest: |
  The LiteLLM row is marked `drifted`, so it may not be cited as settled — and this ticket does not
  need it to be. The re-test IS this ticket's own work, and it is the strongest possible form:
  the plane is already BUILT and MERGED, so instead of desk-comparing LiteLLM against the
  hand-rolled ThreadingHTTPServer we route real traffic through it and measure.
  Concretely: point the live route at litellm_plane, then compare against the current hand-rolled
  path on the same requests — correctness (same responses), failover behaviour, latency, and which
  of the 52 Router kwargs become reachable (`order`, `fallbacks`, `enable_pre_call_checks` are all
  unreachable today because nothing imports the plane). Record the numbers in EVAL-REGISTRY as a
  superseding row with an honest alignment.
  If the measured result is that LiteLLM should NOT serve the gateway, that is an equally valid
  outcome — but then the plane gets DELETED and the row updated, rather than left merged, marked
  done, and unimported as it is now. Either way the drift is resolved by execution, not argument.
depends_on: GATEWAY-NONTOKEN-METERING
note: |
  REOPEN, not a new build. GW-CUTOVER-LIVE-WIRE (merged #181) and all four GW-BRIDGE-1..4 are in
  fleet/state/done/ AND fleet/board/archive/ — the cutover is recorded as COMPLETE.

  MEASURED 2026-08-01: `grep -rn litellm_plane /home/stack/code/charon/src` returns ZERO
  production importers. The only references are tools/dogfood_litellm_router.py:36 and tests.
  The gateway data plane is still the hand-rolled ThreadingHTTPServer in
  src/charon/proxy_server.py.

  So the adopt-the-substrate work was done, merged, marked done — and the live route never pointed
  at it. This is the single largest instance of the rig's dominant failure class
  (built + merged + marked done + structurally incapable of firing), and it is the one that most
  directly contradicts the ADOPT-FIRST doctrine: we carry the cost of the dependency and get none
  of the benefit, while the hand-roll it was meant to replace still serves every request.

  DECIDE AND ACT — do not leave it ambiguous:
    (a) point the live route at litellm_plane and prove it serves traffic, OR
    (b) if the plane is genuinely wrong for the gateway, DELETE it and record why in
        EVAL-REGISTRY (superseding the LiteLLM adopt row).
  What is NOT acceptable is a third session finding it merged, done, and unimported.
accept: |
  - Either: a real request through the live gateway is served via litellm_plane, proven by an
    assertion on observable effect (not a self-report), and `grep -rn litellm_plane src/` shows a
    production importer on the serving path.
  - Or: the plane is removed and EVAL-REGISTRY carries a superseding row explaining the reversal.
  - fail-on-revert test in tests/test_gw_cutover_reopen.py; red-proof externally and report both
    counts (green with the fix, RED on revert).
  - No spend cap, pool, or provider config is changed by this ticket.

## Dependencies & Sequence

- **depends_on: (none)** — the prerequisite work all landed; only the wiring is missing.
- **Sequence: high.** Every request served today bypasses the substrate we already paid for.
- **Blocks / unblocks:** unblocks the litellm Router capabilities (`order`, `fallbacks`,
  `enable_pre_call_checks`) that LITELLM-CAPABILITY-ADOPTION dispositions — all of which are
  unreachable while the plane has no importer.
- **owns-collision:** verify against live board before claiming; `src/charon/gateway.py` is
  high-traffic. Sequence behind any in-flight gateway ticket rather than co-writing.
