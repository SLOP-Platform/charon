repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: money-path
branch: feat/gateway-park-drained-provider
depends_on:
owns: fleet/gateway-park.sh, fleet/tests/gateway-park.test.sh, fleet/state/GATEWAY-PARK-API.md
serial_justified: |
  One control action against one live gateway. Two lanes issuing park/unpark concurrently against
  the same provider set would race on the very state they are trying to establish.
substrate: N/A
substrate-novel: |
  The park MECHANISM already exists in the product and must NOT be rebuilt — `BalanceTracker`
  implements `park()` / `unpark()` / `is_parked()` / `parked_providers()` at
  `/home/stack/code/charon/src/charon/balance.py:407-427`, and the gateway exposes console writes
  at `/charon/enable`, `/charon/disable`, `/charon/remove` plus `/charon/balance` (labelled
  "DRAIN-AND-PARK re-arm") — see `proxy_server.py:86-92`. The novel slice is a THIN, SAFE rig-side
  CLI over that existing API plus the written contract for it, because today no rig script can
  park a provider and the manager had to reverse-engineer the endpoints live.
execution: |
  Off-Claude, SG tab. Use BARE model ids only — never a provider-pinned id.
source: |
  Operator, 2026-08-02 - work was failing on "Insufficient balance" from the opencode workspace,
  and the operator's standing rule is "DO NOT PIN ANYTHING, the Broker doesn't need anything
  pinned." The correct response to a drained provider is to PARK IT AT THE BROKER, never to pin
  callers at a different one.
note: |
  ## THE OPERATIONAL NEED, right now
  The opencode workspace (`wrk_01KQ0MFF0B3V4W21EXPR8D7V4X`) is OUT OF CREDIT. ONE balance backs
  BOTH `opencode-zen` and `opencode-go`. MEASURED 2026-08-02:
    - SG worker sessions created with 0 tokens / 0 cost — never executed.
    - bare `deepseek-v4-flash` (a 7-leg pool) still routed to the opencode leg and failed with
      "only available hosted in China and requires explicit opt in".
    - `/charon/status` shows `opencode-go: served 5833, failed 0, errors 105, last_status 200` —
      so the gateway does NOT consider it unhealthy, and keeps offering it.
  A drained provider that the broker still offers is indistinguishable, from the caller's side,
  from a broken model. **Parking it is the fix; pinning the caller is the anti-fix.**

  ## WHAT TO BUILD — a thin CLI, not a new mechanism
  `fleet/gateway-park.sh {park|unpark|status} <provider> [...]`
    - AUTH: derive the token correctly. **This is the trap that cost a session today** —
      `source fleet/env-registry.sh` does NOT export the value; `$CHARON_GATEWAY_TOKEN` keeps the
      shell's STALE value (same 32-char length, different content). The ONE correct form is:
        `TOK="$(bash -c 'source fleet/env-registry.sh >/dev/null 2>&1; bearer_token')"`
      (`bearer_token()` at `fleet/env-registry.sh:57`). Header is `Authorization: Bearer <t>`
      (`proxy_server.py:244-246`).
    - ALWAYS assert `%{http_code}`. Unauthenticated AND stale-token requests BOTH return
      **302 with a zero-byte body and curl exits 0** — byte-identical to each other and
      indistinguishable from success. Tracked as AUTH-302-SILENT-FAILURE; until that lands, the
      client MUST assert the status code or it will silently believe it parked something.
    - `status` prints, per provider - parked? drained? balance? last_status? served/errors.
    - `park` / `unpark` are IDEMPOTENT and print the BEFORE and AFTER state. A park that reports
      success without a verified state change is exactly the failure class this rig keeps hitting.

  ## FIRST, WRITE DOWN THE API — that is half the value
  No rig doc records how to park a provider; the manager had to read product source live and
  still did not finish. Produce `fleet/state/GATEWAY-PARK-API.md` - the endpoints, their exact
  payloads, the auth form, which are reads vs writes, the CSRF constraints on console writes
  (`console_router.py:141-164` refuses cross-origin and cross-site writes and caps body size),
  and whether a park survives a gateway restart. **Answer the restart question explicitly** —
  a park that evaporates on restart is a very different tool from one that persists.

  ## THEN DO THE OPERATIONAL ACTION
  Park `opencode-zen` and `opencode-go`. Verify with `status` that the broker stops offering them,
  then prove a bare `deepseek-v4-flash` request succeeds via a non-opencode leg. Record the
  before/after. Leave a clear UNPARK command for when the operator tops the workspace up.
accept: |
  a. `fleet/state/GATEWAY-PARK-API.md` documents the endpoints, payloads, auth, CSRF constraints
     and restart-persistence, every claim cited to a product file:line.
  b. `fleet/gateway-park.sh` implements park/unpark/status, idempotent, printing before/after.
  c. Every gateway call asserts `%{http_code}`; a 302 or non-200 is a hard failure with a
     DISTINCT message and exit code. Prove it by running against a deliberately WRONG token and
     showing the script FAILS LOUD rather than reporting success.
  d. RED-PROOF - park a provider, assert `status` shows it parked and the broker stops offering
     it; unpark, assert it returns. Each direction SEEN to work, not assumed.
  e. LIVE RESULT - opencode-zen and opencode-go parked, and a bare `deepseek-v4-flash` request
     succeeds through a non-opencode leg. Record the exact before/after from `/charon/status`.
  f. The UNPARK command is written down for the operator, verbatim and copy-pasteable.
scope: |
  A rig-side CLI over the EXISTING gateway park API, its contract doc, and the one operational
  park. Does NOT change product code, does NOT alter tier chains, and does NOT pin any caller to
  a provider. The automatic drain-detect/re-arm LOGIC is PARK-REARM-FUNDED-PROVIDER's scope
  (owns `src/charon/proxy.py`) and is currently CLAIMED — do not touch those files.

## Dependencies & Sequence

- **depends_on: none.** The park mechanism and endpoints already exist.
- DISJOINT from `PARK-REARM-FUNDED-PROVIDER` (live claim, owns `src/charon/proxy.py`): that
  ticket automates WHEN to park; this one gives the rig the ability to park AT ALL, by hand,
  today. Neither blocks the other.
- Pairs with `AUTH-302-SILENT-FAILURE` — until that lands, every client here must assert the
  status code by hand. Do not wait for it; assert.
