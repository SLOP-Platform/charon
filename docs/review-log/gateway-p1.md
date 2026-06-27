## 2026-06-26 — Gateway P1: `charon gateway` standalone command

- **Change under review:** standalone gateway mode on the existing
  `GatewayProxyServer` — `src/charon/gateway.py` (config + run), a `gateway`
  subcommand in `cli.py`, `src/charon/netutil.py` (shared `is_loopback`), and
  additive `token`/`model_ids` support on `GatewayProxyServer`.
- **Scope (ADR-0005 P1):** `/v1/chat/completions` (stream + non-stream, already in
  the proxy) + aggregated `/v1/models`; config from `charon.toml` **or**
  `.charon/models.json` (one schema, D6/R5); loopback default + optional bearer
  token. **Failover is P2** — P1 forwards each model to its one configured upstream.
- **Security (D5/R8):** `gateway.run` refuses a non-loopback bind without a token
  (mirrors the service `__main__` guard, now factored into `netutil.is_loopback`).
  Token is constant-time compared (`hmac.compare_digest`), accepted via `Authorization`
  or `?token=`. `/v1/models` is field-allowlisted to ids — no `key_env`/`upstream_base`
  leak (R4). Provider keys stay server-side (existing invariant).
- **Back-compat:** `token`/`model_ids` default to `None`, so the bare proxy and all
  existing proxy tests are unchanged.
- **Proofs:** `tests/test_gateway.py` — config from TOML (key-env resolution, arg
  overrides, acp-only entries skipped) + from `models.json`; `/v1/models` + token gate
  (header, `?token=`, wrong/absent → 401); end-to-end forward through a mock upstream;
  loopback guard refuses `0.0.0.0` untokened. **Live-smoked:** `charon gateway` started
  on `:8099`, `GET /v1/models` returned the aggregated list.
- **Gate:** 120 passed, ruff clean, mypy clean (28 files), boundary OK, version OK.
- **Adversarial review:** security-critical surfaces (token gate, loopback guard,
  models allowlist) sent to an independent reviewer (see next entry / verdict).
