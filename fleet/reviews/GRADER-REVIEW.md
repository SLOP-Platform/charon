# ADVERSARIAL REVIEW — BENCH-OOB-GRADING (#26 Wave 1)

**Commit:** `f5fc2be` (5 files: `grader-daemon.py`, `graders/reds_replay.py`,
`selftest/test_grader_daemon.py`, `RUN-BENCHMARK.md`, `REVIEW-PACKET.md`)
**Branch:** `feat/bench-oob-grading`
**Reviewer:** mace-windu (independent, read-only)
**Date:** 2026-07-10

## VERDICT: MERGE-WITH-FIXES — confidence HIGH

The OOB grading trust boundary is **architecturally sound** (keys are
0700/inaccessible, daemon is sole grader + sole scorecard writer, no product
import of the artifact, versioned append-only scorecard, real-substrate
isolation test passes). The FAIL-ON-REVERT test genuinely reddens when the
invariants are reverted. **But two CRITICAL security holes in the request-
handling path let a graded agent who can drop a `req/<run>.json` destroy the
keys tree or execute arbitrary commands as `bench-grader`.** Both root-cause
to the same unvalidated agent-controlled field (`run`) flowing into a path
join and a shell command. They are one-line fixes each. Merge after fixing
F1+F2 (required); the rest are recommended.

## ATTACK CHECKLIST — explicit answers

1. **Isolation (keys unreadable, no self-grade):**
   **YES, the boundary holds at the substrate level.** Verified live:
   `/home/bench-grader` is `drwxr-x--- bench-grader`, `/home/bench-grader/keys`
   is `0700` and unreadable by `stack` (Check A passes:
   `ls` → `Permission denied`; `stat` → `Permission denied`).
   The spool root `/var/lib/bench-grader` is `0700`; `work/`, `state/`,
   `artifacts/` are unreachable by `stack`. The daemon is the sole reader of
   `$KEYS` and sole writer of `scorecard.v{n}.json`. The agent never executes
   a grader or `check_cmd`. **No leak path from the graded artifact** —
   `res/<run>.json` contains only `verdict/score/next_prompt/reason`
   (grader-daemon.py:312-322); no `check_cmd`, baseline, or grader source is
   echoed back. `reds_replay.py` returns only a truncated (400/120 char)
   combined stdout/stderr, never the `check_cmd` string itself
   (reds_replay.py:131,146,149).
   **CAVEAT (F3):** the isolation holds *as long as F1/F2 are not exploited*
   — those two holes would let the agent break isolation at runtime.

2. **No product import:**
   **YES.** Grep of the 3 new files shows zero `import charon` /
   `from charon` / `src.charon` / `src/charon` references
   (`grader-daemon.py`, `reds_replay.py`, `test_grader_daemon.py` all clean).
   Check C verifies no `.py` under `/home/stack/code/charon` references
   `scorecard.v` (verified: 0 hits). The artifact seam (`scorecard.v{n}.json`
   never imported by product) is intact. Note: pre-existing sibling files
   (`selftest/session_cost_selftest.py`, `lib/charon_cost.py`,
   `lib/detect_model.py`) DO import product — but those are out-of-scope for
   this commit and are not on the grading path.

3. **Versioning:**
   **YES, but with a residual (F4).** `_bump_version()` (grader-daemon.py:173)
   advances a persisted `scorecard.version` counter at daemon start and seals
   the prior artifact `chmod 0444` via `_seal_artifact()` (:189). Frozen
   consumers see a file that is never touched again. Rows carry both
   `artifact_version` and `schema_version` (=1). Verified live: the selftest
   creates `scorecard.v1.json`, appends 2 rows, bumps to v2. **Residual
   (F4):** there is no binding between a row and the daemon binary that wrote
   it — a stale/older `grader-daemon.py` running against a newer
   `scorecard.version` file would silently continue appending with an old
   schema. The version file is a monotonic counter, not a content hash or
   schema gate; a schema change bumps the constant but nothing rejects a row
   whose `schema_version` differs from the current constant.

4. **Reds-replay validity (fail-on-revert):**
   **PARTIAL.** `reds_replay.py` does run a real `check_cmd` from
   `$KEYS/reds-replay.tsv` against the snapshot and maps exit!=green → score
   0/BLOCK (reds_replay.py:144-149). A no-op worktree that leaves the red
   still-RED will score 0. **But the anti-false-green guard is NOT enforced
   by the grader (F5):** the docstring (reds_replay.py:21-23) says "the
   pre-fix snapshot must FAIL the check … that gate is run by curation in
   `$KEYS`." If a curated row's red is already green pre-fix, the grader
   scores 100 with no pre-fix assertion — a false green. The grader trusts
   the curated row unconditionally. No self-test asserts a non-fixed snapshot
   scores 0; the only test uses `trivial_ok` with `flag.txt` pre-existing
   (the "fix" is a no-op), so the selftest would pass even if the grader
   scored an unfixed worktree 100.

