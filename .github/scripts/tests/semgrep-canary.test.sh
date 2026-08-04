#!/usr/bin/env bash
# semgrep-canary.test.sh — FAIL-ON-REVERT canary for the ADOPTED Semgrep policy gate.
#
# This is the proof the gate ACTUALLY EXECUTES. A gate whose green is not backed by a firing red
# is a false receipt. This canary asserts, hermetically:
#   (1) CANARY FIRES  — the wrapper flags fixtures/semgrep-known-bad.py (>=1 finding, exit 1).
#   (2) FAIL-ON-REVERT— neuter the flagship rule (charon-no-hardcoded-lan-host) in a COPY of the
#                        ruleset -> findings drop to 0 and the wrapper goes GREEN. This proves the
#                        RED in (1) is produced BY that rule, not by accident. If neutering did
#                        NOT flip it, this step FAILS — i.e. reverting the rule breaks the canary,
#                        as required.
#   (3) CLEAN PASSES  — a clean snippet yields 0 findings, exit 0.
#   (4) VACUOUS GUARD — an empty ruleset must NEVER go green: a rules file emptied to nothing
#                        cannot masquerade as a passing gate. The wrapper's OWN rule-count guard
#                        reds on zero rules (exit 2) — VERSION-INDEPENDENT, NOT relying on
#                        semgrep's --strict, whose empty-ruleset behavior changed between semgrep
#                        versions (older semgrep errors on `rules: []`; >=1.170 treats a no-rules
#                        directory config as a clean exit-0 pass).
#   (5) FAIL-CLOSED   — --diff against an UNRESOLVABLE base must exit non-zero, never green. A
#                        shallow CI checkout is the classic silent-green cause.
#
# Fully hermetic: neutered/empty rulesets live in mktemp dirs; the real semgrep-rules/ is never
# mutated. Run:  bash .github/scripts/tests/semgrep-canary.test.sh   (exit 0 = all pass)
set -uo pipefail
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAP="$SCRIPTS/semgrep.sh"
RULES="$SCRIPTS/semgrep-rules"
FIXTURE="$SCRIPTS/fixtures/semgrep-known-bad.py"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

command -v semgrep >/dev/null 2>&1 || {
  echo "semgrep-canary: semgrep is not installed — cannot run the canary. Adopt the engine first" >&2
  echo "(pip install semgrep==<pin>). REFUSING to fake a green." >&2
  exit 2
}
[ -f "$FIXTURE" ] || { echo "semgrep-canary: fixture missing: $FIXTURE" >&2; exit 2; }

# Count findings via the SAME engine the wrapper uses, over an arbitrary rules dir + paths.
count(){ local rdir="$1"; shift
  semgrep scan --config "$rdir" --json --quiet "$@" 2>/dev/null \
    | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["results"]))'
}

# (1) CANARY FIRES on the known-bad fixture.
n="$(count "$RULES" "$FIXTURE")"
[ "${n:-0}" -ge 1 ] && ok "1 canary FIRES: known-bad yields $n finding(s)" \
                    || bad "1 canary must fire on known-bad (got '${n}')"
rc=0; bash "$WRAP" "$FIXTURE" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 1 ] && ok "1b wrapper exits 1 (blocks merge) on known-bad" \
              || bad "1b wrapper should exit 1 on known-bad (got $rc)"

# (2) FAIL-ON-REVERT: neuter the private-range alternation the flagship rule matches the fixture
#     with -> findings drop to 0, wrapper goes green.
tmp="$(mktemp -d)"; cp -r "$RULES/." "$tmp/"
sed -i 's/192\\.168\\./__NEUTERED_NO_MATCH__/' "$tmp"/charon-policy.yml
nn="$(count "$tmp" "$FIXTURE")"
[ "${nn:-1}" -eq 0 ] && ok "2 FAIL-ON-REVERT: neutering charon-no-hardcoded-lan-host drops $n->0 (rule is load-bearing)" \
                     || bad "2 neutered ruleset still finds '${nn}' — rule NOT load-bearing (or sed missed the pattern)"
