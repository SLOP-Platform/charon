# GATE-INTEGRITY-A — review log

Ticket: GATE-INTEGRITY-A (sub-A: inert side). Branch: `feat/gate-integrity-inert`.
Owns: `tools/check_inert_code.py`, `tools/inert-code-disposition.json`, `tools/inert_to_graph.py`.
Disjoint from GATE-INTEGRITY-B (which owns `gate_runner.py` + `check_gate_registry.py`).

## Spec reference

`fleet/state/S1-GATE-INTEGRITY-SPEC.md` §2a / §3 / §4.
Read before coding.

## What changed

### §3 — `_EXCLUDE_DIRS` monkeypatch (the determinism fix)

Root cause: the vendored detector (`tools/_vendor/ksf_inert_code.py`) hard-codes a
scan-root as `db_path.parent.parent` and uses `_EXCLUDE_DIRS` to prune what
`rglob("*.py")` walks. The shipped set has no entry for `.claude`, so on a live
dev box with `~/.claude/worktrees/agent-X/` (full copies of `src/`, `tests/`,
`tools/`, `packaging/` created/torn down by Claude Code background-agent
sessions) the AST call graph gets polluted with namespaced copies of every
real module — e.g. `.claude.worktrees.agent-X.src.charon.quota.QuotaTracker`.
Reachability becomes run-dependent on whichever in-flight (uncommitted,
being-edited-by-another-agent) symbols the worktree happens to contain at
scan time, producing the 43-52 dead-symbol band the task brief reported.

The vendored file's own header forbids hand-edits ("do not hand-edit the
logic below; re-copy from KSF"), so the fix is a monkeypatch from the
Charon-owned adapter (`tools/check_inert_code.py`) right after the import.
The vendored module's constant is mutated in place; constant-name is the
re-vendor merge-survival hook.

