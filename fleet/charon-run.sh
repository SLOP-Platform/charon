#!/usr/bin/env bash
# charon-run.sh <cwd> <outlog> <brief-file> <model1> [model2 ...]
# Headless opencode against the Charon gateway with CROSS-MODEL failover.
# Charon already fails over across PROVIDERS for one model id; this adds failover
# across MODELS when one is exhausted across all its providers (session/rate limit).
# Zero Claude limit (all models are non-Claude on the 4-LOM gateway).
set -u
PFR_DEBUG="${PFR_DEBUG:-0}"
dbg() { [ "$PFR_DEBUG" = "1" ] && printf '[charon-run][DEBUG] %s\n' "$*" >&2; return 0; }
CWD="$1"; OUT="$2"; BRIEF="$3"; shift 3
MODELS=("$@")
PROMPT="$(cat "$BRIEF")"
dbg "invoked: cwd=$CWD out=$OUT brief=$BRIEF models=[${MODELS[*]}]"
: > "$OUT"
LABEL=$(basename "$OUT" .txt)
LEDGER="${CHARON_EXHAUST_LEDGER:-/home/stack/charon-private/fleet/provider-exhaustion-ledger.tsv}"
if [ ! -f "$LEDGER" ]; then
  printf 'ts\tjob\tmodel\tevent\tnote\n' > "$LEDGER" 2>/dev/null || true
fi
 led() { printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$LABEL" "$1" "$2" "$3" >> "$LEDGER" 2>/dev/null || true; }
for M in "${MODELS[@]}"; do
  echo "===== [charon-run] attempt: charon/$M @ $(basename "$CWD") =====" >> "$OUT"
  MARK=$(wc -l < "$OUT")
  dbg "attempt model=charon/$M cwd=$CWD cmd: timeout 1800 opencode run --model charon/$M <PROMPT, ${#PROMPT} bytes>"
  # `</dev/null`: this subprocess must NEVER read stdin. When this script is
  # invoked from preflight.sh's per-task `while read` loop, an inherited,
  # unbounded stdin here is what silently truncates that loop to ONE task
  # (see preflight.sh's fd-3 fix + comment) — belt-and-suspenders even when
  # invoked standalone (headless run should never block on / consume tty
  # input either).
  ( cd "$CWD" && timeout 1800 opencode run --model "charon/$M" "$PROMPT" ) </dev/null >> "$OUT" 2>&1
  RC=$?
  dbg "attempt model=charon/$M exit_code=$RC"
  TAIL=$(tail -n +"$MARK" "$OUT")
  # Hard failure OR limit-signal in this attempt's tail -> fail over to next model.
  if printf '%s' "$TAIL" | grep -qiE '\b429\b|rate.?limit|quota exceeded|insufficient (funds|credit|balance)|session limit|no capacity|model (is )?(over|exhausted)|out of (credit|quota)'; then
    echo "[charon-run] model '$M' hit a provider/session LIMIT -> failing over" >> "$OUT"
    led "$M" "limit-failover" "rc=$RC; all providers for this model exhausted at gateway"
    continue
  elif [ "$RC" -ne 0 ]; then
    echo "[charon-run] model '$M' exited nonzero (rc=$RC, not a limit) -> failing over" >> "$OUT"
    led "$M" "error-failover" "rc=$RC; non-limit failure"
    continue
  fi
  echo "[charon-run] SUCCESS on model '$M' (rc=0)" >> "$OUT"
  echo "CHARON_RUN_RESULT=SUCCESS model=$M" >> "$OUT"
  exit 0
done
echo "[charon-run] ALL MODELS EXHAUSTED: ${MODELS[*]}" >> "$OUT"
led "${MODELS[*]}" "ALL-EXHAUSTED" "every model failed over; POOL TOO THIN -> consider adding providers"
echo "CHARON_RUN_RESULT=EXHAUSTED" >> "$OUT"
exit 3
