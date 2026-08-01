repo: charon
tier: strong
priority: 2
difficulty: 1
work_class: tests
branch: fix/module-registry-drift-guard
owns: tests/test_module_registry_drift.py
serial_justified: A single drift-guard test; nothing to split.
substrate: N/A
substrate-novel: |
  Nothing external applies. This asserts an invariant between two artefacts INSIDE one of our own
  functions — a hardcoded name tuple and that function's own signature. No linter models
  "this string list must equal that parameter list": ruff/vulture/deadcode all see two valid
  constructs. Verified 2026-08-01 by enumerating ruff's full 59-family surface and deadcode's
  option/class surface — neither has a rule for it.
depends_on:
note: |
  FOUND 2026-08-01 while chasing vulture's five 100%-confidence "unused variable" hits in
  `src/charon/proxy_server.py` (virtual_key_manager, speculative_executor, session_affinity,
  observability, consensus_router).

  VERDICT ON THOSE: FALSE POSITIVES, not inert features. All five ARE consumed — via a
  `locals()`-based merge loop at proxy_server.py:559-568 that static analysis cannot follow:

      _mod_param_names = ("guardrails", "semantic_cache", ..., "policy_router")
      for _mn in _mod_param_names:
          _mv = locals().get(_mn)
          if _mv is not None:
              self.modules[_mn] = _mv

  Worth recording in its own right: vulture's HIGHEST-confidence tier (100%) produced five false
  positives here, while the case that actually mattered (src/charon/litellm_plane, zero production
  importers) sits in its LOWEST tier (60%). Confidence measures provability, not importance, and is
  not a quality ordering.

  THE REAL DEFECT IS LATENT, NOT LIVE. Checked today: the tuple and the signature currently MATCH
  exactly — no drift right now, and `locals()` at :566 is the ONLY such lookup in src/. But the
  coupling is invisible to every tool and to review:
    * rename a parameter and it silently stops merging — that module becomes permanently None,
      with NO error, NO type failure, NO test failure;
    * add a module parameter and forget the tuple, and passing that kwarg is silently ignored —
      the feature looks configurable and does nothing.
  That second shape is precisely the built-but-inert class this rig keeps paying for, pre-armed.
accept: |
  - A test asserting `_mod_param_names` exactly equals the set of module parameters in
    `_ProxyServer.__init__`'s signature — fails on EITHER direction of drift (name in the tuple
    but not a parameter; module parameter absent from the tuple).
  - Derive both sides programmatically (`inspect.signature` + reading the tuple). Do NOT hardcode a
    third copy of the list — that would add another artefact to drift.
  - Explicitly exclude the known non-module params: `modules`, `balance_tracker`, `latency_tracker`
    (separate concerns, deliberately not registry entries) — and assert THAT exclusion list too, so
    a future module param cannot be quietly parked there.
  - fail-on-revert: rename one parameter without touching the tuple -> test RED. Report both counts.
  - No production behaviour change. This ticket adds a guard only; if the fragile pattern is to be
    replaced outright (explicit dict instead of `locals()`), that is a separate ticket with its own
    review — do not fold it in here.

## Dependencies & Sequence

- **depends_on: (none).** Test-only, additive.
- **Sequence: whenever.** Nothing is broken today; this stops a silent breakage later.
- **Blocks / unblocks:** nothing.
- **owns-collision:** none — new test file.
