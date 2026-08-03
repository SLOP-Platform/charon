#!/usr/bin/env bash
# board-lock.sh — the LOCKED CHOKE POINT for board mutation.
#
# WHY THIS EXISTS (2026-07-24, two losses in one day):
#   (a) A sub's bare `git commit` swept another lane's staged `git mv board/X.md
#       board/archive/X.md` out of the SHARED main-checkout index. A bare `git commit` takes the
#       WHOLE index — not just the paths the caller `git add`ed.
#   (b) master was rebased under a live sub; its uncommitted WIP was stashed and dropped by
#       another lane, recovered only from a dangling commit.
# Board writes were serialised by an UNENFORCED CONVENTION — the manager telling each sub "you are
# the only board writer". That is not a mechanism.
#
# THE CRUX: sub-sessions mutate fleet/board/*.md and fleet/state/ROADMAP.tsv with DIRECT FILE
# WRITES, not through a script, so there is nothing to flock at edit time. The choke point is
# therefore the COMMIT — the moment a board edit becomes shared state — and it is ENFORCED by the
# pre-commit hook work-lease.sh already auto-installs into the git-COMMON-dir (one install covers
# the main checkout AND every linked worktree). An agent's own `git add`+`git commit` on a board
# path is REFUSED; the only way through is `board-lock.sh commit`, which mints a per-commit token
# into the environment of the `git commit` it runs, and which the hook verifies against the live
# holder record. Advisory-only would have reproduced exactly the convention that failed.
#
# ONE LOCK (do NOT fork a second): every read-modify-write of the holder record runs under `flock`
# on fleet/state/lock — the SAME file claim.sh:207 / work-lease.sh / lease-enqueue.sh /
# review-pool.sh / sync-checkouts.sh already use. This script adds a holder RECORD, not a lock.
#
# FAIL-CLOSED everywhere: no flock -> refuse (never proceed unlocked); no `flock` binary ->
# refuse; master moved under the holder -> refuse; unknown token -> refuse.
#
# STALE HOLDS ARE BOUNDED AND LOUD, NEVER SILENTLY STEALABLE:
#   age < BOARD_LOCK_STALE_S            -> CONFLICT, refuse.
#   age >= stale AND holder PID DEAD    -> reclaim, but with a LOUD banner + an audit line in
#                                          state/board-lock.log. The fleet can never deadlock.
#   age >= stale AND holder PID ALIVE   -> REFUSE. Requires an explicit `steal <session> --force`
#                                          (also loud + logged). A live holder is never robbed.
#
# Usage:
#   board-lock.sh acquire <session> [--] ............ take the hold for an EDIT SESSION; pins HEAD
#   board-lock.sh release <session> ................. give it back
#   board-lock.sh status ............................ who holds it, and is it stale (LOUD)
#   board-lock.sh steal <session> --force ........... explicit, logged takeover
#   board-lock.sh commit --session <s> -m <msg> [--keep] -- <path>...
#                                                     THE choke point: locked, master-moved-checked,
#                                                     PATHSPEC-LIMITED commit
#   board-lock.sh pre-commit ........................ hook arm (refuses unlocked board commits)
#   board-lock.sh paths ............................. print the guarded path prefixes
#
# Exit codes: 0 ok | 1 CONFLICT (another holder) | 3 master moved under holder | 4 unlocked board
#             commit refused | 5 usage | 6 nothing to commit / bad pathspec | 7 unparseable ticket
#             frontmatter | 70 could not lock (fail-closed)
#
# Test hooks (hermetic): BOARD_LOCK_STALE_S, BOARD_LOCK_WAIT_S, BOARD_LOCK_FLOCK_FILE,
# BOARD_LOCK_PATHS (space-separated repo-relative prefixes), BOARD_LOCK_BYPASS (LOUD + logged),
# BOARD_LOCK_FM_BYPASS (LOUD + logged; frontmatter parse-check only).
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$FLEET/state"
LOCK="${BOARD_LOCK_FLOCK_FILE:-$STATE/lock}"   # SAME flock file as claim.sh / work-lease.sh
HOLD="$STATE/board-lock"                        # durable holder RECORD (not a lock file)
LOG="$STATE/board-lock.log"                     # audit trail for reclaims / steals / bypasses
STALE_S="${BOARD_LOCK_STALE_S:-900}"
WAIT_S="${BOARD_LOCK_WAIT_S:-10}"
# The guarded set. fleet/board/** is per-ticket but lives in ONE shared index; ROADMAP.tsv is
# openly shared. Both are mutated by direct agent file writes.
BOARD_PATHS="${BOARD_LOCK_PATHS:-fleet/board/ fleet/state/ROADMAP.tsv}"

