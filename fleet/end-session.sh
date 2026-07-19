#!/usr/bin/env bash
# end-session.sh — the ONLY sanctioned way to CLOSE a fleet session (build-rig only).
#
# WHY: session-end handoff (write -> check -> commit) has relied on manager MEMORY and keeps
# producing bad/uncommitted handoffs (memory: mechanized-handoff-gate; audit item #4 in
# fleet/state/MANUAL-STEPS-AUDIT-2026-07-10.md). This wraps the whole ritual so the gate can
# NOT be skipped: it REFUSES to declare the session closed until handoff-check.sh PASSES, and
# only then commits the handoff file to charon-private.
#
# TWO-PHASE close (run this script, fill in, run it again):
#   Phase 1 (handoff file absent, or --regen): generate the machine-state via handoff.sh into
#           SESSION-HANDOFF-<session>.md, then STOP with a non-zero exit — the session is NOT
#           closed. The operator fills in the human sections (summary / key findings / gotchas /
#           committed SHA / session-bridge) that a next session cannot start without.
#   Phase 2 (handoff file present): run handoff-check.sh on it. FAIL -> REFUSE to close
#           (non-zero), do NOT commit. PASS -> commit the file to charon-private, print CLOSED.
#
# Usage:
#   SESSION=mace-windu bash /home/stack/charon-private/fleet/end-session.sh
#   SESSION=mace-windu bash fleet/end-session.sh --regen      # force-regenerate machine-state
#   bash fleet/end-session.sh --selftest                      # fail-on-revert self-test (no real commit)
#
# TEST HOOKS (used only by --selftest / fleet/tests; never in normal operation):
#   END_SESSION_GIT=<git-bin>       stub the git binary so the commit is recorded, not performed
#   END_SESSION_HANDOFF_SH=<path>   stub the machine-state generator (avoid the slow real gate)
#   END_SESSION_CHECK_SH=<path>     point at a stub/real handoff-check
#   END_SESSION_DEPLOY_HOOK=<path>  stub the session-end deploy harness source
#   SESSION_END_DEPLOY_SH=<path>    stub the deploy binary called by the deploy harness
#   END_SESSION_PRIV=<repo>         repo to commit the handoff into (default /home/stack/charon-private)
#   END_SESSION_FILE=<path>         explicit handoff file (default SESSION-HANDOFF-<session>.md)
#   END_SESSION_PUSH=0              skip the auto-push step (still REFUSES if unpushed; test/replay only)
#   END_SESSION_PUSH_TIMEOUT=<sec>  wall-clock ceiling on the land-push call (default 120)
#   END_SESSION_SECOND_REPOS="<p>…" whitespace-separated repo paths for the second-repo strand
#                                   check, replacing the repo-registry lookup (fixtures only)
#   END_SESSION_SECOND_REPO_CHECK=0 skip the second-repo strand check entirely (fixtures that
#                                   are not exercising it; NEVER set this in real operation)
set -uo pipefail

FLEET="${END_SESSION_FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PRIV="${END_SESSION_PRIV:-/home/stack/charon-private}"
GIT_BIN="${END_SESSION_GIT:-git}"
HANDOFF_SH="${END_SESSION_HANDOFF_SH:-$FLEET/handoff.sh}"
CHECK_SH="${END_SESSION_CHECK_SH:-$FLEET/handoff-check.sh}"
DEPLOY_HOOK="${END_SESSION_DEPLOY_HOOK:-$FLEET/deploy-session-end.sh}"

say(){ printf '%s\n' "$*"; }

# ---------------------------------------------------------------------------
# commit_handoff <file> — commit ONLY the handoff file to charon-private.
# Isolated behind GIT_BIN so the self-test can stub it (never a real commit in tests).
# ---------------------------------------------------------------------------
commit_handoff(){
  local f="$1" utc
  utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$GIT_BIN" -C "$PRIV" add -- "$f" \
    && "$GIT_BIN" -C "$PRIV" commit -m "chore(fleet): session handoff ${SESSION} (${utc})" -- "$f"
}