5. **Tests fail-on-revert:**
   **MOSTLY.** Check A (isolation) reddens if keys become world-readable —
   verified by reasoning (the `iterdir()` succeeds → `check(False,...)`)
   :62-64. Check B reddens if `_append_scorecard_row` is neutered to a no-op
   (the `assert len(rows)==1` at :598 fails) or if versioning is removed
   (`assert v2==v+1` :611 fails). Check C reddens if a product file adds
   `scorecard.v`. **But Check D is a string-presence test, not a behavioral
   one (F6):** it greps the daemon source for the literals `_bump_version`,
   `_seal_artifact`, `_append_scorecard_row`, etc.
   (test_grader_daemon.py:147-156). A saboteur who empties the *body* of
   those functions but keeps the symbol names passes Check D; only Check B
   catches a fully-neutered writer. Check D therefore adds little beyond
   what B already covers, and gives false confidence that the logic is
   intact when only the names survive.

6. **Gameability:**
   **The rubric is NOT grader-readable** (keys are 0700, agent cannot list
   them, check_cmd is in `$KEYS/reds-replay.tsv` not in any stack-readable
   path). There is no self-report trust — the daemon is sole writer. There is
   no deterministic-answer leakage via `res/` (verdict/score/next_prompt
   only). **However F1/F2 constitute a gameability escape**: an agent who
   can drop a crafted `req/<run>.json` can execute arbitrary shell as
   `bench-grader` (e.g. `chmod 777 $KEYS` then read it, or write a
   `scorecard.v1.json` row with any score). This is strictly more powerful
   than gaming the grader.

---

## FINDINGS

### F1 — CRITICAL: path traversal in `run` field deletes any bench-grader-owned path
**File:** `fleet/benchmark/grader-daemon.py:286-287` (`grade_one`),
`:357-358` (`_snapshot_worktree`)

The `run` field is read from the agent-supplied request JSON
(`req.get("run", run_id)`, :277) and joined unsanitized into the snapshot
path: `work_snapshot = self.work_dir / run` (:286).
`_snapshot_worktree` then does `if dst.exists(): shutil.rmtree(dst)`
(:357-358) **before** copying. Because `work_dir` is
`/var/lib/bench-grader/spool/work` and `stack` can drop a file into the
`1733` maildrop `req/`, an agent can set:

```json
{"run": "../../keys", "worktree": "/tmp/x", "kind": "red", ...}
```

`dst` resolves to `/home/bench-grader/keys` → `shutil.rmtree` deletes the
entire answer-key tree as `bench-grader`. Confirmed by resolution:

```
work_snapshot = /var/lib/bench-grader/spool/work/../../keys
            -> /home/bench-grader/keys  (rmtree target)
```

**Severity CRITICAL.** Destroys the isolation invariant the whole system
exists to protect; recoverable only by restoring `$KEYS` from backup. The
`req/` maildrop (mode `1733`) is world-writable-by-creation but the daemon
trusts the JSON body completely.

**Fix:** reject any `run` containing path separators or `..`;
`os.path.basename(run)` or a regex `^[A-Za-z0-9_.-]+$`. Apply the same to
`req_path.stem`-derived `run_id` and to `unit_id`/`kind`.

### F2 — CRITICAL: shell injection via `run` field in reds_replay._run_check
**File:** `fleet/benchmark/graders/reds_replay.py:118-122` (`_run_check`)

The snapshot path derived from the agent-controlled `run` field (see F1) is
substituted into `check_cmd` and run with `shell=True`:

```python
cmd = check_cmd.replace("{worktree}", str(worktree))   # :118
proc = subprocess.run(cmd, shell=True, cwd=str(worktree), ...)  # :120-122
```

An agent setting `run = 'x$(chmod 777 /home/bench-grader/keys)'` causes
`bench-grader` to execute `chmod 777 $KEYS` as a side effect of the shell
expanding `$(...)` inside the substituted path. After that the agent reads
`$KEYS/reds-replay.tsv` directly — full answer-key compromise. Confirmed
the resulting shell command is:

