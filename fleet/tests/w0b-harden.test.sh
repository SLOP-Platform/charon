#!/usr/bin/env bash
# w0b-harden.test.sh — FAIL-ON-REVERT tests for W0b (three sites the W0 destruction-class fix
# skipped). Every case uses REAL git objects / REAL directories inside its OWN `mktemp -d`.
# NOTHING here ever names a path outside its temp root: no destruction guard is exercised
# against a live tree, and $HOME is redirected into the temp root for the reaper cases so even
# the "$HOME is protected" assertion touches only a throwaway directory.
#
# SIBLING-STATE ISOLATION: every assertion builds its own fresh temp repo/dir. No case reads
# state another case wrote, so a RED here is always that case's own failure, never a cascade.
#
# FIX 1 — fleet/land.sh safe_sync_base(): when another worktree HOLDS <base>, every
#   `git checkout "$base"` inside it dies with "already used by worktree at ..." and the old code
#   returned 0 from the "checkout failed — skipping sync" arm: a SILENT no-op (observed 3x).
# FIX 2 — fleet/branch-reaper.sh: `rm -rf "$wt_dir"` guarded only by two equality checks.
# FIX 3 — fleet/benchmark/dogfood-eval.sh run_one(): `rm -rf "$wt"` with no guard at all.
#
# Run:  bash fleet/tests/w0b-harden.test.sh   (exit 0 = all pass)
set -uo pipefail
FLEET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAND="$FLEET_DIR/land.sh"
REAPER="$FLEET_DIR/branch-reaper.sh"
DOGFOOD="$FLEET_DIR/benchmark/dogfood-eval.sh"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 fixture: bare origin + primary clone ON master + a second worktree on a
# feature branch. land.sh --sync-only is invoked FROM the second worktree, so the
# PRIMARY is the holder of master — exactly the live shape that misfired today.
# `base_ahead` pushes an extra commit to origin so a real fast-forward is possible.
# ─────────────────────────────────────────────────────────────────────────────
mk_holder_fixture(){
  local root; root="$(mktemp -d)"
  local origin="$root/origin.git" primary="$root/primary" wt="$root/wt"
  git init -q --bare "$origin"
  git clone -q "$origin" "$primary" 2>/dev/null
  git -C "$primary" config user.email t@t; git -C "$primary" config user.name t
  git -C "$primary" checkout -q -b master 2>/dev/null || git -C "$primary" checkout -q master
  printf 'base\n' > "$primary/tracked.txt"
  git -C "$primary" add -A; git -C "$primary" commit -q -m c1
  git -C "$primary" push -q -u origin master 2>/dev/null
  # advance origin/master by one commit made in a throwaway clone (primary stays BEHIND)
  local bump="$root/bump"
  git clone -q "$origin" "$bump" 2>/dev/null
  git -C "$bump" config user.email t@t; git -C "$bump" config user.name t
  printf 'ahead\n' >> "$bump/tracked.txt"
  git -C "$bump" add -A; git -C "$bump" commit -q -m c2
  git -C "$bump" push -q origin master 2>/dev/null
  # second worktree on a feature branch — this is where land.sh runs from
  git -C "$primary" worktree add -q "$wt" -b feature master 2>/dev/null
  git -C "$primary" fetch -q origin
  printf '%s\n' "$root"
}

# --- A1: holder present, holder CLEAN -> the sync ACTUALLY HAPPENS in the holder ---
# REVERT LINE: fleet/land.sh — delete the whole `if holder="$(pv_branch_holder "$repo" "$base")"`
# block in safe_sync_base(). Reverted, `git checkout master` fails ("already used by worktree"),
# the function returns 0 from the "checkout $base failed — skipping sync" arm, and master stays
# at c1 => the sha assertion goes RED for its OWN reason (base not advanced).
ROOT_A1="$(mk_holder_fixture)"
BEFORE_A1="$(git -C "$ROOT_A1/primary" rev-parse master)"
ORIGIN_A1="$(git -C "$ROOT_A1/primary" rev-parse origin/master)"
OUT_A1="$(bash "$LAND" --sync-only "$ROOT_A1/wt" master 2>&1)"; RC_A1=$?
AFTER_A1="$(git -C "$ROOT_A1/primary" rev-parse master)"
check "A1a: holder-clean sync returns rc 0" "$RC_A1" "0"
if [ "$BEFORE_A1" = "$ORIGIN_A1" ]; then
  bad "A1 fixture broken: master was already at origin/master (nothing to sync)"
