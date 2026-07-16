# FAIL-LOUD-CONTRACT — review/decision notes

## Scope (owns)
- `src/charon/forwarder.py` (terminal synth block + new helper)
- `tests/test_forwarder_fail_loud.py` (new)

## What I did (tickets asks, observed ground truth)

ADR-0016 step #5: harden the existing terminal `all_providers_exhausted`
synthesis so the caller sees which providers were tried, why each failed,
and when each re-arms — without reading logs.

### Verified state on 2026-07-15
The ticket's line citations had drifted; I confirmed the actual ground
truth before editing:
- Terminal synth: `src/charon/forwarder.py` lines 654-664 (pre-edit) →
  654-694 (post-edit), still inside `forward_with_failover`.
- The 4xx-vs-exhaustion distinction is gated on `obs.failover`
  (line 596) and `obs.exhausted` (line 597), then `more` (line 630) and
  a non-empty `failovers` list (line 631) — three independent guards.
  A 401-bad-key has `obs.failover=False` (genuine auth, not billing),
  so it falls through to the relay branch (line 665-668) untouched.
  A 400 bad-request has `obs.failover=False` and `obs.exhausted=False`
  → same relay branch.
- 502 (no route) lives at lines 310-316, not inside the synth block.
  I extended that path with the same envelope schema so the operator
  has one shape to learn.

### Implementation
1. New helper `_classify_provider(provider, bt) -> (class, rearm)` at
   top of `forwarder.py` (after imports). Sourced from
   `balance_tracker.funding_class(provider)` — the routing-time source
   of truth, never hand-fabricated. Taxonomy mirrors `balance.py` /
   `config/providers.py` (1=free-recurring, 2=flat-sub, 3=drain-then-
   park, 4=PAYG). Unknown → `("unknown", "unknown")` so the field is
   always populated (never None).
2. 502 path: added `type`, `requested_model`, `no_provider_reason`,
   `retry_after_s` (None — permanent misconfiguration, retrying won't
   help), `providers_tried` (empty).
3. 503 path: build a `providers_tried` array by walking the existing
   `failovers` list and adding `class` + `rearm` from the helper. Body
   carries `requested_model`, `no_provider_reason` (None — chain had
   members), `retry_after_s` (mirrors the bounded `Retry-After`
   header), and `providers_tried`. `failover_reasons` legacy string
   array kept for back-compat with the X-Charon-Failover-Reasons
   header consumer.

### Reuse (not hand-duplication)
- `class`/`rearm` strings come from `balance_tracker.funding_class`,
  which is the same taxonomy used by the pre-flight drain routing at
  `forwarder.py:342-372`. No hand-fabricated placeholders.
- `retry_after_s` mirrors `srv.retry_after_hint(ordered)` — the same
  bounded hint already used for the `Retry-After` header (P1).
