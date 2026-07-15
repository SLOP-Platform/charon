#!/usr/bin/env bash
# leg-preflight.sh — STAGE-1 due-diligence gate (LEG-PREFLIGHT-CANARY).
#
# A FAST (seconds, not minutes) per-(model,LEG) canary that proves a leg is
# reachable + actually SERVES a working model (not a stub/degraded/wrong
# model) + measures performance, so we RANK legs and only send the expensive
# full honest-battery/dogfood (8-min budget) to legs that pass. Motivating
# waste (2026-07-15): minimax-m2.7 burned ~24min (3x8min rc=124 hangs) on a
# dead leg with NO pre-check; NVIDIA NIM was proven healthy in ~7s by the
# prototype canary this script promotes.
#
# Design of record: fleet/board/LEG-PREFLIGHT-CANARY.md. Reference impl:
# fleet/state/leg-canary-prototype.py. Review add-ons this build satisfies:
# fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md F6 (leg-pinning end-to-end)
# and F14 (sandbox the exec-check).
#
# ── LEG-PINNING (F6) ─────────────────────────────────────────────────────────
# The ranking harnesses call BASE pool ids (e.g. "deepseek-v4-pro") which the
# gateway routes to whichever provider is cheapest-available that moment and
# fails over across providers INSIDE that one id — so a base-pool id can
# NEVER be pinned to a single leg, and any rank collected against one is an
# average over whatever served (dogfood-eval.sh:328 admits this). The ONLY
# leg-pinned mechanism today is a provider-suffixed / vendor-namespaced id
# whose gateway-side pool has exactly ONE provider — the existing
# "-ds"/"-cb"/"-together" aliases (opencode.json) and vendor-namespaced ids
# like "nvidia/…" (leg-canary-prototype.py:11-12). This script PINS by
# sending that id VERBATIM as the request's "model" field — never stripped,
# never normalized to a base id — so the request can only be served by that
# one provider. Callers MUST pass leg-suffixed/vendor-namespaced ids (the
# DEFAULT_LEGS roster below does); a bare base-pool id is still accepted (so
# an operator can probe an unknown future alias) but gets a loud WARNING
# because its rank cannot be trusted as per-leg.
#
# ── SANDBOX (F14) ────────────────────────────────────────────────────────────
# The canary's coding task makes the candidate model emit Python, which must
# be executed to check it. leg-canary-prototype.py did a bare in-process
# exec() ("trusted-ish, short") — a supply-chain hole once promoted. Here the
# exec-check runs via preflight-tasks/canary/exec_check.py, which itself
# forks a FRESH child process (never exec()'d in this script's own process)
# under a CPU/address-space/no-fork resource ceiling, a wall-clock timeout,
# and a stripped environment. See that file for the boundary detail.
#
# ── GATE HOOK ────────────────────────────────────────────────────────────────
#   leg-preflight.sh --gate <model>
# reads LEG-RANK.tsv, takes the LAST recorded row per leg for <model> (the
# file is append-only — later rows are newer), and exits 0 (ELIGIBLE for the
# full battery) iff at least one leg's latest verdict is HEALTHY, else exits
# 1 (SKIP — every leg is non-HEALTHY). This is the hook a sweep/dogfood
# caller consults before spending its 8-minute budget on a model.
#
# Usage:
#   leg-preflight.sh [model-or-leg ...]      probe (default: DEFAULT_LEGS)
#   leg-preflight.sh --gate <model>          gate-check only, no probing
#
# Env overrides (all optional; heavily used by fleet/tests/leg-preflight.test.sh):
#   LPF_CANARY_DIR        default: <this-dir>/preflight-tasks/canary
#   LPF_RANK_FILE         default: <fleet-dir>/state/LEG-RANK.tsv
#   LPF_GATEWAY_URL        default: http://10.0.1.60:8080/v1/chat/completions
#   LPF_TOKEN              default: read from ~/.config/opencode/opencode.json
#   LPF_PROBE_CMD          if set: <cmd> <leg-id> <prompt-text> <max-tokens>
#                          must print the candidate's raw completion text to
#                          stdout and exit 0 on success, or exit non-zero to
#                          simulate an unreachable/timed-out leg. Overriding
#                          this is how the test harness stays fully hermetic
#                          (no live network) while still exercising the real
#                          task set + real sandboxed exec-check.
#   LPF_REQ_TIMEOUT_S      default: 45   (per-task request timeout)
#   LPF_LATENCY_BUDGET_S   default: 20   (avg latency above this -> SLOW)
#
# Exit codes: 0 = ran to completion (LEG-RANK.tsv updated; individual leg
#                 verdicts may still be UNREACHABLE/DEGRADED — that's DATA,
#                 not a script failure)
#             1 = (--gate mode only) model has no HEALTHY leg -> SKIP
#             2 = fail-loud abort — task registry / sandbox substrate missing,
#                 or bad input; nothing was probed
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET_DIR="$(cd "$HERE/.." && pwd)"