```
test -f /var/lib/bench-grader/spool/work/x$(chmod 777 /home/bench-grader/keys)/flag.txt
```

The `shlex` import (reds_replay.py:32) is **dead code** — never used; it
appears someone intended `shlex.quote` but it was never wired in. Passing
`shell=True` with an interpolated, partially-agent-controlled string is
the classic injection vector.

**Severity CRITICAL.** Arbitrary code execution as `bench-grader`; total
isolation collapse. Independent of F1 — even if the path-traversal in F1
were fixed, this still fires because the snapshot *path string* (not its
file target) reaches the shell.

**Fix:** (a) validate `run` as in F1 so the path contains no shell
metacharacters; AND (b) pass `check_cmd` as a list (`shell=False`) or
`shlex.quote()` the worktree before substitution. Defense in depth: both.

### F3 — MEDIUM: the two CRITICAL holes are reachable by the threat model
**File:** `fleet/benchmark/grader-daemon.py:229-244` (`_drain`),
`:277-287` (`grade_one`)

The threat model (ADR §1.3) explicitly states `stack` "can write `req/`"
via the `1733` maildrop. The ADR §1.5 describes `req/` as "DROP BOX: stack
can create+write a file it names but cannot `ls`." The daemon reads every
`*.json` in `req/` and passes the JSON body's `run` field into the
vulnerable paths (F1/F2). So the attack surface is exactly the intended
agent capability — no privilege beyond "the graded agent can submit a
grading request" is required. The selftest validates the daemon only with
benign `run="r1"`/`"r2"` values; no adversarial input test exists.

**Severity MEDIUM** (severity is the *reachability*, not the impact — the
impact is folded into F1/F2). Documents that the holes are not theoretical.

**Fix:** add an adversarial test to `test_grader_daemon.py` that submits a
`run` containing `..` and shell metacharacters and asserts the daemon
rejects it (score 0, no rmtree, no shell expansion).

### F4 — LOW: versioning has no binding to the writing daemon binary / schema
**File:** `fleet/benchmark/grader-daemon.py:84` (`ARTIFACT_SCHEMA_VERSION`),
`:166-187` (version file)

`scorecard.version` is a monotonic integer written as plain text
(:186). `_current_version()` reads it back (:166-171). If an older daemon
binary is (re)started against a `scorecard.version` left by a newer daemon,
it silently continues appending rows with its older `schema_version`
constant into the current-version file. Consumers reading the frozen
artifact see a mix of schema versions in one file. `schema_version` is
recorded per-row (:344) but nothing in the consumer path is shown to
reject mismatched rows. A stale-grader-mistaken-for-current scenario is
therefore possible at the binary level (not the file level).

**Severity LOW.** Frozen prior versions are still sealed 0444 and immutable,
and the current version is always append-only; the risk is a schema mix
*within* the current version during a botched deploy.

**Fix:** record a daemon-build hash or the `ARTIFACT_SCHEMA_VERSION` in the
version file and reject appends whose constant != the recorded one; or bump
the file version, not just the schema constant, on any schema change.

### F5 — MEDIUM: reds_replay has no pre-fix (false-green) assertion
**File:** `fleet/benchmark/graders/reds_replay.py:21-26, 134-150`