mkdir -p "$STATE" 2>/dev/null || true
: >>"$LOCK" 2>/dev/null || true

# ------------------------------------------------------------------ helpers
_die(){ printf '%s\n' "$*" >&2; }
_log(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >>"$LOG" 2>/dev/null || true; }
_f(){ grep -m1 "^$1:" "$HOLD" 2>/dev/null | cut -d' ' -f2- ; }   # field read from the holder record
_alive(){ [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }
_now(){ date +%s; }
_token(){ head -c 16 /dev/urandom 2>/dev/null | od -An -tx1 | tr -d ' \n' || echo "$$-$(_now)"; }

# _with_lock <fn> [args...] — run <fn> holding fd 9 on $LOCK.
# FAIL-CLOSED: a missing `flock` binary or a timed-out acquisition REFUSES; we never fall through
# and mutate the holder record unlocked. That fall-through is the whole bug class this closes.
_with_lock(){
  command -v flock >/dev/null 2>&1 || {
    _die "BOARD-LOCK REFUSED (fail-closed): no 'flock' binary — refusing to mutate board state unlocked."
    return 70; }
  exec 9>>"$LOCK" || { _die "BOARD-LOCK REFUSED (fail-closed): cannot open lock file $LOCK"; return 70; }
  if ! flock -w "$WAIT_S" 9; then
    exec 9>&-
    _die "BOARD-LOCK REFUSED (fail-closed): could not take flock on $LOCK within ${WAIT_S}s."
    _die "  Another board writer is mid-write. Retry, or: bash $FLEET/board-lock.sh status"
    return 70
  fi
  local rc=0
  "$@" || rc=$?
  exec 9>&-
  return "$rc"
}

_repo_top(){ git rev-parse --show-toplevel 2>/dev/null; }
# Is this git repo the one that carries the board? Cheap, and it makes the hook arm a no-op in the
# PRODUCT repo (where the same hook symlink is installed) without a hardcoded path.
_is_board_repo(){ local t; t="$(_repo_top)" || return 1; [ -n "$t" ] && [ -d "$t/fleet/board" ]; }

# _is_main_checkout — is the current repo+worktree the MAIN checkout (not a fleet worktree)?
# Determined by: (a) not bare, (b) branch is master, (c) fleet/board/ directory exists,
# (d) worktree root is the repo root.  All four signals are required so fleet worktrees
# (which share the same git dir and may have HEAD on master) are excluded.
_is_main_checkout(){
  local rt; rt="$(_repo_top)" || return 1
  git -C "$rt" rev-parse --is-bare-repository 2>/dev/null | grep -q true && return 1  # bare -> not main
  local ref; ref="$(git -C "$rt" symbolic-ref --short HEAD 2>/dev/null)" || return 1
  [ "$ref" = "master" ] || return 1
  [ -d "$rt/fleet/board" ] || return 1   # PRODUCT charon repo: no fleet/ subdirectory
  [ "$(git -C "$rt" worktree list --porcelain 2>/dev/null | head -1 | awk '{print $2}')" = "$rt" ] || return 1
  return 0
}

# _is_board_path <repo-relative-path> — matches a guarded PREFIX or an exact guarded file.
_is_board_path(){
  local p="$1" pat
  for pat in $BOARD_PATHS; do
    case "$pat" in
      */) case "$p" in "$pat"*) return 0;; esac ;;
      *)  [ "$p" = "$pat" ] && return 0 ;;
    esac
  done
  return 1
}

_write_hold(){  # _write_hold <session> <token> <base-sha>
  cat >"$HOLD" <<EOF
session: $1
token: $2
pid: $PPID
worktree: $(_repo_top 2>/dev/null || echo "$PWD")
base: $3
acquired: $(_now)
heartbeat: $(_now)
EOF
}

_loud(){   # a banner that cannot be mistaken for chatter, on stderr AND in the audit log
  local line
  _die "################################################################"
  while IFS= read -r line; do _die "# $line"; _log "$line"; done
  _die "################################################################"
}

