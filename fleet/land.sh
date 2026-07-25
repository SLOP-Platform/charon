#!/usr/bin/env bash
# land.sh — THE sanctioned merge/land path for the manager. ONE command:
#   commit pending work -> GATE (refuse on red) -> branch -> push -> PR -> merge -> sync local base.
# Raw `git push`/`git merge` are deny-listed and kept getting denied + shipping UNGATED merges; this
# wrapper is the allowed path (its git ops run inside the script, not as top-level denied commands).
# Self-gates on the AUTONOMOUS lever (like land-push.sh): OFF -> refuse and print the manual command.
#
# Usage: land.sh <feature-branch> [repo] [--base <base>] [--gate "<cmd>"] [--msg "<commit msg>"]
#   default repo = /home/stack/code/charon ; default base = master
#   gate auto-detects: charon.cli gate (product) / validate_board (fleet) / pytest — or pass --gate.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$FLEET/push-verify.sh"   # pv_branch_holder / pv_push_verified — prove the push (step 4/5).
# _lib.sh supplies the CANONICAL board-field readers (ticket_owns / ticket_for_branch) used by the
# step-1 dirty scoping. Guarded: a minimal test fixture may not carry it, and step 1 then fails
# CLOSED (no `owns:` resolvable -> refuse unless --commit-dirty), never open.
# shellcheck source=/dev/null
[ -f "$FLEET/_lib.sh" ] && source "$FLEET/_lib.sh"