The docstring asserts the invariant ("the pre-fix snapshot must FAIL the
check") but immediately defers it: "that gate is run by curation in
`$KEYS`." The grader therefore trusts the curated row and scores purely on
the post-fix check. If a red is curated incorrectly (already green
pre-fix), the grader scores 100 on a no-op task — a false green that moves
a load-bearing number. The `prefix_snapshot` column exists in the ADR
schema (ADR §1.5: `prefix-snapshots/<red-id>.tar`) and the daemon forwards
`prefix_snapshot` to the grader env (grader-daemon.py:409-412) but
`reds_replay.py` never reads or uses it.

**Severity MEDIUM.** A curated red that is already green pre-fix scores 100
with no work. This is the "no-op passes the grader" failure the brief asked
about — it does not pass for a *real* red, but there is no guard that the
red is real at grade time.

**Fix:** load `prefix_snapshot` in `reds_replay._load_reds_row`, expand it
into a temp dir, run `check_cmd` against it, and BLOCK (score 0) if the
pre-fix snapshot does NOT fail the check. Add a selftest row asserting an
already-green fixture scores 0.

### F6 — LOW: Check D is a string-presence test, not a behavioral gate
**File:** `fleet/benchmark/selftest/test_grader_daemon.py:138-163`

Check D greps the daemon source for the literal symbols `_bump_version`,
`_seal_artifact`, `_append_scorecard_row`, `ARTIFACT_SCHEMA_VERSION`, and the
keys/spool path strings (:147-156). A saboteur who replaces the *bodies* of
those functions with `pass` / `return 1` but keeps the symbol names passes
Check D. Check B catches a fully-neutered `_append_scorecard_row` (the row
count assertion :598 fails), but a partially-neutered `_seal_artifact` (no
chmod) or a `_bump_version` that returns a constant would pass both B and
D. The "daemon source contains all required refs" claim is weaker than
"the logic works."

**Severity LOW.** Check B already covers the most important behavioral
property; Check D gives marginal additional assurance and slightly
overstates its coverage. Worth fixing for honesty about what the test does.

**Fix:** either (a) remove Check D and rely on Check B plus an explicit
"is the prior artifact actually 0444?" assertion in the selftest, or
(b) keep D but relabel it "daemon source contains required symbols
(structural smoke, not behavioral)".

### F7 — LOW: ledger ownership does not match the ADR
**File:** `fleet/ADR-BENCH-OOB-GRADING.md:307-309` (spec) vs live state

ADR §1.5 specifies `model-scorecard.tsv` is `chown bench-grader:bench-grader
0644` (daemon is sole writer). Live: the file is `stack:stack 0644`. The
daemon's `DEFAULT_LEDGER` points at it (grader-daemon.py:67-72) but the
daemon never writes to it (no `_append_scorecard_row`-style ledger write;
`ledger_path` is a dataclass field only, never used). So the mismatch is
currently inert — the daemon writes only `scorecard.v{n}.json`, not the
TSV. But it means the "sole writer of the ledger" claim in the ADR is not
yet realized, and if ledger appends are later wired, the file is currently
`stack`-writable, reintroducing the self-report hole.

**Severity LOW** (inert today; latent if ledger writes are added without
the chown). The `ledger_path` field is dead code — a smell that suggests an
unfinished integration.

**Fix:** either drop `ledger_path` (daemon only writes the scorecard
artifact, not the TSV — update the ADR) or wire the chown + the append.
Either way, remove the dead `ledger_path` field to avoid implying the
daemon writes the TSV.

---

## SUMMARY TABLE

| # | Sev | File:line | One-line |
|---|-----|-----------|----------|
| F1 | CRIT | grader-daemon.py:286,357 | path traversal in `run` → `rmtree` of `$KEYS` |
| F2 | CRIT | reds_replay.py:118,120 | `shell=True` + agent path → RCE as bench-grader |
| F3 | MED  | grader-daemon.py:229,277 | F1/F2 reachable via the intended `req/` maildrop |
| F4 | LOW  | grader-daemon.py:166,84 | no binary/schema binding; stale grader can append |
| F5 | MED  | reds_replay.py:21,134 | no pre-fix false-green guard (trusts curation) |
| F6 | LOW  | test_grader_daemon.py:138 | Check D is string grep, not behavioral |
| F7 | LOW  | grader-daemon.py:107, ADR §1.5 | ledger path dead; file is stack-owned, not bench-grader |

## EXPLICIT ANSWERS (required by brief)

- **Isolation (keys unreadable + no self-grade): YES** at substrate level
  (0700 bench-grader, verified unreadable by `stack`); ** Conditional on
  F1/F2** — the runtime attack path breaks it.
- **No product import: YES** — the 3 graded files import no `charon`/
  `src.charon`; Check C confirms no product `.py` references `scorecard.v`.
- **Fail-on-revert: PARTIAL** — A/B/C are behavioral and reddens correctly;
  D is structural-only; the reds_replay pre-fix guard (F5) is untested.

## REQUIRED BEFORE MERGE
1. **F1 + F2** — validate the agent-supplied `run` (and `unit_id`, `kind`)
   against `^[A-Za-z0-9_.-]+$` with no path separators / `..` / shell
   metacharacters; AND `shell=False` (or `shlex.quote`) in
   `_run_check`. Both are one-line fixes.
2. Add an adversarial input test (F3) that submits a malicious `run` and
   asserts rejection.

## RECOMMENDED (post-merge ok)
3. F5 — wire the `prefix_snapshot` pre-fix assertion + a selftest row.
4. F4 — bind the version file to a daemon/schema hash.
5. F6 — drop or relabel Check D; add an explicit 0444 assertion.
6. F7 — remove dead `ledger_path` or wire + chown the TSV.