LPF_CANARY_DIR="${LPF_CANARY_DIR:-$HERE/preflight-tasks/canary}"
LPF_RANK_FILE="${LPF_RANK_FILE:-$FLEET_DIR/state/LEG-RANK.tsv}"
LPF_GATEWAY_URL="${LPF_GATEWAY_URL:-http://10.0.1.60:8080/v1/chat/completions}"
LPF_REQ_TIMEOUT_S="${LPF_REQ_TIMEOUT_S:-45}"
LPF_LATENCY_BUDGET_S="${LPF_LATENCY_BUDGET_S:-20}"
LPF_PROBE_CMD="${LPF_PROBE_CMD:-}"

log()  { printf '[leg-preflight] %s\n' "$*" >&2; }
err()  { printf '[leg-preflight] ERROR: %s\n' "$*" >&2; }
die()  { err "$*"; exit 2; }

# Non-Anthropic, leg-suffixed/vendor-namespaced default roster (sg-never-anthropic).
DEFAULT_LEGS=(
  deepseek-v4-pro-ds
  gemma-4-31b-cb
  minimax-m3-together
  nvidia/NVIDIA-Nemotron-3-Super-120B-A12B
  nvidia/Nemotron-3-Nano-30B-A3B
)

is_anthropic() {
  case "$1" in
    *claude*|*opus*|*sonnet*|*haiku*|*anthropic*) return 0 ;;
    *) return 1 ;;
  esac
}

# split_leg <id> -> sets SPLIT_MODEL / SPLIT_LEG globals.
# Vendor-namespaced ("nvidia/…") and the current -ds/-cb/-together aliases
# are recognized as PINNED; anything else is still probed (so a future alias
# can be tried) but flagged UNPINNED — its rank cannot be trusted as per-leg
# (F6): a bare base-pool id routes cheapest-available server-side regardless
# of what we send, so we cannot claim to have pinned it.
split_leg() {
  local id="$1"
  if [[ "$id" == */* ]]; then
    SPLIT_LEG="${id%%/*}"
    SPLIT_MODEL="${id#*/}"
  else
    case "$id" in
      *-ds)       SPLIT_LEG="ds";       SPLIT_MODEL="${id%-ds}" ;;
      *-cb)       SPLIT_LEG="cb";       SPLIT_MODEL="${id%-cb}" ;;
      *-together) SPLIT_LEG="together"; SPLIT_MODEL="${id%-together}" ;;
      *)
        SPLIT_LEG="unpinned"
        SPLIT_MODEL="$id"
        log "WARNING: '$id' has no recognized leg suffix / vendor namespace" \
            "(F6) — probing it anyway, but its rank cannot be trusted as" \
            "per-leg (a base-pool id routes cheapest-available server-side)."
        ;;
    esac
  fi
}

ensure_rank_file() {
  mkdir -p "$(dirname "$LPF_RANK_FILE")" || die "cannot create $(dirname "$LPF_RANK_FILE")"
  if [ ! -f "$LPF_RANK_FILE" ]; then
    printf 'model\tleg\treachable\tcanary_score\tlatency_s\ttok_s\tverdict\tdate\n' > "$LPF_RANK_FILE"
  fi
}

