tier: frontier
difficulty: 5
work_class: refactor
branch: refactor/f29-module-registry
depends_on:
owns: src/charon/gateway.py, src/charon/proxy_server.py
accept: |
  F29 slice (a) — SMART-ROUTING MODULE REGISTRY. Design of record: fleet/state/GODFILE-DECOMPOSE-REVIEW.md §3-4
  + "Highest-leverage single move". Replace the accretion-prone module wiring in gateway.py + proxy_server.py
  with ONE declarative table so a new Smart-Routing module = 1 spec row + 1 module file, editing ZERO god-files.
  DO:
  - Add a declarative `MODULE_SPECS` table (name, json-config file, factory callable, opt-in flag) — the single
    source of truth for every Smart-Routing module.
  - Collapse gateway.py's `_module_inst` if/elif ladder (gateway.py:211-276) into a LOOP over MODULE_SPECS.
  - Replace GatewayConfig's ~15 optional module fields (gateway.py:60-95) with `modules: dict[str,Any]`;
    `build_server` (gateway.py:298-337) passes that dict generically instead of ~20 pass-through kwargs.
  - Collapse GatewayProxyServer.__init__'s ~15 module params/assignments (proxy_server.py:453-782) into the
    SAME registry: `self.modules[...]`. This is the shared-root collision — fix it in ONE place across both files.
  - Do NOT touch proxy_server.py's already-extracted dispatch (console_router/forwarder/proxy_response). Registry only.
  BACK-COMPAT FACED: preserve the current flat public surface / import points so no external caller breaks.
  FAIL-ON-REVERT (add a NEW test, e.g. tests/test_module_registry.py): a test that adds a throw-away spec row +
  stub module file and asserts the gateway builds it with ZERO edits to gateway.py/proxy_server.py bodies (loop
  picks it up); revert the loop→ladder conversion and the test RED (the stub module is not instantiated).
  GREEN-IS-NOT-PROOF: the pre-existing gateway route-build + sort suite passing is NECESSARY but NOT sufficient —
  it is a behavior-preserving refactor, so also REQUIRE (1) the new registry test above and (2) a reviewer diff-read
  confirming every removed field/branch/kwarg/param is reachable ONLY through MODULE_SPECS now (no dead second path,
  no silently-dropped module). proxy_server.py is money-path adjacent → ADVERSARIAL review (regressions hide in the
  __init__ param collapse). Run: PYTHONPATH=src python3 -m pytest tests/test_gateway.py tests/test_module_registry.py -q
scope: |
  F29 REVISIT — operator-approved SURGICAL un-defer (2026-07-12). This is the highest-leverage of the three F29
  slices: ONE table dissolves the collision shared by the two biggest owner clusters (gateway R10/R11/R12/R13 +
  proxy_server R30/R42). Registry slice runs FIRST. The full 4-file split stays deferred; this is registry-only.
  [[charon-work-engine-vision]] Reuse the response_adapters._ADAPTERS registry precedent; consider the KS29
  component-registry-primitive shape (declare → conformance) but do NOT block on it.
ds: FLEET Wave G (F29 surgical). depends_on EMPTY — board-unblocked, launch NOW. Owns gateway.py + proxy_server.py
  (proxy_server.py has zero other live owns-owner; gateway.py's other live owners PRICING-LIMITS-CHECKER +
  PROVIDER-PROBE-FIX are sequenced BEHIND this via PROVIDER-PROBE-FIX's depends_on). Runs CONCURRENTLY with the
  other two F29 slices (F29-CONFIG-PKG / F29-PROVIDERS-DATA) — disjoint files. Registry-first is a staffing
  priority, not a hard dep. MONOPOLIZES gateway.py + proxy_server.py for its wave.
