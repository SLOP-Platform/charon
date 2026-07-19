#!/usr/bin/env bash
# droid-identity.test.sh — FAIL-ON-REVERT tests for COMMIT-ACTOR-STAMP (FIX 4).
#
# THE BUG (2026-07-18): every rig commit was `sim <sim@sim>`, so a droid commit and a manager
# sub-agent commit are INDISTINGUISHABLE in git history. Forensics on a wrong-commit merge needed
# a log-file archaeology dig that a committer name would have answered in 30 seconds.
#
# NON-FIXTURE: sources the REAL fleet/droid-identity.sh and makes a REAL commit in a REAL temp
# repo (whose local user.name/user.email are deliberately set to the old `sim <sim@sim>`), then
# reads the attribution back out of git itself — no transcription of the export lines.
#
# ── FAIL-ON-REVERT ──────────────────────────────────────────────────────────────────────────
#   U1 — droid-identity.sh: drop the `export GIT_COMMITTER_NAME`/`GIT_COMMITTER_EMAIL` lines.
#        RED: assertion 1 (%cn falls back to the repo's `sim`).
#   U2 — droid-identity.sh: drop the `export GIT_AUTHOR_NAME`/`GIT_AUTHOR_EMAIL` lines.
#        RED: assertion 2.
#   U3 — fleet-droid.sh: delete the `droid_git_identity "$DROID"` call after DROID= is set.
#        RED: assertion 4 (the launcher no longer stamps its session).
#   U4 — droid-identity.sh: in droid_identity_for_repo, replace the whole body with
#        `droid_git_identity "$2"` (i.e. stamp the droid id for every repo, the pre-MED-3
#        behaviour).                                    RED: assertions 5, 6, 9.
#        (NOT 8 — assertion 8 WANTS the droid id for the rig, so it stays green under U4. That is
#        the point: U4 is caught by the public-repo assertions, not by the rig one.)
#   U5 — fleet-droid.sh: delete the per-ticket `droid_identity_for_repo "$RR_KEY" "$DROID"` line
#        that follows the `repo=$RR_KEY` echo.          RED: assertion 9.
set -uo pipefail
FLEET_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
ok(){ printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
R="$D/repo"; git init -q -b master "$R"
git -C "$R" config user.name sim; git -C "$R" config user.email sim@sim   # the OLD indistinguishable identity

# shellcheck source=/dev/null
source "$FLEET_SRC/droid-identity.sh"
droid_git_identity "frontier-25379" >/dev/null

echo x > "$R/f"; git -C "$R" add f; git -C "$R" commit -qm stamped

cn="$(git -C "$R" log -1 --format=%cn)"; ce="$(git -C "$R" log -1 --format=%ce)"
an="$(git -C "$R" log -1 --format=%an)"

[ "$cn" = "frontier-25379" ] \
  && ok "1 committer name is the droid id (was 'sim')" \
  || bad "1 committer name is '$cn', want 'frontier-25379'"
[ "$an" = "frontier-25379" ] \
  && ok "2 author name is the droid id" \
  || bad "2 author name is '$an', want 'frontier-25379'"
# A REAL git identity, not a marker string: git parsed it into a normal name/email pair, so every
# existing `git log --format=…` / mailmap consumer keeps working.
case "$ce" in
  frontier-25379@*) ok "3 the identity is a real name<email> pair git parsed normally ($ce)" ;;
  *)                bad "3 committer email is '$ce' — not a valid stamped address" ;;
esac

# ── 4. the LAUNCHER actually calls it (a library nobody wires up stamps nothing) ─────────────
# fleet-droid.sh itself is NOT invoked here — running it claims real tickets and launches real
# model sessions. Instead: assert the wiring exists in the launcher AND execute those exact two
# lines standalone, so the assertion covers behaviour, not just the presence of text.
if grep -q 'droid_git_identity "\$DROID"' "$FLEET_SRC/fleet-droid.sh" \
   && grep -q 'source "\$FLEET/droid-identity.sh"' "$FLEET_SRC/fleet-droid.sh"; then
  # confirm the wiring is EXECUTABLE, not just present: run the same two lines standalone.
  got="$(bash -c 'FLEET="'"$FLEET_SRC"'"; DROID="strong-999"; source "$FLEET/droid-identity.sh"; droid_git_identity "$DROID" >/dev/null; printf "%s" "$GIT_COMMITTER_NAME"')"
  [ "$got" = "strong-999" ] \
    && ok "4 fleet-droid.sh wires the stamp into its session (DROID id exported as committer)" \
    || bad "4 the launcher's wiring does not export the droid id (got '$got')"
