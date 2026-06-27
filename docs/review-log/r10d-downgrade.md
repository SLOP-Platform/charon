## 2026-06-26 — R10d downgrade normalization: prefix/normalized compare

- **Change:** `proxy.py` classify path now uses normalized (prefix-stripped) model id comparison to avoid false-positive silent-downgrade flags when an upstream returns a provider-prefixed model id.
- **Rationale:** existing code compared raw model ids, so a bare expected id `"kimi-k2.7-code"` would mismatch an upstream's normalized return `"opencode-go/kimi-k2.7-code"`, incorrectly flagging it as a downgrade. New `_normalize_model_id()` strips the provider prefix before comparing, resolving aliases safely.
- **Tests:** four new assertions in `test_proxy.py` covering: (1) upstream returns with provider prefix (R10d case), (2) normalization still catches real downgrades, (3) both sides prefixed, (4) different prefixes with same base model.
- **Gate:** 174 passed, ruff/mypy/boundary/version OK.
