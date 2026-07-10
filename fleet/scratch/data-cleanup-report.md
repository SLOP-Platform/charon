# Benchmark data cleanup — 2026-07-06

Harness confirmed IDLE before starting (`pgrep -fa 'bench\.sh|grade_state|run\.sh'` matched
nothing but the pgrep invocation itself). No commit/push performed — working tree only,
for the manager to review and land.

## Backup

- Source: `/home/stack/charon-private/fleet/model-scorecard.tsv`
- Backup: `/home/stack/backups/scorecard-precleanup.tsv`
- Verified byte-identical with `cmp` (no diff) before any edits.
- SHA-256 (both files, pre-edit): `1782a73efebb4b438222809017023061bdf87d5797f460d81f799d449bb84789`

## 1. Discarded deepseek-v4-pro bench rows

Grounded in `scratch/kimi-k26-diagnostic.md` ("CONTAMINATION SCOPE" section): all 7
`bench`-source `deepseek-v4-pro` rows (S0-S6) carry a frozen stale `start_ts`
(2026-07-05 21:09:01) from before the actual Jul-6 run, graded ~91,700-91,875s later
→ forced `score=0`/`BLOCK` on every section, and the name itself is untrustworthy
(harness keys run state by bare model name; the diagnostic concludes kimi-k2.6 was
actually being driven into the deepseek-named dir).

Matched exactly on `source=="bench" AND model=="deepseek-v4-pro"` (the two `live`-source
deepseek-v4-pro rows, lines 9-10 — real reviewed work items, unrelated to this bench
run — were correctly left untouched).

**7 rows removed** (verbatim, in original order; note S3's field literally contains an
embedded newline in the on-disk TSV — reproduced here as-is):

```
2026-07-06	bench	S0	bugfix	0	deepseek-v4-pro	BLOCK	pass	0	91701.0	-	0	timeout (clean minimal fix: only chearp->cheap changed)
2026-07-06	bench	S1	money-path	1	deepseek-v4-pro	BLOCK	pass	0	91711.8	-	0	timeout (fix correct, new test fails on buggy code / passes on fixed, scope clean)
2026-07-06	bench	S2	routing	2	deepseek-v4-pro	BLOCK	fail	0	91716.3	-	0	timeout (select_provider does not return ascending cost_rank order (got: 'prov-b,prov-a,prov-c'))
2026-07-06	bench	S3	ci-infra	2	deepseek-v4-pro	BLOCK	fail	0	91721.6	-	0	timeout (still red / no defects fixed - yaml=False(YAML parse error: mapping values are not allowed here
  in "<unicode string>", line 12, column 13:
             run: pytest -q
                ^); pipefail_static=False; behavioral=False(smoke.sh exits 0 against an unreachable health endpoint (masking bug still present)); port=False(ci.yml still hardcodes HOST_PORT literal); markers=CHECK markers baseline=2 worktree=2)
2026-07-06	bench	S4	refactor	3	deepseek-v4-pro	BLOCK	pass	0	91738.2	-	0	timeout (subtle bug found, isolating test discriminates buggy/fixed, suite green, scope clean)
2026-07-06	bench	S5	greenfield-feature	4	deepseek-v4-pro	BLOCK	pass	0	91856.6	-	0	timeout (honest scoping: ambiguities named, minimal/labeled, explicitly defers - ambiguities_named=3/4; new_config_without_hedge=none; files_touched=2; explicit_defer=True)
2026-07-06	bench	S6	frontend	2	deepseek-v4-pro	BLOCK	pass	0	91875.2	-	0	timeout (scope_ok=true; render_ok=true rendered=[{"name":"prov-a","cost_class":"cheap","status":"ok"},{"name":"prov-b","cost_class":"strong","status":"degraded"},{"name":"prov-c","cost_class":"premium","status":"down"}]; real_data_proof=true rendered_after_mutation=[{"name":"prov-x","cost_class":"premium","status":"ok"},{"name":"prov-y","cost_class":"cheap","status":"down"}])
```

Post-removal check: `awk -F'\t' '$2=="bench" && $6=="deepseek-v4-pro"' model-scorecard.tsv | wc -l` → **0**.
(The two `live`-source deepseek-v4-pro rows remain, correctly, since they were never in scope.)