# ---------------------------------------------------------------------------
# second_repo_paths — absolute checkout paths of the NON-rig repos a session can strand work
# in. Resolved through fleet/repo-registry.sh (the rig's path SSOT) rather than hardcoded, so
# adding a repo to the registry automatically extends this gate. $PRIV is excluded — it is
# already covered by the dirty/ahead checks above. END_SESSION_SECOND_REPOS overrides the whole
# list (test hook; also lets an operator narrow it).
# ---------------------------------------------------------------------------
second_repo_paths(){
  if [ -n "${END_SESSION_SECOND_REPOS-}" ]; then
    printf '%s\n' $END_SESSION_SECOND_REPOS
    return 0
  fi
  local reg="$FLEET/repo-registry.sh" k seen=""
  [ -f "$reg" ] || return 0            # registry absent -> caller decides (fails closed below)
  # shellcheck source=/dev/null
  . "$reg" || return 0
  for k in $(repo_known_keys); do
    RR_PATH=""
    repo_resolve "$k" "" >/dev/null 2>&1 || continue
    [ -n "$RR_PATH" ] || continue
    [ "$RR_PATH" = "$PRIV" ] && continue          # the rig itself: already checked
    case " $seen " in *" $RR_PATH "*) continue ;; esac   # keys alias onto shared paths
    seen="$seen $RR_PATH"
    printf '%s\n' "$RR_PATH"
  done
}

# ---------------------------------------------------------------------------
# check_second_repos — 0 only when NO second repo holds strandable work.
# Refuses on dirty tree, on commits ahead of origin/<branch>, and — failing CLOSED — whenever a
# present repo's state cannot be determined at all (git fails, detached HEAD, no tracking ref).
# Every refusal NAMES the repo, so the operator knows which tree to go look at.
# A path that does not EXIST is skipped, not refused: an absent checkout cannot strand work, and
# refusing on it would wedge close forever on any box that only has one of the repos.
# ---------------------------------------------------------------------------
check_second_repos(){
  if [ "${END_SESSION_SECOND_REPO_CHECK:-1}" = "0" ]; then
    return 0
  fi
  if [ ! -f "$FLEET/repo-registry.sh" ] && [ -z "${END_SESSION_SECOND_REPOS-}" ]; then
    say "end-session: REFUSING to close — $FLEET/repo-registry.sh is missing, so the other repos'"
    say "  paths cannot be resolved and unpushed work there cannot be ruled out (failing closed)."
    return 1
  fi
  local path porcelain branch oref hsha ahead rc=0
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    [ -d "$path" ] || continue                 # no checkout on this box -> nothing to strand
    if ! "$GIT_BIN" -C "$path" rev-parse --git-dir >/dev/null 2>&1; then
      say "end-session: REFUSING to close — $path exists but is NOT a git repo (state undeterminable)."
      say "  Fix: remove or repair $path, then re-run."
      rc=1; continue
    fi
    porcelain="$("$GIT_BIN" -C "$path" status --porcelain 2>/dev/null || echo '__GIT_FAIL__')"
    if [ "$porcelain" = "__GIT_FAIL__" ]; then
      say "end-session: REFUSING to close — '$GIT_BIN -C $path status' FAILED (repo unreachable/corrupt)."
      rc=1; continue
    fi
    if [ -n "$porcelain" ]; then
      say "end-session: REFUSING to close — $path working tree is DIRTY (uncommitted session work)."
      say "  This is the PRODUCT/second repo, not the rig — end-session commits nothing here."
      say "  ---"
      printf '%s\n' "$porcelain" | sed 's/^/    /'
      say "  ---"
      say "  Fix: commit and push that work in $path, then re-run."
      rc=1; continue
    fi
    branch="$("$GIT_BIN" -C "$path" branch --show-current 2>/dev/null || echo '')"
    if [ -z "$branch" ]; then
      say "end-session: REFUSING to close — $path is on a DETACHED HEAD; whether its commits are"
      say "  on origin cannot be determined (failing closed rather than assuming clean)."
      say "  Fix: git -C $path checkout <branch>   then re-run."
      rc=1; continue
    fi
    oref="$("$GIT_BIN" -C "$path" rev-parse --verify "origin/$branch" 2>/dev/null || true)"
    hsha="$("$GIT_BIN" -C "$path" rev-parse HEAD 2>/dev/null || true)"
    if [ -z "$oref" ]; then
      say "end-session: REFUSING to close — $path is on '$branch' with no origin/$branch ref."
      say "  Its commits are on NO remote (never pushed / never fetched) — that is stranded work."
      say "  Fix: git -C $path fetch origin $branch   (or push the branch), then re-run."
      rc=1; continue
    fi
    if [ "$oref" != "$hsha" ]; then
      ahead="$("$GIT_BIN" -C "$path" rev-list --count "$oref"..HEAD 2>/dev/null || echo 0)"
      if [ "${ahead:-0}" -gt 0 ]; then
        say "end-session: REFUSING to close — $path has $ahead commit(s) on '$branch' NOT on origin/$branch."
        say "  Session work in the PRODUCT/second repo would be stranded by closing now."
        say "  Fix: git -C $path push origin $branch   then re-run."
        rc=1
      fi
    fi
  done <<EOF
$(second_repo_paths)
EOF
  return "$rc"
}