# safe_sync_base — step 7, factored out and hardened (LAND-SH-SAFE-SYNC).
# Sync the local base branch to origin AFTER a landed merge. HARD INVARIANT: this must
# NEVER `reset --hard` / `clean -fd` over an uncommitted DIRTY working tree — that is how a
# whole session's uncommitted work got destroyed. Rules:
#   * FAST-FORWARD ONLY. On divergence (base has local commits not on origin) → abort LOUDLY,
#     print the manual command, leave the tree untouched. Never force the ref back.
#   * Clean tree            → checkout base + `merge --ff-only` (no reset).
#   * Dirty tree ON base    → SKIP the sync loudly (can't leave base without risking the work).
#   * Dirty tree off base   → `git stash -u` (incl. untracked) → FF base → return → `stash pop`,
#     so uncommitted + untracked files are preserved; a pop conflict keeps them safe in the stash.
safe_sync_base() {
  local repo="$1" base="$2" branch="${3:-}"
  cd "$repo" || { echo "land: WARN sync: no repo $repo — skipping base sync" >&2; return 0; }
  git fetch -q origin || { echo "land: WARN sync: fetch failed — skipping base sync" >&2; return 0; }
  local cur; cur="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  local dirty=""; [ -n "$(git status --porcelain)" ] && dirty=1

  # W0b FIX 1 (WORKTREE-HOLDER GAP). LAND-SAFETY-FIX taught step 4 to detect a worktree holding
  # the target branch, but this function never got the same treatment. When any worktree holds
  # <base>, EVERY `git checkout "$base"` below dies with
  #   fatal: '<base>' is already used by worktree at '<path>'
  # and the old code fell into "checkout $base failed — skipping sync" and returned 0. Observed
  # firing three times during the W1 lands: it warned, touched nothing, and SILENTLY did not do
  # its job — exactly the class fixed one level up. Reuse the SAME primitive (pv_branch_holder),
  # do NOT add a second holder detector. Correct alternate path: the holder IS the checkout that
  # can fast-forward <base>, so perform the FF THERE. If the holder cannot take it, REFUSE
  # LOUDLY with rc 3 — never a silent 0. Checked BEFORE the dirty split because both arms below
  # check out <base>.
  local holder
  if holder="$(pv_branch_holder "$repo" "$base")"; then
    echo "land: sync: '$base' is held by worktree $holder — this checkout CANNOT check it out; syncing THERE."
    if [ -n "$(git -C "$holder" status --porcelain 2>/dev/null)" ]; then
      echo "land: REFUSING sync: worktree $holder holds '$base' and is DIRTY — not touching it." >&2
      echo "land:   sync by hand: (cd $holder && git stash -u && git merge --ff-only origin/$base && git stash pop)" >&2
      return 3
    fi
    if [ "$(git -C "$holder" rev-parse --abbrev-ref HEAD 2>/dev/null)" != "$base" ]; then
      echo "land: REFUSING sync: $holder holds '$base' but is not ON it — cannot fast-forward safely." >&2
      return 3
    fi
    if git -C "$holder" merge --ff-only -q "origin/$base"; then
      echo "land: '$base' synced to origin in $holder -> $(git -C "$holder" rev-parse --short HEAD)"
      return 0
    fi
    echo "land: REFUSING sync: '$base' in $holder DIVERGED from origin/$base (not a fast-forward) — NOT resetting." >&2
    echo "land:   resolve by hand: (cd $holder && git log --oneline $base..origin/$base)" >&2
    return 3
  fi

  if [ -z "$dirty" ]; then
    git checkout -q "$base" || { echo "land: WARN sync: checkout $base failed — skipping sync" >&2; return 0; }
    if git merge --ff-only -q "origin/$base"; then
      echo "land: '$base' synced to origin -> $(git rev-parse --short HEAD)"
    else
      echo "land: WARN sync: local '$base' DIVERGED from origin/$base (not a fast-forward) — NOT resetting." >&2
      echo "land:   resolve by hand: (cd $repo && git checkout $base && git log --oneline $base..origin/$base)" >&2
    fi
    return 0
  fi

  # DIRTY working tree — uncommitted and/or untracked work is present. NEVER destroy it.
  if [ "$cur" = "$base" ]; then
    echo "land: WARN sync: working tree is DIRTY on '$base' — SKIPPING base sync to PROTECT uncommitted work." >&2
    echo "land:   sync manually once clean: (cd $repo && git stash -u && git merge --ff-only origin/$base && git stash pop)" >&2
    return 0
  fi
  if ! git stash push -u -q -m "land-safe-sync ${branch:-$base}"; then
    echo "land: WARN sync: could not stash dirty tree — SKIPPING base sync to PROTECT uncommitted work." >&2
    echo "land:   sync manually: (cd $repo && git checkout $base && git merge --ff-only origin/$base)" >&2
    return 0
  fi
  echo "land: sync: stashed dirty working tree before base sync"
  if ! git checkout -q "$base"; then
    echo "land: WARN sync: checkout $base failed — restoring stash, skipping sync" >&2
    git checkout -q "$cur" 2>/dev/null || true
    git stash pop -q 2>/dev/null || echo "land: WARN sync: your work is SAFE in 'git stash' (git stash list)" >&2
    return 0
  fi
  if git merge --ff-only -q "origin/$base"; then
    echo "land: '$base' synced to origin -> $(git rev-parse --short HEAD)"
  else
    echo "land: WARN sync: local '$base' DIVERGED from origin/$base (not a fast-forward) — NOT resetting." >&2
  fi
  git checkout -q "$cur" 2>/dev/null || true   # pop onto the branch the work came from
  if git stash pop -q; then
    echo "land: sync: restored stashed working tree on '$cur'"
  else
    echo "land: WARN sync: stash pop conflicted — your work is SAFE in 'git stash' (git stash list; stash@{0})." >&2
  fi
}

# Hidden maintenance/test entrypoint: run ONLY the dirty-safe base sync, then exit. It performs
# no push/merge (a local FF sync only), so it bypasses the AUTONOMOUS + gate machinery below.
if [ "${1:-}" = "--sync-only" ]; then
  shift
  safe_sync_base "${1:?usage: land.sh --sync-only <repo> <base> [branch]}" "${2:?land: --sync-only needs <base>}" "${3:-}"
  exit $?
fi

if [ ! -e "$FLEET/state/AUTONOMOUS" ]; then
  echo "land: AUTONOMOUS off — the manager will not land. Run manually or: bash $FLEET/autonomous.sh on" >&2
  exit 3
fi

BRANCH="${1:?usage: land.sh <feature-branch> [repo] [--base b] [--gate cmd] [--msg m] [--force]}"; shift
REPO="/home/stack/code/charon"; BASE=""; GATE=""; MSG=""; FORCE=""; COMMIT_DIRTY=""
while [ $# -gt 0 ]; do case "$1" in
  --base)  BASE="$2"; shift 2;;
  --gate)  GATE="$2"; shift 2;;
  --msg)   MSG="$2";  shift 2;;
  --force) FORCE=1;   shift;;
  --commit-dirty) COMMIT_DIRTY=1; shift;;
  *)       REPO="$1"; shift;;