# ---------------------------------------------------------------- acquire
# Returns the holder TOKEN on stdout. Everything else goes to stderr so `commit` can capture it.
_acquire_locked(){   # _acquire_locked <session> [force]
  local session="$1" force="${2:-}" now age hs hpid hwt tok base
  now="$(_now)"
  base="$(git rev-parse HEAD 2>/dev/null || echo "")"
  if [ -f "$HOLD" ]; then
    hs="$(_f session)"; hpid="$(_f pid)"; hwt="$(_f worktree)"
    age=$(( now - $(_f heartbeat 2>/dev/null || echo 0) ))
    if [ "$hs" = "$session" ] && [ -z "$force" ]; then
      # Idempotent re-acquire by the SAME session: refresh the heartbeat, KEEP the pinned base
      # (that pin is what makes "master moved under me" detectable across the edit session).
      sed -i "s/^heartbeat:.*/heartbeat: $now/" "$HOLD" 2>/dev/null
      _f token; return 0
    fi
    if [ -z "$force" ]; then
      if [ "$age" -lt "$STALE_S" ]; then
        _die "BOARD-LOCK CONFLICT: held by '$hs' (pid ${hpid:-?}) @ ${hwt:-?} — age ${age}s < ${STALE_S}s."
        _die "  REFUSING (fail-closed). Wait, or ask the holder to run: board-lock.sh release $hs"
        return 1
      fi
      if _alive "$hpid"; then
        printf '%s\n' \
          "STALE BOARD LOCK, BUT THE HOLDER IS ALIVE — NOT STEALING." \
          "holder='$hs' pid=$hpid worktree=${hwt:-?} age=${age}s (stale after ${STALE_S}s)" \
          "A stale hold is LOUD, never silently stealable. Requester '$session' was REFUSED." \
          "If '$hs' is genuinely wedged, take it EXPLICITLY:" \
          "  bash $FLEET/board-lock.sh steal $session --force" | _loud
        return 1
      fi
      printf '%s\n' \
        "RECLAIMING STALE BOARD LOCK — prior holder is DEAD." \
        "holder='$hs' pid=${hpid:-?} (no such process) worktree=${hwt:-?} age=${age}s >= ${STALE_S}s" \
        "new holder='$session'. This is why a crashed board writer cannot deadlock the fleet." | _loud
    else
      printf '%s\n' \
        "FORCED BOARD-LOCK STEAL (--force, deliberate)." \
        "prior holder='$hs' pid=${hpid:-?} @ ${hwt:-?} age=${age}s ; new holder='$session'" \
        "The prior holder's in-flight board edits are NOT protected from here on." | _loud
    fi
  fi
  tok="$(_token)"
  _write_hold "$session" "$tok" "$base"
  _log "acquire session=$session token=${tok:0:8} base=${base:0:12}"
  printf '%s\n' "$tok"
}

cmd_acquire(){
  local session="${1:-}"; [ -n "$session" ] || { _die "usage: board-lock.sh acquire <session>"; return 5; }
  local tok; tok="$(_with_lock _acquire_locked "$session")" || return $?
  echo "board-lock: HELD by '$session' (base $(_f base | cut -c1-12), token ${tok:0:8}…)"
  echo "board-lock: commit through -> bash $FLEET/board-lock.sh commit --session $session -m '<msg>' -- <paths>"
}

cmd_steal(){
  local session="${1:-}" force="${2:-}"
  [ -n "$session" ] && [ "$force" = "--force" ] || { _die "usage: board-lock.sh steal <session> --force"; return 5; }
  local tok; tok="$(_with_lock _acquire_locked "$session" force)" || return $?
  echo "board-lock: STOLEN by '$session' (token ${tok:0:8}…) — logged to $LOG"
}

_release_locked(){
  local session="$1" hs; hs="$(_f session)"
  [ -f "$HOLD" ] || { echo "board-lock: not held (nothing to release)"; return 0; }
  if [ -n "$hs" ] && [ "$hs" != "$session" ]; then
    _die "BOARD-LOCK: refusing to release a hold owned by '$hs' (you are '$session'). Use steal --force."
    return 1
  fi
  rm -f "$HOLD"; _log "release session=$session"; echo "board-lock: released ($session)"
}
cmd_release(){
  local session="${1:-}"; [ -n "$session" ] || { _die "usage: board-lock.sh release <session>"; return 5; }
  _with_lock _release_locked "$session"
}

