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
#   END_SESSION_PRIV=<repo>         repo to commit the handoff into (default /home/stack/charon-private)
#   END_SESSION_FILE=<path>         explicit handoff file (default SESSION-HANDOFF-<session>.md)
set -uo pipefail

FLEET="${END_SESSION_FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PRIV="${END_SESSION_PRIV:-/home/stack/charon-private}"
GIT_BIN="${END_SESSION_GIT:-git}"
HANDOFF_SH="${END_SESSION_HANDOFF_SH:-$FLEET/handoff.sh}"
CHECK_SH="${END_SESSION_CHECK_SH:-$FLEET/handoff-check.sh}"

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

  # -- handoff-check PASSED -> commit the handoff, THEN declare the session closed -----------
  say "end-session: handoff-check PASSED — committing $file to charon-private."
  if ! commit_handoff "$file"; then
    say "end-session: commit FAILED — session NOT closed (nothing to hand off)."
    return 1
  fi
  say ""
  say "end-session: SESSION CLOSED. Handoff committed."
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

  # recording git stub — records intent, performs NO real commit.
  cat > "$D/git-stub.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GITLOG"
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

  local ES="$D/end-session.sh"
  export GITLOG="$D/git.log"

  run(){  # run(check_sh, extra-args...) with a PRE-EXISTING handoff file $D/HO.md
    : > "$GITLOG"
    SESSION=selftest \
    END_SESSION_GIT="$D/git-stub.sh" \
    END_SESSION_HANDOFF_SH="$D/gen-stub.sh" \
    END_SESSION_CHECK_SH="$1" \
    END_SESSION_PRIV="$D" \
    END_SESSION_FILE="$D/HO.md" \
    bash "$ES" "${@:2}"
  }

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
  # git-free valid SHA: read the loose branch ref of charon-private (handoff-check accepts a
  # commit that exists in charon-private OR /home/stack/code/charon).
  local sha=""
  local headref="$SRC/../.git/refs/heads/feat/fragility-tickets"
  [ -f "$headref" ] && sha="$(tr -d ' \n' < "$headref")"
  if [ -z "$sha" ] && [ -f "$SRC/../.git/packed-refs" ]; then
    sha="$(awk '/feat\/fragility-tickets/{print $1; exit}' "$SRC/../.git/packed-refs")"
  fi
  if [ -z "$sha" ]; then
    echo "SKIP: (D) no readable charon-private branch SHA — complete-handoff case skipped"
  else
    {
      echo "# Session handoff — selftest — Bootstrap"
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
          END_SESSION_FILE="$D/HO.md" \
          bash "$ES" 2>&1 )" || rc=$?
  [ "$rc" -ne 0 ] && ok "E1 phase-1 does NOT declare closed (non-zero)" || bad "E1 phase-1 not closed (rc=$rc)"
  [ -f "$D/HO.md" ] && ok "E2 machine-state file generated" || bad "E2 machine-state file generated"
  [ -s "$GITLOG" ] && bad "E3 NO commit during phase-1" || ok "E3 NO commit during phase-1"

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
