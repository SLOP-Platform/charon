#!/usr/bin/env bash
# THE sanctioned push path for the manager. Raw `git push` and `git -C … push` are both
# deny-listed, so this wrapper is the only way the manager can push. It self-gates on the
# AUTONOMOUS lever (state/AUTONOMOUS):
#   flag ON  -> gate + push (full-autonomous mode: no human in the routine loop)
#   flag OFF -> REFUSE and print the operator's push command (the human checkpoint on main)
# Runs the pre-push gate (ruff + mypy + repo gate) before every push. Green -> push.
# Red -> ABORT, no push. --force bypasses the gate (explicit + logged).
# Usage: land-push.sh <branch> [repo-or-worktree] [--gate <cmd>] [--force]
#   default repo = /home/stack/code/charon
#
# LAND-SAFETY-FIX (2026-07-18): this used to end in a bare `git push origin "$BRANCH"`, which
# publishes the LOCAL REF MATCHING THAT NAME — not HEAD. With HEAD on a feature branch,
# `land-push.sh master` printed "pushing 'master'" and exited 0 while publishing NOTHING (the
# local master ref was stale). It now resolves EXACTLY which sha it intends to publish, refuses
# when that is not what the caller meant, and PROVES the result with `git ls-remote`.
# The explicit `HEAD:master` refspec form (how master was reconciled) still works — it is now the
# REQUIRED form whenever the named branch is not what HEAD points at.
#
# EXIT CODES (callers depend on these being distinguishable):
#   0  pushed AND proven (origin/<dst> == intended sha, ls-remote verified)
#   3  AUTONOMOUS lever is off — refused, nothing pushed
#   4  gate RED — refused, nothing pushed
#   6  refused before pushing (malformed refspec / unresolvable src / stale bare-name ref)
#   7  the push command FAILED — remote unchanged, nothing published
#   8  push exited 0 but origin/<dst> is NOT the intended sha — UNPROVEN, possibly wrong content
#      published. 6 vs 7 vs 8 are deliberately distinct: 6/7 mean NOTHING was published, 8 means
#      something may have been. Do not collapse them.
#   9  REMOTE CI says no, or CI STATUS COULD NOT BE DETERMINED — refused, nothing pushed.
#      Distinct from 4 on purpose: 4 is "the LOCAL gate went red here", 9 is "REMOTE CI says no".
#      A caller retrying on 9 may just need to wait; a caller seeing 4 must fix code. See the
#      CI GATE block below for why this lives in the push path at all.
#      9 covers: FAILING checks; still-PENDING checks; `gh` unable to answer (auth expired, rate
#      limit, network, empty body, malformed/HTML response); python3 absent; a detached HEAD whose
#      PR could not be enumerated. "Could not determine" is NOT a pass — see F2 below.
#
# CI GATE (2026-07-19): this rig repo is PRIVATE on a free plan, so branch protection is
# unavailable (`gh api …/branches/master/protection` -> 403 "Upgrade to GitHub Pro or make this
# repository public"). The rig-ci workflow runs on PRs but CANNOT be made a REQUIRED check, so
# nothing on GitHub's side blocks merging a red PR. Enforcement therefore lives HERE, in the one
# sanctioned push path. Fail-closed on red, fail-closed on pending, fail-closed when the status
# CANNOT BE DETERMINED, and — deliberately — OPEN on the two honest "nothing covers this" cases:
# no PR exists at all (every rig branch predating the workflow), and the PR head is not the sha
# being pushed (the normal state straight after a local commit). Both of those are narrated as
# UNVERIFIED-BY-CI and never as green: a gate that bricks all existing work gets deleted rather
# than obeyed [[gates-must-actually-run]], but a gate that prints a receipt for content no check
# ever saw is worse than no gate at all.
# "CI GREEN" is printed ONLY when the rollup's headRefOid EQUALS the sha this run publishes.
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]: read-only `gh pr view`. It must never call
# land-push/land.sh, never `gh pr create|merge|comment`, never anything that triggers a CI run.
#
# LOW-6: the stale-bare-name guard below applies only to the BARE form (`master`). An EXPLICIT
# same-name refspec (`master:master`) sets BRANCH != SRC and skips it, so the stale-ref defect is
# still reachable that way. That is deliberate — an explicit refspec is an explicit statement of
# which ref the caller means — but no refspec form is inherently safe, and the refusal message
# must not imply otherwise.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLAG="$FLEET/state/AUTONOMOUS"
# shellcheck source=/dev/null
source "$FLEET/push-verify.sh"   # pv_resolve_sha / pv_push_verified — prove the push, never trust it.

