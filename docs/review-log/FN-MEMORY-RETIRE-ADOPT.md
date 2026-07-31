# FN-MEMORY-RETIRE-ADOPT — review log

## Scope
Owner-verified: all changed files are in `owns:` (`fleet/memory/`, `fleet/research.sh`).

## RETIRE (already done in origin/master)

The inert hand-rolled memory store (FN1/FN2/FN3) was deleted in commit `64cee96`,
already merged into origin/master before this branch was created. Verified:
- `fleet/memory/` directory absent from disk and from origin/master tree.
- fleet/tests/curate.test.sh and fleet/tests/test_bitemporal.py absent.
- ON-DEMAND-TOOL-LEDGER.tsv: no dangling refs to session-preamble.sh or migrate.py.
- fleet/research.sh: no memory/markdown pointers (already purged).
- fleet/tests/research.test.sh: fixture already updated.

## ADOPT (this commit)

Two thin wrapper scripts added under fleet/memory/:

### migrate-frontmatter.sh
One-shot migration over the REAL basic-memory vault. Uses `basic-memory tool
search-notes` + `edit-note` to add tags and last_referenced frontmatter where
missing. Idempotent; dry-run with `--dry-run`.

### curation.sh
Approval-gated curation job. Dry-run by default (`--apply` to act). Detects:
1. Orphan notes (via `basic-memory orphans`)
2. Decay candidates (notes untouched > 90d)
3. Duplicate titles (via search-notes metadata comparison)

Both scripts use basic-memory CLI exclusively — no hand-rolled search/decay
logic, preserving the FAIL-ON-REVERT guard.

## ROUTER-LEDGER-DECAY
The bitemporal.py gap-B2 ledger-decay intent is preserved as
fleet/board/ROUTER-LEDGER-DECAY.md (router-side, build-when-needed).

## Gate
`bash fleet/checks/rig-ci-scope.sh tests` GREEN (no memory suite in CI_SUITES).
basic-memory is installed and reachable on this system.
