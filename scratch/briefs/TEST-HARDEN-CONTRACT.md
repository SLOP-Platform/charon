# SESSION — TEST-HARDEN-CONTRACT: kill the self-mirroring-mock blind spot

**Model:** sonnet (strong) — mechanical test/lint work, clear spec. One tier down (test work).
**Repo:** charon · **Ticket:** TEST-HARDEN-CONTRACT
**Base branch/worktree:** `feat/test-harden-contract` at `/home/stack/code/charon-fleet-TEST-HARDEN-CONTRACT`
(an isolated worktree off latest `origin/master` — do NOT work in the shared main tree
`/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create it off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master`; resolve conflicts; re-run tests after.
3. Register on the session-bridge (`register`: your `session_id`, `repo: "charon"`,
   `ticket: "TEST-HARDEN-CONTRACT"`, `status: "in-progress"`); heartbeat via `update`.
4. Read `scratch/test-gap-audit.md` (Fix 3 detail) before starting.

## FILES OWNED (touch only these)
- `tests/conftest.py`
- `tests/test_provider_response_contract.py` *(new)*
- `tools/check_test_patterns.py` *(EXISTS on disk — DTC-8 already landed/done; extend it)*
- `tests/test_check_test_patterns.py` *(EXISTS — extend it)*

## THE TASK (what's broken)
`conftest.py:54-60` plus ~14 inline handlers all return the canonical OpenAI shape, so
foreign-envelope bugs are invisible — this is why the cline non-stream defect passed green. The
mocks mirror the code's expectations instead of a provider's real wire shape.

## REQUIRED CHANGE
1. **Parametrized provider-contract test** (`tests/test_provider_response_contract.py`) over
   EVERY `ProviderPreset` in `providers.py`: for each preset, drive a non-stream completion
   through the proxy against a mock returning THAT preset's known raw shape, and assert the
   CLIENT response has a **top-level `choices` list AND a top-level `usage` dict**. A new preset
   with no declared shape fixture must fail the parametrization LOUDLY (not silently skip).
   - For `cline-pass`, mark that parametrization case
     `@pytest.mark.xfail(reason="cline non-stream envelope unwrapped by RESPONSE-ADAPTER-UNIVERSAL", strict=False)`.
     `strict=False` means once RESPONSE-ADAPTER-UNIVERSAL lands it simply xpasses — no
     cross-ticket edit needed, and this ticket never touches Fix 4's files.
2. **`check_test_patterns.py` lint extension** (self-mirroring-mock rule): flag any proxy/
   forwarder test whose upstream mock body is authored inline AND whose assertions only read
   *inside* `choices` — nudge toward the contract fixture. Extend
   `tests/test_check_test_patterns.py` to cover the new rule.
3. Update `conftest.py` ONLY as needed to support the contract fixture (still the sole ticket
   touching conftest.py).

## ACCEPTANCE CRITERIA
- Per-ticket:
  `PYTHONPATH=src python3 -m pytest tests/test_provider_response_contract.py tests/test_check_test_patterns.py -q` green.
- **FAIL-ON-REVERT test (required):** `test_check_test_patterns_flags_self_mirroring_mock` —
  asserts the new lint rule FIRES on a fixture that mocks canonical output AND only asserts
  inside `choices`. RED without the rule, GREEN with it, RED again on revert. (The contract test
  is the durable class-killer that asserts client-observable top-level `choices`+`usage`; this
  lint test is the crisp revert-guard.)

## MERGE GATE (not pytest-alone)
FULL CI from the worktree, ALL green before this is merge-eligible:
- `ruff` (lint)
- `mypy` (types)
- `PYTHONPATH=src python3 -m charon.cli gate`  (ruff/mypy/SLOP-boundary/version/gate-registry)
- `PYTHONPATH=src python3 -m pytest -q`
Standard review (test harness, not money-path code). Product ships STANDALONE: no `/home/stack`,
fleet, SLOP, or runner references in `src/`, `tests/`, `tools/`, or committed config.

## Dependencies & sequence
- **depends_on:** *(empty)* — Wave 1, launches immediately. The cline-pass contract case is
  `xfail(strict=False)`, so this ticket does NOT depend on RESPONSE-ADAPTER-UNIVERSAL and is not
  pushed to a later wave.
- **Concurrency safety:** owns conftest.py + the new contract test + the lint file/test, all
  disjoint from BILLING-EST-COST-FIX (forwarder.py) and NORMALIZE-CASE-QUANT-FIX (proxy.py). No
  shared Wave-1 file. `check_test_patterns.py` + `test_check_test_patterns.py` were DTC-8's; DTC-8
  is DONE (state/done marker), so this ticket is now their sole LIVE owner (done/live = ok).

## REPORT BACK (short — no diffs)
Files changed, test names, gate pass/fail, and the commit SHA.

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "TEST-HARDEN-CONTRACT: parametrized provider-response contract test + self-mirroring-mock lint rule"
```
Report the commit SHA back to the manager.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.

## REJECTED 2026-07-10 — FIX THESE 2 DEFECTS BEFORE RESUBMIT (review: scratch/review-pr87-testharden.md)
1. The contract test lists `anthropic` in `_OPENAI_SHAPE_PRESETS` and feeds it a FABRICATED OpenAI-shaped mock. But `anthropic` is wire=WIRE_ANTHROPIC (native /v1/messages; the proxy does NOT translate its response to OpenAI shape until Phase-2) — this re-introduces the exact self-mirroring blind spot the ticket exists to kill. FIX: exclude `anthropic` from the OpenAI-shape contract set (mark xfail/known-native pending Phase-2, like cline-pass) OR feed a REAL anthropic-shaped mock and assert its true contract. The mock must not lie about the provider's real wire shape.
2. The self-mirroring-mock lint is a WARNING that runs NOWHERE — `charon.cli gate` never invokes the enforcer, so it gates nothing. FIX: wire the enforcer INTO `charon.cli gate` as an ERROR; prove it (a planted self-mirroring mock must FAIL the gate; clean codebase must pass).
Keep everything else (per-preset coverage, cline xfail, shape-sensitive assertion) — verified solid.
