# F29-REGISTRY-SLICE — module registry refactor

## Change

Replaced the accretion-prone `if/elif` module wiring in `gateway.py` and
`proxy_server.py` with a single declarative `_MODULE_SPECS` table so that
adding a new Smart-Routing module = 1 spec row + 1 module file, editing
ZERO god-files.

### Specifics
- Added `ModuleSpec` dataclass and `_MODULE_SPECS` list in `gateway.py` —
  the single source of truth for every Smart-Routing module (name, config
  file, factory callable, opt-in flag).
- Collapsed `_module_inst`'s 12-branch `if`/`elif` ladder into a loop over
  `_MODULE_SPECS`.
- Replaced `GatewayConfig`'s ~15 optional module fields (`semantic_cache`,
  `guardrails`, `spend_limiter`, etc.) with a single `modules: dict[str,Any]`
  field. Backward-compat `cfg.guardrails` etc. resolve via `__getattr__`.
- `load_config` populates the modules dict via a loop — no per-module wiring.
- `build_server` passes `modules=cfg.modules` generically instead of ~12
  individual kwargs.
- `GatewayProxyServer.__init__` accepts `modules=` dict, merges old-style
  kwargs, stores `self.modules`, and sets backward-compat direct attributes
  for forwarder.py access (`srv.guardrails`, etc.).

### Backward compatibility
- `cfg.semantic_cache`, `cfg.spend_limiter`, `cfg.guardrails`, etc. all
  resolve via `__getattr__` on the frozen dataclass.
- `GatewayProxyServer` constructor still accepts old kwargs (`semantic_cache=`,
  `spend_limiter=`, etc.) and merges them into `self.modules`.
- All 12 known module attrs are set on the server instance for direct access.
- Public import surface unchanged (imports from `charon.gateway` +
  `charon.proxy_server` resolve identically).

### Test coverage
- `tests/test_module_registry.py` (12 tests): FAIL-ON-REVERT — verifies the
  loop picks up new modules, opt-in gating, `GatewayConfig` backward compat,
  `load_config` population, `build_server` forwarding, and `GatewayProxyServer`
  kwarg backward compat.
- All pre-existing gateway and proxy_server tests pass.

### Reviewer notes
- The `_mod_param_names` tuple in `GatewayProxyServer.__init__` is the set of
  known backward-compat attr names. It intentionally mirrors `_MODULE_SPECS`
  but is kept local to avoid a cross-module import dependency.
- `__getattr__` on `GatewayConfig` does a linear scan over `_MODULE_SPECS`
  (12 entries); this is construction-time cost only and inconsequential.
- `test_failover_chain_check_warns_when_no_pools_or_fallback` was already
  failing pre-change (environment-dependent — it tries `load_fallback_providers()`
  from the default config dir).
