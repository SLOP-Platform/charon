# SESSION — LITELLM-COST-FIELD-TEST: unblock the v0.6.1 release

**Model:** a NON-ANTHROPIC model through the Charon gateway. Never Claude/Anthropic.
Graded sample, work_class `money-path`.
**Repo:** charon (PUBLIC) · **Branch:** `fix/litellm-cost-field-test`
**Worktree:** `/home/stack/charon-wt/LITELLM-COST-FIELD-TEST` — ISOLATED.
**Do NOT work in `/home/stack/code/charon`** (manager holds it) or any other agent's worktree.

## WHY THIS EXISTS — it gates an IMMUTABLE release
`v0.6.1` cannot be cut until this lands. An adversarial review of `6782236` returned **HOLD** with one
BLOCKING and one SHOULD-FIX finding. Published GHCR tags are **immutable — never overwritten**, so a
test cannot be added to this tag later. Fix both, then the release proceeds.

**Reassuring context, so you calibrate correctly:** the reviewer PROVED this module is verify-only —
`litellm_cost` has **zero production callers**; Charon's authoritative spend runs
`forwarder.py → proxy._model_provider_cost → BalanceTracker`, untouched. So there is no live money
bug to chase. You are hardening an ALARM, not fixing billing. Do not go looking for a money bug that
the review already refuted.

## FIRST ACTS
0. **Claim your session name MECHANICALLY:**
   ```
   NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"
   echo "claimed: $NAME"
   ```
   Then `session-bridge_register(session_id="<the claimed NAME>", name="LITELLM-COST-FIELD-TEST",
   repo="charon", ticket="LITELLM-COST-FIELD-FIX", status="in-progress", model="<your model>")`.
   **Never reuse a name on the board.** If your lease expires, do NOT renew — **re-register**.
1. `git -C /home/stack/code/charon fetch origin`
2. `git -C /home/stack/code/charon worktree add -b fix/litellm-cost-field-test /home/stack/charon-wt/LITELLM-COST-FIELD-TEST origin/master`
3. `cd /home/stack/charon-wt/LITELLM-COST-FIELD-TEST`
4. Read the full review first:
   `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-LITELLM-COST-FIELD.md`

## FIX 1 (BLOCKING) — zero test coverage on the new branch
`src/charon/litellm_plane/metering.py:55-58` and `:60-62` — `_cost_from_hidden()` prefers
`_hidden_params["response_cost"]` before falling back to `usage.cost` / `usage.total_cost`.
`git diff 6782236^..6782236 -- tests/` is EMPTY: no test was added. The existing tests only exercise
`usage.cost`.
**Failure scenario to close:** litellm renames `response_cost`, or someone "fixes" the dict branch.
No test fails. The next release ships a silently-broken cross-check — and that cross-check is the
alarm sitting on top of a meter *already known to be wrong* (live gateway reports `$0.000704` against
252M input tokens). The verify-only invariant quietly becomes verify-nothing.
Add a test per new branch edge: hidden-param present, hidden-param absent (falls back), malformed
value (coerce fails → falls back, not crash).

## FIX 2 (SHOULD-FIX) — `0.0` is conflated with "missing"
`metering.py:57-58`. Verified by the reviewer's smoke test: `_hidden_params={'response_cost': 0.0}`
returns `0.0` and does NOT fall back to `usage.cost=0.5`.
**Failure scenario:** a legitimately-$0.00 request (cached, free tier) where Charon's token-priced
cost is non-zero → `COST DIVERGENCE` logs on EVERY such call, drowning the 13+ genuine divergence
cases. That alarm has driven rollback decisions, so saturating it is an operational regression.
Distinguish "field absent" from "field present, value 0" — a sentinel that lets the caller fall
through. Preserve the genuine-zero case: a real $0.00 must still be reportable as zero, not silently
converted to a fallback value.

## FIX 3 (NIT, only if trivially safe)
`metering.py:67-69` — the dict branch reads `cost` AND `total_cost`; the object branch reads only
`cost`. Asymmetry introduced by `6782236` for no reason. Make them symmetric, or say why not.

## REQUIRED PROOF (green is not proof)
- **RED-PROOF BY EXECUTION** for FIX 1: revert `_cost_from_hidden` to ignore `_hidden_params` -> the
  new test goes RED naming the hidden-param case. **Report BOTH exit codes.**
- **RED-PROOF for FIX 2:** restore the 0.0-conflation -> a test goes RED showing a genuine-$0.00
  request no longer falls through. Report both exit codes.
- NON-VACUOUS: a test that asserts nothing about the fallback path is not coverage — state which
  branch EDGE each test pins.
- Do NOT change what the module BOOKS — it books nothing and must continue to book nothing. If your
  change makes this module authoritative for spend, you have gone wrong: STOP and report.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- `PYTHONPATH=src python3 -m charon.cli gate` GREEN and `PYTHONPATH=src python3 -m pytest -q` GREEN.
- State what you proved by RUNNING vs by READING, and which git ref you measured on.

## BOUNDARY
Product is PUBLIC: no `/home/stack` paths, no internal IPs/hostnames, no fleet/rig/SLOP references,
no secrets in `src/` or committed config.

## OWNS — do not touch anything else
`src/charon/litellm_plane/metering.py`, `tests/test_gw_bridge2_metering.py`.
**`src/charon/gateway.py` is NOT yours** (four tickets claim it), nor is `forwarder.py`, `proxy.py`,
`balance.py`, or `routing_policy/`. If the fix appears to need any of them, STOP and report.

## REPORT BACK (short — no diffs)
Which branch edges are now pinned · both exit codes for each red-proof · confirmation the module
still books nothing · gate pass/fail · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "LITELLM-COST-FIELD-TEST: pin the hidden-params cost branch and stop conflating 0.0 with absent"
```
Do NOT push. **NEVER use `WORK_LEASE_BYPASS=1`** — if a gate refuses, STOP and report.

## Dependencies & sequence
- **Depends on: NOTHING. Startable immediately.** `metering.py` is owned by no live board ticket
  (verified 2026-07-26 against the full owns: set).
- **Blocks: the `v0.6.1` release** — which in turn blocks the 4-LOM deploy carrying `0947401`
  (grading) and `fd03840` (energy_kwh money bug), and the frontier re-measure that depends on the
  aistudio Gemini-3 alias going live.
- **Wave:** release lane, P0.