cmd_status(){
  [ -f "$HOLD" ] || { echo "board-lock: FREE"; return 0; }
  local age hpid; hpid="$(_f pid)"; age=$(( $(_now) - $(_f heartbeat 2>/dev/null || echo 0) ))
  echo "board-lock: HELD"
  sed 's/^/  /' "$HOLD"
  echo "  age: ${age}s (stale after ${STALE_S}s)"
  if [ "$age" -ge "$STALE_S" ]; then
    if _alive "$hpid"; then
      printf '%s\n' "STALE BOARD LOCK held by a LIVE process (pid $hpid, age ${age}s)." \
                    "It will NOT be auto-reclaimed. Investigate, then steal explicitly if wedged." | _loud
    else
      printf '%s\n' "STALE BOARD LOCK, holder pid ${hpid:-?} is DEAD (age ${age}s)." \
                    "The next acquire will reclaim it (loudly)." | _loud
    fi
    return 1
  fi
}

cmd_paths(){ printf '%s\n' $BOARD_PATHS; }

# ------------------------------------------------------- frontmatter parse-check (SHIFT LEFT)
# WHY THIS EXISTS (2026-08-01, FIVE breakages in ONE session):
#   LOOP-GUARD-REASON-WIRE, CAPTURE-WIRING-TIMEOUT-FIX, MODEL-HARDCODE-PURGE, REVIEWER-TAB-POOL
#   and LAUNCHER-GATE-SETE-KILL all shipped the SAME defect — a prose value containing ': ' or a
#   backtick written as a PLAIN scalar instead of a block scalar. YAML reads `key: One guard: the
#   wire` as a nested mapping and dies with "mapping values are not allowed here"; a leading
#   backtick is a RESERVED indicator and dies with "found character '`' that cannot start any
#   token". Neither is exotic — both are what prose does to unquoted YAML.
#
# THE COST WAS NOT THE TYPO, IT WAS THE LATENCY. The only thing that parsed ticket frontmatter was
# fleet/checks/rig-ci-scope.sh -> substrate-first-gate.sh, which runs at PUSH. So each of the five
# was discovered 1-3 commits AFTER it was written and cost a full push cycle to fix. board-lock.sh
# already gates EVERY board write (it is the enforced choke point — see the header), so it is the
# earliest place the defect can be caught, and catching it here costs one local parse.
#
# NO THIRD CONVENTION. The split is not reimplemented here: this calls the SAME
# fleet/checks/substrate_first_gate.py:read_frontmatter() that the downstream gate calls, so the
# splitting rule, the parser, the error text and the suggested fix are BY CONSTRUCTION identical.
# (That module's convention: board tickets have NO leading `---` delimiter — frontmatter is the
# leading run of lines, CRLF/CR-normalised, ending at the first line matching
# _HALT = ^(#{1,6}\s|---\s*$|</?[A-Za-z][\w-]*\s*/?>) — a markdown heading, a lone `---` rule, or a
# raw HTML-ish tag — and that run is fed to yaml.safe_load. Empty or non-mapping => RED.)
# PyYAML is the ADOPTED parser for exactly this job (fleet/state/EVAL-REGISTRY.md: "PyYAML …
# ADOPT — shipped, pinned PyYAML 6.0.3"), so there is nothing to re-decide and nothing to add.
#
# DIFF-SCOPED, exactly like the downstream gate. Only the ticket files THIS commit carries are
# parsed — a pre-existing broken ticket someone else owns must never wedge an unrelated board
# write, and it is not this commit's defect to fix. The path regex is rig-ci-scope.sh's
# _scoped_board_files regex verbatim: ^fleet/board/[^/]+\.md$ — top level only, so board/archive/
# (retired tickets, which the substrate gate also excludes) is out of scope.
#
# FAIL-CLOSED, per this file's standing rule: no python3, no PyYAML, or a missing rule module =>
# REFUSE. "I could not tell" is never a pass. The refusal names the audited escape.
_FM_RE='^fleet/board/[^/]+\.md$'

# _staged_board_tickets <pathspec>... — repo-relative ticket files this commit will carry.
# ACMR (not D): a DELETED ticket has no content to parse.
_staged_board_tickets(){
  git diff --cached --name-only --diff-filter=ACMR -- "$@" 2>/dev/null | grep -E "$_FM_RE" || true
}

