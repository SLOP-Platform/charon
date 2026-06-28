Fix a latent missing test dependency that fails on a clean machine (found by the CI1 hosted-runner
switch). Canonical tier: **med** (fleet `sonnet`). Tiny, surgical.

THE BUG: `tests/test_service_api.py` constructs starlette's `TestClient`, which requires `httpx`.
But `httpx` is declared NOWHERE in `pyproject.toml` — it was only ambiently present on the
maintainer's box. On a clean runner (a forking contributor, or a fresh dev install), 3 tests
ERROR instead of running: `RuntimeError: The starlette.testclient module requires the httpx
package to be installed.` (`test_post_runs_returns_202_and_queues_job`,
`test_post_runs_without_token_is_refused`, `test_post_runs_503_when_queue_not_configured`).

FIX (own ONLY these two files):
1. `pyproject.toml` — add `httpx` to the **`dev`** optional-dependencies extra (NOT `service`;
   httpx is a TEST-only dep via TestClient, not a runtime dep). Pin a sane lower bound consistent
   with the repo's style (e.g. `httpx>=0.27`). The CI gate installs `.[dev,service]`, so this
   makes the gate green on a clean runner.
2. `tests/test_service_api.py` — add `pytest.importorskip("httpx")` alongside the existing
   `pytest.importorskip("fastapi")` so the module SKIPS cleanly (not ERRORs) when someone runs the
   suite without the dev extra installed. Belt-and-suspenders for the same root cause.

VERIFY: from a clean perspective, `python3 -m pytest tests/test_service_api.py -q` passes (or
skips cleanly if httpx truly absent). Do NOT change product/src code or the service runtime deps.

CONSTRAINTS: own ONLY `pyproject.toml` and `tests/test_service_api.py`. Gate green every commit
(pytest, ruff, mypy src tests, check_boundary, check_version, check_decisions). Note
`check_version.py` may assert version consistency — do NOT bump the version. Conventional commits.
Write your review note as `docs/review-log/DEP1.md`. Commit ALL work on your branch and STOP — do
NOT push / open a PR / run submit.sh; the launcher publishes after you exit. If a fix needs a file
outside the owns list, STOP and run release.sh with a one-line reason.
