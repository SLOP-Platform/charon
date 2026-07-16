# MEMORY-WIRE-RETRIEVAL — Review Log

## Decision: WIRE the live store to point-of-need (ends MEMORY.md hand-compaction)

The fleet/memory store (basic-memory adopt + bitemporal decay + curate, PRs #49-51)
is **live** but was **not wired** — sessions still loaded MEMORY.md wholesale. This
ticket lands the wiring called out in MEMORY-TOOL-EVAL.md migration steps 2-4:
the SessionStart hook payload is now `pin.md` (1.5KB) + a one-line pointer to
`fleet/memory/search.py "<topic>"`. The full ~92-file markdown/ set is no
longer loaded into session context; everything else is pulled on demand.

## What changed

- **`fleet/memory/session-preamble.sh`** (new, ~75 lines)
  - Default mode: prints PINNED core + point-of-need pointer. 1937 bytes total
    (1537 pin + ~400 pointer) vs the 187,813-byte wholesale dump → **97x smaller
    session-start payload**.
  - `--check` mode: self-test for CI / `tests/test_wire.sh` (asserts
    pin/markdown ratio + failover probe returns ranked results).
  - Contains a MANAGER-WIRING block documenting the two integration
    follow-ups the manager owns (SessionStart hook swap in
    `~/.claude/settings.json`; weekly `curate.sh --apply` schedule).

- **`fleet/memory/load.sh`** (extended — was 42 lines, now ~65)
  - Default mode unchanged: prints PINNED core + pointer. (Already correct.)
  - **NEW `--query <topic>` and `--json <topic>` modes**: wrap
    `fleet/memory/search.py` so `load.sh` is the canonical point-of-need
    entry. Reuse-check and tool-inventory both point here.
  - `--full` debug mode preserved.

- **`fleet/memory/tests/test_wire.sh`** (new, ~120 lines, 17 assertions)
  - `(a)` preamble is small (<5000 bytes, <50% of wholesale dump)
  - `(b)` preamble contains PINNED CORE + `search.py` pointer
  - `(c)` `load.sh` default = pinned only (no `FULL MEMORY SET` marker)
  - `(d)` `load.sh --query` wraps search.py (human-readable output)
  - `(e)` `load.sh --json` wraps search.py (valid JSON list)
  - `(f)` search.py direct returns ranked failover results, top hit =
    `charon-failover-bug-and-tier-fallback.md`
  - `(g)` `session-preamble.sh --check` exits 0, reports ratio + search count

## Why this design

- **Manager owns the seam, droid owns the repo.** The actual SessionStart
  hook swap lives in `~/.claude/settings.json` (operator home — never in
  the repo, never another droid's `owns:`). The MANAGER-WIRING block in
  `session-preamble.sh` makes the two follow-up commands exact + explicit
  so a future operator session can apply them as a one-line edit.
- **load.sh is the canonical entry, not search.py.** `load.sh` already
  exists and the existing tool-inventory/reuse-check conventions route
  through it. Wrapping search.py keeps a single seam for "ask the memory
  store" — sessions don't need to know whether it's `load.sh` or
  `search.py` underneath.
- **Two-mode test strategy.** `test_wire.sh` is a bash test (the
  contract is shell-level — bytes, grep, exit codes) so it can be run
  in isolation and as part of the fleet's bash-test sweep. The
  existing `test_memory_store.py` keeps the Python-level invariants
  (frontmatter, JSON shape, file count) — the two test files do not
  overlap and both must pass.

## Tradeoffs / known limitations

- **No `pip install -e`:** per privileged-core rules, this ticket added
  no new dependencies. The wiring is pure bash + stdlib python3 — keeps
  the `src/` core stdlib-only.
- **Pre-existing reds NOT introduced by this ticket:** pytest baseline
  on origin/master = 1 failed / 74 passed (the `rig-meta` work-class
  rejection in `fleet/capture/enqueue-capture.sh`); ruff baseline = 18
  errors (all in `fleet/benchmark/`); mypy baseline = the `__main__`
  duplicate-module config error. All three match the branch baseline
  before my changes — confirmed via `git stash` baseline diff.
- **Manager-wiring follow-ups are explicit and mechanical.** The
  MANAGER-WIRING block in `session-preamble.sh` names the exact two
  edits (1) `~/.claude/settings.json` SessionStart hook swap and (2)
  weekly `curate.sh --apply` cron. Neither is implemented here by
  design — those belong to the operator home + scheduler, not this
  ticket's `owns:`.

## Gate result

- `bash fleet/memory/tests/test_wire.sh` → **17/17 PASS**
- `pytest -q fleet/memory/tests/` → **11/11 PASS**
- `pytest -q` (full) → 74 passed, 1 pre-existing red (unrelated)
- `ruff check` → 18 pre-existing errors, 0 new
- `mypy src tests` → 1 pre-existing config error, 0 new
- Scope self-check (`git diff origin/master...HEAD` + untracked) →
  only files in `owns:` + this review-log fragment.
