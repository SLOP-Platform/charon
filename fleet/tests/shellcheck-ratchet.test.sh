#!/usr/bin/env bash
# SHELLCHECK-RATCHET.TEST.SH (capitalized: a line starting "# shellcheck" is parsed by shellcheck
# itself as a directive and errors out — SC1072/SC1073 — so this header cannot spell its own
# filename in lowercase without tripping the very tool it tests).
# FAIL-ON-REVERT tests for fleet/checks/shellcheck-ratchet.sh, the
# baseline ratchet that lets shellcheck's full rule surface (-o all: default severities + all 11
# optional checks, all OFF anywhere in this rig before this ticket) run in CI without blocking on
# the ~36,700 pre-existing findings a bare `enable=all` would surface (that number would reject
# every PR from commit 1 — automatic reject, not a gate. See TOOL-UTILIZATION-AUDIT.md, 2026-08-01,
# 31,810 at the time of measurement; not re-derived here).
#
# Hermetic/offline: every fixture is a throwaway `mktemp -d` directory of *.sh files, never the
# live fleet/. Real fleet/checks/shellcheck-ratchet.sh is invoked with its SHELLCHECK_RATCHET_*
# env overrides pointed at the fixture, so this exercises the ACTUAL script, not a re-implementation.
#
# Covers:
#   (1) BASELINE FLOOR   — a fixture tree's pre-existing findings, once baselined, does not RED.
#   (2) NEW FINDING REDS — adding an SC-code instance ABOVE its baselined count REDs, with the
#                          file and SC-code named in the output (not a silent/opaque failure).
#   (2r) REVERT PROOF    — the SAME new-finding fixture against BARE `shellcheck -o all` (no
#                          ratchet) also REDs, AND so does the ORIGINAL unmodified fixture — i.e.
#                          bare enablement fails even the clean case. This is the exact defect the
#                          ratchet exists to remove: (1) proves the ratchet does not, (2r) proves
#                          bare enablement would have.
#   (3) FAIL CLOSED      — a missing baseline file is a REFUSAL (rc 2), never a silent pass.
#   (4) IMPROVEMENT OK   — fixing a baselined finding (count drops to 0) still passes; the ratchet
#                          only blocks increases, never requires decreases.
#
# Run:  bash fleet/tests/shellcheck-ratchet.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"     # .../fleet
RATCHET="$SRC/checks/shellcheck-ratchet.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

command -v shellcheck >/dev/null 2>&1 || { echo "SKIP: shellcheck not installed — cannot test the ratchet at all"; exit 0; }

# mk_fixture -> echoes a throwaway root dir with fleet/checks/ + fleet/one.sh (real findings:
# SC2168 'local' outside a function (error) + SC2250 style brace preference).
mk_fixture(){
  local d; d="$(mktemp -d)"
  mkdir -p "$d/fleet/checks"
  cat > "$d/fleet/one.sh" <<'SH'
#!/usr/bin/env bash
set -uo pipefail
local this_is_not_in_a_function=1
echo "$this_is_not_in_a_function"
SH
  printf '%s' "$d"
}

_run(){ SHELLCHECK_RATCHET_ROOT="$1" SHELLCHECK_RATCHET_SCAN_DIR="$1/fleet" \
        SHELLCHECK_RATCHET_BASELINE="$1/fleet/checks/shellcheck-baseline.tsv" \
        bash "$RATCHET" "$2"; }

# ---- (1) BASELINE FLOOR ------------------------------------------------------------------------
D1="$(mk_fixture)"
if _run "$D1" generate >/tmp/scr-gen.$$ 2>&1; then ok "(1a) generate succeeds over a real fixture with real findings"; else bad "(1a) generate: $(cat /tmp/scr-gen.$$)"; fi
[ -s "$D1/fleet/checks/shellcheck-baseline.tsv" ] && ok "(1b) baseline file written and non-empty" || bad "(1b) baseline missing/empty"
grep -q 'SC2168' "$D1/fleet/checks/shellcheck-baseline.tsv" 2>/dev/null && ok "(1c) the fixture's known error-level finding (SC2168) is IN the baseline" || bad "(1c) SC2168 missing from baseline"
if _run "$D1" check >/tmp/scr-c1.$$ 2>&1; then ok "(1d) unmodified fixture (findings == baseline) is CLEAN (rc 0)"; else bad "(1d) unmodified fixture REDs: $(cat /tmp/scr-c1.$$)"; fi

