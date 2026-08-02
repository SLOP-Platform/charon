#!/usr/bin/env bash
# auto-done-on-merge.test.sh — FAIL-ON-REVERT proof for AUTO-DONE-ON-MERGE-MISS.
#
# THE DEFECT (measured 2026-08-01): a MERGED PR did not produce fleet/state/done/<TICKET>, so the
# ticket stayed in `submitted` forever and claim.sh refused to admit its dependents. Root cause was
# NOT a missing mechanism — fleet/reconcile-merged.sh has been wired into `preflight.sh scan` all
# along — it was that reconcile-merged.sh queried exactly ONE repo (the PRODUCT, SLOP-Platform/
# charon, derived from a single hardcoded slug), while the board is MULTI-REPO. Every ticket with
# `repo: charon-private` was therefore structurally unreachable: its PR merges in
# Nnyan/charon-private, a repo the reconciler never asked about.
# Live instance: LEDGER-NO-EVIDENCE-NO-VERDICT merged as Nnyan/charon-private#358 at 19:31:39Z, got
# no marker, and blocked GRADE-MODEL-PROVIDER-PAIR until the marker was hand-written.
#
# WHAT EACH CASE PINS (and what reverting breaks):
#   (a) a RIG ticket whose PR merged in Nnyan/charon-private is auto-closed WITH proof, and its
#       stale `submitted/` marker is cleared.        <-- REVERT: rig repo never queried -> FAILS
#   (b) a PRODUCT ticket still auto-closes (no regression of the pre-existing behaviour).
#   (c) CROSS-REPO ISOLATION: a merged PRODUCT PR on branch `feat/shared-name` must NOT close the
#       RIG ticket that uses the same branch name. Querying two repos without scoping the match to
#       the PR's own repo would trade the old miss for a far worse FALSE close, so the scoping is
#       pinned here.                                  <-- REVERT of _slug_matches: FAILS
#   (d) ZERO GraphQL: the reconciler must reach the forge over REST (`gh api`) only. The GraphQL
#       quota that `gh pr list` spends was fully exhausted on 2026-08-01, and an exhausted quota
#       used to render as "clean".                    <-- REVERT: `gh pr list` seen -> FAILS
#   (e) IDEMPOTENT: a second run changes no marker and exits 0.
#   (f) FAIL CLOSED on an UNDETERMINED repo: when the listing call fails (rate limit / auth /
#       network) NO done marker is written for that repo and the run is LOUD + non-zero, never
#       "clean". A false `done` retires a ticket whose work may not exist.
#   (g) FAIL CLOSED at the write point: a PR the listing calls merged but whose per-PR REST record
#       says `.merged=false` is REFUSED. This is the last gate before a marker every downstream
#       gate treats as ground truth.
#
# NO REAL API CALLS: `gh` is stubbed by a PATH shim that serves canned JSON out of a fixture dir
# and logs every invocation (the log is what (d) asserts against). The shim also answers the OLD
# `gh pr list` GraphQL form with the PRODUCT repo's merged list — deliberately, so that reverting
# the source leaves (b) GREEN and fails precisely (a)/(c)/(d). That makes the red-proof point at
# the multi-repo gap rather than at "nothing works".
#
# Run:  bash fleet/tests/auto-done-on-merge.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

PROD_SLUG="SLOP-Platform/charon"
RIG_SLUG="Nnyan/charon-private"

# ── isolated repos ────────────────────────────────────────────────────────────────────────────
# done.sh proves `--merged-sha` by ancestry against the TICKET'S OWN repo (it is repo-aware since
# the H2 fix), so the rig and product arms need SEPARATE checkouts with distinct shas — that
# separation is what makes (c) meaningful rather than accidental.
mk_repo(){ local p="$1"; git -C "$p" init -q
           git -C "$p" commit -q --allow-empty -m base
           git -C "$p" update-ref refs/remotes/origin/master "$(git -C "$p" rev-parse HEAD)"
           git -C "$p" rev-parse HEAD; }
P="$(mktemp -d)"; SP="$(mk_repo "$P")"
R="$(mktemp -d)"; SR="$(mk_repo "$R")"

# ── gh PATH shim ──────────────────────────────────────────────────────────────────────────────
SHIMBIN="$(mktemp -d)"
FIX="$(mktemp -d)"; mkdir -p "$FIX/list" "$FIX/pr" "$FIX/files"
GH_CALL_LOG="$FIX/calls.log"; : > "$GH_CALL_LOG"
cat > "$SHIMBIN/gh" <<'SHIM'
#!/usr/bin/env bash
# Stub `gh`. Serves canned JSON from $FIX and logs every call to $GH_CALL_LOG. NO NETWORK.
# jq is real, so the production --jq filters are genuinely exercised rather than bypassed.
set -uo pipefail
printf '%s\n' "$*" >> "$GH_CALL_LOG"
key(){ printf '%s' "${1//\//__}"; }