# _frontmatter_check <pathspec>... — rc 0 = every carried ticket parses (or nothing to check),
# rc 7 = at least one does not. Prints the file, the line, the parse error and the fix.
_frontmatter_check(){
  local files; files="$(_staged_board_tickets "$@")"
  [ -n "$files" ] || return 0                     # no tickets in this commit: nothing to say

  # The audited escape. A genuinely broken PRE-EXISTING ticket must not permanently wedge the
  # board, so there is a way through — but it is LOUD and it lands in state/board-lock.log, the
  # same shape as BOARD_LOCK_BYPASS. BOARD_LOCK_BYPASS itself also disables this: it is the
  # broader "let this board commit through unchecked" escape and this check is inside that scope.
  if [ -n "${BOARD_LOCK_FM_BYPASS:-}" ] || [ -n "${BOARD_LOCK_BYPASS:-}" ]; then
    printf '%s\n' "FRONTMATTER PARSE-CHECK BYPASSED — a board commit was allowed through UNPARSED." \
                  "files: $(printf '%s' "$files" | tr '\n' ' ')" \
                  "The downstream gate (rig-ci-scope -> substrate-first-gate) will still red on it." \
                  "This is an audited escape, not a silent one." | _loud
    return 0
  fi

  local mod="$FLEET/checks/substrate_first_gate.py"
  if [ ! -f "$mod" ]; then
    _die "BOARD-LOCK REFUSED (fail-closed): missing rule module $mod — cannot parse ticket frontmatter."
    _die "  Audited escape (LOUD + logged): BOARD_LOCK_FM_BYPASS=1 bash $FLEET/board-lock.sh commit ..."
    return 7
  fi

  # ONE python3 for the whole set, each ticket as its OWN argv entry (never a space-joined
  # string — a path is not a word list). read_frontmatter() owns the file read (UTF-8 strict),
  # the CRLF/CR normalisation, the split and the parse — we add nothing but the loop.
  local -a argv=(); local f
  while IFS= read -r f; do [ -n "$f" ] && argv+=("$f"); done <<<"$files"

  local out rc=0
  out="$(FM_FLEET="$FLEET" python3 - "${argv[@]}" <<'PY' 2>&1
import os, sys
sys.path.insert(0, os.path.join(os.environ["FM_FLEET"], "checks"))
try:
    import substrate_first_gate as gate   # THE parser of record — never a second copy of it
except SystemExit:
    raise                                 # module exits 1 at import when PyYAML is absent
except Exception as exc:                  # any import failure is fail-closed, never a pass
    sys.stderr.write("cannot import substrate_first_gate (%s)\n" % exc)
    sys.exit(2)

bad = 0
for path in sys.argv[1:]:
    try:
        gate.read_frontmatter(path)
    except gate.TicketError as exc:
        bad += 1
        print("%s: %s" % (path, exc))
sys.exit(1 if bad else 0)
PY
  )" || rc=$?
  [ "$rc" -eq 0 ] && return 0

  # rc 1 is the only "a ticket did not parse" verdict. ANY other non-zero (2 = import failure,
  {
    echo "################################################################"
    echo "# BOARD-WRITE REFUSED: a ticket in this commit has UNPARSEABLE frontmatter."
    echo "#"
    printf '%s\n' "$out" | sed 's|^|#   |'
    echo "#"
    echo "# This is the SAME parse the CI gate runs (fleet/checks/substrate-first-gate.sh, via"
    echo "# rig-ci-scope.sh). Committing it now only moves the failure to push time, 1-3 commits"
    echo "# later — which is what this check exists to stop. Fix it here, for free."
    echo "#"
    echo "# The usual cause is PROSE in a plain scalar: a value containing ': ' or starting with a"
    echo "# backtick. Quote the value or make it a block scalar (\`key: |\`):"
    echo "#"
    echo "#     serial_justified: |"
    echo "#       One guard: the wire is cohesive."
    echo "#"
    echo "# Audited escape (LOUD + logged, not silent), for a genuinely broken PRE-EXISTING ticket"
    echo "# that must not wedge the board:"
    echo "#   BOARD_LOCK_FM_BYPASS=1 bash $FLEET/board-lock.sh commit --session <s> -m '<msg>' -- <paths>"
    echo "################################################################"
  } >&2
  _log "frontmatter-refused files=$(printf '%s' "$files" | tr '\n' ' ')"
  return 7
}

