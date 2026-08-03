# LAND-PUSH-WORKTREE-STATE — review fragment

## The defect (reproduced live, 2026-08-02)

`fleet/land-push.sh:59` reads the AUTONOMOUS lever from `$FLEET/state/AUTONOMOUS`,
where `FLEET` is the directory containing the *copy of the script that ran*:

```sh
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLAG="$FLEET/state/AUTONOMOUS"
```

`fleet/state/*` is gitignored (`.gitignore` line 10) except a small tracked allow-list
(`ROADMAP.tsv`, `OPERATOR-ACTIONS.md`, `RULE-REGISTRY.tsv`, `REDS-CORPUS.md`,
`RULE-SYNC-REGISTER.tsv`, `CONFIG-SOURCES.tsv`, `service-registry.tsv`). `AUTONOMOUS`
is not excepted, so it exists **only in the main checkout's runtime store**. Every linked
worktree therefore reads a lever that is always absent, and `land-push.sh` always exits 3
(REFUSE) when invoked from a worktree — even while the lever is ON in the main checkout.

Measured in this worktree (`/home/stack/charon-private-wt/LAND-PUSH-WORKTREE-STATE`,
a real linked worktree of `/home/stack/charon-private`):

```
$ git rev-parse --git-dir
/home/stack/charon-private/.git/worktrees/LAND-PUSH-WORKTREE-STATE      # linked worktree

$ ls /home/stack/charon-private/fleet/state/AUTONOMOUS                  # main: lever ON
-rw-r--r-- 1 stack stack 21 Jul 14 21:53 .../state/AUTONOMOUS

$ ls fleet/state/AUTONOMOUS                                             # worktree: absent
ls: cannot access 'fleet/state/AUTONOMOUS': No such file or directory

$ bash fleet/land-push.sh master ; echo "EXIT=$?"
land-push: AUTONOMOUS mode is OFF — the manager will not push.
  operator runs:  git -C /home/stack/code/charon push origin master
  or flip the lever: bash /home/stack/charon-private-wt/LAND-PUSH-WORKTREE-STATE/fleet/autonomous.sh on
EXIT=3
```

Two compounding facts surface in the reproduction: the refusal fired **while the lever was
ON in the main checkout** (this is the reported blocking bug), and the printed recovery
command names the *worktree's* `autonomous.sh` — running it would `mkdir -p` a lever into the
worktree's ignored `state/`, permanently desynchronising the two stores. The guidance is not
just unhelpful in a worktree, it actively widens the split.

## Same-class sweep ($FLEET/state/ readers of GLOBAL, main-only state)

The AUTONOMOUS lever readers are the same-assumption hits — every one of them resolves the
lever (or writes it) relative to the invoking copy of the script:

| Reader | Line | Kind | Worktree impact |
|---|---|---|---|
| `fleet/land-push.sh` | 59 | read | **THE defect** — lever always OFF in a worktree → exit 3, push blocked |
| `fleet/land-push.sh` | 72-77 | guidance | refusal names `$FLEET/autonomous.sh`, i.e. the worktree copy → wrong store on `on` |
| `fleet/land.sh` | 120 | read | same lever, same class. `land.sh` is a main-checkout path by doctrine (the work-lease commit-msg hook sanctions `land:*` in main, and it `cd`s to the target repo), so a worktree invocation is an anti-pattern — but the check happens *before* the `cd`, and a worktree-invoked `land.sh` would mis-read identically |
| `fleet/access-check.sh` | 17 | read | purely informational (`exit 0` always), runs at session start from the main checkout — a worktree run only mis-reports the lever, gates nothing |
| `fleet/autonomous.sh` | 8 | **write** | `FLAG="$FLEET/state/AUTONOMOUS"` — a worktree `autonomous.sh on` creates the lever in the ignored worktree store, not the main one |

The remaining `$FLEET/state/` readers (claims / done / submitted markers, run-logs, service
registries) read **per-ticket or per-run** state, not a global lever:
- the claims store was already unified via `git rev-parse --git-common-dir` by
  WORK-LEASE-WORKTREE-RESOLVE (`fleet/work-lease.sh:_state_root`), with fail-on-revert
  tests 16/17;
- the marker-dependent board gates (`validate_board.sh`, `reconcile-*`, `retire-done.sh`,
  `dark-work-check.sh`) are **already worktree-aware by design**: `land-push.sh`'s board gate
  detects a state-less checkout (`_SMODE` absent/empty/branch-diff, MED-F7) and runs the
  marker-independent subset instead of emitting phantom REDs;
- `plane-canary.sh`, `watchdog/*`, `research.sh`, `wci-actions.sh` run as main-checkout-bound
  services or write run-state, not gate a push.

