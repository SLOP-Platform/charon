# BENCH-OOB-GRADING — Out-of-band grading verification (pivot #26, P0 integrity)

**Date:** 2026-07-23  
**Verdict:** LAND  
**Author:** plo-koon (build droid, BENCH-OOB-GRADING ticket)

## Summary

Verified the out-of-band grading subsystem — 13 graders + daemon deployed & live via
`bench-grader-setup.sh` 2026-07-16.  Source files landed in the charon public repo under
`benchmark/`.  The daemon (`benchmark/grader-daemon.py`, 992 lines) + all 13 section/preflight
graders + `grade_state.py` (run-state management with bench-run-collision hardening) are the
canonical source of the deployed system.

## Three invariants: enforced design

| Invariant | Enforcement |
|---|---|
| **1. Answer key out of subject's reach** | Graders live in `benchmark/graders/` (source) / `/home/bench-grader/keys/` (deployed, mode 0700). The agent's bench.sh never reads these — it enqueues requests to the daemon spool. |
| **2. Grading not self-driven** | `bench.sh grade` writes a grading request to `/var/lib/bench-grader/spool/req/` (mode 1733: write-only, sticky) and polls `spool/res/` for the daemon's verdict. The daemon — a SEPARATE process running as the `bench-grader` unix user — snapshots the worktree, runs the grader, and writes the result. |
| **3. No self-report** | The daemon is the sole ledger writer (`_append_to_ledger` + `_append_to_scorecard`). bench.sh NO LONGER calls `model-scorecard.sh append` — it reads the daemon's result JSON but never touches the ledger. |

## bench.sh modification (OOB grading)

`do_grade()` replaced direct grader invocation + scorecard append with:
1. Write `{run_id, model, unit_id, kind, worktree, stage}` to daemon spool req/
2. Poll `res/<run_id>.json` with configurable timeout (default 600s)
3. Parse the daemon's result JSON for score, verdict, gate, corrections, finalize
4. Display result and advance to next section (daemon handles ledger append)

Configurable via env vars: `BENCH_SPOOL_REQ`, `BENCH_SPOOL_RES`, `BENCH_SPOOL_POLL_TIMEOUT`.

## Security hardening (already in deployed daemon)

- **F1 sandbox confinement** (`_confine` / `SandboxError`): all attacker-controlled `run_id` paths
  resolved under `WORK_DIR`; `../` traversal and absolute paths rejected before any filesystem
  operation — prevents path-traversal rmtree or write outside the spool.
- **FLAW-3 enum validation** (`_VALID_CAPTURE_VERDICTS` / `_VALID_CAPTURE_GATES`): capture requests
  validated against allowed enums; unpaired FINALs require provenance anchor via
  `state/model-used/<ref>`.
- **STAGE-DEMUX** (`_resolve_trust_stage`): column-16 trust axis (provisional/active) resolved
  from request's `trust_stage` (canonical) or `stage` (legacy alias) field — makes the trust
  axis expressible end-to-end.
- **Versioned scorecard artifact** (`scorecard.v{n}.json`): append-only frozen artifacts,
  never imported by product code. Consumers read frozen artifacts only (freeze-ring pattern).

## Cross-ticket dependencies (files referenced but owned by other tickets)

These files are referenced by owned files but are NOT created here (they belong to other tickets,
primarily BENCH-PROVISIONAL-SCORING #20 and BENCH-REGROUND-LIVE):

- `benchmark/lib/sections.sh` — sourced by bench.sh for section metadata/fixtures
- `benchmark/lib/detect_model.py` — model auto-detection (bench-model-misdetect fix)
- `benchmark/lib/tier_chart.py` — tier chart rendering
- `benchmark/lib/charon_cost.py` — gateway cost attribution (imported by grade_state.py)

## Verification status

- **Daemon deployed:** live via `bench-grader-setup.sh` 2026-07-16
- **Source files:** landed in charon repo under `benchmark/`
- **Gate integrity:** F1 (path traversal), FLAW-3 (enum validation), STAGE-DEMUX (trust axis)
  all present in deployed daemon
- **Human sign-off criteria:** addressed by design — agent can't read graders (permission 0700),
  can't write ledger (daemon is sole writer), re-grading is deterministic (same snapshot,
  same grader)

## Remaining (post-land)

- STAGE-FAILCLOSED default flip (separate ticket)
- Cross-ticket dependency files to be created by their owning tickets
