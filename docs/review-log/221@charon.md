# Review: 221@charon
**PR:** refactor: decompose proxy_server.py into proxy_session and proxy_routes
**URL:** https://github.com/SLOP-Platform/charon/pull/221
**Date:** 2026-08-02T15:23:13Z
**Reviewer:** reviewer-tab-2541479
**Author:** charon-bot

## Verdict
NEEDS-REVISION

## Findings
- The arch gate is not updated for the two new gateway-boundary modules: `tools/check_arch.py::_ENGINE_FORBIDDEN` (lines 38-43) enumerates the proxy_server decompose modules (`proxy_console_assets`, `proxy_response`, `console_router`, `forwarder`) but omits `proxy_routes` and `proxy_session`. Empirically verified: an `engine/` module that does `import charon.proxy_routes` or `import charon.proxy_session` produces ZERO `engine→forbidden` violations — the ADR-0010 D2 anti-dilution boundary that `test_check_arch.py:311` explicitly extends to decompose modules is silently widened. The review-log's gate list (`pytest`, `ruff`, `mypy`, `check_boundary`, `check_version`) conspicuously omits `check_arch.py`, which is exactly why this regression passed. One-line fix: add both modules to `_ENGINE_FORBIDDEN`.
- Facade re-export is asymmetric: `proxy_server.py` re-exports `_b64url` (with a `# noqa: F401` note for `test_gateway_gui_auth`) but NOT `_b64url_decode` (verified `hasattr(charon.proxy_server, "_b64url_decode") is False`), contradicting the review-log's stated invariant that every `from charon.proxy_server import ...` site resolves unchanged. No current consumer imports `_b64url_decode` from the facade, so nothing breaks today — but it is the decoder the entire session pipeline relies on, and any future site doing `from charon.proxy_server import _b64url_decode` will NameError. Add it to the re-export list (and ideally assert the full session surface re-exports in a test, which would have caught this). The verbatim extraction itself, the HMAC/session logic, `label` safety, and all 33+73 runtime tests are confirmed correct.

## Fail-on-revert check
A revert restores the monolithic `proxy_server.py` but can never remove or detect the stale `_ENGINE_FORBIDDEN` gap (the module-registration fix was never committed), so the boundary hole silently persists after revert.

## Status
Pending Manager dispensation
