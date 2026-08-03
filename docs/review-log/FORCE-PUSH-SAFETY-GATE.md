# FORCE-PUSH-SAFETY-GATE — Review Log

## Ticket
FORCE-PUSH-SAFETY-GATE: `--force` must PROVE it destroys nothing before pushing. After 19
correct `land-push.sh --force` rescues, the 20th was wrong and nearly destroyed a +905-line fix
on `fix/shared-namespace-contention`; only git's non-fast-forward refusal stopped it. The safety
must come from a check, not from an accident of history shape.

## Scope (owns-enforced)
`owns:` is ONLY `fleet/tests/force-push-safety.test.sh`. The production gate would live in
`fleet/land-push.sh` / `fleet/rescue-push.sh`, both owned by OTHER board tickets (land-push.sh
has a live board owner; RIG-CI-BASE-DEFAULT-BRANCH). Per the ownership doctrine (`owns:` wins,
out-of-owns files double-claim), the gate is delivered as an EMBEDDED REFERENCE implementation
inside the test suite — the test IS the gate spec. `fleet/land-push.sh` was NOT touched.

## What was done
`fleet/tests/force-push-safety.test.sh` (new, 13 assertions, hermetic `mktemp -d` + real bare
file:// remotes, no network):
- Reference gate: `fps_gate_check` = `count=$(git rev-list <local>..<remote>)`; count==0 →
  proceed, count>0 → REFUSE printing sha + subject + diffstat of every at-risk commit.
- `fps_destroy_override` = the SEPARATE, louder flag `--force-with-destroy=<reason>`; it names
  exactly what it discards.
- Fixed a real bug in the count computation: `wc -l` on an empty orphan list counts a blank line
  as 1 → FALSE REFUSAL on the anti-over-block path. Now `grep -c .` (empty → 0). Assertion 9
  (remote EXISTS but holds nothing unique → proceeds) pins this path — it fails on the old code.

## DONE CONTRACT coverage (all verified by execution)
- a. Near-miss reproduced: remote holds 1 unique fix commit, local holds 24 board commits;
  `--force` REFUSED and the commit is NAMED. Revert the check → RED (R1: 3, 3b, 4, 4b fail).
- b. Remote has nothing unique → `--force` proceeds (anti-over-block: assertions 1, 9).
- c. `--force-with-destroy` DOES proceed and names what it discarded (5, 5b).
- d. Refusal shows sha + subject + diffstat (4, 4b) — enough to decide without digging.
- e. Normal non-force pushes unaffected (7, 8, 10).

## FAIL-ON-REVERT — all four documented reverts run to RED
- R1 (gate always proceeds): RED on 3, 3b, 4, 4b.
- R2 (drop sha+subject+diffstat printing): RED on 4, 4b.
- R3 (override routes through the gate): RED on 5, 5b.
- R4 (non-force consults the gate): RED on 10.
Full suite GREEN: 13 pass / 0 fail; `bash -n` OK; shellcheck clean.

## Live dogfood (real branch, offline against the local clone of charon-private)
`fix/shared-namespace-contention` still diverges on the private origin: 1 unique commit
(6e8247b, the real fix: 5 files changed, 1100 insertions, 73 deletions — same class as the
incident's 63ece1f) vs 91 master-side commits. The reference gate:
```
fps: REFUSING --force — origin/fix/shared-namespace-contention holds 1 commit(s) this push would destroy:
fps:   6e8247b...  fix(shared-namespace-contention): split claim from check, idempotent re-claim, orphan reap, namespaced scratch
fps:     5 files changed, 1100 insertions(+), 73 deletions(-)
```
REFUSED, named the at-risk commit, did NOT push. The incident branch/commit still live on the
private origin (63ece1f has since advanced to 6e8247b on the same fix).

## Key decisions
- Embedded reference gate rather than editing land-push.sh (owns-enforced; see Scope).
- `--force-with-destroy` must be a separate flag, not a `--force` sub-mode: it routes around the
  gate by design and must name its reason in its own invocation.
- The gate stays fail-OPEN on "branch does not exist on remote" and on rev-list error (matches
  today's behavior; the 19 legitimate rescues must keep working).

## Notes / follow-ups
- Pre-existing false-red on master (NOT this change): `pytest` fails
  `fleet/capability/tests/test_tier_classify.py::test_live_board_drift_is_exactly_the_pending_retiers`
  on origin/master itself.
- NEXT: wire this reference gate into the production push path (land-push.sh --force →
  `fps_gate_check`, rescue-push.sh diverged-shape), and add this suite to the
  `fleet/checks/rig-ci-scope.sh` CI_SUITES allowlist so it runs in CI.