# ── --gate mode ──────────────────────────────────────────────────────────────
gate_mode() {
  local qmodel="$1"
  [ -z "$qmodel" ] && die "--gate requires a model name"
  if [ ! -f "$LPF_RANK_FILE" ]; then
    log "GATE: no LEG-RANK.tsv at $LPF_RANK_FILE yet — '$qmodel' never probed -> SKIP"
    exit 1
  fi
  local healthy=0
  declare -A latest_verdict=()
  while IFS=$'\t' read -r m leg reachable score lat toks verdict date; do
    [ "$m" = "model" ] && continue   # header row
    [ "$m" = "$qmodel" ] || continue
    latest_verdict["$leg"]="$verdict"
  done < "$LPF_RANK_FILE"
  local leg
  for leg in "${!latest_verdict[@]}"; do
    [ "${latest_verdict[$leg]}" = "HEALTHY" ] && healthy=1
  done
  if [ "$healthy" -eq 1 ]; then
    log "GATE: $qmodel has >=1 HEALTHY leg -> ELIGIBLE for full battery"
    exit 0
  else
    local legs_seen="${!latest_verdict[*]}"
    [ -z "$legs_seen" ] && legs_seen="none"
    log "GATE: $qmodel has NO HEALTHY leg (legs seen: $legs_seen) -> SKIP full battery"
    exit 1
  fi
}

