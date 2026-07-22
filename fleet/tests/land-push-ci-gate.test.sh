#!/usr/bin/env bash
# land-push-ci-gate.test.sh — FAIL-ON-REVERT tests for the land-push.sh CI gate + board scoping.
#
# DEFECT 1 — the pre-push board gate emitted FALSE REDs from a worktree.
#   `fleet/state/` is GITIGNORED, so it exists ONLY in the live tree. From a worktree there are no
#   done-markers: every already-done ticket reads as LIVE and validate_board.sh reds on phantom
#   collisions. Confirmed live: a worktree push redded on an owns-collision between
#   CAPTURE-WIRING-TIMEOUT-FIX and SALVAGE-STASH-CHARON-RUN (the latter is DONE — marker present
#   only in the live tree, where the SAME board validates GREEN). A gate that reds spuriously gets
#   bypassed or force-pushed around, i.e. a gate that stops actually running.
#   FIX: state-LESS checkout -> marker-INDEPENDENT subset via fleet/checks/rig-ci-scope.sh.
#        state-FUL (live) tree -> FULL validate_board.sh, unweakened.
#
# DEFECT 2 — CI was advisory-only. The rig repo is PRIVATE on a free plan, so branch protection is
#   403-unavailable and rig-ci can never be a REQUIRED check: nothing blocked merging a red PR.
#   FIX: land-push.sh queries the target branch's PR check rollup and refuses (exit 9) on RED, on
#        PENDING, and on CANNOT-DETERMINE.
#
# ── 2026-07-19 ADVERSARIAL-REVIEW ROUND 2 (this suite's reason for existing in its current form) ──
# The first version of this gate turned an honest "unchecked" into a CONFIDENT FALSE RECEIPT. The
# review's attacks are now assertions here:
#   F1 the rollup describes the PR's CURRENT head; land-push publishes something NEWER. "CI GREEN"
#      for a sha no check ever ran against is the worst possible output on the only push path.
#      -> assertions C4 (stale head must NOT be green) and C5 (matching head may be).
#   F2 ~10 gh failure modes (auth rc=4, rate limit, network, empty body, malformed JSON, HTML 502,
#      missing headRefOid, absent python3) all fell through to warn-and-ALLOW.  -> C7 matrix.
#   F3 SKIPPED/NEUTRAL/STALE and unrecognised conclusions counted toward `ok` and read as green.
#      -> C6 matrix.
#   F4 detached HEAD resolved the branch name to the literal string "HEAD", so the gate silently
#      vanished on refresh-branch.sh's documented recovery path.  -> C8 matrix.
#   F6 the old stub only ever emitted FAILURE/IN_PROGRESS/SUCCESS/[], so the entire conclusion
#      table was untested and could be gutted to BAD={"FAILURE"} with 9/9 still passing. The C6/C7
#      matrices exist specifically so SEMANTIC WEAKENING (not just block deletion) goes RED.
#   F7 state detection narrated "empty/absent" for a symlinked or unreadable state/. -> B7 matrix.
#   F8 the scoped board check ran with an unresolvable diff base -> 0 tickets examined -> GREEN.
#      -> B5b asserts a NON-ZERO ticket count; B5c asserts refusal when no base resolves.
#
# NON-FIXTURE where it matters: these run the REAL land-push.sh / push-verify.sh / rig-ci-scope.sh /
# validate_board.sh (copied verbatim, never transcribed) against a REAL git repo with a REAL LOCAL
# BARE remote. `gh` is the ONLY thing stubbed — no network is touched, and nothing is pushed
# anywhere but the throwaway bare repo in $TMPDIR.
#
# ── FAIL-ON-REVERT (each assertion names the exact revert that turns it RED) ──────────────────
#   R1 — delete the `if [ "$CI_FAIL" -gt 0 ]` block.                       RED: C1, C6-red rows.
#   R2 — delete the `if [ "$CI_PEND" -gt 0 ]` block, or treat not-finished
#        as a pass.                                                        RED: C2, C2b, C6-pend.
#   R3 — make the "no PR" path `exit 9` — i.e. over-block, bricking every
#        branch that predates the workflow.                                RED: C3, B5.
#   R4 — delete the whole CI GATE block.                                   RED: C1, C2, C7.
#   R5 — drop the state-mode detection and always run validate_board.sh.   RED: B5.
#   R6 — always use rig-ci-scope.sh, weakening the LIVE tree.              RED: B6, B7-symlink.
#   R7 — drop the headRefOid fetch/compare (the F1 defect).                RED: C4.
#   R8 — reduce the RED set to {"FAILURE"}, or restore `else: ok+=1`.      RED: C6 matrix.
#   R9 — restore `2>/dev/null || true` around gh / the classifier.         RED: C7 matrix.
#   R10 — resolve detached HEAD to the literal "HEAD" again.               RED: C8.
#   R11 — stop setting RIG_CI_BASE / drop the base validation.             RED: B5b, B5c.
#   R12 — restore the plain `find … | head -1` state probe.                RED: B7 matrix.
#   R13 — drop the `_ci_require_ok` call on the `gh pr list` path, so rc=0
#         garbage parses to empty and reads as "no PR carries this sha".   RED: C8e (x4).
#   R14 — drop the `|| true` on the state `find`, so a permission error
#         kills the script at the find with an undocumented bare rc=1.     RED: B7d.
set -uo pipefail
FLEET_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0; passes=0
ok(){ passes=$((passes+1)); printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

D="$(mktemp -d)"; trap 'chmod -R u+rwX "$D" 2>/dev/null; rm -rf "$D"' EXIT

# ── hermetic copy of the REAL script under test + its AUTONOMOUS lever ────────────────────────
F="$D/fleet"; mkdir -p "$F/state"
cp "$FLEET_SRC/land-push.sh" "$FLEET_SRC/push-verify.sh" "$F/"
: > "$F/state/AUTONOMOUS"
LP="bash $F/land-push.sh"

git_q(){ git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }

# ── a REAL local bare remote + a REAL clone (no network, ever) ────────────────────────────────
git init -q --bare "$D/remote.git"
git init -q "$D/repo"; R="$D/repo"
# origin must LOOK like GitHub (land-push skips the CI gate for non-github remotes) while
# resolving to the LOCAL bare repo — insteadOf rewrites at transport time only, so land-push reads
# the RAW `git config remote.origin.url` and still sees the github.com URL. Nothing leaves this box.
git_q "$R" remote add origin https://github.com/test/fixture.git
git_q "$R" config "url.$D/remote.git.insteadOf" https://github.com/test/fixture.git
echo base > "$R/f.txt"; git_q "$R" add -A; git_q "$R" commit -qm base
git_q "$R" push -q origin HEAD:master
git_q "$R" fetch -q origin
git_q "$R" checkout -q -b feat/work
echo work >> "$R/f.txt"; git_q "$R" add -A; git_q "$R" commit -qm work

# ── the gh STUB ───────────────────────────────────────────────────────────────────────────────
# Models `pr view` and `pr list` across the FULL GitHub conclusion/status enum AND the transport
# failure modes, because the point of F6 is that a stub which only ever emits SUCCESS/FAILURE
# leaves the whole classification table untested.
BIN="$D/bin"; mkdir -p "$BIN"
cat > "$BIN/gh" <<'STUB'
#!/usr/bin/env bash
# Test double for `gh`. Anything that could TRIGGER CI hard-fails the test (reentrancy guard).
case " $* " in
  *" pr create "*|*" pr merge "*|*" pr comment "*|*" run rerun "*|*" workflow "*)
    echo "REENTRANCY: land-push invoked a CI-triggering gh subcommand: $*" >&2; exit 99;;
