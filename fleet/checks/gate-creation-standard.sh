#!/usr/bin/env bash
# gate-creation-standard.sh — META-GATE for GATE-CREATION-STANDARDIZE (operator directive).
# Doctrine: green-is-not-proof [[green-is-not-proof]]. A NEW/CHANGED gate (an entry in the
# product registry tools/gates.json, or a script under fleet/checks/) must carry EVIDENCE it
# meets fleet/GATE-CREATION-STANDARD.md — above all a RED-PROOF (a committed fail-on-revert
# test demonstrating the gate goes RED on a real failure) — or this meta-gate goes RED.
#
# Derived from fleet/state/GATE-GAP-LEDGER.tsv (the append-only ledger of green-gate
# misses). ANTI-ACCRETION: this COMPOSES existing lenses — the gates.json registry contract
# (id/red_proof fields), the fleet companion-test convention (fleet/tests/), and the ledger —
# it does NOT mint per-instance checker scripts; a new gate's own red-proof test IS its
# evidence.
#
# WHO IS AUDITED (META-GATE-CALLSITE-ENUM, 2026-07-24): the audited population used to be a
# DIRECTORY GLOB (`"$CHECKS_DIR"/*.sh|*.py`), so PLACEMENT WAS THE EXEMPTION — enforcement
# logic inlined in validate_board.sh / preflight.sh, a top-level fleet/*.sh, or a CI step was
# exempt with no override record and no signal. §B now enumerates by CALL SITE: the union of
# (a) fleet/checks/* and (b) every script INVOKED BY the rig's enforcement entrypoints
# (ENTRYPOINTS below). An inline enforcement block in validate_board.sh therefore pulls
# validate_board.sh ITSELF into the audited set. Exemptions are explicit NAMED lists that may
# only shrink, never an accident of where a file was put.
#
# What it enforces (each item names the GATE-CREATION-STANDARD.md item + ledger class):
#   * S1 RED-PROOFED  — every NON-grandfathered gates.json entry has a red_proof file that
#                       EXISTS; every NON-grandfathered audited script (fleet/checks/* OR a
#                       call-site member) has a companion test in fleet/tests/ carrying a
#                       red-proof/fail-on-revert marker.
#   * S2 NON-VACUOUS  — gates.json must be a non-empty registry; the ledger must have >0
#                       data rows; the CALL-SITE set must resolve to >0 paths (a gate that
#                       passes on zero items examined proves nothing).
#   * S3 UN-GAMED     — the baseline gate-id set, the baseline fleet/checks set and the
#                       call-site set cannot silently shrink (CALLSITE_MIN floor, and every
#                       named entrypoint must exist); the ledger row count cannot drop below
#                       its floor (append-only). Grandfather lists are EXPLICIT and frozen,
#                       and a grandfathered name that no longer exists is itself a RED.
#   * S5 FAIL-LOUD    — every audited *.sh carries `set -...uo pipefail` (fail-quiet-
#                       pipe-mask class: validate_board's historic green-on-double-claim).
#   * S10 TRACEABILITY— every ledger root_class appears in GATE-CREATION-STANDARD.md.
#
# Usage:
#   gate-creation-standard.sh check          HARD verdict. Exit 0 GREEN / 1 RED (names every
#                                            finding + the standard item it violates).
#   gate-creation-standard.sh scan           ADVISORY. Same findings as GATE-STANDARD-ADVISORY
#                                            lines, ALWAYS exit 0 — for validate_board-style
#                                            composition (advisory-first per the ticket). Also
#                                            reports its own wiring status HONESTLY (S8: no
#                                            claimed wiring that isn't real).
#   gate-creation-standard.sh append "<gates_green>" "<issue_shipped>" <root_class> \
#                                    "<gate_improvement>" "<status>"
#                                            Validated append to the GATE-GAP-LEDGER (stamps
#                                            date, rejects embedded tabs / unknown classes).
#                                            MANDATORY every time a green gate misses.
#
# Env seams (isolated self-test overrides; defaults are the real fleet/product):
#   GCS_FLEET GCS_PRODUCT_REPO GCS_GATES_JSON GCS_CHECKS_DIR GCS_TESTS_DIR GCS_LEDGER
#   GCS_STANDARD GCS_VALIDATE_BOARD GCS_LEDGER_MIN
#   GCS_REPO_ROOT GCS_ENTRYPOINTS GCS_CALLSITE_MIN
#   GCS_BASELINE_GATE_IDS GCS_GRANDFATHER_NO_REDPROOF GCS_BASELINE_CHECKS
#   GCS_GRANDFATHER_NO_TEST GCS_GRANDFATHER_NO_SETLINE
#   GCS_GRANDFATHER_CALLSITE_NO_TEST                     (space/comma-separated lists)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"      # fleet/ (script in fleet/checks/)
FLEET="${GCS_FLEET:-$HERE}"
PRODUCT_REPO="${GCS_PRODUCT_REPO:-/home/stack/code/charon}"
GATES_JSON="${GCS_GATES_JSON:-$PRODUCT_REPO/tools/gates.json}"
CHECKS_DIR="${GCS_CHECKS_DIR:-$FLEET/checks}"
TESTS_DIR="${GCS_TESTS_DIR:-$FLEET/tests}"
LEDGER="${GCS_LEDGER:-$FLEET/state/GATE-GAP-LEDGER.tsv}"
STANDARD="${GCS_STANDARD:-$FLEET/GATE-CREATION-STANDARD.md}"
VALIDATE_BOARD="${GCS_VALIDATE_BOARD:-$FLEET/validate_board.sh}"
LEDGER_MIN="${GCS_LEDGER_MIN:-8}"

