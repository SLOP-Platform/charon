Fix a FALSE-POSITIVE in the engine-stdlib-only boundary scan added by E0
(tools/check_boundary.py). It currently flags RELATIVE imports inside
src/charon/engine/ — e.g. `from .board import X`, `from ..ledger import Y` — as
"engine-stdlib-only" violations. Relative imports are intra-`charon` and MUST be allowed
(they are the repo's standard style — see coordinator.py `from .ledger import`).

FIX (tools/check_boundary.py): in the engine scan, treat any `ImportFrom` with `level >= 1`
(a relative import) as charon-internal → ALLOWED. Only flag ABSOLUTE imports whose
top-level package is neither stdlib nor `charon`. Genuine third-party absolute imports
(e.g. `import requests`) must STILL fail. The transitive `sys.modules` gateway test stays
as-is.

Add a regression test in tests/test_boundary.py: an engine-style file using
`from ..ledger import X` PASSES; one using `import requests` FAILS.

CONSTRAINTS: own ONLY tools/check_boundary.py, tests/test_boundary.py. Gate green every
commit (pytest, ruff check, mypy src tests, python3 tools/check_boundary.py src,
python3 tools/check_version.py). Stdlib-only. No secrets. Conventional commits. Open a
DRAFT PR base=master; do NOT merge. (This unblocks E1, whose code is correct.)