Verified empirically: pre-fix in `/tmp/opencode/claude-pollution` (a tree
that mirrors the launcher's environment with one simulated worktree file),
the detector scans it; post-fix (with the patch applied), `is_excluded_dir`
returns True for the polluted file (confirmed via direct module inspection
in both modes). 3 consecutive `check_inert_code.py` invocations with the
patch and pollution present all report `28 dead symbol(s) found, 28
tracked` — identical to a fresh-clone baseline.

Do NOT also try to add the same exclusion to the vendored file — the
ticket and the file's own contract both forbid that. The upstream KSF
project should pick this up natively in a future re-vendor; the constant
name is the merge hook for that.

### §2a — `tools/inert_to_graph.py` @covers strip

The file is untracked in the main checkout (`git status`: untracked; never
committed in any branch — `git log --all --diff-filter=A -- tools/inert_to_graph.py`
returns empty). It does not exist in a fresh `git clone` of `origin/master`,
so the orphan-covers red it would otherwise produce in
`check_gate_registry.py` is naturally absent from this worktree. No
artifact to strip; the gate already reports "no ORPHAN-COVERS issues"
and `@covers annotations: 13` (down from 14 on the main checkout that
has the stray annotation). The work-spec's other suggested path
(register a gates.json entry for `inert-graph-coupling`) was rejected:
the file is a diagnostic/visualization helper with no invariant/exit-code
contract and is not part of origin/master, so introducing a gates.json
entry would be scope creep. Action: leave the file absent from this branch.

### §4 — disposition file triage

Added 24 new entries to `tools/inert-code-disposition.json` per the spec's
triage table, key-sorted (alpha) for stable diffs. Each entry has a
`{reason, disposition}` pair matching the `_VALID_DISPOSITIONS` schema
(`wire|delete|keep-<why>`). Total entries went from 28 → 52.

Two new disposition tags introduced (both match the schema's `keep-.+`):

- `keep-detector-false-positive-qualified-submodule-call` — for symbols
  reached via `from .pkg import submod; submod.func(...)` patterns where
  the detector's `_resolve_call()` (tools/_vendor/ksf_inert_code.py:283-303)
  builds a malformed candidate name and fails to match. Used for
  `charon.engine.semantic_proof.{IndependenceCertificate, compute_certificate}`.
- `keep-manual-instrumentation` — for ad-hoc calibration harnesses not
  on the hot path. Used for `charon.scanners.benchmark_scanners`.

Existing tags extended: `keep-detector-false-positive-uvicorn-string-load`
(picks up `charon.service.app.RunRequest`), `delete` (5 new
`charon.pricing_limits_checker.*` dataclasses joining the already-condemned
functions in the same module), `keep-pending-wire` (`ReviewerCircuitBreaker`,
`next_entry`, `proxy_excluded_keys`, `QuotaTracker`), `keep-needs-triage`
(`discover_models`, `load_cost_map`), `keep-pending-decision` (3 more
`engine.reconcile.*` symbols joining the already-tracked `ReconcileFinding`),
`wire` (`bootstrap`, `scheduled_refresh` joining the same not-yet-integrated
lifecycle module; `probe_handoff`, `ToolCallRepair`).

## Known spec/contract nuance — read this if you remove any of the 24 new entries

24 of the 52 disposition entries are **stale by the current detector's
standard** — i.e. the detector does NOT currently flag them as dead,
because the spec's listed symbols all have at least one test-file import
edge (`tests/test_*.py`), and the detector explicitly counts test-file
references as production callers (tools/_vendor/ksf_inert_code.py:460-482:
"Also scan test files and .ksf red-proof files for reference edges. They
are real callers; we use their imports/calls to mark production symbols
reachable without flagging test files themselves.").

The spec's stated basis is "zero production callers / zero importers in
src/", which is true — but the detector's policy of counting test imports
as references means none of these symbols are actually flagged today.
The 24 entries are added for **forward-looking disposition tracking**:
they encode the wire/delete decision before the test references are
removed during the eventual wire or delete, so the gate stays green
throughout that transition without requiring a follow-up disposition
audit.

Consequence: `check_inert_code.py` now emits a 24-line "stale disposition
entries" info message to stderr on every run. This is informational
(check_inert_code.py:165-170 — `passed` does not consult the stale set,
and the test suite's `TestCleanCodebase::test_current_codebase_passes`
asserts `undisposed == []` and `passed is True`, neither of which is
affected). It is a quality-of-output regression, not a gate failure.
A future cleanup could distinguish "actively tracked dead" from
"forward-declared future disposition" by adding a third optional
`forward_tracked: true` field to the entry shape; that's a follow-up
ticket, not in scope here.

If you remove any of the 24 entries before the wire/delete actually
happens, the corresponding symbol becomes undisposed dead the moment
its last test-file importer is removed — the gate will fail on that
exact commit, exactly as the spec/ticket intends.

## Verification (all from this worktree, post-change)

- `PYTHONPATH=src python3 tools/check_inert_code.py` × 3 in
  `/tmp/opencode/claude-pollution` (with simulated `.claude/worktrees/`
  pollution) → 3/3 identical (`28 dead symbol(s) found, 28 tracked`).
- `PYTHONPATH=src python3 tools/check_gate_registry.py` → exit 0,
  "check_gate_registry: OK" (no orphan-covers, no @covers annotations
  pointing at unregistered domains).
- `PYTHONPATH=src python3 -m charon.cli gate` → all checks passed
  (ruff/mypy/SLOP-boundary/version/gate-registry/public-clean/no-rig-import/
   check-arch/security-scan/test-patterns/workflow-policy/inert-code).
- `PYTHONPATH=src python3 -m pytest` → 1723 passed, 1 xfailed, 1 xpassed
  in 164s.
- `mypy src tests` → "Success: no issues found in 237 source files".
- `python3 tools/check_boundary.py src` → "boundary OK".
- `python3 tools/check_version.py` → "VERSION DRIFT" warning, but the
  script itself says "Not failing outside CI" so this is informational.

## Pre-existing baseline conditions (not introduced by this change)

- `ruff check` (no path) reports 5 errors, all in
  `tools/_vendor/ksf_inert_code.py` (imports un-sorted, unused
  `typing.Any`, two unused loop variables `alias` and `orig`). These
  are in the vendored file, which is owned by upstream KSF and whose
  own header forbids hand-edits. They are present on `master` (b7aa4c8)
  baseline. This ticket does not address them. `charon gate` itself
  invokes `ruff check src tests` and so does not see them.
- `python3 tools/check_version.py` reports the editable-install drift
  warning. The script's own output says it's informational; no
  behavior change needed.
