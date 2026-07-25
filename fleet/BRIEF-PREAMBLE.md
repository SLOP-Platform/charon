# BRIEF PREAMBLE — standing rules for every sub-session

Referenced by briefs as: *"Read `fleet/BRIEF-PREAMBLE.md` first — it is binding."*
Exists so briefs stop restating ~200 words of identical rules. Task-specific FACTS
(file:line, prior findings, "do not re-derive") still belong in the brief itself —
those prevent rework and must not be compressed away.

## 1. GREEN IS NOT PROOF
A passing result is evidence only if ALL hold:
- **RED-PROOFED** — you made it fail on purpose and observed it. Report both exit codes.
- **NON-VACUOUS** — zero items examined is RED, never a silent pass.
- **UN-GAMED** — no skip/xfail/exemption without a written, linked reason.
- **NOT INERT** — exercises real, wired code on the production path.
- **FAIL-LOUD** — failure exits non-zero and is NEVER masked by `| tail`, `| head`,
  `|| true`, or a missing `set -o pipefail`.

Verify by EXECUTION, not by reading. Say explicitly what you proved by running vs by reading.

## 2. Fix the CLASS, not the instance
On finding any defect: name the class, auto-scan for other instances (do not wait to be
asked), and fix or ticket the class as ONE shared primitive. Fixing only the instance
while the class stands is itself a defect.

## 3. ANTI-ACCRETION (hard)
Extend an EXISTING script/gate. A new standalone script is FORBIDDEN unless the brief
says otherwise. Adopt-first: a maintained tool or an already-built internal module beats
hand-rolling. Before building, check whether it already exists — this rig repeatedly
rebuilds things it already has.

## 4. Never dismiss a pre-existing red
Investigate and fix, or report it precisely. "Not mine" is not a disposition. Do not fix
unrelated reds you were not asked to touch — report them separately.

## 5. Tests must be reachable by a real runner
`fleet/gate.sh` matches `fleet/tests/*.test.sh`. **A `test_*.sh` name is NEVER matched.**
`fleet/checks/rig-ci-scope.sh:CI_SUITES` is the CI allowlist. A red-proof no runner
executes is not evidence. Confirm your test actually ran and say how you confirmed.

## 6. Work-lease
Acquire via the MAIN checkout's `/home/stack/charon-private/fleet/work-lease.sh` invoked
from your worktree cwd — the worktree's own copy writes to a different claims store and
the hook will not see it. Subcommands on master: `acquire|check|holds|bind|dispatch|release`.
**Plus `guard-branch` on branch `feat/branch-ticket-map-gate` (`b784de1`)** — the creation-time
gate at `work-lease.sh:408`, wired at `fleet-droid.sh:375`, refusing a branch that maps to no
board ticket. It is NOT on master, so grepping master will wrongly report it absent.

**Method note, learned the hard way:** "X does not exist" is only true if you checked the right
ref. Two sessions concluded `guard-branch` was missing by grepping master while it lived on an
unlanded branch, and one of them nearly wrote that error into three tickets. **Always state
which ref you checked when you report something missing.**

Release when done. **Do NOT use `WORK_LEASE_BYPASS=1`** — report the refusal instead,
unless the brief explicitly authorises it.

## 7. Git / landing
- `land.sh` DOES create PRs (`:395` create, `:399` ready, `:404` merge) — it is the whole
  lifecycle. It needs HEAD on the branch; use `land-push.sh <branch> [repo]` for a named branch.
- `git add` aborts entirely if ANY pathspec fails — nothing stages. Always check
  `git diff --cached --name-only` before committing.
- **`git cherry` and `git log origin/master..<branch>` give FALSE NEGATIVES here** — work
  lands by RE-DERIVATION, not cherry-pick, so dead branches still report unique commits.
  Prove liveness by CONTENT: diff owned files vs `origin/master`, and look for an archived
  `status: done` ticket.
- Never `--force`, never `git reset --hard` on shared state. Do not push unless told.

## 8. Repos
- PRODUCT `/home/stack/code/charon` is **PUBLIC**: never commit `/home/stack` paths,
  internal IPs, hostnames, or secrets. Never print a token value.
- RIG `/home/stack/charon-private` is private tooling. Do not let rig paths leak into product.
- **Do NOT run `charon gate` on `feat/diff-cover-mutmut-adopt`** — unbounded pytest↔gate
  recursion; it has fork-starved this box.

## 9. Collisions
Never two writers on one file. Board files are per-ticket, but `fleet/state/ROADMAP.tsv`
is shared — only the designated owner writes it. Check `git worktree list` before assuming
a branch is free; a branch checked out elsewhere cannot be checked out again.

## 10. Reporting
Terse. Write findings to a file; reply with a pointer plus the requested line budget.
No narration, no pasting diffs or logs. Report failures plainly — a wrong green is worse
than a red. If you could not do something, say so rather than working around it.
Finite timeouts on every command.
