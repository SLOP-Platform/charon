# Review: 409@charon-private
**PR:** feat(class-detectors): uniform detector harness for all nine missing-class checks
**URL:** https://github.com/Nnyan/charon-private/pull/409
**Date:** 2026-08-02T15:32:52Z
**Reviewer:** reviewer-tab-2541479
**Author:** frontier-2788762

## Verdict
NEEDS-REVISION

## Findings
- FAIL-ON-REVERT is not actually implemented for classes 4-9. Test section D seeds a missing SSOT key but only asserts `CLASS[config-ssot-keys]` appears (the comment admits "verdict depends on whether grep finds the key" — it never asserts a FINDING), and sections E-F only assert class names appear in output. Classes 5-9 (deploy-drift, catalog-rot, daemon-liveness, name-pool-exhaustion, operator-staleness) have ZERO tests. The review log and `fleet/state/MISSING-CLASS-DETECTORS.md` claim "Every class has a corresponding test... that seeds the exact condition and proves it FIRES" and "All 31 tests pass" — a gutted detector body replaced with `echo "CLASS[x]..."` passes every test. The "structural integrity" claim (section F) is a cover: presence of a class label in output proves nothing about firing.
- `detect_name_pool_exhaustion` computes `total` as `grep -c '^[[:space:]]*[a-z]' "$claim_script"` — that counts every indented code line in the script (if/for/local/echo bodies), not the pool size. With `total` in the hundreds, `available <= total/4` is trivially true, so the detector permanently false-positives (or, if `bash list` emits nothing, `available=0` → always FINDING). The "48% burned, ~9 left" measurement is not reproducible and this class has no test.
- `detect_operator_staleness` contains dead code that masquerades as real logic: it computes per-label `added` from `git log`, then never uses it — the finding fires purely on `total_items > 10`. The doc claims an "age signal" detector; the implementation is just an item counter.
- Reentrancy guard exits 0 on nested invocation: `[ -n "${CLASS_DETECTOR_ACTIVE:-}" ] && { ...; exit 0; }`. A duplicate/parallel cron run silently reports CLEAN (exit 0) while doing nothing — masking for a detector whose whole contract is "exit 0 only when all classes OK". Test G checks only the message, never the exit code.
- `--class` with a missing trailing argument (e.g. `--class`) causes `shift 2` to error; with `set -uo pipefail` (no `-e`), `$#` stays 1 and the arg-parsing `while` loops forever — a cron hang.
- `detect_catalog_rot` runs comma-fielded `awk -F','` and header-subtracting line counts over `*.csv -o *.json -o *.tsv` indiscriminately: JSON/TSV files parsed as CSV produce garbage `total_models`/`zero_priced` counts. Untested, silently wrong on the actual product data.
- Untrusted filenames are interpolated raw into the machine-readable contract: `git ls-files --others` output and review-log basenames flow unescaped into `summary="..."` / `recover="..."`. A filename containing `"`, newline, or `$(...)` corrupts the line contract and injects into any consumer that executes `recover` (which the state doc explicitly advertises as "exact command to fix").
- `verdict=STALE` is misused in crontab-registration for "referenced script does not exist" — the contract defines STALE as heartbeat/output-age only. It also increments `FOUND` → exit 1, so one dangling cron path permanently fails the box, and a consumer keying on STALE semantics will mis-triage it.
- `detect_crontab_registration` counts `fleet/` occurrences via `grep -c 'fleet/'` over the full crontab including `#`-commented lines, so commented-out entries register as present — false "all registered".
- deploy-drift's `gh repo view` runs against the caller's CWD repo, not `$product_repo`; it only falls back to `git remote get-url origin` if the gh call returns empty, so in a wrong-CWD cron context it can check drift for the wrong repo.

## Fail-on-revert check
A revert of the firing-proof tests would pass because the suite only greps for class labels in output — it never asserts any detector FIRES, so removing the cross-reference, pool-size, or age logic (classes 4-9) is undetectable.

## Status
Pending Manager dispensation
