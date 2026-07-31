# HANDOFF-NAME-ALLOCATOR — Review Log

## Ticket
HANDOFF-NAME-ALLOCATOR: mechanized Jedi-name allocator that prevents session-name
reuse by computing a pool-minus-exclusion-set, deterministically claiming the first
available name, and failing loud when the pool is exhausted.

## Root cause being fixed
On 2026-07-23 a session free-picked the name `luminara-unduli` — already used
2026-07-21 (commit 6f29737) — so its session-end handoff write (73eb30c, PR #203)
landed ON TOP of the 07-21 file instead of a fresh one. The handoff carried a
GENERATED-STATE block ~30 commits stale. Confirmed root cause: session names are
a 100% model free-pick with NO mechanized allocator and NO check against history.
The session-bridge TTL (600s) structurally cannot remember a 2-day-old name.

## Design decisions

### Exclusion set = live-tree + git history
The exclusion set is the union of:
- **(a)** Names from `fleet/SESSION-HANDOFF-*.md` in the live tree (fast, O(glob))
- **(b)** Names from `git log --diff-filter=A --all -- 'fleet/SESSION-HANDOFF-*.md'`
  (the query that catches `luminara-unduli`: file deleted from tree but created in
  history)

The git-history half is load-bearing. The selftest (B1) proves this: an allocator
stripped of the git-history query claims `luminara-unduli`, while the real allocator
excludes it.

### Deterministic ordering
The pool file (`fleet/state/jedi-name-pool.txt`) is ordered alphabetically.
The allocator reads names in file order and picks the first non-excluded entry.
Given a fixed exclusion set, the result is deterministic.

### Claim-before-build (atomic stub creation)
The allocator writes an empty `fleet/SESSION-HANDOFF-<name>.md` stub via
`set -o noclobber` (O_EXCL) BEFORE printing the name. If two concurrent
invocations race for the same name, exactly one wins the atomic create;
the loser falls through to the next pool entry. This is the same pattern
as WORK-LEASE-GATE.

### Pool exhaustion = FAIL LOUD
When every pool name is either in the exclusion set or currently claimed,
the allocator exits non-zero with "pool exhausted" on stderr and prints
nothing on stdout. The operator must supply an explicit `-2`-suffixed
disambiguated name. Silent reuse is NEVER permitted.

### Belt-and-suspenders (NOT in this ticket's owns)
The ticket's accept criteria describe refuse-checks in `handoff.sh` and
`end-session.sh` that reject a session whose `SESSION-HANDOFF-$SESSION.md`
already has commits predating this process's start. These edits are NOT in
this ticket's `owns:` — they belong to a follow-up ticket. The allocator
itself is the primary guard; the refuse-checks are secondary (belt-and-suspenders).

## Files created/modified
| File | Status | Description |
|---|---|---|
| `fleet/state/jedi-name-pool.txt` | NEW | 69-entry checked-in Jedi name pool |
| `fleet/claim-jedi-name.sh` | NEW | Mechanized allocator with selftest |
| `fleet/tests/claim-jedi-name.test.sh` | NEW | Fail-on-revert test + pool integrity |
| `docs/review-log/HANDOFF-NAME-ALLOCATOR.md` | NEW | This review fragment |

## Test coverage
- **(A)** Regression fixture: `luminara-unduli` in git history, not in live tree → excluded
- **(A2)** `ki-adi-mundi` in both live tree and history → excluded
- **(B1)** Allocator without git-history half claims `luminara-unduli` → proves git-half is load-bearing
- **(C)** Pool exhaustion → non-zero exit + "pool exhausted" on stderr + no stdout
- **(D)** Two consecutive claims return different names
- **(2)** Pool file: exists, >30 entries, valid kebab-case slugs, no duplicates
- **(3)** Key historical names present in pool

## Adversarial review notes
- The allocator MUST be the FIRST wire in the Bootstrap block that handoff.sh emits
  (handoff.sh:86-90). The operator/model READS a name instead of choosing one.
- The git-history query uses `--all` to catch names from every branch, not just
  the current one — a name on a merged/abandoned branch is still "used."
- Non-Jedi session names (`recover-session`, `yoda-prev`) are intentionally absent
  from the Jedi pool; they would never be claimable anyway since git history excludes
  them. Future non-Jedi session names should use a separate allocator mechanism.
- Grand Master names (`yoda`, `luke-skywalker`, `satele-shan`) ARE in the pool but
  are excluded by git history; the session-bridge registration protocol enforces
  the manager-only reservation independently.
