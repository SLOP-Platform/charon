#!/usr/bin/env bash
# hold-reason-gate.test.sh — FAIL-ON-REVERT tests for the DRAFT CONVENTION gate.
# SOURCES a COPY of preflight.sh (+ _lib.sh + gh-cache.sh + repo-registry.sh + verify-merged.sh)
# in an ISOLATED temp fleet and drives hold_reason_gate / hold_check / hold_prs_tsv directly.
# NEVER touches the live reds.tsv, and NEVER calls gh (GH_HOLD_FIXTURE drives everything offline).
#
# THE CONVENTION under test: draft state is the launcher's UNCONDITIONAL default (every PR opens
# draft) so it carries NO information — it means only "not yet human-reviewed". A REAL hold is the
# `hold` LABEL plus a `HOLD: <reason>` comment. The gate FAILS a hold-labelled PR with no reason.
#
# Covers:
#   (a) hold label + NO 'HOLD:' comment -> gate FAILS, auto-registers a blocking red.
#   (b) hold label + a 'HOLD:' comment  -> gate PASSES, PR not flagged.
#   (c) ANTI-REGRESSION: a normal draft PR is untouched (the old "draft == hold" rule would have
#       blocked EVERY PR). The query keys on the LABEL, never on draft state.
#   (d) OFFLINE DEGRADE: gh absent + no cache -> unverifiable (non-zero), not a false "no holds".
#   (e) the registered red SELF-CLOSES once the reason exists (hold_check rc contract).
# Each case builds its OWN temp fleet + OWN fixture + OWN reds.tsv — sibling-state cascades have
# repeatedly produced false greens in this repo, so nothing is shared between assertions.
#
# Run:  bash fleet/tests/hold-reason-gate.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
TAB=$'\t'

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

# mkfleet -> prints a fresh isolated fleet dir (own scripts, own EMPTY reds.tsv, own cache).
mkfleet(){
  local d; d="$(mktemp -d -p "$ROOT")"
  cp "$SRC/preflight.sh" "$SRC/_lib.sh" "$SRC/gh-cache.sh" "$SRC/repo-registry.sh" \
     "$SRC/verify-merged.sh" "$d/"
  printf '# reds registry (test fixture)\n' > "$d/reds.tsv"
  mkdir -p "$d/state/cache" "$d/state/done" "$d/board/archive"
  printf '%s' "$d"
}

# run_gate <fleet-dir> <fixture-tsv-content> -> gate stdout. The dir is passed IN (not created
# here) so the caller can inspect that run's OWN reds.tsv — command substitution would swallow
# any variable this function set.
run_gate(){
  local d="$1"
  printf '%s' "$2" > "$d/hold.tsv"
  GH_HOLD_FIXTURE="$d/hold.tsv" GH_CACHE_DIR="$d/state/cache" HOLD_GATE_SLUG="acme/widget" \
    bash -c 'source "$1/preflight.sh"; hold_reason_gate' _ "$d" 2>/dev/null
}
red_status(){ awk -F'\t' -v id="$2" '$1==id{print $7; exit}' "$1/reds.tsv"; }

echo "== (a) hold label + NO 'HOLD:' comment -> FAILURE =="
# REVERT LINE: fleet/preflight.sh, hold_reason_gate — the `bad=$((bad+1))` / `cmd_add ... hold-no-reason`
# block (delete it, or `continue` before it, and an unreasoned hold is silently accepted).
dA="$(mkfleet)"; out="$(run_gate "$dA" "77${TAB}0"$'\n')"
if printf '%s\n' "$out" | grep -q 'acme/widget#77' \
   && printf '%s\n' "$out" | grep -q 'AUTO-REGISTERED blocking red' \
   && [ "$(red_status "$dA" hold-no-reason-acme-widget-77)" = open ]; then
  ok "(a) unreasoned hold FAILS the gate and opens a blocking red"
else
  bad "(a) unreasoned hold FAILS the gate and opens a blocking red (out: $out)"
fi

echo "== (b) hold label + a 'HOLD:' comment -> PASSES =="
# REVERT LINE: fleet/preflight.sh, hold_reason_gate — the `if [ "$flag" = 1 ]` accept branch
# (flip to `[ "$flag" = 0 ]` and a properly-recorded hold is wrongly flagged).
dB="$(mkfleet)"; out="$(run_gate "$dB" "88${TAB}1"$'\n')"
if printf '%s\n' "$out" | grep -q 'hold-reason-gate: clean' \
   && ! printf '%s\n' "$out" | grep -q 'acme/widget#88' \
   && [ -z "$(red_status "$dB" hold-no-reason-acme-widget-88)" ]; then
  ok "(b) hold WITH a recorded 'HOLD:' reason PASSES and opens no red"
else
  bad "(b) hold WITH a recorded 'HOLD:' reason PASSES (out: $out)"
fi

echo "== (c) ANTI-REGRESSION: a normal draft PR is untouched =="
# The launcher opens EVERY PR as a draft, so a rule that read draft as a hold would block the whole
# board. The gate selects on the `hold` LABEL only, so an unlabelled draft never enters the result.
# REVERT LINE: fleet/gh-cache.sh, hold_prs_tsv — the `--label hold` flag on the `gh pr list` call
# (drop it and every open DRAFT PR is selected and then flagged as an unreasoned hold).
dC="$(mkfleet)"; out="$(run_gate "$dC" "")"
if printf '%s\n' "$out" | grep -q 'hold-reason-gate: clean' \
   && ! printf '%s\n' "$out" | grep -q 'AUTO-REGISTERED' \
   && ! grep -q '^hold-no-reason' "$dC/reds.tsv"; then
  ok "(c) no hold-labelled PR -> gate clean; draft state alone never registers a red"