# ---- call-site enumeration seams (§B0) ----
# ENUM_ROOT is the repo root the entrypoint patterns are relative to (fleet/ lives under it).
ENUM_ROOT="${GCS_REPO_ROOT:-$(cd "$FLEET/.." 2>/dev/null && pwd)}"
# ENTRYPOINTS: the FROZEN list of enforcement entrypoints whose invocations define membership.
# A pattern that matches NO file on disk is a RED (S3 UN-GAMED) — the node-set cannot shrink
# by an entrypoint quietly disappearing or being renamed.
ENTRYPOINTS="${GCS_ENTRYPOINTS-fleet/preflight.sh fleet/gate.sh fleet/land.sh fleet/land-push.sh fleet/validate_board.sh fleet/foreman.sh fleet/hooks/* fleet/watchdog/*.sh .github/workflows/*.yml}"
# CALLSITE_MIN: append-only floor, seeded 2026-07-24 from the MEASURED derived-set size (36).
CALLSITE_MIN="${GCS_CALLSITE_MIN:-36}"
# ---- frozen baselines + grandfather lists (S3 UN-GAMED: explicit, append-forbidden). ----
# Pre-standard gates are NAMED; anything new must arrive red-proofed. Removing a baseline
# member is itself a RED (the node-set cannot silently shrink).
BASELINE_GATE_IDS="${GCS_BASELINE_GATE_IDS:-boundary-check version-check ruff-lint mypy-type pytest validate-board check-arch check-decisions render-review-log gate-registry security-scan test-patterns charon-gate workflow-policy public-clean no-rig-import-check inert-code}"
GRANDFATHER_NO_REDPROOF="${GCS_GRANDFATHER_NO_REDPROOF:-version-check ruff-lint mypy-type pytest validate-board gate-registry charon-gate}"
BASELINE_CHECKS="${GCS_BASELINE_CHECKS:-base-integrity.sh bridge-health.py config-ssot-gate.sh gpt55-primary.sh no-anthropic-in-sg.sh no-claude-executor.sh parallelizability-gate.sh rule-sync.sh gate-creation-standard.sh}"
GRANDFATHER_NO_TEST="${GCS_GRANDFATHER_NO_TEST:-bridge-health.py gpt55-primary.sh no-anthropic-in-sg.sh no-claude-executor.sh}"
GRANDFATHER_NO_SETLINE="${GCS_GRANDFATHER_NO_SETLINE:-gpt55-primary.sh}"
# Call-site members that pre-date this enumerator and carry NO companion test at all. This
# list is the POINT of META-GATE-CALLSITE-ENUM: these were exempt by PLACEMENT (invisible,
# unrecorded, unbounded); they are now exempt by NAME (visible, recorded, bounded). Measured
# 2026-07-24 by execution. APPEND IS FORBIDDEN — the list may only SHRINK; a name that no
# longer exists on disk is a RED (stale exemption).
# DELIBERATELY NOT EXEMPTED: fleet/validate_board.sh — it is the TRIGGER INSTANCE of this
# class (the tier-drift enforcement block inlined into it, commit 0a759a8). Exempting the
# very escape this enumerator exists to close would re-hide it; it stays RED until it carries
# a red-proofed companion test.
GRANDFATHER_CALLSITE_NO_TEST="${GCS_GRANDFATHER_CALLSITE_NO_TEST-fleet/_lib.sh fleet/access-check.sh fleet/autonomous.sh fleet/capability/grades.py fleet/cg-drift.sh fleet/dark-work-check.sh fleet/handoff-check.sh fleet/land-needs-push.sh fleet/pending.sh fleet/project-audit.sh fleet/push-verify.sh fleet/reap-orphans.sh fleet/release.sh fleet/repo-registry.sh fleet/watchdog/discover-services.sh fleet/watchdog/generate-monit-config.sh fleet/watchdog/monit-selfwatch.sh fleet/watchdog/watchdog-lib.sh fleet/wci-contention.sh}"
REDS=()
red(){ REDS+=("$1"); }
in_list(){ # in_list <needle> <space/comma list>
  local n="$1" x
  for x in ${2//,/ }; do [ "$x" = "$n" ] && return 0; done
  return 1
}
norm(){ # normalize a check/test filename to a comparable stem
  local s; s="$(basename "$1")"
  s="${s%.test.sh}"; s="${s%.sh}"; s="${s%.py}"; s="${s#test_}"
  s="${s//[-_.]/}"
  printf '%s' "$s" | tr '[:upper:]' '[:lower:]'
}

# ===================== append mode (the mandated postmortem one-liner) =====================
if [ "${1:-check}" = "append" ]; then
  shift
  if [ $# -ne 5 ]; then
    echo "usage: gate-creation-standard.sh append \"<gates_green>\" \"<issue_shipped>\" <root_class> \"<gate_improvement>\" \"<status>\"" >&2
    exit 2
  fi
  gates_green="$1"; issue="$2"; klass="$3"; improve="$4"; status="$5"
  for f in "$gates_green" "$issue" "$klass" "$improve" "$status"; do
    [ -n "$f" ] || { echo "append: empty field refused (all 5 fields required)" >&2; exit 2; }
    case "$f" in *"$(printf '\t')"*) echo "append: embedded TAB refused (tabs are the column separator)" >&2; exit 2;; esac
  done
  if ! printf '%s' "$klass" | grep -qE '^[a-z0-9][a-z0-9-]*$'; then
    echo "append: root_class '$klass' must be a lowercase slug (a-z0-9-)" >&2; exit 2
  fi
  if ! grep -q -- "$klass" "$STANDARD" 2>/dev/null; then
    echo "append: root_class '$klass' is NOT traced in $STANDARD — add the class to the standard's checklist/traceability FIRST (a new class = a new standard item), then append" >&2
    exit 2
  fi
  [ -f "$LEDGER" ] || { echo "append: ledger $LEDGER not found" >&2; exit 2; }
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date +%F)" "$gates_green" "$issue" "$klass" "$improve" "$status" >> "$LEDGER"
  echo "appended: $(date +%F) [$klass] -> $LEDGER"
  exit 0
