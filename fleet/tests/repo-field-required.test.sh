#!/usr/bin/env bash
# repo-field-required.test.sh — FAIL-ON-REVERT tests for REPO-FIELD-REQUIRED.
#
# THE DEFECT (measured 2026-07-18): 120 of 226 board tickets carried NO `repo:` field.
# validate_board.sh:97-98 defaulted an absent field to "charon" (the PRODUCT repo), and done.sh
# defaulted the same way. So a rig ticket (REPO-DECL-CENTRAL) was merge-proven by a PRODUCT-side
# commit that does not exist in the rig repo at all, counted done, and its worktree became
# eligible for DESTRUCTIVE removal — verify_merged GATES worktree deletion. A wrong-repo default
# is a data-loss-adjacent defect, not a cosmetic one.
#
# THE RULES (this ticket):
#   (a)  `repo:` is MANDATORY + KNOWN on every live ticket. Absent -> RED (today: silently
#        defaults to "charon"). Unknown -> RED (rule 0 already did present-but-unknown; now it
#        also covers ABSENT). The default-to-"charon" behaviour is REMOVED, not merely warned.
#   (a2) INCONSISTENT with owns -> RED: a PRODUCT-code owns (`src/charon/*` | `tests/*` |
#        `tools/*`) declared `repo: charon-private`, or a `fleet/*` owns declared `repo: charon`,
#        is the exact recurring mis-pointing (a session files a product fix as a rig ticket).
#   (a3) `tier:` must be in the canonical set (`charon tier ranks` SSOT — NOT hardcoded here). A
#        stray `tier: standard` slipped through silently because validate_board checked work_class
#        but NOT tier.
#
# Tests the VALIDATOR against FIXTURE boards — NEVER asserts against the live board's contents (a
# live-content assertion goes green the moment the backfill lands and proves nothing about the
# durable rule). The backfill covered ~120 board/archive files; this test guards the RULE, which
# is the half that survives after the data migration lands.
#
# TIER SSOT is `charon tier ranks`; for hermetic isolation the tests inject CHARON_TIER_RANKS_CMD
# with a stub that prints the same shape (economy<strong<frontier + aliases low/med/high,
# haiku/sonnet/opus). Reusing the canonical command shape — NOT a second hardcoded tier list — is
# the whole point of (a3); a stub that hardcodes the list would test itself, not the rule.
#
# ── FAIL-ON-REVERT (each assertion names the revert that turns it RED) ──────────────────────
#   R1 — in validate_board.sh:repo check, change `if not key:` (absent -> RED) back to the old
#        `key = ... or "charon"` default in repo_key()+repo_root() and drop the repo-missing arm.
#        RED: assertion M1 (a fixture ticket with NO repo: field stops being REJECTED) and the
#             live backfill would silently re-drift. Also the "add field -> GREEN" half (M2) flips.
#   R2 — in validate_board.sh:repo check, change the unknown-repo arm to a warning (append to
#        `warn` not `red`).                              RED: assertion U1 (unknown -> REJECTED).
#   R3 — in validate_board.sh:implied_repos_from_owns, delete the `src/`|`tests/`|`tools/`
#        PRODUCT_OWNS_PREFIXES arm so product owns no longer imply charon. RED: assertion C1
#        (repo: charon-private + owns src/charon/x.py stops being REJECTED) — the (a2) defect.
#   R4 — in validate_board.sh:tier gate, delete the 2f-per-ticket loop (or drop the import of
#        `charon tier ranks`).                          RED: assertion T1 (`tier: standard` stops
#        being REJECTED) and T2 (canonical `tier: strong` regresses). The SSOT reuse must stay.
#   R5 — revert the backfill of ANY one board file (drop its `repo:` line). The live board's
#        validate_board.sh goes RED with `repo-missing: <id>` — so the rule catches a future
#        silent re-drift. (This is enforced by the live board run in the gate, asserted at the
#        end of this file by running the REAL validator over the REAL fleet after isolation.)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }

# stub tier ranks — same shape as `charon tier ranks` (the SSOT); canonicals economy/strong/
# frontier PLUS the rank aliases low/med/high, haiku/sonnet/opus. Asserted canonical below.
TIER_STUB="$(mktemp)"
trap 'rm -f "$TIER_STUB"' EXIT
printf 'low 1\nmed 2\nhigh 3\neconomy 1\nfrontier 3\nhaiku 1\nopus 3\nsonnet 2\nstrong 2\n' > "$TIER_STUB"
STUB_CMD="cat '$TIER_STUB'"
# sanity: the stub carries every canonical a real `charon tier ranks` would (guards a stub that
# would falsely trip the validator's own canonical-presence assertion).
for c in economy strong frontier low med high haiku sonnet opus; do
  grep -qx "$c [0-9]" "$TIER_STUB" || { echo "FATAL: tier stub missing $c"; exit 2; }