# ── one leg, all canary tasks -> one TSV data line (without model/leg/date) ──
# Runs as a single python3 process per leg: reads the manifest, calls the leg
# for each task (via LPF_PROBE_CMD if set, else the real gateway), routes
# exec-kind checks through the sandboxed exec_check.py subprocess, exact-kind
# checks through a plain digit-match, and prints:
#   reachable<TAB>canary_score<TAB>latency_s<TAB>tok_s<TAB>verdict<TAB>note
probe_leg() {
  local leg="$1"
  LPF_LEG="$leg" \
  LPF_CANARY_DIR="$LPF_CANARY_DIR" \
  LPF_GATEWAY_URL="$LPF_GATEWAY_URL" \
  LPF_TOKEN="${LPF_TOKEN:-}" \
  LPF_PROBE_CMD="$LPF_PROBE_CMD" \
  LPF_REQ_TIMEOUT_S="$LPF_REQ_TIMEOUT_S" \
  LPF_LATENCY_BUDGET_S="$LPF_LATENCY_BUDGET_S" \
  python3 - <<'PYEOF'
import json, os, re, subprocess, sys, time, urllib.request

leg = os.environ["LPF_LEG"]
canary_dir = os.environ["LPF_CANARY_DIR"]
gateway_url = os.environ["LPF_GATEWAY_URL"]
token = os.environ.get("LPF_TOKEN", "")
probe_cmd = os.environ.get("LPF_PROBE_CMD", "")
req_timeout = float(os.environ["LPF_REQ_TIMEOUT_S"])
latency_budget = float(os.environ["LPF_LATENCY_BUDGET_S"])

manifest_path = os.path.join(canary_dir, "manifest.tsv")
exec_check_path = os.path.join(canary_dir, "exec_check.py")


def load_manifest():
    rows = []
    with open(manifest_path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            rows.append(parts[:5])
    return rows


def call_leg(prompt_text, max_tokens):
    """-> (ok, content, completion_tokens, latency_s, error)"""
    t0 = time.time()
    if probe_cmd:
        try:
            r = subprocess.run(
                [probe_cmd, leg, prompt_text, str(max_tokens)],
                capture_output=True, text=True, timeout=req_timeout,
            )
        except subprocess.TimeoutExpired:
            return False, "", 0, round(time.time() - t0, 2), "probe-cmd-timeout"
        dt = round(time.time() - t0, 2)
        if r.returncode != 0:
            note = (r.stderr or r.stdout or "probe-cmd-failed").strip()[:160]
            return False, "", 0, dt, note
        return True, r.stdout, 0, dt, ""
    body = json.dumps({
        "model": leg,  # verbatim — THIS is the leg-pin (F6): never stripped/normalized
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        gateway_url, body,
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=req_timeout)
        dt = round(time.time() - t0, 2)
        d = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001 — any network/HTTP failure = unreachable, never a crash
        return False, "", 0, round(time.time() - t0, 2), str(e)[:160]
    content = (d.get("choices", [{}])[0].get("message", {}).get("content") or "")
    usage = d.get("usage", {}) or {}
    return True, content, usage.get("completion_tokens") or 0, dt, ""


total_passed = 0
total_checks = 0
latencies = []
tok_sum = 0
reachable_any = False
note = ""

for task_id, kind, prompt_file, checkfile, max_tokens_s in load_manifest():
    with open(os.path.join(canary_dir, prompt_file)) as fh:
        prompt_text = fh.read()
    ok, content, tok, dt, err = call_leg(prompt_text, int(max_tokens_s))
    if not ok:
        note = f"{task_id}:{err}"
        continue
    reachable_any = True
    latencies.append(dt)
    tok_sum += tok
    if kind == "exec":
        checks_path = os.path.join(canary_dir, checkfile)
        try:
            r = subprocess.run(
                [sys.executable, exec_check_path, checks_path],
                input=content, capture_output=True, text=True, timeout=15,
            )
            lines = (r.stdout or "").strip().splitlines()
            result = json.loads(lines[-1]) if lines else {}
        except Exception as e:  # noqa: BLE001 — a broken sandbox call = a failed check, not a crash
            result = {"passed": 0, "total": 1, "note": f"sandbox-call-failed:{e!r}"[:100]}
        total_passed += result.get("passed", 0)
        total_checks += result.get("total", 0)
    elif kind == "exact":
        expected = checkfile.strip()
        m = re.search(r"-?\d+", content or "")
        got = m.group(0) if m else ""
        total_checks += 1
        if got == expected:
            total_passed += 1

if not reachable_any:
    print(f"false\t0/0\t0\t0\tUNREACHABLE\t{note}")
else:
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    tok_s = round(tok_sum / sum(latencies), 1) if sum(latencies) > 0 else 0.0
    if total_checks == 0 or total_passed < total_checks:
        verdict = "DEGRADED-serves-wrong"
    elif avg_latency > latency_budget:
        verdict = "SLOW"
    else:
        verdict = "HEALTHY"
    print(f"true\t{total_passed}/{total_checks}\t{avg_latency}\t{tok_s}\t{verdict}\t{note}")
PYEOF
}

# ── main ─────────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--gate" ]; then
  gate_mode "${2:-}"
  exit $?  # gate_mode always exits itself; unreachable in practice
fi

[ -f "$LPF_CANARY_DIR/manifest.tsv" ] || die "canary task registry missing: $LPF_CANARY_DIR/manifest.tsv"
[ -f "$LPF_CANARY_DIR/exec_check.py" ] || die "sandboxed exec-checker missing: $LPF_CANARY_DIR/exec_check.py"
command -v python3 >/dev/null 2>&1 || die "python3 not found"

if [ -z "${LPF_TOKEN:-}" ] && [ -z "$LPF_PROBE_CMD" ]; then
  LPF_TOKEN="$(python3 -c "
import json, os
try:
    print(json.load(open(os.path.expanduser('~/.config/opencode/opencode.json')))['provider']['charon']['options']['apiKey'])
except Exception:
    pass
" 2>/dev/null || true)"
  [ -z "$LPF_TOKEN" ] && log "WARNING: no gateway token found (~/.config/opencode/opencode.json) — legs will likely rank UNREACHABLE"
fi

LEGS=("$@")
[ ${#LEGS[@]} -eq 0 ] && LEGS=("${DEFAULT_LEGS[@]}")

ensure_rank_file
TODAY="$(date -u +%Y-%m-%d)"

for leg in "${LEGS[@]}"; do
  if is_anthropic "$leg"; then
    log "SKIP (sg-never-anthropic): $leg"
    continue
  fi
  split_leg "$leg"
  model="$SPLIT_MODEL"; legtag="$SPLIT_LEG"
  log "probing $leg (model=$model leg=$legtag) …"
  line="$(probe_leg "$leg")"
  IFS=$'\t' read -r reachable score latency toks verdict note <<< "$line"
  [ -n "$note" ] && log "  note: $note"
  log "  -> reachable=$reachable score=$score latency_s=$latency tok_s=$toks verdict=$verdict"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$model" "$legtag" "$reachable" "$score" "$latency" "$toks" "$verdict" "$TODAY" >> "$LPF_RANK_FILE"
done

log "done -> $LPF_RANK_FILE"