# ---------------------------------------------------------------- the choke point
# commit --session <s> -m <msg> [--keep] -- <path>...
#
# THE PATHSPEC-LIMITED COMMIT. `git commit --only -- <paths>` is the whole point: it commits the
# working-tree content of exactly those paths and IGNORES everything else in the index, leaving
# foreign staged entries staged and intact. A bare `git commit` here would take the whole index —
# that is the defect that swept another lane's staged rename.
_commit_locked(){
  local session="$1" msg="$2" keep="$3"; shift 3
  local tok base cur
  tok="$(_acquire_locked "$session")" || return $?

  # MASTER MOVED UNDER ME — detect and REFUSE, never silently proceed. `base` was pinned when the
  # hold was taken (possibly a separate `acquire` at the start of the edit session), so a rebase /
  # merge / land that moved the branch out from under the editor is caught here.
  base="$(_f base)"; cur="$(git rev-parse HEAD 2>/dev/null || echo "")"
  if [ -n "$base" ] && [ -n "$cur" ] && [ "$base" != "$cur" ]; then
    printf '%s\n' \
      "BASE MOVED UNDER THE BOARD LOCK — REFUSING TO COMMIT." \
      "holder='$session' pinned base=$base but HEAD is now $cur" \
      "Your working tree may have been rebased/merged under you. Re-read the board files, then:" \
      "  bash $FLEET/board-lock.sh release $session && bash $FLEET/board-lock.sh acquire $session" | _loud
    return 3
  fi

  local p
  for p in "$@"; do
    case "$p" in -*) _die "board-lock: refusing option-like pathspec '$p'"; return 6;; esac
  done

  git add -- "$@" || { _die "board-lock: 'git add' failed (nothing staged — git add is all-or-nothing)"; return 6; }
  if [ -z "$(git diff --cached --name-only -- "$@" 2>/dev/null)" ]; then
    _die "board-lock: no staged change under the given pathspec — nothing to commit (refusing an empty commit)."
    return 6
  fi

  # SHIFT-LEFT PARSE CHECK. Runs AFTER staging (so it sees exactly the ticket set this commit
  # carries) and BEFORE `git commit` (so a refusal leaves NOTHING committed and the hold still
  # held — the author fixes the value and re-runs the same command). See _frontmatter_check.
  _frontmatter_check "$@" || return $?

  # MAIN-CHECKOUT MASTER REFUSAL — refuse board commits directly on master in the main checkout.
  # The mechanism: board-lock.sh commit -> branch cut from local master tip -> land opens a PR ->
  # GitHub MERGE commit wraps the content in a merge, but local master holds it bare. Local master
  # is simultaneously ahead AND behind origin/master — divergence by construction on every board write.
  # The fix: board commits go through a scratch worktree (never touching main-checkout master),
  # so local master stays a pure FF-only mirror. Advisory first — but a blocking gate is planned
  # once the ergonomic path (fleet/worktree-commit-and-land.sh) is shipped and the refusal becomes
  # survivable rather than a dead-end.
  #
  # RETIRE_DONE_BYPASS: retire-done.sh is an auto-admin operation that legitimately needs to commit
  # from the main checkout (the board lives there). Its archive moves are not "board edits" in the
  # sense of the divergence problem — they are mechanical cleanup of already-landed work. Bypass
  # the advisory but still hold the board lock (which protects the shared index).
  if _is_main_checkout 2>/dev/null && [ -z "${RETIRE_DONE_BYPASS:-}" ]; then
    printf '%s\n' \
      "BOARD-LOCK ADVISORY: board commit in the MAIN CHECKOUT on 'master' causes divergence." \
      "Local master is a pure FF-only mirror of origin/master. A board commit on master ->" \
      "a PR merge on GitHub wraps the content in a MERGE commit, but local master holds it BARE." \
      "Local master is simultaneously ahead AND behind origin/master — divergence by construction." \
      "Instead, use the ergonomic path:" \
      "  bash $FLEET/worktree-commit-and-land.sh --session $session -m '$msg' -- $*" \
      "The scratch worktree approach keeps local master pure and avoids the divergence ratchet." \
      "Audited escape (LOUD + logged, use only for genuine recovery/conflict resolution):" \
      "  BOARD_LOCK_BYPASS=1 bash $FLEET/board-lock.sh commit --session $session -m '$msg' -- $*" \
      "Audit: BOARD_LOCK_BYPASS is logged to state/board-lock.log." | _loud >&2
    _log "main-checkout-advisory-refused session=$session paths=$*"
    return 7
  fi

  # BOARD_LOCK_COMMIT is the token the pre-commit hook verifies. It is exported ONLY for this one
  # `git commit`, so it cannot leak into an agent's ad-hoc commit later in the session.
  if ! BOARD_LOCK_COMMIT="$tok" git commit -q --only -m "$msg" -- "$@"; then
    _die "board-lock: git commit REFUSED/failed — nothing was committed."
    return 6
  fi
  local sha; sha="$(git rev-parse --short HEAD)"
  _log "commit session=$session sha=$sha paths=$*"
  echo "board-lock: committed $sha (scoped to: $*)"
  [ -n "$keep" ] || _release_locked "$session" >/dev/null
}