esac; done

cd "$REPO" || { echo "land: no repo $REPO" >&2; exit 1; }
# MULTI-REPO: derive the base branch from the repo's own default when not given (charon->master,
# keystone->main). Keeps `land.sh <branch> <repo>` working for any repo with no --base guesswork.
if [ -z "$BASE" ]; then
  BASE="$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null)"
  [ -n "$BASE" ] || BASE="master"
fi
echo "land: repo=$REPO base=$BASE branch=$BRANCH"

# EXISTING-BRANCH GUARD (2026-07-23): land.sh's model snapshots the CURRENT HEAD onto <branch>. If
# <branch> ALREADY exists locally with commit(s) NOT reachable from HEAD (a droid's submitted PR branch,
# a recovered/edited branch), that model resets it to HEAD and the land fails "NOT PROVEN" (bit stass-
# allie 3x). The tool for landing an existing named branch is land-push.sh; or put HEAD on it first.
# Fires ONLY when the branch exists AND diverges from HEAD — inert for the normal `checkout -b`-from-HEAD
# flow (HEAD == branch). Fail-safe: any rev-parse error skips the guard.
if git -C "$REPO" rev-parse --verify --quiet "refs/heads/$BRANCH" >/dev/null 2>&1; then
  _lg_head="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || true)"
  _lg_br="$(git -C "$REPO" rev-parse "refs/heads/$BRANCH" 2>/dev/null || true)"
  if [ -n "$_lg_head" ] && [ -n "$_lg_br" ] && [ "$_lg_head" != "$_lg_br" ] \
     && [ -n "$(git -C "$REPO" log --oneline "$_lg_head..$_lg_br" 2>/dev/null)" ]; then
    echo "land: REFUSING — branch '$BRANCH' already has commit(s) not in HEAD; land.sh snapshots HEAD and would clobber/desync it." >&2
    echo "land:   VERIFIED fix — put HEAD on the branch, then re-run: (cd $REPO && git checkout -B $BRANCH $_lg_br) && bash $FLEET/land.sh $BRANCH $REPO" >&2
    echo "land:   Or use the by-name landing tool: bash $FLEET/land-push.sh $BRANCH $REPO" >&2
    exit 6
  fi
fi