# ---- (2) NEW FINDING REDS ------------------------------------------------------------------------
D2="$(mk_fixture)"; _run "$D2" generate >/dev/null 2>&1
# Add a SECOND SC2168 instance (a genuinely new instance of an already-baselined code) — the
# ratchet is keyed on (file, code) COUNT, so a 1->2 increase must RED even though the code itself
# was already present at count 1.
cat >> "$D2/fleet/one.sh" <<'SH'
local another_one_not_in_a_function=2
SH
out="$(_run "$D2" check 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(2a) a SECOND instance of an already-baselined SC-code (1->2) REDs" || bad "(2a) count increase not caught: $out"
echo "$out" | grep -q 'SC2168' && ok "(2b) RED output names the offending SC-code" || bad "(2b) RED output silent on which code: $out"
echo "$out" | grep -q 'one\.sh' && ok "(2c) RED output names the offending file" || bad "(2c) RED output silent on which file: $out"

# A finding in a BRAND NEW file (implicit baseline of 0) must also RED — not just count-increases
# in already-tracked files.
D2B="$(mk_fixture)"; _run "$D2B" generate >/dev/null 2>&1
cat > "$D2B/fleet/two.sh" <<'SH'
#!/usr/bin/env bash
set -uo pipefail
local brand_new_file_violation=1
SH
out2b="$(_run "$D2B" check 2>&1)"; rc2b=$?
[ "$rc2b" -ne 0 ] && ok "(2d) a finding in a brand-new file (implicit baseline 0) REDs" || bad "(2d) new-file finding not caught: $out2b"
echo "$out2b" | grep -q 'two\.sh' && ok "(2e) RED output names the new file" || bad "(2e) new-file RED silent on filename: $out2b"

# ---- (2r) REVERT PROOF: bare enablement would have failed even the CLEAN case -------------------
# This is the exact automatic-reject failure the ratchet exists to prevent: bare `shellcheck -o
# all` treats EVERY pre-existing finding as a failure, so even an untouched, fully-baselined
# fixture REDs under bare enablement. The ratchet (1d above) does not. Both must be true for the
# ratchet to mean anything.
if ! shellcheck -o all "$D1/fleet/one.sh" >/dev/null 2>&1; then
  ok "(2r) REVERT PROOF: bare 'shellcheck -o all' (no ratchet) REDs on the SAME unmodified fixture that the ratchet (1d) passed — this is what bare enablement would have done to every PR"
else
  bad "(2r) bare shellcheck -o all unexpectedly passed the fixture — fixture no longer carries a real finding, test is not exercising anything"
fi

# ---- (3) FAIL CLOSED -----------------------------------------------------------------------------
D3="$(mk_fixture)"   # deliberately: no `generate` run, no baseline file
if _run "$D3" check >/tmp/scr-c3.$$ 2>&1; then bad "(3) missing baseline was treated as a silent PASS"; else
  rc3=$?
  [ "$rc3" -eq 2 ] && ok "(3) missing baseline is a REFUSAL (rc 2), distinct from 'new finding' (rc 1)" || bad "(3) missing baseline gave rc=$rc3, expected 2"
fi

# ---- (4) IMPROVEMENT OK ---------------------------------------------------------------------------
D4="$(mk_fixture)"; _run "$D4" generate >/dev/null 2>&1
: > "$D4/fleet/one.sh"   # the file that carried the baselined findings is now EMPTY — 0 findings
printf '#!/usr/bin/env bash\ntrue\n' > "$D4/fleet/one.sh"
if _run "$D4" check >/tmp/scr-c4.$$ 2>&1; then ok "(4) fixing every baselined finding (count -> 0) still passes; the ratchet never demands a decrease"; else bad "(4) improvement REDed: $(cat /tmp/scr-c4.$$)"; fi

rm -rf "$D1" "$D2" "$D2B" "$D3" "$D4" /tmp/scr-*.$$ 2>/dev/null

echo
echo "--- $PASS passed, $FAIL failed ---"
if [ "$FAIL" -eq 0 ]; then echo "ALL SHELLCHECK-RATCHET TESTS PASS"; exit 0; else echo "SHELLCHECK-RATCHET TESTS FAILED"; exit 1; fi
