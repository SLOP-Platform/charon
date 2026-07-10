# Adversarial review — PR #88 `fix/billing-est-cost` (BILLING-EST-COST-FIX)

Money-path review of the BRANCH DIFF (`git diff origin/master...origin/fix/billing-est-cost`).
Read-only. Diff = `src/charon/forwarder.py` (2 helpers + 3 call-site swaps), new
`tests/test_forwarder_billing.py`, `docs/review-log/BILLING-EST-COST-FIX.md`. Nothing else.

## Verdict: **MERGE** (clean within scope) — with ONE required follow-up flagged below.

The diff is defect-free and correct for its `owns:` boundary. The one substantive issue
(partial coverage of the $223 phantom) is a scope limitation the builder documented and
correctly punted to another ticket, not a defect introduced here.

---

## Findings by severity

### 🟡 MEDIUM — the money-path bug is only PARTIALLY closed (documented, out-of-scope)
- The fix keys billing on `obs.cost_source` (`forwarder.py` new `_spend_to_record`):
  records `0.0` only for `free`/`provider`/`computed`, keeps the `est_cost` floor for
  `cost_source == "unpriced"` or `usage is None`.
- In the current classifier (`proxy.py:330-351`), an EXPLICIT provider `cost: 0` with
  no `free` flag and no stored per-token pricing is classified **`unpriced`** — because
  `_gateway_usage` (proxy.py:126) collapses "no cost field" and "explicit 0" to the same
  `cost_usd == 0`. So a flat-subscription provider (e.g. NanoGPT: explicit `cost:0`, no
  per-token pricing) **still hits the floor** and still inflates spend.json.
- Failure scenario: point the gateway at NanoGPT (flat plan). Every completion reports
  `cost:0`, classifies `unpriced`, and bills `request_bytes/4·$1.5e-6` — the same phantom
  that produced ~$223. This PR fixes only the `free:true`-flagged half.
- NOT a blocking defect: the classifier change belongs to a different ticket's `owns:`
  (`NORMALIZE-CASE-QUANT-FIX`, Wave 1), and this code is forward-compatible — it records
  `0.0` the moment proxy.py emits a real-$0 cost_source. The review-log calls this out
  explicitly. **ACTION for manager: PR #88 does NOT fully kill the $223 phantom; the
  proxy.py companion MUST land or flat-plan providers keep inflating spend.** Confirm the
  operator's actual leaking provider was `free:true` (fixed here) vs flat-plan (not).

### 🟢 Fabrication removal — CORRECT within scope (req 1)
Exactly two billing writes exist (`spend_limiter.record`, forwarder.py:315 non-stream,
:400 stream); both now route through `_spend_to_record`. No other path stamps the floor.
`note_request` logs the real `cost` var, never est_cost. `observer.record` is the usage
ledger, untouched.

### 🟢 Real PAYG cost still lands (req 2)
`_spend_to_record` returns `obs.usage.cost_usd` for `provider`/`computed`/`free`. For
`provider`/`computed` that value is always > 0 (proxy.py:330 routes explicit-$0 elsewhere,
and `computed` requires `computed > 0`). Metered charges are recorded verbatim.

### 🟢 Fail-on-revert HOLDS (req 3)
`test_flat_provider_zero_cost_not_billed_est_floor` drives `forward_with_failover` e2e
with `model_pricing={"v":{"free":True}}`; mock returns `usage.cost:0.0`.
- Classify → `cost_source == "free"` (proxy.py:335), usage not None.
- Verified the floor is strictly positive here: `_pre_flight_estimate` with `{free:True}`
  has `cost_input/cost_output == None`, so it returns `est_tokens·0.0000015 > 0`
  (proxy_response.py) — the free flag does NOT zero the estimate. So old
  `cost if cost>0 else est_cost` records a positive floor → asserts `== [0.0]` → RED;
  new records `[0.0]` → GREEN. True fail-on-revert, both stream + non-stream.
- The test asserts the ledger-observable amount (`_RecordingLimiter.recorded`), not an
  internal. `test_unpriced_response_still_records_est_floor` is a boundary/SR-7 guard
  (passes both ways by design — correctly labeled, not a fail-on-revert test).

### 🟢 Normalizer bonus fix — CORRECT and in-scope (req 4)
`_normalize_message_content` (forwarder.py) parses the body, rewrites ONLY
`choices[0].message.content` via the `@staticmethod ResponseNormalizer.normalize`
(response_normalizer.py:196), re-serializes. Safe fall-throughs: unparseable body,
missing choices/message/content, or non-str content (multimodal list) → returned
byte-for-byte, never corrupted. No Content-Length header is emitted for the 200 relay
(`_send_resp_headers` sets none), so json.dumps reformatting/ensure_ascii is harmless.
Classification happens BEFORE normalization (order unchanged), so downgrade detection and
caching are unaffected. Streaming path never invoked the normalizer — unchanged.

### 🟢 No scope creep / no regressions (req 5)
Diff touches only forwarder billing + the content-only normalizer. Failover, usage ledger,
streaming buffering, caching, and downgrade logic are untouched.

### 🟢 spend.json reset (req 6)
The diff contains NO programmatic spend.json reset — correct. spend.json is runtime state
on the /data volume; resetting it is an OPS step, not a code change, so there is zero risk
of code wiping other state. NOTE: the actual prod reset is therefore a manual operator
action that is NOT part of this PR — confirm it is performed on deploy.

---

## Bottom line
Code is correct, tested with a genuine fail-on-revert, no regressions, normalizer fix
sound. MERGE. Two things the manager must carry forward (neither blocks this PR):
1. The proxy.py companion (`NORMALIZE-CASE-QUANT-FIX`) is REQUIRED to close the flat-plan
   `provider(0)` half of the phantom spend.
2. The prod spend.json reset is a manual ops step, not in this diff.