end_session(){
  local regen=0 selftest_file=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --regen) regen=1 ;;
      --file)  selftest_file="${2:?--file needs a path}"; shift ;;
      *) say "end-session: unknown arg '$1'"; return 64 ;;
    esac
    shift
  done

  local session="${SESSION:-}"
  if [ -z "$session" ]; then
    say "end-session: SESSION is required (export SESSION=<your-jedi-name>)."
    return 64
  fi

  local file="${END_SESSION_FILE:-${selftest_file:-$FLEET/SESSION-HANDOFF-$session.md}}"

  # -- Phase 1: generate machine-state if the handoff does not exist (or --regen) -------------
  if [ ! -f "$file" ] || [ "$regen" -eq 1 ]; then
    say "end-session: generating machine-state handoff -> $file"
    local grc=0
    SESSION="$session" bash "$HANDOFF_SH" > "$file" || grc=$?
    if [ "$grc" -ne 0 ]; then
      say "end-session: WARNING — handoff.sh exited non-zero (rc=$grc): the GATE is RED."
      say "end-session: a red gate MUST NOT be handed off as green — fix it before closing."
    fi
    say ""
    say "end-session: machine-state written. NOT CLOSED YET."
    say "  -> Fill in the human sections (summary / key findings / gotchas / committed SHA /"
    say "     session-bridge), then RE-RUN this script to check + commit + close."
    return 3
  fi

  # -- Phase 2: the handoff exists -> it MUST PASS handoff-check before we close --------------
  say "end-session: checking handoff -> $file"
  local crc=0
  bash "$CHECK_SH" "$file" || crc=$?
  if [ "$crc" -ne 0 ]; then
    say ""
    say "end-session: REFUSING to close — handoff-check FAILED (rc=$crc)."
    say "  The handoff is incomplete/inaccurate (see the ✗ lines above). Fix it and re-run."
    say "  Nothing was committed. The session is NOT closed."
    return "$crc"
  fi

  # -- BRANCH-GUARD (session-end-hardening 2026-07-14): never commit the handoff onto a stray
  # feature branch. The rig primary was found left on a droid's feat/* branch; committing there
  # tangles session work into an unrelated PR, and a later checkout clobbered live grader state
  # (model-scorecard.tsv reverted 31->4 rows + flipped owner stack<-bench-grader, breaking appends).
  # NOTE: must go through $GIT_BIN like every other git call in this script. This line used a
  # BARE `git`, which silently bypassed the documented END_SESSION_GIT test hook: with a stubbed
  # git and a non-repo $PRIV fixture the lookup failed, cur_branch came back EMPTY, and the
  # branch-guard below refused every close. That made the whole "close succeeds" path untestable
  # from any fixture (end-session --selftest B*, deploy-session-end t5) — the same false-RED class
  # as #124. Production behaviour is unchanged: END_SESSION_GIT defaults to `git`.
  local cur_branch
  cur_branch="$("$GIT_BIN" -C "$PRIV" branch --show-current 2>/dev/null || echo '')"
  case "$cur_branch" in
    master|main|chore/session-*|chore/handoff-*) : ;;
    *)
      say "end-session: REFUSING to close — rig is on branch '$cur_branch', not master or a chore/session-*/chore/handoff-* branch."
      say "  Committing the handoff here would tangle it into an unrelated branch/PR (recurred 2026-07-14)."
      say "  Fix: git -C $PRIV checkout master   (or: git -C $PRIV checkout -b chore/session-<name> master), then re-run."
      return 1
      ;;
  esac

  # -- handoff-check PASSED -> commit the handoff, THEN declare the session closed -----------
  # -- PUSH-GATE (SESSION-END-PUSH-GATE 2026-07-15): session work must reach origin/master, not
  # just land locally. cere-junda's close-time bug stranded 6 session commits in the rig while
  # the handoff-check still passed — a fresh next session pulling origin would have MISSED all of
  # it. Sibling of BASE-INTEGRITY-GATE (same disease, exit side).
  # Two checks before we ever print CLOSED:
  #   (a) working tree is CLEAN — no uncommitted session work (not just no handoff, ALL of it).
  #       We do the dirty check AFTER the handoff commit, so a clean tree means EVERY piece of
  #       session work is committed (not just the handoff). A dirty entry here is uncommitted work
  #       that would strand if we close now.
  #   (b) local $PRIV HEAD is not ahead of origin/$cur_branch — all committed work is on origin.
  #       If it IS ahead, push via the sanctioned land-push (autonomous-gated); on AUTONOMOUS=off
  #       land-push REFUSES — we surface the exact operator command instead of stranding work.

  say "end-session: handoff-check PASSED — committing $file to charon-private."
  if ! commit_handoff "$file"; then
    say "end-session: commit FAILED — session NOT closed (nothing to hand off)."
    return 1
  fi

  local repo_porcelain
  repo_porcelain="$("$GIT_BIN" -C "$PRIV" status --porcelain 2>/dev/null || echo '__GIT_FAIL__')"
  if [ "$repo_porcelain" = "__GIT_FAIL__" ]; then
    say "end-session: REFUSING to close — '$GIT_BIN -C $PRIV status' failed (repo unreachable / corrupt)."
    say "  Fix: verify $PRIV is a healthy git repo, then re-run."
    return 1
  fi
  if [ -n "$repo_porcelain" ]; then
    say "end-session: REFUSING to close — $PRIV working tree is DIRTY (uncommitted session work)."
    say "  end-session.sh commits ONLY the handoff file; anything listed below is stranded."
    say "  ---"
    printf '%s\n' "$repo_porcelain" | sed 's/^/    /'
    say "  ---"
    say "  Fix: review, commit (and push) the rest of the session's work, then re-run."
    return 1
  fi

  # After the handoff commit, the rig MAY now be ahead of origin. Sync it (autonomous-gated) or
  # refuse LOUDLY with the exact command — never silently close with unpushed work.
  local ahead origin_ref head_sha
  origin_ref="origin/$cur_branch"
  # `git rev-parse --verify <ref>` exits 1 if the ref is unknown (never fetched) — treat as
  # 'no origin/<branch> known' and require an explicit fetch first.
  origin_ref="$("$GIT_BIN" -C "$PRIV" rev-parse --verify "$origin_ref" 2>/dev/null || true)"
  head_sha="$("$GIT_BIN" -C "$PRIV" rev-parse HEAD 2>/dev/null || true)"
  if [ -z "$origin_ref" ]; then
    say "end-session: REFUSING to close — $PRIV has no $origin_ref tracking ref (never fetched)."
    say "  Fix:  git -C $PRIV fetch origin $cur_branch   then re-run end-session."
    return 1
  fi
  if [ "$origin_ref" != "$head_sha" ]; then
    ahead="$("$GIT_BIN" -C "$PRIV" rev-list --count "$origin_ref"..HEAD 2>/dev/null || echo 0)"
    if [ "${ahead:-0}" -eq 0 ]; then
      # HEAD != origin but origin is descendant of HEAD (e.g. local rewind) — still safe to push.
      : # fall through to push attempt
    else
      say "end-session: $ahead commit(s) on $PRIV are ahead of $origin_ref — pushing via land-push."
    fi
    if [ "${END_SESSION_PUSH:-1}" = "0" ]; then
      say "end-session: REFUSING to close — END_SESSION_PUSH=0 (push suppressed), but $PRIV is ahead of $origin_ref."
      say "  Fix:  bash $FLEET/land-push.sh $cur_branch $PRIV   (autonomous-gated; refuses with the operator command on AUTONOMOUS=off)"
      return 1
    fi
    local push_sh="$FLEET/land-push.sh"
    if [ ! -x "$push_sh" ]; then
      say "end-session: REFUSING to close — $push_sh not executable; cannot push $ahead commit(s)."
      say "  Fix:  bash $push_sh $cur_branch $PRIV   (or:  git -C $PRIV push origin $cur_branch)"
      return 1
    fi
    # BLOCK-FOREVER GUARD (adversarial review 2026-07-19). This used to be a bare
    # `bash "$push_sh" ...` — no timeout, no stdin redirect, no GIT_TERMINAL_PROMPT — and
    # land-push.sh sets none of them either. A credential prompt (https remote, expired token)
    # or a black-holed remote therefore hung session close FOREVER with no error printed: the
    # operator sees the script sit there, ^C's it, and every commit stays stranded — precisely
    # the failure this gate exists to prevent, in its worst form (a hung close is worse than a
    # failed one, because a failed one TELLS you). Bound it three ways:
    #   timeout            — wall-clock ceiling; 124 is refused LOUDLY, never silently closed.
    #   </dev/null         — stdin is EOF, so a prompt can never wait on a human.
    #   GIT_TERMINAL_PROMPT=0 / ssh BatchMode — git and ssh fail fast instead of prompting.
    # Precedent: the DEPLOY path in deploy-session-end.sh already wraps every external lookup
    # in `timeout` for the same reason (deploy-session-end.test.sh t6 proves close never blocks).
    # GIT_SSH_COMMAND is only defaulted, never overridden — an operator with a custom ssh
    # wrapper keeps it. Kept local to this call: land-push.sh is owned by another branch.
    local push_timeout="${END_SESSION_PUSH_TIMEOUT:-120}"
    local prc=0
    GIT_TERMINAL_PROMPT=0 \
    GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=10}" \
      timeout "$push_timeout" bash "$push_sh" "$cur_branch" "$PRIV" </dev/null || prc=$?
    if [ "$prc" -eq 124 ] || [ "$prc" -eq 137 ]; then
      say "end-session: REFUSING to close — land-push did not finish within ${push_timeout}s (timed out)."
      say "  It was killed, so the push may be PARTIAL or may not have happened at all: $PRIV is"
      say "  still ahead of $origin_ref as far as this gate can tell. Do NOT treat this as closed."
      say "  Likely causes: a credential prompt on the remote, or an unreachable/slow origin."
      say "  Fix:  git -C $PRIV push origin $cur_branch    (run it by hand to see the real error)"
      return 1
    fi
    if [ "$prc" -ne 0 ]; then
      say "end-session: REFUSING to close — land-push REFUSED (see above)."
      say "  The rig is ahead of $origin_ref. Either flip the lever and re-run, or run the operator command printed by land-push."
      return 1
    fi
    # Re-read BOTH refs AFTER the push. This line used to print "$origin_ref", which still held
    # the PRE-push sha captured above — it cheerfully reported "synced to <the old sha>", the one
    # value that proves the push did NOT happen. Report what git says now, and if the two still
    # disagree, land-push exited 0 without actually syncing: refuse rather than print a green lie.
    local post_head post_origin
    post_head="$("$GIT_BIN" -C "$PRIV" rev-parse HEAD 2>/dev/null || true)"
    post_origin="$("$GIT_BIN" -C "$PRIV" rev-parse --verify "origin/$cur_branch" 2>/dev/null || true)"
    if [ -z "$post_origin" ] || [ "$post_head" != "$post_origin" ]; then
      say "end-session: REFUSING to close — land-push exited 0 but $PRIV HEAD ($post_head)"
      say "  still does not match origin/$cur_branch (${post_origin:-<unknown>}). Work is NOT on origin."
      say "  Fix:  git -C $PRIV push origin $cur_branch   then re-run end-session."
      return 1
    fi
    say "end-session: land-push GREEN — local HEAD synced to origin/$cur_branch at $post_origin."
  fi

  # -- SECOND-REPO STRAND CHECK (adversarial review 2026-07-19) ------------------------------
  # Everything above inspects ONLY $PRIV (charon-private). Session work committed-but-unpushed
  # in the PRODUCT repo was never looked at, so a session that built product code and forgot to
  # push it printed SESSION CLOSED with all of it stranded — the exact failure class this whole
  # gate exists to prevent, missed on half the surface. handoff-check.sh already treats the
  # product repo as a second first-class repo (it resolves handoff SHAs against either), so the
  # omission here was inconsistent, not deliberate.
  # Path comes from fleet/repo-registry.sh, the rig's path SSOT — NOT hardcoded (standing rule
  # no-hardcoded-cross-boundary-paths). We check, we do NOT push: auto-pushing a product branch
  # from session close is a far bigger blast radius than refusing with the exact command.
  if ! check_second_repos; then
    return 1
  fi

  # Advisory only: deploy failures/unreachable infrastructure must never strand close.
  if [ -f "$DEPLOY_HOOK" ]; then
    # shellcheck source=/dev/null
    source "$DEPLOY_HOOK"
    session_end_deploy || true
  fi
  # -- regenerate the self-contained HTML roadmap (advisory; never block close) --
  if [ -f "$FLEET/roadmap-html.sh" ]; then
    local rmap_out="$PRIV/fleet/state/roadmap.html"
    bash "$FLEET/roadmap-html.sh" "$rmap_out" 2>/dev/null || true
    say ""
    say "=== ROADMAP HTML ==="
    say "Regenerated: $rmap_out"
    say "To keep the durable web link current, re-publish the file above to Artifact URL:"
    say "  255411a5-edda-46c1-aded-a23b6d53811d"
    say "(refresh the artifact at each close to keep the link current)"
    say "===================="
  fi

  say ""
  say "end-session: SESSION CLOSED. Handoff committed."
  say ""
  # Print the full waved roadmap on the screen at session end (operator 2026-07-10).
  [ -f "$FLEET/report.sh" ] && bash "$FLEET/report.sh" 2>/dev/null
  return 0
}

