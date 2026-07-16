# REVIEW LOG — PROVIDER-URL-HELPER

**Ticket:** PROVIDER-URL-HELPER (dedup provider URL/path construction)
**Branch:** `refactor/provider-url-helper`
**Work class:** refactor · **Tier:** strong (D3)
**Depends on:** DELETE-STATIC-RANK (ticket metadata) · real-dep on PROVIDER-PROBE-FIX
(shared writer of config.py `validate_provider_key` region + providers.py base_url
handling) — confirmed merged into the branch's origin/master base.

## Files changed (all in `owns:`)
- `src/charon/providers.py` — added `validate_base_url`, `join_endpoint`,
  `models_url`, `chat_url`; rewired `list_models` to call `models_url` (removed
  its inline scheme/host guard + `base.rstrip("/") + "/models"`).
- `src/charon/config/keyprobe.py` — `validate_provider_key` now calls the shared
  `providers.models_url` / `providers.chat_url` instead of its own inline
  `raw_base = base_url.rstrip("/")` + `raw_base + "/models"` + `raw_base +
  "/chat/completions"` and its own inline SSRF guard. Catches the helper's
  `ValueError` to preserve the dict-return contract `{valid: False, message}`.
- `src/charon/discover.py` — `discover_provider` now calls
  `providers.join_endpoint(providers.validate_base_url(base_url), path)` with
  `path = "models" if strip_v1 else "v1/models"` (preserving the `strip_v1=False`
  → `/v1/models` semantics). Catches `ValueError` → returns `None` (old behavior
  on any error). Previously a bare `base_url.rstrip("/") + "/models"` with NO
  scheme/host validation at all — now it gets the SSRF guard for free.
- `tests/test_providers.py` — added 11 tests (see Test names below).

## Design decisions
1. **Helper home = `providers.py`** (where `ProviderPreset` lives), as the spec
   required. `config/keyprobe.py` imports it via `from .. import providers`
   (deferred/local import avoids any module-cycle concern; keyprobe is inside the
   `config` package which must not reverse-depend on `providers` at module load).
2. **Message wording preserved exactly.** `validate_base_url` raises
   `f"invalid base URL scheme {parts.scheme!r}"` and
   `f"refusing link-local / metadata host {host!r}"` — these are the EXACT
   strings the old inline keyprobe guard produced, so `str(exc)` flowing through
   keyprobe's catch keeps `test_console_provider_mgmt.py::test_validate_provider_key_bad_scheme`
   (`assert "scheme" in message`) and `_metadata_host` (`assert "refusing"`)
   green. `(config._store._validate_base_url` keeps its separate, pre-existing
   `f"base_url must be http(s)..."` wording — it's NOT in my owns and its
   callers don't assert on the word "scheme", so unifying wording there is out of
   scope and unnecessary.)
3. **No-behavior-change guard is exhaustive.** `_EXPECTED_MODELS_URLS` /
   `_EXPECTED_CHAT_URLS` hardcode the exact resolved URL for EVERY preset in
   `PRESETS` (26 providers), including the nested-path bases (opencode-zen
   `.../zen/v1`, opencode-go `.../zen/go/v1`, zai `.../api/paas/v4`, groq
   `.../openai/v1`, cline-pass `.../api/v1`, fireworks `.../inference/v1`). A
   missing/extra preset fails first (the dict key sets are diffed), then each
   resolved URL is string-compared. This is the regression guard the acceptance
   criteria require.
4. **SSRF guard moved, not duplicated.** `config/keyprobe.py` no longer has its
   own `if parts.scheme not in (...)` / `host.startswith("169.254.")` block — it
   delegates to `validate_base_url` and catches the `ValueError`. `discover.py`
   gains the guard it previously lacked (it now refuses a link-local base instead
   of surfacing a confusing urllib error). The accept-command grep confirms zero
   leftover `rstrip("/") + "/(models|chat/completions)"` inline construction in
   the three owned files.
5. **`cli.py` left untouched (READ-ONLY reference context).** It has its own
   `_do_probe` / `providers test` call sites with inline rstrip+concat — they
   are NOT in this ticket's `owns:`. Per the work-spec, if a refactor genuinely
   required editing `cli.py`, STOP and flag. This refactor does not: `cli.py`'s
   `_do_probe` is a standalone probe used only by `charon providers test` and
   its message contract is asserted by `test_console_provider_mgmt.py`; touching
   it would be off-scope. Flagged here for a future ticket.

## Test names added (tests/test_providers.py)
- `test_models_url_preserves_all_preset_endpoints_exactly` — no-behavior-change
  guard for `models_url` across ALL 26 PRESETS.
- `test_chat_url_preserves_all_preset_endpoints_exactly` — same for `chat_url`.
- `test_models_url_keeps_nested_path_segments` — opencode-zen / opencode-go /
  zai path segments not dropped.
- `test_chat_url_strips_trailing_slash_once` — single slash, no `//`.
- `test_models_url_rejects_link_local_and_metadata_hosts` — SSRF guard survived
  the move (169.254.x + metadata.google.internal).
- `test_chat_url_rejects_link_local_and_metadata_hosts` — SSRF on chat path too.
- `test_validate_base_url_rejects_non_https_scheme` — ftp/file/gopher refused.
- `test_validate_base_url_accepts_http_and_https_and_strips_trailing_slash` —
  http (localhost) accepted; trailing slashes stripped.
- `test_join_endpoint_single_slash_no_path_drop` — join contract.

## Gate
- `PYTHONPATH=src python3 -m pytest tests/test_providers.py tests/test_config.py
  tests/test_discover.py -q` → **97 passed**.
- Accept command (helper importable + test name grep + leftover-grep + targeted
  pytest) → **PASS**.
- `ruff check` (owned files) → clean. (5 pre-existing `tools/` errors on master
  are out of scope.)
- `mypy src tests` → `Success: no issues found in 244 source files`.
- `tools/check_boundary.py src` → `boundary OK`.
- `tools/check_version.py` → exit 0 (pre-existing local "VERSION DRIFT … Not
  failing outside CI" note; environment artifact, not a regression).
- Full `pytest -q -p no:randomly` → **1843 passed** (the full-suite failures
  observed under random ordering are pre-existing on clean master — confirmed by
  `git stash` + full-suite run: 149 failed/30 errors baseline; a test-ordering
  pollution issue unrelated to this change).

## Behavior change
None to any provider's resolved URL — verified by the exhaustive
`_EXPECTED_{MODELS,CHAT}_URLS` guards. This is a pure dedup refactor.
