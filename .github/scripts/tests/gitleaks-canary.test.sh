#!/usr/bin/env bash
# gitleaks-canary.test.sh — FAIL-ON-REVERT canary for the ADOPTED gitleaks secret-scan gate.
#
# This is the proof the gate ACTUALLY EXECUTES. A gate whose green is not backed by a firing red
# is a false receipt. This canary asserts, hermetically:
#   (1) CANARY FIRES  — the wrapper flags fixtures/gitleaks-known-bad.txt (>=1 finding, exit 1).
#   (2) FAIL-ON-REVERT— point the SAME wrapper at a neutered config (useDefault=false + one rule
#                        that never matches) -> findings drop to 0 and the wrapper goes GREEN.
#                        This proves the RED in (1) is produced BY the maintained default ruleset,
#                        not by accident. If neutering did NOT flip it, this step FAILS —
#                        reverting the ruleset breaks the canary, as required.
#   (3) CLEAN PASSES  — a clean snippet yields 0 findings, exit 0.
#   (4) VACUOUS GUARD — a config that loads ZERO rules must NEVER go green: gitleaks itself prints
#                        "no leaks found" (exit 0) on a secret-laden file when handed a no-rules
#                        config (verified 8.21.2). The wrapper's OWN rule-count guard reds on that
#                        (exit 2) — VERSION-INDEPENDENT, not relying on any gitleaks flag.
#   (5) FAIL-CLOSED   — --diff against an UNRESOLVABLE base must exit non-zero, never green. A
#                        shallow CI checkout is the classic silent-green cause.
#
# Fully hermetic: neutered/vacuous configs live in mktemp files; nothing tracked is mutated.
# Run:  bash .github/scripts/tests/gitleaks-canary.test.sh   (exit 0 = all pass)
set -uo pipefail
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAP="$SCRIPTS/gitleaks.sh"
FIXTURE="$SCRIPTS/fixtures/gitleaks-known-bad.txt"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

command -v gitleaks >/dev/null 2>&1 || {
  echo "gitleaks-canary: gitleaks is not installed — cannot run the canary. Adopt the scanner" >&2
  echo "first (download the pinned release binary). REFUSING to fake a green." >&2
  exit 2
}
[ -f "$FIXTURE" ] || { echo "gitleaks-canary: fixture missing: $FIXTURE" >&2; exit 2; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# The maintained default ruleset (what the wrapper uses when GITLEAKS_CONFIG is unset).
defcfg="$tmp/default.toml"
printf 'title = "canary-default"\n[extend]\nuseDefault = true\n' > "$defcfg"
# A neutered config: no maintained default, one rule that can never match the fixture.
neutcfg="$tmp/neutered.toml"
printf 'title = "canary-neutered"\n[[rules]]\nid = "never-matches-anything"\nregex = %s\n' \
  "'''ZZZ_THIS_PATTERN_NEVER_APPEARS_IN_THE_FIXTURE_ZZZ'''" > "$neutcfg"
# A vacuous config: no rules at all, no useDefault.
vaccfg="$tmp/vacuous.toml"
printf 'title = "canary-vacuous"\n' > "$vaccfg"

# Count findings via the SAME scanner the wrapper uses, over an arbitrary config + target.
count(){ local cfg="$1" tgt="$2" rep="$tmp/rep.json"
  gitleaks dir --config "$cfg" --no-banner --report-format json --report-path "$rep" "$tgt" >/dev/null 2>&1
  python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$rep" 2>/dev/null || echo -1
}

# (1) CANARY FIRES on the known-bad fixture.
n="$(count "$defcfg" "$FIXTURE")"
[ "${n:-0}" -ge 1 ] && ok "1 canary FIRES: known-bad yields $n finding(s)" \
                    || bad "1 canary must fire on known-bad (got '${n}')"
rc=0; bash "$WRAP" "$FIXTURE" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 1 ] && ok "1b wrapper exits 1 (blocks merge) on known-bad" \
              || bad "1b wrapper should exit 1 on known-bad (got $rc)"

# (2) FAIL-ON-REVERT: neuter the ruleset -> findings drop to 0, wrapper goes green.
nn="$(count "$neutcfg" "$FIXTURE")"
[ "${nn:-1}" -eq 0 ] && ok "2 FAIL-ON-REVERT: neutering the maintained ruleset drops $n->0 (ruleset is load-bearing)" \
                     || bad "2 neutered config still finds '${nn}' — ruleset NOT load-bearing (or neuter missed)"
