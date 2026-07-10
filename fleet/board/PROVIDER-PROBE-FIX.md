tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: fix/provider-probe-validation
depends_on: RESPONSE-ADAPTER-UNIVERSAL
real-dep: RESPONSE-ADAPTER-UNIVERSAL shared-file hand-off — that ticket is a live (not-done)
  owner of the SAME gateway.py and providers.py this ticket edits (plumbing an adapter key
  through ProviderPreset/gateway routing). Serialize behind it rather than run as a
  concurrent second writer of either file; rebase onto its merge before starting.
owns: src/charon/gateway.py, src/charon/config.py, src/charon/providers.py, tests/test_config.py
accept: PYTHONPATH=src python3 -m pytest tests/test_config.py tests/test_gateway.py tests/test_providers.py -q
prompt: /home/stack/charon-private/fleet/board/briefs/PROVIDER-PROBE-FIX.md
scope: Fragility finding #4. `config.validate_provider_key` (config.py:448-508) probes a
  provider with `POST /chat/completions {"model": "."}` as its universal-fallback check.
  Many providers correctly 400 on an unknown model id even with a fully valid key/base, and
  the `except urllib.error.HTTPError` branch (config.py:499-502) treats ANY non-401/403 HTTP
  error as `valid: False` WITHOUT checking whether the earlier `/models` probe (config.py:
  469-482) already proved the key works — so a valid key + valid base gets rejected and the
  operator is pushed toward an unsafe live bypass. Fix: treat a successful authenticated
  `GET /models` (models_count > 0 or a clean 200) as sufficient validation on its own; only
  fall through to the chat probe when `/models` is unreachable/inconclusive, and when it does
  run, pick a real model id from the `/models` response instead of `"."`. Add an explicit
  `skip_probe` path (gateway.py's `providers` action + config.validate_provider_key caller)
  for operators with token-gated/limited-access keys who need to add a provider without any
  live probe. Keep the existing SSRF guard (link-local/metadata host refusal) and the
  no-redirect opener unchanged — this is a validation-logic fix, not a security-boundary
  change.
note: Standard review. Sequenced behind RESPONSE-ADAPTER-UNIVERSAL (see real-dep above),
  not because of any functional coupling — purely to avoid two concurrent writers of
  gateway.py/providers.py. Fleet auto-claims once that ticket merges+done.sh.
