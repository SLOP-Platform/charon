#!/usr/bin/env bash
# test_detention.sh — FAIL-ON-REVERT tests for DETENTION-REDLINE (scorecard -> assignment guardrail).
#
# Proves the REAL production path: model-detention.sh's redline computation AND fleet-droid.sh's
# per-ticket chain filter (exercised via `fleet-droid.sh resolve <tier> <ticket>`, which runs the
# SAME helpers the claim loop uses — production path == test path).
#
# Every test runs over a FIXTURE ledger (a temp tsv) + fixture tier-models + fixture ticket files.
# It NEVER touches the live grader-owned model-scorecard.tsv (that stays 0644, bench-grader-owned).
# The fixtures are injected via CHARON_SCORECARD_TSV / CHARON_TIER_MODELS — the scripts under test
# are the REAL ones in fleet/.
#
# Coverage (each goes RED if the corresponding logic is reverted):
#   (1) FABRICATION (gate=pass AND verdict=BLOCK) for M/money-path -> `check M money-path` exits 3
#       AND fleet-droid's resolved chain for a money-path ticket EXCLUDES M.
#   (2) a clean model N is NOT excluded -> `check N money-path` exits 0 AND N stays in the chain.
#   (3) work_class SCOPING — M detained on money-path is still eligible for ci-infra (exit 0) AND
#       stays in the chain for a ci-infra ticket.
#   (4) BLOCK-RATE ADVISORY (>=50% over n>=3, no fabrication) -> `check ADV routing` exits 1 but is
#       NOT filtered out of the chain while advisory.
#   (5) PAROLE — 2 consecutive MERGE after a fabrication restores eligibility (exit 0). [bonus]
#   (6) FAIL-LOUD — a wholly HARD-detained chain makes `resolve` exit 7 (never a silent run). [bonus]
#
# Run:  bash fleet/tests/test_detention.sh    (exit 0 = all pass, 1 = a failure)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the real fleet/ dir
DET="$SRC/model-detention.sh"
DROID="$SRC/fleet-droid.sh"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
eq(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
# exit code of `model-detention.sh check <model> <wc>` (0/1/3), set +e-guarded
check_rc(){ local rc; set +e; bash "$DET" check "$1" "$2" >/dev/null 2>&1; rc=$?; set -e; echo "$rc"; }
# resolved (post-detention-filter) chain for a tier+ticket via the REAL fleet-droid resolve hook
resolve_chain(){ bash "$DROID" resolve "$1" "$2" 2>/dev/null; }
# resolve exit code (7 = whole chain HARD-detained), set +e-guarded
resolve_rc(){ local rc; set +e; bash "$DROID" resolve "$1" "$2" >/dev/null 2>&1; rc=$?; set -e; echo "$rc"; }
# does a comma chain contain an exact model id?
in_chain(){ case ",$1," in *",$2,"*) echo yes;; *) echo no;; esac; }

# ---- build the fixture world -------------------------------------------------------------------
D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
LED="$D/model-scorecard.tsv"           # FIXTURE ledger — never the live one
TIERS="$D/tier-models.tsv"             # FIXTURE tier chain
export CHARON_SCORECARD_TSV="$LED"
export CHARON_TIER_MODELS="$TIERS"

# tier chain contains M (fabricator), N (clean), ADV (advisory), and a clean tail.
printf '# fixture tier-models\nfrontier\tM,N,ADV,kimi-k2.6\n' > "$TIERS"
# an all-detained tier for the fail-loud test.
printf 'strong\tM,BADD\n' >> "$TIERS"