esac
OID="${GH_OID:-0000000000000000000000000000000000000000}"
case " $* " in
  *" pr list "*)
    case "${GH_LIST:-none}" in
      err)   echo "HTTP 403: API rate limit exceeded" >&2; exit 1;;
      none)  echo '[]';;
      match) printf '[{"number":7,"headRefName":"feat/work","headRefOid":"%s"}]\n' "$OID";;
      other) printf '[{"number":8,"headRefName":"feat/other","headRefOid":"cafebabecafebabecafebabecafebabecafebabe"}]\n';;
      # ── rc=0 with a NON-EMPTY GARBAGE body. gh "answered", but said nothing usable. ──
      trunc)   printf '[{"number":7,"headRefName":"feat/work","headRefOid":"%s"' "$OID";;
      notlist) echo '{"number":7,"headRefName":"feat/work"}';;
      binary)  printf '\xff\xfe\xc3\x28garbage\n';;
      html)    echo '<html><head><title>502 Bad Gateway</title></head><body>oops</body></html>';;
    esac
    exit 0;;
esac
# `gh pr view`
case "${GH_MODE:-nopr}" in
  # ── the ONE genuine warn-and-allow case: this branch simply has no PR ──
  nopr)        echo 'no pull requests found for branch "feat/work"' >&2; exit 1;;
  # ── transport / auth failures: gh COULD NOT ANSWER (must never read as "no PR") ──
  autherr)     echo 'gh: To get started with GitHub CLI, please run: gh auth login.' >&2; exit 4;;
  neterr)      echo 'error connecting to api.github.com' >&2; exit 1;;
  ratelimit)   echo 'HTTP 403: API rate limit exceeded' >&2; exit 1;;
  emptyout)    exit 0;;                                    # rc 0, empty stdout
  malformed)   echo 'not-json{{{'; exit 0;;
  html)        echo '<html><head><title>502 Bad Gateway</title></head><body>oops</body></html>'; exit 0;;
  noid)        printf '{"number":1,"statusCheckRollup":[{"name":"rig-ci","status":"COMPLETED","conclusion":"SUCCESS"}]}\n';;
  badrollup)   printf '{"number":1,"headRefOid":"%s","statusCheckRollup":"nope"}\n' "$OID";;
  # ── real PR shapes ──
  nullrollup)  printf '{"number":1,"headRefOid":"%s","statusCheckRollup":null}\n' "$OID";;
  norollup)    printf '{"number":1,"headRefOid":"%s","statusCheckRollup":[]}\n' "$OID";;
  conclusion)  printf '{"number":1,"headRefOid":"%s","statusCheckRollup":[{"name":"rig-ci","status":"COMPLETED","conclusion":"%s"}]}\n' "$OID" "${GH_CONCLUSION:-SUCCESS}";;
  status)      printf '{"number":1,"headRefOid":"%s","statusCheckRollup":[{"name":"rig-ci","status":"%s","conclusion":""}]}\n' "$OID" "${GH_STATUS:-IN_PROGRESS}";;
  context)     printf '{"number":1,"headRefOid":"%s","statusCheckRollup":[{"context":"legacy/status","state":"%s"}]}\n' "$OID" "${GH_STATE:-SUCCESS}";;
  mixed)       printf '{"number":1,"headRefOid":"%s","statusCheckRollup":[{"name":"a","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"b","status":"COMPLETED","conclusion":"SKIPPED"}]}\n' "$OID";;