else
  ok "A1 fixture sane: local master is BEHIND origin/master before the sync"
fi
check "A1b: base was ACTUALLY fast-forwarded in the holding worktree (not silently skipped)" \
  "$AFTER_A1" "$ORIGIN_A1"
case "$OUT_A1" in
  *"is held by worktree"*) ok "A1c: the holder was reported by name, not silently skipped" ;;
  *) bad "A1c: no holder report in output: $OUT_A1" ;;
esac
case "$OUT_A1" in
  *"skipping sync"*) bad "A1d: still took the old SILENT-SKIP arm" ;;
  *) ok "A1d: did not fall into the old 'checkout failed — skipping sync' arm" ;;
esac

# --- A2: holder present but DIRTY -> LOUD refusal with a non-zero rc the caller can see ---
# REVERT LINE: fleet/land.sh — in the dirty-holder arm of safe_sync_base(), change `return 3`
# to `return 0`. Reverted, rc becomes 0 and A2a goes RED for its own reason (refusal swallowed).
ROOT_A2="$(mk_holder_fixture)"
printf 'dirty-in-holder\n' >> "$ROOT_A2/primary/tracked.txt"
BEFORE_A2="$(git -C "$ROOT_A2/primary" rev-parse master)"
OUT_A2="$(bash "$LAND" --sync-only "$ROOT_A2/wt" master 2>&1)"; RC_A2=$?
AFTER_A2="$(git -C "$ROOT_A2/primary" rev-parse master)"
check "A2a: dirty holder => caller sees a NON-ZERO rc (refusal not swallowed)" "$RC_A2" "3"
check "A2b: dirty holder => base ref left untouched" "$AFTER_A2" "$BEFORE_A2"
case "$OUT_A2" in
  *"REFUSING sync"*) ok "A2c: refusal is reported LOUDLY" ;;
  *) bad "A2c: no REFUSING line in output: $OUT_A2" ;;
esac
DIRTY_A2="$(cat "$ROOT_A2/primary/tracked.txt")"
case "$DIRTY_A2" in
  *dirty-in-holder*) ok "A2d: the holder's uncommitted work survived untouched" ;;
  *) bad "A2d: uncommitted work in the holder was destroyed" ;;
esac

# --- A3: NO holder -> the ordinary clean-tree fast-forward path still works (positive case) ---
# REVERT LINE: same holder block. This case proves the new block does not hijack the normal
# path; it is independent of A1/A2 (its own fixture, and no worktree holds master).
ROOT_A3="$(mk_holder_fixture)"
git -C "$ROOT_A3/primary" worktree remove --force "$ROOT_A3/wt" >/dev/null 2>&1
ORIGIN_A3="$(git -C "$ROOT_A3/primary" rev-parse origin/master)"
OUT_A3="$(bash "$LAND" --sync-only "$ROOT_A3/primary" master 2>&1)"; RC_A3=$?
AFTER_A3="$(git -C "$ROOT_A3/primary" rev-parse master)"
check "A3a: no-holder ordinary sync returns rc 0" "$RC_A3" "0"
check "A3b: no-holder ordinary sync still fast-forwards base" "$AFTER_A3" "$ORIGIN_A3"

