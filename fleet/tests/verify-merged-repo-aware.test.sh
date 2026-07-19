#!/usr/bin/env bash
# verify-merged-repo-aware.test.sh — FAIL-ON-REVERT tests for TICKET-AWARE merge verification.
#
# THE BUG (2026-07-18): _lib.sh's _vm_repo()/_vm_slug() were ticket-INDEPENDENT — they always
# returned the PRODUCT repo (/home/stack/code/charon, SLOP-Platform/charon). verify_merged() is
# the ONE proof that gates every DESTRUCTIVE rig action (needs-push guard delete, worktree remove,
# retire-off-board, G2 auto-close), and the board carries ~71 tickets marked `repo: charon-private`.
# So every RIG ticket was being proven against the PRODUCT repo. Two live failures:
#   (a) FALSE NEGATIVE — SALVAGE-STASH-CHARON-RUN carries `merged:#83` (RIG PR 83, merged). Checked
#       against SLOP-Platform/charon it can never verify, so the ticket can never retire.
#   (b) FALSE POSITIVE (the sharp edge) — REPO-DECL-CENTRAL's marker carries
#       merged:c44e7bda0ee835afa01c7a9e876e5df3e2a7162d. That object does not exist in the rig repo
#       at ALL, but it IS an ancestor of PRODUCT origin/master (a product-side commit that only added
#       docs/review-log/REPO-DECL-CENTRAL.md). A rig ticket was "merge-proven" by a product commit.
#
# THE RULE (canonical: _vm_resolve() in _lib.sh): the ticket's `repo:` field selects the repo+slug.
#   repo: charon | product          -> PRODUCT_REPO / PRODUCT_SLUG
#   repo: charon-private|fleet|rig  -> FLEET_REPO   / FLEET_SLUG
#   repo: <anything else>           -> FAIL CLOSED (verify_merged returns 1; NEVER falls back)
#   no `repo:` field                -> PRODUCT (deliberate back-compat with pre-fix behaviour)
#
# Exercises the REAL verify_merged from _lib.sh (sourced), never a transcription.
# Offline: a throwaway "product" git repo + the REAL rig repo's own history. No network, no gh.
#
# ── FAIL-ON-REVERT (each assertion below names the exact revert that turns it RED) ──────────
#   R1 — in _lib.sh:_vm_resolve, change the `charon-private|fleet|rig)` arm to print
#        "$PRODUCT_REPO"/"$PRODUCT_SLUG" (i.e. restore the ticket-independent behaviour).
#        RED: assertions 1 (rig sha no longer found in the temp product repo) AND
#             2 (product-only sha wrongly verifies for a rig ticket — bug (b) itself).
#   R2 — in _lib.sh:_vm_resolve, change the `*) return 1 ;;` arm to print "$PRODUCT_REPO"/"$PRODUCT_SLUG"
#        (and drop the `_vm_resolve "$id" >/dev/null || return 1` fail-closed line in verify_merged).
#        RED: assertion 4 (repo: bogus wrongly verifies against the product repo).
#   R3 — in _lib.sh:_vm_resolve, change the `""|charon|product)` arm to print "$FLEET_REPO".
#        RED: assertion 3 (an ordinary product ticket stops verifying — guards against over-fixing).
set -uo pipefail
FLEET_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
ok(){ printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
mkdir -p "$D/board/archive" "$D/state/done"

# ── a throwaway PRODUCT repo (its sha exists ONLY here) ─────────────────────────────────────
P="$D/product"; mkdir -p "$P"
git -C "$P" init -q -b master
git -C "$P" config user.email t@t; git -C "$P" config user.name t
: > "$P/f"; git -C "$P" add f; git -C "$P" commit -qm p1
git -C "$P" update-ref refs/remotes/origin/master master
PROD_SHA="$(git -C "$P" rev-parse HEAD)"

# ── the REAL rig repo + a REAL sha from its origin/master history (not a synthetic fixture) ──
RIG="$(git -C "$FLEET_SRC" rev-parse --show-toplevel)"
RIG_SHA="$(git -C "$RIG" rev-parse origin/master^ 2>/dev/null || git -C "$RIG" rev-parse origin/master)"
[ -n "$RIG_SHA" ] && ok "picked a real rig-history sha (${RIG_SHA:0:8}) from $RIG origin/master" \
                  || bad "could not read a sha from the rig repo — the positive case cannot be proven"
# sanity: the two repos really are disjoint, else the negative case would be vacuous.
git -C "$RIG" cat-file -e "$PROD_SHA" 2>/dev/null \
  && bad "product sha unexpectedly exists in the rig repo — negative case is vacuous" \
  || ok "product-only sha is genuinely absent from the rig repo"

mkt(){ # mkt <id> <repo-field-line> <marker-sha>
  { [ -n "$2" ] && printf '%s\n' "$2"; printf 'branch: n/a\nowns:\n'; } > "$D/board/$1.md"
  printf '%s\tmerged:%s\tbranch:n/a\n' "2026-07-18T00:00:00Z" "$3" > "$D/state/done/$1"
}
mkt RIG-OK      "repo: charon-private" "$RIG_SHA"
mkt RIG-BAD     "repo: charon-private" "$PROD_SHA"
mkt PROD-OK     "repo: charon"         "$PROD_SHA"
mkt BOGUS       "repo: bogus"          "$PROD_SHA"
mkt NO-REPO     ""                     "$PROD_SHA"

# source the REAL library against the fixture board/state; VERIFY_MERGED_REPO points the PRODUCT
# side at the throwaway repo, CHARON_FLEET_REPO points the FLEET side at the real rig repo.
export VERIFY_MERGED_REPO="$P" CHARON_FLEET_REPO="$RIG"
unset VERIFY_MERGED_FIXTURE 2>/dev/null || true
FLEET="$D"
# shellcheck source=/dev/null
source "$FLEET_SRC/_lib.sh"

# 1. POSITIVE — rig ticket, sha really in RIG origin/master -> verified.        [RED under R1]
verify_merged RIG-OK && ok "repo: charon-private + real rig sha VERIFIES" \
                     || bad "rig ticket with a genuine rig-master sha did NOT verify (bug (a))"
# 2. NEGATIVE — rig ticket whose sha exists ONLY in the product repo -> NOT verified. This is
#    REPO-DECL-CENTRAL's live false positive.                                    [RED under R1]
verify_merged RIG-BAD && bad "rig ticket 'proven' by a PRODUCT-only sha (bug (b) — gates destructive actions)" \
                      || ok "repo: charon-private + product-only sha correctly NOT verified"
# 3. product tickets still resolve to the product repo.                          [RED under R3]
verify_merged PROD-OK && ok "repo: charon still verifies against the product repo" \
                      || bad "product ticket stopped verifying — the fix over-reached"
# 4. FAIL CLOSED on an unmappable repo value.                                    [RED under R2]
verify_merged BOGUS && bad "repo: bogus verified — unknown repo fell back to the product repo" \
                    || ok "repo: bogus FAILS CLOSED (not verified)"
# 5. back-compat: no `repo:` field keeps the pre-fix product default.
verify_merged NO-REPO && ok "ticket with no repo: field keeps the product default (back-compat)" \
                      || bad "no-repo ticket changed behaviour — back-compat broken"

# 6. the map has exactly ONE home: done.sh must NOT carry its own repo->slug case.
grep -vE '^[[:space:]]*#' "$FLEET_SRC/done.sh" | grep -qE 'charon-private\)[[:space:]]*REPO_SLUG=' \
  && bad "done.sh re-implements the repo->slug map — the drift class this fix removed" \
  || ok "done.sh consumes the _lib.sh map (no second copy)"
grep -q 'ticket_repo_slug' "$FLEET_SRC/done.sh" \
  && ok "done.sh calls ticket_repo_slug" || bad "done.sh does not consume ticket_repo_slug"

# 7. REPO-DECL-CENTRAL's canonical declarations really exist here (they never landed before).
for v in PRODUCT_REPO FLEET_REPO PRODUCT_SLUG FLEET_SLUG; do
  [ -n "${!v:-}" ] && ok "canonical $v declared in _lib.sh (= ${!v})" || bad "$v missing from _lib.sh"
done

# ════════════════════════════════════════════════════════════════════════════════════════════
# PRE-LAND ADVERSARIAL-REVIEW FIXES (2026-07-18). Each block names the EXACT revert that turns
# it RED; every revert below was RUN and observed RED before this file was committed.
# ════════════════════════════════════════════════════════════════════════════════════════════

# ── H3: the parser must be no STRICTER than validate_board.sh's field() ─────────────────────
# _vm_meta used `awk -F': '` (a literal ": " is REQUIRED). validate_board.sh:field() uses
# line.startswith(key+":"). So `repo:charon-private` (no space) is a VALID RIG ticket to the board
# validator but read as "" here -> PRODUCT default -> a product-only sha VERIFIES a rig ticket.
# Board GREEN, destructive gate reading the wrong repo.
#   REVERT (RED): in _lib.sh restore
#     _vm_meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2" 2>/dev/null; }
mkt RIG-NOSPACE "repo:charon-private" "$PROD_SHA"
verify_merged RIG-NOSPACE \
  && bad "H3: 'repo:charon-private' (no space) verified a PRODUCT-only sha — parser stricter than the board validator" \
  || ok  "H3: 'repo:charon-private' (no space) routes to the RIG repo (product-only sha NOT verified)"
# and the same line must POSITIVELY verify a genuine rig sha (it routes to the rig, not merely fails)
mkt RIG-NOSPACE-OK "repo:charon-private" "$RIG_SHA"
verify_merged RIG-NOSPACE-OK && ok "H3: 'repo:charon-private' + a real rig sha VERIFIES (routed, not just failing)" \
                             || bad "H3: no-space repo line did not resolve to the rig repo at all"
# tolerances that ALREADY worked must not regress: CRLF, trailing whitespace, mixed case.
{ printf 'repo: charon-private\r\nbranch: n/a\r\nowns:\r\n'; } > "$D/board/RIG-CRLF.md"
printf '%s\tmerged:%s\tbranch:n/a\n' "2026-07-18T00:00:00Z" "$RIG_SHA" > "$D/state/done/RIG-CRLF"
verify_merged RIG-CRLF && ok "H3: CRLF board file still resolves to the rig repo" \
                       || bad "H3: CRLF handling REGRESSED"
mkt RIG-TRAIL "repo: charon-private   " "$RIG_SHA"
verify_merged RIG-TRAIL && ok "H3: trailing whitespace still resolves to the rig repo" \
                        || bad "H3: trailing-whitespace handling REGRESSED"
mkt RIG-CASE  "repo: Charon-Private"   "$RIG_SHA"
verify_merged RIG-CASE && ok "H3: mixed-case repo value still resolves to the rig repo" \
                       || bad "H3: mixed-case handling REGRESSED"
# _vm_meta is shared with `branch`/`owns`/`base`/`depends_on` — loosening it must not break them.
printf 'branch: has: colon\nowns: a.py, b.py\n' > "$D/board/META.md"
[ "$(_vm_meta branch "$D/board/META.md")" = "has: colon" ] \
  && ok "H3: a value containing a colon is preserved (only the first '<key>:' is consumed)" \
  || bad "H3: colon-bearing value mangled — _vm_meta's other callers (branch/owns/base) broken"
[ "$(_vm_meta owns "$D/board/META.md")" = "a.py, b.py" ] \
  && ok "H3: owns: still parses unchanged" || bad "H3: owns: parse broken"

# ── M4: a marker with NO board file at all must NOT verify ──────────────────────────────────
# An orphan state/done/<id> (no board/<id>.md, no board/archive/<id>.md) yielded an empty repo
# field, indistinguishable from "board file present, no repo: field" -> PRODUCT default -> rc 0 on
# a product-only sha. FAIL-OPEN on the input most likely to be a lie.
#   REVERT (RED): in _lib.sh:_vm_ticket_repo_field change `[ -f "$b" ] || return 1` -> `|| return 0`.
printf '%s\tmerged:%s\tbranch:n/a\n' "2026-07-18T00:00:00Z" "$PROD_SHA" > "$D/state/done/ORPHAN"
verify_merged ORPHAN && bad "M4: a marker with NO board file verified against the product repo (fail-OPEN)" \
                     || ok  "M4: a marker with NO board file does NOT verify (fail closed)"
# the ADJACENT case must be untouched: a board file that EXISTS but declares no repo: keeps the
# deliberate product default (assertion 5 above covers NO-REPO) — these two must not be collapsed.

# ── H1: the repo key map has ONE home (fleet/repo-registry.sh) ──────────────────────────────
# _vm_resolve carried its own `case`, a FOURTH copy of a map with an existing SSOT, and had already
# DIVERGED: it omitted keystone|ksf, so a `repo: keystone` ticket returned rc 1 unconditionally ->
# held forever by retire-done.sh + an unclosable done-unmerged-* red in preflight.sh.
#   REVERT (RED): in _lib.sh:_vm_resolve delete the trailing `_vm_registry_path "$r"` delegation
#   and restore `*) return 1 ;;` as a case arm.
ticket_repo_path >/dev/null 2>&1   # no-arg form still works (base-integrity.sh:63 relies on it)
mkt KS-T "repo: keystone" "$PROD_SHA"
KS_PATH="$(ticket_repo_path KS-T 2>/dev/null || true)"
[ -n "$KS_PATH" ] && ok "H1: 'repo: keystone' RESOLVES via repo-registry.sh (= $KS_PATH), not an unconditional rc 1" \
                  || bad "H1: 'repo: keystone' is still unresolvable — a keystone ticket can never retire"
# it must resolve to what the SSOT says, not to a private re-listing here.
( . "$FLEET_SRC/repo-registry.sh"; repo_resolve keystone "" >/dev/null && printf '%s' "$RR_PATH" ) \
  | grep -qx -- "$KS_PATH" \
  && ok "H1: the resolved keystone path comes from repo_resolve (single map, no local copy)" \
  || bad "H1: _vm_resolve's keystone path DIVERGES from repo-registry.sh — the map is copied again"
# every key repo_known_keys advertises must resolve (that is what "one map" means).
for k in $( . "$FLEET_SRC/repo-registry.sh"; repo_known_keys ); do
  printf 'repo: %s\nbranch: n/a\nowns:\n' "$k" > "$D/board/KEY-T.md"
  ticket_repo_path KEY-T >/dev/null 2>&1 && ok "H1: advertised key '$k' resolves" \
                                         || bad "H1: repo_known_keys advertises '$k' but _vm_resolve cannot resolve it"
done
rm -f "$D/board/KEY-T.md"
# UNKNOWN still FAILS CLOSED (assertion 4 covers verify_merged; this covers the resolver itself).
mkt UNKNOWN-KEY "repo: not-a-repo" "$PROD_SHA"
ticket_repo_path UNKNOWN-KEY >/dev/null 2>&1 \
  && bad "H1: an unknown repo key RESOLVED — delegation widened the map instead of narrowing it" \
  || ok  "H1: an unknown repo key still FAILS CLOSED in the resolver"
verify_merged UNKNOWN-KEY && bad "H1: unknown repo key verified a product sha" \
                          || ok  "H1: unknown repo key does not verify"

# ── H2: the marker WRITER (done.sh) must prove against the TICKET'S repo ────────────────────
# done.sh:sha_in_master was `git -C "$CHARON_REPO"` (hardcoded PRODUCT) while REPO_SLUG beside it
# was already ticket-aware. For a RIG ticket that made a PRODUCT sha ACCEPTED — printing "verified
# ... ancestor of Nnyan/charon-private origin/master" while having read SLOP-Platform/charon. This
# is how REPO-DECL-CENTRAL's phantom c44e7bda marker was WRITTEN.
#   REVERT (RED): in done.sh restore
#     sha_in_master(){ git -C "$CHARON_REPO" merge-base --is-ancestor "$1" origin/master 2>/dev/null; }
h2dir(){ local d; d="$(mktemp -d)"
  cp "$FLEET_SRC/done.sh" "$FLEET_SRC/retire-done.sh" "$FLEET_SRC/leak-guard.sh" \
     "$FLEET_SRC/_lib.sh" "$FLEET_SRC/verify-merged.sh" "$FLEET_SRC/repo-registry.sh" "$d/" 2>/dev/null
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/submitted" "$d/state/claims" "$d/state/needs-push"
  printf 'repo: charon-private\ntier: economy\nbranch: n/a\nowns:\n' > "$d/board/RIG-W.md"
  printf 'tier: economy\nbranch: n/a\nowns:\n'                       > "$d/board/PROD-W.md"
  echo "$d"; }
# H2a: a RIG ticket + a PRODUCT-only sha -> REFUSED, and NO marker written (the phantom-marker regression).
d="$(h2dir)"; rc=0
out="$(DONE_CHARON_REPO="$P" CHARON_FLEET_REPO="$RIG" bash "$d/done.sh" RIG-W --merged-sha "$PROD_SHA" 2>&1)" || rc=$?
[ "$rc" = "3" ] && ok "H2: rig ticket + PRODUCT-only sha is REFUSED (exit 3)" \
                || bad "H2: rig ticket + PRODUCT-only sha exited $rc (expected 3) — phantom marker path OPEN"
[ -e "$d/state/done/RIG-W" ] && bad "H2: a phantom marker was WRITTEN for a rig ticket from a product sha" \
                             || ok  "H2: no marker written for the refused rig/product-sha close"
printf '%s' "$out" | grep -q 'charon-private' \
  && ok "H2: the refusal names the rig repo it actually checked" \
  || bad "H2: refusal message does not name the repo actually checked"
rm -rf "$d"
# H2b: a RIG ticket + a GENUINE rig sha -> ACCEPTED and the marker carries that sha.
d="$(h2dir)"; rc=0
out="$(DONE_CHARON_REPO="$P" CHARON_FLEET_REPO="$RIG" bash "$d/done.sh" RIG-W --merged-sha "$RIG_SHA" 2>&1)" || rc=$?
[ "$rc" = "0" ] && ok "H2: rig ticket + GENUINE rig sha is ACCEPTED (exit 0)" \
                || bad "H2: rig ticket + genuine rig sha exited $rc (expected 0) — the false NEGATIVE, bug (a)"
grep -q "merged:$RIG_SHA" "$d/state/done/RIG-W" 2>/dev/null \
  && ok "H2: the marker carries the genuine rig sha" || bad "H2: marker missing merged:<rig sha>"
rm -rf "$d"
# H2c: a PRODUCT ticket still closes on a product sha — DONE_CHARON_REPO override preserved.
d="$(h2dir)"; rc=0
DONE_CHARON_REPO="$P" bash "$d/done.sh" PROD-W --merged-sha "$PROD_SHA" >/dev/null 2>&1 || rc=$?
[ "$rc" = "0" ] && ok "H2: product ticket still closes via the DONE_CHARON_REPO override (back-compat)" \
                || bad "H2: DONE_CHARON_REPO override broken (exit $rc) — the fix over-reached"
rm -rf "$d"

printf -- '--- %s failed ---\n' "$fails"
[ "$fails" -eq 0 ]