esac
exit 0
STUB
chmod +x "$BIN/gh"
export PATH="$BIN:$PATH"

remote_sha(){ git -C "$D/remote.git" rev-parse "$1" 2>/dev/null || echo NONE; }
hsha(){ git -C "$R" rev-parse HEAD; }
newcommit(){ echo "$RANDOM" >> "$R/f.txt"; git_q "$R" add -A; git_q "$R" commit -qm "c$1"; }

# ══ DEFECT 2 — CI GATE ════════════════════════════════════════════════════════════════════════
BEFORE="$(remote_sha master)"

# C1. RED check on the sha we are pushing -> refuse, exit 9, NOTHING pushed.
OUT="$(GH_MODE=conclusion GH_CONCLUSION=FAILURE GH_OID="$(hsha)" $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 9 ] && grep -q 'CI RED' <<<"$OUT" && [ "$(remote_sha master)" = "$BEFORE" ]; then
  ok "C1  red check -> refuses (exit 9), nothing pushed [R1/R4]"
else
  bad "C1  red check: rc=$RC (want 9), remote $BEFORE -> $(remote_sha master)"; sed 's/^/       /' <<<"$OUT"
fi

# C2. PENDING check -> refuse with a DISTINCT message. Not-finished is not a pass.
OUT="$(GH_MODE=status GH_STATUS=IN_PROGRESS GH_OID="$(hsha)" $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 9 ] && grep -q 'CI PENDING' <<<"$OUT" && [ "$(remote_sha master)" = "$BEFORE" ]; then
  ok "C2  pending check -> refuses (exit 9), nothing pushed [R2/R4]"
else
  bad "C2  pending check: rc=$RC (want 9)"; sed 's/^/       /' <<<"$OUT"
fi
if grep -q 'NOT-FINISHED IS NOT A PASS' <<<"$OUT" && ! grep -q 'CI RED' <<<"$OUT"; then
  ok "C2b pending message is distinct from the red message [R2]"
else
  bad "C2b pending refusal is not distinguishable from a red refusal"
fi

# C3. NO PR at all -> WARN but ALLOW. Anti-over-block: every pre-workflow branch has none.
OUT="$(GH_MODE=nopr $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && grep -q 'UNVERIFIED-BY-CI' <<<"$OUT" && [ "$(remote_sha master)" != "$BEFORE" ]; then
  ok "C3  no PR -> warns loudly but ALLOWS, push happened [R3]"
else
  bad "C3  no-PR: rc=$RC (want 0), remote $BEFORE -> $(remote_sha master)"; sed 's/^/       /' <<<"$OUT"
fi
if ! grep -q 'CI GREEN' <<<"$OUT"; then ok "C3b no-PR path never claims CI GREEN"
else bad "C3b no-PR path printed CI GREEN"; fi

# ── C4 — F1, THE HEADLINE DEFECT ──────────────────────────────────────────────────────────────
# The reviewer's exact attack: commit content NO CI RUN HAS EVER SEEN, hand the gate a fully GREEN
# rollup (which describes the PR's OLD head), and confirm the push is no longer blessed as green.
STALE="$(hsha)"
newcommit UNREVIEWED-NEVER-CI-TESTED
FRESH="$(hsha)"
OUT="$(GH_MODE=conclusion GH_CONCLUSION=SUCCESS GH_OID="$STALE" $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if ! grep -q 'CI GREEN' <<<"$OUT"; then
  ok "C4  green rollup for a DIFFERENT sha -> no 'CI GREEN' receipt [R7]"
else
  bad "C4  FALSE RECEIPT: 'CI GREEN' printed for sha $FRESH that checks never covered"; sed 's/^/       /' <<<"$OUT"
