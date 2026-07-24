#!/usr/bin/env bash
# tier-drift.test.sh — FAIL-ON-REVERT / red-proof tests for the validate_board TIER-DRIFT
# gate (validate_board.sh check "2f") and its rule engine, fleet/capability/tier_classify.py.
#
# Runs every assertion in an ISOLATED temp fleet built by mkfleet() (own validate_board.sh,
# own capability/, own checks/, own board/, own state/). Nothing here touches the live board,
# the live state/ tree or the network — the only thing read out of the real repo is the
# tracked-ness of the shipped RED-set file, which is the whole point of case (a).
#
# THE GATE under test: `tier:` on a ticket used to be free text validated for NOTHING, so a
# hand-set wrong tier routed real work and real spend onto a wrong-capability model chain.
# Check 2f re-derives the tier from work_class/difficulty/owns and compares. A mismatch is a
# WARN by default and a HARD RED for the ids in fleet/state/tier-drift-red.txt.
#
# Each case names the exact REVERT LINE it red-proofs. The three defects this suite exists to
# keep dead (all three shipped green in the gate's first cut):
#   F1  the RED set file was never shipped, so the gate could not go RED in ANY configuration.
#   F2  the gate failed OPEN: it accepted rc 2 as success, but `python3 <missing-file>` and
#       argparse-on-bad-subcommand BOTH exit 2, so moving the classifier deleted the whole
#       check silently and validate_board stayed GREEN.
#   F9  a scan that compared ZERO tickets reported "no drift" — zero discovery was
#       indistinguishable from zero drift.
#
# Run:  bash fleet/tests/tier-drift.test.sh   (exit 0 = all pass, non-zero = RED)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"     # the real fleet/
REPO="$(cd "$SRC/.." && pwd)"
RED_SET_REL="fleet/state/tier-drift-red.txt"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

# mkfleet -> prints a fresh isolated fleet dir: real validate_board.sh + real classifier +
# real checks/ + the shipped RED set + a SMALL board of REAL tickets (real tickets, so the
# rest of validate_board's checks pass and the only thing this suite can move is 2f).
mkfleet(){
  local d; d="$(mktemp -d -p "$ROOT")"
  mkdir -p "$d/state/done" "$d/board"
  cp "$SRC/validate_board.sh" "$d/"
  cp -r "$SRC/capability" "$SRC/checks" "$d/"
  cp "$REPO/$RED_SET_REL" "$d/state/"
  cp "$SRC/board/FIX-PROVIDER-KEY-EXFIL.md" "$SRC/board/DEGRADE-ALERT.md" "$d/board/"
  printf '%s' "$d"
}
mistier(){ sed -i 's/^tier: .*/tier: economy/' "$1/board/FIX-PROVIDER-KEY-EXFIL.md"; }
drift(){ python3 "$1/capability/tier_classify.py" drift 2>&1; }

echo "== (a) the RED set is SHIPPED and GIT-TRACKED (F1) =="
# REVERT LINE: fleet/state/tier-drift-red.txt itself, and the `!fleet/state/tier-drift-red.txt`
# negation in .gitignore. `fleet/state/*` is gitignored wholesale; delete either the file or the
# negation and _red_set() reads nothing, every mismatch degrades to an advisory WARN, and the
# gate can never go RED again — the exact configuration the gate originally shipped in.
if [ -s "$REPO/$RED_SET_REL" ]; then
  ok "(a1) $RED_SET_REL exists and is non-empty"
else
  bad "(a1) $RED_SET_REL is missing or empty — the tier-drift gate has no hard-fail set"
fi
ids="$(grep -v '^[[:space:]]*#' "$REPO/$RED_SET_REL" 2>/dev/null | grep -c '[^[:space:]]')"
if [ "${ids:-0}" -ge 5 ]; then
  ok "(a2) RED set carries $ids ticket ids (non-vacuous hard-fail set)"
else
  bad "(a2) RED set carries only ${ids:-0} ids — a near-empty set is a gate with no teeth"
fi
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  if git -C "$REPO" ls-files --error-unmatch "$RED_SET_REL" >/dev/null 2>&1; then
    ok "(a3) RED set is git-TRACKED (survives a fresh clone / every worktree)"
  else
    bad "(a3) RED set is NOT git-tracked — gitignored by fleet/state/*; the gate ships toothless"
  fi
else
  bad "(a3) cannot verify tracking: $REPO is not a git repo (fail-closed, not assumed-tracked)"
fi

