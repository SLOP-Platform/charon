#!/usr/bin/env bash
# run-canary.sh — the ALWAYS-ON gate-test sensor (4LOM-CANARY-SERVICE).
#
# WHY THIS EXISTS
#   The manager must never run the ~77-file gate suite inline. It reads a CACHED report instead.
#   But a cached report is only trustworthy if it answers two questions the raw gate cannot:
#     1. Is this red GENUINE, or did it just lose a race under concurrent load?
#     2. Is this report still TRUE, or is the sensor itself dead?
#   Both were live failures on this rig: `reconcile-merged.test.sh` PASSES standalone and only
#   fails under the gate's concurrent runner (plus `fork: Resource temporarily unavailable`
#   flakes under parallel load) — 4 such false-reds were hiding 8 genuine ones; and the OOB
#   grader died on a reboot and looked healthy for 9 days because nothing aged its output.
#
# HOW SLOW-vs-BROKEN IS DECIDED  (the load-bearing mechanism — do not "simplify" it away)
#   Phase 1 (CONCURRENT): every discovered *.test.sh runs in parallel under `timeout`, exactly
#                         like fleet/gate.sh — this is the environment that MANUFACTURES the
#                         false reds, so it must be reproduced, not avoided.
#   Phase 2 (SERIAL ADJUDICATION): every test that failed in phase 1 is RE-RUN ALONE, one at a
#                         time, with a generous timeout, no competing load, and up to
#                         CANARY_SERIAL_ATTEMPTS tries.
#   Verdict:
#     concurrent PASS                                 -> green / ok
#     concurrent FAIL, ANY serial attempt PASSES      -> SLOW   (load-induced false red; NOT a
#                                                 verdict about the check. attribution `slow`,
#                                                 or `slow-timeout` when phase 1 rc was 124)
#     concurrent FAIL, EVERY serial attempt rc == 124 -> BROKEN-TIMEOUT (hangs even unloaded;
#                                                 too slow to finish IS a failure, not a flake)
#     concurrent FAIL, EVERY serial attempt FAILS     -> BROKEN (genuine red)
#   rc=124 is the timeout marker, but rc=124 ALONE is deliberately NOT sufficient to call SLOW:
#   `handoff-mechanize.test.sh` was OBSERVED (2026-07-24, real suite) at concurrent rc=124 /
#   serial rc=1 — a genuine red that merely also happens to be slow. rc never decides; the
#   serial re-run is the adjudicator.
#
#   WHY THE RETRY IS NOT OPTIONAL (measured, 2026-07-24, real suite): `reconcile-merged.test.sh`'s
#   ONLY failing assertion is a wall clock — "reconciled in Nms (<5000ms)". It passes standalone
#   at 3567ms and failed its FIRST serial re-run at 6765ms because the box still carried ambient
#   load from other sessions. A single serial attempt therefore mislabels the rig's canonical
#   SLOW case as BROKEN — the exact confusion this service exists to end. A second attempt
#   resolves it, and deterministic reds fail every attempt, so the retry only ever costs extra
#   runs of tests that are genuinely red.
#
# HOW STALENESS IS PREVENTED
#   The report carries `last_run` (epoch) + its own `ttl_s`. `status` refuses to report the
#   cached verdict once age > ttl: it prints UNKNOWN/STALE and exits non-zero. A missing report
#   is likewise UNKNOWN, never green. The same file is a freshness_probe row in
#   fleet/state/service-registry.tsv, so the watchdog alarms on the sensor itself.
#
# NON-VACUOUS / FAIL-CLOSED / FAIL-LOUD
#   Zero discovered checks is RED (rc=3), never a silent pass. Missing machinery (no `timeout`,
#   no tests dir, unwritable report path) is RED (rc=4), never "skipped". `set -euo pipefail`
#   is on and no verdict-bearing command is masked with `|| true` / `| tail` / `| head`.
#
# EXIT CODES (stable contract; the test red-proofs each one)
#   0  GREEN     — every discovered check green
#   1  RED       — >=1 BROKEN (genuine failure; includes broken-timeout)
#   2  DEGRADED  — >=1 SLOW and 0 BROKEN (load-induced only; distinct from RED on purpose)
#   3  VACUOUS   — zero checks discovered: a report that examined nothing is RED
#   4  FAIL-CLOSED — the canary's own machinery is missing/unrunnable
#   5  STALE/UNKNOWN — `status` only: no report, or report older than its ttl
#   6  REENTRANCY refusal — nested gate/canary invocation (fork-bomb class guard)
#
# USAGE
#   run-canary.sh run            one full cycle (phase 1 + phase 2), writes the cached report
#   run-canary.sh loop           run forever on a cadence (the systemd service entry point)
#   run-canary.sh status         token-lean one-liner from the CACHED report (SessionStart surface)
#   run-canary.sh report         dump the cached report verbatim
#   run-canary.sh self-check     machinery-only fail-closed check (rc 0 or 4)
#
# ENV (defaults are the deployed values; every var below is also the test seam)
#   CANARY_FLEET             fleet dir                    (default: this script's ../)
#   CANARY_TESTS_DIR         suite dir                    (default: $CANARY_FLEET/tests)
#   CANARY_REPORT            cached report path           (default: $CANARY_FLEET/state/canary-report.tsv)
#   CANARY_LOG_DIR           per-failure logs             (default: $CANARY_FLEET/state/canary-logs)
#   CANARY_TTL_S             report freshness bound       (default: 3600)
#   CANARY_INTERVAL_S        loop cadence                 (default: 900)
#   CANARY_TIMEOUT_S         phase-1 per-test timeout     (default: 180)
#   CANARY_SERIAL_TIMEOUT_S  phase-2 per-test timeout     (default: 300)
#   CANARY_SERIAL_ATTEMPTS   phase-2 tries before BROKEN  (default: 2 — see the retry note above;
#                            1 is a KNOWN-BAD setting, it mislabels the load-sensitive reds)
#   CANARY_JOBS              phase-1 parallelism          (default: nproc, min 2)
#   CANARY_REPO              checkout to git-pull         (default: $CANARY_FLEET/..)
#   CANARY_GIT_PULL          1 = ff-only pull before run  (default: 0; the systemd unit sets 1)
#   CANARY_NOW               override "now" for freshness math (tests only)
#   CANARY_ALLOW_NESTED      1 = permit a nested run, honoured ONLY when CANARY_TESTS_DIR points
#                            somewhere other than THIS repo's fleet/tests (tests only; it can
#                            therefore never re-enable the gate->canary->gate recursion)
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANARY_FLEET="${CANARY_FLEET:-$(cd "$SELF_DIR/.." && pwd)}"
TESTS_DIR="${CANARY_TESTS_DIR:-$CANARY_FLEET/tests}"
REPORT="${CANARY_REPORT:-$CANARY_FLEET/state/canary-report.tsv}"
LOG_DIR="${CANARY_LOG_DIR:-$CANARY_FLEET/state/canary-logs}"
TTL_S="${CANARY_TTL_S:-3600}"
INTERVAL_S="${CANARY_INTERVAL_S:-900}"
TIMEOUT_S="${CANARY_TIMEOUT_S:-180}"
SERIAL_TIMEOUT_S="${CANARY_SERIAL_TIMEOUT_S:-300}"
SERIAL_ATTEMPTS="${CANARY_SERIAL_ATTEMPTS:-2}"
[ "$SERIAL_ATTEMPTS" -ge 1 ] 2>/dev/null || SERIAL_ATTEMPTS=1
REPO="${CANARY_REPO:-$(cd "$CANARY_FLEET/.." && pwd)}"
GIT_PULL="${CANARY_GIT_PULL:-0}"
TAB="$(printf '\t')"