rc=0; GITLEAKS_CONFIG="$neutcfg" bash "$WRAP" "$FIXTURE" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "2b neutered wrapper goes GREEN on known-bad (confirms the RED came FROM the ruleset)" \
              || bad "2b neutered wrapper should be green (got $rc)"

# (3) CLEAN PASSES: an ordinary file with no secret.
clean="$tmp/clean_ok.txt"
printf 'def pick(cfg):\n    return route(model_id=cfg["model"], host=cfg["gateway_url"])\n' > "$clean"
cn="$(count "$defcfg" "$clean")"
[ "${cn:-1}" -eq 0 ] && ok "3 CLEAN: clean snippet yields 0 findings" \
                     || bad "3 clean snippet should be 0 (got '${cn}')"
rc=0; bash "$WRAP" "$clean" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "3b wrapper exits 0 on clean" || bad "3b wrapper should exit 0 on clean (got $rc)"

# (4) VACUOUS GUARD (VERSION-INDEPENDENT): a config that loads ZERO rules can never find anything,
#     so its green is a false receipt. gitleaks ITSELF exits 0 "no leaks found" on such a config
#     over the secret-laden fixture — so we assert the WRAPPER's own rule-count guard reds it.
rc=0; out="$(GITLEAKS_CONFIG="$vaccfg" bash "$WRAP" "$FIXTURE" 2>&1)" || rc=$?
[ "$rc" -ne 0 ] && ok "4 vacuous (zero-rule) config does NOT go green — wrapper fails closed (exit $rc)" \
              || bad "4 vacuous config went green — zero-work-green not prevented"
printf '%s\n' "$out" | grep -q "loads ZERO rules" \
  && ok "4a wrapper's own rule-count guard fired (independent of any gitleaks flag / version)" \
  || bad "4a wrapper did not report the zero-rule guard — vacuous red may be version-fragile, not the wrapper"
printf '%s\n' "$out" | grep -q "OK — no leaked-secret findings" \
  && bad "4b vacuous config printed the OK line — that is the false receipt this canary forbids" \
  || ok "4b vacuous config never printed the OK line"

# (5) FAIL-CLOSED on an unresolvable diff base (the shallow-checkout silent-green case).
rc=0; out="$(CHARON_CI_BASE=__no_such_ref__ CHARON_CI_HEAD=HEAD bash "$WRAP" --diff 2>&1)" || rc=$?
[ "$rc" -ne 0 ] && ok "5 unresolvable merge-base fails closed (exit $rc)" \
              || bad "5 unresolvable merge-base went green — shallow-checkout silent green not prevented"

# ── (6) --DIFF MODE: the path CI actually runs ────────────────────────────────────────────────
#     Everything above this line runs in PATHS mode. These cases drive the REAL pipeline —
#     resolve base -> list changed files -> scan -> LINE-FILTER -> verdict — against a throwaway
#     repo shaped exactly like a GitHub merge ref. See _difflab.sh for why that gap mattered.
# shellcheck source=.github/scripts/tests/_difflab.sh
. "$SCRIPTS/tests/_difflab.sh"
LAB="$tmp/lab"
VIOL='aws_access_key_id = "AKIAZ3FAKEXAMPLE1234"'
WRAP_BASENAME='gitleaks.sh'
diffcase(){ local mode="$1" want="$2" label="$3" rc
  difflab "$LAB" "$mode" "$VIOL" >/dev/null 2>&1
  rc="$(difflab_run "$LAB" "$WRAP_BASENAME")"
  if [ "$rc" = "$want" ]; then ok "$label (rc=$rc)"
  else bad "$label — expected rc=$want, got rc=$rc :: $(tail -2 "$LAB/out.txt" 2>/dev/null | tr '\n' ' ')"; fi
}
diffcase plain     1 "6 --diff: a violation the PR ADDS blocks merge"
diffcase payload   1 "6a --diff: a '++ ' line in an earlier hunk does NOT hide the violation (diff-parser regression)"
diffcase otherlane 0 "6b --diff: a violation landed on MASTER is not blamed on this PR (base = merge ref's first parent)"
diffcase nonascii  1 "6c --diff: a violation in a NON-ASCII filename still blocks (quotePath/NUL-safe listing)"
diffcase reformat  0 "6d --diff: a pre-existing violation merely moved/reindented does not block"
if [ "$(id -u)" -eq 0 ]; then
  ok "6e --diff: unreadable-target case SKIPPED (running as root, chmod 000 does not deny root)"
else
  diffcase unreadable 2 "6e --diff: an unreadable target fails closed instead of scanning nothing"
fi

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL GITLEAKS CANARY TESTS PASS"