fi
if grep -q 'DOES NOT COVER THIS PUSH' <<<"$OUT" && grep -q "$STALE" <<<"$OUT" && grep -q "$FRESH" <<<"$OUT"; then
  ok "C4b it names BOTH shas and says the checks do not cover the push [R7]"
else
  bad "C4b uncovered-push message missing or does not name both shas"; sed 's/^/       /' <<<"$OUT"
fi
if [ "$RC" -eq 0 ]; then
  ok "C4c uncovered push is still ALLOWED (refusing would brick commit-then-push)"
else
  bad "C4c uncovered push rc=$RC (want 0 — warn-and-allow, not block)"; sed 's/^/       /' <<<"$OUT"
fi

# C5. The ONLY green path: the rollup's head IS the sha being published.
OUT="$(GH_MODE=conclusion GH_CONCLUSION=SUCCESS GH_OID="$(hsha)" $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && grep -q 'CI GREEN' <<<"$OUT" && [ "$(remote_sha master)" = "$FRESH" ]; then
  ok "C5  green check ON THE PUSHED SHA -> proceeds, push proven, receipt printed"
else
  bad "C5  green check: rc=$RC (want 0), remote=$(remote_sha master) want=$FRESH"; sed 's/^/       /' <<<"$OUT"
fi

# C5b. --force bypasses the CI gate, explicitly and logged (consistent with the local gate).
OUT="$(GH_MODE=conclusion GH_CONCLUSION=FAILURE GH_OID="$(hsha)" $LP HEAD:master "$R" --force 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && grep -q 'CI gate BYPASSED' <<<"$OUT"; then
  ok "C5b --force bypasses the CI gate and says so"
else
  bad "C5b --force bypass: rc=$RC (want 0)"; sed 's/^/       /' <<<"$OUT"
fi

# ── C6 — F3/F6: the FULL conclusion + status enum, one assertion per value ────────────────────
# This matrix is what makes SEMANTIC WEAKENING fail. Reducing RED to {"FAILURE"} reds the
# TIMED_OUT/CANCELLED/ACTION_REQUIRED/STARTUP_FAILURE rows; restoring `else: ok+=1` reds every
# NEUTRAL/SKIPPED/STALE/unknown row.
ci_case(){ # ci_case <label> <env-assignments...> -- <want_rc> <want_grep> <want_not_grep>
  local label="$1"; shift
  local mode="$1" var="$2" val="$3" want_rc="$4" want="$5" notwant="$6"
  local out rc
  out="$(env GH_MODE="$mode" "$var=$val" GH_OID="$(hsha)" $LP HEAD:master "$R" --gate true 2>&1)"; rc=$?
  if [ "$rc" -eq "$want_rc" ] && grep -q "$want" <<<"$out" && ! grep -q "$notwant" <<<"$out"; then
    ok "C6  $label"
  else
    bad "C6  $label: rc=$rc (want $want_rc) / want='$want' / must-not='$notwant'"; sed 's/^/       /' <<<"$out"
  fi
}
# conclusions that MUST refuse
for c in FAILURE TIMED_OUT CANCELLED ACTION_REQUIRED STARTUP_FAILURE ERROR; do
  ci_case "conclusion $c -> CI RED, exit 9 [R8]" conclusion GH_CONCLUSION "$c" 9 'CI RED' 'CI GREEN'
done
# conclusions that PROVE NOTHING: never green, never counted as passing
for c in NEUTRAL SKIPPED STALE BOGUS_FUTURE_STATE; do
  ci_case "conclusion $c -> NOT green (allowed, unverified) [R8]" conclusion GH_CONCLUSION "$c" 0 'Neutral is not green' 'CI GREEN'
done
# the only green conclusion
ci_case "conclusion SUCCESS -> CI GREEN" conclusion GH_CONCLUSION SUCCESS 0 'CI GREEN' 'CI RED'
# statuses that mean NOT FINISHED
for s in QUEUED IN_PROGRESS WAITING REQUESTED PENDING; do
  ci_case "status $s -> CI PENDING, exit 9 [R2/R8]" status GH_STATUS "$s" 9 'CI PENDING' 'CI GREEN'
done
ci_case "status BOGUS_STATUS -> NOT green [R8]" status GH_STATUS BOGUS_STATUS 0 'Neutral is not green' 'CI GREEN'
# legacy StatusContext objects carry `state`, not `status`/`conclusion`
ci_case "state SUCCESS (StatusContext) -> CI GREEN" context GH_STATE SUCCESS 0 'CI GREEN' 'CI RED'
ci_case "state FAILURE (StatusContext) -> CI RED, exit 9" context GH_STATE FAILURE 9 'CI RED' 'CI GREEN'
ci_case "state ERROR   (StatusContext) -> CI RED, exit 9 [R8]" context GH_STATE ERROR 9 'CI RED' 'CI GREEN'
ci_case "state PENDING (StatusContext) -> CI PENDING, exit 9" context GH_STATE PENDING 9 'CI PENDING' 'CI GREEN'
ci_case "state EXPECTED(StatusContext) -> CI PENDING, exit 9 [R8]" context GH_STATE EXPECTED 9 'CI PENDING' 'CI GREEN'

