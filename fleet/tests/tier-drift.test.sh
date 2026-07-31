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

echo "== (h) EFFORT replaces BREADTH: nsurf alone can never reach frontier (F5) =="
# REVERT LINE: fleet/capability/tier_classify.py — the money branch's `high_effort` conjunct
# (`if money and (d >= 4 or (livefwd and d >= 3) or high_effort)`) plus
# fleet/capability/effort.py's EFFORT_DIFFICULTY_FLOOR / FRONTIER_EFFORT. Restore the old
# `nsurf >= 3` and case (h1) flips to frontier: a difficulty-2 money ticket that owns three
# small files gets priced at the top tier FOR ITS WHOLE LIFE (tier is a claim CEILING).
# MEASURED on this board: nsurf vs declared tier rho=+0.075 (p=0.43, noise); difficulty +0.413.
cls_a(){ python3 "$SRC/capability/tier_classify.py" classify \
           --work-class "$1" --difficulty "$2" --owns "$3" --accept "$4" | cut -f1; }
wide="src/charon/routing_policy/a.py,src/charon/routing_policy/b.py,src/charon/routing_policy/c.py"
wider="$wide,src/charon/routing_policy/d.py,src/charon/routing_policy/e.py,src/charon/routing_policy/f.py"
got="$(cls_a money-path 2 "$wide" '- one behaviour')"
if [ "$got" = "strong" ]; then
  ok "(h1) d2 money ticket owning 3 files -> $got (breadth alone no longer promotes)"
else
  bad "(h1) d2 money ticket owning 3 files -> $got, expected strong (breadth proxy is back)"
fi
got="$(cls_a money-path 2 "$wider" '- one behaviour')"
if [ "$got" = "strong" ]; then
  ok "(h2) DOUBLING breadth (6 files, same d2) still -> $got — breadth is not a promotion path"
else
  bad "(h2) 6-file d2 money ticket -> $got, expected strong"
fi
# ANTI-NEUTER: the clause must still FIRE on genuinely high-effort work, or the change is just
# a deletion. Same single file, difficulty 3, a real 10-item requirement list -> frontier.
acc="$(printf -- '- behaviour %s\n' 1 2 3 4 5 6 7 8 9 10)"
got="$(cls_a money-path 3 src/charon/routing_policy/a.py "$acc")"
if [ "$got" = "frontier" ]; then
  ok "(h3) d3 money ticket with a 10-behaviour accept -> frontier (EFFORT still promotes)"
else
  bad "(h3) high-effort d3 money ticket -> $got, expected frontier — the effort clause is inert"
fi
# and the DIFFICULTY FLOOR is structural, not arithmetic: the same 10-behaviour accept at d2
# must NOT promote, whatever the score.
got="$(cls_a money-path 2 src/charon/routing_policy/a.py "$acc")"
if [ "$got" = "strong" ]; then
  ok "(h4) same 10-behaviour accept at d2 -> strong (EFFORT_DIFFICULTY_FLOOR is load-bearing)"
else
  bad "(h4) d2 + 10 behaviours -> $got, expected strong — the F5 difficulty floor is gone"
fi
# LIVE PROOF: the one ticket the review named. FT-CATALOG-SEED (greenfield-feature, d2, three
# files) is the ticket breadth mis-priced; it must derive `strong` off the REAL board file.
if [ -f "$SRC/board/FT-CATALOG-SEED.md" ]; then
  got="$(python3 "$SRC/capability/tier_classify.py" classify FT-CATALOG-SEED | cut -f1)"
  if [ "$got" = "strong" ]; then
    ok "(h5) LIVE FT-CATALOG-SEED (the F5 example) derives $got, not frontier"
  else
    bad "(h5) LIVE FT-CATALOG-SEED derives $got, expected strong"
  fi
else
  bad "(h5) fleet/board/FT-CATALOG-SEED.md is missing — cannot prove the F5 example (fail-closed)"
fi