# ===========================================================================
# SELF-TEST — FAIL-ON-REVERT. Runs a COPY of this script in an isolated temp
# fleet, stubs the git binary (NO real commit) and the handoff generator, and
# drives both the refuse path and the pass path — against BOTH a stub checker
# and the REAL handoff-check.sh (deliberately-incomplete vs complete handoff).
# Reverting the refuse-until-PASS gate or the commit-only-on-PASS wiring flips
# an assertion -> the test fails.
#   Run:  bash fleet/end-session.sh --selftest
# ===========================================================================
selftest(){
  local SRC; SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local PASS=0 FAIL=0
  ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
  bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
  check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

  local D; D="$(mktemp -d)"
  cp "$SRC/end-session.sh" "$D/end-session.sh"
  cp "$SRC/deploy-session-end.sh" "$D/deploy-session-end.sh"

  # recording git stub — records intent, performs NO real commit. Also fakes the push-gate
  # status/rev-parse lookups so the existing (A)-(E) tests can still drive a close without
  # a real rig repo. (A)-(E) model "all-clean, HEAD already at origin/$cur_branch" — the
  # dedicated end-session-push.test.sh (END_SESSION_PUSH=0 fixtures) covers the real dirty /
  # unpushed cases.
  cat > "$D/git-stub.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GITLOG"
# Fake a clean tree + HEAD == origin/master so the push-gate does not refuse.
case "$*" in
  *"status --porcelain"*) exit 0 ;;
  *"rev-parse --verify origin/"*) echo "0000000000000000000000000000000000000000"; exit 0 ;;
  *"rev-parse HEAD"*) echo "0000000000000000000000000000000000000000"; exit 0 ;;
  *"rev-list --count "*) echo 0; exit 0 ;;
  *"branch --show-current"*) echo "master"; exit 0 ;;
