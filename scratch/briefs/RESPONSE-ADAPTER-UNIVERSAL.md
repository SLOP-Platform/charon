# SESSION — RESPONSE-ADAPTER-UNIVERSAL: universal per-provider response adapter (unwrap cline non-stream)

**Model:** opus (frontier) — money-path failover/metering with subtle side-effects; ADR §10
mandates the strongest coder. Do NOT economize.
**Repo:** charon · **Ticket:** RESPONSE-ADAPTER-UNIVERSAL
**Base branch/worktree:** `feat/response-adapter-universal` at `/home/stack/code/charon-fleet-RESPONSE-ADAPTER-UNIVERSAL`
(an isolated worktree off latest `origin/master` — do NOT work in the shared main tree
`/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create it off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master` — **this MUST already contain the merged
   BILLING-EST-COST-FIX** (your `depends_on`); you rebase onto its forwarder.py changes, never
   run as a concurrent second writer. Resolve conflicts; re-run tests after.
3. Register on the session-bridge (`register`: your `session_id`, `repo: "charon"`,
   `ticket: "RESPONSE-ADAPTER-UNIVERSAL"`, `status: "in-progress"`); heartbeat via `update`.
4. Read `fleet/ADR-UNIVERSAL-RESPONSE-ADAPTER.md` (the design of record, T1–T5) before starting.

## FILES OWNED (touch only these)
- `src/charon/response_adapters.py` *(new)*
- `src/charon/providers.py`
- `src/charon/gateway.py`
- `src/charon/proxy_server.py`
- `src/charon/forwarder.py`  *(shared with BILLING-EST-COST-FIX — you rebase onto its merge)*
- `tests/test_response_adapters.py` *(new)*
- `tests/test_proxy_server.py`

## THE TASK (what's wanted)
Implement `fleet/ADR-UNIVERSAL-RESPONSE-ADAPTER.md` (T1–T5; T6 streaming DEFERRED). Cline Pass's
non-stream responses come back wrapped as `{"data":{…choices,usage…},"success":true}` with no
top-level `choices` — Charon relays that verbatim, breaking non-stream clients AND silently
undercounting usage/spend.

## REQUIRED CHANGE
1. New `src/charon/response_adapters.py`: a `ResponseAdapter` Protocol; `IdentityAdapter` +
   `IDENTITY` singleton (default for every provider, byte-identical passthrough); `ClineAdapter`
   (unwrap `{"data":{…choices…},"success":true}` → the inner OpenAI object; idempotent + total);
   an `_ADAPTERS` registry + `get_adapter`.
2. Plumb an `adapter` key mirroring `wire`: a field on `ProviderPreset` (providers.py) → resolve
   in `_route_from_spec` (gateway.py) → a field on `UpstreamRoute` (proxy_server.py) → resolved
   once per attempt in the forwarder.
3. Plug into `forward_with_failover` on the **non-streaming 200 path** (between `_drain` and
   `_extract`, ~`forwarder.py:271`) behind an `if route.adapter:` guard so the IDENTITY path
   stays byte-identical; also apply on the non-200 error-unwrap (guarded). Restores real `usage`
   metering for cline non-stream.
4. Add a `cline-pass` preset with `adapter="cline"`, `strip_v1`, and the no-`/models` note.

## ACCEPTANCE CRITERIA
- Per-ticket:
  `PYTHONPATH=src python3 -m pytest tests/test_proxy_server.py tests/test_response_adapters.py -q` green.
- **FAIL-ON-REVERT test (required):** `test_proxy_nonstream_cline_shaped_upstream_returns_openai_body`
  (integration) — a stub upstream returns a wrapped `{"data":{…choices,usage…},"success":true}`
  body on a route with `adapter="cline"`; drive ONE non-stream request; assert the CLIENT body
  has top-level `choices` (content matches the inner object) AND that `usage`/cost was recorded
  non-zero via the observer/spend path. Reverting the shim → served body lacks `choices` → RED.
  It asserts client-observable body + metering, GREEN only with the adapter, RED on revert.
- Plus `test_identity_provider_body_byte_identical` (default path unchanged) and the config-flow
  test (`provider: cline-pass` → `UpstreamRoute.adapter == "cline"`).

## MERGE GATE (not pytest-alone)
FULL CI from the worktree, ALL green before this is merge-eligible:
- `ruff` (lint)
- `mypy` (types)
- `PYTHONPATH=src python3 -m charon.cli gate`  (ruff/mypy/SLOP-boundary/version/gate-registry)
- `PYTHONPATH=src python3 -m pytest -q`
Money-path change (touches the classify/usage/spend path Fix 1 just changed) → ADVERSARIAL
review before merge. Product ships STANDALONE: no `/home/stack`, fleet, SLOP, or runner
references in `src/` or committed config.

## Dependencies & sequence
- **depends_on:** `BILLING-EST-COST-FIX` — REAL shared-file prereq. This ticket edits the SAME
  `forward_with_failover` non-stream 200 path that BILLING-EST-COST-FIX edits, so it MUST rebase
  onto that merge and never be a concurrent second writer of `forwarder.py`. This edge is what
  makes the shared forwarder.py ownership legal under `validate_board.sh`.
- **Wave 2** — the frontier pool auto-claims this the instant BILLING-EST-COST-FIX is MERGED and
  `done.sh`'d (`claim.sh` gates on `state/done/BILLING-EST-COST-FIX`). No manual un-park needed;
  keep one frontier tab alive through the Wave 1→2 gap.
- **No cross-ticket edits:** TEST-HARDEN-CONTRACT's cline-pass contract case is
  `xfail(strict=False)` and will simply xpass once this lands — you do NOT touch
  `tests/test_provider_response_contract.py`.

## REPORT BACK (short — no diffs)
Files changed, test names, gate pass/fail, and the commit SHA.

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "RESPONSE-ADAPTER-UNIVERSAL: universal ResponseAdapter (Identity default + Cline unwrap) on the non-stream path"
```
Report the commit SHA back to the manager.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.