_nproc(){ command -v nproc >/dev/null 2>&1 && nproc || echo 4; }
JOBS="${CANARY_JOBS:-$(_nproc)}"
[ "$JOBS" -ge 2 ] 2>/dev/null || JOBS=2

_now(){ echo "${CANARY_NOW:-$(date +%s)}"; }
_iso(){ date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "@$1"; }
_age_h(){ # humanise seconds
  local s="$1"
  if   [ "$s" -lt 120 ];   then echo "${s}s"
  elif [ "$s" -lt 7200 ];  then echo "$((s/60))m"
  else                          echo "$((s/3600))h$(( (s%3600)/60 ))m"; fi
}

# ── reentrancy guard (fleet-selfcheck-forkbomb-class) ────────────────────────────────────────
# gate.sh exports CHARON_GATE_ACTIVE=1 to every test it spawns. If the canary were runnable from
# inside a gate-spawned test against the REAL suite, gate -> canary -> gate recursion is back.
# The escape hatch is honoured only for a tests dir that is NOT this repo's own, so a hermetic
# fixture suite can exercise the canary while the recursive path stays permanently closed.
_reentrancy_guard(){
  local nested=0
  [ "${CHARON_CANARY_ACTIVE:-0}" = "1" ] && nested=1
  [ "${CHARON_GATE_ACTIVE:-0}" = "1" ] && nested=1
  [ "$nested" -eq 1 ] || return 0
  local own_tests="$SELF_DIR/../tests"
  own_tests="$(cd "$own_tests" 2>/dev/null && pwd || echo "$own_tests")"
  local resolved="$TESTS_DIR"
  resolved="$(cd "$resolved" 2>/dev/null && pwd || echo "$resolved")"
  if [ "${CANARY_ALLOW_NESTED:-0}" = "1" ] && [ "$resolved" != "$own_tests" ]; then
    return 0
  fi
  echo "canary: REFUSING nested run (CHARON_GATE_ACTIVE/CHARON_CANARY_ACTIVE set) — fork-bomb guard" >&2
  exit 6
}

