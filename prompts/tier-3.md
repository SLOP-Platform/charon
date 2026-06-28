Add the `charon tier` CLI — the fleet's entrypoints into the tier config. Canonical tier for
this ticket: **med** (mapped to fleet `sonnet`). Depends on TIER-1 (merged): `config.py`
exposes `load_tiers`/`set_tiers`/`resolve_tier`/`tier_members`/`tier_rank`. Read
`/home/stack/charon-private/fleet/DTC-tier-abstraction.md` §"Where the mapping lives + the
resolution contract", §"Fleet consumption", and §"Migration path" FIRST, plus the existing
`src/charon/cli.py` subcommand structure.

GOAL: `charon tier init|set|list|ranks|resolve` — `init` seeds backward-compat tiers;
`resolve --executor anthropic` and `ranks` are the fleet entrypoints.

DESIGN ANCHORS (cite in your review note):
- `tier init` writes `tiers.json` with `order=[low,med,high]`, the legacy `aliases`
  (`opus→high sonnet→med haiku→low` + `frontier/strong/economy`), and seeds each tier's
  `members` with the single matching Anthropic model so DAY-ONE == TODAY.
- `tier ranks` prints canonical + alias rows for the fleet to parse ONCE before `flock`,
  e.g. lines `low 1` / `med 2` / `high 3` / `opus 3` … (canonical AND aliases). This is the
  exact contract `claim.sh` (TIER-5) consumes; legacy fallback when absent is the fleet's job.
- `tier resolve <tier> --executor anthropic` returns the CHEAPEST live tier member whose
  provider is Anthropic-API-runnable (so `claude -p` can execute it) — the name lookup
  `fleet-droid.sh` (TIER-6) uses; print just the concrete model name on stdout.
- `tier set` edits `members`/`aliases`/`order` via `config.set_tiers` (atomic). `tier list`
  is human-readable.
- All commands degrade gracefully: absent `tiers.json` → legacy behavior; callers fall back.

BUILD:
1. src/charon/cli.py — ADD a new `tier` subcommand block (init/set/list/ranks/resolve) wired
   to TIER-1's config API. Keep output machine-parseable for `ranks`/`resolve` (the fleet
   greps stdout; non-zero exit on failure so `||` fallbacks fire).
2. tests/test_cli_tier.py — proven-red: `init` seeds order+aliases+Anthropic members;
   `ranks` emits canonical+alias rank rows; `resolve --executor anthropic` returns the
   cheapest Anthropic-runnable member; `set`/`list` round-trip; absent-config exit codes let
   callers fall back.

CONSTRAINTS: own ONLY the files in your board ticket's `owns:` line
(src/charon/cli.py, tests/test_cli_tier.py) — nothing else. cli.py already exists: EDIT it.
Import `config` (TIER-1); do NOT edit config.py. Same wave as TIER-2 (disjoint files) — do
NOT touch gateway.py. If your work needs a file outside `owns:`, STOP and run release.sh with
a one-line reason. Stdlib-only core. Gate green every commit (pytest, ruff, mypy src tests,
check_boundary, check_version). No secrets. Conventional commits. Write your review note as
`docs/review-log/TIER-3.md` (NEVER the shared `docs/REVIEW-LOG.md`). Commit ALL work on your
branch and STOP — do NOT push, do NOT open a PR, do NOT run submit.sh; the launcher publishes
after you exit.
