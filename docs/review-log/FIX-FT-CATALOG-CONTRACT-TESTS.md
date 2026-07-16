# FIX-FT-CATALOG-CONTRACT-TESTS — review fragment

Ticket: FIX-FT-CATALOG-CONTRACT-TESTS
Branch: fix/ft-catalog-contract-tests (off origin/master)
Owns: tests/test_provider_presets.py

## Problem

FT-CATALOG-SEED (PR #135, branch `feat/ft-catalog-seed`) adds 3 new hosted
presets — `github_models`, `featherless`, `ollama_cloud` — to
`src/charon/provider_presets/hosted.py`. Two things break on master when that
PR merges without a contract-test companion:

1. `tests/test_provider_presets.py::test_all_original_keys_present` — asserts
   `len(providers.PRESETS) == len(_KNOWN_KEYS)` (both 26) and set equality.
   After #135 lands: 26 != 29, FAIL.
2. The 3 new presets have no spot-check / wire-shape fixture, so a silently
   broken `base_url` / `key_env` on any of them ships without a test catching
   it.

A SEPARATE contract file — `tests/test_provider_response_contract.py` —
maintains `_OPENAI_SHAPE_PRESETS` (24 names) and would also fail on #135 land
with "preset has no declared raw-shape fixture" — but that file is NOT in
this ticket's `owns:` and is the work of a future response-adapter ticket
(per its existing TODO comment about the RESPONSE-ADAPTER-UNIVERSAL work).
This fragment therefore deliberately does not touch that file.

## Decision: forward-compatible assertions, not "land after #135"

The launcher's wave plan does NOT place FIX-FT-CATALOG-CONTRACT-TESTS in a
later wave than FT-CATALOG-SEED (both currently READY, both have empty
`depends_on:`), so the contract fix could land EITHER before or after
#135. The cleanest contract — "this PR alone keeps the gate green, and
also keeps the gate green when #135 lands" — is forward-compatibility:

- `_KNOWN_KEYS` now documents the FULL 29-preset expected set (split into
  `_ORIGINAL_KEYS` = 26 + `_FT_CATALOG_SEED_KEYS` = 3, joined into
  `_KNOWN_KEYS`).
- `test_all_original_keys_present` now asserts the original 26 are a SUBSET
  of `PRESETS.keys()` and `len(PRESETS) >= 26`. **The FAIL-ON-REVERT
  invariant is preserved**: drop a category module → count goes below 26
  OR an original key is missing → RED, exactly as before.
- If the 3 new keys ARE already in `PRESETS` (i.e. #135 has landed), the
  test additionally asserts strict equality to the 29-preset set — so a
  future PR that, say, duplicates or misspells one of the new keys goes
  RED too. The strict branch is conditional; the subset branch always
  holds. No silent drift.
- 3 new spot-checks (`test_spot_check_github_models`,
  `test_spot_check_featherless`, `test_spot_check_ollama_cloud`) declare
  the expected wire-shape fields (base_url, key_env, strip_v1,
  max_context) and skip cleanly via `pytest.skip` when the preset is not
  yet in `PRESETS` (helper `_require_preset`). When #135 lands, the
  skips turn into real assertions automatically — no second pass
  required.

## Verification

Current state (this branch only, off origin/master, #135 not yet merged):

```
PYTHONPATH=src python3 -m pytest -q tests/test_provider_presets.py
.....s.s......s.                                                         [100%]
13 passed, 3 skipped in 0.17s
```

(The 3 `s` are the new spot-checks, skipping because the presets don't
exist yet — exactly the forward-compat behavior we want.)

Verified the post-#135 state by temporarily dropping in
`feat/ft-catalog-seed`'s `hosted.py` and re-running the test (then
reverting — no commit, no off-scope edit):

```
................                                                         [100%]
16 passed in 0.12s
```

All 16 (10 original + 3 new + 3 new spot-checks) pass when the 3
presets are present; the count assertion's strict-equality branch fires
and verifies 29 == 29.

## Why not edit `test_provider_response_contract.py`?

`owns:` for this ticket is `tests/test_provider_presets.py` only. That
file's `_OPENAI_SHAPE_PRESETS` is a hand-maintained 24-name frozenset and
will go RED the moment #135 lands (loud `AssertionError`, not a skip).
Touching that file here would double-claim with the response-adapter
ticket that already plans to handle it (see the `cline-pass` TODO in
`test_provider_response_contract.py:108-111`). The forward-compat design
in this ticket keeps the gate green for THIS file in BOTH merge orders;
the response-contract file is a separate ticket's problem, surfaced
loudly by its own test the moment it matters.