esac
exit 0
STUB
  chmod +x "$D/git-stub.sh"

  # stub handoff generator (avoid the slow real gate); writes a marker file.
  cat > "$D/gen-stub.sh" <<'GEN'
#!/usr/bin/env bash
echo "# machine-state (stub) for ${SESSION:-?}"
GEN
  chmod +x "$D/gen-stub.sh"

  # stub checkers
  printf '#!/usr/bin/env bash\nexit 0\n' > "$D/check-pass.sh"; chmod +x "$D/check-pass.sh"
  printf '#!/usr/bin/env bash\nexit 1\n' > "$D/check-fail.sh"; chmod +x "$D/check-fail.sh"
  printf '# id\topened\tsev\tarea\tdesc\tcheck\tstatus\tclosed_by\n' > "$D/reds.tsv"

  local ES="$D/end-session.sh"
  export GITLOG="$D/git.log"

  run(){  # run(check_sh, extra-args...) with a PRE-EXISTING handoff file $D/HO.md
    : > "$GITLOG"
    SESSION=selftest \
    END_SESSION_GIT="$D/git-stub.sh" \
    END_SESSION_HANDOFF_SH="$D/gen-stub.sh" \
    END_SESSION_CHECK_SH="$1" \
    END_SESSION_PRIV="$D" \
    END_SESSION_SECOND_REPO_CHECK=0 \
    END_SESSION_FILE="$D/HO.md" \
    END_SESSION_DEPLOY_HOOK="$D/deploy-session-end.sh" \
    FLEET="$D" \
    SESSION_END_REDS_TSV="$D/reds.tsv" \
    SESSION_END_LATEST_TAG_CMD="printf '%s\\n' 'v9.9.9'" \
    SESSION_END_RUNNING_TAG_CMD="printf '%s\\n' 'ghcr.io/slop-platform/charon:v9.9.9'" \
    SESSION_END_CI_GREEN_CMD="printf '%s\\n' 'completed success'" \
    SESSION_END_DEPLOY_SH="$D/deploy-stub.sh" \
    bash "$ES" "${@:2}"
  }

  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> "$DEPLOYLOG"\nexit 0\n' > "$D/deploy-stub.sh"
  chmod +x "$D/deploy-stub.sh"
  export DEPLOYLOG="$D/deploy.log"

  echo "== (A) wiring: check FAIL -> REFUSE, no commit =="
  echo "handoff" > "$D/HO.md"
  local rc=0 out
  out="$(run "$D/check-fail.sh" 2>&1)" || rc=$?
  [ "$rc" -ne 0 ] && ok "A1 refuses (non-zero) when check fails" || bad "A1 refuses when check fails (rc=$rc)"
  [ -s "$GITLOG" ] && bad "A2 NO commit on failed check" || ok "A2 NO commit on failed check"
  case "$out" in *REFUS*) ok "A3 prints REFUSING";; *) bad "A3 prints REFUSING";; esac

  echo "== (B) wiring: check PASS -> commit + CLOSED =="
  rc=0
  out="$(run "$D/check-pass.sh" 2>&1)" || rc=$?
  check "B1 exits 0 when check passes" "$rc" "0"
  grep -q 'commit' "$GITLOG" && ok "B2 commit invoked on pass" || bad "B2 commit invoked on pass"
  grep -q 'add' "$GITLOG"    && ok "B3 add invoked on pass"    || bad "B3 add invoked on pass"
  case "$out" in *CLOSED*) ok "B4 prints SESSION CLOSED";; *) bad "B4 prints SESSION CLOSED";; esac
  [ -s "$DEPLOYLOG" ] && bad "B5 no deploy when 4-LOM already current" || ok "B5 no deploy when 4-LOM already current"

  echo "== (C) real handoff-check.sh + a deliberately-INCOMPLETE handoff -> REFUSE, no commit =="
  {
    echo "# handoff (incomplete on purpose)"
    echo "Only a title. No bootstrap block, no sections, no SHA."
  } > "$D/HO.md"
  rc=0
  out="$(run "$SRC/handoff-check.sh" 2>&1)" || rc=$?
  [ "$rc" -ne 0 ] && ok "C1 real check REFUSES an incomplete handoff" || bad "C1 real check refuses incomplete (rc=$rc)"
  [ -s "$GITLOG" ] && bad "C2 NO commit for incomplete handoff" || ok "C2 NO commit for incomplete handoff"

  echo "== (D) real handoff-check.sh + a COMPLETE handoff -> commit + CLOSED =="
  # A real SHA for the handoff to reference. handoff-check accepts any commit that exists in
  # charon-private OR /home/stack/code/charon.
  #
  # This USED to poke directly at "$SRC/../.git/refs/heads/feat/fragility-tickets", which only
  # resolves in the live rig checkout: in a linked worktree ".git" is a FILE (a gitdir pointer),
  # not a directory, so the loose-ref and packed-refs reads both came up empty and (D) SKIPPED
  # itself everywhere except one machine's one tree. Ask git for HEAD instead — that resolves in
  # the live tree, a linked worktree, and a fresh checkout alike. The literal-file reads stay as
  # fallbacks for a git-less environment, and the SKIP remains for the case where nothing at all
  # resolves, so this can never turn into a false RED.
  local sha=""
  sha="$(git -C "$SRC" rev-parse HEAD 2>/dev/null || true)"
  if [ -z "$sha" ]; then
    local headref="$SRC/../.git/refs/heads/feat/fragility-tickets"
    [ -f "$headref" ] && sha="$(tr -d ' \n' < "$headref")"
  fi
  if [ -z "$sha" ] && [ -f "$SRC/../.git/packed-refs" ]; then
    sha="$(awk '/feat\/fragility-tickets/{print $1; exit}' "$SRC/../.git/packed-refs")"
  fi
  # Only use the SHA if handoff-check will actually be able to see it; otherwise skip honestly
  # rather than red on an environment that legitimately cannot resolve it.
  if [ -n "$sha" ] \
     && ! git -C "$SRC" cat-file -e "$sha^{commit}" 2>/dev/null \
     && ! git -C /home/stack/code/charon cat-file -e "$sha^{commit}" 2>/dev/null; then
    sha=""
  fi
  if [ -z "$sha" ]; then
    echo "SKIP: (D) no commit SHA visible to handoff-check — complete-handoff case skipped"
  else
    {
      echo "# Session handoff — selftest — Bootstrap"
      echo ""
      # handoff-check requires a date stamp near the top. The fixture predates that rule and
      # was never caught because (D) silently SKIPPED itself on every machine.
      echo "**Date:** $(date -u '+%Y-%m-%d %H:%M UTC')"
      echo ""
      echo '```'
      echo "Read /home/stack/charon-private/fleet/RUNBOOK.md then register a fresh Jedi name and resume gating"
      echo '```'
      echo ""
      echo "## Done / committed"
      echo "Work committed at $sha (see /home/stack/charon-private/fleet/handoff.sh)."
      echo ""
      echo "## NEXT action"
      echo "FIRE the next WAVE per RUNBOOK."
      echo ""
      echo "## GOTCHA"
      echo "avoid re-running a red gate."
      echo ""
      echo "## session-bridge"
      echo "Registered via the session-bridge board."
    } > "$D/HO.md"
    rc=0
    out="$(run "$SRC/handoff-check.sh" 2>&1)" || rc=$?
    check "D1 real check PASSES a complete handoff (exit 0)" "$rc" "0"
    grep -q 'commit' "$GITLOG" && ok "D2 commit invoked on complete pass" || bad "D2 commit invoked on complete pass"
    case "$out" in *CLOSED*) ok "D3 prints SESSION CLOSED";; *) bad "D3 prints SESSION CLOSED";; esac
  fi

  echo "== (E) phase-1: absent handoff -> generate, NOT closed, no commit =="
  rm -f "$D/HO.md"; : > "$GITLOG"
  rc=0
  out="$( SESSION=selftest \
          END_SESSION_GIT="$D/git-stub.sh" \
          END_SESSION_HANDOFF_SH="$D/gen-stub.sh" \
          END_SESSION_CHECK_SH="$D/check-pass.sh" \
          END_SESSION_PRIV="$D" \
          END_SESSION_SECOND_REPO_CHECK=0 \
          END_SESSION_FILE="$D/HO.md" \
          bash "$ES" 2>&1 )" || rc=$?
  [ "$rc" -ne 0 ] && ok "E1 phase-1 does NOT declare closed (non-zero)" || bad "E1 phase-1 not closed (rc=$rc)"
  [ -f "$D/HO.md" ] && ok "E2 machine-state file generated" || bad "E2 machine-state file generated"
  [ -s "$GITLOG" ] && bad "E3 NO commit during phase-1" || ok "E3 NO commit during phase-1"

  echo "== (F) BRANCH-GUARD: rig on a stray feat/* branch -> REFUSE, no commit =="
  # FAIL-ON-REVERT for the branch-guard. Deleting that block used to red NOTHING: every fixture's
  # git stub reports "master", so the guard was never exercised in either direction. This drives
  # the refusing direction by having the stub report a droid feature branch instead.
  cat > "$D/git-stub-feat.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GITLOG"
