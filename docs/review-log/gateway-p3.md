## 2026-06-26 — Gateway P3: provider registry + presets

- **Change under review:** `src/charon/providers.py` (preset table + `resolve`) and
  gateway config support for a `provider` reference on a model.
- **Abstraction:** a *provider* groups `base_url` + `key_env` + quirks
  (`strip_v1`, `downgrade_prone`); a model references a provider + `upstream_model`
  instead of repeating the base URL. `UpstreamRoute` gains an optional `strip_v1`
  quirk (per-provider; None → server default). Presets:
  `opencode-go`, `openrouter`, `nanogpt`, `zai`, `lmstudio`, `jan`, `ollama`,
  `local`. Direct `upstream_base` entries (P1/P2) still work — providers are additive.
- **Honesty (work-order rule — don't guess provider quirks):** `openrouter` and
  `opencode-go` bases are verified; **`nanogpt` and `zai` bases are marked UNVERIFIED**
  (no key to live-check) with a note, and every preset is overridable via
  `[providers.<name>]`. OpenRouter free tiers flagged `downgrade_prone` (the P2
  failover guard covers them). No real provider was called — the contract is proven
  against config + the mock-upstream tests.
- **Cost-rank:** unchanged — pools sort free-first/cheapest-first from registry
  metadata (D4), editable per entry.
- **Proofs:** `tests/test_providers.py` — preset resolution, override-over-preset,
  unknown-provider error, `zai` strip_v1 quirk, and a model→provider→route end-to-end
  (base/key/upstream_model/strip_v1 all resolved).
- **Gate:** 132 passed, ruff clean, mypy clean (29 files), boundary OK, version OK.
