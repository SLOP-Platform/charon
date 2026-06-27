## DEP1 — httpx declared as dev test dependency

**What:** `httpx` was not listed in `pyproject.toml`, so `starlette.testclient` (used via
`fastapi.testclient.TestClient`) raised a `RuntimeError` on clean runner installs.

**Fix:**
- `pyproject.toml` `[dev]` extra: added `httpx>=0.27` (test-only; not a runtime dep).
- `tests/test_service_api.py`: added `pytest.importorskip("httpx")` beside the existing
  `pytest.importorskip("fastapi")` in the three `TestClient`-using tests, so a bare
  install skips cleanly instead of erroring.

**Gate:** 536 passed, ruff/mypy/check_boundary/check_version all green.

**Scope:** only `pyproject.toml` and `tests/test_service_api.py` touched (plus this fragment).
