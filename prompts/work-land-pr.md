# WORK-LAND-PR — close the loop: open a PR (behind a flag) + a real review gate

## Why (verified on origin/master 2026-06-27 — re-confirm with `--help`/grep before editing)
`charon work` finishes a unit but only PARTIALLY closes the loop, and its quality bar is weaker
than it should be:

- (a) **PR is never opened.** `run_work` (cli.py:~822) drives each DONE unit through
  `land.land_unit(...)` (cli.py:~915), which is READ-ONLY: commits on a DETACHED HEAD (no branch),
  runs the acceptance gate, computes a propose/hold verdict — but NEVER pushes and NEVER opens a
  PR. `land.open_pr` (land.py:~411) exists but is invoked ONLY from the separate
  `charon land --open-pr` CLI path (cli.py:~120-126), never from `work`. So an autonomous run
  produces local commits + a verdict and stops — nothing lands as a reviewable PR.
- (b) **The real reviewer is not wired into the work path.** `adapters/review.py` ships
  `GatewayReviewer` (a real cross-model consensus reviewer that calls the loopback Charon gateway);
  the deterministic `MockReviewer` lives in `adapters/review_mock.py`. Only `charon run` wires a
  reviewer, and it wires the MOCK (cli.py:~41-42,55). The `work` path (run_work → CoordinatorRunner)
  passes NO reviewer → default L1, no review gate. So `GatewayReviewer` is dead-on-arrival for
  autonomous work; the only bar is the acceptance checks.

## What to build (ONE ticket, both parts — operator decision 2026-06-27)
**(a) Open a PR behind a flag.** Add a `work` flag (e.g. `--open-pr` / `--propose`, **OFF by
default, fail-closed**) that, for each unit whose verdict is *propose*, creates a branch + pushes +
calls `open_pr` — producing a DRAFT PR. **NEVER auto-merge** (ADR-0010 D5 propose-default is
non-negotiable; a human/other-agent merges). When the flag is off, behavior is exactly as today
(read-only, no push).

**(b) Wire the real reviewer.** Thread `GatewayReviewer` (NOT the mock) into the work path so each
unit gets a real cross-model adversarial review gate in addition to the acceptance checks. Construct
it where run_work builds the CoordinatorRunner and pass it through (mirror how `charon run`
constructs+passes its reviewer, but use GatewayReviewer). It routes via the loopback gateway, so it
composes with the now-merged WORK-GATEWAY-WIRE credential forwarding.

## Hard constraints
- **NEVER auto-merge** — propose-default only; push/PR strictly behind the explicit flag, fail-closed
  when off.
- Agent/provider-agnostic; product-clean (no SLOP/fleet/rig leak); privileged core stdlib-only;
  no secrets committed.
- The review gate must not silently weaken acceptance checks — it's additive.

## Acceptance
- `tests/test_work_land.py` (new): with the flag ON, a *propose* unit triggers branch+push+open_pr
  (assert at the seam — mock the push/PR call) and produces a DRAFT PR request; it NEVER merges.
  With the flag OFF, the work path stays read-only (no push/PR) — exactly today's behavior.
- A test that the work path constructs and uses `GatewayReviewer` (not MockReviewer) — assert the
  reviewer threaded into the runner is the gateway one.
- Existing run_work / CLI tests still GREEN (update `tests/test_cli.py` only as needed for the new
  flag; keep changes minimal).

## CONSTRAINTS
Own ONLY: `src/charon/cli.py`, `src/charon/land.py`, `src/charon/adapters/review.py`,
`src/charon/coordinator.py`, `tests/test_work_land.py`, `tests/test_cli.py`. Stdlib core only; no
`pip install -e`; no secrets committed. Gate GREEN every commit:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`.
Conventional commits; new behavior ships with its test in the same commit. Review note →
`docs/review-log/WORK-LAND-PR.md` (per-ticket fragment; NEVER the shared REVIEW-LOG.md).
Open a DRAFT PR (base master), run `submit.sh WORK-LAND-PR`, then STOP — never merge. If a fix
genuinely needs a file outside owns, STOP and `release.sh WORK-LAND-PR` with the reason.

NOTE: `coordinator.py` is included for threading the reviewer into CoordinatorRunner; if the wiring
turns out to live entirely in cli.py, leaving coordinator.py untouched is fine (owns is a ceiling,
not a quota).

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