echo "== (b) a mis-tiered RED-SET ticket drives the classifier to the RED sentinel (F1) =="
# REVERT LINE: fleet/capability/tier_classify.py, the `drift` branch — `return DRIFT_RED_RC if
# any_red else 0` and the `level = "RED" if tid in red else "WARN"` selection.
d="$(mkfleet)"; mistier "$d"; out="$(drift "$d")"; rc=$?
if [ "$rc" -eq 3 ] && printf '%s\n' "$out" | grep -q '^RED tier-drift: FIX-PROVIDER-KEY-EXFIL '; then
  ok "(b1) mis-tiered security ticket -> 'RED tier-drift' + rc 3 (the distinct RED sentinel)"
else
  bad "(b1) mis-tiered security ticket -> RED + rc 3 (got rc=$rc, out: $out)"
fi
# UN-GAMED: prove rc 3 comes from the RED SET, not merely from any mismatch. Same mis-tier,
# RED set removed -> advisory WARN, rc 0. If this ever returns 3 the RED set is not what is
# selecting hard failures and case (a) stops meaning anything.
rm -f "$d/state/tier-drift-red.txt"; out="$(drift "$d")"; rc=$?
if [ "$rc" -eq 0 ] && printf '%s\n' "$out" | grep -q '^WARN tier-drift: FIX-PROVIDER-KEY-EXFIL '; then
  ok "(b2) same mis-tier with NO RED set -> WARN/rc 0 — the shipped file IS what supplies teeth"
else
  bad "(b2) same mis-tier with NO RED set -> WARN/rc 0 (got rc=$rc, out: $out)"
fi

echo "== (c) validate_board turns that RED into a RED PREFLIGHT, end to end (F1+F2) =="
# REVERT LINE: fleet/validate_board.sh check 2f — the `if _line.startswith("RED "):
# red.append(...)` branch and the `_td.returncode == _TIER_DRIFT_RED_RC` handling.
d="$(mkfleet)"; out="$(bash "$d/validate_board.sh" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && ! printf '%s\n' "$out" | grep -q 'tier-drift'; then
  ok "(c1) CONTROL: an undisturbed board is GREEN (rc 0) with no tier-drift line"
else
  bad "(c1) CONTROL: undisturbed board should be GREEN with no tier-drift (rc=$rc, out: $out)"
fi
mistier "$d"; out="$(bash "$d/validate_board.sh" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] \
   && printf '%s\n' "$out" | grep -q 'tier-drift: FIX-PROVIDER-KEY-EXFIL declared=economy derived=frontier'; then
  ok "(c2) mis-tiered security ticket -> validate_board RED (rc=$rc), wave does NOT launch"
else
  bad "(c2) mis-tiered security ticket -> validate_board RED (rc=$rc, out: $out)"
fi

echo "== (d) FAIL-CLOSED: a MISSING classifier is RED, not silently green (F2) =="
# REVERT LINE: fleet/validate_board.sh check 2f — the `if not os.path.exists(_tc_path):`
# guard. Drop it and `mv capability/tier_classify.py .bak` makes the entire check vanish
# with no RED, no WARN and no stderr, because python3 exits 2 on a missing file and the old
# code accepted rc 2 as success.
d="$(mkfleet)"; mv "$d/capability/tier_classify.py" "$d/capability/tier_classify.py.bak"
out="$(bash "$d/validate_board.sh" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && printf '%s\n' "$out" | grep -q 'tier-drift-check-missing'; then
  ok "(d1) classifier absent -> validate_board RED 'tier-drift-check-missing' (rc=$rc)"
else
  bad "(d1) classifier absent must be RED with tier-drift-check-missing (rc=$rc, out: $out)"
fi
# and the rc-2 collision that made the old guard useless is documented by execution:
python3 "$d/capability/does-not-exist.py" drift >/dev/null 2>&1; py_missing_rc=$?
if [ "$py_missing_rc" -eq 2 ]; then
  ok "(d2) python3 on a missing file exits 2 — so rc 2 can NEVER mean 'RED drift found'"
else
  bad "(d2) expected python3-missing-file rc 2, got $py_missing_rc (the sentinel choice needs rechecking)"
fi

echo "== (e) FAIL-CLOSED: rc 2 from the check itself is a HARD FAILURE (F2) =="
# REVERT LINE: fleet/validate_board.sh check 2f — `elif _td.returncode != 0:` (the old code
# was `if _td.returncode not in (0, 2)`). Restore the (0, 2) allowance and this stub — which
# is exactly what a renamed `drift` subcommand or a broken import looks like — passes silently.
d="$(mkfleet)"
printf '#!/usr/bin/env python3\nimport sys\nsys.exit(2)\n' > "$d/capability/tier_classify.py"
out="$(bash "$d/validate_board.sh" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && printf '%s\n' "$out" | grep -q 'tier-drift-check-failed'; then
  ok "(e1) classifier exiting 2 -> validate_board RED 'tier-drift-check-failed' (rc=$rc)"