# ─────────────────────────────────────────────────────────────────────────────
# FIX 2 — branch-reaper.sh catastrophic-target guard.
# Each case gets its own temp root AND its own fake $HOME inside that root.
# ─────────────────────────────────────────────────────────────────────────────
mk_reaper_fixture(){   # -> root; repo at $root/live, fleet state at $root/fleet, HOME at $root/home
  local root; root="$(mktemp -d)"
  mkdir -p "$root/live" "$root/fleet/state/claims" "$root/fleet/state/needs-push" "$root/home"
  git -C "$root/live" init -q -b master
  git -C "$root/live" config user.email t@t; git -C "$root/live" config user.name t
  echo seed > "$root/live/README.md"
  git -C "$root/live" add -A; git -C "$root/live" commit -q -m seed
  printf '%s\n' "$root"
}
run_reaper(){ # run_reaper <root> <glob> [repo_override]
  # NOTE: separate statements — a single `local root="$1" repo="${3:-$root/live}"` declares both
  # names before assigning, so $root is still unset when the default expands and `set -u` aborts
  # the whole function, making every assertion below it pass VACUOUSLY on empty output.
  local root="$1"
  local glob="$2"
  local repo="${3:-$root/live}"
  HOME="$root/home" \
  REAPER_REPO="$repo" REAPER_BASE=master REAPER_FLEET_DIR="$root/fleet" \
  REAPER_WT_GLOB="$glob" bash "$REAPER" --apply 2>&1
}
# NON-VACUITY NOTE. Every glob below is chosen so the candidate reaches the guard with a
# NON-EMPTY id: a bare directory glob (no `*`) makes wt_prefix == the glob, so id == "" and the
# loop `continue`s on the label check — an assertion written that way would pass even with the
# guard DELETED. Each glob therefore ends in a partial-name `*` (…/wtdi*, …/liv*, …/hom*) so the
# id is non-empty and the ONLY thing standing between the directory and `rm -rf` is the guard.

# REVERT LINE (covers B1..B4): fleet/branch-reaper.sh — delete the
# `if _rp_why="$(_lg_wt_catastrophic "$_rp_real" "$_rp_repo")"; then ... continue; fi` block.
# Reverted, each catastrophic dir below is rm -rf'd and its "survived" assertion goes RED.

# B1: target is an ANCESTOR of the live checkout. The repo is nested at <root>/wtdir/live and the
# glob "<root>/wtdi*" matches <root>/wtdir with id="r" — so the candidate reaches the guard.
ROOT_B1="$(mk_reaper_fixture)"
mkdir -p "$ROOT_B1/wtdir"
git -C "$ROOT_B1/wtdir" init -q -b master 2>/dev/null
mkdir -p "$ROOT_B1/wtdir/live"
git -C "$ROOT_B1/wtdir/live" init -q -b master
git -C "$ROOT_B1/wtdir/live" config user.email t@t; git -C "$ROOT_B1/wtdir/live" config user.name t
echo seed > "$ROOT_B1/wtdir/live/README.md"
git -C "$ROOT_B1/wtdir/live" add -A; git -C "$ROOT_B1/wtdir/live" commit -q -m seed
echo keep > "$ROOT_B1/wtdir/canary"
OUT_B1="$(run_reaper "$ROOT_B1" "$ROOT_B1/wtdi*" "$ROOT_B1/wtdir/live")"
[ -f "$ROOT_B1/wtdir/canary" ] && [ -f "$ROOT_B1/wtdir/live/README.md" ] \
  && ok "B1a: ancestor-of-live-checkout target SURVIVED (not rm -rf'd)" \
  || bad "B1a: ancestor of the live checkout was DESTROYED"
case "$OUT_B1" in *REFUSE*) ok "B1b: the refusal was reported" ;; *) bad "B1b: no REFUSE line: $OUT_B1" ;; esac

# B2: target IS the live checkout itself. REAPER_REPO carries a trailing slash, so the
# pre-existing `[ "$wt_dir" = "$REAPER_REPO" ]` STRING equality does NOT match — only the
# realpath-based guard catches it. That is what makes this case non-vacuous.
ROOT_B2="$(mk_reaper_fixture)"
OUT_B2="$(run_reaper "$ROOT_B2" "$ROOT_B2/liv*" "$ROOT_B2/live/")"
[ -f "$ROOT_B2/live/README.md" ] \
  && ok "B2a: the live checkout itself SURVIVED (string-equality check evaded by a trailing slash)" \
  || bad "B2a: the live checkout was DESTROYED"
case "$OUT_B2" in *REFUSE*) ok "B2b: the refusal was reported" ;; *) bad "B2b: no REFUSE line: $OUT_B2" ;; esac

