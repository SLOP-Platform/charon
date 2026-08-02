#!/usr/bin/env bash
# board-lock-frontmatter.test.sh — FAIL-ON-REVERT tests for the board-lock FRONTMATTER PARSE-CHECK.
#
# THE COST THIS CLOSES (2026-08-01 — FIVE breakages in ONE session, all the same shape):
#   LOOP-GUARD-REASON-WIRE     — a `D&S — Deps & Sequence:` pseudo-key whose list items carry ': '
#   CAPTURE-WIRING-TIMEOUT-FIX — `real-dep:` multi-line prose
#   MODEL-HARDCODE-PURGE       — a pseudo-key plus backticks
#   REVIEWER-TAB-POOL          — `serial_justified:` prose containing ': '
#   LAUNCHER-GATE-SETE-KILL    — `substrate:` prose containing ': '
# Every one was a PROSE value written as a PLAIN scalar. Nothing parsed ticket frontmatter until
# PUSH (rig-ci-scope.sh -> substrate-first-gate.sh), so each was found 1-3 commits after it was
# written and cost a full push cycle. The parse now runs at the board-lock commit choke point.
#
# WHAT IS PROVEN (each assertion names the revert that turns it RED):
#   1 REFUSAL on the real shapes — all five defect shapes REFUSE with the documented exit 7, and
#     NOTHING is committed while the author's content survives on disk.
#     Revert: drop the `_frontmatter_check "$@" || return $?` line from _commit_locked.
#   2 NO FALSE RED — the correct BLOCK-SCALAR spelling of the same prose commits cleanly, and a
#     ticket that merely omits optional fields is not invented into a failure.
#     Revert: refuse on any ': ' in the file rather than on a real parse verdict.
#   3 ACTIONABLE — the refusal names the FILE, the LINE, the parse error, and the fix wording
#     ("quote the value or make it a block scalar (`key: |`)") the downstream gate already uses.
#     Revert: replace the reused rule module with a bare `yaml.safe_load` / a hand-rolled check.
#   4 DIFF-SCOPED — a pre-existing broken ticket that is NOT in this commit's pathspec does not
#     block the commit, and a non-board file (and fleet/board/archive/) is ignored entirely.
#     Revert: parse the whole board instead of `git diff --cached ... -- <pathspec>`.
#   5 AUDITED ESCAPE — BOARD_LOCK_FM_BYPASS (and the broader BOARD_LOCK_BYPASS) let a genuinely
#     broken pre-existing ticket through, LOUDLY, so the board can never be permanently wedged.
#     Revert: drop the bypass branch -> a broken ticket becomes uncommittable forever.
#   6 AGREES WITH THE DOWNSTREAM GATE — for every fixture, board-lock's parse verdict matches
#     `fleet/checks/substrate-first-gate.sh check`'s parse verdict, in BOTH directions. A commit
#     that passes here can never fail there for parse reasons, which is the whole contract.
#     Revert: split the frontmatter differently here (a second convention) -> the two diverge.
#
# ONE KNOWN, DELIBERATE DIVERGENCE (found building this, verified 2026-08-01 — reported, NOT
# silently mirrored): board-lock parses EVERY ticket it carries, including a PARKED one.
# rig-ci-scope.sh:_check_ticket calls _is_parked (a sed field read, which works on text that does
# not parse) and RETURNS BEFORE invoking substrate-first-gate.sh — so in CI a `parked: true` ticket
# with unparseable frontmatter is skipped entirely and is GREEN. The parser of record disagrees
# with that skip: `substrate-first-gate.sh check` on the same file exits 1 with the parse RED.
# board-lock therefore sides with the PARSER, not with the pre-filter. The direction is the safe
# one — board-lock is stricter, so nothing that passes here can fail there for parse reasons —
# and it stops a parked ticket from carrying a latent RED until the day it is unparked.
# Not asserted as a fixture here because fleet/checks/ is out of this ticket's scope to change.
#
# HERMETIC: the REAL fleet/board-lock.sh, the REAL fleet/hooks/pre-commit and the REAL
# fleet/checks/ (including substrate_first_gate.py, the parser of record) are COPIED verbatim into
# a temp fleet — the code under test is the real code, never a transcription — and driven against
# a real git repo under mktemp -d. No network, no gh, no touch of the live fleet/state.
#
# `set -uo pipefail` (not -e) deliberately: this suite asserts on NON-ZERO exit codes, and -e
# would abort the run on the first intentional refusal. Same reason board-lock.sh itself omits -e.
#
# Run:  bash fleet/tests/board-lock-frontmatter.test.sh   (exit 0 = all pass, 1 = a failure)
set -uo pipefail