So the same-assumption set is exactly the four AUTONOMOUS-lever sites. Nothing else reads a
global main-only lever through `$FLEET/state/` from a worktree.

## The fix (specification — the mechanism already exists)

Apply WORK-LEASE-WORKTREE-RESOLVE's resolution to the lever, not a new mechanism. Copy the
`_state_root` pattern from `fleet/work-lease.sh:39-52` and derive the lever root from
`git rev-parse --path-format=absolute --git-common-dir` (fallback: the relative form, then
`$FLEET` when not inside a repo), with the same guard that the resolved parent actually holds a
`fleet/`:

```sh
# ONE LEVER ACROSS WORKTREES: fleet/state/ is gitignored, so a linked worktree's own
# state/AUTONOMOUS is always absent. Resolve the lever from the git-common-dir, which is
# IDENTICAL for the main checkout and every linked worktree, so both read one lever.
_state_root() {
  if [ -n "${LAND_PUSH_STATE_ROOT:-}" ]; then printf '%s' "$LAND_PUSH_STATE_ROOT"; return 0; fi
  local gcd root
  gcd="$(git -C "$FLEET" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" \
    || gcd="$(git -C "$FLEET" rev-parse --git-common-dir 2>/dev/null)" || gcd=""
  if [ -n "$gcd" ]; then
    case "$gcd" in /*) :;; *) gcd="$(cd "$FLEET" && cd "$gcd" 2>/dev/null && pwd)" || gcd="";; esac
  fi
  if [ -n "$gcd" ]; then
    root="$(cd "$gcd/.." 2>/dev/null && pwd)" || root=""
    if [ -n "$root" ] && [ -f "$root/fleet/land-push.sh" ]; then printf '%s' "$root/fleet"; return 0; fi
  fi
  printf '%s' "$FLEET"
}
FLAG="$( _state_root )/state/AUTONOMOUS"
```

Then:
- **land-push.sh**: use the resolved `FLAG` (above), and fix the two guidance lines (74-75) to
  name the **resolved** fleet's `autonomous.sh` and the **main** checkout's lever path, so a
  worktree refusal never sends the operator at a worktree-store writer.
- **land.sh:120** and **access-check.sh:17**: same lever read — either switch to the shared
  resolver, or (for `land.sh`) explicitly `cd` to the resolved main checkout before reading.
  Minimal correct slice: a shared `_state_root` (or a `fleet/state-root.sh` helper both source)
  rather than three hand-rolled copies — two implementations of the same resolution WILL drift
  (the validate_board/rig-ci-scope split was re-used deliberately for exactly this reason).
- **autonomous.sh:8**: the **writer** is the one that must never write into a worktree store —
  resolve the same way so `autonomous.sh on` always touches the main checkout's `state/`.
  This is the assertion that keeps the read fixed: a lever written to the shared store can then
  be read from any worktree.

The env-var escape hatch (`LAND_PUSH_STATE_ROOT`) mirrors `WORK_LEASE_STATE_ROOT` and keeps
hermetic tests able to pin a throwaway store.

## Fail-on-revert (covering the worktree case)

New suite `fleet/tests/land-push-worktree-state.test.sh`, mirroring `work-lease.test.sh`
tests 16/17 and the `land-safety.test.sh` harness (copy the REAL `land-push.sh` into a temp
FLEET; real git repos; bare fs remote so the CI gate short-circuits at the non-github origin):

1. Build a real repo with `fleet/land-push.sh` + `fleet/push-verify.sh` at its root, commit,
   `git worktree add` a linked worktree, place `state/AUTONOMOUS` **in the main checkout only**.
2. Run the **worktree's** copy of `land-push.sh <branch> <bare-remote>`.
3. Assert it does **NOT** exit 3 (lever resolved from git-common-dir → main store → ON), and
   the push is attempted/refused for the RIGHT reason, not "AUTONOMOUS mode is OFF".
4. Revert = restore `FLAG="$FLEET/state/AUTONOMOUS"` → the worktree run exits 3 again → RED.

This is the assertion the ticket demands: the lever must read the same value from a linked
worktree as from the main checkout, exactly as tests 16/17 do for the claims store.

## Scope note (owns boundary)

This ticket's `owns:` is only `docs/review-log/LAND-PUSH-WORKTREE-STATE.md`, so no code was
changed here. The spec above is the deliverable; applying it touches `fleet/land-push.sh`,
`fleet/land.sh`, `fleet/access-check.sh`, `fleet/autonomous.sh` and a new `fleet/tests/*.sh` —
all outside this ticket's owns (and `pr-has-ticket` would RED a PR that edits `fleet/land-push.sh`
without a base-ref board ticket owning it). Follow-up ticket(s) with the proper `owns:` should
land the fix + the fail-on-revert suite.