done

mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/validate_board.sh" "$d/"
  cp -r "$SRC/capability" "$d/capability"   # validate_board imports capability/grades.py
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/claims" "$d/state/submitted" "$d/prompts"
  echo "$d"
}
# A valid baseline ticket (repo present + canonical tier + owns consistent). Args: dir id [repo] [tier] [owns]
mk_ticket(){
  local d="$1" id="$2" repo="${3:-charon}" tier="${4:-strong}" owns="${5:-docs/$2.md}"
  {
    echo "repo: $repo"
    echo "tier: $tier"
    echo "difficulty: 1"
    echo "work_class: docs"
    echo "branch: feat/$id"
    echo "depends_on:"
    echo "owns: $owns"
  } > "$d/board/$id.md"
}
# run validator against a fixture fleet; returns rc + sets OUT.
run_vb(){
  OUT="$(CHARON_REPO="$1" CHARON_TIER_RANKS_CMD="$STUB_CMD" bash "$1/validate_board.sh" 2>&1)"; RC=$?
}

# ════════════════════════════════════════════════════════════════════════════════════════════
# (a) MISSING repo: -> REJECTED; add the field -> GREEN.                        [RED under R1]
# ════════════════════════════════════════════════════════════════════════════════════════════
d="$(mk_fleet)"
# a ticket with NO repo: field
{
  echo "tier: strong"
  echo "difficulty: 1"
  echo "work_class: docs"
  echo "branch: feat/no-repo"
  echo "depends_on:"
  echo "owns: docs/x.md"
} > "$d/board/NO-REPO.md"
run_vb "$d"
[ "$RC" != "0" ] && ok "M1: a ticket with NO repo: field is REJECTED (non-zero, the core defect)" \
                 || bad "M1: a ticket with NO repo: field passed GREEN — the silent default is still live"
has "$OUT" "repo-missing" "M1: rejection names the rule 'repo-missing'"
has "$OUT" "NO-REPO" "M1: rejection names the offending ticket"
# add the field -> GREEN (the revert is removing the field again, which the first half catches).
{ echo "repo: charon"; echo "tier: strong"; echo "difficulty: 1"; echo "work_class: docs"
  echo "branch: feat/no-repo"; echo "depends_on:"; echo "owns: docs/x.md"; } > "$d/board/NO-REPO.md"
run_vb "$d"
[ "$RC" = "0" ] && ok "M2: adding repo: charon turns the same ticket GREEN" \
               || bad "M2: adding repo: charon did NOT turn it GREEN — { printf '%s' "$OUT"; }"
rm -rf "$d"

# ════════════════════════════════════════════════════════════════════════════════════════════
# (a) UNKNOWN repo: -> REJECTED.                                                [RED under R2]
# ════════════════════════════════════════════════════════════════════════════════════════════
d="$(mk_fleet)"
mk_ticket "$d" UNKNOWN-KEY "not-a-real-repo" strong "docs/x.md"
run_vb "$d"
[ "$RC" != "0" ] && ok "U1: repo: not-a-real-repo is REJECTED" \
                 || bad "U1: an unknown repo: value passed GREEN"
has "$OUT" "unknown-repo" "U1: rejection names the rule 'unknown-repo'"
rm -rf "$d"

# ════════════════════════════════════════════════════════════════════════════════════════════
# (a2) repo/owns INCONSISTENCY -> REJECTED; flip repo to match owns -> GREEN.  [RED under R3]
# ════════════════════════════════════════════════════════════════════════════════════════════
d="$(mk_fleet)"
# the exact mis-pointing: owns a PRODUCT source file but declares the RIG -> REJECTED.
mk_ticket "$d" MIS-POINT "charon-private" strong "src/charon/x.py"
run_vb "$d"
[ "$RC" != "0" ] && ok "C1: repo: charon-private + owns src/charon/x.py is REJECTED (the mis-pointing defect)" \
                 || bad "C1: a product-fix filed as a rig ticket passed GREEN — the (a2) defect is live"
