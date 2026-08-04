#!/usr/bin/env bash
# generate.sh — collect the rig's + product's REAL current state and render ONE self-contained
# static HTML snapshot (fleet/status-board/board.html) that a NON-CODER can read.
#
# ⛔ THE HONESTY RULE — the whole reason this file exists (STATUS-BOARD-V1 / D-011) ⛔
#   THREE states for anything this page JUDGES, never two:
#     GREEN     checked AND passing.
#     RED       checked AND failing.
#     UNPROVEN  we cannot claim it. Either the check would not run, or nothing has ever
#               demonstrated the check is CAPABLE of failing — so "it passed" is worthless.
#   A gate whose red-proof suite has never executed in CI renders UNPROVEN, NOT green.
#   This project has shipped that lie: 114 red-proof suites absent from the LITERAL CI_SUITES
#   allowlist in fleet/checks/rig-ci-scope.sh (a suite absent from that array has NEVER run), and
#   a PASSING check reported as RED for weeks. A page that renders everything green is worse than
#   no page, because the operator would believe it.
#
#   MECHANIZED, not remembered — the two rules are one function each and there is no third path:
#     _verdict()        rc!=0 -> RED (failure was DIRECTLY OBSERVED, so it is always claimable).
#                       rc==0 -> GREEN *only* if the proof is CI-enforced or the tile is a DIRECT
#                       read of a primary field. Otherwise UNPROVEN. Fail-closed.
#     _run()            a source that could not RUN AT ALL (missing, non-executable, timed out,
#                       silent) never yields a verdict — it yields UNPROVEN with the reason.
#   Neither function can return GREEN by default. There is no code path where an unknown becomes
#   a pass, which is the single defect this whole ticket exists to prevent.
#
# A FOURTH CHIP, DELIBERATELY NOT A FOURTH VERDICT: some numbers are pure INVENTORY (how many
# tickets exist, how big the code map is). They have no pass/fail line, so forcing them into a
# verdict would either fake a green or dilute UNPROVEN. They render in a separate band labelled
# COUNTED, which makes NO health claim at all. No JUDGED tile may ever be COUNTED, and COUNTED is
# never coloured green. The judged band still carries exactly the three states above.
#
# WHY A GENERATED STATIC PAGE (settled in the ticket, do not re-litigate): n8n is workflow
# automation, not a dashboard; monit owns PROCESS LIVENESS and is already wired from
# fleet/state/service-registry.tsv (this page READS its verdict, it does not replace it); Grafana
# is the right LATER upgrade but costs a server to keep alive, and keeping services alive is
# precisely what keeps failing here. A static page has zero runtime, no auth, nothing to keep up,
# and is versioned in git.
#
# NOT REALTIME. Every tile is stamped once, at generation time. The page says SNAPSHOT in the
# header, prints the generation timestamp and both repo HEAD shas, and never implies live data.
#
# SEAMS (why every source is env-overridable): the companion suite fleet/tests/status-board.test.sh
# must be HERMETIC, OFFLINE and FAST to be allowed into CI_SUITES, and it must drive a
# DELIBERATELY BROKEN source to prove the UNPROVEN path is real. Every override DEFAULTS to the
# real production source and is consumed by the SAME _run/_verdict code the production run uses —
# so the test exercises the production path, not a fixture bypass
# (cf. fleet/checks/fixture-bypass.sh, and the SW_PR_FIXTURE precedent in stranded-work.sh).
#
# REUSE — this file collects and renders. It re-implements NO detector:
#   product gate      charon.cli gate                       (product repo owns it)
#   board gate        fleet/validate_board.sh               (rig board correctness)
#   gate liveness     fleet/checks/gate-integrity.sh scan    (G3 UNPROVEN / G5 UNENFORCED-PROOF)
#   CI allowlist      fleet/checks/rig-ci-scope.sh suites    (the literal CI_SUITES array)
#   work loss         fleet/checks/stranded-work.sh          (8 shapes, report-only)
#   code-map freshness fleet/checks/graphify-freshness.sh summary
#   service liveness  fleet/watchdog/discover-services.sh    (monit's own view)
#   gateway auth+url  fleet/env-registry.sh (SOURCED for bearer_token/$GATEWAY_URL — that file is
#                     explicitly sourceable and is the SSOT for both; do not duplicate them here)
#
# Usage:  bash fleet/status-board/generate.sh [--out <path>]
# Exit:   0 = a page was written (even if every tile is RED — reporting bad news is success).
#         1 = no page could be written (that is the only failure mode of a reporter).
#         2 = usage.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${SB_RIG_REPO:-$(cd "$HERE/../.." && pwd)}"
PRODUCT="${SB_PRODUCT_REPO:-/home/stack/code/charon}"
OUT="${SB_OUT:-$HERE/board.html}"

case "${1:-}" in
  --out) [ -n "${2:-}" ] || { echo "usage: generate.sh [--out <path>]" >&2; exit 2; }; OUT="$2" ;;
  "") : ;;
  *) echo "usage: generate.sh [--out <path>]" >&2; exit 2 ;;
esac

# ---- source commands (all overridable; all default to the REAL thing) ------------------------
SB_TIMEOUT="${SB_TIMEOUT:-600}"
SB_PRODUCT_GATE_CMD="${SB_PRODUCT_GATE_CMD:-cd '$PRODUCT' && PYTHONPATH='$PRODUCT/src' python3 -m charon.cli gate}"
SB_RIG_GATE_CMD="${SB_RIG_GATE_CMD:-bash '$ROOT/fleet/validate_board.sh' '$ROOT/fleet'}"
SB_GATE_INTEGRITY_CMD="${SB_GATE_INTEGRITY_CMD:-bash '$ROOT/fleet/checks/gate-integrity.sh' scan}"
SB_CI_SUITES_CMD="${SB_CI_SUITES_CMD:-bash '$ROOT/fleet/checks/rig-ci-scope.sh' suites}"
SB_STRANDED_CMD="${SB_STRANDED_CMD:-bash '$ROOT/fleet/checks/stranded-work.sh'}"
SB_FRESHNESS_CMD="${SB_FRESHNESS_CMD:-bash '$ROOT/fleet/checks/graphify-freshness.sh' summary}"
SB_LIVENESS_CMD="${SB_LIVENESS_CMD:-bash '$ROOT/fleet/watchdog/discover-services.sh'}"
SB_BOARD_DIR="${SB_BOARD_DIR:-$ROOT/fleet/board}"
SB_TESTS_DIR="${SB_TESTS_DIR:-$ROOT/fleet/tests}"
SB_REGISTRY_TSV="${SB_REGISTRY_TSV:-$ROOT/fleet/state/service-registry.tsv}"
SB_GRAPH_JSON="${SB_GRAPH_JSON:-$PRODUCT/graphify-out/graph.json}"
SB_ENV_REGISTRY="${SB_ENV_REGISTRY:-$ROOT/fleet/env-registry.sh}"
SB_GATEWAY_TIMEOUT="${SB_GATEWAY_TIMEOUT:-25}"
# Offline hooks for the two NETWORK sources. Set -> the file is read and no request is made.
SB_PR_FIXTURE="${SB_PR_FIXTURE:-}"                 # TSV: repo<TAB>number<TAB>draft<TAB>sha<TAB>conclusions
SB_GATEWAY_STATUS_JSON="${SB_GATEWAY_STATUS_JSON:-}"
SB_GATEWAY_CONFIG_JSON="${SB_GATEWAY_CONFIG_JSON:-}"

WORK="$(mktemp -d 2>/dev/null)" || { echo "generate.sh: RED cannot mktemp -d" >&2; exit 1; }
trap 'rm -rf "$WORK" 2>/dev/null || true' EXIT
TILES="$WORK/tiles.rec"; : >"$TILES"
US=$'\037'
RUNI=0

