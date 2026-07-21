# ADR-0020 — LiteLLM Metering Bridge: routing cost accounting through litellm callbacks

- **Status:** Proposed / Pending (DECISION-PENDING — gates GW-BRIDGE-2-METERING-SPEND)
- **Deciders:** Nnyan (solo operator)
- **Repo:** `github.com/SLOP-Platform/charon`
- **Relates to:** ADR-0016 (vendored price data / exhaustion envelope), ADR-0017 (outcome-graded
  gateway; adopt litellm.Router, delete the hand-rolled money-path), the DEFERRED slice in
  `ADOPT-MAP.md` §"Slice boundary", and `docs/DECISIONS.md` D025 (no double-bill).

---

## Context

The gateway money-path is being cut over from the hand-rolled forwarder/`http.server` stack to
`litellm.Router` (ADR-0017), decomposed into four additive bridges + one cutover. **Bridge 2**
moves cost metering onto the Router path: instead of the hand-rolled `proxy.observe` /
`forwarder` accounting advancing `BalanceTracker`, spend is advanced by **litellm's cost
callback** (fed by the already-vendored `model_prices_and_context_window.json`, ADR-0016).

This is not a mechanical port. It **changes the SOURCE OF RECORD for money accounting** — the
authority that decides how much a request cost, and therefore when a provider drains and parks.
Handing that authority to a third-party callback is a decision that must be made deliberately,
which is why this ADR gates the bridge.

## Decision (PENDING)

**Proposed:** route per-request cost accounting through the litellm cost callback into the
existing `BalanceTracker`, making the callback the source of record for token-priced spend —
**only if** the following invariants are provably preserved. Until ratified, GW-BRIDGE-2 is not
claimable.

### Non-negotiable invariants (the bridge must prove each with a fail-on-revert test)

1. **Non-token / energy metering preserved.** Providers billed by energy or other non-token
   units must still be metered by their own rule, **not silently zeroed** by a token-cost
   callback that only understands `$/token`. The meter was inert once before
   (`charon-meter-inert`); it must not regress to token-only.
2. **Drain-then-park preserved.** Spend advanced by the callback must still drive funding-class
   drain-then-park: a provider crossing its threshold parks; it re-arms on top-up. The callback
   is a new *feed* into the same policy, not a replacement policy.
3. **D025 no-double-bill preserved.** An already-billed `200` is never discarded-and-rebilled; a
   genuine downgrade is served with `X-Charon-Downgrade`, billed exactly once. The callback must
   compose with GW-BRIDGE-1's re-hosted downgrade control so a served downgrade is counted once,
   never twice. (D025 is Settled; this bridge must not weaken it.)

### Open questions to resolve before ratifying

- Does litellm's callback fire **exactly once per billed response** (including on failover /
  retry / cooldown paths), or can it double-fire / miss? The no-double-bill invariant depends on
  the answer.
- How is a provider with **no price row** (or an energy-billed provider) surfaced by the
  callback — as `0`, as `None`, or as an error — and does Charon's own metering rule take over
  cleanly in that case?
- Is the callback's cost the **authority**, or a cross-check against Charon's own computation
  (defense-in-depth)? Source-of-record vs. verify-only is the crux of this decision.

## Consequences

**If accepted:** the Router owns token-priced spend accounting, shrinking the hand-rolled cost
path at cutover; energy/non-token metering stays Charon policy fed alongside. **If the invariants
cannot be proven:** keep Charon's own cost computation as the source of record and use the litellm
callback only as a cross-check (verify-only), or defer the metering move past the cutover.

**Gates:** `GW-BRIDGE-2-METERING-SPEND` (board) — do not claim until this ADR is **Accepted**.