# B3: target is $HOME (redirected into this case's own temp root — never the real home).
ROOT_B3="$(mk_reaper_fixture)"
echo precious > "$ROOT_B3/home/precious"
OUT_B3="$(run_reaper "$ROOT_B3" "$ROOT_B3/hom*")"
[ -f "$ROOT_B3/home/precious" ] \
  && ok "B3a: \$HOME SURVIVED" \
  || bad "B3a: \$HOME was DESTROYED"
case "$OUT_B3" in *REFUSE*) ok "B3b: the refusal was reported" ;; *) bad "B3b: no REFUSE line: $OUT_B3" ;; esac

# B4: target is the filesystem root — asserted via the REFUSE report only. `/` is never a
# candidate for removal here because the guard refuses before any rm, and the test asserts the
# refusal text; nothing on the real filesystem is touched either way.
ROOT_B4="$(mk_reaper_fixture)"
OUT_B4="$(run_reaper "$ROOT_B4" "/")"
case "$OUT_B4" in
  *"refusing filesystem root"*) ok "B4: '/' is REFUSED with the root reason" ;;
  *) bad "B4: '/' was not refused as filesystem root: $OUT_B4" ;;
esac

# B5 (POSITIVE): a legitimate stale fleet worktree dir with no live marker is STILL reaped.
# REVERT LINE: this is the anti-over-block case — if the guard were widened to refuse
# everything, B5 goes RED. It is what proves B1..B4 are not passing vacuously.
ROOT_B5="$(mk_reaper_fixture)"
mkdir -p "$ROOT_B5/live-fleet-TICKET1"; echo stale > "$ROOT_B5/live-fleet-TICKET1/f"
OUT_B5="$(run_reaper "$ROOT_B5" "$ROOT_B5/live-fleet-*")"
[ -d "$ROOT_B5/live-fleet-TICKET1" ] \
  && bad "B5: a legitimate stale worktree was NOT reaped (guard over-blocks)" \
  || ok "B5: a legitimate stale worktree is still reaped (guard does not over-block)"

# B6 (POSITIVE, pre-existing guard intact): a worktree with a live claim marker is KEPT.
ROOT_B6="$(mk_reaper_fixture)"
mkdir -p "$ROOT_B6/live-fleet-TICKET2"; echo work > "$ROOT_B6/live-fleet-TICKET2/f"
touch "$ROOT_B6/fleet/state/claims/TICKET2"
OUT_B6="$(run_reaper "$ROOT_B6" "$ROOT_B6/live-fleet-*")"
[ -f "$ROOT_B6/live-fleet-TICKET2/f" ] \
  && ok "B6: the pre-existing live-claim guard still protects a claimed worktree" \
  || bad "B6: a CLAIMED worktree was reaped (pre-existing guard broken)"

# ─────────────────────────────────────────────────────────────────────────────
# FIX 3 — dogfood-eval.sh run_one() catastrophic-target guard. Drives the REAL script.
# DOGFOOD_TS pins the run stamp so the exact worktree path is known up front; the product repo
# is then placed INSIDE that path, making the worktree target an ancestor of the live checkout.
# ─────────────────────────────────────────────────────────────────────────────
mk_dogfood_root(){ mktemp -d; }
run_dogfood(){ # run_dogfood <root> <product_repo> <ticket_label> <ts> <model>
  local root="$1" repo="$2" label="$3" ts="$4" model="$5"
  mkdir -p "$root/results"
  echo "brief" > "$root/brief.md"
  DOGFOOD_TEST_MODE=1 DOGFOOD_TS="$ts" \
  DOGFOOD_PRODUCT_REPO="$repo" \
  DOGFOOD_BASE_REF=master \
  DOGFOOD_WORKTREE_PARENT="$root/wtp" \
  DOGFOOD_RESULTS_DIR="$root/results" \
  DOGFOOD_GATE_CMD=true DOGFOOD_TEST_CMD=true \
  DOGFOOD_CHARON_RUN="$root/fake-charon-run.sh" \
  DOGFOOD_KEEP_WORKTREE=1 \
    bash "$DOGFOOD" "$label" "$root/brief.md" "$model" 2>&1
}
mk_fake_run(){ printf '#!/usr/bin/env bash\nexit 0\n' > "$1/fake-charon-run.sh"; chmod +x "$1/fake-charon-run.sh"; }
mk_repo(){ mkdir -p "$1"; git -C "$1" init -q -b master; git -C "$1" config user.email t@t
           git -C "$1" config user.name t; echo seed > "$1/README.md"
           git -C "$1" add -A; git -C "$1" commit -q -m seed; }

