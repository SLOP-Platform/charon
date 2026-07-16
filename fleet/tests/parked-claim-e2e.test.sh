#!/usr/bin/env bash
# parked-claim-e2e.test.sh — DOGFOOD E2E for the PARKED gate.
#
# parked-semantics.test.sh proves the RULE is right in each implementation. This proves the
# rule actually BITES: it runs the REAL claim.sh, as a real droid, against a real board, and
# asserts a prose-parked ticket is never handed out while a ready sibling still is.
#
# Green unit tests were never the gap — the rule was locally "correct" in four places and the
# system still offered an operator-held ticket. Only an end-to-end claim can show that.
#
# Fully isolated: builds a temp fleet (copied claim.sh/_lib.sh + synthetic board + empty state).
# NEVER touches the live board, the live state, or the product repo.
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
ok(){ printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
F="$WORK/fleet"; mkdir -p "$F/board" "$F/state"
cp "$SRC/claim.sh" "$SRC/_lib.sh" "$F/"

mk(){ # mk <id> <tier> <extra-yaml>
  { printf 'tier: %s\nbranch: feat/%s\ndepends_on:\n' "$2" "$(echo "$1" | tr 'A-Z' 'a-z')"
    [ -n "${3:-}" ] && printf '%s\n' "$3"
    printf 'owns: src/%s.py\naccept: |\n  synthetic e2e fixture\n' "$1"; } > "$F/board/$1.md"
}

# The exact shape that defeated the old rule: a park reason written as PROSE.
mk E2E-PROSE-PARKED strong 'parked: operator-led DEEP-DIVE next session — the operator will personally investigate/design this before it is built. Do NOT route to an SG droid.'
mk E2E-BARE-PARKED  strong 'parked: true'
mk E2E-EMPTY-PARKED strong 'parked:'
mk E2E-READY        strong ''

claim(){ ( cd "$F" && bash ./claim.sh "$1" "$2" both 2>/dev/null ); }

# DRAIN the board: keep claiming as distinct droids until claim.sh says NONE, and record every
# id it ever handed out. Asserting the SET (not an order) — claim order follows the board glob,
# which is alphabetical and not part of claim.sh's contract; an order-coupled test would just be
# testing the fixture names.
handed=""; guard=0
while [ "$guard" -lt 10 ]; do
  guard=$((guard+1))
  out="$(claim strong "e2e-droid-$guard")"
  case "$out" in
    CLAIMED\ *) handed="$handed $(awk '{print $2}' <<<"$out")";;
    *) break;;
  esac
done
handed="${handed# }"

# ── 1. neither real park is EVER handed out, however many droids ask ───────────────────
case " $handed " in
  *" E2E-PROSE-PARKED "*) bad "E2E: claim.sh handed out the PROSE-parked ticket — operator directive ignored";;
  *) ok "E2E: PROSE-parked ticket never claimed (handed: ${handed:-<none>})";;
esac
case " $handed " in
  *" E2E-BARE-PARKED "*) bad "E2E: claim.sh handed out the bare 'parked: true' ticket";;
  *) ok "E2E: bare parked:true ticket never claimed";;
esac

# ── 2. the board is not starved: every genuinely claimable ticket IS handed out ────────
# The over-correction guard — treating `parked:` with an EMPTY value as parked would strand
# real work (MEMORY-INDEX-COMPACTION ships exactly that shape).
case " $handed " in
  *" E2E-READY "*) ok "E2E: READY ticket claimed";;
  *) bad "E2E: READY ticket never handed out — the gate over-blocks (handed: ${handed:-<none>})";;
esac
case " $handed " in
  *" E2E-EMPTY-PARKED "*) ok "E2E: empty parked: value is still claimable";;
  *) bad "E2E: empty parked: treated as PARKED — over-correction strands real tickets";;
esac

# ── 3. the drain terminates at NONE rather than falling back to parked work ────────────
n=$(wc -w <<<"$handed")
[ "$n" -eq 2 ] \
  && ok "E2E: board drained to NONE after exactly the 2 claimable tickets" \
  || bad "E2E: expected exactly 2 claimable tickets, got $n ($handed)"

printf '\n  parked-claim-e2e: %s\n\n' "$([ "$fails" -eq 0 ] && echo 'GREEN' || echo "RED ($fails failed)")"
[ "$fails" -eq 0 ]
