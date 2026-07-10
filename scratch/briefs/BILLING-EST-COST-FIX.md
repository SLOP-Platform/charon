# SESSION — BILLING-EST-COST-FIX: stop billing the est_cost floor on free/flat $0 responses

**Model:** opus (frontier) — money-path metering; strongest coder, do NOT economize.
**Repo:** charon · **Ticket:** BILLING-EST-COST-FIX
**Base branch/worktree:** `fix/billing-est-cost` at `/home/stack/code/charon-fleet-BILLING-EST-COST-FIX`
(an isolated worktree off latest `origin/master` — do NOT work in the shared main tree
`/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create it off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master`; resolve conflicts; re-run tests after.
3. Register on the session-bridge (`register`: your `session_id`, `repo: "charon"`,
   `ticket: "BILLING-EST-COST-FIX"`, `status: "in-progress"`); heartbeat via `update`.
4. Read `scratch/provider-cost-rationalization.md` (Fix 1 est_cost evidence) before starting.

## FILES OWNED (touch only these)
- `src/charon/forwarder.py`
- `tests/test_forwarder_billing.py` *(new)*

## THE TASK (what's broken)
`forwarder.py` fabricates spend. At `forwarder.py:315` (non-stream) and `forwarder.py:400`
(stream) the code does `srv.spend_limiter.record(cost if cost > 0 else est_cost)`. `est_cost`
is the pre-flight floor from `_pre_flight_estimate` (defined ~`forwarder.py:141`:
`(request_bytes/4) · $1.5e-6`). Whenever a provider reports a REAL `cost == 0` — which is
ALWAYS for free/flat-rate routes — the code substitutes the phantom `est_cost`, inflating
spend.json to the fictional ~$223.28 seen in prod.

## REQUIRED CHANGE
1. **Only substitute `est_cost` when cost is genuinely UNPRICED/UNKNOWN, never when the
   provider reported a real $0 or the model is free/flat.** Distinguish the cost source:
   `cost_source in {"free","provider(0)"}` → record `0.0`; only `unpriced` (no price data at
   all) → record the `est_cost` floor. Apply the SAME fix at BOTH record sites:
   `forwarder.py:315` (non-stream) and `forwarder.py:400` (stream).
2. **Bonus latent bug, same file, fold in:** `forwarder.py:296-300` passes the WHOLE decoded
   JSON body to `response_normalizer.normalize(...)`, but the normalizer is specified to operate
   on `choices[0].message.content` ONLY (STANDARDIZE_MD runs regex over the entire envelope
   today). Fix so the post-hook only ever receives/rewrites message content, not the JSON
   envelope.

## ACCEPTANCE CRITERIA
- Per-ticket: `PYTHONPATH=src python3 -m pytest tests/test_forwarder_billing.py -q` green.
- **FAIL-ON-REVERT test (required):** `test_flat_provider_zero_cost_not_billed_est_floor` —
  drive `forward_with_failover` on BOTH the non-stream AND stream paths against a stub upstream
  reporting `cost_usd == 0` on a free/flat route; assert `spend_limiter.record` was called with
  **`0.0`**, NOT the `est_cost` floor. It must be RED today (records the floor), GREEN only with
  the fix, and RED again if the fix is reverted — it asserts the client-observable metering
  outcome, not an internal detail.
- Second assertion `test_response_normalizer_receives_content_not_whole_body`: the post-hook is
  handed `choices[0].message.content`, not the full JSON envelope.

## MERGE GATE (not pytest-alone)
FULL CI from the worktree, ALL green before this is merge-eligible:
- `ruff` (lint)
- `mypy` (types)
- `PYTHONPATH=src python3 -m charon.cli gate`  (ruff/mypy/SLOP-boundary/version/gate-registry)
- `PYTHONPATH=src python3 -m pytest -q` (scope with `-k`/path if the full suite is slow)
Money-path change → ADVERSARIAL review before merge. Product ships STANDALONE: no `/home/stack`,
fleet, SLOP, or runner references in `src/` or committed config.

## Dependencies & sequence
- **depends_on:** *(empty)* — Wave 1, launches immediately.
- **Concurrency safety:** owns `forwarder.py` + a NEW test file, disjoint from the other two
  Wave-1 tickets (NORMALIZE-CASE-QUANT-FIX owns proxy.py; TEST-HARDEN-CONTRACT owns conftest/
  contract-test/lint). No shared file in Wave 1.
- **Downstream:** RESPONSE-ADAPTER-UNIVERSAL (Wave 2) `depends_on` THIS ticket — it edits the
  same `forward_with_failover` non-stream 200 path and must rebase onto this merge (never a
  concurrent second writer of forwarder.py). Land this cleanly so Wave 2 can build on it.
- **Out-of-band follow-up (manager/operator, NOT this droid):** after merge+deploy, reset
  `/data/spend.json` `spent_usd` 223.28 → 0 on the live box (10.0.1.60). Not part of this PR.

## REPORT BACK (short — no diffs)
Files changed, test names, gate pass/fail, and the commit SHA.

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "BILLING-EST-COST-FIX: bill real $0 as 0, not the est_cost floor; normalizer touches content only"
```
Report the commit SHA back to the manager.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.