# REVERT LINE (covers C1, C2): fleet/benchmark/dogfood-eval.sh — delete the
# `if dg_why="$(_lg_wt_catastrophic "$dg_real" "$dg_repo")"; then ... return; fi` block in
# run_one(). Reverted, `rm -rf "$wt"` runs on a directory CONTAINING the product repo and the
# canary is destroyed => C1 goes RED for its own reason.
TS_C=20260718T000000Z
MODEL_C=stub-model

# C1: worktree target CONTAINS the live checkout -> REFUSED, canary survives.
ROOT_C1="$(mk_dogfood_root)"; mk_fake_run "$ROOT_C1"
WT_C1="$ROOT_C1/wtp/charon-fleet-dogfood-CAT-${MODEL_C}-${TS_C}"
mkdir -p "$WT_C1"
mk_repo "$WT_C1/product"
echo precious > "$WT_C1/canary"
OUT_C1="$(run_dogfood "$ROOT_C1" "$WT_C1/product" CAT "$TS_C" "$MODEL_C")"
[ -f "$WT_C1/canary" ] \
  && ok "C1a: catastrophic worktree target (contains the live checkout) SURVIVED" \
  || bad "C1a: dogfood-eval rm -rf'd a directory containing the live checkout"
[ -f "$WT_C1/product/README.md" ] \
  && ok "C1b: the live checkout inside the target SURVIVED" \
  || bad "C1b: the live checkout was DESTROYED"
case "$OUT_C1" in
  *"REFUSING"*) ok "C1c: the refusal was reported" ;;
  *) bad "C1c: no REFUSING line: $OUT_C1" ;;
esac

# C2 (POSITIVE): an ordinary, non-catastrophic worktree target is NOT refused — the candidate
# runs and produces a card. This is what proves C1 is not passing because the script simply
# refuses everything.
ROOT_C2="$(mk_dogfood_root)"; mk_fake_run "$ROOT_C2"
mk_repo "$ROOT_C2/product"
OUT_C2="$(run_dogfood "$ROOT_C2" "$ROOT_C2/product" OKAY "$TS_C" "$MODEL_C")"
WT_C2="$ROOT_C2/wtp/charon-fleet-dogfood-OKAY-${MODEL_C}-${TS_C}"
[ -d "$WT_C2" ] \
  && ok "C2a: a legitimate worktree target was created (guard does not over-block)" \
  || bad "C2a: a legitimate worktree target was refused/never created: $OUT_C2"
case "$OUT_C2" in
  *"catastrophic-worktree-target"*) bad "C2b: a legitimate target was wrongly called catastrophic" ;;
  *) ok "C2b: a legitimate target is not reported catastrophic" ;;
esac

# ─────────────────────────────────────────────────────────────────────────────
# MED-1 / MED-2 / LOW-4 / LOW-5 (2026-07-19 adversarial review of the W0b fix itself).
# The C cases above only ever prove the guard refuses a target that CONTAINS a protected tree.
# They say nothing about a target that ESCAPES $WORKTREE_PARENT onto an UNPROTECTED sibling —
# which $TICKET_LABEL could do, because it is bare-interpolated into the rm -rf'd path.
# Every case below gets its OWN mktemp -d; nothing reads another case's state.
# ─────────────────────────────────────────────────────────────────────────────