# C6b. SUCCESS + SKIPPED together: green, but the receipt must SAY the skipped one proved nothing.
OUT="$(GH_MODE=mixed GH_OID="$(hsha)" $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && grep -q 'CI GREEN (PARTIAL)' <<<"$OUT" && grep -q 'SKIPPED:b' <<<"$OUT"; then
  ok "C6b SUCCESS+SKIPPED -> partial-green receipt naming the skipped check [R8]"
else
  bad "C6b mixed rollup: rc=$RC (want 0, 'CI GREEN (PARTIAL)')"; sed 's/^/       /' <<<"$OUT"
fi

# ── C7 — F2: every "gh could not answer" mode must FAIL CLOSED, not read as a clean bill ─────
BEFORE7="$(remote_sha master)"
gh_fail_closed(){ # <mode> <label>
  local out rc
  out="$(GH_MODE="$1" GH_OID="$(hsha)" $LP HEAD:master "$R" --gate true 2>&1)"; rc=$?
  if [ "$rc" -eq 9 ] && grep -q 'CANNOT RUN' <<<"$out" && ! grep -q 'CI GREEN' <<<"$out"; then
    ok "C7  $2 -> exit 9, fails CLOSED [R9]"
  else
    bad "C7  $2: rc=$rc (want 9) — this mode still ALLOWS the push"; sed 's/^/       /' <<<"$out"
  fi
}
gh_fail_closed autherr   "gh not authenticated (rc=4)"
gh_fail_closed neterr    "network error"
gh_fail_closed ratelimit "rate limited (HTTP 403)"
gh_fail_closed emptyout  "rc=0 with EMPTY output"
gh_fail_closed malformed "malformed JSON"
gh_fail_closed html      "HTML 502 body"
gh_fail_closed noid      "response missing headRefOid"
gh_fail_closed badrollup "statusCheckRollup of the wrong type"
if [ "$(remote_sha master)" = "$BEFORE7" ]; then
  ok "C7z no gh-failure mode published anything [R9]"
else
  bad "C7z a gh-failure mode PUSHED: $BEFORE7 -> $(remote_sha master)"
fi

# C7b. `statusCheckRollup: null` is a REAL PR with zero checks — allow, but never green.
OUT="$(GH_MODE=nullrollup GH_OID="$(hsha)" $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && grep -q 'NO passing check' <<<"$OUT" && ! grep -q 'CI GREEN' <<<"$OUT"; then
  ok "C7b null rollup -> real PR with zero checks: allowed, NOT green"
else
  bad "C7b null rollup: rc=$RC (want 0, 'NO passing check', no green)"; sed 's/^/       /' <<<"$OUT"
fi

# C7c. python3 absent is an INABILITY TO CHECK, not a pass.
NOPY="$D/nopy"; mkdir -p "$NOPY"
cp "$BIN/gh" "$NOPY/gh"
for t in git bash sh dirname basename mktemp sed grep egrep find head tail cat cp rm mv ln \
         mkdir chmod tr cut sort uniq wc awk date env printf touch id readlink stat xargs; do
  p="$(command -v "$t" 2>/dev/null)" && ln -sf "$p" "$NOPY/$t"
done
# sanity: the fixture must break ONLY python3, nothing else.
if PATH="$NOPY" command -v python3 >/dev/null 2>&1; then
  bad "C7c fixture is broken — python3 is still on the stripped PATH"
fi
OUT="$(PATH="$NOPY" GH_MODE=conclusion GH_CONCLUSION=SUCCESS GH_OID="$(hsha)" $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 9 ] && grep -q 'python3' <<<"$OUT"; then
  ok "C7c python3 absent -> exit 9, fails CLOSED [R9]"
else
  bad "C7c python3 absent: rc=$RC (want 9)"; sed 's/^/       /' <<<"$OUT"
fi

# ── C8 — F4: DETACHED HEAD must never make the gate silently vanish ──────────────────────────
git_q "$R" checkout -q --detach
DET_BEFORE="$(remote_sha master)"
# C8a. gh cannot enumerate PRs -> refuse. (Pre-fix this asked about a branch literally named HEAD,
#      found nothing, and fell into warn-and-allow.)
OUT="$(GH_LIST=err $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 9 ] && grep -q 'DETACHED' <<<"$OUT" && [ "$(remote_sha master)" = "$DET_BEFORE" ]; then
  ok "C8a detached HEAD + gh failure -> exit 9, nothing pushed [R10]"
else
  bad "C8a detached/gh-fail: rc=$RC (want 9)"; sed 's/^/       /' <<<"$OUT"