## 2. Re-graded S5 cells (premature-grade race)

Ran the exact grader the harness uses (`benchmark/bench.sh do_grade` invokes
`section_grader S5` → `python3 graders/s5.py --worktree <worktree> --baseline
fixtures/sections/s5`), read-only, against the untouched worktrees:

```
$ python3 graders/s5.py --worktree runs/kimi-k2.6/S5/worktree --baseline fixtures/sections/s5
{"score": 100, "verdict": "MERGE", "gate": "pass", "reason": "honest scoping: ambiguities named, minimal/labeled, explicitly defers - ambiguities_named=4/4; new_config_without_hedge=none; files_touched=0; explicit_defer=True"}

$ python3 graders/s5.py --worktree runs/glm-5.2/S5/worktree --baseline fixtures/sections/s5
{"score": 100, "verdict": "MERGE", "gate": "pass", "reason": "honest scoping: ambiguities named, minimal/labeled, explicitly defers - ambiguities_named=4/4; new_config_without_hedge=none; files_touched=0; explicit_defer=True"}
```

Both returned exactly the expected `score=100, ambiguities_named=4/4` — matches the
diagnostic's prediction, so both were corrected.

### kimi-k2.6 / S5

- **Before**: `score=60  verdict=FIXES  reason="flags some ambiguity / defers but incomplete or partially overbuilds - ambiguities_named=0/4; new_config_without_hedge=none; files_touched=0; explicit_defer=True"`
- **After**: `score=100  verdict=MERGE  reason="honest scoping: ambiguities named, minimal/labeled, explicitly defers - ambiguities_named=4/4; new_config_without_hedge=none; files_touched=0; explicit_defer=True"`
- `time_s` (0.6), `cost_usd` (0.000000), `corrections` (0) left untouched — those are
  measured run metadata, not derived from score.
- `benchmark/runs/kimi-k2.6/S5/meta.json`: `final_score` 60 → 100 (only field changed;
  `final_time_s`/`final_cost_usd`/`final_corrections` untouched, matching the ledger row).

### glm-5.2 / S5

- **Before**: `score=60  verdict=FIXES  reason="flags some ambiguity / defers but incomplete or partially overbuilds - ambiguities_named=0/4; new_config_without_hedge=none; files_touched=0; explicit_defer=True"`
- **After**: `score=100  verdict=MERGE  reason="honest scoping: ambiguities named, minimal/labeled, explicitly defers - ambiguities_named=4/4; new_config_without_hedge=none; files_touched=0; explicit_defer=True"`
- `time_s` (5.1), `cost_usd` (0.001141), `corrections` (0) left untouched.
- `benchmark/runs/glm-5.2/S5/meta.json`: `final_score` 60 → 100 (same, only field changed).

`verdict` was updated in both rows because it is a pure function of score
(`verdict_from_score`: score>=90 → MERGE) — `gate` stayed `pass` (unchanged by score).

## Verification

- `diff` between backup and cleaned TSV shows **exactly**: the 7 deepseek-v4-pro block
  removed, and the 2 S5 rows changed (score/verdict/reason only) — no other row touched.
- Data-record count: 39 → 32 (**delta -7**, confirmed programmatically, counting logical
  TSV records rather than physical lines — the removed S3 deepseek row spans 4 physical
  lines due to an embedded newline in its note field).
- `model-scorecard.sh render` runs clean, no parse errors. Tier-4 (greenfield-feature)
  mean score for both kimi-k2.6 and glm-5.2 now shows `100.0` (single S5 row each),
  confirming the re-grade took effect. `deepseek-v4-pro` still appears in the EFFICIENCY
  table as `-`/no-data (from its remaining `live` rows only), as expected.

## Files touched

- `/home/stack/charon-private/fleet/model-scorecard.tsv` (7 rows removed, 2 rows corrected)
- `/home/stack/charon-private/fleet/benchmark/runs/kimi-k2.6/S5/meta.json` (`final_score` 60→100)
- `/home/stack/charon-private/fleet/benchmark/runs/glm-5.2/S5/meta.json` (`final_score` 60→100)
- Backup: `/home/stack/backups/scorecard-precleanup.tsv` (untouched, byte-identical to
  pre-cleanup original)

No commit/push performed.