# D1: a TRAVERSAL ticket label is REFUSED and destroys nothing.
# This is the reviewer's live repro: with the intermediate dir present, 'x/../../NEIGHBOUR'
# normalised $wt OUT of $WORKTREE_PARENT, the catastrophic guard passed with NO refusal line,
# and the rm -rf at run_one destroyed $root/NEIGHBOUR-... .
# REVERT LINE: fleet/benchmark/dogfood-eval.sh — delete the
# `if ! repo_valid_id "$TICKET_LABEL"; then ... exit 2; fi` block after the argv parse.
# Reverted, the label is accepted, run_one is reached and the NEIGHBOUR canary is destroyed
# => D1a goes RED for its OWN reason (canary gone), independently of every other case.
ROOT_D1="$(mk_dogfood_root)"; mk_fake_run "$ROOT_D1"
mk_repo "$ROOT_D1/product"
TS_D=20260719T000000Z
# the intermediate dir the traversal walks THROUGH (this is what made the escape resolvable)
mkdir -p "$ROOT_D1/wtp/charon-fleet-dogfood-x"
# the unprotected sibling the escape lands on — a plain directory, NOT $HOME, NOT a checkout,
# so _lg_wt_catastrophic has no reason of its own to refuse it.
mkdir -p "$ROOT_D1/NEIGHBOUR-${MODEL_C}-${TS_D}/data"
echo precious > "$ROOT_D1/NEIGHBOUR-${MODEL_C}-${TS_D}/data/canary"
OUT_D1="$(run_dogfood "$ROOT_D1" "$ROOT_D1/product" 'x/../../NEIGHBOUR' "$TS_D" "$MODEL_C")"; RC_D1=$?
[ -f "$ROOT_D1/NEIGHBOUR-${MODEL_C}-${TS_D}/data/canary" ] \
  && ok "D1a: traversal label destroyed NOTHING (unprotected sibling survived)" \
  || bad "D1a: a traversal ticket label rm -rf'd an unprotected sibling tree"
# D1b/D1c are deliberately sharper than "rc != 0 / some REFUSING line": with the label check
# deleted the CONTAINMENT block still stops the rm -rf (defence in depth) and the run still exits
# non-zero for an incidental reason, so a loose assertion would pass vacuously on the revert.
# These two isolate the label check by asserting the run dies BEFORE any candidate starts.
case "$OUT_D1" in
  *"=== candidate:"*) bad "D1b: the run reached a candidate — the unsafe label was not refused up front" ;;
  *) ok "D1b: refused BEFORE any candidate ran (rejected at the argv check, not downstream)" ;;
esac
case "$OUT_D1" in
  *"unsafe ticket label"*) ok "D1c: the refusal names the unsafe label" ;;
  *) bad "D1c: no unsafe-ticket-label refusal: $OUT_D1" ;;
esac
# D1d: $TICKET_LABEL is ALSO interpolated into $SUMMARY_FILE, so a traversal label escapes
# $RESULTS_DIR too — a hole the worktree-containment block does NOT cover.
[ -e "$ROOT_D1/NEIGHBOUR-${TS_D}-SUMMARY.md" ] \
  && bad "D1d: a traversal label wrote a SUMMARY file OUTSIDE \$RESULTS_DIR" \
  || ok "D1d: no summary file escaped \$RESULTS_DIR"
[ "$RC_D1" -ne 0 ] \
  && ok "D1e: traversal label exits NON-ZERO (caller can see the refusal)" \
  || bad "D1e: traversal label was accepted silently (rc=$RC_D1)"

# D2: repo_valid_id is the SSOT doing the rejecting — asserted against the real function, so a
# future rewrite that hand-rolls a weaker second validator here is visible.
# REVERT LINE: fleet/repo-registry.sh — delete the `*/*) return 1` / `*..*) return 1` arms of
# repo_valid_id. Reverted, D2a goes RED (the label is called valid) AND D1 goes RED with it.
ROOT_D2="$(mktemp -d)"   # own temp root even though this case is pure-function
( set -e; . "$FLEET_DIR/repo-registry.sh"
  repo_valid_id 'x/../../NEIGHBOUR' && exit 1 || exit 0 ) >/dev/null 2>&1 \
  && ok "D2a: repo_valid_id REJECTS the traversal label" \
  || bad "D2a: repo_valid_id ACCEPTS 'x/../../NEIGHBOUR'"