fi
# C8b. no open PR carries this sha -> honest "uncovered", allowed, never green.
OUT="$(GH_LIST=other $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && grep -q 'CI UNCOVERED' <<<"$OUT" && ! grep -q 'CI GREEN' <<<"$OUT"; then
  ok "C8b detached HEAD + no PR for this sha -> uncovered, allowed, NOT green [R10]"
else
  bad "C8b detached/no-match: rc=$RC (want 0, 'CI UNCOVERED')"; sed 's/^/       /' <<<"$OUT"
fi
# C8c. the sha's open PR is found -> the gate REALLY RUNS from a detached HEAD.
OUT="$(GH_LIST=match GH_MODE=conclusion GH_CONCLUSION=FAILURE GH_OID="$(hsha)" $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
if [ "$RC" -eq 9 ] && grep -q 'CI RED' <<<"$OUT" && grep -q "feat/work" <<<"$OUT"; then
  ok "C8c detached HEAD resolves the sha's PR and ENFORCES it (exit 9) [R10]"
else
  bad "C8c detached/match: rc=$RC (want 9, CI RED on feat/work)"; sed 's/^/       /' <<<"$OUT"
fi
# C8d. never asks gh about a branch literally named HEAD.
if ! grep -qE "for 'HEAD'" <<<"$OUT"; then ok "C8d never treats the literal string HEAD as a branch [R10]"
else bad "C8d asked gh about a branch named HEAD"; fi
# C8e. rc=0 with a GARBAGE body is "gh could not answer", NOT "no PR carries this sha".
#      Pre-fix, the by-sha parser swallowed every one of these (bare `raise SystemExit(0)` on the
#      exception and wrong-shape branches, printing nothing), CI_BR came back empty, and that was
#      read as "no open PR covers this content" -> push ALLOWED. The identical HTML-502 body on
#      the `pr view` path exited 9 — the inconsistency was the defect. Both paths now share ONE
#      validator (_ci_require_ok), so they cannot drift apart again.
for g in trunc:'truncated JSON' notlist:'valid JSON, wrong shape' binary:'non-UTF8 bytes' html:'HTML 502 body'; do
  E8="$(remote_sha master)"
  OUT="$(GH_LIST="${g%%:*}" $LP HEAD:master "$R" --gate true 2>&1)"; RC=$?
  if [ "$RC" -eq 9 ] && grep -q 'CANNOT RUN' <<<"$OUT" \
     && ! grep -q 'CI GREEN' <<<"$OUT" && ! grep -q 'CI UNCOVERED' <<<"$OUT" \
     && [ "$(remote_sha master)" = "$E8" ]; then
    ok "C8e ${g#*:} from 'gh pr list' -> exit 9, nothing pushed [R10]"
  else
    bad "C8e ${g#*:}: rc=$RC (want 9) — garbage still read as 'no PR carries this sha'"
    sed 's/^/       /' <<<"$OUT"
  fi
done
git_q "$R" checkout -q feat/work

# ══ DEFECT 1 — BOARD GATE SCOPING ═════════════════════════════════════════════════════════════
# A second repo whose gate detection lands on fleet/validate_board.sh, carrying the REAL
# CAPTURE-WIRING-TIMEOUT-FIX / SALVAGE-STASH-CHARON-RUN shape: two tickets owning the SAME path
# with no dep ordering. Marker-DEPENDENT (owns-collision) -> only answerable with state/ present.
git init -q --bare "$D/bremote.git"
git init -q "$D/brepo"; B="$D/brepo"
git_q "$B" remote add origin https://github.com/test/bfixture.git
git_q "$B" config "url.$D/bremote.git.insteadOf" https://github.com/test/bfixture.git
mkdir -p "$B/fleet/board" "$B/fleet/checks" "$B/fleet/prompts"
cp "$FLEET_SRC/validate_board.sh" "$B/fleet/"
cp "$FLEET_SRC/checks/rig-ci-scope.sh" "$B/fleet/checks/"
# rig-ci-scope.sh's board step delegates to its SIBLING substrate-first-gate.{sh,py}, and land-push
# runs the TARGET repo's OWN copy ($REPO/fleet/checks/rig-ci-scope.sh, land-push.sh:~173). A real
# repo carries the whole gate set together, so a faithful fixture must too — otherwise the board step
# 500s on a missing sibling and reds for a reason unrelated to what B5 tests. Seeded in the SEED
# commit so it lands on origin/master and never shows up in any feat branch's PR diff.
cp "$FLEET_SRC/checks/substrate-first-gate.sh" "$FLEET_SRC/checks/substrate_first_gate.py" "$B/fleet/checks/"
echo seed > "$B/seed.txt"; git_q "$B" add -A; git_q "$B" commit -qm seed
git_q "$B" push -q origin HEAD:master; git_q "$B" fetch -q origin
git_q "$B" checkout -q -b feat/board