REAL_FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad(){  FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ── hermetic FLEET carrying the REAL scripts ────────────────────────────────────────────────
FLEET="$TMP/fleet"
mkdir -p "$FLEET/hooks" "$FLEET/board/archive" "$FLEET/state"
cp "$REAL_FLEET/board-lock.sh"    "$FLEET/board-lock.sh"
cp "$REAL_FLEET/hooks/pre-commit" "$FLEET/hooks/pre-commit"
# checks/ carries substrate_first_gate.py — the SAME module board-lock now calls. Copying the real
# dir (not a stub) is what makes assertion 6 an agreement proof rather than a tautology.
cp -r "$REAL_FLEET/checks" "$FLEET/checks"
[ -f "$REAL_FLEET/state/EVAL-REGISTRY.md" ] && cp "$REAL_FLEET/state/EVAL-REGISTRY.md" "$FLEET/state/"
chmod +x "$FLEET/board-lock.sh" "$FLEET/hooks/pre-commit"
BL="$FLEET/board-lock.sh"
SG="$FLEET/checks/substrate-first-gate.sh"

# work-lease.sh is the hook's SECOND leg. Stub it to a pass so this suite isolates the frontmatter
# leg (work-lease.test.sh owns proving the lease leg). The board leg still runs for real.
printf '#!/usr/bin/env bash\nexit 0\n' > "$FLEET/work-lease.sh"; chmod +x "$FLEET/work-lease.sh"

# ── a real git repo whose worktree IS the fleet's parent (so fleet/board/ is repo-relative) ──
REPO="$TMP"
git -C "$REPO" init -q 2>/dev/null
git -C "$REPO" config user.email t@t; git -C "$REPO" config user.name t
git -C "$REPO" config commit.gpgsign false
ln -sf "$FLEET/hooks/pre-commit" "$REPO/.git/hooks/pre-commit"

printf 'id\tstatus\n' > "$REPO/fleet/state/ROADMAP.tsv"
printf 'repo: charon\ntier: strong\n' > "$REPO/fleet/board/SEED.md"
git -C "$REPO" add -A >/dev/null 2>&1
git -C "$REPO" -c core.hooksPath=/dev/null commit -q -m seed --no-verify

# run <cmd...> in $REPO, capturing stdout/stderr; echoes the exit code.
run(){ ( cd "$REPO" && "$@" ) >"$TMP/out" 2>"$TMP/err"; echo $?; }
head_sha(){ git -C "$REPO" rev-parse HEAD; }

# ── the FIVE REAL DEFECT SHAPES, verbatim in structure ───────────────────────────────────────
# A common valid prelude so the ONLY difference between a fixture and its fixed twin is the
# offending value — otherwise a refusal could be blamed on something else in the ticket.
PRELUDE=$'repo: charon\ntier: strong\npriority: 2\ndifficulty: 3\nwork_class: bugfix\nbranch: fix/x\nowns: fleet/a.sh\n'

# REVIEWER-TAB-POOL: `serial_justified:` prose containing ': ' (offending value on file line 8).
fx_serial(){ printf '%s' "$PRELUDE"; printf 'depends_on:\nserial_justified: One reviewer pool: the tabs are cohesive.\n'; }
# LAUNCHER-GATE-SETE-KILL: `substrate:` prose containing ': '.
fx_substrate(){ printf '%s' "$PRELUDE"; printf 'substrate: bash set -e — reject — reason: the trap is ours.\n'; }
# MODEL-HARDCODE-PURGE: a pseudo-key plus backticks (backtick is a RESERVED YAML indicator).
fx_backtick(){ printf '%s' "$PRELUDE"; printf 'substrate: `ripgrep` — reject — grep locates, never concludes\n'; }
# LOOP-GUARD-REASON-WIRE: a `D&S — Deps & Sequence:` pseudo-key whose list items carry ': ' AND
# wrap onto a second line. Copied in structure from the real pre-fix ticket (13c538a^): the
# wrapped `- Depends on X: <prose that continues on the next line>` is an implicit mapping key
# spanning two lines, which YAML rejects with "could not find expected ':'".
# NOTE the discipline this fixture cost: the first draft of it (`- after X: needs the field`, one
# line) PARSED CLEANLY — a one-line `- k: v` is a perfectly legal nested mapping. The defect is
# the WRAP, not the colon. A fixture that does not actually break proves nothing.
fx_pseudokey(){ printf '%s' "$PRELUDE"
  printf 'D&S — Deps & Sequence:\n'
  printf '  - Depends on SESSION-REPORT-WIRE: both edit `fleet/fleet-droid.sh` (LAUNCHER-CRASH\n'
  printf '    is the third owner, sequenced last). Collision ordering, not a build prereq.\n'; }
# CAPTURE-WIRING-TIMEOUT-FIX: `real-dep:` multi-line prose.
fx_realdep(){ printf '%s' "$PRELUDE"; printf 'real-dep: CAPTURE-WIRING build-dep\n  the timeout path is shared: both write the same fd\n'; }
# The CORRECT spelling of the same prose — a block scalar. Must PASS.
fx_blockscalar(){ printf '%s' "$PRELUDE"; printf 'depends_on:\nserial_justified: |\n  One reviewer pool: the tabs are cohesive.\n  substrate: `ripgrep` — reject — grep locates, never concludes\n'; }
# A ticket with NO frontmatter at all (starts at a markdown heading -> the head is empty).
fx_nofrontmatter(){ printf '# LOOP GUARD\n\nProse only, no fields at all.\n'; }

# write_ticket <name> <fixture-fn>
write_ticket(){ "$2" > "$REPO/fleet/board/$1.md"; }

echo "== 1. REFUSAL: every one of the five REAL defect shapes is refused at commit =="
i=0
for pair in "SERIAL:fx_serial" "SUBSTRATE:fx_substrate" "BACKTICK:fx_backtick" \
            "PSEUDOKEY:fx_pseudokey" "REALDEP:fx_realdep"; do
  i=$((i+1))
  name="${pair%%:*}"; fn="${pair#*:}"
  write_ticket "$name" "$fn"
  before="$(head_sha)"
  rc="$(run bash "$BL" commit --session S -m "board: $name" -- "fleet/board/$name.md")"
  check "1.$i $name REFUSED with the documented exit 7" "$rc" "7"
  check "1.$i $name nothing was committed" "$(head_sha)" "$before"
  grep -q 'UNPARSEABLE frontmatter' "$TMP/err" \
    && ok "1.$i $name refusal is LOUD" || bad "1.$i $name refusal banner missing"
  grep -q "fleet/board/$name.md" "$TMP/err" \
    && ok "1.$i $name refusal NAMES the file" || bad "1.$i $name refusal does not name the file"
  # the author's edit must still be on disk — a refusal never eats content
  [ -s "$REPO/fleet/board/$name.md" ] && ok "1.$i $name content intact on disk" \
    || bad "1.$i $name content lost on refusal"
  bash "$BL" release S >/dev/null 2>&1
  rm -f "$REPO/fleet/board/$name.md"; git -C "$REPO" reset -q >/dev/null 2>&1
done

echo "== 2. NO FALSE RED: the correct BLOCK-SCALAR spelling of the same prose commits =="
write_ticket BLOCKOK fx_blockscalar
before="$(head_sha)"
rc="$(run bash "$BL" commit --session S -m 'board: BLOCKOK' -- fleet/board/BLOCKOK.md)"
check "2.1 block-scalar ticket ALLOWED (exit 0)" "$rc" "0"
[ "$(head_sha)" != "$before" ] && ok "2.2 the board commit landed" || bad "2.2 nothing was committed"
git -C "$REPO" show --name-only --format= HEAD | grep -q 'fleet/board/BLOCKOK.md' \
  && ok "2.3 the ticket is in the commit" || bad "2.3 ticket missing from the commit"

echo "== 3. ACTIONABLE: file + line + parse error + the SAME fix wording as the CI gate =="
write_ticket SERIAL fx_serial
run bash "$BL" commit --session S -m 'board: SERIAL' -- fleet/board/SERIAL.md >/dev/null
# PRELUDE is 7 lines, then `depends_on:` (8) and the offending `serial_justified:` (9).
grep -q 'at line 9' "$TMP/err" \
  && ok "3.1 refusal names the LINE of the offending value" \
  || bad "3.1 no line number (err: $(grep -m1 SERIAL "$TMP/err"))"
grep -q 'mapping values are not allowed here' "$TMP/err" \
  && ok "3.2 refusal carries the real parser error" || bad "3.2 parser error text missing"
grep -q 'block scalar' "$TMP/err" \
  && ok "3.3 refusal suggests the fix (block scalar)" || bad "3.3 fix suggestion missing"
grep -q 'BOARD_LOCK_FM_BYPASS' "$TMP/err" \
  && ok "3.4 refusal names the audited escape" || bad "3.4 escape not named"
bash "$BL" release S >/dev/null 2>&1

echo "== 4. DIFF-SCOPED: someone else's broken ticket, non-board files and archive/ are ignored =="
# SERIAL.md (broken) stays on disk and UNCOMMITTED — it stands for a pre-existing broken ticket
# this lane does not own. A commit of a DIFFERENT, valid ticket must still go through.
write_ticket OTHEROK fx_blockscalar
before="$(head_sha)"
rc="$(run bash "$BL" commit --session S -m 'board: OTHEROK' -- fleet/board/OTHEROK.md)"
check "4.1 a foreign BROKEN ticket does not block an unrelated board commit" "$rc" "0"
[ "$(head_sha)" != "$before" ] && ok "4.2 the unrelated commit landed" || bad "4.2 commit blocked"

# A non-board file carrying the SAME unparseable text must be ignored (this gate is board-scoped).
mkdir -p "$REPO/docs"; fx_serial > "$REPO/docs/NOT-A-TICKET.md"
before="$(head_sha)"
rc="$(run bash "$BL" commit --session S -m 'docs: not a ticket' -- docs/NOT-A-TICKET.md)"
check "4.3 a NON-board .md with the same defect is IGNORED (exit 0)" "$rc" "0"
[ "$(head_sha)" != "$before" ] && ok "4.4 the non-board commit landed" || bad "4.4 non-board commit blocked"

# fleet/board/archive/ is retired work; rig-ci-scope's ^fleet/board/[^/]+\.md$ excludes it, so
# this must too — mirroring the downstream scope is the point.
fx_serial > "$REPO/fleet/board/archive/RETIRED.md"
before="$(head_sha)"
rc="$(run bash "$BL" commit --session S -m 'board: retire' -- fleet/board/archive/RETIRED.md)"
check "4.5 fleet/board/archive/ is out of scope (matches rig-ci-scope's regex)" "$rc" "0"
[ "$(head_sha)" != "$before" ] && ok "4.6 the archive commit landed" || bad "4.6 archive commit blocked"

echo "== 5. NO-FRONTMATTER ticket is refused, exactly as the downstream gate refuses it =="
write_ticket EMPTYFM fx_nofrontmatter
before="$(head_sha)"
rc="$(run bash "$BL" commit --session S -m 'board: EMPTYFM' -- fleet/board/EMPTYFM.md)"
check "5.1 a ticket with NO frontmatter is REFUSED (exit 7)" "$rc" "7"
check "5.2 nothing was committed" "$(head_sha)" "$before"
grep -q 'frontmatter is EMPTY' "$TMP/err" \
  && ok "5.3 refusal uses the downstream gate's own EMPTY wording" || bad "5.3 EMPTY wording missing"
bash "$BL" release S >/dev/null 2>&1

echo "== 6. AUDITED ESCAPE: a genuinely broken ticket can be forced through, LOUDLY =="
before="$(head_sha)"
rc="$( ( cd "$REPO" && BOARD_LOCK_FM_BYPASS=1 bash "$BL" commit --session S \
        -m 'board: forced' -- fleet/board/EMPTYFM.md ) >"$TMP/out" 2>"$TMP/err"; echo $? )"
check "6.1 BOARD_LOCK_FM_BYPASS lets the broken ticket through (exit 0)" "$rc" "0"
[ "$(head_sha)" != "$before" ] && ok "6.2 the forced commit landed" || bad "6.2 forced commit did not land"
grep -q 'PARSE-CHECK BYPASSED' "$TMP/err" \
  && ok "6.3 the bypass is LOUD, not silent" || bad "6.3 bypass banner missing"
grep -q 'frontmatter-refused\|PARSE-CHECK BYPASSED' "$FLEET/state/board-lock.log" 2>/dev/null \
  && ok "6.4 the escape is written to the audit log" || bad "6.4 nothing in state/board-lock.log"

# The BROADER escape must cover it too — bypassing the board lock cannot leave a stricter
# sub-check still armed, or BOARD_LOCK_BYPASS would stop being a way out.
write_ticket SERIAL2 fx_serial
before="$(head_sha)"
rc="$( ( cd "$REPO" && BOARD_LOCK_BYPASS=1 bash "$BL" commit --session S \
        -m 'board: forced2' -- fleet/board/SERIAL2.md ) >"$TMP/out" 2>"$TMP/err"; echo $? )"
check "6.5 BOARD_LOCK_BYPASS (the broader escape) also covers the parse-check" "$rc" "0"
[ "$(head_sha)" != "$before" ] && ok "6.6 the broadly-forced commit landed" || bad "6.6 commit did not land"

echo "== 7. AGREEMENT with the downstream gate, in BOTH directions =="
# The contract: what board-lock REFUSES for parse reasons, substrate-first-gate.sh must also flag
# for parse reasons — and what board-lock PASSES, it must not. Any mismatch here means a second
# frontmatter convention crept in, which is the exact failure this design forbids.
#   downstream_parse_red <file> -> "1" if the CI gate reports a PARSE verdict, else "0"
downstream_parse_red(){
  local out
  out="$( cd "$REPO" && SUBSTRATE_REGISTRY="$FLEET/state/EVAL-REGISTRY.md" \
          bash "$SG" check "$1" 2>&1 )"
  case "$out" in
    *"does not parse as YAML"*|*"frontmatter is EMPTY"*) echo 1 ;;
    *) echo 0 ;;
  esac
}
#   boardlock_parse_red <file> -> "1" if board-lock refuses it for parse reasons, else "0"
boardlock_parse_red(){
  local rc
  git -C "$REPO" reset -q >/dev/null 2>&1
  rc="$(run bash "$BL" commit --session AG -m 'agreement probe' -- "${1#"$REPO"/}")"
  bash "$BL" release AG >/dev/null 2>&1
  [ "$rc" = "7" ] && echo 1 || echo 0
}
j=0
for pair in "AGSERIAL:fx_serial:1" "AGSUBSTRATE:fx_substrate:1" "AGBACKTICK:fx_backtick:1" \
            "AGPSEUDO:fx_pseudokey:1" "AGREALDEP:fx_realdep:1" \
            "AGBLOCKOK:fx_blockscalar:0" "AGEMPTYFM:fx_nofrontmatter:1"; do
  j=$((j+1))
  name="${pair%%:*}"; rest="${pair#*:}"; fn="${rest%%:*}"; want="${rest#*:}"
  write_ticket "$name" "$fn"
  bl="$(boardlock_parse_red "$REPO/fleet/board/$name.md")"
  dg="$(downstream_parse_red "$REPO/fleet/board/$name.md")"
  check "7.$j $name board-lock verdict matches the expected parse verdict" "$bl" "$want"
  check "7.$j $name board-lock AGREES with substrate-first-gate (bl=$bl dg=$dg)" "$bl" "$dg"
  # the fixtures that PASSED were committed by the probe; the refused ones were not
  rm -f "$REPO/fleet/board/$name.md"
done

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL BOARD-LOCK FRONTMATTER TESTS PASS"