has "$OUT" "repo-owns-inconsistent" "C1: rejection names the rule 'repo-owns-inconsistent'"
has "$OUT" "MIS-POINT" "C1: rejection names the offending ticket"
# flip repo to charon (match the product owns) -> GREEN.
mk_ticket "$d" MIS-POINT "charon" strong "src/charon/x.py"
run_vb "$d"
[ "$RC" = "0" ] && ok "C2: flipping repo: to charon (matching owns) turns it GREEN" \
               || bad "C2: flipping repo: to charon did NOT turn it GREEN — { printf '%s' "$OUT"; }"
# the reverse mis-pointing: owns a RIG file (fleet/) but declares the PRODUCT -> REJECTED.
mk_ticket "$d" REV-POINT "charon" strong "fleet/x.sh"
run_vb "$d"
[ "$RC" != "0" ] && ok "C3: repo: charon + owns fleet/x.sh is REJECTED (reverse mis-pointing)" \
                 || bad "C3: owns fleet/ + repo: charon passed GREEN"
has "$OUT" "repo-owns-inconsistent" "C3: reverse mis-pointing also names 'repo-owns-inconsistent'"
mk_ticket "$d" REV-POINT "charon-private" strong "fleet/x.sh"
run_vb "$d"
[ "$RC" = "0" ] && ok "C4: flipping repo: to charon-private (matching owns fleet/) turns it GREEN" \
               || bad "C4: fleet/ owns + charon-private did NOT turn GREEN — { printf '%s' "$OUT"; }"
# ambiguous owns (docs/, a bare filename) must NOT trip the rule — a ticket may legitimately keep
# bare relative owns under its declared repo root (BENCH-OOB-GRADING's `benchmark/` is rig-intended).
mk_ticket "$d" AMBIG "charon-private" strong "benchmark/graders/keys.json"
run_vb "$d"
[ "$RC" = "0" ] && ok "C5: ambiguous owns (benchmark/) + repo: charon-private stays GREEN (no false positive)" \
               || bad "C5: ambiguous owns falsely tripped the consistency rule — { printf '%s' "$OUT"; }"
rm -rf "$d"

# ════════════════════════════════════════════════════════════════════════════════════════════
# (a3) tier validation: stray tier REJECTED; canonical tier GREEN.             [RED under R4]
# ════════════════════════════════════════════════════════════════════════════════════════════
d="$(mk_fleet)"
mk_ticket "$d" STRAY-TIER "charon" standard "docs/x.md"
run_vb "$d"
[ "$RC" != "0" ] && ok "T1: tier: standard is REJECTED (the stray that slipped through silently)" \
                 || bad "T1: a non-canonical tier passed GREEN — the (a3) defect is live"
has "$OUT" "tier-invalid" "T1: rejection names the rule 'tier-invalid'"
has "$OUT" "STRAY-TIER" "T1: rejection names the offending ticket"
# flip to a canonical tier -> GREEN.
mk_ticket "$d" STRAY-TIER "charon" strong "docs/x.md"
run_vb "$d"
[ "$RC" = "0" ] && ok "T2: flipping tier: to strong turns it GREEN" \
               || bad "T2: canonical tier: strong did NOT turn GREEN — { printf '%s' "$OUT"; }"
# a rank alias (sonnet) is also accepted (the SSOT's canonical+alias shape).
mk_ticket "$d" ALIAS-TIER "charon" sonnet "docs/alias.md"
run_vb "$d"
[ "$RC" = "0" ] && ok "T3: tier: sonnet (a rank alias) is GREEN — the SSOT alias shape is honoured" \
               || bad "T3: rank alias sonnet erroneously REJECTED — { printf '%s' "$OUT"; }"
# MISSING tier -> REJECTED (required, same discipline as work_class/difficulty).
{ echo "repo: charon"; echo "difficulty: 1"; echo "work_class: docs"; echo "branch: feat/no-tier"
  echo "depends_on:"; echo "owns: docs/x.md"; } > "$d/board/NO-TIER.md"
run_vb "$d"
[ "$RC" != "0" ] && ok "T4: a ticket with NO tier: field is REJECTED" \
                 || bad "T4: a missing tier: field passed GREEN — tier is not required"
has "$OUT" "tier-missing" "T4: rejection names the rule 'tier-missing'"
rm -rf "$d"