rc=0; SEMGREP_RULES_DIR="$tmp" bash "$WRAP" "$FIXTURE" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "2b neutered wrapper goes GREEN on known-bad (confirms the RED came FROM the rule)" \
              || bad "2b neutered wrapper should be green (got $rc)"

# (3) CLEAN PASSES: no private-LAN literal, no developer-home absolute path.
clean="$tmp/clean_ok.py"
printf 'def pick(cfg):\n    return route(model_id=cfg["model"], host=cfg["gateway_url"])\n' > "$clean"
cn="$(count "$RULES" "$clean")"
[ "${cn:-1}" -eq 0 ] && ok "3 CLEAN: clean snippet yields 0 findings" \
                     || bad "3 clean snippet should be 0 (got '${cn}')"
rc=0; bash "$WRAP" "$clean" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "3b wrapper exits 0 on clean" || bad "3b wrapper should exit 0 on clean (got $rc)"

# (4) VACUOUS GUARD (VERSION-INDEPENDENT): a ruleset that loads ZERO rules can never find
#     anything, so its green is a false receipt. We assert the WRAPPER ITSELF refuses to run it
#     (semgrep.sh's own rule-count guard, exit 2) — deliberately NOT relying on semgrep's --strict
#     empty-ruleset behavior, which is version-dependent.
empty="$(mktemp -d)"; printf 'rules: []\n' > "$empty/empty.yml"
rc=0; out="$(SEMGREP_RULES_DIR="$empty" bash "$WRAP" "$FIXTURE" 2>&1)" || rc=$?
[ "$rc" -ne 0 ] && ok "4 vacuous (zero-rule) ruleset does NOT go green — wrapper fails closed (exit $rc)" \
              || bad "4 vacuous ruleset went green — zero-work-green not prevented"
printf '%s\n' "$out" | grep -q "loads ZERO rules" \
  && ok "4a wrapper's own rule-count guard fired (independent of semgrep --strict / version)" \
  || bad "4a wrapper did not report the zero-rule guard — vacuous red may be coming from version-fragile semgrep behavior, not the wrapper"
printf '%s\n' "$out" | grep -q "OK — no policy findings" \
  && bad "4b vacuous ruleset printed the OK line — that is the false receipt this canary forbids" \
  || ok "4b vacuous ruleset never printed the OK line"

# (5) FAIL-CLOSED on an unresolvable diff base (the shallow-checkout silent-green case).
rc=0; out="$(CHARON_CI_BASE=__no_such_ref__ CHARON_CI_HEAD=HEAD bash "$WRAP" --diff 2>&1)" || rc=$?
[ "$rc" -ne 0 ] && ok "5 unresolvable merge-base fails closed (exit $rc)" \
              || bad "5 unresolvable merge-base went green — shallow-checkout silent green not prevented"

rm -rf "$tmp" "$empty"
# ── (6) --DIFF MODE: the path CI actually runs ────────────────────────────────────────────────
#     Everything above this line runs in PATHS mode. These cases drive the REAL pipeline —
#     resolve base -> list changed files -> scan -> LINE-FILTER -> verdict — against a throwaway
#     repo shaped exactly like a GitHub merge ref. See _difflab.sh for why that gap mattered.
# shellcheck source=.github/scripts/tests/_difflab.sh
. "$SCRIPTS/tests/_difflab.sh"
LAB="$tmp/lab"
# Assembled at runtime for the same reason as the gitleaks canary. Today every rule in the
# ruleset is `languages: [python]`, so a LAN-IP literal sitting in this shell script is not
# analysable and would not fire — but that is scoping luck, not a property worth relying on:
# the day a generic/non-Python rule lands, this literal becomes a self-inflicted red. Building
# it from fragments also drops the public-clean waiver this line used to need.
_lan_prefix='192.168'
VIOL="GATEWAY = \"http://${_lan_prefix}.42.7:8080/v1\""
WRAP_BASENAME='semgrep.sh'
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
echo "ALL SEMGREP CANARY TESTS PASS"