case "$*" in
  *"branch --show-current"*)      echo "feat/some-droid-branch"; exit 0 ;;
  *"status --porcelain"*)         exit 0 ;;
  *"rev-parse --verify origin/"*) echo "0000000000000000000000000000000000000000"; exit 0 ;;
  *"rev-parse HEAD"*)             echo "0000000000000000000000000000000000000000"; exit 0 ;;
  *"rev-list --count "*)          echo 0; exit 0 ;;
esac
exit 0
STUB
  chmod +x "$D/git-stub-feat.sh"
  echo "handoff" > "$D/HO.md"; : > "$GITLOG"
  rc=0
  out="$( SESSION=selftest \
          END_SESSION_GIT="$D/git-stub-feat.sh" \
          END_SESSION_HANDOFF_SH="$D/gen-stub.sh" \
          END_SESSION_CHECK_SH="$D/check-pass.sh" \
          END_SESSION_PRIV="$D" \
          END_SESSION_SECOND_REPO_CHECK=0 \
          END_SESSION_FILE="$D/HO.md" \
          END_SESSION_DEPLOY_HOOK="$D/deploy-session-end.sh" \
          FLEET="$D" \
          bash "$ES" 2>&1 )" || rc=$?
  [ "$rc" -ne 0 ] && ok "F1 REFUSES to close on a stray feat/* branch" || bad "F1 REFUSES on stray branch (rc=$rc)"
  case "$out" in *CLOSED*) bad "F2 no CLOSED print on a stray branch";; *) ok "F2 no CLOSED print on a stray branch";; esac
  grep -q 'commit' "$GITLOG" && bad "F3 NO handoff commit on a stray branch" || ok "F3 NO handoff commit on a stray branch"

  rm -rf "$D"
  echo
  echo "--- $PASS passed, $FAIL failed ---"
  [ "$FAIL" -eq 0 ] || { echo "END-SESSION SELF-TEST FAILED"; return 1; }
  echo "ALL END-SESSION SELF-TESTS PASS"
  return 0
}

# --- guarded dispatch: sourcing exposes the functions with NO side effects -----------------
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  if [ "${1:-}" = "--selftest" ]; then
    selftest
  else
    end_session "$@"
  fi
fi