# ── fail-closed machinery check ──────────────────────────────────────────────────────────────
# Missing machinery is RED, never "skipped". Every reason is printed; the caller exits 4.
_self_check(){
  local bad=0
  command -v timeout >/dev/null 2>&1 || { echo "canary: FAIL-CLOSED — \`timeout\` not on PATH; SLOW-vs-BROKEN cannot be decided" >&2; bad=1; }
  command -v bash    >/dev/null 2>&1 || { echo "canary: FAIL-CLOSED — \`bash\` not on PATH" >&2; bad=1; }
  [ -d "$TESTS_DIR" ] || { echo "canary: FAIL-CLOSED — tests dir missing: $TESTS_DIR" >&2; bad=1; }
  local rdir; rdir="$(dirname "$REPORT")"
  mkdir -p "$rdir" 2>/dev/null || true
  [ -d "$rdir" ] && [ -w "$rdir" ] || { echo "canary: FAIL-CLOSED — report dir not writable: $rdir" >&2; bad=1; }
  return "$bad"
}

# ── report writer (atomic; a half-written report must never be read as a verdict) ────────────
# rows arrive on stdin as: name<TAB>status<TAB>attribution   (last_run is stamped here)
_write_report(){
  local verdict="$1" rc="$2" total="$3" green="$4" broken="$5" slow="$6" dur="$7" pull="$8"
  local now tmp; now="$(_now)"; tmp="$REPORT.tmp.$$"
  {
    printf '# canary-report.tsv — GENERATED by fleet/canary-service/run-canary.sh. DO NOT EDIT BY HAND.\n'
    printf '# A report older than ttl_s is UNKNOWN, not the last-known-good verdict (`run-canary.sh status`).\n'
    printf '# meta%slast_run=%s%sttl_s=%s%stotal=%s%sgreen=%s%sbroken=%s%sslow=%s%sverdict=%s%src=%s%sduration_s=%s%shost=%s%scommit=%s%spull=%s\n' \
      "$TAB" "$now" "$TAB" "$TTL_S" "$TAB" "$total" "$TAB" "$green" "$TAB" "$broken" "$TAB" "$slow" \
      "$TAB" "$verdict" "$TAB" "$rc" "$TAB" "$dur" "$TAB" "$(hostname 2>/dev/null || echo unknown)" \
      "$TAB" "$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)" "$TAB" "$pull"
    printf '# test%sstatus%slast_run%sattribution\n' "$TAB" "$TAB" "$TAB"
    local name st attr
    while IFS="$TAB" read -r name st attr; do
      [ -n "$name" ] || continue
      printf '%s%s%s%s%s%s%s\n' "$name" "$TAB" "$st" "$TAB" "$now" "$TAB" "$attr"
    done
  } > "$tmp"
  mv -f "$tmp" "$REPORT"
}