cmd_commit(){
  local session="" msg="" keep=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --session) session="${2:-}"; shift 2 || return 5 ;;
      -m|--message) msg="${2:-}"; shift 2 || return 5 ;;
      --keep) keep=1; shift ;;
      --) shift; break ;;
      *) _die "board-lock commit: unknown arg '$1'"; return 5 ;;
    esac
  done
  [ -n "$session" ] && [ -n "$msg" ] && [ $# -gt 0 ] || {
    _die "usage: board-lock.sh commit --session <s> -m <msg> [--keep] -- <path>..."; return 5; }
  _with_lock _commit_locked "$session" "$msg" "$keep" "$@"
}

# ---------------------------------------------------------------- enforcement (hook arm)
# Called from fleet/hooks/pre-commit. REFUSES any commit that stages a guarded board path unless it
# carries the live holder token — i.e. unless it came through `board-lock.sh commit`. This is what
# makes the lock ENFORCED rather than merely asked for.
cmd_pre_commit(){
  git rev-parse --git-dir >/dev/null 2>&1 || return 0
  _is_board_repo || return 0
  local staged board_staged=""
  staged="$(git diff --cached --name-only --diff-filter=ACMRD 2>/dev/null)" || return 0
  local p
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    _is_board_path "$p" && board_staged="$board_staged$p"$'\n'
  done <<<"$staged"
  [ -n "$board_staged" ] || return 0

  if [ -n "${BOARD_LOCK_BYPASS:-}" ]; then
    printf '%s\n' "BOARD_LOCK_BYPASS USED — an UNLOCKED board commit was allowed through." \
                  "paths: $(printf '%s' "$board_staged" | tr '\n' ' ')" \
                  "This is an audited escape, not a silent one." | _loud
    return 0
  fi

  if [ -n "${BOARD_LOCK_COMMIT:-}" ] && [ -f "$HOLD" ] && [ "$BOARD_LOCK_COMMIT" = "$(_f token)" ]; then
    return 0
  fi

  {
    echo "################################################################"
    echo "# BOARD-WRITE REFUSED: this commit stages BOARD state without the board lock."
    echo "#"
    printf '%s' "$board_staged" | sed 's|^|#   |'
    echo "#"
    echo "# Board files are shared state written by MANY sessions through ONE index. A bare"
    echo "# 'git commit' takes the WHOLE index and has already swept another lane's staged"
    echo "# rename out of existence (2026-07-24). Commit board state through the lock:"
    echo "#"
    echo "#   bash $FLEET/board-lock.sh commit --session <your-session> \\"
    echo "#        -m '<msg>' -- <the board paths above>"
    echo "#"
    if [ -f "$HOLD" ]; then
      echo "# Current holder: '$(_f session)' (pid $(_f pid)) @ $(_f worktree)"
    else
      echo "# The board lock is currently FREE."
    fi
    echo "# Audited escape (LOUD + logged, not silent): BOARD_LOCK_BYPASS=1 git commit ..."
    echo "################################################################"
  } >&2
  return 4
}

# ------------------------------------------------------------------ dispatch
cmd="${1:-}"; shift 2>/dev/null || true
case "$cmd" in
  acquire)    cmd_acquire "$@" ;;
  release)    cmd_release "$@" ;;
  status)     cmd_status "$@" ;;
  steal)      cmd_steal "$@" ;;
  commit)     cmd_commit "$@" ;;
  pre-commit) cmd_pre_commit "$@" ;;
  paths)      cmd_paths "$@" ;;
  *) _die "Usage: $(basename "$0") {acquire|release|status|steal|commit|pre-commit|paths}"; exit 5 ;;
esac
