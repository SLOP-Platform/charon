# PUBLIC-CLEAN-LINT — review fragment

## What was built

**`tools/check_public_clean.py`** — a lint tool that hard-fails (non-zero exit) if tracked
files contain personal/internal patterns:

| Pattern | Description |
|---|---|
| `10\.\d+\.\d+\.\d+` | Internal IP (10.0.0.0/8) | <!-- public-clean: allow — documentation of pattern -->
| `\b4-?lom\b` (case-insensitive) | Hostname "4-lom" | <!-- public-clean: allow — documentation of pattern -->
| `\bcharon-?vm\b` (case-insensitive) | Hostname "charon-vm" | <!-- public-clean: allow — documentation of pattern -->
| `/home/stack` | Home path | <!-- public-clean: allow — documentation of pattern -->
| `charon-private` | Build-rig repo name | <!-- public-clean: allow — documentation of pattern -->
| `\b[0-9a-fA-F]{40,}\b` | Hex token shape (>=40 chars) |

**Waiver mechanism:** any line containing a matched pattern is skipped if the **same**
line also contains `public-clean: allow` (any comment syntax). GitHub action pinned
commit SHAs in CI workflows use this waiver.

**Exception config:** `tools/.public-clean-exceptions.json` maps file paths to
sets of exact line CONTENT (not line numbers) for content that cannot host an
inline waiver (e.g. JSON). Content-keying means an unrelated insertion/deletion
elsewhere in the file never shifts a waiver onto the wrong line; if the
exempted content itself is edited, the exemption stops matching and the line
is re-evaluated normally (fail-safe, not fail-silent). A regression test
(`test_shipped_exceptions_match_tracked_file_content`) asserts every shipped
entry is still verbatim-present, catching stale/drifted exemptions early.

**Tests** (`tests/test_public_clean.py`, 20 tests):
- Each pattern category has a positive detection test
- Waiver mechanism: inline waiver works, waiver on a different line does not,
  `public-clean: skip` does not waive (only `allow`)
- Exception config: per-line suppression, only suppresses specific lines
- Red-proof: planted leaks are flagged; green-proof: clean files are clean
- Edge cases: binary files skipped, one violation per line, `check_paths` aggregation

**CI wiring:** added `python3 tools/check_public_clean.py` step to `ci.yml` and
`release.yml` right after the boundary check.

## Scrubbed files

13 files with `4-lom` / `4-LOM` → `<self-hosted-runner>`: <!-- public-clean: allow — documentation of pattern -->
`.github/actionlint.yaml`, `.github/workflows/{ci,heavy,release,windows-exe}.yml`,
`CONTRIBUTING.md`, `docs/DECISIONS.md`, `docs/adr/0005-gateway-first-charon.md`,
`docs/review-log/{CI1,FB5,TEST-PORT-FLAKE,github-unwind,hygiene-adr0005}.md`

2 files with `charon-vm` → `<self-hosted-dev>`: <!-- public-clean: allow — documentation of pattern -->
`docs/review-log/SETUP-UX-A.md`, `tests/test_setup_ux.py`

7 files with `charon-private` → `<private-rig-repo>`: <!-- public-clean: allow — documentation of pattern -->
`README.md`, `docs/DECISIONS.md`, `docs/adr/0010-native-work-engine-substrate.md`,
`docs/review-log/{DS-PLAN-REVIEW,E7,TIER-5,TIER-6}.md`

3 files with `/home/stack` → `<workspace>`: <!-- public-clean: allow — documentation of pattern -->
`docs/review-log/{DS-PLAN-REVIEW,TIER-5,TIER-6}.md`

## Cross-repo recommendation

The same `check_public_clean.py` can be shared between repos. The pattern list
should be a config file that both repos reference. A pre-commit hook that calls
`python3 tools/check_public_clean.py` would be the simplest integration.