# ── cmd: run ─────────────────────────────────────────────────────────────────────────────────
cmd_run(){
  _reentrancy_guard
  _self_check || {
    # Best-effort: record the fail-closed state so `status` reads RED rather than the stale verdict.
    _write_report machinery 4 0 0 0 0 0 skipped </dev/null 2>/dev/null || true
    echo "canary: verdict=FAIL-CLOSED rc=4"
    return 4
  }
  export CHARON_CANARY_ACTIVE=1

  local pull=skipped
  if [ "$GIT_PULL" = "1" ]; then
    if git -C "$REPO" pull --ff-only --quiet >/dev/null 2>&1; then pull=ok; else pull=failed; fi
  fi

  shopt -s nullglob
  local tests=("$TESTS_DIR"/*.test.sh)
  shopt -u nullglob

  # NON-VACUOUS: a run that examined ZERO checks is RED. This is the single most important
  # branch in the file — a discovery failure that reports green is indistinguishable from
  # a healthy suite, which is how a gate stops gating.
  if [ "${#tests[@]}" -eq 0 ]; then
    _write_report vacuous 3 0 0 0 0 0 "$pull" </dev/null
    echo "canary: VACUOUS — zero *.test.sh discovered in $TESTS_DIR (this is RED, not a pass)" >&2
    echo "canary: verdict=VACUOUS rc=3"
    return 3
  fi

  mkdir -p "$LOG_DIR"
  local work start; work="$(mktemp -d)"; start="$(date +%s)"

  # ── PHASE 1: CONCURRENT — reproduces the exact load that manufactures the false reds ──
  local t name running=0
  for t in "${tests[@]}"; do
    name="$(basename "$t")"
    (
      rc=0
      timeout -k 10 "$TIMEOUT_S" bash "$t" >"$work/$name.c.out" 2>&1 || rc=$?
      echo "$rc" >"$work/$name.c.rc"
    ) &
    running=$((running+1))
    if [ "$running" -ge "$JOBS" ]; then wait -n 2>/dev/null || wait; running=$((running-1)); fi
  done
  wait

  # ── PHASE 2: SERIAL ADJUDICATION — re-run each phase-1 failure ALONE, unloaded ──
  local rows="$work/rows" details="$work/details"
  : > "$rows"; : > "$details"
  local total=0 green=0 broken=0 slow=0 crc src status attr attempt all_timeout
  for t in "${tests[@]}"; do
    name="$(basename "$t")"
    total=$((total+1))
    crc="$(cat "$work/$name.c.rc" 2>/dev/null || echo 99)"
    if [ "$crc" -eq 0 ]; then
      green=$((green+1)); status=green; attr=ok; src=-; attempt=0
    else
      src=0; attempt=0; all_timeout=1
      while :; do
        attempt=$((attempt+1)); src=0
        timeout -k 10 "$SERIAL_TIMEOUT_S" bash "$t" >"$work/$name.s.out" 2>&1 || src=$?
        [ "$src" -eq 124 ] || all_timeout=0
        [ "$src" -eq 0 ] && break
        [ "$attempt" -ge "$SERIAL_ATTEMPTS" ] && break
      done
      if [ "$src" -eq 0 ]; then
        # Failed under concurrency, passes alone => the LOAD failed, not the check.
        slow=$((slow+1)); status=slow
        if [ "$crc" -eq 124 ]; then attr=slow-timeout; else attr=slow; fi
      elif [ "$all_timeout" -eq 1 ]; then
        # Times out even with the whole box to itself, every attempt: too slow to finish IS a
        # failure. Never reported as `slow` — `slow` means "the check is fine", and it is not.
        broken=$((broken+1)); status=red; attr=broken-timeout
      else
        broken=$((broken+1)); status=red; attr=broken
      fi
      cp -f "$work/$name.s.out" "$LOG_DIR/$name.log" 2>/dev/null || true
      printf '# detail%s%s%sconcurrent_rc=%s%sserial_rc=%s%sserial_attempts=%s%slog=%s\n' \
        "$TAB" "$name" "$TAB" "$crc" "$TAB" "$src" "$TAB" "$attempt" "$TAB" "$LOG_DIR/$name.log" >> "$details"
    fi
    printf '%s%s%s%s%s\n' "$name" "$TAB" "$status" "$TAB" "$attr" >> "$rows"
  done

  local rc=0
  if   [ "$broken" -gt 0 ]; then rc=1
  elif [ "$slow"   -gt 0 ]; then rc=2
  fi
  local verdict=green
  [ "$rc" -eq 1 ] && verdict=red
  [ "$rc" -eq 2 ] && verdict=degraded

  local dur=$(( $(date +%s) - start ))
  _write_report "$verdict" "$rc" "$total" "$green" "$broken" "$slow" "$dur" "$pull" < "$rows"
  cat "$details" >> "$REPORT"
  rm -rf "$work"

  printf 'canary: %s green / %s red (%s slow) of %s in %ss -> verdict=%s rc=%s\n' \
    "$green" "$broken" "$slow" "$total" "$dur" "$verdict" "$rc"
  return "$rc"
}

# ── cmd: loop ────────────────────────────────────────────────────────────────────────────────
# The systemd entry point. A cycle's RED must NOT kill the service (the report IS the signal),
# but it is logged loudly to the journal.
cmd_loop(){
  echo "canary: loop starting — interval=${INTERVAL_S}s ttl=${TTL_S}s tests=$TESTS_DIR report=$REPORT"
  while :; do
    local rc=0
    cmd_run || rc=$?
    echo "canary: cycle finished rc=$rc at $(_iso "$(date +%s)")"
    sleep "$INTERVAL_S"
  done
}

# ── cmd: status ──────────────────────────────────────────────────────────────────────────────
# The SessionStart surface. NEVER prints a green-looking line from a stale or missing report.
cmd_status(){
  if [ ! -f "$REPORT" ]; then
    echo "canary: UNKNOWN — no cached report at $REPORT (service never ran / not deployed) — treat as RED"
    return 5
  fi
  local meta last ttl green broken slow verdict now age
  # `|| true` here masks nothing: grep's no-match is IMMEDIATELY converted to RED two lines down.
  # It is a lookup, not a verdict — the verdict path below never swallows a non-zero.
  meta="$(grep -m1 "^# meta$TAB" "$REPORT" || true)"
  if [ -z "$meta" ]; then
    echo "canary: UNKNOWN — cached report has no meta line (corrupt/truncated) — treat as RED"
    return 5
  fi
  _f(){ printf '%s' "$meta" | tr "$TAB" '\n' | awk -v k="$1=" 'index($0,k)==1{sub(/^[^=]*=/,"");print;exit}'; }
  last="$(_f last_run)"; ttl="$(_f ttl_s)"; green="$(_f green)"; broken="$(_f broken)"
  slow="$(_f slow)"; verdict="$(_f verdict)"
  case "$last" in ''|*[!0-9]*) echo "canary: UNKNOWN — unparseable last_run in $REPORT — treat as RED"; return 5;; esac
  case "$ttl"  in ''|*[!0-9]*) ttl="$TTL_S";; esac
  now="$(_now)"; age=$(( now - last ))
  [ "$age" -lt 0 ] && age=0
  if [ "$age" -gt "$ttl" ]; then
    # THE 9-day-dead-grader class: past the freshness bound the cached verdict is not evidence.
    printf 'canary: UNKNOWN — report STALE (age %s > ttl %s) @ %s — the SENSOR may be dead, not the suite\n' \
      "$(_age_h "$age")" "$(_age_h "$ttl")" "$(_iso "$last")"
    return 5
  fi
  case "$verdict" in
    vacuous)   printf 'canary: RED — VACUOUS run (zero checks discovered) @ %s (age %s)\n' "$(_iso "$last")" "$(_age_h "$age")"; return 3;;
    machinery) printf 'canary: RED — canary machinery FAIL-CLOSED @ %s (age %s)\n' "$(_iso "$last")" "$(_age_h "$age")"; return 4;;
  esac
  printf 'canary: %s green / %s red (%s slow) @ %s (age %s)\n' \
    "${green:-?}" "${broken:-?}" "${slow:-?}" "$(_iso "$last")" "$(_age_h "$age")"
  [ "${broken:-1}" -gt 0 ] && return 1
  [ "${slow:-0}"   -gt 0 ] && return 2
  return 0
}

cmd_report(){
  [ -f "$REPORT" ] || { echo "canary: no cached report at $REPORT" >&2; return 5; }
  cat "$REPORT"
}

usage(){
  sed -n '1,60p' "${BASH_SOURCE[0]}" | grep -E '^#( |$)' | sed 's/^# \{0,1\}//'
}

main(){
  local cmd="${1:-status}"; shift || true
  case "$cmd" in
    run)        cmd_run "$@" ;;
    loop)       cmd_loop "$@" ;;
    status|surface) cmd_status "$@" ;;
    report)     cmd_report "$@" ;;
    self-check) _reentrancy_guard; if _self_check; then echo "canary: machinery OK"; return 0; else echo "canary: machinery FAIL-CLOSED"; return 4; fi ;;
    -h|--help|help) usage ;;
    *)          echo "canary: unknown command '$cmd'" >&2; usage >&2; return 2 ;;
  esac
}

main "$@"