# ---- record emit ----------------------------------------------------------------------------
# Values are sanitised of the record separators only; NOTHING is reworded or rounded.
_sane(){ printf '%s' "${1-}" | tr -d '\037' | tr '\n\t' '  ' | sed 's/  */ /g; s/^ //; s/ $//'; }
# _emit <section> <state> <big> <label> <expect> <detail> <source> <proof> <reason>
_emit(){
  printf '%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s\n' \
    "$(_sane "$1")" "$US" "$(_sane "$2")" "$US" "$(_sane "$3")" "$US" "$(_sane "$4")" "$US" \
    "$(_sane "$5")" "$US" "$(_sane "$6")" "$US" "$(_sane "$7")" "$US" "$(_sane "$8")" "$US" \
    "$(_sane "$9")" >>"$TILES"
}

# ---- _run: the ONLY way a source is invoked -------------------------------------------------
# Sets RUN_OUT (file with combined output), RUN_RC, RUN_ERR. Returns non-zero when the source
# COULD NOT RUN — which is categorically different from "the check ran and failed" and must never
# be allowed to become a verdict in either direction.
_run(){
  local tmo="$1" cmd="$2"
  RUNI=$((RUNI+1)); RUN_OUT="$WORK/out.$RUNI"; RUN_RC=0; RUN_ERR=""
  timeout "$tmo" bash -c "$cmd" >"$RUN_OUT" 2>&1
  RUN_RC=$?
  case "$RUN_RC" in
    124|137) RUN_ERR="the source did not finish within ${tmo}s, so nothing was measured" ;;
    126)     RUN_ERR="the source exists but could not be executed (permissions)" ;;
    127)     RUN_ERR="the source program or file was not found: $(head -1 "$RUN_OUT" 2>/dev/null)" ;;
  esac
  [ -z "$RUN_ERR" ] || return 1
  if [ ! -s "$RUN_OUT" ]; then RUN_ERR="the source ran but printed nothing, so there is no measurement to report"; return 1; fi
  return 0
}

# ---- proof enforcement ----------------------------------------------------------------------
# The literal CI_SUITES allowlist. If it cannot be read, EVERY proof lookup is unknown and every
# passing check therefore renders UNPROVEN. Fail-closed by construction.
CI_SUITES_FILE="$WORK/ci-suites.txt"; CI_SUITES_OK=0; CI_SUITES_ERR=""
if _run 60 "$SB_CI_SUITES_CMD"; then cp "$RUN_OUT" "$CI_SUITES_FILE"; CI_SUITES_OK=1; else CI_SUITES_ERR="$RUN_ERR"; fi

# _proof <suite-basename> -> prints a human sentence; returns 0 if the proof is ENFORCED in CI.
_proof(){
  local s="$1"
  if [ "$CI_SUITES_OK" -ne 1 ]; then
    printf 'proof status UNKNOWN — the CI_SUITES allowlist itself could not be read'; return 1
  fi
  if [ ! -f "$SB_TESTS_DIR/$s" ]; then
    printf 'NO red-proof suite exists (%s is absent), so nothing has shown this check can fail' "$s"; return 1
  fi
  if grep -qw -- "$s" "$CI_SUITES_FILE"; then
    printf 'red-proof %s IS in the CI_SUITES allowlist — it runs on every PR' "$s"; return 0
  fi
  printf 'red-proof %s exists but is NOT in the CI_SUITES allowlist, so it has never executed in CI' "$s"
  return 1
}
# _proof_direct: the tile is a direct read of a primary field (an API flag, a file count) — there
# is no gate logic that could be silently inert, so a pass is claimable.
_proof_direct(){ printf 'DIRECT read of a primary field — there is no gate logic here that could be inert'; return 0; }

# _verdict <rc> <proof-enforced-rc> -> GREEN | RED | UNPROVEN
_verdict(){
  if [ "$1" -ne 0 ]; then echo RED; return; fi
  if [ "$2" -eq 0 ]; then echo GREEN; else echo UNPROVEN; fi
}

# _num <sed-ERE with ONE capture group> <file> -> prints that number, or returns 1.
# NEVER prints 0 on a miss — a missing measurement must reach the caller as a refusal, because a
# defaulted 0 is indistinguishable from a real "zero problems" and is therefore a green lie.
#
# THE CAPTURE GROUP IS LOAD-BEARING, MEASURED THE HARD WAY. The first version of this helper did
# `grep -oE <pattern> | grep -oE '[0-9]+' | head -1` — take the matching line, then the first
# number in it. On the real output that read "G5 UNENFORCED-PROOF: 114 suites" and reported
# **5**, because the first digits in the match belong to the token G5. It rendered a catastrophic
# 114 as a nearly-fine 5 on the operator's page. Positional capture, never first-digits-found.
_num(){
  local v
  v="$(sed -nE "s/$1/\1/p" "$2" 2>/dev/null | head -1)"
  [ -n "$v" ] || return 1
  case "$v" in *[!0-9]*|"") return 1 ;; esac
  printf '%s' "$v"
}

# =============================================================================================
# SECTION 1 — CAN WE SHIP?
# =============================================================================================
sec="Can we ship what we have?"

# product gate ---------------------------------------------------------------------------------
if _run "$SB_TIMEOUT" "$SB_PRODUCT_GATE_CMD"; then
  ok="$(grep -cE '^[[:space:]]*\[[a-z0-9_-]+\] OK$' "$RUN_OUT" 2>/dev/null || echo 0)"
  nok="$(grep -cE '^[[:space:]]*\[[a-z0-9_-]+\][[:space:]]*$' "$RUN_OUT" 2>/dev/null || echo 0)"
  tot=$((ok+nok))
  bad="$(grep -E '^[[:space:]]*\[[a-z0-9_-]+\][[:space:]]*$' "$RUN_OUT" | sed -E 's/^[[:space:]]*\[([a-z0-9_-]+)\].*/\1/' | paste -sd', ' -)"
  if [ "$tot" -eq 0 ]; then
    _emit "$sec" UNPROVEN "—" "Quality checks failing on the product" "Healthy would be: 0" \
      "The gate ran but printed no recognisable check lines, so no check result could be read out of it." \
      "python3 -m charon.cli gate" "n/a" \
      "the product gate's output did not contain any '[check] result' lines to count"
  else
    # The product gate's own red-proofs (tests/test_gate_runner_fail_closed.py,
    # tests/test_gate_registry_execution.py) live in the PRODUCT repo and are enforced by the
    # PRODUCT repo's CI, which this page does not inspect. So a PASS here is UNPROVEN from where
    # this page stands, and it says so rather than assuming.
    prc=1; pmsg="the product gate's red-proofs (tests/test_gate_runner_fail_closed.py, tests/test_gate_registry_execution.py) live in the product repo; this page does not verify that the product CI executed them, so a pass could not be claimed"
    st="$(_verdict "$RUN_RC" "$prc")"
    _emit "$sec" "$st" "$nok of $tot" "Quality checks failing on the product" "Healthy would be: 0 of $tot" \
      "$( [ "$RUN_RC" -ne 0 ] && printf 'Failing right now: %s. ' "${bad:-unnamed}" )The product's own gate runs $tot separate checks (code style, types, security scan, dead code and more) before anything ships." \
      "python3 -m charon.cli gate (in $PRODUCT)" "$pmsg" \
      "$( [ "$st" = UNPROVEN ] && printf '%s' "$pmsg" )"
  fi
else
  _emit "$sec" UNPROVEN "—" "Quality checks failing on the product" "Healthy would be: 0" \
    "We cannot say whether the product is healthy, because its gate did not run." \
    "python3 -m charon.cli gate (in $PRODUCT)" "n/a" "$RUN_ERR"
fi

