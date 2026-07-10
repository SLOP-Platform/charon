# bench-model-misdetect (P1) — fix report

Ticket: `fleet/reds.tsv` `bench-model-misdetect`, 2026-07-07, P1, open.
Scope: rig-level (`fleet/benchmark/`), no product touch, no push.

## STEP 1 — root cause (read-only DB query)

Queried `~/.local/share/opencode/opencode.db` read-only
(`SELECT id, directory, title, model, time_created, time_updated FROM
session WHERE model IS NOT NULL ORDER BY time_updated DESC LIMIT 15`).
Relevant rows at investigation time:

| session | dir | model | updated_age |
|---|---|---|---|
| ses_0c129ebd | mediastack | hy3-preview-or | **0s** |
| ses_0c0def8d | charon | glm-5.2 | 547s (~9 min) |

The old `detect_model.py` took `ORDER BY time_updated DESC LIMIT 1` —
system-wide, across every open opencode tab, no matter its purpose. That
single-row heuristic assumed the operator's own bench tab would always be
the freshest row in the whole DB "by construction" (picked model, pasted
immediately). It is not: `session.time_updated` bumps on **any** session
activity, not just a `/model` switch. In this rig's normal operating mode
(manager session + several concurrent droid/bench tabs), some entirely
unrelated tab is very likely to be touched more recently than the
operator's own bench tab, even minutes after the real `/model` pick — its
`model` column reflects whatever was set in it long ago, not anything the
operator just chose.

This is exactly what happened: `ses_0c129ebd` (an unrelated concurrent
tab, model=hy3-preview-or) was touched at this literal instant, beating
`ses_0c0def8d` — the operator's real glm-5.2 benchmark tab, whose last DB
write was 9 minutes earlier (idle between agent turns, not stale/wrong,
just not the *most recently touched* row anymore). `runs/.current_model`
on disk still reads `hy3-preview-or`, confirming a prior `bench.sh start`
invocation was misled by exactly this mechanism. glm-5.2 already had all
7 sections finalized from a prior (v1) run — `hy3-preview-or` was ALSO
already fully finalized — so `start` misdetected, saw 7/7 done, and
silently printed the tier chart instead of starting a fresh v2 run. No
error, no benchmark.

**Why a narrower staleness window does not fix this**: the false candidate
was touched at age ~0s. Any window short of excluding it entirely still
lets it win. The defect is not "the window is too wide" — it's "rank-1
alone cannot distinguish a genuine `/model`-then-paste from unrelated
background activity in a different tab."

## STEP 2 — reliability fix

`lib/detect_model.py`: `detect()` now collects **every** session with a
`model` set that falls inside the (unchanged, 900s) staleness window, and
looks at the **distinct set of model ids** among them:
- 0 candidates → unchanged fallback (nothing fresh).
- 1 distinct id → unambiguous, return it (common single-tab case — no
  regression, same reliability as before).
- 2+ distinct ids → **AMBIGUOUS**: raises `Ambiguous`, `main()` exits 2
  with `{"error": "ambiguous", "candidates": [...]}`. Refuses to guess
  instead of trusting whichever row happened to be touched last — this is
  the direct fix for the confirmed incident above.

`bench.sh`'s `detect_model()` now distinguishes exit code 2 from exit code
1 and prints a specific, loud message naming the ambiguous candidates and
telling the caller to self-report + re-run with `--model`.

`do_start`'s `ANNOUNCE` banner now includes a **STOP - VERIFY** block
(impossible to miss, printed before any section prompt) instructing the
operator/agent to confirm the announced id matches their own `/model`
pick before implementing anything, with the exact re-run command if not.

`RUN-BENCHMARK.md` and `README.md` now lead with **`--model <id>`
recommended on every step, including `start`** (previously only `grade`
carried that recommendation) — the agent already knows its own model id
from the `/model` the operator just ran, so passing it explicitly
sidesteps the whole failure class. Auto-detect remains as a fallback,
now fail-loud instead of fail-silent-wrong.

## STEP 3 — re-run/reset path