if [ "${1:-}" = api ]; then
  shift
  url="$1"; shift
  filter=""
  while [ $# -gt 0 ]; do case "$1" in --jq|-q) filter="${2:-}"; shift 2;; *) shift;; esac; done
  path="${url%%\?*}"
  # GH_FAIL_SLUG simulates a rate-limited / unauthenticated repo: non-zero + a message on stderr,
  # exactly what `gh api` does when the core quota is spent.
  case "$path" in
    repos/*/pulls|repos/*/pulls/*)
      slug="${path#repos/}"; slug="${slug%%/pulls*}"
      if [ -n "${GH_FAIL_SLUG:-}" ] && [ "$slug" = "$GH_FAIL_SLUG" ]; then
        echo "gh: API rate limit exceeded for $slug" >&2; exit 1
      fi ;;
  esac
  case "$path" in
    repos/*/pulls)
      slug="${path#repos/}"; slug="${slug%/pulls}"; f="$FIX/list/$(key "$slug").json" ;;
    repos/*/pulls/*/files)
      rest="${path#repos/}"; slug="${rest%%/pulls/*}"; n="${rest##*/pulls/}"; n="${n%/files}"
      f="$FIX/files/$(key "$slug")-$n.json" ;;
    repos/*/pulls/*)
      rest="${path#repos/}"; slug="${rest%%/pulls/*}"; n="${rest##*/pulls/}"
      f="$FIX/pr/$(key "$slug")-$n.json" ;;
    *) echo "gh shim: unhandled api path: $path" >&2; exit 1 ;;
  esac
  [ -f "$f" ] || { echo "gh shim: no fixture for $path ($f)" >&2; exit 1; }
  if [ -n "$filter" ]; then jq -r "$filter" < "$f"; else cat "$f"; fi
  exit $?
fi

