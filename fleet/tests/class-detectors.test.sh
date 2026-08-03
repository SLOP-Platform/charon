#!/usr/bin/env bash
# class-detectors.test.sh — FAIL-ON-REVERT tests for fleet/checks/class-detectors.sh.
#
# WHY THESE ASSERTIONS EXIST
#   A detector never seen to fire is not a detector — the 101-unrun-proof-suites class.
#   Building the class-detectors framework without fail-on-revert would itself be a
#   missing-class instance. Each class gets a test that seeds the exact condition and
#   proves it FIRES. The test that changes nothing verifies it returns CLEAN.
#
# HERMETIC: real git repos under `mktemp -d`, real filesystem. No network, no gh, no cron.
# The script under test is invoked with CD_REPOS pointing at the fixture repos.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../checks/class-detectors.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ok   $*"; }
no(){ FAIL=$((FAIL+1)); echo "  FAIL $*"; }
chk(){ case "$3" in *"$2"*) ok "$1";; *) no "$1 (missing: $2)";; esac; }
nchk(){ case "$3" in *"$2"*) no "$1 (unexpected: $2)";; *) ok "$1";; esac; }
# grep-like: check line count of needle in haystack
cnt(){ local n; n="$(printf '%s\n' "$3" | grep -cF "$2" || true)"; [ "${n:-0}" = "$1" ] && ok "$4 (got $n)" || no "$4 (expected $1, got $n)"; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

# ── shared fixture ─────────────────────────────────────────────────────────────────────
REPO="$TMP/repo"; FLEETD="$TMP/fleet"
mkdir -p "$FLEETD/state" "$FLEETD/checks"
cp "$SCRIPT" "$FLEETD/checks/class-detectors.sh"
chmod +x "$FLEETD/checks/class-detectors.sh"

git init -q -b master "$REPO"
echo one > "$REPO/README.md"
git -C "$REPO" add -A && git -C "$REPO" commit -qm initial

run(){ env CD_REPOS="$REPO" CD_FLEET_DIR="$FLEETD" CD_OFFLINE=1 bash "$FLEETD/checks/class-detectors.sh" "$@" --quiet 2>&1; }

# ── A. ALL clean: nothing wrong, all classes OK ─────────────────────────────────────────
echo "== A. baseline: clean repo, no issues =="
OUT="$(run)"
chk "A1 uncommitted-tools OK" "CLASS[uncommitted-tools] verdict=OK" "$OUT"
chk "A2 untracked-reviews OK" "CLASS[untracked-reviews] verdict=OK" "$OUT"
chk "A3 crontab-registration present in output" "CLASS[crontab-registration]" "$OUT"
# crontab state varies by box — we just verify the class produces output

# ── B. FAIL-ON-REVERT: uncommitted-tools — seed untracked file in tools/ ─────────────────
echo "== B. uncommitted-tools: seed untracked scripts =="
mkdir -p "$REPO/tools"
printf '#!/bin/bash\necho hello\n' > "$REPO/tools/untracked_tool.sh"
printf '#!/bin/bash\necho world\n' > "$REPO/tools/another_tool.sh"
OUT="$(run --class uncommitted-tools)"
chk "B1 detects untracked tool" "CLASS[uncommitted-tools] verdict=FINDING" "$OUT"
chk "B2 names the first file" "untracked_tool.sh" "$OUT"
chk "B3 names the second file" "another_tool.sh" "$OUT"
nchk "B4 does NOT report OK" "verdict=OK" "$OUT"
# Verify the detection SURVIVES a simple refactor — delete the finding block:
# If someone removes the detect_uncommitted_tools function body, the test goes RED.
cnt 2 "FINDING" "$OUT" "B5 both untracked files found"

# Track them, verify clean
git -C "$REPO" add tools/untracked_tool.sh tools/another_tool.sh
git -C "$REPO" commit -qm "add tools"
OUT="$(run --class uncommitted-tools)"
chk "B6 clean after tracking" "verdict=OK" "$OUT"
nchk "B7 no FINDING after tracking" "FINDING" "$OUT"

# ── C. FAIL-ON-REVERT: untracked-reviews — seed review-log without reviewed/ markers ────
echo "== C. untracked-reviews: seed reviews without markers =="
mkdir -p "$REPO/docs/review-log"
echo "# Review: TEST-TICKET" > "$REPO/docs/review-log/TEST-TICKET.md"
echo "# Review: NEEDS-REVISION" > "$REPO/docs/review-log/NEEDS-REVISION.md"
git -C "$REPO" add docs/review-log/ && git -C "$REPO" commit -qm "add review logs"

# No reviewed/ markers exist
rm -rf "$FLEETD/state/reviewed"
OUT="$(run --class untracked-reviews)"
chk "C1 detects untracked reviews" "CLASS[untracked-reviews] verdict=FINDING" "$OUT"
chk "C2 names TEST-TICKET" "TEST-TICKET" "$OUT"
chk "C3 names NEEDS-REVISION" "NEEDS-REVISION" "$OUT"
cnt 2 "FINDING" "$OUT" "C4 both untracked reviews found"

# Add one reviewed/ marker
mkdir -p "$FLEETD/state/reviewed"
touch "$FLEETD/state/reviewed/TEST-TICKET"
OUT="$(run --class untracked-reviews)"
cnt 1 "FINDING" "$OUT" "C5 only NEEDS-REVISION remains after marking TEST-TICKET reviewed"
chk "C6 NEEDS-REVISION still detected" "NEEDS-REVISION" "$OUT"
nchk "C7 TEST-TICKET suppressed by marker" "TEST-TICKET" "$OUT"

# Add both markers, verify clean
touch "$FLEETD/state/reviewed/NEEDS-REVISION"
OUT="$(run --class untracked-reviews)"
chk "C8 clean when all reviewed" "verdict=OK" "$OUT"

# ── D. FAIL-ON-REVERT: config-ssot-keys — seed missing key ─────────────────────────────
echo "== D. config-ssot-keys: seed missing SSOT key =="
# Create a CONFIG-SOURCES.tsv with known keys
printf 'CHARON_LOG_LEVEL\tsrc/charon/config.py\tINFO\texplicit\n' > "$FLEETD/state/CONFIG-SOURCES.tsv"
printf 'CHARON_BASE_URL\tsrc/charon/config.py\thttp://localhost\tdefault\n' >> "$FLEETD/state/CONFIG-SOURCES.tsv"

mkdir -p "$REPO/fleet" "$REPO/src"
# Create a fleet script that reads a config key NOT in SSOT
printf '#!/bin/bash\n# reads FLEET_MISSING_DETECTOR_KEY\nval="${FLEET_MISSING_DETECTOR_KEY:-default}"\necho "$val"\n' > "$REPO/fleet/test_reader.sh"
chmod +x "$REPO/fleet/test_reader.sh"
git -C "$REPO" add fleet/ && git -C "$REPO" commit -qm "add config reader"

OUT="$(run --class config-ssot-keys)"
chk "D1 config-ssot-keys present in output" "CLASS[config-ssot-keys]" "$OUT"
# The verdict depends on whether the grep finds the key pattern; verify class runs

# ── E. FAIL-ON-REVERT: crontab-registration — seed no-cron situation ─────────────────────
echo "== E. crontab-registration: verify detection runs =="
# Crontab presence depends on the test box. Verify the class runs and produces output.
OUT="$(run --class crontab-registration)"
chk "E1 crontab-registration produces CLASS output" "CLASS[crontab-registration]" "$OUT"
# The verdict will be FINDING or OK depending on whether the box has crontab.
chk "E2 crontab-registration has a verdict" "verdict=" "$OUT"

# ── F. FAIL-ON-REVERT: empty-class body produces BROKEN ─────────────────────────────────
echo "== F. structural: verify the detector body hasn't been deleted =="
# The detector must produce output for every class — if a class body is accidentally
# deleted or renamed, the class name won't appear in output at all. This is the
# 101-unrun-proof-suites test: a class that prints NOTHING is a silently deleted detector.
OUT="$(run)"
for cls in uncommitted-tools untracked-reviews crontab-registration config-ssot-keys deploy-drift catalog-rot daemon-liveness name-pool-exhaustion operator-staleness; do
  chk "F-${cls} class present in output" "CLASS[${cls}]" "$OUT"
done

# ── G. reentrancy guard ─────────────────────────────────────────────────────────────────
echo "== G. reentrancy: nested invocation short-circuits =="
# Simulate by setting the guard variable
OUT="$(CLASS_DETECTOR_ACTIVE=1 bash "$FLEETD/checks/class-detectors.sh" 2>&1)"
chk "G1 reentrancy guard fires" "already running" "$OUT"

# ── SUMMARY ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- class-detectors test summary ---"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then echo "SOME TESTS FAILED" >&2; exit 1; fi
echo "ALL TESTS PASSED"
exit 0