# rig board gate -------------------------------------------------------------------------------
if _run "$SB_TIMEOUT" "$SB_RIG_GATE_CMD"; then
  n="$(_num '.*RED[[:space:]]+([0-9]+) issue.*' "$RUN_OUT")" || n="$(grep -cE '^[[:space:]]*RED[[:space:]]' "$RUN_OUT" 2>/dev/null)"
  pmsg="$(_proof board-correctness.test.sh)"; prc=$?
  st="$(_verdict "$RUN_RC" "$prc")"
  # n="" cannot happen via the grep -c fallback (it prints 0), but rc!=0 with n=0 CAN: the
  # validator failed while naming nothing. Reporting "0 problems / FAILING" side by side would be
  # incoherent, and reporting 0 alone would be the defaulted-zero lie. Refuse instead.
  if [ -z "$n" ] || { [ "$RUN_RC" -ne 0 ] && [ "$n" -eq 0 ]; }; then
    _emit "$sec" UNPROVEN "—" "Problems in the plan of work" "Healthy would be: 0" \
      "The board checker ran but its result could not be read, so no number is claimed." \
      "fleet/validate_board.sh fleet" "$pmsg" \
      "the validator exited non-zero but printed no parsable 'N issue(s)' summary and named no RED lines, so the number of problems is unknown"
  else
    _emit "$sec" "$st" "$n" "Problems in the plan of work" "Healthy would be: 0" \
      "The board is the list of everything being worked on. These are contradictions inside it — two jobs claiming the same file, a job that would be refused the moment someone tried to start it, and similar." \
      "fleet/validate_board.sh fleet" "$pmsg" "$( [ "$st" = UNPROVEN ] && printf '%s' "$pmsg" )"
  fi
else
  _emit "$sec" UNPROVEN "—" "Problems in the plan of work" "Healthy would be: 0" \
    "We cannot say whether the plan of work is self-consistent, because its checker did not run." \
    "fleet/validate_board.sh fleet" "n/a" "$RUN_ERR"
fi

# =============================================================================================
# SECTION 2 — ARE OUR SAFETY NETS REAL?
# =============================================================================================
sec="Are the safety nets real?"

if _run "$SB_TIMEOUT" "$SB_GATE_INTEGRITY_CMD"; then
  GI_OUT="$WORK/gi.txt"; cp "$RUN_OUT" "$GI_OUT"
  pmsg="$(_proof gate-integrity.test.sh)"; prc=$?

  g5="$(_num '.*G5 UNENFORCED-PROOF: ([0-9]+) suites.*' "$GI_OUT")" || g5=""
  if [ -n "$g5" ]; then
    st=RED; [ "$g5" -eq 0 ] && st="$(_verdict 0 "$prc")"
    _emit "$sec" "$st" "$g5" "Safety tests that have never actually run" "Healthy would be: 0" \
      "Each of these is a test written specifically to catch a known way things break — and not one of them is on the list of tests the robot actually runs before merging. They read as protection and provide none. This is the exact lie this page exists to stop." \
      "fleet/checks/gate-integrity.sh scan (G5)" "$pmsg" ""
  else
    _emit "$sec" UNPROVEN "—" "Safety tests that have never actually run" "Healthy would be: 0" \
      "The gate-on-the-gates ran but its G5 total could not be read." \
      "fleet/checks/gate-integrity.sh scan (G5)" "$pmsg" "no 'G5 UNENFORCED-PROOF: N suites' line was found in the output"
  fi

  g3="$(grep -cE 'G3 UNPROVEN' "$GI_OUT" 2>/dev/null)"
  st=RED; [ "${g3:-0}" -eq 0 ] && st="$(_verdict 0 "$prc")"
  _emit "$sec" "$st" "${g3:-0}" "Guards with no working proof they catch anything" "Healthy would be: 0" \
    "A guard here either has no test at all, or has one that never runs. Nobody has ever demonstrated it is capable of noticing the thing it is supposed to notice." \
    "fleet/checks/gate-integrity.sh scan (G3)" "$pmsg" ""

  gt="$(_num '^gate-integrity: ([0-9]+) finding.*' "$GI_OUT")" || gt=""
  if [ -n "$gt" ]; then
    st=RED; [ "$gt" -eq 0 ] && st="$(_verdict 0 "$prc")"
    _emit "$sec" "$st" "$gt" "Total defects found in our own safety machinery" "Healthy would be: 0" \
      "Everything the gate-on-the-gates found: guards nothing calls, guards whose own comments claim wiring they do not have, and acknowledged gaps with nothing behind them." \
      "fleet/checks/gate-integrity.sh scan" "$pmsg" ""
  fi
else
  for lbl in "Safety tests that have never actually run" "Guards with no working proof they catch anything" "Total defects found in our own safety machinery"; do
    _emit "$sec" UNPROVEN "—" "$lbl" "Healthy would be: 0" \
      "We cannot say anything about the state of our safety machinery, because the check on it did not run." \
      "fleet/checks/gate-integrity.sh scan" "n/a" "$RUN_ERR"
  done
fi

# CI coverage ---------------------------------------------------------------------------------
if [ "$CI_SUITES_OK" -eq 1 ] && [ -d "$SB_TESTS_DIR" ]; then
  run_n="$(grep -cE '\.sh$' "$CI_SUITES_FILE" 2>/dev/null)"
  all_n="$(find "$SB_TESTS_DIR" -maxdepth 1 -name '*.test.sh' 2>/dev/null | wc -l | tr -d ' ')"
  pmsg="$(_proof_direct)"; prc=$?
  if [ "${all_n:-0}" -eq 0 ] || [ "${run_n:-0}" -eq 0 ]; then
    _emit "$sec" UNPROVEN "—" "Tests the robot actually runs before merging" "Healthy would be: all of them" \
      "The counts could not be established." "fleet/checks/rig-ci-scope.sh suites vs fleet/tests/*.test.sh" "$pmsg" \
      "one of the two counts came back zero, which is a measurement failure rather than a real value"
  else
    st=RED; [ "$run_n" -ge "$all_n" ] && st="$(_verdict 0 "$prc")"
    _emit "$sec" "$st" "$run_n of $all_n" "Tests the robot actually runs before merging" "Healthy would be: $all_n of $all_n" \
      "The list of tests run before merging is an ALLOWLIST typed out by hand. Any test file not named in it is skipped by default and silently never runs, no matter what it claims to defend." \
      "fleet/checks/rig-ci-scope.sh suites vs fleet/tests/*.test.sh" "$pmsg" ""
  fi
else
  _emit "$sec" UNPROVEN "—" "Tests the robot actually runs before merging" "Healthy would be: all of them" \
    "We cannot say how much of our test suite actually runs." "fleet/checks/rig-ci-scope.sh suites" "n/a" \
    "${CI_SUITES_ERR:-the tests directory $SB_TESTS_DIR could not be read}"
fi

# code map freshness ---------------------------------------------------------------------------
# THE SHOWCASE OF THE RULE: this check PASSES today. Its red-proof suite exists and is NOT in the
# CI_SUITES allowlist, so nothing has ever shown it capable of failing -> UNPROVEN, not green.
if _run 180 "$SB_FRESHNESS_CMD"; then
  stale="$(grep -cE '\|[[:space:]]*(STALE|MISSING)' "$RUN_OUT" 2>/dev/null)"
  fresh="$(grep -cE '\|[[:space:]]*FRESH' "$RUN_OUT" 2>/dev/null)"
  pmsg="$(_proof graphify-freshness.test.sh)"; prc=$?
  if [ "$((stale+fresh))" -eq 0 ]; then
    _emit "$sec" UNPROVEN "—" "Code maps that have fallen out of date" "Healthy would be: 0" \
      "The freshness reporter ran but reported on no repository." "fleet/checks/graphify-freshness.sh summary" "$pmsg" \
      "the summary listed neither a FRESH nor a STALE repository, so there is nothing to report"
  else
    st="$(_verdict "$stale" "$prc")"
    _emit "$sec" "$st" "$stale of $((stale+fresh))" "Code maps that have fallen out of date" "Healthy would be: 0" \
      "The code map is what lets us answer 'if we change this, what else breaks'. A stale map answers that question wrongly and confidently." \
      "fleet/checks/graphify-freshness.sh summary" "$pmsg" \
      "$( [ "$st" = UNPROVEN ] && printf 'the freshness check reports every code map as up to date, but %s — so "up to date" is a claim this page will not make' "$pmsg" )"
  fi