# LEGACY GraphQL form (`gh pr list --repo <slug> --state merged ...`). Present ONLY so the
# pre-fix source still sees the product repo's merged list during the external red-proof.
if [ "${1:-}" = pr ] && [ "${2:-}" = list ]; then
  slug=""; while [ $# -gt 0 ]; do case "$1" in --repo) slug="${2:-}"; shift 2;; *) shift;; esac; done
  f="$FIX/list/$(key "$slug").json"
  [ -f "$f" ] || exit 0
  jq -r '.[] | select(.merged_at != null) | [.head.ref, (.merge_commit_sha // ""), ([.files[].filename]|join(",")), (.number|tostring)] | @tsv' < "$f"
  exit 0
fi
exit 0
SHIM
chmod +x "$SHIMBIN/gh"
export FIX GH_CALL_LOG
export PATH="$SHIMBIN:$PATH"

# ── fixture fleet dir ─────────────────────────────────────────────────────────────────────────
# repo-registry.sh is deliberately NOT copied: absent, _lib.sh's _vm_registry_path returns "no
# registry" and the CHARON_FLEET_REPO / VERIFY_MERGED_REPO env overrides supply the paths, so the
# test can never touch the operator's real /home/stack checkouts.
d="$(mktemp -d)"
cp "$SRC/reconcile-merged.sh" "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" \
   "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$d/"
mkdir -p "$d/board/archive" "$d/state/done" "$d/state/submitted" "$d/state/claims" "$d/state/needs-push"

mk_ticket(){ # <id> <repo-key> <branch> <owns>
  printf 'repo: %s\ntier: economy\nbranch: %s\nowns: %s\nwork_class: docs\n' "$2" "$3" "$4" > "$d/board/$1.md"
  printf '%s\n' "$(date -u +%FT%TZ)" > "$d/state/submitted/$1"
}
mk_ticket PROD-TICK    charon         feat/prod-tick    src/p.py
mk_ticket RIG-TICK     charon-private fix/rig-tick      fleet/r.sh
# Deliberate NAMES: the RIG owner sorts BEFORE the product owner. The board index is built in
# glob (alphabetical) order and an UNSCOPED branch match returns the FIRST hit, so without
# repo-scoping the product PR would close A-RIG-COLLIDE. Naming them the other way round
# would let (c) pass by luck on unscoped code — i.e. it would not be a fail-on-revert case.
mk_ticket A-RIG-COLLIDE  charon-private feat/shared-name  fleet/collide.sh
mk_ticket Z-PROD-COLLIDE charon         feat/shared-name  src/collide.py

pr_json(){ # <branch> <sha> <number> <merged_at> <file>
  printf '{"head":{"ref":"%s"},"merge_commit_sha":"%s","number":%s,"merged":%s,"merged_at":%s,"files":[{"filename":"%s"}]}' \
    "$1" "$2" "$3" "$([ -n "$4" ] && echo true || echo false)" \
    "$([ -n "$4" ] && printf '"%s"' "$4" || echo null)" "$5"
}
write_fixture(){ # rebuild the canned forge state
  { printf '['; pr_json feat/prod-tick   "$SP" 10 2026-08-01T10:00:00Z src/p.py;       printf ','
    pr_json feat/shared-name "$SP" 12 2026-08-01T11:00:00Z src/collide.py; printf ']'
  } > "$FIX/list/SLOP-Platform__charon.json"
  { printf '['; pr_json fix/rig-tick "$SR" 358 2026-08-01T19:31:39Z fleet/r.sh; printf ']'
  } > "$FIX/list/Nnyan__charon-private.json"
  pr_json feat/prod-tick   "$SP" 10  2026-08-01T10:00:00Z src/p.py       > "$FIX/pr/SLOP-Platform__charon-10.json"
  pr_json feat/shared-name "$SP" 12  2026-08-01T11:00:00Z src/collide.py > "$FIX/pr/SLOP-Platform__charon-12.json"
  pr_json fix/rig-tick     "$SR" 358 2026-08-01T19:31:39Z fleet/r.sh     > "$FIX/pr/Nnyan__charon-private-358.json"
  printf '[{"filename":"src/p.py"}]'       > "$FIX/files/SLOP-Platform__charon-10.json"
  printf '[{"filename":"src/collide.py"}]' > "$FIX/files/SLOP-Platform__charon-12.json"
  printf '[{"filename":"fleet/r.sh"}]'     > "$FIX/files/Nnyan__charon-private-358.json"
}
write_fixture

# The env overrides point BOTH repo arms at the throwaway checkouts above.
export DONE_CHARON_REPO="$P" VERIFY_MERGED_REPO="$P" CHARON_FLEET_REPO="$R"
run(){ ( unset RECONCILE_MERGED_SRC RECONCILE_REPO_SLUG; bash "$d/reconcile-merged.sh" ) >"$FIX/out.txt" 2>&1; }

echo "== live REST path (gh shimmed) =="
: > "$GH_CALL_LOG"
rc=0; run || rc=$?
[ "$rc" = 0 ] && ok "run exits 0 when every repo answered" || { bad "run exits 0 (got $rc)"; sed 's/^/    /' "$FIX/out.txt"; }

# (a) THE DEFECT — a rig-repo merge must close its rig ticket.
if [ -e "$d/state/done/RIG-TICK" ]; then ok "a RIG ticket auto-closed from $RIG_SLUG#358"
else bad "a RIG ticket auto-closed from $RIG_SLUG#358"; fi
grep -q "merged:$SR" "$d/state/done/RIG-TICK" 2>/dev/null \
  && ok "a rig marker carries merged:<rig sha> proof" || bad "a rig marker carries merged:<rig sha> proof"
[ -e "$d/state/submitted/RIG-TICK" ] && bad "a stale submitted/ marker cleared for RIG-TICK" \
                                     || ok "a stale submitted/ marker cleared for RIG-TICK"
# (b) no regression on the product arm
[ -e "$d/state/done/PROD-TICK" ] && ok "b PRODUCT ticket still auto-closes" || bad "b PRODUCT ticket still auto-closes"
[ -e "$d/state/submitted/PROD-TICK" ] && bad "b stale submitted/ cleared for PROD-TICK" \
                                      || ok "b stale submitted/ cleared for PROD-TICK"
# (c) cross-repo isolation: same branch name, two repos, only the PR's own repo may close.
[ -e "$d/state/done/Z-PROD-COLLIDE" ] && ok "c product PR closed the PRODUCT owner of feat/shared-name" \
                                    || bad "c product PR closed the PRODUCT owner of feat/shared-name"
[ -e "$d/state/done/A-RIG-COLLIDE" ] && bad "c product PR did NOT close the RIG ticket sharing the branch name" \
                                   || ok "c product PR did NOT close the RIG ticket sharing the branch name"
# (d) REST only — no GraphQL surface touched.
if grep -Eq '^pr (list|view)' "$GH_CALL_LOG"; then
  bad "d ZERO GraphQL calls (saw: $(grep -Em1 '^pr (list|view)' "$GH_CALL_LOG"))"
else ok "d ZERO GraphQL calls — forge reached over REST only"; fi
grep -q '^api repos/Nnyan/charon-private/pulls' "$GH_CALL_LOG" \
  && ok "d the RIG repo was actually queried" || bad "d the RIG repo was actually queried"

# (e) idempotence
before="$(cat "$d/state/done/RIG-TICK" "$d/state/done/PROD-TICK" 2>/dev/null)"
rc=0; run || rc=$?
after="$(cat "$d/state/done/RIG-TICK" "$d/state/done/PROD-TICK" 2>/dev/null)"
[ "$rc" = 0 ] && ok "e second run exits 0" || bad "e second run exits 0 (got $rc)"
[ "$before" = "$after" ] && ok "e second run left every marker byte-identical" \
                         || bad "e second run mutated a marker"

# (f) FAIL CLOSED: the rig listing cannot be fetched -> no marker, loud, non-zero.
echo "== (f) fail-closed when a repo's merge state is UNDETERMINED =="
f="$(mktemp -d)"
cp "$SRC/reconcile-merged.sh" "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" \
   "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$f/"
mkdir -p "$f/board/archive" "$f/state/done" "$f/state/submitted" "$f/state/claims" "$f/state/needs-push"
printf 'repo: charon-private\ntier: economy\nbranch: fix/rig-tick\nowns: fleet/r.sh\nwork_class: docs\n' > "$f/board/RIG-TICK.md"
printf 'now\n' > "$f/state/submitted/RIG-TICK"
rc=0
( unset RECONCILE_MERGED_SRC RECONCILE_REPO_SLUG; GH_FAIL_SLUG="$RIG_SLUG" bash "$f/reconcile-merged.sh" ) \
  >"$FIX/fail.txt" 2>&1 || rc=$?
[ "$rc" != 0 ] && ok "f UNDETERMINED merge state exits non-zero (got $rc)" || bad "f UNDETERMINED merge state exits non-zero (got 0)"
[ -e "$f/state/done/RIG-TICK" ] && bad "f NO done marker written for an unqueryable repo" \
                                || ok "f NO done marker written for an unqueryable repo"
[ -e "$f/state/submitted/RIG-TICK" ] && ok "f submitted/ left INTACT (not retired on a guess)" \
                                     || bad "f submitted/ left INTACT (not retired on a guess)"
grep -q 'UNDETERMINED' "$FIX/fail.txt" && ok "f failure is LOUD (says UNDETERMINED)" || bad "f failure is LOUD (says UNDETERMINED)"
grep -q 'reconcile-merged: clean' "$FIX/fail.txt" && bad "f must NOT report 'clean' when a repo failed" \
                                                  || ok "f must NOT report 'clean' when a repo failed"

# (g) FAIL CLOSED at the write point: listed as merged, but the per-PR record says otherwise.
echo "== (g) fail-closed when the per-PR REST record does not confirm the merge =="
g="$(mktemp -d)"
cp "$SRC/reconcile-merged.sh" "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" \
   "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$g/"
mkdir -p "$g/board/archive" "$g/state/done" "$g/state/submitted" "$g/state/claims" "$g/state/needs-push"
printf 'repo: charon-private\ntier: economy\nbranch: fix/rig-tick\nowns: fleet/r.sh\nwork_class: docs\n' > "$g/board/RIG-TICK.md"
printf 'now\n' > "$g/state/submitted/RIG-TICK"
# the LIST still advertises it as merged; the authoritative per-PR record does not.
printf '{"head":{"ref":"fix/rig-tick"},"merge_commit_sha":"%s","number":358,"merged":false,"merged_at":null,"files":[{"filename":"fleet/r.sh"}]}' \
  "$SR" > "$FIX/pr/Nnyan__charon-private-358.json"
rc=0
( unset RECONCILE_MERGED_SRC RECONCILE_REPO_SLUG; bash "$g/reconcile-merged.sh" ) >"$FIX/g.txt" 2>&1 || rc=$?
[ -e "$g/state/done/RIG-TICK" ] && bad "g REFUSED a marker the per-PR record does not confirm" \
                               || ok "g REFUSED a marker the per-PR record does not confirm"
grep -q 'is NOT merged per REST' "$FIX/g.txt" && ok "g refusal names the REST evidence" || bad "g refusal names the REST evidence"
write_fixture   # restore

rm -rf "$d" "$f" "$g" "$P" "$R" "$SHIMBIN" "$FIX"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL AUTO-DONE-ON-MERGE TESTS PASS"