# ANTI-OVER-BLOCK: every label the real sweep (fleet/benchmark/honest-battery-sweep.sh) passes.
D2_BAD=""
for lbl in SECRET-HOTROTATE PROVIDER-URL-HELPER RFL-3 W0B-HARDEN v1.2.3; do
  ( . "$FLEET_DIR/repo-registry.sh"; repo_valid_id "$lbl" ) >/dev/null 2>&1 || D2_BAD="$D2_BAD $lbl"
done
[ -z "$D2_BAD" ] \
  && ok "D2b: every REAL sweep ticket label is still accepted (validator does not over-block)" \
  || bad "D2b: repo_valid_id rejects legitimate real labels:$D2_BAD"

# D3 (POSITIVE, and the case that makes the `realpath -m` branch LOAD-BEARING — MED-2):
# $wt does not exist yet when the guard runs, so `cd`+pwd -P always fails and `realpath -m` is
# the branch that resolves it. Here $WORKTREE_PARENT is reached through a SYMLINK, so the
# normalised target ($root/real-parent/charon-fleet-...) only tests as contained because
# realpath -m resolved it; an un-normalised path fails the ancestry test.
# REVERT LINE: fleet/benchmark/dogfood-eval.sh — delete the `|| dg_real="$(realpath -m "$wt"
# 2>/dev/null)"` arm (leaving `|| dg_real=""` per LOW-4). Reverted, dg_real is empty, the
# containment test refuses, no worktree is created => D3a goes RED for its own reason.
ROOT_D3="$(mk_dogfood_root)"; mk_fake_run "$ROOT_D3"
mk_repo "$ROOT_D3/product"
mkdir -p "$ROOT_D3/real-parent"
ln -s "$ROOT_D3/real-parent" "$ROOT_D3/wtp"
OUT_D3="$(run_dogfood "$ROOT_D3" "$ROOT_D3/product" LEGIT "$TS_D" "$MODEL_C")"
[ -d "$ROOT_D3/real-parent/charon-fleet-dogfood-LEGIT-${MODEL_C}-${TS_D}" ] \
  && ok "D3a: a legitimate (symlinked-parent) target is normalised and ALLOWED" \
  || bad "D3a: a legitimate target was refused — guard over-blocks: $OUT_D3"
case "$OUT_D3" in
  *"escapes the worktree parent"*) bad "D3b: a contained target was wrongly called an escape" ;;
  *) ok "D3b: no false escape report for a legitimate target" ;;
esac

# D4 (LOW-5): DOGFOOD_TS inherited from the environment must NOT pin a PRODUCTION run's stamp.
# Left ungated, a stray exported DOGFOOD_TS collides every real run onto one worktree/SUMMARY path.
# REVERT LINE: fleet/benchmark/dogfood-eval.sh — replace the DOGFOOD_TEST_MODE-gated block with
# the old `TS="${DOGFOOD_TS:-$(date -u +%Y%m%dT%H%M%SZ)}"`. Reverted, the production run below
# lands on the pinned stamp and D4a goes RED for its own reason.
ROOT_D4="$(mk_dogfood_root)"; mk_fake_run "$ROOT_D4"
mk_repo "$ROOT_D4/product"
mkdir -p "$ROOT_D4/results"; echo brief > "$ROOT_D4/brief.md"
# NOTE: DOGFOOD_TEST_MODE deliberately NOT set — this is a production-mode invocation.
OUT_D4="$(DOGFOOD_TS=19990101T000000Z \
  DOGFOOD_PRODUCT_REPO="$ROOT_D4/product" DOGFOOD_BASE_REF=master \
  DOGFOOD_WORKTREE_PARENT="$ROOT_D4/wtp" DOGFOOD_RESULTS_DIR="$ROOT_D4/results" \
  DOGFOOD_GATE_CMD=true DOGFOOD_TEST_CMD=true \
  DOGFOOD_CHARON_RUN="$ROOT_D4/fake-charon-run.sh" DOGFOOD_KEEP_WORKTREE=1 \
  bash "$DOGFOOD" PRODMODE "$ROOT_D4/brief.md" "$MODEL_C" 2>&1)"