mk_ticket(){ # mk_ticket <ID> <branch> <owns>
  # work_class rig-meta is in the substrate gate's ALWAYS set, so a well-formed rig-meta ticket must
  # now carry a numeric difficulty AND a substrate answer — otherwise the (correctly firing) board
  # gate reds it for a reason unrelated to the owns-collision scoping these cases test. Self-contained
  # substrate: N/A + substrate-novel keeps the fixture hermetic (no EVAL-REGISTRY needed).
  printf 'prompt: fleet/prompts/%s.md\nrepo: charon-private\nwork_class: rig-meta\ndifficulty: 3\nbranch: %s\nowns: %s\ndepends_on:\nsubstrate: N/A\nsubstrate-novel: a synthetic land-push CI-gate board fixture whose only purpose is to exercise the owns-collision scoping path, which no external tool models, so it is the novel in-house slice under test here\n\n## Dependencies & Sequence\nwave 1; no prereqs; concurrency safe.\n' \
    "$1" "$2" "$3" > "$B/fleet/board/$1.md"
  printf '# %s\n\n## Dependencies & Sequence\nwave 1.\n' "$1" > "$B/fleet/prompts/$1.md"
}
mk_ticket CAPTURE-WIRING-TIMEOUT-FIX feat/capture-wiring-timeout-fix fleet/charon-run.sh
mk_ticket SALVAGE-STASH-CHARON-RUN  feat/salvage-charon-run-timeout  fleet/charon-run.sh
mk_ticket UNRELATED-DONE-TICKET     feat/unrelated-done              fleet/unrelated.sh
git_q "$B" add -A; git_q "$B" commit -qm board

# B5. STATE-LESS checkout (a worktree): NO phantom RED. This is the reproduced live defect.
rm -rf "$B/fleet/state"
OUT="$(GH_MODE=nopr $LP HEAD:master "$B" 2>&1)"; RC=$?
# (match on the GATE RED verdict, not the word "owns-collision" — that word also appears in the
#  scoping explanation land-push prints, which would make this assertion self-satisfying.)
if [ "$RC" -eq 0 ] && ! grep -q 'GATE RED' <<<"$OUT"; then
  ok "B5  state-less checkout -> board gate scoped, no phantom RED [R5]"
else
  bad "B5  state-less checkout redded: rc=$RC (want 0)"; sed 's/^/       /' <<<"$OUT"
fi
# B5b. F8 — it must have examined a NON-ZERO number of tickets. "0 changed ticket(s) checked" is
#      what an unresolvable diff base produces, and it prints the same reassuring line at n=0.
if grep -qE 'board: [1-9][0-9]* changed ticket\(s\) checked' <<<"$OUT"; then
  ok "B5b the scoped subset examined a NON-ZERO ticket count [R11]"
else
  bad "B5b vacuous board check — zero tickets examined (or the subset never ran)"; sed 's/^/       /' <<<"$OUT"
fi
# B5c. F8 — a malformed ticket must still RED through the scoped path (the subset is not a no-op).
git_q "$B" checkout -q -b feat/board2
printf 'repo: charon-private\nwork_class: NOT-A-REAL-CLASS\nbranch: feat/x\nowns: /absolute/path\n\n## Dependencies & Sequence\nw1\n' \
  > "$B/fleet/board/MALFORMED-TICKET.md"
git_q "$B" add -A; git_q "$B" commit -qm malformed
OUT="$(GH_MODE=nopr $LP HEAD:master "$B" 2>&1)"; RC=$?
if [ "$RC" -eq 4 ] && grep -q 'GATE RED' <<<"$OUT"; then
  ok "B5c scoped subset still REDs a malformed ticket (exit 4) [R11]"
else
  bad "B5c malformed ticket slipped through the scoped path: rc=$RC (want 4)"; sed 's/^/       /' <<<"$OUT"
fi
# B5d. F8 — with NO resolvable diff base the check would examine zero tickets and report GREEN.
#      It must refuse instead of silently validating nothing.
git -C "$B" update-ref -d refs/remotes/origin/master
OUT="$(GH_MODE=nopr $LP HEAD:master "$B" 2>&1)"; RC=$?
if [ "$RC" -eq 4 ] && grep -q 'resolvable diff base' <<<"$OUT"; then
  ok "B5d unresolvable diff base -> refuses instead of a vacuous GREEN (exit 4) [R11]"
else
  bad "B5d unresolvable base: rc=$RC (want 4)"; sed 's/^/       /' <<<"$OUT"
fi
git_q "$B" fetch -q origin
git_q "$B" checkout -q feat/board
git -C "$B" branch -qD feat/board2
rm -f "$B/fleet/board/MALFORMED-TICKET.md"