fi

MODE="${1:-check}"
case "$MODE" in check|scan) ;; *) echo "usage: gate-creation-standard.sh [check|scan|append ...]" >&2; exit 2;; esac

# ===================== A. product registry (tools/gates.json) =====================
if [ ! -f "$GATES_JSON" ]; then
  red "gates-registry-missing: $GATES_JSON not found (S2 NON-VACUOUS — an absent registry is a RED, not a pass)"
else
  while IFS= read -r line; do
    [ -n "$line" ] && red "$line"
  done < <(
    GCS_BASELINE_GATE_IDS="$BASELINE_GATE_IDS" GCS_GRANDFATHER_NO_REDPROOF="$GRANDFATHER_NO_REDPROOF" \
    python3 - "$GATES_JSON" "$PRODUCT_REPO" <<'PY'
import json, os, sys
path, repo = sys.argv[1], sys.argv[2]
baseline = set(os.environ["GCS_BASELINE_GATE_IDS"].replace(",", " ").split())
grandfathered = set(os.environ["GCS_GRANDFATHER_NO_REDPROOF"].replace(",", " ").split())
try:
    entries = json.load(open(path))
except Exception as e:
    print(f"gates-registry-unreadable: {path} — {e} (S5 FAIL-LOUD: unparseable registry is RED)")
    sys.exit(0)
if not isinstance(entries, list) or not entries:
    print(f"vacuous-registry: {path} has no gate entries (S2 NON-VACUOUS — a gate set of zero proves nothing)")
    sys.exit(0)
ids = {e.get("id", "") for e in entries}
for b in sorted(baseline):
    if b not in ids:
        print(f"gate-removed: baseline gate '{b}' vanished from {path} (S3 UN-GAMED — the node-set cannot silently shrink)")
for e in entries:
    gid = e.get("id", "<no-id>")
    if gid in grandfathered:
        continue
    rp = e.get("red_proof")
    if not rp:
        print(f"unproofed-gate: '{gid}' has no red_proof (S1 RED-PROOFED — a NEW gate must carry a fail-on-revert test proving it goes RED on a real failure; see fleet/GATE-CREATION-STANDARD.md)")
    elif not os.path.exists(os.path.join(repo, rp)):
        print(f"red-proof-missing-file: '{gid}' names red_proof '{rp}' which does not exist (S1/S8 ARTIFACT-VERIFIED — a claimed proof that isn't in the tree is a self-report-lie)")
PY
  )
