#!/usr/bin/env bash
# fleet/tests/lib/sandbox.sh — sandbox CONTAINMENT + FAIL-CLOSED helpers for fleet tests.
#
# ── WHY THIS FILE EXISTS (2026-08-01 incident, three faces, one root) ─────────────────
#
# Every fleet test builds its fixtures with a bare `mktemp -d`. `mktemp` roots its output
# at $TMPDIR. Nothing in the rig ever CONSTRAINED $TMPDIR, so when a caller exported a
# TMPDIR that pointed INSIDE a git work tree (measured live: fleet/state/tmpdir-land/ and
# fleet/state/pytmp-inert/, 56M of pytest/bash fixtures, plus a whole-checkout copy under
# scratch/fleet-copy/), every test sandbox — including nested `git init` repos and
# `git worktree add` checkouts — was created INSIDE THE REPO BEING TESTED. Consequences,
# all three observed on the same day:
#
#   FACE 1 — LIVE-REPO WRITES. A test does `( cd "$D/seed" && ... git commit )`. Fleet
#     tests run under `set -uo pipefail` — note the missing `-e` — so when $D had been
#     deleted out from under the run, `cd` failed, the subshell KEPT GOING, and the git
#     commands executed against the CURRENT WORKING DIRECTORY, i.e. the live checkout.
#     Because those tests also `export GIT_AUTHOR_EMAIL=t@t`, the result is committed as
#     `t <t@t>`. 16 such commits (subjects c1..c4) and the fixture file `f.txt` reached
#     origin/master. This is the FALL-THROUGH the fail-closed helpers below exist to stop.
#
#   FACE 2 — `git add` SWEEPS THE SANDBOXES IN. Sandboxes inside the tree are just
#     untracked files to git. A blanket `git add` hits nested repos and half-built
#     worktrees and dies with exit 128:
#         warning: adding embedded git repository: scratch/fleet-copy/.../repo
#         error: '.../worktree/' does not have a commit checked out
#         fatal: adding files failed
#     That killed droid tabs outright.
#
#   FACE 3 — MASS SANDBOX DELETION. Any tool that `rm -rf`'s "its" temp root (see the
#     trap-expansion defect fixed in fleet/review-pool.sh and fleet/ladder-health.sh)
#     deletes every OTHER concurrent test's sandbox with it, because they all share the
#     one in-tree root. ~118 tests reported "killed (no exit status recorded)" and one
#     reviewer returned a SPURIOUS GREEN.
#
# The root fix is containment: a test sandbox must never be inside a git work tree. Get
# that right and Face 2 and Face 3 are both impossible, and Face 1 loses its trigger.
# Fail-closed is the belt to that braces: even if a sandbox does vanish, no test may
# silently fall through to running git in the live checkout.
#
# ── USAGE ────────────────────────────────────────────────────────────────────────────
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/sandbox.sh"
#   sandbox_init                 # once, near the top: pins a contained $TMPDIR
#   D="$(sandbox_mk)"            # contained mktemp -d (asserted outside every work tree)
#   ( sandbox_cd "$D/seed"; git commit ... )     # fail-closed cd — aborts, never falls through
#
# `sandbox_init` is idempotent and safe to call from a test that fleet/gate.sh already
# ran `sandbox_init` for: the inherited TMPDIR is re-validated, and kept if it is clean.

# ── sandbox_die <msg...> — LOUD, non-zero, unconditional. Never returns. ──────────────
# Deliberately not a soft `return 1`: the whole failure mode being prevented is a test
# that keeps executing git commands after its sandbox is gone.
sandbox_die(){
  printf '\n' >&2
  printf 'FATAL sandbox-guard: %s\n' "$*" >&2
  printf 'FATAL sandbox-guard: refusing to continue — a fleet test with a missing or\n' >&2
  printf 'FATAL sandbox-guard: in-tree sandbox would run git against the LIVE checkout.\n' >&2
  printf 'FATAL sandbox-guard: (cwd=%s)\n' "$PWD" >&2
  printf '\n' >&2
  exit 99
}

# ── sandbox_in_worktree <path> — 0 if <path> is inside a git work tree, else 1. ───────
# `git rev-parse --show-toplevel` IS the containment predicate: it is exactly the
# discovery walk that a stray `git add` / `git commit` would perform from that directory.
# Testing anything else (a /tmp/* prefix match, a repo-root string compare) approximates
# it and misses the cases that actually bit us — worktrees, nested checkouts, a copy of
# the repo parked under scratch/.
sandbox_in_worktree(){
  local p="$1"
  [ -d "$p" ] || p="$(dirname "$p")"
  [ -d "$p" ] || return 1
  git -C "$p" rev-parse --show-toplevel >/dev/null 2>&1
}