else
  _emit "$sec" UNPROVEN "—" "Code maps that have fallen out of date" "Healthy would be: 0" \
    "We cannot say whether the code map is current." "fleet/checks/graphify-freshness.sh summary" "n/a" "$RUN_ERR"
fi

# blast radius ---------------------------------------------------------------------------------
# Honest refusal. `graphify affected` exists and has ZERO call sites anywhere in the rig, so its
# output has never been calibrated here; and it needs a NAMED NODE, which a whole-repo snapshot
# has no defensible way to choose. Inventing one would be a number nobody could act on.
_emit "$sec" UNPROVEN "—" "If we change something, what else breaks?" "" \
  "This page does not answer this question. The tool that could (graphify affected) needs to be pointed at one specific thing, and a whole-system snapshot has no honest way to pick which one." \
  "graphify affected \"<node>\" --depth N" "no red-proof suite, and zero call sites anywhere in the rig" \
  "graphify affected requires a named starting point that a whole-repo snapshot cannot choose, and it has 0 call sites in this rig so its output has never been calibrated here"

# =============================================================================================
# SECTION 3 — IS WORK GETTING LOST?
# =============================================================================================
sec="Is finished work getting lost?"

if _run "$SB_TIMEOUT" "$SB_STRANDED_CMD"; then
  SW_OUT="$WORK/sw.txt"; cp "$RUN_OUT" "$SW_OUT"
  n="$(_num '^stranded-work: ([0-9]+) finding.*' "$SW_OUT")" || n=""
  pmsg="$(_proof stranded-work.test.sh)"; prc=$?
  grep -oE 'stranded-work: [0-9]+ x [a-z-]+' "$SW_OUT" 2>/dev/null | sed 's/^stranded-work: //' | sort -t' ' -k1,1nr >"$WORK/sw-shapes.txt" || true
  if [ -z "$n" ]; then
    _emit "$sec" UNPROVEN "—" "Pieces of unfinished work that could be lost" "Healthy would be: 0" \
      "The detector ran but its total could not be read, so no number is claimed." \
      "fleet/checks/stranded-work.sh" "$pmsg" "no 'N finding(s)' total line was found in the detector's output"
  else
    st=RED; [ "$n" -eq 0 ] && st="$(_verdict 0 "$prc")"
    _emit "$sec" "$st" "$n" "Pieces of unfinished work that could be lost" "Healthy would be: 0" \
      "Work that was done and then left somewhere it can quietly disappear: committed but never sent anywhere, sent but with nobody asked to merge it, or attached to a request that was closed without landing." \
      "fleet/checks/stranded-work.sh" "$pmsg" ""
  fi
else
  _emit "$sec" UNPROVEN "—" "Pieces of unfinished work that could be lost" "Healthy would be: 0" \
    "We cannot say whether work is being lost, because the detector did not run." \
    "fleet/checks/stranded-work.sh" "n/a" "$RUN_ERR"
fi

# pull requests --------------------------------------------------------------------------------
# REST + --jq only. `gh pr view`/`gh pr edit` are broken by Projects-classic on these repos, and
# the GraphQL quota is scarce [[gh-projects-classic-breaks-subcommands]].
PR_TSV="$WORK/prs.tsv"; PR_ERR=""
if [ -n "$SB_PR_FIXTURE" ]; then
  if [ -r "$SB_PR_FIXTURE" ]; then cp "$SB_PR_FIXTURE" "$PR_TSV"; else PR_ERR="the pull-request fixture $SB_PR_FIXTURE could not be read"; fi