fi

# ============ B0. CALL-SITE enumeration (who is audited is decided by INVOCATION) ==========
# The audited population is derived from what the frozen enforcement entrypoints actually
# INVOKE, not from where a file happens to live. A mention inside a comment is not an
# invocation; the rig's own test suite is excluded (tests are the PROOFS, not the gates —
# their reachability is META-GATE-REDPROOF-REACHABLE, leg ii).
CALLSITE=()
while IFS=$'\t' read -r kind payload; do
  case "$kind" in
    RED)  [ -n "$payload" ] && red "$payload" ;;
    PATH) [ -n "$payload" ] && CALLSITE+=("$payload") ;;
  esac
done < <(
  GCS_ENTRYPOINTS_RESOLVED="$ENTRYPOINTS" \
  python3 - "$ENUM_ROOT" "$FLEET" "$TESTS_DIR" <<'PY'
import glob, os, re, sys
root, fleet, tests_dir = sys.argv[1], sys.argv[2], sys.argv[3]
patterns = os.environ["GCS_ENTRYPOINTS_RESOLVED"].replace(",", " ").split()
eps = []
for pat in patterns:
    hits = sorted(p for p in glob.glob(os.path.join(root, pat)) if os.path.isfile(p))
    if not hits:
        print("RED\tentrypoint-missing: enforcement entrypoint '%s' matches no file under %s "
              "(S3 UN-GAMED — the call-site node-set cannot shrink by an entrypoint quietly "
              "vanishing or being renamed)" % (pat, root))
    eps += hits
# index every candidate script under fleet/, EXCLUDING the test suite
idx = {}
tests_dir = os.path.normpath(tests_dir)
for dp, dn, fn in os.walk(fleet):
    if dp == tests_dir or dp.startswith(tests_dir + os.sep) or "__pycache__" in dp:
        continue
    for f in sorted(fn):
        if f.endswith((".sh", ".py")):
            idx.setdefault(f, os.path.join(dp, f))
TOK = re.compile(r"[A-Za-z0-9_.${}/\\-]*\.(?:sh|py)")
out = set()
for e in eps:
    try:
        lines = open(e, errors="replace").read().splitlines()
    except OSError as ex:
        print("RED\tentrypoint-unreadable: %s — %s (S5 FAIL-LOUD — an unreadable entrypoint is "
              "RED, not a silent skip)" % (e, ex))
        continue
    for line in lines:
        if line.lstrip().startswith("#"):
            continue        # a mention in a comment is not an invocation
        for m in TOK.finditer(line):
            b = os.path.basename(m.group(0))
            if "*" in b or b.endswith(".test.sh") or b.startswith("test_"):
                continue
            p = idx.get(b)
            if p:
                out.add(os.path.relpath(p, root))
for p in sorted(out):
    print("PATH\t" + p)
PY
)
# S2 NON-VACUOUS / S3 UN-GAMED on the derived set itself: a run that examined ZERO call sites
# must NEVER be green, and the set may not silently shrink below its measured floor.
if [ "${#CALLSITE[@]}" -eq 0 ]; then
  red "callsite-enum-vacuous: the enforcement-entrypoint scan of $ENUM_ROOT resolved ZERO invoked scripts (S2 NON-VACUOUS — a meta-gate that examined nothing proves nothing; check GCS_ENTRYPOINTS/GCS_REPO_ROOT)"
