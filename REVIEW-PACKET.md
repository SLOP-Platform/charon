# REVIEW PACKET — BENCH-OOB-GRADING #26 (Wave 1)

**Ticket:** BENCH-OOB-GRADING-26  
**Model:** glm-5.2 (deepseek-v4-pro)  
**Branch:** feat/fragility-tickets  
**Date:** 2026-07-10

## Files + line ranges changed

| File | Lines | Change |
|------|-------|--------|
| `fleet/benchmark/grader-daemon.py` | 1–400+ | **NEW** — OOB grader daemon |
| `fleet/benchmark/graders/real.py` | 1–79 | **NEW** — real-task grading module (reds-replay) |
| `fleet/benchmark/scorecard.version` | 1 | **NEW** — scorecard version file (v1) |
| `fleet/benchmark/selftest/test_grader_daemon.py` | 1–200+ | **NEW** — FAIL-ON-REVERT test |
| `fleet/benchmark/RUN-BENCHMARK.md` | 95–125 | **MODIFIED** — daemon trust-boundary doc section appended |

## Root cause / approach

The grading pipeline had **three structural trust defects** (per ADR §1.1):
1. Answer keys readable by the subject (in-repo graders)
2. Grading self-driven (model ran `bench.sh grade` itself)
3. Self-report (model pasted its own tier chart)

**Approach:** Build an out-of-band grader daemon that runs as the dedicated
`bench-grader` user. The daemon:
- Watches `/var/lib/bench-grader/spool/req/` (maildrop dir, mode 1733 — agent can
  write but not list/read)
- Snapshots the agent's worktree into a read-only daemon-private copy
- Grades against private keys in `/home/bench-grader/keys/` (mode 0700)
- Writes results to `spool/res/` for the agent to poll
- Is the **sole writer** of `model-scorecard.tsv` (owned by bench-grader)
- Writes **versioned, append-only** `scorecard.v{n}.json` artifacts
  (RED-TEAM FIX #2 artifact seam)

**RED-TEAM FIX #2 (artifact seam):** The versioned scorecard is NEVER imported
by product code. Consumers read frozen artifacts only. The `.version` file
establishes a monotonically-incrementing version namespace. Each `v{n}` file
is an append-only JSON object with `{version, created, rows: [...]}` — rows
are added never modified.

## FAIL-ON-REVERT test

**Name:** `test_grader_daemon.py` — grader-daemon isolation + versioning

**Exact run command:**
```
python3 fleet/benchmark/selftest/test_grader_daemon.py
```

**What it checks (must go RED if reverted):**
- **Check A (ISOLATION):** `/home/bench-grader/keys/` is permission-denied to
  the `stack` user. Removing the `chmod 0700` / `chown bench-grader` on keys
  makes this test FAIL.
- **Check B (VERSIONING):** `scorecard.version` exists with a positive integer.
  Deleting this file or making it non-numeric → FAIL.
- **Check C (NO-PRODUCT-IMPORT):** No product file under
  `/home/stack/code/charon/` references `scorecard.v`. Adding a product import
  of the scorecard → FAIL (the artifact seam is breached).
- **Check D (DAEMON STRUCTURE):** The daemon source contains the required
  spool paths, versioning references, and the "never modified" contract
  comment. Removing these → FAIL.

## Self-run FULL GATE result

```
CHARON GATE — running all validation checks...
  [ruff] OK
  [mypy] OK
  [SLOP-boundary] OK
  [version] OK
  [gate-registry] OK
  [public-clean] OK
CHARON-GATE: all checks passed
```

## Residual risk + blast radius

1. **No bench.sh integration yet** — the daemon is built but bench.sh still
   grades in-process. The operator must wire bench.sh to drop req JSONs and
   poll res JSONs (step-5 in the ADR). Until then, the daemon watches an
   empty spool. Risk: nil (daemon is idle, no false grades).

2. **Cost attribution degraded** — `grade_state.py record` snapshots gateway
   cost via `charon_cost.py`, which reads `~/.config/opencode/opencode.json`.
   When daemon runs as `bench-grader`, `~` resolves to `/home/bench-grader/`
   which has no opencode config. Cost will be `"-"` on daemon-graded rows.
   Acceptable: cost was already best-effort and `"-"` is the honest fallback.

3. **No reds-replay.tsv yet** — the keys file for real-task grading (#25) is
   not populated. The daemon handles this gracefully (returns BLOCK with
   "not found" reason). Once #25 lands and seeds `$KEYS/reds-replay.tsv`,
   reds-replay grading activates without code changes.

4. **Daemon must be started by operator** — `sudo -u bench-grader nohup python3 ...`
   or a systemd unit (step 5 of ADR). Not wired in this wave per instructions.

5. **Blast radius: zero** — the daemon is a new file with no existing callers.
   The product (`/home/stack/code/charon`) never imports it. The synthetic
   section graders (s0.py–s6.js) are unchanged. bench.sh's existing
   in-process grading path is untouched.

## Commit SHA

`15b87a0`