New `bench.sh reset --model <id> [--force]` (operator-facing, not part of
the agent's own S0..S6 loop):
1. Validates `<id>` against `[A-Za-z0-9._-]+` (used as a path component —
   blocks path traversal).
2. Refuses if that model has a genuinely **active** in-flight section
   (via `grade_state.py is_active`) unless `--force` is passed — protects
   a run that's actually mid-flight right now.
3. Backs up `runs/<id>/` and `model-scorecard.tsv` to
   `runs/.reset-backups/<id>-<timestamp>/` **before** touching anything.
4. Clears `runs/<id>/` entirely.
5. Strips **only** `<id>`'s rows from `model-scorecard.tsv` where
   `source` is `bench` or `bench2` — **`source=live` rows for that model
   are always kept** (real production usage grades, not re-runnable
   harness output; discovered live glm-5.2 had 2 live + 7 bench rows
   mixed together — a naive "strip all rows for this model" would have
   destroyed real production signal).
6. Clears the shared `runs/.current_model` pointer only if it currently
   points at the target model.
7. Every other model's `runs/<other>/` and scorecard rows are provably
   untouched (verified below).

## Verification (scratch copy only — live state untouched)

Copied `fleet/benchmark/`, `fleet/model-scorecard.sh`, and
`fleet/model-scorecard.tsv` into an isolated scratch dir
(`.../scratchpad/fleet-test/fleet/`) and ran everything there. The live
repo at `/home/stack/charon-private/fleet/` was **never** invoked through
`bench.sh` during this task — only read via `git diff`/`grep`/`ls` to
confirm it was unchanged.

**1. Detection dry-run against the REAL live DB (read-only, no bench.sh
invocation):**
```
$ python3 lib/detect_model.py
{"error": "ambiguous", "candidates": ["glm-5.2", "hy3-preview-or"]}
exit=2
```
Correctly refuses instead of silently reporting hy3-preview-or.

**2. `bench.sh start` with no `--model` (scratch copy):** refuses with the
new ambiguous-candidates message, exit 1 (via `die`), naming both
`glm-5.2` and `hy3-preview-or`.

**3. `bench.sh start --model glm-5.2` (scratch copy):** announces
`glm-5.2` with the new STOP-VERIFY block; since the scratch copy carried
glm-5.2's pre-existing 7/7 finalized sections, it correctly falls through
to "already finalized, printing the tier chart" (Frontier, composite
100.0, rank #1 of 3).

**4. `bench.sh reset --model glm-5.2` (scratch copy):**
- Before: `model-scorecard.tsv` had 9 glm-5.2 rows (2 `live` + 7 `bench`);
  `runs/glm-5.2/` had all 7 finalized sections.
- After: 2 `live` rows kept verbatim, 7 `bench` rows removed;
  `runs/glm-5.2/` gone; every other model's row-count and `runs/<model>/`
  dir confirmed byte-identical before/after (`deepseek-v4-pro`: 2/2,
  `hy3-preview-or`: 7/7, `kimi-k2.6`: 7/7, `gpt-5.4`: 7/7); full backup at
  `runs/.reset-backups/glm-5.2-<ts>/` (both the pre-reset `runs/glm-5.2/`
  tree and `model-scorecard.tsv.bak`).
- `bench.sh start --model glm-5.2` immediately after reset correctly
  starts a fresh S0.

**5. Guard tests (scratch copy):**
- `reset --model glm-5.2` while S0 was genuinely active → refused
  ("ACTIVE in-flight run ... pass --force to override").
- `reset --model glm-5.2 --force` while active → succeeded.
- `reset --model "../../etc"` → refused (path-traversal charset guard).
- `reset` with no `--model` → usage error.

**6. Live repo integrity check (after all scratch testing):**
```
$ grep -cP '\tglm-5\.2\t' fleet/model-scorecard.tsv   # still 9 (untouched)
$ cat fleet/benchmark/runs/.current_model             # still "hy3-preview-or" (untouched)
$ ls fleet/benchmark/runs/glm-5.2 | wc -l              # still 7 (untouched)
```
No live file was written by this task. `git status` on `fleet/benchmark/`
shows exactly the 4 intended edits (`README.md`, `RUN-BENCHMARK.md`,
`bench.sh`, `lib/detect_model.py`) plus one pre-existing untracked file
(`BENCHMARK-V2-REVIEW.md`) and a pre-existing `reds.tsv` addition (the
`bench-model-misdetect` ticket row itself) that were already present
before this task started — neither touched by this fix.

## Files changed

- `fleet/benchmark/lib/detect_model.py` — ambiguity-based refusal (the
  core fix); module docstring rewritten with the incident + rationale.
- `fleet/benchmark/bench.sh` — `detect_model()` handles exit-2 distinctly;
  `do_start`'s ANNOUNCE gets a STOP-VERIFY block; new `do_reset()` +
  `reset` subcommand wired into `main()`; header comment updated.
- `fleet/benchmark/RUN-BENCHMARK.md` — leads with `--model` on `start`
  too, explicit verify instruction, reset path pointer.
- `fleet/benchmark/README.md` — "Model detection" section rewritten
  (incident + two-part fix), `start`/new `reset` entries in the
  subcommand reference.

## Proposed commit

```
fix(bench): refuse ambiguous model auto-detect + add reset/re-run path (bench-model-misdetect P1)

detect_model.py used to trust the single most-recently-*touched* opencode
session system-wide, which silently misreports whenever any other
concurrent tab is touched more recently than the operator's own
freshly-/model-picked bench tab (this rig's normal multi-tab mode).
Confirmed incident: announced hy3-preview-or instead of glm-5.2 after an
opencode restart, saw hy3 already finalized, and silently skipped the run.

- detect() now refuses (exit 2, "ambiguous") whenever 2+ DIFFERENT models
  were set within the staleness window, instead of guessing rank-1.
- bench.sh surfaces that refusal with a specific message; start's ANNOUNCE
  banner gets a STOP-VERIFY block; --model is now the documented default
  path in RUN-BENCHMARK.md/README.md.
- new `bench.sh reset --model <id> [--force]`: backs up then clears one
  model's runs/<id>/ + its bench-sourced scorecard rows only (keeps any
  live-sourced rows), so an already-finalized model can be re-run cleanly
  (e.g. moving to v2 scoring).

Verified against the real (live) opencode.db read-only (now correctly
refuses instead of misdetecting) and against an isolated scratch copy of
fleet/benchmark for all mutating paths (start --model, reset, guards) -
live model-scorecard.tsv/runs/ untouched throughout.
```

Not committed/pushed — manager to review and land.