# ledger header + rows. Columns: date source ref work_class tier model verdict gate score
#   time_s cost_usd corrections note
printf '# fixture ledger (fail-on-revert) — NOT the grader-owned tsv\n' > "$LED"
# M: FABRICATION on money-path (gate=pass AND verdict=BLOCK)
printf '2026-07-05\tlive\tf1\tmoney-path\t-\tM\tBLOCK\tpass\t-\t-\t-\t-\tgreen-but-fake\n' >> "$LED"
# M: a clean MERGE on ci-infra (work_class scoping — still eligible there)
printf '2026-07-05\tlive\tc1\tci-infra\t-\tM\tMERGE\tpass\t-\t-\t-\t-\tclean docker fix\n' >> "$LED"
# N: clean MERGE on money-path (must stay eligible)
printf '2026-07-05\tlive\tn1\tmoney-path\t-\tN\tMERGE\tpass\t-\t-\t-\t-\tclean\n' >> "$LED"
# ADV: block-rate advisory on money-path — 2 BLOCK (gate=fail, NOT fabrication) + 1 FIXES = 66%, n=3
printf '2026-07-05\tlive\ta1\tmoney-path\t-\tADV\tBLOCK\tfail\t-\t-\t-\t-\tfailed gate\n' >> "$LED"
printf '2026-07-06\tlive\ta2\tmoney-path\t-\tADV\tBLOCK\tfail\t-\t-\t-\t-\tfailed gate\n' >> "$LED"
printf '2026-07-07\tlive\ta3\tmoney-path\t-\tADV\tFIXES\tfail\t-\t-\t-\t-\tneeded fixes\n' >> "$LED"
# BADD: fabrication on money-path (used only for the all-detained fail-loud test)
printf '2026-07-05\tlive\tb1\tmoney-path\t-\tBADD\tBLOCK\tpass\t-\t-\t-\t-\tfake\n' >> "$LED"
# PAR: fabrication then 2 consecutive MERGE on money-path -> paroled
printf '2026-07-05\tlive\tp1\tmoney-path\t-\tPAR\tBLOCK\tpass\t-\t-\t-\t-\tfake\n' >> "$LED"
printf '2026-07-06\tlive\tp2\tmoney-path\t-\tPAR\tMERGE\tpass\t-\t-\t-\t-\tclean\n' >> "$LED"
printf '2026-07-07\tlive\tp3\tmoney-path\t-\tPAR\tMERGE\tpass\t-\t-\t-\t-\tclean\n' >> "$LED"

# fixture tickets (only the fields the filter reads: tier + work_class)
MP="$D/ticket-money.md"; printf 'tier: frontier\nwork_class: money-path\n' > "$MP"
CI="$D/ticket-ci.md";    printf 'tier: frontier\nwork_class: ci-infra\n'    > "$CI"

echo "== (1) FABRICATION -> HARD detain + excluded from money-path chain =="
eq "1a check M money-path exits 3 (HARD)" "$(check_rc M money-path)" "3"
mp_chain="$(resolve_chain frontier "$MP")"
eq "1b fleet-droid money-path chain EXCLUDES M" "$(in_chain "$mp_chain" M)" "no"

echo "== (2) clean model N NOT excluded =="
eq "2a check N money-path exits 0 (eligible)" "$(check_rc N money-path)" "0"
eq "2b N stays in the money-path chain" "$(in_chain "$mp_chain" N)" "yes"

echo "== (3) work_class SCOPING — M detained on money-path is eligible for ci-infra =="
eq "3a check M ci-infra exits 0 (scoped, not a global ban)" "$(check_rc M ci-infra)" "0"
ci_chain="$(resolve_chain frontier "$CI")"
eq "3b M stays in the ci-infra chain" "$(in_chain "$ci_chain" M)" "yes"

echo "== (4) BLOCK-RATE ADVISORY — flagged (exit 1) but NOT filtered while advisory =="
eq "4a check ADV money-path exits 1 (advisory)" "$(check_rc ADV money-path)" "1"
eq "4b ADV stays in the money-path chain (advisory != excluded)" "$(in_chain "$mp_chain" ADV)" "yes"

echo "== (5) PAROLE — 2 consecutive MERGE after fabrication restores eligibility [bonus] =="
eq "5a check PAR money-path exits 0 (paroled)" "$(check_rc PAR money-path)" "0"

echo "== (6) FAIL-LOUD — a wholly HARD-detained chain makes resolve exit 7 [bonus] =="
# strong tier = M,BADD, both fabricators on money-path -> whole chain detained
MP2="$D/ticket-money2.md"; printf 'tier: strong\nwork_class: money-path\n' > "$MP2"
eq "6a resolve exits 7 when every model is HARD-detained" "$(resolve_rc strong "$MP2")" "7"

echo "-----"
echo "detention tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