# ════════════════════════════════════════════════════════════════════════════════════════════
# (b) the SSOT reuse is the point — the validator MUST consult `charon tier ranks` (via
# CHARON_TIER_RANKS_CMD) and NOT hardcode a second tier list. A stub that carries the canonicals
# PLUS an EXTRA tier 'gamma' must be HONOURED: 'gamma' (not in any hardcoded list) is GREEN here,
# proving the runtime set comes from the command. A stub missing a load-bearing canonical FAILS.
# ════════════════════════════════════════════════════════════════════════════════════════════
d="$(mk_fleet)"
SUPSET_STUB="$(mktemp)"
# canonicals (so the canonical-presence guard passes) + an EXTRA tier 'gamma' a hardcoded list
# would never carry. If the validator consults this stub -> 'gamma' is GREEN; if it hardcodes ->
# 'gamma' is REJECTED. The cheaper direction first: 'gamma' not in the hardcoded real ranks.
printf 'low 1\nmed 2\nhigh 3\neconomy 1\nfrontier 3\nhaiku 1\nopus 3\nsonnet 2\nstrong 2\ngamma 5\n' > "$SUPSET_STUB"
mk_ticket "$d" SSOT-EXTRA "charon" gamma "docs/gamma.md"
OUT2="$(CHARON_REPO="$d" CHARON_TIER_RANKS_CMD="cat '$SUPSET_STUB'" bash "$d/validate_board.sh" 2>&1)"; RC2=$?
[ "$RC2" = "0" ] && ok "S1: stub-only tier 'gamma' is GREEN — the set is read from the command, not hardcoded" \
                 || bad "S1: 'gamma' rejected despite being in the stubbed SSOT — the list is hardcoded (and a junk stub only is not production data)"
rm -f "$SUPSET_STUB"
# and the validator refuses a stub that is missing a load-bearing canonical (economy/strong/frontier).
BAD_STUB="$(mktemp)"
printf 'only-thing 1\n' > "$BAD_STUB"
mk_ticket "$d" SSOT-OK "charon" strong "docs/ok.md"
OUT4="$(CHARON_REPO="$d" CHARON_TIER_RANKS_CMD="cat '$BAD_STUB'" bash "$d/validate_board.sh" 2>&1)"; RC4=$?
[ "$RC4" != "0" ] && ok "S2: a stub missing canonical economy/strong/frontier FAILS the validator (no silent pass)" \
                 || bad "S2: a junk stub passed — the canonical-presence guard is gone"
has "$OUT4" "tier-check-failed" "S2: the failure names 'tier-check-failed'"
rm -f "$BAD_STUB"
rm -rf "$d"

# ════════════════════════════════════════════════════════════════════════════════════════════
# (R5) the LIVE board is GREEN after the backfill — the rule catches a future silent re-drift.
# Runs the REAL validator over the REAL fleet (with the REAL `charon tier ranks`). This is the
# only assertion that touches the live board; it guards the backfill (half (b)), not the rule.
# ════════════════════════════════════════════════════════════════════════════════════════════
OUT_LIVE="$(bash "$SRC/validate_board.sh" 2>&1)"; RC_LIVE=$?
[ "$RC_LIVE" = "0" ] && ok "L1: the live board (rules + backfill landed together) is GREEN" \
                    || bad "L1: the live board is RED after the backfill — { printf '%s' "$OUT_LIVE" | grep RED | head; }"
# every live board ticket carries an explicit repo: (revert any backfill line -> this goes RED).
_n_lacking_board=0
for _f in "$SRC"/board/*.md; do grep -q '^repo:' "$_f" || _n_lacking_board=$((_n_lacking_board+1)); done
[ "$_n_lacking_board" = "0" ] && ok "L2: every live board/*.md ticket carries an explicit repo: field" \
                            || bad "L2: $_n_lacking_board live board/*.md ticket(s) missing repo: — backfill incomplete"
# every archived ticket too: verify_merged reads archived tickets when resolving done markers, so a
# repo-less archive ticket re-opens the original wrong-repo-default defect on retirement.
_n_lacking_arch=0
for _f in "$SRC"/board/archive/*.md; do grep -q '^repo:' "$_f" || _n_lacking_arch=$((_n_lacking_arch+1)); done
[ "$_n_lacking_arch" = "0" ] && ok "L3: every archived board ticket carries an explicit repo: field" \
                            || bad "L3: $_n_lacking_arch archived ticket(s) missing repo: — verify_merged would re-default it"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL REPO-FIELD-REQUIRED TESTS PASS"