else
  bad "4 fleet-droid.sh does not source/call droid_git_identity — droid commits stay unattributable"
fi


# ══════════════════════════════════════════════════════════════════════════════════════════════
# MED-3 — the PUBLIC product repo must not carry rig taxonomy. fleet-droid.sh exports the droid
# identity process-tree-wide and routes `repo: charon` tickets into the PUBLIC product checkout,
# so product commits would have read `frontier-25379 <frontier-25379@fleet.local>` — an internal
# tier name plus a PID, published. NON-FIXTURE: real repos, real commits, attribution read back
# out of git.
# ══════════════════════════════════════════════════════════════════════════════════════════════
# shellcheck source=/dev/null
source "$FLEET_SRC/repo-registry.sh"

commit_as(){   # <repo-key> <droid-id> <repo-dir> -> echoes "<committer name>|<committer email>"
  local key="$1" did="$2" r="$3"
  ( git init -q -b master "$r"
    git -C "$r" config user.name sim; git -C "$r" config user.email sim@sim
    droid_identity_for_repo "$key" "$did" >/dev/null
    echo x > "$r/f"; git -C "$r" add f; git -C "$r" commit -qm stamped
    printf '%s|%s' "$(git -C "$r" log -1 --format=%cn)" "$(git -C "$r" log -1 --format=%ce)" )
}

# ── 5/6. a PRODUCT (public) commit carries NO droid id, NO pid, NO rig domain.
prod="$(commit_as charon "frontier-25379" "$D/prod")"
prod_n="${prod%%|*}"; prod_e="${prod#*|}"
case "$prod_n$prod_e" in
  *frontier*|*25379*) bad "5 PUBLIC product commit leaks the droid id: $prod_n <$prod_e>" ;;
  *)                  ok  "5 a PUBLIC product commit carries NO droid id/pid ($prod_n <$prod_e>)" ;;
esac
case "$prod_e" in
  *fleet.local*) bad "6 PUBLIC product commit leaks the rig domain fleet.local: $prod_e" ;;
  *)             ok  "6 a PUBLIC product commit carries no rig domain ($prod_e)" ;;
esac

# ── 7. it is still a SYNTACTICALLY VALID git identity (the sanitizer contract at line ~23 holds):
# git parsed it into a normal name/email pair, so mailmap and every --format consumer keep working.
if [ -n "$prod_n" ] && printf '%s' "$prod_e" | grep -Eq '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'; then
  ok "7 the neutral product identity is still a valid name<email> pair ($prod_n <$prod_e>)"
else
  bad "7 neutral identity is not a valid address: '$prod_n' <'$prod_e'>"
fi

# ── 8. the RIG keeps its droid-id attribution — that is the whole point of the stamp (forensics).
rig="$(commit_as charon-private "frontier-25379" "$D/rig")"
[ "${rig%%|*}" = "frontier-25379" ]   && ok "8 a RIG commit DOES carry the droid id (attribution preserved where it belongs)"   || bad "8 rig commit committer is '${rig%%|*}', want 'frontier-25379'"

# ── 9. the LAUNCHER re-picks the identity PER TICKET (a droid handles several repos per session,
# so a launch-time-only stamp would put the rig id on product commits). Assert the wiring exists
# AND that it is downstream of repo_resolve, where RR_KEY is actually known.
if grep -q 'droid_identity_for_repo "\$RR_KEY" "\$DROID"' "$FLEET_SRC/fleet-droid.sh"; then
  got9="$(bash -c 'FLEET="'"$FLEET_SRC"'"; source "$FLEET/repo-registry.sh"; source "$FLEET/droid-identity.sh"; repo_resolve charon T >/dev/null; droid_identity_for_repo "$RR_KEY" "tier-777" >/dev/null; printf "%s" "$GIT_COMMITTER_NAME"')"
  case "$got9" in
    *tier-777*|"") bad "9 launcher wiring still stamps the droid id for the product repo (got '$got9')" ;;
    *)             ok  "9 fleet-droid.sh re-picks the stamp per ticket from RR_KEY (product -> '$got9')" ;;
  esac
else
  bad "9 fleet-droid.sh never calls droid_identity_for_repo — rig taxonomy reaches PUBLIC commits"
fi

echo "droid-identity: $fails failure(s)"
[ "$fails" -eq 0 ]