# Parse args: land-push.sh <branch> [repo] [--gate <cmd>] [--force]
BRANCH="${1:?usage: land-push.sh <branch> [repo] [--gate <cmd>] [--force]}"; shift
REPO="/home/stack/code/charon"; GATE=""; FORCE=""
while [ $# -gt 0 ]; do case "$1" in
  --gate)  GATE="$2";  shift 2;;
  --force) FORCE=1;    shift;;
  *)       REPO="$1";  shift;;
esac; done

if [ ! -e "$FLAG" ]; then
  echo "land-push: AUTONOMOUS mode is OFF — the manager will not push." >&2
  echo "  operator runs:  git -C $REPO push origin $BRANCH" >&2
  echo "  or flip the lever: bash $FLEET/autonomous.sh on" >&2
  exit 3
fi

# GATE — refuse on red before push (explicit ruff + mypy + repo gate)
GATE_PARTS=()
if [ -n "$FORCE" ]; then
  echo "land-push: FORCE — gate BYPASSED (logged)" >&2
else
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
      # BOARD GATE SCOPING (2026-07-19) — validate_board.sh is only board-accurate in the LIVE
      # tree. `fleet/state/` is GITIGNORED, so a WORKTREE/fresh checkout has NO done-markers:
      # every already-done ticket reads as LIVE and the validator emits PHANTOM REDs. Confirmed
      # live: pushing from a worktree redded on an owns-collision between CAPTURE-WIRING-TIMEOUT-FIX
      # and SALVAGE-STASH-CHARON-RUN — the latter is DONE, its marker existing only in the live
      # tree, where the very same board validates GREEN. A gate that reds spuriously gets
      # force-pushed around, which is how gates stop actually running [[gates-must-actually-run]].
      # So: state-ful checkout -> FULL validation (unchanged). State-LESS checkout -> the
      # MARKER-INDEPENDENT subset only, via fleet/checks/rig-ci-scope.sh, which already encodes
      # exactly this in/out-of-scope split for CI. Reused deliberately: two implementations of the
      # same scoping rule WILL drift, and validate_board.sh is contended by four live tickets and
      # must not gain a fifth writer.
      # MED-F7 (2026-07-19): the old detection was `find "$REPO/fleet/state" -type f 2>/dev/null`,
      # which took the WEAK path — while narrating "empty/absent (worktree or fresh checkout)" — in
      # three cases where that narration was FALSE: state/ holding only empty subdirs, state/ being
      # a SYMLINK to a populated store (plain `find` will not descend a symlink argument), and
      # state/ being present-but-unreadable (the error went to /dev/null). A gate that silently
      # weakens itself while stating a cause it never established is worse than one that fails
      # loudly, so detection is now explicit and UNREADABLE fails CLOSED.
      _SD="$REPO/fleet/state"; _SMODE=""
      if [ ! -e "$_SD" ] && [ ! -L "$_SD" ]; then
        _SMODE=absent                                   # genuinely not there
      elif [ ! -d "$_SD" ]; then
        _SMODE=unreadable                               # a plain file, or a dangling symlink
      elif [ ! -r "$_SD" ] || [ ! -x "$_SD" ]; then
        _SMODE=unreadable                               # e.g. chmod 000 — we CANNOT know what is in it
      else
        _SERR="$(mktemp)"
        # -L follows a symlinked state/ ; -quit avoids a SIGPIPE from `| head -1`.
        # `|| true`: find exits 1 on a permission error, and under `set -e` a bare command
        # substitution would kill the script HERE — an undocumented rc=1 with no diagnostic,
        # leaving the next line dead for the exact case it was written to handle.
        _SHIT="$(find -L "$_SD" -type f -print -quit 2>"$_SERR")" || true
        if [ -s "$_SERR" ];   then _SMODE=unreadable    # permission/IO errors are NOT "empty"
        elif [ -n "$_SHIT" ]; then _SMODE=populated
        else                       _SMODE=empty; fi
        rm -f "$_SERR"
      fi
      case "$_SMODE" in
      populated)
        GATE_PARTS+=("bash '$REPO/fleet/validate_board.sh' '$REPO/fleet'") ;;
      unreadable)
        echo "land-push: GATE RED — cannot determine board state: '$_SD' exists but could not be" >&2
        echo "land-push:   read (permissions, dangling symlink, or not a directory). The full board" >&2
        echo "land-push:   gate needs done-markers and the scoped fallback would be a SILENT" >&2
        echo "land-push:   downgrade under a wrong stated cause. Refusing rather than guessing." >&2
        exit 4 ;;
      absent|empty)
        if [ -f "$REPO/fleet/checks/rig-ci-scope.sh" ]; then
          # MED-F8: rig-ci-scope.sh diffs against RIG_CI_BASE (default origin/master). We used to set
          # only RIG_CI_ROOT, so when refs/remotes/origin/master did not exist (bare fixture, mirror,
          # `main`-named default) `_merge_base` fell back to the LITERAL string, `git diff` failed to
          # /dev/null, and the check reported "board: 0 changed ticket(s) checked" -> GREEN over a
          # malformed ticket. Resolve the base HERE and refuse when none resolves.
          _DSTG="${BRANCH#*:}"; [ "$BRANCH" = "${BRANCH%%:*}" ] && _DSTG="$BRANCH"
          _DSTG="${_DSTG#refs/heads/}"
          _CIB=""
          for _cand in "origin/$_DSTG" origin/master origin/main; do
            if git -C "$REPO" rev-parse --verify -q "refs/remotes/$_cand" >/dev/null 2>&1; then
              _CIB="$_cand"; break
            fi
          done
          if [ -z "$_CIB" ]; then
            echo "land-push: GATE RED — the scoped board check needs a resolvable diff base and none" >&2
            echo "land-push:   of origin/$_DSTG, origin/master, origin/main exists in $REPO." >&2
            echo "land-push:   Without one the check silently examines ZERO tickets and reports GREEN." >&2
            echo "land-push:   Run 'git -C $REPO fetch origin' (or set the base explicitly) and rerun." >&2
            exit 4
          fi
          echo "land-push: board gate SCOPED — '$_SD' is $_SMODE (worktree or fresh checkout), so" >&2
          echo "land-push:   marker-DEPENDENT checks (live-vs-done, retirement, dependency satisfaction," >&2
          echo "land-push:   owns-collision) are unanswerable here and would emit phantom REDs. Running" >&2
          echo "land-push:   the marker-INDEPENDENT subset via rig-ci-scope.sh against base '$_CIB'." >&2
          echo "land-push:   The LIVE tree still gets FULL validation — this does not weaken it there." >&2
          # RIG_CI_HEAD is PINNED to HEAD, not merely left to its default. If land-push is invoked
          # from an environment that already exports RIG_CI_HEAD (rig-ci.yml used to set it as
          # job-level env, so every test step inherited it), that FOREIGN sha does not exist in
          # $REPO, the diff scope cannot resolve, and pre-fix the check reported
          # "0 changed ticket(s) checked" -> GREEN over a malformed ticket. Pin all three.
          GATE_PARTS+=("RIG_CI_ROOT='$REPO' RIG_CI_BASE='$_CIB' RIG_CI_HEAD=HEAD bash '$REPO/fleet/checks/rig-ci-scope.sh' board")
        else
          echo "land-push: WARN — state-less checkout and no rig-ci-scope.sh; board NOT validated" >&2
        fi ;;
      esac
    elif [ -d "$REPO/tests" ]; then
      GATE_PARTS+=("python3 -m pytest -q")
    fi
  else
    GATE_PARTS+=("$GATE")
  fi
  if [ ${#GATE_PARTS[@]} -gt 0 ]; then
    for part in "${GATE_PARTS[@]}"; do
      echo "land-push: gate -> $part"
      RC=0; ( cd "$REPO" && eval "$part" ) || RC=$?
      if [ "$RC" -ne 0 ]; then
        echo "land-push: GATE RED — '$part' failed (exit $RC) — refusing to push '$BRANCH'" >&2
        exit 4
      fi
    done
    echo "land-push: gate GREEN"
  else
    echo "land-push: WARN — no gate detected for $REPO; pushing UNGATED"
  fi
fi

# ── RESOLVE EXACTLY WHAT WE INTEND TO PUBLISH (fail closed) ──────────────────────────────────
# BRANCH is either a plain branch name (`master`) or an explicit refspec (`HEAD:master`).
SRC="${BRANCH%%:*}"; DST="${BRANCH#*:}"
[ "$BRANCH" = "$SRC" ] && DST="$SRC"          # no colon -> src and dst are the same name
DST="${DST#refs/heads/}"
if [ -z "$SRC" ] || [ -z "$DST" ]; then
  echo "land-push: REFUSING — malformed refspec '$BRANCH' (delete-refspecs are not supported here)" >&2
  exit 6
fi
INTENDED="$(pv_resolve_sha "$REPO" "$SRC")" || {
  echo "land-push: REFUSING — cannot resolve '$SRC' to a commit in $REPO (nothing to push)" >&2; exit 6; }

# THE 2026-07-18 DEFECT, closed: pushing a BARE NAME whose local ref is not where HEAD is
# publishes a stale ref while reporting success. Allowed only when the local ref IS HEAD;
# otherwise the caller must say which they mean with an explicit `HEAD:$DST` refspec.
if [ "$BRANCH" = "$SRC" ]; then
  HEAD_SHA="$(pv_resolve_sha "$REPO" HEAD)" || { echo "land-push: cannot resolve HEAD in $REPO" >&2; exit 6; }
  if [ "$HEAD_SHA" != "$INTENDED" ]; then
    CUR_BR="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)"
    echo "land-push: REFUSING — local ref '$SRC' is $INTENDED but HEAD ($CUR_BR) is $HEAD_SHA." >&2
    echo "land-push:   pushing the bare name would publish the STALE ref and report success." >&2
    echo "land-push:   say which you mean, by SHA, not by form:" >&2
    echo "land-push:     publish what HEAD is at:  bash $FLEET/land-push.sh HEAD:$DST $REPO" >&2
    echo "land-push:     publish the '$SRC' ref  :  bash $FLEET/land-push.sh $SRC:$DST $REPO" >&2
    echo "land-push:   NOTE: the refspec form is NOT a safety check — it only records which ref you" >&2
    echo "land-push:   meant. '$SRC:$DST' publishes $INTENDED and skips this guard by design. Confirm" >&2
    echo "land-push:   the sha above is the work you intend to publish before rerunning." >&2
    exit 6
  fi
fi

# ── CI GATE — refuse when the target branch's PR is red or still running (see header) ────────
# Fail-closed on FAILING and on PENDING; OPEN (warn) on "no PR / no checks", by design.
if [ -n "$FORCE" ]; then
  echo "land-push: FORCE — CI gate BYPASSED (logged)" >&2
elif ! command -v gh >/dev/null 2>&1; then
  echo "land-push: WARN — gh not available; CI status NOT checked, pushing unverified-by-CI" >&2
elif ! git -C "$REPO" config --get remote.origin.url 2>/dev/null | grep -q 'github\.com'; then
  # No GitHub remote -> there is no PR and no check rollup to ask about. Skipping keeps this gate
  # from making a pointless (and possibly NETWORK) gh call for local/mirror remotes.
  echo "land-push: WARN — origin is not a github.com remote; CI status NOT checked" >&2
elif ! command -v python3 >/dev/null 2>&1; then
  # F2: `python3 -c … || true` used to swallow a MISSING INTERPRETER into "no CI status" -> allow.
  # An absent classifier is an inability to check, not a clean bill of health.
  echo "land-push: CI gate CANNOT RUN — python3 is not available to classify the check rollup." >&2
  echo "land-push:   Refusing rather than reporting an unchecked push as fine. Use --force to override." >&2
  exit 9
else
  # ── F1/F2/F3/F4 (2026-07-19) — what this block is NOT allowed to do ─────────────────────────
  # F1: the rollup describes the sha ALREADY on the PR branch. land-push exists to publish
  #     something NEWER, so a green rollup says NOTHING about $INTENDED. We now fetch headRefOid
  #     and only ever print "CI GREEN" when the checks ran against the exact sha being pushed.
  # F2: `2>/dev/null || true` + "anything that isn't OK means no PR" turned ~10 distinct failures
  #     (auth expired rc=4, rate limit, network error, empty body, malformed JSON, HTML 502,
  #     null rollup, absent python3) into a silent pass. "could not determine" now fails CLOSED;
  #     warn-and-allow survives ONLY for the genuine "this branch has no PR" case, which is the
  #     one that legitimately must not brick pre-workflow branches.
  # F3: SKIPPED / NEUTRAL / STALE hit the old `else: ok+=1` and read as POSITIVELY green — a
  #     paths:-filtered or superseded rig-ci run became a false receipt. They are NEUTRAL now:
  #     never counted toward ok, and an unrecognised conclusion is likewise never green.
  # F4: `rev-parse --abbrev-ref HEAD` returns the literal string "HEAD" in a detached checkout,
  #     so `gh pr view HEAD` found nothing and the gate silently vanished — on refresh-branch.sh's
  #     documented recovery path, i.e. exactly where it matters most. Detached HEAD now resolves
  #     via the sha's open PR, or is reported as uncovered. It is never silently skipped.
  # READ-ONLY. Never `gh pr create|merge|comment|rerun` here — that would re-trigger CI and loop.
  CI_BR="$SRC"
  if [ "$CI_BR" = "HEAD" ]; then CI_BR="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"; fi
  CI_ERR="$(mktemp)"; CI_STATE=""; CI_SUMMARY=""

  _ci_gh_failed(){   # distinguish "no PR exists" (allow) from "gh could not answer" (fail closed)
    grep -qiE 'no (open )?pull requests? found|could not resolve to a pullrequest|no pull requests match' "$CI_ERR"
  }

  # A (2026-07-19): ONE validator, shared by BOTH gh-JSON parsers below. Each parser emits a
  # leading `OK <payload…>` sentinel on success, `ERR <reason>` on a shape/parse failure; anything
  # else (interpreter crash, no output at all) is likewise undetermined. Two validators that must
  # agree would drift, so there is exactly one.
  #   Why: `gh pr list` was checked only for rc!=0 or EMPTY output. rc=0 with a non-empty GARBAGE
  #   body — truncated JSON, valid JSON of the wrong shape, non-UTF8 bytes, an HTML 502 error page
  #   — parsed to nothing, was read as "no OPEN PR carries this sha", and the push was ALLOWED.
  #   The identical HTML-502 body arriving on the `pr view` path correctly exited 9. That
  #   inconsistency was the defect: "gh could not answer" is not "nothing covers this content".
  _ci_require_ok(){   # $1 = parser output, $2 = what was being parsed (for the message)
    if [ -z "$1" ] || [ "${1%% *}" != "OK" ]; then
      echo "land-push: CI gate CANNOT RUN — $2 was unreadable" >&2
      echo "land-push:   (${1:-classifier produced no output}). Malformed or truncated API" >&2
      echo "land-push:   output is an undetermined answer, NOT a pass. Refusing (--force to override)." >&2
      exit 9
    fi
  }

  # ── F4: detached HEAD — there is no branch name to ask about. Find the PR by SHA. ───────────
  if [ -z "$CI_BR" ] || [ "$CI_BR" = "HEAD" ]; then
    CI_RC=0
    CI_LIST="$( cd "$REPO" && gh pr list --state open --limit 100 \
                  --json number,headRefName,headRefOid 2>"$CI_ERR" )" || CI_RC=$?
    if [ "$CI_RC" -ne 0 ] || [ -z "$CI_LIST" ]; then
      echo "land-push: CI gate CANNOT RUN — HEAD is DETACHED in $REPO and 'gh pr list' failed" >&2
      echo "land-push:   (rc=$CI_RC), so the PR for $INTENDED could not be identified. A detached" >&2
      echo "land-push:   HEAD used to make this gate silently vanish; it now refuses instead." >&2
      sed 's/^/land-push:   gh: /' "$CI_ERR" >&2; rm -f "$CI_ERR"
      echo "land-push:   Rerun naming the branch explicitly, or --force (explicit + logged)." >&2
      exit 9
    fi
    # Emits: OK <headRefName>  (match) | OK  (parsed fine, genuinely no match) | ERR <reason>
    CI_LRES="$(printf '%s' "$CI_LIST" | INTENDED="$INTENDED" python3 -c '
import json,os,sys
try: d=json.loads(sys.stdin.buffer.read().decode("utf-8"))
except Exception: print("ERR unparseable-json"); raise SystemExit(0)
if not isinstance(d,list): print("ERR unexpected-json-shape"); raise SystemExit(0)
want=os.environ["INTENDED"]
for p in d:
    if isinstance(p,dict) and (p.get("headRefOid") or "")==want:
        print("OK "+(p.get("headRefName") or "")); raise SystemExit(0)
print("OK")
' 2>/dev/null || true)"
    _ci_require_ok "$CI_LRES" "the open-PR list for $INTENDED"
    CI_BR="${CI_LRES#OK}"; CI_BR="${CI_BR# }"
    if [ -z "$CI_BR" ]; then
      rm -f "$CI_ERR"
      echo "land-push: CI UNCOVERED — HEAD is DETACHED and no OPEN PR has $INTENDED as its head," >&2
      echo "land-push:   so NO CI run covers the content being pushed. Allowing (a detached-HEAD" >&2
      echo "land-push:   rebuild is the documented recovery path and often predates any PR), but this" >&2
      echo "land-push:   push is UNVERIFIED-BY-CI. It is NOT green." >&2
      CI_STATE=SKIP
    else
      echo "land-push: detached HEAD -> resolved $INTENDED to open PR branch '$CI_BR'" >&2
    fi
  fi

  if [ -z "$CI_STATE" ]; then
    CI_RC=0
    CI_JSON="$( cd "$REPO" && gh pr view "$CI_BR" \
                  --json number,headRefOid,statusCheckRollup 2>"$CI_ERR" )" || CI_RC=$?
    if [ "$CI_RC" -ne 0 ]; then
      if _ci_gh_failed; then
        CI_STATE=NOPR
      else
        echo "land-push: CI gate CANNOT RUN — 'gh pr view $CI_BR' failed (rc=$CI_RC). This is NOT" >&2
        echo "land-push:   the same as 'no PR exists': an expired token, a rate limit or an API blip" >&2
        echo "land-push:   must never read as a clean bill of health. Refusing." >&2
        sed 's/^/land-push:   gh: /' "$CI_ERR" >&2; rm -f "$CI_ERR"
        echo "land-push:   Fix gh (e.g. 'gh auth status'), or rerun with --force (explicit + logged)." >&2
        exit 9
      fi
    elif [ -z "$CI_JSON" ]; then
      rm -f "$CI_ERR"
      echo "land-push: CI gate CANNOT RUN — 'gh pr view $CI_BR' exited 0 but returned NOTHING." >&2
      echo "land-push:   An empty body is an undetermined answer, not a pass. Refusing (--force to override)." >&2
      exit 9
    fi
  fi
  rm -f "$CI_ERR"

  if [ "$CI_STATE" = NOPR ]; then
    echo "land-push: WARN — no PR exists for '$CI_BR' (branch predates the workflow, or no PR yet)." >&2
    echo "land-push:   ALLOWING the push UNVERIFIED-BY-CI. This is deliberate: hard-blocking here would" >&2
    echo "land-push:   brick every pre-existing branch that has zero checks." >&2
  elif [ "$CI_STATE" = SKIP ]; then
    :   # already narrated above (detached HEAD, no PR carries this sha)
  else
    # Classify. Emits: OK <headRefOid> <fail> <pend> <ok> <neutral> <names...>  |  ERR <reason>
    CI_SUMMARY="$(printf '%s' "$CI_JSON" | python3 -c '
import json,sys
try: d=json.loads(sys.stdin.read())
except Exception: print("ERR unparseable-json"); raise SystemExit(0)
if not isinstance(d,dict): print("ERR unexpected-json-shape"); raise SystemExit(0)
oid=(d.get("headRefOid") or "").strip()
if not oid: print("ERR no-headRefOid"); raise SystemExit(0)
rollup=d.get("statusCheckRollup")
if rollup is None: rollup=[]
if not isinstance(rollup,list): print("ERR unexpected-rollup-shape"); raise SystemExit(0)
# The FULL GitHub enum, explicitly. Anything unrecognised is NOT green (F3).
RED    ={"FAILURE","TIMED_OUT","CANCELLED","STARTUP_FAILURE","ACTION_REQUIRED","ERROR"}
GREEN  ={"SUCCESS"}
NEUTRAL={"NEUTRAL","SKIPPED","STALE"}          # ran-but-proved-nothing: never counted as ok
RUNNING={"QUEUED","IN_PROGRESS","PENDING","WAITING","REQUESTED","EXPECTED"}
fail=pend=ok=neut=0; names=[]
for c in rollup:
    if not isinstance(c,dict): neut+=1; names.append("UNKNOWN:check"); continue
    nm=c.get("name") or c.get("context") or "check"
    st=(c.get("status") or "").upper()          # CheckRun: QUEUED/IN_PROGRESS/COMPLETED
    cc=(c.get("conclusion") or "").upper()
    state=(c.get("state") or "").upper()        # StatusContext carries state, not status
    if st and st!="COMPLETED":
        if st in RUNNING: pend+=1; names.append("PENDING:"+nm)
        else: neut+=1; names.append("UNKNOWN-STATUS("+st+"):"+nm)
        continue
    v=cc or state
    if   not v:            pend+=1; names.append("PENDING:"+nm)
    elif v in RED:         fail+=1; names.append("RED("+v+"):"+nm)
    elif v in GREEN:       ok+=1;   names.append("GREEN:"+nm)
    elif v in NEUTRAL:     neut+=1; names.append(v+":"+nm)
    elif v in RUNNING:     pend+=1; names.append("PENDING:"+nm)
    else:                  neut+=1; names.append("UNKNOWN("+v+"):"+nm)
print("OK %s %d %d %d %d %s"%(oid,fail,pend,ok,neut," ".join(names) or "-"))
' 2>/dev/null || true)"
    _ci_require_ok "$CI_SUMMARY" "the PR check rollup for '$CI_BR'"
    read -r _ CI_OID CI_FAIL CI_PEND CI_OK CI_NEUT CI_NAMES <<<"$CI_SUMMARY"

    if [ "$CI_OID" != "$INTENDED" ]; then
      # ── F1, the false receipt. The checks ran against the PR's CURRENT head; we are publishing
      # a DIFFERENT sha. Refusing outright would brick the normal "commit locally, then push"
      # flow, so we allow — but we state plainly that nothing here covers $INTENDED, and we do
      # NOT print a green receipt no matter how green the rollup for the old sha is.
      echo "land-push: CI DOES NOT COVER THIS PUSH — the PR for '$CI_BR' has head $CI_OID, but this" >&2
      echo "land-push:   push publishes $INTENDED. The check rollup describes the OLD sha; NO CI run" >&2
      echo "land-push:   has seen the content being published. Allowing (this is the normal state" >&2
      echo "land-push:   right after a local commit) but it is UNVERIFIED-BY-CI — NOT green." >&2
      echo "land-push:   rollup for $CI_OID was: fail=$CI_FAIL pending=$CI_PEND ok=$CI_OK neutral=$CI_NEUT" >&2
    elif [ "$CI_FAIL" -gt 0 ]; then
      echo "land-push: CI RED — $CI_FAIL failing check(s) on the PR for '$CI_BR' @ $CI_OID — refusing." >&2
      echo "land-push:   $CI_NAMES" >&2
      echo "land-push:   fix the checks, or (explicit + logged) rerun with --force." >&2
      exit 9
    elif [ "$CI_PEND" -gt 0 ]; then
      echo "land-push: CI PENDING — $CI_PEND check(s) still running on the PR for '$CI_BR' — refusing." >&2
      echo "land-push:   NOT-FINISHED IS NOT A PASS. Wait for them to complete and rerun." >&2
      echo "land-push:   $CI_NAMES" >&2
      exit 9
    elif [ "$CI_OK" -eq 0 ]; then
      # Covers both "zero checks at all" and "every check was SKIPPED/NEUTRAL/STALE/unrecognised".
      echo "land-push: WARN — PR for '$CI_BR' @ $CI_OID has NO passing check ($CI_NEUT neutral/skipped/" >&2
      echo "land-push:   stale/unrecognised, 0 successful). Neutral is not green. Pushing UNVERIFIED-BY-CI." >&2
      if [ "$CI_NEUT" -gt 0 ]; then echo "land-push:   $CI_NAMES" >&2; fi
    elif [ "$CI_NEUT" -gt 0 ]; then
      echo "land-push: CI GREEN (PARTIAL) — $CI_OK passing, $CI_NEUT neutral/skipped/stale on '$CI_BR'" >&2
      echo "land-push:   @ $CI_OID — the neutral ones prove nothing. $CI_NAMES" >&2
    else
      echo "land-push: CI GREEN — $CI_OK check(s) passing on the PR for '$CI_BR' @ $CI_OID (== the sha being pushed)"
    fi
  fi
fi

echo "land-push: AUTONOMOUS on — publishing $INTENDED ('$SRC') -> origin/$DST from $REPO"
PV_RC=0; pv_push_verified "$REPO" origin "$INTENDED" "$DST" || PV_RC=$?
if [ "$PV_RC" -ne 0 ]; then
  echo "land-push: FAILED — origin/$DST was NOT proven to be $INTENDED (rc=$PV_RC). NOT reporting success." >&2
  # LOW-5: this was `exit $((4 + PV_RC))`, which produced 6 for "pushed but UNPROVEN" — colliding
  # with the 6 used above for "REFUSED, nothing was pushed". A caller could not tell NOTHING WAS
  # PUBLISHED from THE WRONG THING MAY BE PUBLISHED, and the second is by far the more dangerous
  # state. They now have distinct codes (see the exit-code table in the header).
  case "$PV_RC" in
    1) exit 7 ;;   # the push command itself failed — remote unchanged, nothing published
    *) exit 8 ;;   # push exited 0 but origin/$DST is NOT $INTENDED — UNPROVEN, possibly wrong
  esac
fi
echo "land-push: DONE — origin/$DST == $INTENDED (ls-remote verified)"