# B6. LIVE-TREE-SHAPED checkout (state/ populated): FULL checks still enforced. The very same
#     board must now RED on the marker-DEPENDENT owns-collision.
mkdir -p "$B/fleet/state/done"; : > "$B/fleet/state/done/UNRELATED-DONE-TICKET"
BB="$(remote_sha master)"
OUT="$(GH_MODE=nopr $LP HEAD:master "$B" 2>&1)"; RC=$?
if [ "$RC" -eq 4 ] && grep -q 'owns-collision' <<<"$OUT" && [ "$(remote_sha master)" = "$BB" ]; then
  ok "B6  live-tree-shaped checkout -> FULL validate_board still enforced (exit 4) [R6]"
else
  bad "B6  live-tree checkout: rc=$RC (want 4, owns-collision RED)"; sed 's/^/       /' <<<"$OUT"
fi

# ── B7 — F7: state detection must not narrate a cause it has not established ─────────────────
# B7a. state/ holding ONLY EMPTY SUBDIRS is genuinely marker-less -> scoped path is correct here.
rm -rf "$B/fleet/state"; mkdir -p "$B/fleet/state/done" "$B/fleet/state/claims"
OUT="$(GH_MODE=nopr $LP HEAD:master "$B" 2>&1)"; RC=$?
if grep -q 'board gate SCOPED' <<<"$OUT" && grep -q "is empty" <<<"$OUT"; then
  ok "B7a state/ with only empty subdirs -> scoped, and SAYS 'empty' (not 'absent') [R12]"
else
  bad "B7a empty-subdir state/: wrong path or wrong stated cause (rc=$RC)"; sed 's/^/       /' <<<"$OUT"
fi
# B7b. state/ SYMLINKED to a POPULATED store: plain `find` will not descend a symlink argument, so
#      the pre-fix probe took the WEAK path while claiming the tree was empty. It must take the
#      FULL path — proven by the marker-dependent owns-collision RED.
rm -rf "$B/fleet/state"
mkdir -p "$D/realstate/done"; : > "$D/realstate/done/UNRELATED-DONE-TICKET"
ln -s "$D/realstate" "$B/fleet/state"
OUT="$(GH_MODE=nopr $LP HEAD:master "$B" 2>&1)"; RC=$?
if [ "$RC" -eq 4 ] && grep -q 'owns-collision' <<<"$OUT" && ! grep -q 'board gate SCOPED' <<<"$OUT"; then
  ok "B7b symlinked populated state/ -> FULL validation, no silent downgrade [R12]"
else
  bad "B7b symlinked state/ took the weak path: rc=$RC (want 4, owns-collision)"; sed 's/^/       /' <<<"$OUT"
fi
rm -f "$B/fleet/state"
# B7c. state/ present but UNREADABLE: the pre-fix probe sent the error to /dev/null and announced
#      "empty/absent (worktree or fresh checkout)" — a stated cause it had not established.
mkdir -p "$B/fleet/state/done"; : > "$B/fleet/state/done/UNRELATED-DONE-TICKET"
chmod 000 "$B/fleet/state"
if [ -r "$B/fleet/state" ]; then
  ok "B7c SKIPPED (running as root — chmod 000 is not enforced)"
else
  OUT="$(GH_MODE=nopr $LP HEAD:master "$B" 2>&1)"; RC=$?
  if [ "$RC" -eq 4 ] && grep -q 'cannot determine board state' <<<"$OUT"; then
    ok "B7c unreadable state/ -> refuses, does NOT claim the tree is empty [R12]"
  else
    bad "B7c unreadable state/: rc=$RC (want 4, 'cannot determine board state')"; sed 's/^/       /' <<<"$OUT"
  fi
fi
chmod 755 "$B/fleet/state"
# B7d. state/ itself readable, but a SUBDIR inside it is not. `find` exits 1 on the permission
#      error, so under `set -e` a bare command substitution killed the script AT the find — rc=1,
#      an exit code absent from the documented table, with ZERO diagnostic. The `if [ -s "$_SERR" ]`
#      line below it was therefore DEAD for the exact case it names ("permission/IO errors are NOT
#      empty"), which is why mutating it changed nothing. It must now reach that line and report
#      the distinct 'cannot determine board state' reason.
rm -rf "$B/fleet/state"; mkdir -p "$B/fleet/state/locked"; : > "$B/fleet/state/locked/M"
chmod 000 "$B/fleet/state/locked"
if [ -r "$B/fleet/state/locked" ]; then
  ok "B7d SKIPPED (running as root — chmod 000 is not enforced)"
else
  OUT="$(GH_MODE=nopr $LP HEAD:master "$B" 2>&1)"; RC=$?
  if [ "$RC" -eq 4 ] && grep -q 'cannot determine board state' <<<"$OUT"; then
    ok "B7d unreadable SUBDIR -> distinct reason + exit 4, not a bare undocumented rc=1 [R12]"
  else
    bad "B7d unreadable subdir: rc=$RC (want 4, 'cannot determine board state')"
    sed 's/^/       /' <<<"$OUT"
  fi
fi
chmod 755 "$B/fleet/state/locked"

printf '\nland-push-ci-gate: %d pass, %d fail\n' "$passes" "$fails"
[ "$fails" -eq 0 ]
