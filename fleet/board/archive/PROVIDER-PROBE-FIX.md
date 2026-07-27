repo: charon
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: fix/provider-probe-validation
depends_on: RESPONSE-ADAPTER-UNIVERSAL, F29-REGISTRY-SLICE, F29-CONFIG-PKG, F29-PROVIDERS-DATA
real-dep: RESPONSE-ADAPTER-UNIVERSAL shared-file hand-off — that ticket is a live (not-done)
  owner of the SAME gateway.py and providers.py this ticket edits (plumbing an adapter key
  through ProviderPreset/gateway routing). Serialize behind it rather than run as a
  concurrent second writer of either file; rebase onto its merge before starting.
real-dep: F29-REGISTRY-SLICE / F29-CONFIG-PKG / F29-PROVIDERS-DATA god-file hand-off (2026-07-12
  F29 surgical un-defer) — those three decompose gateway.py/proxy_server.py, config.py, and
  providers.py respectively, the SAME files this ticket edits. This ticket (and its downstream
  chain PROVIDER-URL-HELPER + PRICING-LIMITS-CHECKER, which depend_on it) is BLOCKED behind the
  F29 decompose so it edits the post-split modules, never as a concurrent second writer of the
  god-files. Rebase onto all three F29 merges before starting; expect the edit sites to have moved
  into config/*.py and provider_presets/*.py.
owns: src/charon/config/keyprobe.py, src/charon/gateway.py, tests/test_config.py
serial_justified: one coherent validation-logic fix — the `skip_probe` escape hatch threads
  through both config/keyprobe.py (the probe logic) and gateway.py (the `providers` action caller),
  and the /models-probe-sufficiency change is a single behavior; splitting into per-file sub-tickets
  would fragment one atomic fix + its shared test, creating worse cross-ticket coupling than the
  serial cost. Not splittable.
verified: 2026-07-13 (board-reconcile pass) — F29-CONFIG-PKG already split config.py, so the bug
  MOVED: it is now at `src/charon/config/keyprobe.py:69-72` — the `except urllib.error.HTTPError`
  branch rejects any non-401/403 without checking the earlier successful `/models` probe (the
  `models_count` fallback exists ONLY in the generic `except Exception` branch, lines 73-78). The
  `skip_probe` escape hatch is entirely ABSENT (`grep -rn skip_probe src/ tests/` = 0 hits). Fix
  targets keyprobe.py, not the stale config.py line refs below. STILL A LIVE SG BUG (breaks provider
  validation) — priority per operator "fix SG-work issues, don't delay."
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