# 1. commit pending work — SCOPED TO THE TICKET'S `owns:` (LAND-DIRTY-SCOPE, 2026-07-19)
#
# THE DEFECT this replaces (present since 368053b, the file's creation): step 1 was a bare
#   [ -n "$(git status --porcelain)" ] && git add -A && git commit -m "${MSG:-land: $BRANCH}"
# It ran in $REPO on whatever branch HEAD is — so when HEAD was on `master` it committed
# EVERYTHING in the tree straight onto master, BEFORE the gate (step 3) and BEFORE the
# branch/holder refusal (step 4/5). Step 4/5 then refused and nothing was pushed, leaving local
# master diverged from origin with a junk commit on it. Real contamination it produced:
#   4ea0a34  1462 files, incl. graphify-out/graph.json (164k lines)
#   075ac58  12 files, incl. a stash-backup patch      94a6783  7 session-notes
#   58234f6 / 2f630dc  stray submit-auto notes
# submit.sh/checkin.sh write fleet/session-notes/ continuously, so the tree is dirty on nearly
# every land and this fired nearly every time. Compounding it, neither land.sh nor push-verify.sh
# ever calls leak-guard.sh (still true — see the note at step 3.5), so `git add -A` swept
# unreviewed content into a commit with NO secret scan in front of it.
#
# THE INTENT IS LEGITIMATE and is preserved: the manager edits in the live tree and then lands.
# What changes is the SCOPE — we commit the ticket's OWN files, not the whole tree:
#   * ticket declares `owns:`  -> stage ONLY those paths; any other dirty file -> REFUSE, listing it
#   * no `owns:` resolvable    -> REFUSE unless --commit-dirty is passed
#   * --commit-dirty           -> the ONLY way to sweep unowned files (explicit, logged)
# REJECTED ALTERNATIVE: a blanket `git stash -u` / restore around step 1. This tree is read by
# ~61 live worktrees and running droids; whole-tree stashing races every one of them. (Contrast
# safe_sync_base() above, whose stash is scoped to a moment when it is about to leave the branch
# anyway and which carries an explicit never-destroy invariant — that care is matched here by
# refusing outright rather than by mutating a tree other processes are reading.)
#
# `owns:` is read through _lib.sh's ticket_owns()/ticket_for_branch() — the CANONICAL board-field
# readers. Do NOT add an awk/grep over `owns:` here: per-consumer re-parsing is the drift class
# that already produced four disagreeing copies of `parked:`.
LAND_STAGE=()
land_scope_plan(){
  LAND_STAGE=()
  [ -n "$(git status --porcelain)" ] || return 0          # clean tree — nothing to do

  if [ -n "$COMMIT_DIRTY" ]; then
    echo "land: --commit-dirty — sweeping the WHOLE dirty tree into one commit (explicit opt-in):" >&2
    git status --porcelain >&2
    LAND_STAGE=(-A)
    return 0
  fi

  # Resolve this land's ticket and its declared `owns:` paths.
  local tid="" owns=""
  if command -v ticket_for_branch >/dev/null 2>&1; then
    tid="$(ticket_for_branch "$BRANCH" 2>/dev/null || true)"
    [ -n "$tid" ] && owns="$(ticket_owns "$tid" 2>/dev/null || true)"
  fi
  # `owns:` paths are relative to the TICKET'S repo. If this land is running against a DIFFERENT
  # checkout than the ticket declares, those paths mean nothing here — treat it as no owns.
  if [ -n "$owns" ] && command -v ticket_repo_path >/dev/null 2>&1; then
    local trepo; trepo="$(ticket_repo_path "$tid" 2>/dev/null || true)"
    if [ -n "$trepo" ] && [ "$(cd "$trepo" 2>/dev/null && pwd -P)" != "$(pwd -P)" ]; then
      echo "land: note: ticket $tid declares repo '$trepo' but this land runs in '$(pwd -P)'" >&2
      owns=""
    fi
  fi

  if [ -z "$owns" ]; then
    echo "land: ####################################################################" >&2
    echo "land: # REFUSING to commit a DIRTY tree with no 'owns:' scope." >&2
    echo "land: # branch '$BRANCH' -> ticket '${tid:-<none found>}' declares no usable owns: paths," >&2
    echo "land: # so land.sh cannot tell your work from unrelated dirt (session-notes, build" >&2
    echo "land: # output, other droids' scratch). A blind 'git add -A' here is what put 1462" >&2
    echo "land: # unrelated files on master in 4ea0a34. Nothing was staged or committed." >&2
    echo "land: # DIRTY FILES in $(pwd -P):" >&2
    git status --porcelain >&2
    echo "land: # fix by ONE of:" >&2
    echo "land: #   * add an 'owns:' line to $FLEET/board/${tid:-<ticket>}.md, then re-run" >&2
    echo "land: #   * commit your work yourself, then re-run land.sh on a clean tree" >&2
    echo "land: #   * sweep it ALL deliberately: bash $FLEET/land.sh $BRANCH $REPO --commit-dirty" >&2
    echo "land: ####################################################################" >&2
    return 9
  fi

  # Split the dirty set into owned / unowned. -z is REQUIRED: porcelain's default form quotes and
  # backslash-escapes non-ASCII paths, so a plain `cut -c4-` mis-reads exactly the filenames most
  # likely to be surprising. With -z a rename emits "XY new\0old\0"; the bare old-path record has
  # no XY prefix and is checked as a path too (conservative — it can only cause a REFUSAL).
  # Split `owns:` on commas ONCE, into an array — no IFS juggling inside the match loop (a
  # `local IFS`/`unset IFS` pair inside a loop is a classic way to leak a broken IFS).
  local -a owns_paths=(); local e
  # `|| [ -n "$e" ]` is REQUIRED: the stream has no trailing newline, so plain `read` returns
  # non-zero on the LAST field and drops it — for the common single-path `owns:` that silently
  # yielded ZERO paths and refused every land (caught by D2 in land-dirty-scope.test.sh).
  while IFS= read -r e || [ -n "$e" ]; do
    e="${e#"${e%%[![:space:]]*}"}"; e="${e%"${e##*[![:space:]]}"}"; e="${e%/}"
    [ -n "$e" ] && owns_paths+=("$e")
  done < <(printf '%s' "$owns" | tr ',' '\n')
  [ ${#owns_paths[@]} -gt 0 ] || { echo "land: REFUSING — ticket $tid's owns: parsed to no usable paths" >&2; return 9; }

  local -a owned=() unowned=(); local rec p hit
  while IFS= read -r -d '' rec; do
    if [[ "$rec" =~ ^..\  ]]; then p="${rec:3}"; else p="$rec"; fi
    [ -n "$p" ] || continue
    hit=""
    for e in "${owns_paths[@]}"; do
      # exact file match, or anything beneath a declared directory
      if [ "$p" = "$e" ] || [ "${p#"$e"/}" != "$p" ]; then hit=1; break; fi
    done
    if [ -n "$hit" ]; then owned+=("$p"); else unowned+=("$p"); fi
  done < <(git status --porcelain -z)

  if [ ${#unowned[@]} -gt 0 ]; then
    echo "land: ####################################################################" >&2
    echo "land: # REFUSING to commit — ${#unowned[@]} dirty file(s) are OUTSIDE ticket $tid's owns:." >&2
    echo "land: # owns: $owns" >&2
    echo "land: # UNOWNED and therefore NOT committable by this land:" >&2
    for p in "${unowned[@]}"; do echo "land: #     $p" >&2; done
    echo "land: # Nothing was staged or committed. Fix by ONE of:" >&2
    echo "land: #   * clean/commit those files yourself, then re-run land.sh" >&2
    echo "land: #   * widen 'owns:' in $FLEET/board/$tid.md if they really belong to this ticket" >&2
    echo "land: #   * sweep them ALL deliberately: bash $FLEET/land.sh $BRANCH $REPO --commit-dirty" >&2
    echo "land: ####################################################################" >&2
    return 9
  fi

  [ ${#owned[@]} -gt 0 ] && LAND_STAGE=(-- "${owned[@]}")
  return 0
}
# Run the PLAN (read-only: it stages and commits nothing) BEFORE the gate, so a refusal costs no
# gate run. The COMMIT itself happens at step 3.5, after the gate.
land_scope_plan || exit $?

# 2. build the gate command parts (ruff + mypy + repo gate)
GATE_PARTS=()
if [ -z "$GATE" ]; then
  if   [ -f "$REPO/src/charon/cli.py" ]; then
    GATE_PARTS+=("ruff check $REPO/src $REPO/tests")
    GATE_PARTS+=("mypy $REPO/src")
    GATE_PARTS+=("PYTHONPATH=$REPO/src python3 -m charon.cli gate")
  elif [ -f "$REPO/ksf/cli.py" ]; then
    GATE_PARTS+=("ruff check $REPO/ksf $REPO/tests")
    GATE_PARTS+=("mypy $REPO/ksf")
    GATE_PARTS+=("PYTHONPATH=$REPO python3 -m ksf.cli --repo-root $REPO gate && PYTHONPATH=$REPO python3 -m ksf.cli --repo-root $REPO verify-self")
  elif [ -f "$REPO/fleet/validate_board.sh" ]; then
    GATE_PARTS+=("bash $REPO/fleet/validate_board.sh $REPO/fleet")
    # LAND-GATE-RIG-SUITE — the RIG's merge gate ran validate_board.sh and NOTHING ELSE.
    # validate_board.sh is a BOARD-STRUCTURE check: it reads fleet/board/*.md and says nothing at
    # all about whether the rig's own code works. fleet/gate.sh (the canonical fleet suite,
    # 78 files) was NEVER invoked on a rig land. Proven live on PR #264: land.sh ran exactly one
    # command, printed "GREEN board structurally valid", and merged onto a master carrying 8 RED
    # tests. So rig merges were not test-gated at all, contrary to MANAGER-OPERATING-RULES §8
    # ("Merge gate = the FULL CI gate ... NEVER pytest-alone").
    #
    # THE FLIP — `LAND_RIG_TESTS=1` is the SINGLE switch that arms this; default 0 = DISABLED.
    #   arm it:  LAND_RIG_TESTS=1 bash fleet/land.sh <branch> /home/stack/charon-private
    # SHIPPED DISABLED ON PURPOSE: master currently carries 8 failing suites (verified
    # 2026-07-24: `bash fleet/gate.sh` -> "summary: 70 passed, 8 failed", rc=1, 1m44s wall).
    # Arming it now would refuse EVERY rig land until those 8 are green, so the flip is left OFF
    # and flipping it is a deliberate, separate act — NOT a silent behaviour change on merge.
    #
    # HONESTY: this is a CONVENTION, not ENFORCEMENT. It only binds callers who go through
    # land.sh; `gh pr merge` / the web UI defeat it entirely. The durable fix is forge-native
    # branch protection with a required status check — see
    # fleet/state/GATE-FORGE-PROTECTION-agen-kolar.md, to be folded into FORGE-PRIMARY-GITEA
    # (GitHub cannot do it here: branch-protection API returns 403 "Upgrade to GitHub Pro or make
    # this repository public" on this private/free-plan repo; Gitea can, free and self-hosted).
    if [ "${LAND_RIG_TESTS:-0}" = "1" ] && [ -f "$REPO/fleet/gate.sh" ]; then
      GATE_PARTS+=("bash $REPO/fleet/gate.sh")
    fi
  elif [ -d "$REPO/tests" ]; then
    GATE_PARTS+=("python3 -m pytest -q")
  fi
else
  GATE_PARTS+=("$GATE")
fi

# 3. GATE — refuse on red, naming the failing check
if [ -n "$FORCE" ]; then
  echo "land: FORCE — gate BYPASSED (logged)" >&2
elif [ ${#GATE_PARTS[@]} -gt 0 ]; then
  for part in "${GATE_PARTS[@]}"; do
    echo "land: gate -> $part"
    RC=0; ( cd "$REPO" && eval "$part" ) || RC=$?
    if [ "$RC" -ne 0 ]; then
      echo "land: GATE RED — '$part' failed (exit $RC) — refusing to land '$BRANCH'" >&2
      exit 4
    fi
  done
  echo "land: gate GREEN"
else
  echo "land: WARN — no gate detected for $REPO; landing UNGATED"
fi

# 3.5 COMMIT the scoped set — deliberately AFTER the gate.
# ORDERING RATIONALE (LAND-DIRTY-SCOPE): nothing between here and the old position depends on the
# commit existing. Step 2 only stat()s files to auto-detect a gate command; step 3 `eval`s that
# command against the WORKING TREE (ruff/mypy/pytest/validate_board all read files on disk, none
# reads HEAD or a git index), so the gate sees byte-identical input either way. The first consumer
# of the commit is step 4's `git rev-parse --verify HEAD`, which is still downstream. Moving it
# therefore changes no gate outcome, and it removes the second half of the original harm: on a RED
# gate the old order had ALREADY written a commit onto whatever branch HEAD was on, then exited 4
# — leaving local master diverged with nothing pushed. Now a red gate leaves the tree untouched.
# Re-planned rather than reusing the step-1 array because a gate can legitimately modify the tree
# (formatters), and any dirt it introduces must face the same owns: scoping, not ride in unchecked.
land_scope_plan || exit $?
if [ ${#LAND_STAGE[@]} -gt 0 ]; then
  # NOT SECRET-SCANNED: leak-guard.sh is called by fleet-droid.sh / retire-done.sh / branch-reaper.sh
  # but has never been wired into land.sh or push-verify.sh (0 grep hits, verified 2026-07-19).
  # Scoping the add shrinks the exposure to files a ticket explicitly claims; wiring the scan in is
  # a separate change with its own blast radius and is NOT done here.
  git add "${LAND_STAGE[@]}" \
    && git commit -q -m "${MSG:-land: $BRANCH}" \
    && echo "land: committed scoped changes -> $(git rev-parse --short HEAD)"
fi

# 4. put the work on the feature branch (if we're currently on base)
# LAND-SAFETY-FIX (2026-07-18): this used to be `git branch -f "$BRANCH" HEAD && echo …` with the
# rc IGNORED (the script runs under `set -uo pipefail`, no -e). `git branch -f` FAILS with
#   fatal: cannot force update the branch '<b>' used by worktree at '<path>'
# whenever ANY live worktree holds that branch — with 63 worktrees in play that is the COMMON
# path. land.sh fell through to step 5 and pushed the STALE same-named local ref, which is how the
# WRONG COMMIT (be41ece) got merged while land.sh reported DONE. Now: detect the holding worktree
# FIRST with an actionable message, check the rc of the ref update, and fail CLOSED on either.
HEAD_SHA="$(git rev-parse --verify HEAD)" || { echo "land: cannot resolve HEAD in $REPO" >&2; exit 5; }
CUR="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CUR" != "$BRANCH" ]; then
  if HOLDER="$(pv_branch_holder "$REPO" "$BRANCH")"; then
    echo "land: REFUSING — branch '$BRANCH' is checked out by another worktree:" >&2
    echo "land:     $HOLDER" >&2
    echo "land:   'git branch -f $BRANCH' CANNOT update it, and landing anyway would push that" >&2
    echo "land:   worktree's stale ref instead of this HEAD ($HEAD_SHA) — the wrong-commit merge." >&2
    echo "land:   fix by ONE of:" >&2
    echo "land:     * land from the holding worktree:  bash $FLEET/land.sh $BRANCH $HOLDER" >&2
    echo "land:     * land this HEAD under its own name: bash $FLEET/land.sh <new-branch-name> $REPO" >&2
    echo "land:     * release the branch:  git -C $REPO worktree remove $HOLDER" >&2
    exit 5
  fi
  if ! git branch -f "$BRANCH" "$HEAD_SHA"; then
    echo "land: REFUSING — 'git branch -f $BRANCH $HEAD_SHA' FAILED; the local ref does NOT point at" >&2
    echo "land:   this HEAD, so pushing '$BRANCH' would publish some other commit. Nothing pushed." >&2
    exit 5
  fi
  echo "land: branch '$BRANCH' -> $(git rev-parse --short "$BRANCH")"
fi
# The ref update must have actually taken effect — never trust the command's own success message.
BR_SHA="$(git rev-parse --verify "$BRANCH" 2>/dev/null || true)"
if [ "$BR_SHA" != "$HEAD_SHA" ]; then
  echo "land: REFUSING — '$BRANCH' is ${BR_SHA:-<absent>} but the work to land is $HEAD_SHA. Nothing pushed." >&2
  exit 5
fi

# 5. push the branch (sanctioned) — push the RESOLVED SHA and PROVE with ls-remote that origin
# now has exactly it. A push that "succeeds" without moving the remote ref is the false-success
# class that produced today's wrong-commit merge.
PV_RC=0; pv_push_verified "$REPO" origin "$HEAD_SHA" "$BRANCH" || PV_RC=$?
if [ "$PV_RC" -ne 0 ]; then
  echo "land: push NOT PROVEN (rc=$PV_RC) — origin/$BRANCH is not $HEAD_SHA; refusing to open/merge a PR" >&2
  exit 5
fi

# 6. PR + merge (official gated merge)
OWNER_REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)"
[ -n "$OWNER_REPO" ] || OWNER_REPO="$(git remote get-url origin 2>/dev/null | sed -E 's#.*[:/]([^/]+/[^/.]+)(\.git)?$#\1#')"
[ -n "$OWNER_REPO" ] || { echo "land: could not resolve owner/repo via gh or remote" >&2; exit 6; }
gh pr create --repo "$OWNER_REPO" --base "$BASE" --head "$BRANCH" --fill 2>/dev/null || echo "land: (PR may already exist)"
# NO-FALSE-DONE: a DRAFT PR makes `gh pr merge` fail silently while land still printed
# "DONE" — false success that nearly recorded phantom lands (recurring LESSON). Mark ready
# FIRST, merge, then VERIFY the PR is genuinely MERGED and fail LOUD (non-zero) otherwise.
gh pr ready "$BRANCH" --repo "$OWNER_REPO" 2>/dev/null || true
# PACE merges: GitHub's SECONDARY content-creation limit (~80/min, not shown in gh api rate_limit)
# trips on rapid merge BURSTS (observed: 8 rapid lands -> temporary block). A small delay keeps a
# sequential land batch under it. Tune/disable via LAND_PACE_S.
sleep "${LAND_PACE_S:-2}"
gh pr merge "$BRANCH" --repo "$OWNER_REPO" --merge 2>&1 | tail -2
# Verify genuinely MERGED. `gh pr view` can briefly RACE right after a merge and return an
# empty/unknown state on a PR that DID merge — retry once so a real merge is not misreported as
# failed (which would also skip the auto-done-mark below). Still fails LOUD on a true non-merge.
_land_state="$(gh pr view "$BRANCH" --repo "$OWNER_REPO" --json state -q .state 2>/dev/null)"
if [ "$_land_state" != "MERGED" ]; then
  sleep 2
  _land_state="$(gh pr view "$BRANCH" --repo "$OWNER_REPO" --json state -q .state 2>/dev/null)"
fi
if [ "$_land_state" != "MERGED" ]; then
  echo "land: MERGE FAILED — '$BRANCH' PR state='${_land_state:-unknown}', NOT merged; refusing to report DONE" >&2
  exit 7
fi

# 6.5 post-land graphify refresh: keep the code map current after every land.
# Mechanized auto-refresh on the post-land trigger — a stale map is a reinvention
# risk (WIRE-GRAPHIFY-FRESHNESS, see checks/graphify-freshness.sh).
GRAPHIFY_FRESHNESS_SH="$FLEET/checks/graphify-freshness.sh"
if [ -f "$GRAPHIFY_FRESHNESS_SH" ]; then
  bash "$GRAPHIFY_FRESHNESS_SH" update 2>&1 | sed 's/^/land: [graphify] /' || true
fi

# 7. sync local base to origin — DIRTY-SAFE (LAND-SH-SAFE-SYNC). FF-only; never reset --hard /
# clean over uncommitted or untracked work. See safe_sync_base() above for the full contract.
# W0b FIX 1: the rc was previously DISCARDED (this script runs -uo pipefail, no -e), so a refusal
# was swallowed and land.sh still printed a clean DONE. The merge itself already succeeded here,
# so a refusal must NOT abort steps 8+ — but it MUST be visible and it MUST change the exit code.
_land_sync_rc=0
safe_sync_base "$REPO" "$BASE" "$BRANCH" || _land_sync_rc=$?
if [ "$_land_sync_rc" -ne 0 ]; then
  echo "land: ####################################################################" >&2
  echo "land: # BASE SYNC REFUSED (rc=$_land_sync_rc) — '$BRANCH' IS merged, but local" >&2
  echo "land: # '$BASE' was NOT synced. See the REFUSING line above and sync by hand." >&2
  echo "land: ####################################################################" >&2
fi

# 8. AUTO-DONE-MARK (self-heals board starvation): a merged PR whose ticket is never
# done-marked leaves its dependents BLOCKED (they gate on state/done/<dep>). Now that done.sh
# is O(1) (single-ticket retire), mark the ticket here so every land instantly unblocks its
# dependents and the fleet tabs stay fed. Skip silently when the branch has no board ticket
# (e.g. a manager fix branch). done.sh re-verifies the merge itself, so this is safe.
# Uses the SAME resolver as step 1's dirty scoping (ticket_for_branch, _lib.sh) so the two steps
# cannot disagree about which ticket this land belongs to. The old inline
# `grep -lE "^branch: *$BRANCH *$"` was a third parse of `branch:` and, unlike _vm_meta, it
# interpolated $BRANCH into a REGEX (a branch with a `.` or `+` matched the wrong ticket).
_land_tid=""
if command -v ticket_for_branch >/dev/null 2>&1; then
  _land_tid="$(ticket_for_branch "$BRANCH" 2>/dev/null || true)"
fi
if [ -n "$_land_tid" ]; then
  echo "land: auto-done-marking $_land_tid (unblocks its dependents)"
  AUTONOMOUS=1 bash "$FLEET/done.sh" "$_land_tid" >/dev/null 2>&1 \
    || echo "land: (auto-done-mark for $_land_tid was non-fatal — run 'done.sh $_land_tid' if a dependent stays blocked)" >&2
fi

if [ "$_land_sync_rc" -ne 0 ]; then
  echo "land: DONE-WITH-WARNING — '$BRANCH' merged into '$BASE' on $OWNER_REPO (verified state=MERGED)," >&2
  echo "land:   but the local '$BASE' sync was REFUSED (rc=$_land_sync_rc). Exiting non-zero so this is not swallowed." >&2
  exit 8
fi
echo "land: DONE — '$BRANCH' merged into '$BASE' on $OWNER_REPO (verified state=MERGED)"