[ -d "$ROOT_D4/wtp/charon-fleet-dogfood-PRODMODE-${MODEL_C}-19990101T000000Z" ] \
  && bad "D4a: an inherited DOGFOOD_TS PINNED a production run's stamp" \
  || ok "D4a: an inherited DOGFOOD_TS does NOT affect a production run"
[ -f "$ROOT_D4/results/PRODMODE-19990101T000000Z-SUMMARY.md" ] \
  && bad "D4b: an inherited DOGFOOD_TS pinned the production SUMMARY path (cross-run collision)" \
  || ok "D4b: the production SUMMARY path is not pinned by an inherited DOGFOOD_TS"
case "$OUT_D4" in
  *"IGNORING DOGFOOD_TS"*) ok "D4c: the ignored test hook is reported, not silently dropped" ;;
  *) bad "D4c: no IGNORING DOGFOOD_TS notice: $OUT_D4" ;;
esac
# D4d: the hook still WORKS when explicitly opted in — otherwise C1/C2/D1/D3 above would be
# testing nothing. Own temp root; asserts the pinned path really is used under the marker.
ROOT_D4B="$(mk_dogfood_root)"; mk_fake_run "$ROOT_D4B"
mk_repo "$ROOT_D4B/product"
run_dogfood "$ROOT_D4B" "$ROOT_D4B/product" HOOKON "$TS_D" "$MODEL_C" >/dev/null 2>&1
[ -d "$ROOT_D4B/wtp/charon-fleet-dogfood-HOOKON-${MODEL_C}-${TS_D}" ] \
  && ok "D4d: DOGFOOD_TEST_MODE=1 still honours DOGFOOD_TS (the hook is not dead)" \
  || bad "D4d: the pinned-stamp test hook no longer works under DOGFOOD_TEST_MODE=1"

# D5: the CONTAINMENT assertion's OWN fail-on-revert case.
# With repo_valid_id guarding $TICKET_LABEL, a label can no longer walk the target out of
# $WORKTREE_PARENT — so containment needs an escape the label validator CANNOT see. A planted or
# stale SYMLINK sitting where the worktree would go is exactly that: $wt is lexically under
# $WORKTREE_PARENT, `cd`+pwd -P succeeds and resolves it OUTSIDE, and the target is a plain
# unprotected dir, so _lg_wt_catastrophic has no reason of its own to refuse. Only containment
# stands between it and the `rm -rf`/`worktree remove --force` at run_one.
# REVERT LINE: fleet/benchmark/dogfood-eval.sh — delete the
# `if ! _lg_path_contains "$WORKTREE_PARENT_REAL" "$dg_real"; then ... return; fi` block.
# Reverted, the escape is no longer detected and D5b goes RED for its own reason. D5b — NOT
# D5a — is this block's fail-on-revert assertion: `rm -rf` on a SYMLINK unlinks the link and
# leaves the tree behind, so the canary survives either way. D5a is kept as a plain safety
# canary (it would catch a future change that followed the link before removing).
ROOT_D5="$(mk_dogfood_root)"; mk_fake_run "$ROOT_D5"
mk_repo "$ROOT_D5/product"
mkdir -p "$ROOT_D5/wtp" "$ROOT_D5/outside/data"
echo precious > "$ROOT_D5/outside/data/canary"
ln -s "$ROOT_D5/outside" "$ROOT_D5/wtp/charon-fleet-dogfood-ESC-${MODEL_C}-${TS_D}"
OUT_D5="$(run_dogfood "$ROOT_D5" "$ROOT_D5/product" ESC "$TS_D" "$MODEL_C")"
[ -f "$ROOT_D5/outside/data/canary" ] \
  && ok "D5a: a symlink escaping \$WORKTREE_PARENT destroyed NOTHING outside it" \
  || bad "D5a: a symlinked worktree target escaped \$WORKTREE_PARENT and was DESTROYED"
case "$OUT_D5" in
  *"escapes the worktree parent"*) ok "D5b: the escape was reported with its own reason" ;;
  *) bad "D5b: no containment-escape report: $OUT_D5" ;;
esac

echo
echo "w0b-harden: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