else
  : >"$PR_TSV"
  if ! command -v gh >/dev/null 2>&1; then
    PR_ERR="the GitHub CLI (gh) is not installed, so open change-requests could not be listed"
  else
    for repo_dir in "$ROOT" "$PRODUCT"; do
      slug="$(git -C "$repo_dir" remote get-url origin 2>/dev/null | sed -E 's#^git@github\.com:##; s#^https://github\.com/##; s#\.git$##')"
      case "$slug" in ""|*/*) : ;; *) slug="" ;; esac
      [ -n "$slug" ] || { PR_ERR="could not work out the GitHub repository for $repo_dir"; continue; }
      list="$WORK/prlist.$$"
      if ! timeout 180 gh api "repos/$slug/pulls?state=open&per_page=100" --paginate \
             --jq '.[] | [.number, (.draft|tostring), .head.sha] | @tsv' >"$list" 2>/dev/null; then
        PR_ERR="the GitHub API call for $slug failed, so its change-requests are not counted"; continue
      fi
      while IFS=$'\t' read -r num draft sha; do
        [ -n "${sha:-}" ] || continue
        concl="$(timeout 60 gh api "repos/$slug/commits/$sha/check-runs" --jq '[.check_runs[]|.conclusion]|@csv' 2>/dev/null)"
        printf '%s\t%s\t%s\t%s\t%s\n' "$slug" "$num" "$draft" "$sha" "${concl:-NONE}" >>"$PR_TSV"
      done <"$list"
    done
  fi
fi

if [ -z "$PR_ERR" ] && [ -s "$PR_TSV" ]; then
  pr_all="$(wc -l <"$PR_TSV" | tr -d ' ')"
  pr_draft="$(awk -F'\t' '$3=="true"' "$PR_TSV" | wc -l | tr -d ' ')"
  pr_fail="$(awk -F'\t' '$5 ~ /failure|timed_out|cancelled/' "$PR_TSV" | wc -l | tr -d ' ')"
  pr_none="$(awk -F'\t' '$5=="NONE" || $5==""' "$PR_TSV" | wc -l | tr -d ' ')"
  pr_green="$((pr_all - pr_fail - pr_none))"
  pmsg="$(_proof_direct)"; prc=$?
  st=RED; [ "$((pr_draft*2))" -le "$pr_all" ] && st="$(_verdict 0 "$prc")"
  _emit "$sec" "$st" "$pr_draft of $pr_all" "Change-requests marked 'not ready', so nothing can merge them" "Healthy would be: fewer than half" \
    "A draft change-request is finished-looking work that no reviewer will pick up and no robot will merge. It sits there until someone remembers it." \
    "gh api repos/{owner}/{repo}/pulls?state=open (REST, --jq)" "$pmsg" ""
  st=RED; [ "$pr_fail" -eq 0 ] && st="$(_verdict 0 "$prc")"
  _emit "$sec" "$st" "$pr_fail of $pr_all" "Change-requests whose automatic checks are failing" "Healthy would be: 0" \
    "$pr_green of $pr_all are fully green. $pr_none have no automatic checks at all — those look mergeable with nothing whatsoever verified." \
    "gh api repos/{owner}/{repo}/commits/{sha}/check-runs (REST, --jq)" "$pmsg" ""
else
  for lbl in "Change-requests marked 'not ready', so nothing can merge them" "Change-requests whose automatic checks are failing"; do
    _emit "$sec" UNPROVEN "—" "$lbl" "" \
      "We cannot say anything about open change-requests." "gh api .../pulls (REST, --jq)" "n/a" \
      "${PR_ERR:-the pull-request query produced no rows at all, which is a measurement failure rather than 'no open change-requests'}"
  done
fi

# =============================================================================================
# SECTION 4 — IS THE MACHINE RUNNING?
# =============================================================================================
sec="Is the machine actually running?"

if _run 180 "$SB_LIVENESS_CMD"; then
  LV="$WORK/lv.txt"; cp "$RUN_OUT" "$LV"
  alive="$(grep -cE '^[[:space:]]*ok[[:space:]]+[a-z0-9-]+ — alive' "$LV" 2>/dev/null)"
  dead="$(grep -cE '^[[:space:]]*DEAD[[:space:]]' "$LV" 2>/dev/null)"
  pmsg="$(_proof service-watchdog.test.sh)"; prc=$?
  if ! grep -qE '^== watchdog:' "$LV"; then
    _emit "$sec" UNPROVEN "—" "Background services that are dead" "Healthy would be: 0" \
      "The watchdog ran but produced no verdict line." "fleet/watchdog/discover-services.sh" "$pmsg" \
      "the watchdog printed no '== watchdog: ...' verdict line, so its result could not be read"
  elif [ "$((alive+dead))" -eq 0 ]; then
    _emit "$sec" UNPROVEN "—" "Background services that are dead" "Healthy would be: 0" \
      "The watchdog reported on no service at all." "fleet/watchdog/discover-services.sh" "$pmsg" \
      "the watchdog listed zero services, so 'all alive' would be a vacuous pass"
  else
    st="$(_verdict "$dead" "$prc")"
    _emit "$sec" "$st" "$dead of $((alive+dead))" "Background services that are dead" "Healthy would be: 0" \
      "These are the always-on helpers (the message bridge, the tunnel to the coordinator, the gateway host, the canary). A dead one fails silently — that is how it stays dead." \
      "fleet/watchdog/discover-services.sh" "$pmsg" \
      "$( [ "$st" = UNPROVEN ] && printf '%s' "$pmsg" )"
  fi
else
  _emit "$sec" UNPROVEN "—" "Background services that are dead" "Healthy would be: 0" \
    "We cannot say which background services are alive." "fleet/watchdog/discover-services.sh" "n/a" "$RUN_ERR"
fi

# gateway (providers + pricing) -----------------------------------------------------------------
GW_S="$WORK/gw-status.json"; GW_C="$WORK/gw-config.json"; GW_ERR=""
if [ -n "$SB_GATEWAY_STATUS_JSON" ] || [ -n "$SB_GATEWAY_CONFIG_JSON" ]; then
  { [ -r "${SB_GATEWAY_STATUS_JSON:-}" ] && cp "$SB_GATEWAY_STATUS_JSON" "$GW_S"; } || GW_ERR="the supplied gateway status file could not be read"
  { [ -r "${SB_GATEWAY_CONFIG_JSON:-}" ] && cp "$SB_GATEWAY_CONFIG_JSON" "$GW_C"; } || GW_ERR="${GW_ERR:-the supplied gateway config file could not be read}"
elif [ ! -r "$SB_ENV_REGISTRY" ]; then
  GW_ERR="fleet/env-registry.sh is missing, so neither the gateway address nor its access token could be resolved"
else
  # env-registry.sh is explicitly SOURCEABLE (it returns 0 when sourced) and is the SSOT for BOTH
  # $GATEWAY_URL and bearer_token(). Neither is duplicated here. Note that the shell's
  # CHARON_GATEWAY_TOKEN is documented STALE in that file — the token MUST be re-derived, which is
  # exactly what bearer_token() does, so we ignore the ambient variable entirely.
  # Sourced inside a SUBSHELL: that file assigns FLEET/GATEWAY_URL/OUTPUT/... and must not be able
  # to reach into this script's state. Only the two values we asked for come back.
  GW_URL="$( . "$SB_ENV_REGISTRY" >/dev/null 2>&1 && printf '%s' "${GATEWAY_URL:-}" )"
  GW_TOK="$( . "$SB_ENV_REGISTRY" >/dev/null 2>&1 && bearer_token 2>/dev/null )"
  if [ -z "${GW_URL:-}" ]; then
    GW_ERR="fleet/env-registry.sh did not yield a gateway address, so the gateway could not be contacted"
  elif [ -z "${GW_TOK:-}" ]; then
    GW_ERR="no gateway access token could be derived from the opencode config, and the gateway refuses unauthenticated requests"
  else
    for ep in status config; do
      dst="$GW_S"; [ "$ep" = config ] && dst="$GW_C"
      code="$(timeout "$SB_GATEWAY_TIMEOUT" curl -s -m "$SB_GATEWAY_TIMEOUT" \
                -H "Authorization: Bearer $GW_TOK" -H 'Accept: application/json' \
                -o "$dst" -w '%{http_code}' "$GW_URL/charon/$ep" 2>/dev/null)"
      [ "$code" = "200" ] || GW_ERR="the gateway answered HTTP ${code:-none} for /charon/$ep$( [ "${code:-}" = 302 ] && printf ' (it redirected to a browser login instead of answering)' )"
    done
  fi
fi

GW_FACTS="$WORK/gw-facts.txt"; : >"$GW_FACTS"
if [ -z "$GW_ERR" ] && [ -s "$GW_S" ] && [ -s "$GW_C" ]; then
  python3 - "$GW_S" "$GW_C" >"$GW_FACTS" 2>/dev/null <<'PY'
import json, sys
try:
    st = json.load(open(sys.argv[1])); cf = json.load(open(sys.argv[2]))
except Exception as e:
    sys.exit(1)
bal = st.get("balance") or {}
if not isinstance(bal, dict) or not bal:
    sys.exit(1)
models = cf.get("models") or {}
unknown = cf.get("unknown_pricing")
if not isinstance(models, dict) or not models or not isinstance(unknown, list):
    sys.exit(1)
parked = sorted(k for k, v in bal.items() if isinstance(v, dict) and (v.get("parked") or v.get("drained")))
print("providers_total\t%d" % len(bal))
print("providers_parked\t%d" % len(parked))
print("parked_names\t%s" % ", ".join(parked))
print("models_total\t%d" % len(models))
print("models_unpriced\t%d" % len(unknown))
print("pools_total\t%d" % len(cf.get("pools") or {}))
print("build_sha\t%s" % (st.get("build_sha") or "unknown"))
PY
  [ -s "$GW_FACTS" ] || GW_ERR="the gateway answered, but its reply did not carry the provider funding and pricing fields this page reads"
fi
_gwf(){ awk -F'\t' -v k="$1" '$1==k{print $2}' "$GW_FACTS" 2>/dev/null; }

if [ -z "$GW_ERR" ] && [ -s "$GW_FACTS" ]; then
  pt="$(_gwf providers_total)"; pp="$(_gwf providers_parked)"; pn="$(_gwf parked_names)"
  mt="$(_gwf models_total)"; mu="$(_gwf models_unpriced)"
  pmsg="$(_proof_direct)"; prc=$?
  st=RED; [ "$pp" -eq 0 ] && st="$(_verdict 0 "$prc")"
  _emit "$sec" "$st" "$pp of $pt" "AI suppliers switched off (out of money or over their limit)" "Healthy would be: 0" \
    "A parked supplier is one the router is no longer allowed to use, so all its capacity is gone. Currently parked: ${pn:-none}." \
    "GET \$GATEWAY_URL/charon/status -> balance[].parked" "$pmsg" ""
  st=RED; [ "$mu" -eq 0 ] && st="$(_verdict 0 "$prc")"
  _emit "$sec" "$st" "$mu of $mt" "Models we cannot put a price on" "Healthy would be: 0" \
    "Every request to one of these is billed at a price the system does not know. Cheapest-first routing and every spend limit are guessing for these models." \
    "GET \$GATEWAY_URL/charon/config -> unknown_pricing" "$pmsg" ""
else
  for lbl in "AI suppliers switched off (out of money or over their limit)" "Models we cannot put a price on"; do
    _emit "$sec" UNPROVEN "—" "$lbl" "Healthy would be: 0" \
      "We cannot say anything about the live gateway's suppliers or pricing." \
      "GET \$GATEWAY_URL/charon/{status,config}" "n/a" "${GW_ERR:-the gateway reply could not be read}"
  done
fi

# =============================================================================================
# SECTION 5 — COUNTED, NOT JUDGED (inventory: no pass/fail line exists, so no verdict is given)
# =============================================================================================
sec="Counted, not judged"

if [ -d "$SB_BOARD_DIR" ]; then
  live_n="$(find "$SB_BOARD_DIR" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  park_n="$(find "$SB_BOARD_DIR" -maxdepth 1 -name '*.md.parked' 2>/dev/null | wc -l | tr -d ' ')"
  : >"$WORK/prio.txt"
  for p in 0 1 2 3; do
    c="$(grep -lE "^priority:[[:space:]]*$p([[:space:]]|$)" "$SB_BOARD_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')"
    printf 'P%s\t%s\n' "$p" "$c" >>"$WORK/prio.txt"
  done
  noprio="$(grep -LE '^priority:' "$SB_BOARD_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$live_n" -eq 0 ]; then
    _emit "$sec" UNPROVEN "—" "Jobs on the board right now" "" "The board directory holds no job files." \
      "fleet/board/*.md frontmatter" "n/a" "the board directory contains no *.md files, which is a measurement failure rather than 'no work'"
  else
    _emit "$sec" COUNTED "$live_n" "Jobs on the board right now" "" \
      "$(awk -F'\t' '{printf "%s: %s. ", $1, $2}' "$WORK/prio.txt")Plus $park_n staged but deliberately not started.$( [ "${noprio:-0}" -gt 0 ] && printf ' %s carry no priority field.' "$noprio" ) There is no right number of open jobs, so this page makes no health claim about it." \
      "fleet/board/*.md frontmatter (+ *.md.parked)" "counted directly from the files; no verdict is offered" ""
  fi
else
  _emit "$sec" UNPROVEN "—" "Jobs on the board right now" "" "The board could not be read." \
    "fleet/board/*.md" "n/a" "the board directory $SB_BOARD_DIR does not exist"
fi

if [ -r "$SB_GRAPH_JSON" ]; then
  GM="$WORK/graph.txt"
  python3 - "$SB_GRAPH_JSON" >"$GM" 2>/dev/null <<'PY'
import json, sys, collections
d = json.load(open(sys.argv[1]))
nodes = d.get("nodes"); links = d.get("links") or d.get("edges")
if not isinstance(nodes, list) or not nodes or not isinstance(links, list):
    sys.exit(1)
c = collections.Counter(n.get("community") for n in nodes if isinstance(n, dict))
print("nodes\t%d" % len(nodes))
print("links\t%d" % len(links))
print("clusters\t%d" % len([k for k in c if k is not None]))
print("top\t%s" % ", ".join("cluster %s (%d parts)" % (k, v) for k, v in c.most_common(3) if k is not None))
print("commit\t%s" % (d.get("built_at_commit") or "unknown"))
PY
  if [ -s "$GM" ]; then
    _emit "$sec" COUNTED "$(awk -F'\t' '$1=="nodes"{print $2}' "$GM")" "Distinct parts in the product's code map" "" \
      "Connected by $(awk -F'\t' '$1=="links"{print $2}' "$GM") relationships, grouped into $(awk -F'\t' '$1=="clusters"{print $2}' "$GM") clusters. Biggest: $(awk -F'\t' '$1=="top"{print $2}' "$GM"). Built at commit $(awk -F'\t' '$1=="commit"{print substr($2,1,12)}' "$GM")." \
      "graphify graph.json" "counted directly from the map file; no verdict is offered" ""
  else
    _emit "$sec" UNPROVEN "—" "Distinct parts in the product's code map" "" "The code map could not be read." \
      "graphify graph.json" "n/a" "$SB_GRAPH_JSON could not be parsed, or carried no nodes"
  fi
else
  _emit "$sec" UNPROVEN "—" "Distinct parts in the product's code map" "" "There is no code map to count." \
    "graphify graph.json" "n/a" "no graph.json at $SB_GRAPH_JSON — run 'graphify update' to build one"
fi

if [ -r "$SB_REGISTRY_TSV" ]; then
  reg_n="$(grep -vE '^[[:space:]]*(#|$)' "$SB_REGISTRY_TSV" 2>/dev/null | wc -l | tr -d ' ')"
  reg_names="$(grep -vE '^[[:space:]]*(#|$)' "$SB_REGISTRY_TSV" 2>/dev/null | cut -f1 | paste -sd', ' -)"
  _emit "$sec" COUNTED "$reg_n" "Services we have promised to keep alive" "" \
    "Declared in the registry the watchdog is generated from: ${reg_names:-none}. This is the promise; the dead-services tile above is the reality." \
    "fleet/state/service-registry.tsv" "counted directly from the registry file; no verdict is offered" ""
else
  _emit "$sec" UNPROVEN "—" "Services we have promised to keep alive" "" "The service registry could not be read." \
    "fleet/state/service-registry.tsv" "n/a" "no readable registry at $SB_REGISTRY_TSV"
fi

if [ -z "$GW_ERR" ] && [ -s "$GW_FACTS" ]; then
  _emit "$sec" COUNTED "$(_gwf models_total)" "Models the gateway can reach" "" \
    "Across $(_gwf providers_total) suppliers and $(_gwf pools_total) routing pools. Gateway build $(printf '%.12s' "$(_gwf build_sha)")." \
    "GET \$GATEWAY_URL/charon/config" "counted directly from the gateway's own reply; no verdict is offered" ""
fi

# =============================================================================================
# RENDER
# =============================================================================================
GEN_AT="$(date -u '+%Y-%m-%d %H:%M:%S UTC' 2>/dev/null)"; GEN_AT="${GEN_AT:-unknown}"
_headsha(){ git -C "$1" rev-parse --short=12 HEAD 2>/dev/null || printf 'UNPROVEN (not a readable git repo)'; }
_headbr(){ git -C "$1" rev-parse --abbrev-ref HEAD 2>/dev/null || printf '?'; }
RIG_SHA="$(_headsha "$ROOT")"; RIG_BR="$(_headbr "$ROOT")"
PRD_SHA="$(_headsha "$PRODUCT")"; PRD_BR="$(_headbr "$PRODUCT")"

mkdir -p "$(dirname "$OUT")" 2>/dev/null
TMP_OUT="$WORK/board.html"
if ! python3 - "$TILES" "$WORK/sw-shapes.txt" "$GEN_AT" \
        "$RIG_SHA" "$RIG_BR" "$PRD_SHA" "$PRD_BR" "$ROOT" "$PRODUCT" >"$TMP_OUT" <<'PY'
import html, sys, os

recs_f, shapes_f, gen_at, rig_sha, rig_br, prd_sha, prd_br, rig_root, prd_root = sys.argv[1:10]
US = "\x1f"
FIELDS = ("section", "state", "big", "label", "expect", "detail", "source", "proof", "reason")

tiles = []
with open(recs_f, encoding="utf-8", errors="replace") as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split(US)
        parts += [""] * (len(FIELDS) - len(parts))
        tiles.append(dict(zip(FIELDS, parts[:len(FIELDS)])))
if not tiles:
    sys.exit(1)

shapes = []
if os.path.exists(shapes_f):
    with open(shapes_f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if " x " in line:
                n, _, name = line.partition(" x ")
                shapes.append((n.strip(), name.strip()))

E = html.escape
CHIP = {
    "GREEN":    ("PASSING",  "&#10003;", "good"),
    "RED":      ("FAILING",  "&#10007;", "crit"),
    "UNPROVEN": ("UNPROVEN", "?",        "unk"),
    "COUNTED":  ("COUNTED",  "&#8226;",  "cnt"),
}
judged = [t for t in tiles if t["state"] in ("GREEN", "RED", "UNPROVEN")]
n_green = sum(1 for t in judged if t["state"] == "GREEN")
n_red = sum(1 for t in judged if t["state"] == "RED")
n_unp = sum(1 for t in judged if t["state"] == "UNPROVEN")
unproven = [t for t in tiles if t["state"] == "UNPROVEN"]

order, seen = [], set()
for t in tiles:
    if t["section"] not in seen:
        seen.add(t["section"]); order.append(t["section"])

# AN UNPROVEN TILE NEVER SHOWS A NUMBER AS ITS HEADLINE. The freshness check, for instance,
# measures "0 of 2 code maps are stale" — but nothing has ever shown that check capable of noticing
# a stale map, so a big grey "0" gets read by a non-coder as "zero problems". That is the green lie
# wearing grey. The headline becomes the word "unknown", and the figure the check produced is
# demoted into the reason, attributed to the check rather than claimed by this page.
def reason_of(t):
    r = t["reason"] or t["proof"] or "no reason was recorded, which is itself a defect in this page"
    if t["state"] == "UNPROVEN" and t["big"] and t["big"] not in ("\u2014", "-", ""):
        r = ("%s (the check itself reported \u201c%s\u201d, but this page will not report that "
             "as a result)" % (r, t["big"]))
    return r

def tile_html(t):
    word, glyph, cls = CHIP.get(t["state"], CHIP["UNPROVEN"])
    big = "unknown" if t["state"] == "UNPROVEN" else t["big"]
    reason = reason_of(t) if t["reason"] else ""
    bigcls = "big" if any(c.isdigit() for c in big) else "big word"
    out = ['<article class="tile s-%s">' % cls]
    out.append('<p class="chip"><span class="dot" aria-hidden="true">%s</span>%s</p>' % (glyph, word))
    out.append('<p class="%s">%s</p>' % (bigcls, E(big)))
    out.append('<h3 class="lbl">%s</h3>' % E(t["label"]))
    if t["expect"]:
        out.append('<p class="expect">%s</p>' % E(t["expect"]))
    if t["detail"]:
        out.append('<p class="detail">%s</p>' % E(t["detail"]))
    if reason:
        out.append('<p class="why"><strong>Why this says UNPROVEN:</strong> %s</p>' % E(reason))
    out.append('<details class="prov"><summary>How this was measured</summary>')
    out.append('<p class="src"><code>%s</code></p>' % E(t["source"]))
    if t["proof"]:
        out.append('<p class="pf">%s</p>' % E(t["proof"]))
    out.append('</details></article>')
    return "".join(out)

P = []
w = P.append
w('<meta name="viewport" content="width=device-width, initial-scale=1">')
w("<title>Charon status snapshot — %s</title>" % E(gen_at))
w("<style>")
w("""
:root{color-scheme:light dark;
 --bg:#f4f4f2;--surface:#fcfcfb;--line:#dcdbd5;--ink:#0b0b0b;--ink2:#52514e;--ink3:#6f6e68;
 --good:#0ca30c;--crit:#d03b3b;--warn:#fab219;--unk:#6b6a66;--cnt:#7a7972;
 --tint-good:rgba(12,163,12,.09);--tint-crit:rgba(208,59,59,.10);--tint-unk:rgba(107,106,102,.10);--tint-cnt:rgba(122,121,114,.06);
 --code:#eceae4;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --bg:#111110;--surface:#1a1a19;--line:#33322e;--ink:#ffffff;--ink2:#c3c2b7;--ink3:#9b9a90;
 --unk:#9a978d;--cnt:#8f8d85;
 --tint-good:rgba(12,163,12,.16);--tint-crit:rgba(208,59,59,.18);--tint-unk:rgba(154,151,141,.14);--tint-cnt:rgba(143,141,133,.09);
 --code:#26251f;}}
:root[data-theme="dark"]{
 --bg:#111110;--surface:#1a1a19;--line:#33322e;--ink:#ffffff;--ink2:#c3c2b7;--ink3:#9b9a90;
 --unk:#9a978d;--cnt:#8f8d85;
 --tint-good:rgba(12,163,12,.16);--tint-crit:rgba(208,59,59,.18);--tint-unk:rgba(154,151,141,.14);--tint-cnt:rgba(143,141,133,.09);
 --code:#26251f;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 -webkit-text-size-adjust:100%}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 72px}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;font-size:.86em}
h1{font-size:clamp(24px,3.4vw,34px);line-height:1.15;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:clamp(17px,2vw,21px);margin:40px 0 4px;letter-spacing:-.01em}
h2+.sub{margin:0 0 16px;color:var(--ink2);font-size:14px}
h3{font-size:16px;margin:0}
.snap{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 14px}
.badge{display:inline-block;padding:5px 11px;border:2px solid var(--crit);border-radius:999px;
 font-size:12px;font-weight:800;letter-spacing:.13em;text-transform:uppercase;color:var(--ink)}
.stamp{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:0 0 22px}
.stamp p{margin:0 0 6px;color:var(--ink2);font-size:14px}
.stamp p:last-child{margin:0}
.stamp b{color:var(--ink)}
.roll{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 6px;padding:0;list-style:none}
.roll li{background:var(--surface);border:1px solid var(--line);border-left:5px solid var(--line);
 border-radius:10px;padding:9px 14px;font-size:14px}
.roll li b{font-size:20px;margin-right:6px}
.roll .r{border-left-color:var(--crit)}.roll .g{border-left-color:var(--good)}.roll .u{border-left-color:var(--unk)}
.legend{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 8px}
.legend dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:8px 14px;align-items:baseline}
.legend dt{margin:0}.legend dd{margin:0;color:var(--ink2);font-size:14.5px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(288px,1fr))}
.tile{background:var(--surface);border:1px solid var(--line);border-left:5px solid var(--line);
 border-radius:12px;padding:15px 16px 13px;display:flex;flex-direction:column}
.s-crit{border-left-color:var(--crit);background:linear-gradient(var(--tint-crit),var(--tint-crit)),var(--surface)}
.s-good{border-left-color:var(--good);background:linear-gradient(var(--tint-good),var(--tint-good)),var(--surface)}
.s-unk{border-left-color:var(--unk);background:linear-gradient(var(--tint-unk),var(--tint-unk)),var(--surface)}
.s-cnt{border-left-color:var(--cnt);background:linear-gradient(var(--tint-cnt),var(--tint-cnt)),var(--surface)}
.chip{margin:0 0 8px;font-size:11.5px;font-weight:800;letter-spacing:.11em;text-transform:uppercase;color:var(--ink2)}
.dot{display:inline-grid;place-items:center;width:17px;height:17px;border-radius:50%;
 margin-right:7px;vertical-align:-4px;font-size:11px;font-weight:700;color:#fff;background:var(--unk)}
.s-crit .dot{background:var(--crit)}.s-good .dot{background:var(--good)}.s-unk .dot{background:var(--unk)}.s-cnt .dot{background:var(--cnt)}
.big{margin:0;font-size:clamp(34px,5.2vw,46px);line-height:1.02;font-weight:800;letter-spacing:-.025em;font-variant-numeric:tabular-nums}
.lbl{margin:7px 0 0;font-size:16.5px;font-weight:650;line-height:1.3}
.big.word{font-size:clamp(24px,3vw,29px);letter-spacing:-.01em;color:var(--ink2)}
.expect{margin:5px 0 0;font-size:13px;color:var(--ink3)}
.detail{margin:9px 0 0;font-size:14.5px;color:var(--ink2)}
.why{margin:10px 0 0;font-size:14px;color:var(--ink2);border-left:3px solid var(--unk);padding-left:10px}
.why strong{color:var(--ink)}
.prov{margin:11px 0 0;font-size:13px;border-top:1px solid var(--line);padding-top:8px}
.prov summary{cursor:pointer;color:var(--ink3);font-size:12.5px;letter-spacing:.02em}
.prov p{margin:7px 0 0;color:var(--ink2)}
.prov code{background:var(--code);border-radius:5px;padding:2px 5px;overflow-wrap:anywhere}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;min-width:420px;background:var(--surface);
 border:1px solid var(--line);border-radius:10px;font-size:14.5px}
caption{text-align:left;font-size:14px;color:var(--ink2);padding:0 0 7px}
th,td{text-align:left;padding:9px 13px;border-bottom:1px solid var(--line)}
th{font-size:12px;letter-spacing:.07em;text-transform:uppercase;color:var(--ink3);font-weight:700}
tr:last-child td{border-bottom:0}
td.n{font-variant-numeric:tabular-nums;font-weight:700;width:1%;white-space:nowrap}
.cannot{background:var(--surface);border:1px solid var(--line);border-left:5px solid var(--unk);
 border-radius:12px;padding:18px 20px}
.cannot ol{margin:12px 0 0;padding-left:22px}
.cannot li{margin:0 0 13px;color:var(--ink2);font-size:14.5px}
.cannot li b{color:var(--ink);font-weight:650}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);color:var(--ink3);font-size:13px}
footer p{margin:0 0 7px}
""")
w("</style>")
w('<div class="wrap">')

w("<h1>Charon &mdash; build &amp; product status</h1>")
w('<p class="snap"><span class="badge">Snapshot</span>'
  '<span class="mono" style="color:var(--ink2);font-size:13px">not live &middot; does not refresh itself</span></p>')
w('<div class="stamp">')
w("<p>Everything below was measured <b>once</b>, at <b>%s</b>. It is a still photograph. "
  "Nothing on this page updates on its own &mdash; if the page is open tomorrow, it is still showing "
  "today's numbers.</p>" % E(gen_at))
w('<p>Build-rig repo at <b class="mono">%s</b> (branch <span class="mono">%s</span>) &mdash; '
  '<span class="mono">%s</span></p>' % (E(rig_sha), E(rig_br), E(rig_root)))
w('<p>Product repo at <b class="mono">%s</b> (branch <span class="mono">%s</span>) &mdash; '
  '<span class="mono">%s</span></p>' % (E(prd_sha), E(prd_br), E(prd_root)))
w("</div>")

w("<h2>The short version</h2>")
w('<p class="sub">Across the %d things this page is willing to judge:</p>' % len(judged))
w('<ul class="roll">')
w('<li class="r"><b>%d</b>checked and failing</li>' % n_red)
w('<li class="u"><b>%d</b>cannot be claimed either way</li>' % n_unp)
w('<li class="g"><b>%d</b>checked and passing</li>' % n_green)
w("</ul>")

w("<h2>How to read this page</h2>")
w('<p class="sub">There are three verdicts, never two. The third one is the important one.</p>')
w('<div class="legend"><dl>')
w('<dt><span class="chip" style="margin:0"><span class="dot" style="background:var(--good)">&#10003;</span>PASSING</span></dt>'
  "<dd>We ran the check, it passed, <em>and</em> someone has demonstrated that this check is capable of failing. "
  "Only then is &ldquo;it passed&rdquo; worth anything.</dd>")
w('<dt><span class="chip" style="margin:0"><span class="dot" style="background:var(--crit)">&#10007;</span>FAILING</span></dt>'
  "<dd>We ran the check and it failed. A failure is always trustworthy, because we watched it happen.</dd>")
w('<dt><span class="chip" style="margin:0"><span class="dot" style="background:var(--unk)">?</span>UNPROVEN</span></dt>'
  "<dd><b>We cannot tell you.</b> Either the check would not run, or nothing has ever shown that the check "
  "is able to notice a problem &mdash; so &ldquo;it passed&rdquo; would mean nothing. This is deliberately "
  "<em>not</em> shown as good news. A page that turns everything green is a page that lies.</dd>")
w('<dt><span class="chip" style="margin:0"><span class="dot" style="background:var(--cnt)">&#8226;</span>COUNTED</span></dt>'
  "<dd>Not a verdict at all &mdash; just a headcount, in its own section at the bottom. There is no "
  "right or wrong number for these, so no health claim is made. <b>Counted is not the same as passing.</b></dd>")
w("</dl></div>")

for sec in order:
    rows = [t for t in tiles if t["section"] == sec]
    w("<h2>%s</h2>" % E(sec))
    if sec == "Counted, not judged":
        w('<p class="sub">Inventory. These carry no verdict, because there is no pass/fail line to hold them to.</p>')
    w('<div class="grid">')
    for t in rows:
        w(tile_html(t))
    w("</div>")
    if sec == "Is finished work getting lost?" and shapes:
        w('<h2 style="font-size:17px;margin-top:26px">How that unfinished work is stranded</h2>')
        w('<div class="scroll"><table><caption>Every row is work that exists and is not merged. '
          "Straight from the detector's own tally.</caption>"
          "<tr><th>Count</th><th>Shape</th><th>In plain English</th></tr>")
        plain = {
            "pushed-no-pr": "sent to the server, but nobody was ever asked to merge it",
            "closed-pr-unlanded": "the request to merge it was closed, and the work never landed",
            "unpushed-branch": "committed on this machine only &mdash; one disk failure from gone",
            "dirty-worktree": "edited files never even committed, in an abandoned working copy",
            "stash": "set aside in a scratch area that belongs to no branch",
            "pr-no-checks": "open for merge with zero automatic checks &mdash; looks safe, verified nothing",
            "unmerged-remote": "on the server and not merged into the main line",
            "orphan-worktree": "a working copy with no job claiming it",
        }
        for n, name in shapes:
            w("<tr><td class='n'>%s</td><td class='mono'>%s</td><td>%s</td></tr>"
              % (E(n), E(name), plain.get(name, "&mdash;")))
        w("</table></div>")

w("<h2>What this page cannot tell you</h2>")
w('<p class="sub">This section is the point of the page, not an apology for it. '
  "Everything here is a question we are <em>not</em> answering, and the reason why.</p>")
w('<div class="cannot">')
if unproven:
    w("<p><b>%d of the %d judged items are UNPROVEN.</b> For each one, the honest answer is "
      "&ldquo;we do not know&rdquo; &mdash; not &ldquo;it is fine&rdquo;.</p>" % (len(unproven), len(judged)))
    w("<ol>")
    for t in unproven:
        w("<li><b>%s</b> &mdash; %s</li>" % (E(t["label"]), E(reason_of(t))))
    w("</ol>")
else:
    w("<p><b>No judged item is UNPROVEN in this snapshot.</b> Every check on this page ran, and "
      "every passing one has a red-proof that actually executes in CI. That is a strong claim &mdash; "
      "if it appears without the underlying suites being enforced, this page has a bug.</p>")
w("<p>Three limits apply to <em>every</em> tile above, including the green ones. "
  "First, this is a snapshot: it says nothing about what happened five minutes after it was taken. "
  "Second, a passing check only ever covers what someone thought to check &mdash; there is no tile for "
  "&ldquo;the problem nobody has imagined yet&rdquo;. "
  "Third, this page reports what the detectors say; it does not re-derive their numbers, so a detector "
  "with a blind spot is a blind spot here too.</p>")
w("</div>")

w("<footer>")
w("<p>Regenerate with <code>bash fleet/status-board/generate.sh</code>. "
  "The page is a single self-contained file with no scripts and no network calls &mdash; it opens from disk.</p>")
w("<p>Every number above came from one of these, and from nothing else: "
  "<code>charon.cli gate</code>, <code>fleet/validate_board.sh</code>, "
  "<code>fleet/checks/gate-integrity.sh</code>, <code>fleet/checks/rig-ci-scope.sh</code>, "
  "<code>fleet/checks/stranded-work.sh</code>, <code>fleet/checks/graphify-freshness.sh</code>, "
  "<code>fleet/watchdog/discover-services.sh</code>, <code>fleet/board/*.md</code>, "
  "<code>fleet/state/service-registry.tsv</code>, <code>graphify graph.json</code>, "
  "<code>gh api</code> (REST), and the gateway's own <code>/charon/status</code> and "
  "<code>/charon/config</code>. Nothing here is estimated, rounded to a nicer number, or filled in "
  "from memory; where a source failed, the tile says UNPROVEN and names the failure.</p>")
w("</footer>")
w("</div>")

sys.stdout.write("\n".join(P) + "\n")
PY
then
  echo "generate.sh: RED the renderer failed — refusing to write a partial page to $OUT" >&2
  exit 1
fi

if [ ! -s "$TMP_OUT" ]; then
  echo "generate.sh: RED the renderer produced an empty page — refusing to write $OUT" >&2
  exit 1
fi
mv -f "$TMP_OUT" "$OUT" || { echo "generate.sh: RED could not write $OUT" >&2; exit 1; }

# Console receipt: the same counts the page shows, so a cron/CI log is self-evidencing.
awk -F'\037' '{c[$2]++} END{printf "status-board: wrote page — %d failing, %d unproven, %d passing, %d counted\n", c["RED"], c["UNPROVEN"], c["GREEN"], c["COUNTED"]}' "$TILES"
echo "status-board: $OUT"
exit 0