else
  bad "(c) no hold-labelled PR -> gate clean (out: $out)"
fi
if grep -q -- '--label hold' "$SRC/gh-cache.sh" && ! grep -q -- '--draft\b' "$SRC/gh-cache.sh"; then
  ok "(c2) the gh query filters on --label hold and never on draft state"
else
  bad "(c2) the gh query filters on --label hold and never on draft state"
fi
# (c3) BEHAVIOURAL version of (c2) — drives the REAL gh code path (no GH_HOLD_FIXTURE) through a
# stub `gh` that HONOURS the label filter: with `--label hold` it returns nothing (the repo has no
# hold-labelled PR); without it, it returns PR #1234, a plain unlabelled DRAFT PR. So dropping the
# filter makes the gate flag an ordinary draft — the exact whole-board-blocking regression.
# REVERT LINE: fleet/gh-cache.sh, hold_prs_tsv — the `--label hold` flag on the `gh pr list` call.
d="$(mkfleet)"; mkdir -p "$d/bin"
cat > "$d/bin/gh" <<'STUB'
#!/usr/bin/env bash
for a in "$@"; do [ "$a" = "hold" ] && exit 0; done   # label filter honoured -> zero hold PRs
printf '1234\t0\n'                                   # filter dropped -> a plain DRAFT PR leaks in
STUB
chmod +x "$d/bin/gh"
out="$(PATH="$d/bin:/usr/bin:/bin" GH_CACHE_DIR="$d/state/cache" HOLD_GATE_SLUG="acme/widget" \
        bash -c 'source "$1/gh-cache.sh"; hold_prs_tsv acme/widget' _ "$d" 2>/dev/null)"
if [ -z "$out" ]; then
  ok "(c3) with --label hold on the wire, an unlabelled DRAFT PR never reaches the gate"
else
  bad "(c3) an unlabelled DRAFT PR leaked into the hold query (got: $out)"
fi

echo "== (d) OFFLINE DEGRADE: gh absent + no cache -> unverifiable, not a false clean =="
# REVERT LINE: fleet/gh-cache.sh, hold_prs_tsv — the FINAL `[ -f "$cf" ] || return 1` degrade
# guard (drop it and an offline run `cat`s nothing, returns 0, and reports "no holds" instead of
# "cannot verify" — a silent false green). It is deliberately the ONLY guard on this path so that
# reverting it is observable; a redundant `command -v gh` fast-path made this assertion a false
# green (it passed with the guard removed) and was deleted for that reason.
d="$(mkfleet)"; mkdir -p "$d/bin"   # a PATH with NO gh on it at all
# NOTE: gh-cache.sh is sourced EXPLICITLY here — preflight.sh only sources it inside the gate, so
# calling hold_prs_tsv off a bare `source preflight.sh` would be command-not-found (rc 127). The
# rc match is ANCHORED for the same reason: an unanchored 'rc=1' substring-matches 'rc=127'.
out="$(PATH="$d/bin:/usr/bin:/bin" GH_CACHE_DIR="$d/state/cache" \
        bash -c 'source "$1/gh-cache.sh"; hold_prs_tsv acme/widget; echo "rc=$?"' _ "$d" 2>/dev/null)"
if printf '%s\n' "$out" | grep -qx 'rc=1'; then
  ok "(d) gh absent + no cache -> hold_prs_tsv non-zero (caller degrades to a NON-blocking advisory)"
else
  bad "(d) gh absent + no cache -> hold_prs_tsv non-zero (out: $out)"
fi
# and the gate itself must SAY so and still return 0 (advisory, never blocking)
out="$(PATH="$d/bin:/usr/bin:/bin" GH_CACHE_DIR="$d/state/cache" \
        bash -c 'source "$1/preflight.sh"; hold_reason_gate; echo "rc=$?"' _ "$d" 2>/dev/null)"
if printf '%s\n' "$out" | grep -qx 'rc=0' \
   && printf '%s\n' "$out" | grep -q 'verification-unavailable'; then
  ok "(d2) hold_reason_gate returns 0 when verification is unavailable (offline-tolerant)"
else
  bad "(d2) hold_reason_gate returns 0 when verification is unavailable (out: $out)"
fi

echo "== (e) the registered red SELF-CLOSES once the reason exists =="
# REVERT LINE: fleet/preflight.sh, hold_check — `[ "$flag" = 1 ] && { ...; return 0; }`
# (delete it and a resolved hold stays red forever, so the gate can never clear itself).
d="$(mkfleet)"
printf '99%s1\n' "$TAB" > "$d/hold.tsv"
GH_HOLD_FIXTURE="$d/hold.tsv" bash "$d/preflight.sh" hold-check acme/widget 99 >/dev/null 2>&1
rc_resolved=$?
printf '99%s0\n' "$TAB" > "$d/hold.tsv"
GH_HOLD_FIXTURE="$d/hold.tsv" bash "$d/preflight.sh" hold-check acme/widget 99 >/dev/null 2>&1
rc_open=$?
if [ "$rc_resolved" -eq 0 ] && [ "$rc_open" -ne 0 ]; then
  ok "(e) hold-check: 0 once a 'HOLD:' reason exists, non-zero while it does not"
else
  bad "(e) hold-check rc contract (resolved=$rc_resolved open=$rc_open)"
fi

echo; echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] && echo "ALL HOLD-REASON-GATE TESTS PASS" || exit 1