else
  bad "(e1) classifier exiting 2 must be RED (rc=$rc, out: $out)"
fi

echo "== (f) NON-VACUOUS: a zero-item scan is RED, not a confident pass (F9) =="
# REVERT LINE: fleet/capability/tier_classify.py, the `drift` branch — the
# `if examined == 0:` block (and `board_scan`'s `examined` counter that feeds it). Without it
# a bad --board, an empty checkout, or a board where nobody declares `tier:` prints nothing
# and exits 0, which reads as "verified drift-free".
d="$(mkfleet)"; mkdir -p "$d/emptyboard"
out="$(python3 "$d/capability/tier_classify.py" drift --board "$d/emptyboard" 2>&1)"; rc=$?
if [ "$rc" -eq 3 ] && printf '%s\n' "$out" | grep -q 'tier-drift-vacuous'; then
  ok "(f1) empty board dir -> RED tier-drift-vacuous, rc 3"
else
  bad "(f1) empty board dir must be RED/rc 3 (got rc=$rc, out: $out)"
fi
mkdir -p "$d/notierboard"
printf 'work_class: docs\ndifficulty: 1\nowns: docs/a.md\n' > "$d/notierboard/A.md"
printf 'work_class: docs\ndifficulty: 2\nowns: docs/b.md\n' > "$d/notierboard/B.md"
out="$(python3 "$d/capability/tier_classify.py" drift --board "$d/notierboard" 2>&1)"; rc=$?
if [ "$rc" -eq 3 ] && printf '%s\n' "$out" | grep -q 'tier-drift-vacuous'; then
  ok "(f2) tickets present but zero declared tiers -> RED tier-drift-vacuous, rc 3"
else
  bad "(f2) zero declared tiers must be RED/rc 3 (got rc=$rc, out: $out)"
fi
# and the LIVE board must be on the non-vacuous side of that line: if the real gate ever
# starts comparing 0 tickets, this suite says so BEFORE the gate reports a false green.
out="$(python3 "$SRC/capability/tier_classify.py" drift --board "$SRC/board" 2>&1)"
if ! printf '%s\n' "$out" | grep -q 'tier-drift-vacuous'; then
  ok "(f3) the LIVE board is non-vacuous — the real gate is comparing >0 declared tiers"
else
  bad "(f3) the LIVE gate is scanning ZERO declared tiers (out: $out)"
fi

echo "== (g) SEC_RE is ANCHORED: trivial docs are not routed to the frontier chain (F3) =="
# REVERT LINE: fleet/capability/tier_classify.py — the SEC_RE anchoring (`_SEC_STRONG` /
# `_SEC_AMBIG` alternation with its component-boundary anchors). Revert to the unanchored
# substring pattern and every path below flips to frontier: SEC_RE is the FIRST rule and has
# no difficulty guard, so a d1 docs ticket becomes claimable ONLY by a frontier droid.
cls(){ python3 "$SRC/capability/tier_classify.py" classify --work-class docs --difficulty 1 --owns "$1" | cut -f1; }
for p in docs/token-budget.md docs/authoring-guide.md docs/keyboard-shortcuts.md \
         docs/oauth-notes.md fleet/state/AUTHORS.md; do
  got="$(cls "$p")"
  if [ "$got" = "economy" ]; then
    ok "(g1) d1 docs '$p' -> $got (not a security surface)"
  else
    bad "(g1) d1 docs '$p' -> $got, expected economy (unanchored SEC_RE false positive)"
  fi
done
# ANTI-NEUTER: anchoring must not have disarmed the rule on real security surfaces.
for p in src/charon/secrets.py src/charon/keyprobe.py src/charon/config/providers.py \
         fleet/checks/egress-key-canary.sh src/charon/auth.py fleet/auth/wire.sh \
         src/charon/api_key_store.py src/charon/tokens.py; do
  got="$(cls "$p")"
  if [ "$got" = "frontier" ]; then
    ok "(g2) security surface '$p' -> frontier (ratchet intact)"
  else
    bad "(g2) security surface '$p' -> $got, expected frontier — SEC_RE was neutered"
  fi
done
# CASE: the choice is deliberate, not accidental. Same stem, different capitalisation, same tier.
if [ "$(cls src/charon/SECRETS.py)" = "$(cls src/charon/secrets.py)" ]; then
  ok "(g3) SEC_RE is case-insensitive by design — capitalisation cannot change the tier"
else
  bad "(g3) SEC_RE tier depends on capitalisation (SECRETS.py != secrets.py)"
fi

echo; echo "--- $PASS passed, $FAIL failed ---"
if [ "$FAIL" -eq 0 ]; then
  echo "ALL TIER-DRIFT TESTS PASS"
else
  exit 1
fi