echo "== (i) PORT PARITY: the rig's effort weights == the product's (option (b) cost) =="
# REVERT LINE: fleet/capability/effort.py's DIFFICULTY_WEIGHT / SIZE_WEIGHT / BEHAVIOR_WEIGHT /
# SOFT_THRESHOLD / HARD_THRESHOLD. The scorer is a PORT of the product's
# src/charon/decompose_effort.py (the rig's CI runs a charon-private-only checkout, so importing
# the product module would make this merge-blocking gate unrunnable there). A port's one real
# cost is silent drift — so both sides are pinned by EXECUTION here.
py_const(){ sed -n "s/^$2 = \([0-9.]*\).*/\1/p" "$1" | head -1; }
E="$SRC/capability/effort.py"
for pair in "DIFFICULTY_WEIGHT 2.0" "SIZE_WEIGHT 0.15" "BEHAVIOR_WEIGHT 1.0" \
            "SOFT_THRESHOLD 10.0" "HARD_THRESHOLD 16.0"; do
  set -- $pair
  got="$(py_const "$E" "$1")"
  if [ "$got" = "$2" ]; then
    ok "(i1) effort.py $1 = $got (pinned)"
  else
    bad "(i1) effort.py $1 = '$got', expected $2 — the ported weights drifted"
  fi
done
# Cross-repo half: whenever the PRODUCT tree is resolvable, diff the two sides for real.
PROD="${CHARON_SRC:-/home/stack/code/charon/src}/charon/decompose_effort.py"
if [ -f "$PROD" ]; then
  mism=0
  for pair in "DIFFICULTY_WEIGHT DIFFICULTY_WEIGHT" "SIZE_WEIGHT SIZE_WEIGHT" \
              "BEHAVIOR_WEIGHT BEHAVIOR_WEIGHT" "SOFT_THRESHOLD DEFAULT_SOFT_THRESHOLD" \
              "HARD_THRESHOLD DEFAULT_HARD_THRESHOLD"; do
    set -- $pair
    a="$(py_const "$E" "$1")"; b="$(py_const "$PROD" "$2")"
    [ -n "$b" ] || { bad "(i2) product constant $2 not found in $PROD"; mism=1; continue; }
    [ "$a" = "$b" ] || { bad "(i2) DRIFT: rig $1=$a vs product $2=$b"; mism=1; }
  done
  [ "$mism" -eq 0 ] && ok "(i2) all 5 constants match the product's decompose_effort.py"
else
  # NOT a silent skip: an unchecked case is announced, and (i1) still pins the rig side on
  # every host, so a rig-side edit reds here even where the product tree is absent.
  ok "(i2) product tree absent ($PROD) — cross-repo half UNCHECKED; (i1) still pins the rig side"
fi

echo "== (j) F11: review-class work is never demoted (operator decision 2026-07-24) =="
# REVERT LINE: fleet/capability/tier_classify.py — the `if review and d >= 3:` ratchet and its
# POSITION (immediately after the security ratchet, before every cheaper branch). Restore the
# old `design-review d>=4 else strong` and (j1) flips to strong: every d3 adversarial review
# runs on a cheaper model. Adversarial review is the rig's load-bearing quality mechanism; the
# operator REJECTED trading its capability for cost.
got="$(cls_a design-review 3 fleet/state/DESIGN.md '- judge it')"
if [ "$got" = "frontier" ]; then
  ok "(j1) design-review d3 -> $got (ratchet holds)"
else
  bad "(j1) design-review d3 -> $got, expected frontier — review capability was traded down"
fi
got="$(cls_a design-review 2 fleet/state/DESIGN.md '- judge it')"
if [ "$got" = "strong" ]; then
  ok "(j2) design-review d2 -> $got (floor: review work never falls to economy)"
else
  bad "(j2) design-review d2 -> $got, expected strong"
fi
# ORDER PROOF: a review ticket that ALSO looks money-ish must not be caught by the money
# branch's cheaper `money floor` return. This is what makes it a ratchet rather than a rule.
got="$(cls_a design-review 3 src/charon/pricing.py '- judge it')"
if [ "$got" = "frontier" ]; then
  ok "(j3) money-looking design-review d3 -> $got (ratchet precedes the money floor)"
else
  bad "(j3) money-looking design-review d3 -> $got, expected frontier — ratchet is mis-ordered"
fi
# BOARD-WIDE INVARIANT: no live design-review ticket derives below strong.
low=0
for f in "$SRC"/board/*.md; do
  [ -f "$f" ] || continue
  grep -q '^work_class: design-review$' "$f" || continue
  t="$(python3 "$SRC/capability/tier_classify.py" classify "$(basename "$f" .md)" | cut -f1)"
  case "$t" in strong|frontier) :;; *) bad "(j4) $(basename "$f" .md) review-class -> $t"; low=1;; esac
done
[ "$low" -eq 0 ] && ok "(j4) every LIVE design-review ticket derives strong or frontier"

echo; echo "--- $PASS passed, $FAIL failed ---"
if [ "$FAIL" -eq 0 ]; then
  echo "ALL TIER-DRIFT TESTS PASS"
else
  exit 1
fi
