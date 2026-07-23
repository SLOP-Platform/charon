repo: charon
tier: frontier
difficulty: 4
work_class: refactor
branch: refactor/f29-config-package
depends_on:
owns: src/charon/config.py, src/charon/config/
accept: |
  F29 slice (b) — config.py -> config/ PACKAGE + FACADE. Design of record: fleet/state/GODFILE-DECOMPOSE-REVIEW.md §2.
  config.py (625 LOC) is ~10 independent stores sharing only `_load`/`_save`. Split into a `config/` package of
  disjoint modules so its 9 owners land on separate files:
  - `config/_store.py` (file primitives _load/_save, config.py:139-191)
  - `config/providers.py` (177-213), `config/models.py` (216-303,513-521), `config/pools.py` (306-314),
    `config/tiers.py` (317-431), `config/autoland.py` (55-136), `config/sandbox.py` (25-52),
    `config/fallback.py` (524-580), `config/keyprobe.py` (validate_provider_key 444-510), `config/summary.py` (582-625).
  - `config/__init__.py` RE-EXPORTS the current flat surface VERBATIM (same facade proxy_server.py already imports)
    so NO other import breaks. Pure move — import surface preserved, test churn near-zero.
  BACK-COMPAT FACED: `from charon import config; config.<anything>` and `from charon.config import <name>` both keep
  working identically. Keep config.py as a thin re-export shim OR delete it and let config/__init__.py own the name
  (whichever keeps every existing import green — verify by running the FULL suite, not just config tests).
  FAIL-ON-REVERT (add tests/test_config_facade.py): assert every symbol the old flat config.py exported is still
  importable from `charon.config` AND resolves to the same object; revert one module's re-export in __init__.py and
  the test RED (missing symbol). GREEN-IS-NOT-PROOF: the existing config/gateway/providers suites passing is
  necessary but not sufficient for a move this wide — also REQUIRE (1) the facade test above and (2) a reviewer
  diff-read confirming each store moved VERBATIM (no logic edited mid-move) and no symbol was dropped from the facade.
  Run: PYTHONPATH=src python3 -m pytest -q  (FULL suite — a facade break can surface anywhere).
scope: |
  F29 REVISIT — operator-approved SURGICAL un-defer (2026-07-12). Mechanical, low-risk (~half-day). Un-blocks all 9
  config.py owners to land on disjoint files. Pure verbatim move behind a preserved facade — the lowest-regression
  slice after providers-data. [[charon-work-engine-vision]]
ds: FLEET Wave G (F29 surgical). depends_on EMPTY — board-unblocked, launch NOW. Runs CONCURRENTLY with
  F29-REGISTRY-SLICE + F29-PROVIDERS-DATA (disjoint files: config.py only). config.py's other live owners
  (PROVIDER-PROBE-FIX, PROVIDER-URL-HELPER) are sequenced BEHIND this via PROVIDER-PROBE-FIX's depends_on.
  MONOPOLIZES config.py for its wave.
