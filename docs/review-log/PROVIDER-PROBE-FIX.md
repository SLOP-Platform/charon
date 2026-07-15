# PROVIDER-PROBE-FIX — review log

**Auth/validation path (not money-path).** Stop `validate_provider_key`
rejecting valid provider keys when the chat probe 4xx's on the placeholder
`"."` model id. Owns: `src/charon/config/keyprobe.py`,
`src/charon/gateway.py`, `tests/test_config.py`.

## What changed

1. **`config/keyprobe.py`** — restructured `validate_provider_key` so a
   successful authenticated `GET /models` (200 + parseable list) short-
   circuits to `valid: True` BEFORE the chat probe runs. The chat probe is
   now strictly a fallback for when `/models` is unreachable/non-200/
   unparseable. When the chat probe DOES run, it picks the first real model
   id from `/models` instead of the placeholder `"."` (defensive — only
   reachable when `/models` returned a list but the items shape prevented
   the short-circuit).
2. **`config/keyprobe.py`** — added a `skip_probe: bool = False` keyword.
   When True, returns `{"valid": True, "skipped": True, ...}` without
   making any HTTP calls. Lets operators persist a provider whose key
   isn't reachable pre-activation (token-gated / limited-access keys).
3. **`gateway.py`** — `providers` action now reads `payload.get("skip_probe")`
   and threads it through to `config.validate_provider_key` via kwarg.
4. **`tests/test_config.py`** — 4 new tests:
   - `test_validate_provider_key_models_ok_short_circuits_chat_probe` — the
     FAIL-ON-REVERT: stubs upstream returning 200+list on `/models` but
     HTTPError(400) on `/chat/completions`, asserts `valid: True`.
   - `test_validate_provider_key_models_unreachable_still_rejects_on_chat_400`
     — guard against the fix becoming a free pass: when `/models` is
     unreachable AND the chat probe 400's, the key is still rejected.
   - `test_validate_provider_key_skip_probe_returns_skipped_without_network`
     — unit-level check: `build_opener` is never called.
   - `test_providers_gateway_action_skip_probe_end_to_end` — the
     `/charon/providers` web-setup action honours `skip_probe: true`,
     persists the provider, returns `probe.skipped: True`.

## Key decision — early-return vs in-band fallback

Considered two shapes:

**(A) Early-return on `/models` success** (chosen):
```python
if models_ok: return {valid: True, message: "via /models", ...}
```
Pros: matches the spec's primary fix verbatim ("Treat a successful
authenticated `GET /models` as sufficient validation on its own"); the
chat probe can't wrongly reject a valid key. Test is crisp.

**(B) In-band fallback** (rejected): mirror the old `except Exception`
behaviour in the `except HTTPError` branch — i.e. when chat 4xx's, check
`models_count > 0` and rescue if set.
Pros: keeps the chat probe as the primary gate, /models as a rescue.
Cons: still runs the chat probe on every `/models` success, still
vulnerable to the provider rejecting the model id we picked. The early-
return is strictly safer.

The spec's requirement to "pick a real model id from the /models response"
is preserved as defensive code: when items in /models parse as a list with
ids, we capture the first id; if the early-return didn't trigger for some
reason, the chat probe would use a real id rather than the placeholder.

## Verified

- `PYTHONPATH=src python3 -m pytest -q` — 1727 passed, 1 xfailed, 1 xpassed
- `ruff check` — clean on touched files (5 pre-existing errors in
  `tools/_vendor/ksf_inert_code.py` are not mine; same on master)
- `mypy src tests` — no errors
- `python3 tools/check_boundary.py src` — OK
- `python3 tools/check_version.py` — pre-existing pyproject drift, not from
  this change
- FAIL-ON-REVERT confirmed: stashing the keyprobe.py change reverts
  `test_validate_provider_key_models_ok_short_circuits_chat_probe` to RED
  with the exact bug message (`'probe failed (HTTP 400)'`).

## Out of scope (intentionally not touched)

- `src/charon/providers.py` — work-spec listed it, but the ticket's `owns:`
  line (single source of truth per the rules) does NOT. The probe logic
  was already moved to `config/keyprobe.py` by F29-CONFIG-PKG; no edit
  needed in `providers.py`.
- `src/charon/config.py` — file no longer exists (F29 split it into
  `src/charon/config/`); the bug location moved to `keyprobe.py` per the
  ticket's `verified` field.
- The SSRF guard (link-local/metadata host refusal) and `_NoRedirect`
  opener — explicitly preserved per the spec.