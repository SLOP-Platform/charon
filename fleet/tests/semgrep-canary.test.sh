#!/usr/bin/env bash
# semgrep-canary.test.sh — FAIL-ON-REVERT canary for the ADOPTED Semgrep policy gate.
#
# This is the proof the gate ACTUALLY EXECUTES (memory: gates-must-actually-run). A gate whose green
# is not backed by a firing red is a false receipt. This canary asserts, hermetically:
#   (1) CANARY FIRES  — the wrapper flags fleet/tests/fixtures/semgrep-known-bad.py (>=1 finding, exit 1).
#   (2) FAIL-ON-REVERT— neuter the flagship rule (charon-no-hardcoded-anthropic-model) in a COPY of the
#                        ruleset -> findings drop to 0 and the wrapper goes GREEN. This proves the RED in
#                        (1) is produced BY that rule, not by accident. If neutering did NOT flip it, this
#                        step FAILS — i.e. reverting the rule breaks the canary, as required.
#   (3) CLEAN PASSES  — a clean snippet yields 0 findings, exit 0.
#   (4) VACUOUS GUARD — an empty ruleset must NEVER go green: a rules file emptied to nothing cannot
#                        masquerade as a passing gate. The wrapper's OWN rule-count guard reds on zero
#                        rules (exit 2) — VERSION-INDEPENDENT, NOT relying on semgrep's --strict, whose
#                        empty-ruleset behavior changed between semgrep versions (see assertion 4/4a).
#
# Fully hermetic: neutered/empty rulesets live in mktemp dirs; the real fleet/semgrep-rules is never
# mutated. Run:  bash fleet/tests/semgrep-canary.test.sh   (exit 0 = all pass)
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAP="$FLEET/checks/semgrep.sh"
RULES="$FLEET/semgrep-rules"
FIXTURE="$FLEET/tests/fixtures/semgrep-known-bad.py"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

command -v semgrep >/dev/null 2>&1 || {
  echo "semgrep-canary: semgrep is not installed — cannot run the canary. Adopt the engine first" >&2
  echo "(uv tool install semgrep / pipx install semgrep). REFUSING to fake a green." >&2
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

# (2) FAIL-ON-REVERT: neuter the flagship rule -> findings drop to 0, wrapper goes green.
tmp="$(mktemp -d)"; cp -r "$RULES/." "$tmp/"
sed -i 's/claude|anthropic|opus|sonnet|haiku|fable/__NEUTERED_NO_MATCH__/' "$tmp"/charon-policy.yml
nn="$(count "$tmp" "$FIXTURE")"
[ "${nn:-1}" -eq 0 ] && ok "2 FAIL-ON-REVERT: neutering charon-no-hardcoded-anthropic-model drops $n->0 (rule is load-bearing)" \
                     || bad "2 neutered ruleset still finds '${nn}' — rule NOT load-bearing (or sed missed the pattern)"
rc=0; SEMGREP_RULES_DIR="$tmp" bash "$WRAP" "$FIXTURE" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "2b neutered wrapper goes GREEN on known-bad (confirms the RED came FROM the rule)" \
              || bad "2b neutered wrapper should be green (got $rc)"

# (3) CLEAN PASSES: no claude/anthropic id, no LAN IP, no /home/stack path.
clean="$tmp/clean_ok.py"
printf 'def pick(cfg):\n    return route(model_id=cfg["model"], host=cfg["gateway_url"])\n' > "$clean"
cn="$(count "$RULES" "$clean")"
[ "${cn:-1}" -eq 0 ] && ok "3 CLEAN: clean snippet yields 0 findings" \
                     || bad "3 clean snippet should be 0 (got '${cn}')"
rc=0; bash "$WRAP" "$clean" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "3b wrapper exits 0 on clean" || bad "3b wrapper should exit 0 on clean (got $rc)"

# (4) VACUOUS GUARD (VERSION-INDEPENDENT): a ruleset that loads ZERO rules can never find anything, so
#     its green is a false receipt. We assert the WRAPPER ITSELF refuses to run it (semgrep.sh's own
#     rule-count guard, exit 2) — deliberately NOT relying on semgrep's --strict empty-ruleset behavior,
#     which is version-dependent (older semgrep errors on `rules: []`; newer semgrep >=1.170 treats a
#     no-rules directory config as a clean exit-0 pass — that regression is what this canary now shrugs off).
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

rm -rf "$tmp" "$empty"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL SEMGREP CANARY TESTS PASS"
