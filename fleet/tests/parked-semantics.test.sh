#!/usr/bin/env bash
# parked-semantics.test.sh — FAIL-ON-REVERT tests for the PARKED predicate.
#
# THE BUG (2026-07-16, crash-recovery session): claim.sh skipped a ticket only when its
# `parked:` value was the literal string true/yes/1. But park reasons are written as PROSE —
# BENCH-PROVISIONAL-SCORING carried `parked: operator-led DEEP-DIVE ... Do NOT route to an SG
# droid`. That parsed as UNPARKED, so an explicit operator directive was silently ignored and
# the ticket stayed claimable. status.sh never read `parked:` at all, so it printed such
# tickets as `ready` — the manager planned waves around work no droid could take.
#
# THE RULE (canonical: is_parked_value() in _lib.sh): a ticket is PARKED iff `parked:` is
# present, NON-EMPTY, and not an explicit false (false/no/0). Empty means NOT parked —
# MEMORY-INDEX-COMPACTION ships `parked:` with no value and must stay claimable.
#
# Runs OFFLINE against temp fixtures; never touches the live board or state.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
ok(){ printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

# ── 1. the canonical predicate (_lib.sh) ───────────────────────────────────────────────
# shellcheck source=/dev/null
source "$FLEET/_lib.sh"

# prose park -> PARKED. Reverting is_parked_value to `== "true"` drops this -> RED.
is_parked_value "operator-led deep-dive — do not route to an sg droid" \
  && ok "prose park value is PARKED" || bad "prose park value read as UNPARKED (the bug)"
is_parked_value "true" && ok "parked: true is PARKED"  || bad "parked: true read as UNPARKED"
is_parked_value "yes"  && ok "parked: yes is PARKED"   || bad "parked: yes read as UNPARKED"
# empty -> NOT parked (MEMORY-INDEX-COMPACTION depends on this).
is_parked_value ""      && bad "empty parked: wrongly PARKED — would strand claimable tickets" \
                        || ok "empty parked: is NOT parked"
is_parked_value "false" && bad "parked: false wrongly PARKED" || ok "parked: false is NOT parked"

# ── 2. claim.sh's INLINE awk rule must AGREE with _lib.sh ──────────────────────────────
# claim.sh cannot source the helper (its loop must not fork per ticket — PERF note at
# claim.sh:26), so the rule is duplicated. This asserts the two never drift apart again.
#
# The condition is EXTRACTED FROM claim.sh ITSELF and evaluated, rather than transcribed
# here — a transcribed copy would only ever test itself and would sail through a real drift.
PARKED_COND="$(grep -vE '^[[:space:]]*#' "$FLEET/claim.sh" \
  | grep -E 'if \(parked .*\) next' | head -1 | sed -E 's/^[[:space:]]*if \((.*)\) next[[:space:]]*$/\1/')"
[ -n "$PARKED_COND" ] \
  && ok "extracted claim.sh parked rule: ${PARKED_COND:0:52}" \
  || bad "could not extract a parked rule from claim.sh — cannot verify drift"
awk_parked(){ awk -v p="$1" "BEGIN{ parked=p; if (${PARKED_COND:-0}) exit 0; exit 1 }"; }
for v in "operator-led deep-dive" "true" "yes" "1" "" "false" "no" "0"; do
  lib=0; is_parked_value "$v" || lib=1
  awkr=0; awk_parked "$v" || awkr=1
  if [ "$lib" -eq "$awkr" ]; then ok "lib==awk for parked='${v:-<empty>}'"
  else bad "DRIFT: _lib.sh and claim.sh disagree on parked='${v:-<empty>}' (lib=$lib awk=$awkr)"; fi
done

# ── 3. the live claim.sh really carries the fixed rule (not a stale literal test) ──────
grep -q 'parked != "" && parked != "false"' "$FLEET/claim.sh" \
  && ok "claim.sh uses the present-and-non-empty rule" \
  || bad "claim.sh reverted to a literal parked test — prose parks become claimable again"
# Strip comments first: the fix DOCUMENTS the old rule in a comment, so a naive grep would
# match the explanation and report a false RED. Only real code counts.
if grep -vE '^[[:space:]]*#' "$FLEET/claim.sh" | grep -qE 'parked == "(true|yes|1)"'; then
  bad "claim.sh CODE still literal-matches parked == true — prose parks claimable again"
else ok "claim.sh code no longer literal-matches parked == true"; fi

# claim.sh is single-quoted awk: an apostrophe in its program ends the string and breaks the
# whole script (hit for real while writing this fix). Guard it.
bash -n "$FLEET/claim.sh"  && ok "claim.sh parses"  || bad "claim.sh SYNTAX ERROR (apostrophe in the awk program?)"
bash -n "$FLEET/status.sh" && ok "status.sh parses" || bad "status.sh SYNTAX ERROR"

# ── 4. status.sh reports PARKED rather than `ready` ────────────────────────────────────
grep -q 'is_parked' "$FLEET/status.sh" \
  && ok "status.sh consults the parked predicate" \
  || bad "status.sh ignores parked: — parked tickets print as 'ready' (the display bug)"

# ── 5. EVERY parked-reading site agrees — no site keeps a private literal rule ─────────
# The bug was one rule copied into four places and fixed in none. foreman.sh decides whether a
# quarantine is a human hold; launch-plan.sh decides what is launchable. A literal test in
# either resurrects the defect on a different surface.
grep -vE '^[[:space:]]*#' "$FLEET/foreman.sh" | grep -qE 'in true\|yes\|1\)' \
  && bad "foreman.sh keeps a literal parked test — prose parks not seen as a human hold" \
  || ok "foreman.sh no longer literal-matches parked"
grep -q 'source "\$FLEET/_lib.sh"' "$FLEET/foreman.sh" \
  && ok "foreman.sh sources the canonical predicate" \
  || bad "foreman.sh does not source _lib.sh — its parked rule can drift again"

# launch-plan.sh's rule is PYTHON — exercise the real function rather than eyeballing it.
if command -v python3 >/dev/null 2>&1; then
  py_out="$(python3 - "$FLEET/launch-plan.sh" <<'PY' 2>/dev/null
import re, sys
src = open(sys.argv[1]).read()
m = re.search(r"^def is_parked\(tf\):\n(?:[ ].*\n|\n)*", src, re.M)
if not m: print("EXTRACT-FAIL"); sys.exit(0)
ns = {"field": lambda tf, k: tf.get(k, "")}
exec(m.group(0), ns)
f = ns["is_parked"]
cases = [({"parked": "operator-led DEEP-DIVE — do NOT route", "note": ""}, True),
         ({"parked": "true",  "note": ""}, True),
         ({"parked": "",      "note": ""}, False),
         ({"parked": "false", "note": ""}, False)]
print("OK" if all(f(tf) is exp for tf, exp in cases) else "MISMATCH")
PY
)"
  case "$py_out" in
    OK) ok "launch-plan.sh is_parked() agrees (prose=parked, empty=claimable)";;
    MISMATCH) bad "launch-plan.sh is_parked() disagrees with the canonical rule";;
    *) bad "could not exercise launch-plan.sh is_parked() ($py_out)";;
  esac
else ok "python3 absent — launch-plan.sh check skipped"; fi

printf '\n  parked-semantics: %s\n\n' "$([ "$fails" -eq 0 ] && echo 'GREEN' || echo "RED ($fails failed)")"
[ "$fails" -eq 0 ]