- `obs.note` (the proxy's classify taxonomy) is the source for the
  per-entry `reason` field.

## Tests — FAIL-ON-REVERT proof

All 6 new tests in `tests/test_forwarder_fail_loud.py`:

1. `test_all_providers_exhausted_carries_structured_per_provider_breakdown`
   — asserts `providers_tried` array of one entry per attempted
   provider, each with provider+status+reason+class+rearm (all 5
   fields, none null), class sourced from real `funding_class` config
   (drain-then-park / free-recurring strings verified).
2. `test_retry_after_within_max_cooldown` — asserts `retry_after_s` ∈
   [1, max_cooldown_s] AND that the `Retry-After` header matches the
   body field (they're the same value).
3. `test_auth_error_is_relayed_transparently_no_synthesized_envelope`
   — solo 401-bad-key → 401 status, real upstream body, NO
   `providers_tried`, NO `Retry-After` header, `X-Charon-Failovers`
   = 0. (Regression-locks the single-upstream relay path; does NOT
   lock the money-path distinction — see test #5.)
4. `test_400_bad_request_is_relayed_transparently` — same 4xx-relay
   invariant, 400 status (solo path).
5. `test_auth_error_on_multi_provider_pool_is_relayed_not_
   synthesized` — TWO-provider pool so the synth branch is reachable.
   A genuine 401-bad-key on every provider is RELAYED as 401, NOT
   failed over and wrapped in the synth 503 envelope. THIS is the
   test that actually locks the ADR-0016 step #5 money-path
   distinction: reverting the classify taxonomy (treating a 401-bad-key
   as exhausted) routes both providers through the failover loop and
   synthesizes the 503 envelope → RED (`503 == 401`).
6. `test_class_and_rearm_default_to_unknown_when_balance_tracker_unconfigured`
   — no balance_tracker → fields present and `("unknown","unknown")`,
   never KeyError or AttributeError.

I verified each FAIL-ON-REVERT claim empirically (obi-wan-kenobi pass,
2026-07-16):
- Reverting the `providers_tried` synth → tests 1, 2, 6 RED with
  `KeyError: 'providers_tried'`.
- Reverting the 4xx-relay distinction in `proxy._is_billing_error` (all
  401 → exhausted) → test #5 RED with `503 == 401` and a synth
  envelope wrapping "Invalid API key" (the silent-downgrade leak). The
  solo tests #3, #4 stayed GREEN, proving they did not lock the
  distinction.
- Reverting the bounded `Retry-After` → test #2 RED.

## Adversarial review callouts (money-path)

1. **No silent downgrade of 4xx to 503 synth.** The 4xx-relay branch
   (forwarder.py:688-704) is reached when `obs.failover` is False (a
   genuine 401-bad-key / 400); the synth branch (forwarder.py:609-687)
   fires only when `obs.failover` is True AND, on the last provider, the
   `failovers` list is non-empty. A reviewer should confirm by reading
   the two branches side-by-side and asking "what happens to a
   401-bad-key?".

   ADVERSARIAL RE-VERIFICATION (2026-07-16, obi-wan-kenobi pass): the
   prior session's solo-upstream relay tests (#3 `test_auth_error_is_…
   _no_synthesized_envelope` and #4 `test_400_bad_request_is_…`) do NOT
   actually lock the money-path distinction — on a single-route pool
   `more` is always False, so the `if more:` failover-continue branch
   (forwarder.py:639) never appends to `failovers`, and the synth branch
   (gated on a non-empty `failovers` list, forwarder.py:643) is
   unreachable regardless of how the 401 is classified. I confirmed this
   empirically: forcing `_is_billing_error` to treat ALL 401s as
   exhausted (the exact silent-downgrade leak the ADR warns about) left
   both solo tests GREEN. The prior session's FAIL-ON-REVERT claim for
   the 4xx-relay distinction was therefore NOT satisfied. I added
   `test_auth_error_on_multi_provider_pool_is_relayed_not_synthesized`
   (test #5) which uses a TWO-provider pool so the synth path is genuinely
   reachable; reverting the relay distinction (misclassifying a genuine
   401-bad-key as exhausted) now reliably routes both providers through
   the failover loop and synthesizes the 503 envelope → the new test
   goes RED with `503 == 401`. The solo tests are retained as
   regression locks on the single-upstream path, but the multi-provider
   test is what actually proves the money-path invariant.
2. **No fabricated class/rearm strings.** `_classify_provider` reads
   from `bt.funding_class(provider)`. If funding_class returns None
   (unconfigured), the field is `("unknown", "unknown")` — not a
   guess. A reviewer should confirm by inspecting
   `balance.BalanceTracker.funding_class` and the helper at
   `forwarder.py:60-80`.
3. **Bounded retry-after.** The `Retry-After` header is bounded to
   [1, max_cooldown_s] by the existing `retry_after_hint` (P1). My
   body field mirrors the same value. A reviewer should confirm by
   reading `proxy_server.retry_after_hint` (line 686) and the
   `handler._send_resp_headers(retry_after=...)` call.
4. **No new pip dependencies.** The helper is stdlib-only (uses
   `int` and dict lookups). Confirmed by inspecting imports at the
   top of `forwarder.py`.
5. **No secrets in repo.** The terminal error body is a structured
   view of routing state — no keys, no base URLs.

## Out of scope (intentionally)

- `proxy.py` classify taxonomy — unchanged. The body just surfaces
  `obs.note` as the per-entry `reason` string (single source of
  truth).
- `balance.py` — unchanged. The helper reads via the public
  `funding_class(provider)` API.
- `proxy_server.py` — unchanged. The `_send_resp_headers` signature
  already accepts `retry_after=...`; no new param added.
- 4xx-relay branch (forwarder.py:665-668) — unchanged. The new
  tests regression-lock the existing behavior, no code change.
