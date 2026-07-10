# Model-id normalize: fix + retroactive cleanup report

Fixes the bug where opencode-provider-namespaced model ids (e.g.
`charon/glm-5.2`) got recorded verbatim into `model-scorecard.tsv` and
`runs/<id>/` instead of the bare curated id (`glm-5.2`), fragmenting one
model into two scorecard identities. Pre-flight: confirmed no benchmark
process running (`pgrep -fa 'bench.sh|grade_state'` empty) before AND after
all edits.

## 1. Source fix

**Reference mirrored exactly**: `src/charon/proxy.py::_normalize_model_id`
(read-only, in `/home/stack/code/charon`, never touched):

```python
def _normalize_model_id(model_id: str | None) -> str:
    if not model_id:
        return ""
    return model_id.rsplit("/", 1)[-1]
```

### `benchmark/lib/detect_model.py`

Added `normalize_model_id()` (same rsplit-final-segment rule; unlike
charon's version, returns the input unchanged on falsy input rather than
`""`, so callers can still distinguish "no id" from "id normalized to
empty" - never fabricates a value) and applied it at the single earliest
point the raw id is read out of opencode's `session.model` JSON, inside
`detect()`:

```python
# before
model_id = data.get("id")
if model_id:
    candidates.append((model_id, age_s))

# after
model_id = normalize_model_id(data.get("id"))
if model_id:
    candidates.append((model_id, age_s))
```

This normalizes BEFORE the ambiguity dedup (`distinct = sorted({...})`), so
two tabs reporting `charon/glm-5.2` and bare `glm-5.2` are correctly seen
as the SAME model, not flagged ambiguous.

### `benchmark/bench.sh`

`detect_model.py` only covers the auto-detect path; every place bench.sh
itself accepts a model id directly (`--model` overrides to
`start`/`grade`/`status`/`reset`, and `chart`'s positional arg) bypassed it
entirely. Added one shared helper (`normalize_model_id`) that shells out to
`detect_model.py`'s own function - never a re-implementation of the rsplit
rule in bash:

```bash
normalize_model_id() {
  local id="${1:-}"
  [ -z "$id" ] && { echo ""; return; }
  python3 -c '
import os, sys
sys.path.insert(0, os.path.dirname(sys.argv[1]))
from detect_model import normalize_model_id as _norm
print(_norm(sys.argv[2]))
' "$DETECT_PY" "$id"
}
```

Applied at every model-id capture point:
- `detect_model()` shell function's `--model` override branch (feeds `do_start`'s ANNOUNCE + `runs/<id>/` path)
- `do_grade`'s `--model` override AND its `$MODEL_STATE`-file fallback read
- `do_status`'s `--model` override AND its `$MODEL_STATE`-file fallback read
- `do_chart`'s positional `<model>` arg AND its `$MODEL_STATE`-file fallback read
- `do_reset`'s `--model` (normalized before the existing path-traversal charset check, so a namespaced id is usable there too)

Net effect: one normalized id flows into the ANNOUNCE banner, the
`runs/<id>/` path, and the scorecard `model` column - normalized once at
each entry point, never scattered ad-hoc string surgery.

### Test-fixture fallout (found and fixed)

`selftest/run_isolation_selftest.py`'s `part7_bench_sh_fallback_fail_closed`
builds a scratch `bench_dir/lib/` mirroring bench.sh's real runtime deps,
previously just `sections.sh, grade_state.py, charon_cost.py`. Since
`--model` overrides now genuinely depend on `detect_model.py` (for
normalization), the scratch fixture was missing a real dependency and the
`bench.sh status --model <id>` sub-test failed with
`ModuleNotFoundError: No module named 'detect_model'`. Fixed by adding
`detect_model.py` to the copied-files tuple. This is the only file besides
`detect_model.py` and `bench.sh` touched by Task 1.

## 2. Retroactive scorecard cleanup

**Backup**: `/home/stack/backups/scorecard-preidfix.tsv`, verified
byte-identical via `cmp` (exit 0) before any mutation.

**Rename**: 7 rows had a provider-prefixed `model` column - all
`charon/glm-5.2` (no `charon-full/` or other prefixes found anywhere in the
file; confirmed by scanning every `model` column for `/`). All 7 renamed to
bare `glm-5.2` (dated 2026-07-07, sections S0-S6).

**Collision found - FULL DETAIL FOR MANUAL REVIEW**: after renaming, all 7
of those rows collided with a PRE-EXISTING bare `glm-5.2` row for the same
`(model, section)` dated 2026-07-06 (an earlier, already-correct, complete
7-section glm-5.2 run that predates the namespacing bug). Per the ticket's
explicit collision rule ("rows dated 2026-07-07 win over older dates"),
this is unambiguous by date, so the older row was removed and the newer
(renamed) row kept in each pair. **Flagging loudly**: this is not merely an
id fix in 2 of the 7 pairs - the 2026-07-07 run actually SCORED WORSE than
the 2026-07-06 run it replaced (S3: 100->75, S5: 100->60), so the
scorecard's `glm-5.2` history now reflects a real regression, not just a
renamed duplicate. All 7 removed rows, verbatim, for manual review:

| section | removed (2026-07-06) row | kept (2026-07-07, renamed) row |
|---|---|---|
| S0 bugfix | `2026-07-06 bench S0 bugfix 0 glm-5.2 MERGE pass 100 7.4 0.002924 0 "clean minimal fix..."` | score 100, MERGE (same note, time_s=84.2, cost=0, tokens_in=138760/out=378) |
| S1 money-path | `2026-07-06 bench S1 money-path 1 glm-5.2 MERGE pass 100 23.2 0.008831 0 "fix correct..."` | score 100, MERGE (same note, time_s=162.2, tokens_in=408237/out=1862) |
| S2 routing | `2026-07-06 bench S2 routing 2 glm-5.2 MERGE pass 100 16.3 0.002956 0 "ascending cost_rank..."` | score 100, MERGE (same note, time_s=135.3, tokens_in=191461/out=692) |
| S3 ci-infra | `2026-07-06 bench S3 ci-infra 2 glm-5.2 MERGE pass 100 71.4 0.023388 0 "all 3 defects fixed, no assertions weakened..."` | **score 75, FIXES** (note: "2 of 3 defects fixed - pipefail_static=False"; time_s=129.8, tokens_in=259196/out=1047) - **regression** |
| S4 refactor | `2026-07-06 bench S4 refactor 3 glm-5.2 MERGE pass 100 25.2 0.010932 0 "subtle bug found..."` | score 100, MERGE (same note, time_s=100.2, tokens_in=195016/out=964) |
| S5 greenfield-feature | `2026-07-06 bench S5 greenfield-feature 4 glm-5.2 MERGE pass 100 5.1 0.001141 0 "honest scoping: ambiguities named 4/4..."` | **score 60, FIXES** (note: "ambiguities_named=2/4...partially overbuilds"; time_s=214.3, tokens_in=402029/out=2597) - **regression** |
| S6 frontend | `2026-07-06 bench S6 frontend 3 glm-5.2 MERGE pass 100 428.6 0.060842 1 "scope_ok=true..."` | score 100, MERGE (same note, time_s=679.7, tokens_in=2806841/out=6951) |

No same-date (ambiguous) collisions were found - every collision resolved
cleanly under the date rule, so nothing was left duplicated. Recommend the
manager double check whether the 2026-07-07 glm-5.2 run (now the sole
`glm-5.2` bench identity) is actually the run they want representing this
model, given the S3/S5 regressions above - the full pre-mutation file is in
the backup if the 2026-07-06 run needs to be restored instead.

**Post-mutation verification**: `grep -c "charon/" model-scorecard.tsv` ->
`0`. `model` column now has exactly 5 distinct values (`glm-5.2`,
`deepseek-v4-pro`, `gpt-5.4`, `hy3-preview-or`, `kimi-k2.6`), all bare. 9
total `glm-5.2` rows (2 `live` + 7 `bench`, one row per section, one
identity). File went from 45 data rows to 38 (7 duplicates removed).

## 3. runs/ dir consolidation

Backups (taken before any mutation):
- `/home/stack/backups/runs-charon-preidfix.tar.gz`
- `/home/stack/backups/runs-glm-5.2-preidfix.tar.gz`
- `/home/stack/backups/current_model-preidfix.txt`

Found `benchmark/runs/charon/glm-5.2/` (namespaced, all 7 sections S0-S6,
all `meta.json` finalized:true, dated 2026-07-07 - matches the run
consolidated into the scorecard above) alongside a PRE-EXISTING
`benchmark/runs/glm-5.2/` (bare, also all 7 sections finalized, dated
2026-07-06 - the same older run whose scorecard rows were superseded
above). **Every one of the 7 sections conflicted** (both sides have a full
`meta.json` + `worktree/` for every section - not a simple non-conflicting-
file merge), so per the conservative "keep both, suffix, note it - never
silently overwrite" instruction, I did NOT merge into the existing
`runs/glm-5.2/`. Instead:

- `runs/charon/glm-5.2/` -> moved to `runs/glm-5.2--from-charon-namespace-2026-07-07/` (full 7-section content preserved verbatim, nothing dropped)
- `runs/charon/` (now-empty wrapper dir, purely an artifact of the bug) -> removed
- Each moved section's `meta.json` had its `"model"` field corrected from `"charon/glm-5.2"` to `"glm-5.2"` (cosmetic - grade_state.py/tier_chart.py never read this field back for identity, only the directory path matters, but kept it consistent with the scorecard)
- `runs/glm-5.2/` (the pre-existing 2026-07-06 content) was left completely untouched

Manual review recommended: the manager may want to either (a) leave this as
is (old run stays at `runs/glm-5.2/`, newer run's worktrees available at
the suffixed path for reference), or (b) since the scorecard now treats
2026-07-07 as authoritative, swap them - `mv runs/glm-5.2
runs/glm-5.2--2026-07-06-superseded && mv
runs/glm-5.2--from-charon-namespace-2026-07-07 runs/glm-5.2`. Given the
score regression flagged in section 2, I deliberately did not make that
call myself.

Also normalized the stale `runs/.current_model` pointer file, which
contained the literal `charon/glm-5.2` (leftover from the buggy run) -
now contains `glm-5.2`. Backed up before changing (see above).

## 4. Verification

**Simulated `detect_model.py` normalization** (real `python3` invocation,
fake in-memory sqlite `opencode.db` with a `session` row set to
`{"providerID": "charon", "id": "charon/glm-5.2"}`):

```
detect() result: ('glm-5.2', 0.0083...)
PASS: providerID/id={charon, charon/glm-5.2} tuple normalized to bare glm-5.2
```

Also unit-checked `normalize_model_id()` directly (both the Python function
and bench.sh's shell wrapper, side by side, all matching):
`charon/glm-5.2`->`glm-5.2`, `charon-full/glm-5.2`->`glm-5.2`,
`openrouter/foo/bar`->`bar`, `glm-5.2`->`glm-5.2` (no-op), `""`->`""`,
`None`->`None`.

**`bash -n bench.sh`**: `SYNTAX_OK` (checked both immediately after the
bench.sh edits and again after all later edits).

**Selftests** (all under `benchmark/selftest/`), each run individually:
- `run_selftests.py` (grader self-tests, 20 cases across S0-S6): ALL PASS
- `token_capture_selftest.py`: PASS
- `run_isolation_selftest.py`: FAILED initially (see Task-1 fixture-fallout note above), PASS after fixing the scratch-lib fixture
- `efficiency_selftest.py`: PASS
- `session_cost_selftest.py`: PASS

**Live end-to-end check** against the real (post-cleanup) tree:
```
$ ./bench.sh status --model charon/glm-5.2
model=glm-5.2  current_section=<none - run complete>
$ ./bench.sh status --model glm-5.2
model=glm-5.2  current_section=<none - run complete>
```
Both resolve to the identical bare id and identical "run complete" status.

**Final scorecard grep/count**:
```
$ grep -c "charon/" model-scorecard.tsv
0
$ awk -F'\t' '!/^#/ && NF>0 && $6=="glm-5.2"' model-scorecard.tsv | wc -l
9
```
One `glm-5.2` identity, 9 rows (2 live + 7 bench, one per section), zero
`charon/`-prefixed values anywhere in the file.

## 5. Proposed commit message (NOT committed/pushed - working tree only)

```
fix(bench): normalize opencode-namespaced model ids to bare curated form

opencode's session.model JSON sometimes reports the id as
provider-namespaced (e.g. charon/glm-5.2) rather than bare (glm-5.2),
which detect_model.py and bench.sh's --model overrides were recording
verbatim - fragmenting one model into two model-scorecard.tsv identities
and two runs/<id>/ trees. Normalize once, mirroring charon's own
proxy.py::_normalize_model_id (rsplit on the final '/' segment), at
detect_model.py's single earliest extraction point plus every bench.sh
--model/positional entry point (all delegating to the same function -
never a reimplementation). Retroactively merged the 7 already-fragmented
charon/glm-5.2 scorecard rows into glm-5.2 (newer 2026-07-07 run superseded
the older 2026-07-06 duplicates per date, full collision detail in
scratch/model-id-normalize-report.md - flags a real S3/S5 score regression
worth a second look) and consolidated the matching runs/charon/glm-5.2/
worktrees to a suffixed sibling of runs/glm-5.2/ (not merged in-place;
every section conflicted). Backups of the pre-fix scorecard and runs/ trees
are under /home/stack/backups/.
```
