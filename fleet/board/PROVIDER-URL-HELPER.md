tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: refactor
branch: refactor/provider-url-helper
depends_on: PROVIDER-PROBE-FIX
real-dep: PROVIDER-PROBE-FIX shared-file hand-off — this ticket edits the SAME
  `validate_provider_key` URL-construction region in config.py (and the same
  `providers.py` base_url handling) that PROVIDER-PROBE-FIX edits; it must rebase onto that
  merge and never run as a concurrent second writer. Sequencing: PROVIDER-PROBE-FIX fixes the
  probe-validation LOGIC bug first (inline, no new helper needed); this ticket then extracts
  the now-fixed URL construction into the shared helper.
owns: src/charon/providers.py, src/charon/config.py, src/charon/discover.py, tests/test_providers.py
accept: PYTHONPATH=src python3 -m pytest tests/test_providers.py tests/test_config.py tests/test_discover.py -q
prompt: /home/stack/charon-private/fleet/board/briefs/PROVIDER-URL-HELPER.md
scope: Fragility finding #9. Provider endpoint URL/path construction is duplicated across
  `providers.py` (`base.rstrip("/") + "/models"` at ~line 248), `config.py`
  (`validate_provider_key`'s `raw_base = base_url.rstrip("/")` then `raw_base + "/models"` /
  `raw_base + "/chat/completions"` at ~lines 467-494, plus the SSRF/link-local/metadata-host
  guard duplicated inline), and `discover.py` / `cli.py` (each independently re-deriving a
  models or chat endpoint from a stored `base_url`). Each call site re-implements the same
  `rstrip("/")` + string-concat + ad hoc scheme/host validation, so a fix to one (e.g. the
  SSRF guard, or a provider whose base already includes a path segment) doesn't propagate to
  the others — exactly the kind of silent drift PROVIDER-PROBE-FIX's bug depended on. Add ONE
  stdlib-only helper (new function(s) in `providers.py`, since that's where `ProviderPreset`
  already lives) that: validates a base URL (scheme in http/https, rejects link-local/
  metadata hosts — reuse config.py's existing guard logic, don't fork it), joins an endpoint
  path onto it consistently (single `rstrip("/")` + `/`-joined, no double slashes, no dropped
  path segments for bases like `.../zen/v1`), and exposes `models_url(base)` /
  `chat_url(base)` (or equivalent) as the ONE place that knows the `/models` and
  `/chat/completions` suffixes. Update `config.py`'s `validate_provider_key`, `providers.py`'s
  existing inline construction, and `discover.py` to call the shared helper instead of
  re-deriving the URL locally; `cli.py` is READ-ONLY reference context for this ticket (find
  its call sites, but it is not in `owns` — if it genuinely needs an edit, stop and flag
  rather than touching a file outside scope). No behavior change to any provider's actual
  resolved URL — this is a dedup refactor, not a routing change.
note: Standard review. Wave 2 relative to PROVIDER-PROBE-FIX (see real-dep above) — the
  fleet auto-claims this once PROVIDER-PROBE-FIX merges+done.sh.