# ── sandbox_init — pin $TMPDIR to a root that is NOT inside any git work tree. ────────
# Exported, so every child (`mktemp`, `pytest`, `git worktree add`, python's tempfile)
# inherits containment without any of them being modified. This is the single choke point
# that covers all 124 fleet test files at once.
sandbox_init(){
  local cand
  for cand in "${TMPDIR:-}" /tmp /var/tmp; do
    [ -n "$cand" ] || continue
    [ -d "$cand" ] || continue
    [ -w "$cand" ] || continue
    if sandbox_in_worktree "$cand"; then
      # A caller handed us an in-tree TMPDIR. Do NOT silently honour it and do NOT
      # silently ignore it either — say so, then fall through to the next candidate.
      printf 'sandbox-guard: rejecting in-tree TMPDIR=%s (inside git work tree %s)\n' \
        "$cand" "$(git -C "$cand" rev-parse --show-toplevel 2>/dev/null)" >&2
      continue
    fi
    TMPDIR="$cand"; export TMPDIR
    return 0
  done
  sandbox_die "no usable temp root: every candidate (TMPDIR, /tmp, /var/tmp) is missing, unwritable, or inside a git work tree"
}

# ── sandbox_mk [template] — a contained `mktemp -d`. ──────────────────────────────────
# Asserts containment AFTER creation, not just before: TMPDIR could be a symlink into a
# work tree, or a repo could be initialised at a parent between the two moments.
sandbox_mk(){
  sandbox_init
  local d
  d="$(mktemp -d "${TMPDIR%/}/${1:-fleet-sandbox}.XXXXXXXX")" \
    || sandbox_die "mktemp -d failed under TMPDIR=$TMPDIR"
  if sandbox_in_worktree "$d"; then
    sandbox_die "created sandbox is INSIDE a git work tree: $d (toplevel $(git -C "$d" rev-parse --show-toplevel 2>/dev/null))"
  fi
  printf '%s\n' "$d"
}

# ── sandbox_require <dir> — fail-closed existence assertion. ──────────────────────────
sandbox_require(){
  [ -n "${1:-}" ] || sandbox_die "sandbox_require called with no path"
  [ -d "$1" ]     || sandbox_die "sandbox vanished (or was never created): $1"
}

# ── sandbox_cd <dir> — THE fail-closed replacement for a bare \`cd\` in a fixture. ──────
# `( cd "$D/seed" && ... )` looks safe but is not: under `set -uo pipefail` a failed `cd`
# does not stop the subshell, and `&&` only guards the FIRST command after it. This
# aborts the whole process instead of continuing in the live checkout.
sandbox_cd(){
  sandbox_require "${1:-}"
  cd "$1" || sandbox_die "cd failed into an existing sandbox dir: $1"
}

# ── sandbox_rm <path> — delete a sandbox, refusing to delete anything ABOVE one. ──────
# THE DOMINANT ROOT CAUSE, measured. fleet/tests/ladder-health.test.sh's cleanup was
# `rm -rf "$(dirname "$FLEET")"`, and its `mk_fleet` returns the mktemp dir ITSELF — so
# `dirname` walked one level UP, out of the sandbox and into $TMPDIR, the temp root SHARED BY
# EVERY CONCURRENTLY RUNNING TEST. Under gate.sh's bounded-concurrency fan-out that fired 12
# times per run. Measured effect: 124/124 tests "killed (no exit status recorded)" — fleet/gate.sh
# completely unrunnable — plus one reviewer GREEN that was purely an artefact of a suite that
# never ran, plus the vanished sandboxes that triggered the live-repo fall-through.
#
# Deliberately a RUNTIME guard, not a static lint. Whether a computed path escapes its sandbox
# is not statically decidable: two other suites (worktree-leak-guard.test.sh,
# test_land_safe_sync.sh) use the identical `rm -rf "$(dirname "$X")"` text CORRECTLY, because
# their fixture builders return "$root/<subdir>" so dirname lands back on the sandbox. A lint
# on the text would red those and get itself disabled. This checks the only thing that matters:
# is the target at or above the temp root.
sandbox_rm(){
  local target="${1:-}"
  [ -n "$target" ] || sandbox_die "sandbox_rm called with an empty path (would have been a bare 'rm -rf')"
  sandbox_init
  local root="${TMPDIR%/}"
  # Resolve so `.`/`..`/symlink games cannot smuggle an escape past the prefix test.
  local abs; abs="$(cd "$target" 2>/dev/null && pwd -P)" || abs="$target"
  case "$abs" in
    /|"$HOME"|"$root") sandbox_die "refusing to delete '$abs' — that is the temp root (or \$HOME, or /), not a sandbox. Delete the sandbox itself; never a path derived by walking UP out of it." ;;
    "$root"/*) ;;   # inside the temp root: a real sandbox, fine
    *) sandbox_die "refusing to delete '$abs' — it is OUTSIDE the temp root ($root), so it is not this run's sandbox." ;;
  esac
  rm -rf "$abs"
}