elif [ "${#CALLSITE[@]}" -lt "$CALLSITE_MIN" ]; then
  red "callsite-set-shrunk: call-site set has ${#CALLSITE[@]} paths, floor is $CALLSITE_MIN (S3 UN-GAMED — the audited population is append-only; enforcement cannot be removed from the entrypoints to escape the audit)"
fi
# Frozen exemptions must stay REAL: a grandfathered name that no longer exists is a stale
# exemption, and stale exemptions are how a shrink-only list silently grows.
for g in ${GRANDFATHER_CALLSITE_NO_TEST//,/ }; do
  [ -e "$ENUM_ROOT/$g" ] || red "stale-exemption: GRANDFATHER_CALLSITE_NO_TEST names '$g' which no longer exists under $ENUM_ROOT (S3 UN-GAMED — remove it from the frozen list; the list may only SHRINK)"
done

# ===================== B. audited gates (fleet/checks/* UNION the call sites) ===============
AUDIT=()            # "<origin>|<display>|<abs path>"
CHECK_NAMES=""
if [ ! -d "$CHECKS_DIR" ]; then
  red "checks-dir-missing: $CHECKS_DIR not found (S2 NON-VACUOUS)"
else
  for b in ${BASELINE_CHECKS//,/ }; do
    [ -e "$CHECKS_DIR/$b" ] || red "check-removed: baseline fleet check '$b' vanished from $CHECKS_DIR (S3 UN-GAMED — the node-set cannot silently shrink)"
  done
  for f in "$CHECKS_DIR"/*.sh "$CHECKS_DIR"/*.py; do
    [ -e "$f" ] || continue
    CHECK_NAMES="$CHECK_NAMES $(basename "$f")"
    AUDIT+=("checks|$(basename "$f")|$f")
  done
fi
for rel in ${CALLSITE[@]+"${CALLSITE[@]}"}; do
  abs="$ENUM_ROOT/$rel"
  [ -e "$abs" ] || continue
  in_list "$(basename "$abs")" "$CHECK_NAMES" && continue   # already audited as a fleet check
  AUDIT+=("callsite|$rel|$abs")
done

# companion-test stems, computed ONCE (the matcher itself is unchanged: norm + in_list).
TEST_PATHS=(); TEST_STEMS=()
for t in "$TESTS_DIR"/*.sh "$TESTS_DIR"/*.py; do
  [ -e "$t" ] || continue
  TEST_PATHS+=("$t"); TEST_STEMS+=("$(norm "$t")")
done

for entry in ${AUDIT[@]+"${AUDIT[@]}"}; do
  origin="${entry%%|*}"; rest="${entry#*|}"; disp="${rest%%|*}"; f="${rest#*|}"
  name="$(basename "$f")"
  # S5 FAIL-LOUD (shell): must fail loud — set -uo pipefail (validate_board's historic
  # pipe-mask green-on-double-claim is the ledger class this closes).
  case "$name" in
    *.sh)
      if ! in_list "$name" "$GRANDFATHER_NO_SETLINE" && \
         ! grep -qE '^[[:space:]]*set[[:space:]]+-[A-Za-z]*u[A-Za-z]*o[[:space:]]+pipefail' "$f"; then
        red "fail-quiet: $disp lacks 'set -...uo pipefail' (S5 FAIL-LOUD — fail-quiet-pipe-mask class)"
      fi
      ;;
  esac
  # S1 RED-PROOFED: companion test in fleet/tests/ with a red-proof/fail-on-revert marker.
  if [ "$origin" = "checks" ]; then
    in_list "$name" "$GRANDFATHER_NO_TEST" && continue
  else
    in_list "$disp" "$GRANDFATHER_CALLSITE_NO_TEST" && continue
  fi
  cstem="$(norm "$name")"
  companion=""
  i=0
  while [ "$i" -lt "${#TEST_PATHS[@]}" ]; do
    tstem="${TEST_STEMS[$i]}"
    if [ "$tstem" = "$cstem" ] || [ "$tstem" = "${cstem%gate}" ] || { [ -n "$cstem" ] && case "$tstem" in *"$cstem"*) true;; *) false;; esac; }; then
      companion="${TEST_PATHS[$i]}"; break
    fi
    i=$((i+1))
  done
  if [ -z "$companion" ]; then
    if [ "$origin" = "checks" ]; then
      red "no-red-proof-test: $name has no companion test in $TESTS_DIR (S1 RED-PROOFED — a gate that has never been seen RED proves nothing green)"
    else
      red "unaudited-callsite: $disp is invoked by an enforcement entrypoint but has no companion test in $TESTS_DIR and no named exemption (S1 RED-PROOFED — enforcement is audited by CALL SITE now; placing it outside fleet/checks/ is no longer an exemption)"
    fi
  elif ! grep -qiE 'red-proof|fail-on-revert' "$companion"; then
    red "no-red-proof-marker: $(basename "$companion") covers $disp but carries no red-proof/fail-on-revert case marker (S1 RED-PROOFED — the test must demonstrate the RED path, not just the green one)"
  fi
done

# ===================== C. the ledger (fleet/state/GATE-GAP-LEDGER.tsv) =====================
if [ ! -f "$LEDGER" ]; then
  red "ledger-missing: $LEDGER not found (S10 CLASS-COVERAGE — the miss history IS the standard's input)"
else
  rows=0; lineno=0
  while IFS= read -r line; do
    lineno=$((lineno+1))
    case "$line" in ''|'#'*|date"$(printf '\t')"*) continue;; esac
    rows=$((rows+1))
    ncols="$(printf '%s\n' "$line" | awk -F'\t' '{print NF}')"
    if [ "$ncols" -ne 6 ]; then
      red "ledger-malformed: $LEDGER line $lineno has $ncols columns, expected 6 (S5 FAIL-LOUD — a malformed row is a HARD ERROR, not a silent skip)"
      continue
    fi
    klass="$(printf '%s\n' "$line" | awk -F'\t' '{print $4}')"
    if [ -f "$STANDARD" ] && ! grep -q -- "$klass" "$STANDARD"; then
      red "class-untraced: ledger root_class '$klass' (line $lineno) maps to NO item in $STANDARD (S10 CLASS-COVERAGE — every ledger class must trace to a standard item)"
    fi
  done < "$LEDGER"
  if [ "$rows" -eq 0 ]; then
    red "ledger-vacuous: $LEDGER has zero data rows (S2 NON-VACUOUS — seed it; a gate standard derived from nothing proves nothing)"
  elif [ "$rows" -lt "$LEDGER_MIN" ]; then
    red "ledger-shrunk: $LEDGER has $rows rows, floor is $LEDGER_MIN (S3 UN-GAMED — the ledger is APPEND-ONLY; rows never disappear)"
  fi
fi

# ===================== D. the standard document itself =====================
if [ ! -f "$STANDARD" ]; then
  red "standard-missing: $STANDARD not found"
else
  for item in RED-PROOFED NON-VACUOUS UN-GAMED NOT-INERT FAIL-LOUD DETERMINISTIC CONTEXT-OF-VALIDITY ARTIFACT-VERIFIED VERIFY-EFFECT CLASS-COVERAGE; do
    grep -q -- "$item" "$STANDARD" || red "standard-item-missing: $STANDARD lacks the '$item' checklist item (S3 UN-GAMED — the checklist cannot silently shrink)"
  done
fi

# ===================== verdict =====================
ADVISORIES=()
if [ -f "$VALIDATE_BOARD" ] && ! grep -q "gate-creation-standard" "$VALIDATE_BOARD"; then
  ADVISORIES+=("not-wired: validate_board.sh does not yet run this meta-gate's scan — see fleet/GATE-CREATION-STANDARD.md 'Wiring status' for the one-liner (reported honestly per S8; owned by another ticket)")
fi

if [ "$MODE" = "scan" ]; then
  for a in ${ADVISORIES[@]+"${ADVISORIES[@]}"}; do echo "GATE-STANDARD-ADVISORY: $a"; done
  for r in ${REDS[@]+"${REDS[@]}"};           do echo "GATE-STANDARD-ADVISORY: $r"; done
  echo "== GATE-STANDARD scan: ${#REDS[@]} finding(s) (advisory — always exit 0) =="
  exit 0
fi

echo "== gate-creation-standard =="
for a in ${ADVISORIES[@]+"${ADVISORIES[@]}"}; do echo "  ADVISORY $a"; done
for r in ${REDS[@]+"${REDS[@]}"};           do echo "  RED  $r"; done
if [ "${#REDS[@]}" -eq 0 ]; then
  echo "  GREEN every gate meets fleet/GATE-CREATION-STANDARD.md (red-proofed, non-vacuous, un-gamed, fail-loud, ledger traced)"
  exit 0
fi
echo "  RED  ${#REDS[@]} finding(s) — a new/changed gate must carry its evidence (see fleet/GATE-CREATION-STANDARD.md)"
exit 1
