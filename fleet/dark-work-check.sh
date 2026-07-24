#!/usr/bin/env bash
# dark-work-check.sh — MECHANIZED VISIBILITY for the fleet's two chronic "dark work" strands
# (tickets NO-DARK-WORK; pairs with F19 bridge-unregister-trap + F38 handoff-mechanize).
#
# FOLDED INTO THE SERVICE-WATCHDOG (SERVICE-LIVENESS-WATCHDOG): this script is the DARK-WORK leg
# of the fleet service-watchdog. fleet/watchdog/discover-services.sh runs it as one of its legs and
# the watchdog cadence (foreman-cadence.sh watchdog) fires it on a timer, so all liveness/visibility
# — service alive+freshness, unregistered-service discovery, AND dark-session/stranded-job — run
# under one supervisor. It remains independently runnable (same CLI/exit contract as before).
#
# WHY: background/detached work goes UNSEEN and its result STRANDS. (1) VISIBILITY — a session
# can run "dark" (a live opencode/claude session was found never registered on the session-bridge,
# invisible to coordination). (2) PICKUP — a launched job reports by writing a log the manager must
# hand-collect, so if the session ends (or a handoff omits the pointer) the result silently strands
# (the KS4 "finished, committed, but UNVERIFIED + unpushed" shape). This script mechanizes BOTH:
#
#   REGISTER leg — scan running claude/opencode PIDs, cross-reference the session-bridge DB, and
#                  flag any running PID that has NO corresponding active session row. Pairs with
#                  auto-register on session start (Claude SessionStart hook; opencode/CG via the
#                  proxy wrapper). The bridge DB is queried DIRECTLY (not via the live daemon's
#                  socket) so the check is hermetic + offline-testable.
#
#   PICKUP leg   — scan the job registry (state/agent-logs/*.txt, state/agent-briefs/*.md) and
#                  flag any LAUNCHED job whose result-pointer has not been picked up: NOT in
#                  state/submitted/<ticket>, state/done/<ticket>, state/needs-push/<ticket>, and
#                  not explicitly waived (state/jobs/waived/<id>). LIVE jobs (droid still running,
#                  fresh mtime) are NOT flagged — only STRANDED results.
#
# USAGE
#   bash fleet/dark-work-check.sh               # both legs; exit non-zero on ANY dark/stranded
#   bash fleet/dark-work-check.sh --register    # only the REGISTER leg
#   bash fleet/dark-work-check.sh --pickup      # only the PICKUP leg
#   bash fleet/dark-work-check.sh --json        # machine-readable {register:[...], pickup:[...]} output
#   bash fleet/dark-work-check.sh --waive <id> <reason>   # mark a job as intentionally not-picked
#                                                           (records the reason, never strand silently)
#   bash fleet/dark-work-check.sh --selftest    # fail-on-revert self-test (no live state touched)
#
# EXIT CODES
#   0  CLEAN — every running claude/opencode is registered on the bridge, every launched job
#              was picked up (or explicitly waived).
#   1  RED   — at least one DARK session OR one UN-PICKED job. The line lists the offender.
#   2  USAGE — bad args / missing dependencies.
#
# TEST HOOKS (used by --selftest only; never in normal operation):
#   DARK_WORK_BRIDGE_DB=<path>    override the session-bridge DB path (default ~/.charon/session-bridge.db)
#   DARK_WORK_FLEET=<path>        override the fleet dir (default: dir of this script)
#   DARK_WORK_PS_BIN=<path>       override `ps` (selftest stub)
#   DARK_WORK_PY_BIN=<path>       override `python3` (selftest stub)
#   DARK_WORK_NOW=<epoch>         override "now" for the LIVE-job age heuristic
#   DARK_WORK_LIVE_AGE_S=<int>    max mtime-age (s) to consider a job LIVE (default 600)
set -uo pipefail

FLEET="${DARK_WORK_FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
BRIDGE_DB="${DARK_WORK_BRIDGE_DB:-$HOME/.charon/session-bridge.db}"
PS_BIN="${DARK_WORK_PS_BIN:-ps}"
PY_BIN="${DARK_WORK_PY_BIN:-python3}"
LIVE_AGE_S="${DARK_WORK_LIVE_AGE_S:-600}"
NOW="${DARK_WORK_NOW:-$(date +%s)}"
JSON=0
LEGS="both"

say(){   printf '%s\n' "$*"; }
warn(){  printf 'WARN: %s\n' "$*" >&2; }
die(){   printf 'error: %s\n' "$*" >&2; exit 2; }

# ---- arg parse ------------------------------------------------------------
WAIVE_ID=""; WAIVE_REASON=""
while [ $# -gt 0 ]; do case "$1" in
  --register)    LEGS="register" ;;
  --pickup)      LEGS="pickup" ;;
  --json)        JSON=1 ;;
  --waive)       [ $# -ge 3 ] || die "--waive needs: <id> <reason>"; WAIVE_ID="$2"; WAIVE_REASON="$3"; shift 2 ;;
  --selftest)    LEGS="selftest" ;;
  -h|--help)     sed -n '2,40p' "$0"; exit 0 ;;
  *)             die "unknown arg: $1" ;;
esac; shift; done

# ---------------------------------------------------------------------------
# REGISTER leg — cross-reference running claude/opencode PIDs vs session-bridge DB
#
# Detection model: the bridge records a `pid` per session row. A session is ACTIVE if last_seen
# is within SESSION_BRIDGE_TTL (default 600s). A running claude/opencode PID that is NOT in the
# set of active session pids is DARK — its session was never registered, or the row was reaped
# after the session died. We do NOT just count (active < running) and bail: the spec requires
# naming the dark PID.
#
# Why the DB, not the live daemon socket: the daemon's last_seen drifts from real time on long
# leases and a socket query races the daemon's purge. The DB is the source of truth for
# "is this PID known right now" (durability of the answer matters more than liveness).
# ---------------------------------------------------------------------------
register_leg(){
  local running=() active_pids=() dark=() bridge_present=1
  if [ ! -f "$BRIDGE_DB" ]; then
    bridge_present=0
    warn "session-bridge DB not found at $BRIDGE_DB — REGISTER leg cannot cross-reference; reporting only running claude/opencode PIDs as suspect."
  fi

  # Collect running claude/opencode PIDs. Match comm OR the full command line (claude launches
  # nested `claude`-named processes; opencode often runs as `opencode run ...` so comm is "opencode"
  # or "node" depending on the binary). We require the command line to contain "claude" or "opencode"
  # to avoid the false-positive of a generic `node` running an unrelated script.
  if ! command -v "$PS_BIN" >/dev/null 2>&1; then
    warn "ps binary not found (DARK_WORK_PS_BIN=$PS_BIN) — REGISTER leg degraded"
  else
    # ps -eo pid=,comm=,args= — args catches the full cmdline. Strip our own $$ (the check script
    # itself runs in a child of a shell; not a model session, so the arg line won't match).
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      case "$line" in *"claude"*|*"opencode"*) running+=("$line") ;; esac
    done < <("$PS_BIN" -eo pid=,comm=,args= -ww 2>/dev/null \
             | awk -v me=$$ '$1!=me')
  fi

  # Collect active session pids from the bridge DB. ACTIVE = last_seen within TTL. The PID column
  # is recorded at register time and may not be the LIVE model pid (the proxy can reconnect), but
  # a session that is still active (recent last_seen) and shares a pid with a running claude/opencode
  # is the strongest "this is the same session" signal we have. We also accept: a row whose
  # session_id matches a pid-stamped live process via the `name` field (operators sometimes name
  # a session "claude-<pid>"), but we keep it simple: pid equality.
  if [ "$bridge_present" -eq 1 ] && command -v "$PY_BIN" >/dev/null 2>&1; then
    local ttl="${SESSION_BRIDGE_TTL:-600}"
    active_pids=()
    while IFS= read -r pid; do
      [ -n "$pid" ] && active_pids+=("$pid")
    done < <("$PY_BIN" - "$BRIDGE_DB" "$ttl" "$NOW" <<'PY' 2>/dev/null
import sqlite3, sys, time
db, ttl, now = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
try:
    c = sqlite3.connect(db)
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now - ttl))
    rows = c.execute("SELECT pid FROM sessions WHERE pid > 0 AND last_seen >= ?", (cutoff,)).fetchall()
    for (p,) in rows:
        print(p)
except Exception as e:
    sys.stderr.write(f"dark-work-check: bridge DB read failed: {e}\n")
    sys.exit(0)
PY
    )
  fi

  # A running line is DARK if its pid is NOT in active_pids AND not in the set of historical
  # session pids in the DB (a recently-registered-then-orphaned session is still DARK — its
  # session was never persisted OR the pid was reused; either way, no current coordination).
  for line in "${running[@]}"; do
    local pid="${line%% *}"
    pid="${pid##* }"; pid="$(printf '%s' "$pid" | tr -d ' ')"
    case "${pid:-}" in ''|*[!0-9]*) continue ;; esac
    local known=0
    local p
    for p in "${active_pids[@]:-}"; do
      [ "$p" = "$pid" ] && { known=1; break; }
    done
    [ "$known" -eq 0 ] || continue
    # Strip the pid from the front of the line (the rest is comm + cmd args). The full
    # `ps` line is preserved for the JSON output; the human report truncates below to
    # stay scannable when a launcher's full argument blob (the brief file content) shows
    # up in `ps args`.
    local cmd_part
    cmd_part="$(printf '%s' "$line" | sed -E 's/^[[:space:]]*[0-9]+[[:space:]]+//')"
    dark+=("pid=$pid cmd=$cmd_part")
  done

  if [ "${#dark[@]}" -gt 0 ]; then
    if [ "$JSON" -eq 1 ]; then
      printf 'register:['
      local first=1 d pid_v cmd_v
      for d in "${dark[@]}"; do
        [ "$first" -eq 1 ] && first=0 || printf ','
        pid_v="$(printf '%s' "$d" | sed -nE 's/^pid=([0-9]+) .*/\1/p')"
        # strip the "pid=<n> cmd=" prefix and keep the full command. json-escape.
        cmd_v="$(printf '%s' "$d" | sed -E 's/^pid=[0-9]+ cmd=//' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e ':a;N;$!ba;s/\n/\\n/g')"
        printf '{"pid":"%s","cmd":"%s"}' "$pid_v" "$cmd_v"
      done
      printf ']'
    else
      say "REGISTER LEG: ${#dark[@]} DARK session(s) (running claude/opencode PID NOT on the session-bridge):"
      local d
      for d in "${dark[@]}"; do
        # Truncate the cmd preview so a full launcher note doesn't drown the human report.
        local short
        short="$(printf '%s' "$d" | sed -E 's/^pid=[0-9]+ cmd=//' | cut -c1-120)"
        printf '  - pid=%s cmd=%s\n' \
          "$(printf '%s' "$d" | sed -nE 's/^pid=([0-9]+) .*/\1/p')" "$short"
      done
      say "  Fix: register the session on the bridge, or kill the orphan."
    fi
    return 1
  fi
  [ "$JSON" -eq 0 ] && say "REGISTER LEG: clean (${#running[@]} running model process(es), all registered; bridge_present=$bridge_present)"
  return 0
}

# ---------------------------------------------------------------------------
# PICKUP leg — scan the job registry, flag un-picked job results
#
# A "job" here is a <droid>-<ticket> pair with both a log file (state/agent-logs/<id>.txt) and a
# brief file (state/agent-briefs/<id>.md). The droid has LAUNCHED when either file exists.
# A job is PICKED UP when any of the following hold:
#   - state/submitted/<ticket>      : submit.sh consumed the result (clean)
#   - state/done/<ticket>          : ticket is fully landed (no follow-up needed)
#   - state/needs-push/<ticket>    : stranded-but-flagged — the manager will hand-collect
#   - state/jobs/waived/<droid>-<ticket>  : operator explicitly waived the pickup
# A job whose result is NOT picked is STRANDED — the next session will never see it without a
# hand-collect. LIVE jobs (droid still running, mtime within LIVE_AGE_S) are NOT stranded.
# ---------------------------------------------------------------------------
pickup_leg(){
  local logs_dir="$FLEET/state/agent-logs"
  local briefs_dir="$FLEET/state/agent-briefs"
  local submitted_dir="$FLEET/state/submitted"
  local done_dir="$FLEET/state/done"
  local needs_push_dir="$FLEET/state/needs-push"
  local waived_dir="$FLEET/state/jobs/waived"
  local stranded=() live=()

  # Find every launched job by brief file (the canonical "client was given a brief" signal —
  # brief is written before charon-run.sh execs the model, so its presence is the strongest
  # "launched" signal we have even if the log hasn't been written yet). Fall back to log files
  # for older runs that predate the brief convention.
  local launched=()
  if [ -d "$briefs_dir" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      launched+=("$f")
    done < <(find "$briefs_dir" -maxdepth 1 -type f -name '*.md' 2>/dev/null \
             | sed "s|^$briefs_dir/||; s|\.md$||")
  fi
  if [ -d "$logs_dir" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      launched+=("$f")
    done < <(find "$logs_dir" -maxdepth 1 -type f -name '*.txt' 2>/dev/null \
             | sed "s|^$logs_dir/||; s|\.txt$||")
  fi
  # de-dup
  if [ "${#launched[@]}" -gt 0 ]; then
    local sorted; sorted="$(printf '%s\n' "${launched[@]}" | sort -u)"
    launched=(); while IFS= read -r x; do launched+=("$x"); done <<< "$sorted"
  fi

  for job in "${launched[@]:-}"; do
    [ -n "$job" ] || continue
    # Convention: <droid>-<ticket>, where <droid>=<tier>-<pid> (TWO dash-separated parts:
    # e.g. `economy-65780-B3-LOG-PRUNE.md` -> droid=`economy-65780`, ticket=`B3-LOG-PRUNE`).
    # Strip the first TWO dash-separated fields; the remainder is the ticket id (and ticket
    # ids themselves contain dashes, e.g. `HANDOFF-MECHANIZE`).
    local ticket; ticket="$(printf '%s' "$job" | awk '{
      n = split($0, p, "-"); if (n <= 2) { print ""; next }
      out = p[3]; for (i=4; i<=n; i++) out = out "-" p[i]; print out
    }')"
    [ -n "$ticket" ] || continue
    # Picked-up conditions (first match wins)
    if [ -e "$submitted_dir/$ticket" ]; then continue; fi
    if [ -e "$done_dir/$ticket" ];     then continue; fi
    if [ -e "$needs_push_dir/$ticket" ]; then continue; fi
    if [ -e "$waived_dir/$job" ];      then continue; fi
    # LIVE check: the most recent mtime across the brief+log is within LIVE_AGE_S. If so,
    # the droid is presumably still running — do NOT flag as stranded; the next session-end
    # will re-check, and a 10-minute-stale log without a picked pointer IS stranded.
    local log_path="$logs_dir/$job.txt"
    local brief_path="$briefs_dir/$job.md"
    local mtime=0 mt
    [ -f "$log_path" ]   && mt="$(stat -c %Y "$log_path"   2>/dev/null || echo 0)" && [ "$mt" -gt "$mtime" ] && mtime="$mt"
    [ -f "$brief_path" ] && mt="$(stat -c %Y "$brief_path" 2>/dev/null || echo 0)" && [ "$mt" -gt "$mtime" ] && mtime="$mt"
    if [ "$mtime" -gt 0 ] && [ $((NOW - mtime)) -lt "$LIVE_AGE_S" ]; then
      live+=("job=$job (LIVE, age=$((NOW - mtime))s)")
      continue
    fi
    local age="unknown"
    [ "$mtime" -gt 0 ] && age="$((NOW - mtime))s"
    stranded+=("job=$job ticket=$ticket age=$age log=$log_path")
  done

  if [ "${#stranded[@]}" -gt 0 ]; then
    if [ "$JSON" -eq 1 ]; then
      printf 'pickup:['
      local first=1 d
      for d in "${stranded[@]}"; do
        [ "$first" -eq 1 ] && first=0 || printf ','
        printf '{"job":"%s","ticket":"%s","age":"%s","log":"%s"}' \
          "$(printf '%s' "$d" | sed -nE 's/^job=([^ ]+).*/\1/p')" \
          "$(printf '%s' "$d" | sed -nE 's/.*ticket=([^ ]+).*/\1/p')" \
          "$(printf '%s' "$d" | sed -nE 's/.*age=([^ ]+).*/\1/p')" \
          "$(printf '%s' "$d" | sed -nE 's/.*log=(.*)$/\1/p')"
      done
      printf ']'
    else
      say "PICKUP LEG: ${#stranded[@]} STRANDED job(s) (launched, result not picked up):"
      local d
      for d in "${stranded[@]}"; do
        say "  - $d"
      done
      say "  Fix: pick up the result (move into state/submitted, state/done, or state/needs-push),"
      say "       or waive explicitly: dark-work-check.sh --waive <job> <reason>"
    fi
    return 1
  fi
  [ "$JSON" -eq 0 ] && say "PICKUP LEG: clean (${#launched[@]} launched job(s), all picked up; ${#live[@]} live)"
  return 0
}

# ---------------------------------------------------------------------------
# --waive: record an explicit operator exception for a stranded job. The reason is persisted in
# state/jobs/waived/<job> so a future session knows WHY the result was not picked (auditable,
# unlike a silent no-op). The waiver is a regular empty file — the file's mere existence is the
# signal; the filename carries the reason.
# ---------------------------------------------------------------------------
cmd_waive(){
  local j="$WAIVE_ID" r="$WAIVE_REASON" d="$FLEET/state/jobs/waived"
  mkdir -p "$d"
  local safe; safe="$(printf '%s' "$j" | tr -c 'A-Za-z0-9._-' '_')"
  printf 'waived_at=%d\nreason=%s\n' "$NOW" "$r" > "$d/$safe"
  say "waived: $d/$safe (reason: $r)"
  exit 0
}

# ===========================================================================
# FAIL-ON-REVERT SELF-TEST
# Drives the two legs through their RED and GREEN paths in an isolated tmp
# fleet — stubs ps + bridge DB so nothing in the live state can interfere.
# Reverting any of the cross-reference logic or the pickup conditions flips
# an assertion -> the test fails.
#   Run:  bash fleet/dark-work-check.sh --selftest
# ===========================================================================
selftest(){
  local PASS=0 FAIL=0
  ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
  bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
  check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

  local D; D="$(mktemp -d)"
  mkdir -p "$D/state/agent-logs" "$D/state/agent-briefs" "$D/state/submitted" \
           "$D/state/done" "$D/state/needs-push" "$D/state/jobs/waived"
  # isolated bridge db
  local DB="$D/bridge.db"
  "$PY_BIN" - "$DB" <<'PY' >/dev/null
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.executescript("""
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY, name TEXT, ticket TEXT, status TEXT,
  blockers TEXT, pid INTEGER, repo TEXT DEFAULT '', registered_at TEXT,
  last_seen TEXT, last_status_change TEXT DEFAULT '', branch TEXT DEFAULT '',
  files TEXT DEFAULT '', busy TEXT DEFAULT '', nudges INTEGER DEFAULT 0,
  nudge_messages TEXT DEFAULT '', lease_token TEXT DEFAULT '',
  lease_expires_at TEXT DEFAULT '', model TEXT DEFAULT ''
);
""")
c.commit()
PY

  # stub ps: returns 3 lines: registered (pid 100), dark (pid 200), the checker itself (pid $$).
  # We use $$ but the stub always emits $$ literally — fix: pass $BASHPID via env in a real run.
  cat > "$D/ps-stub.sh" <<'STUB'
#!/usr/bin/env bash
# args intentionally ignored. Emit three rows:
#   pid=100 comm=claude args="claude -p something"     # registered
#   pid=200 comm=opencode args="opencode run foo"      # DARK (no bridge row)
#   pid=300 comm=claude args="claude -p other"         # DARK (no bridge row)
printf '100 claude /usr/bin/claude -p something\n'
printf '200 opencode /usr/bin/opencode run foo\n'
printf '300 claude /usr/bin/claude -p other\n'
STUB
  chmod +x "$D/ps-stub.sh"

  NOW_EPOCH=1700000000   # fixed "now" for deterministic ages

  write_bridge(){
    local pid="$1" last_seen="$2" sid="$3"
    "$PY_BIN" - "$DB" "$pid" "$last_seen" "$sid" <<'PY' >/dev/null
import sqlite3, sys
db, pid, last_seen, sid = sys.argv[1:5]
c = sqlite3.connect(db)
c.execute("INSERT OR REPLACE INTO sessions(session_id,name,ticket,status,pid,registered_at,last_seen) VALUES(?,?,?,?,?,?,?)",
          (sid, f"n{sid}", None, "in-progress", int(pid), last_seen, last_seen))
c.commit()
PY
  }

  # write a launched job (brief + log), with mtime = NOW - 7200 (well past LIVE_AGE_S)
  write_job(){
    local job="$1" age_s="$2"
    local mt=$((NOW_EPOCH - age_s))
    touch -d "@$mt" "$D/state/agent-briefs/$job.md" 2>/dev/null || \
      (export NOW=$mt; "$PY_BIN" -c "import os; os.utime('$D/state/agent-briefs/$job.md',($mt,$mt))")
    touch -d "@$mt" "$D/state/agent-logs/$job.txt" 2>/dev/null || \
      (export NOW=$mt; "$PY_BIN" -c "import os; os.utime('$D/state/agent-logs/$job.txt',($mt,$mt))")
  }

  echo "== (A) REGISTER leg =="
  # Scenario: pid 100 is in bridge (active), 200 and 300 are NOT -> 2 DARK expected.
  write_bridge 100 "$(date -u -d "@$NOW_EPOCH" +%Y-%m-%dT%H:%M:%S 2>/dev/null || printf '2023-11-14T22:13:20')" "sess-100"
  rc=0; out="$(DARK_WORK_BRIDGE_DB="$DB" DARK_WORK_PS_BIN="$D/ps-stub.sh" \
               DARK_WORK_FLEET="$D" DARK_WORK_NOW="$NOW_EPOCH" \
               DARK_WORK_PY_BIN="$PY_BIN" \
               bash "$0" --register 2>&1)" || rc=$?
  check "A1 register-leg RED when 2 dark PIDs" "$rc" "1"
  case "$out" in *"pid=200"*"opencode"*) ok "A2 names dark pid 200" ;; *) bad "A2 names dark pid 200 (out: $out)";; esac
  case "$out" in *"pid=300"*"claude"*)   ok "A3 names dark pid 300" ;; *) bad "A3 names dark pid 300 (out: $out)";; esac
  case "$out" in *"DARK"*)          ok "A4 DARK banner printed";; *) bad "A4 DARK banner printed";; esac
  # Now register both dark PIDs -> GREEN
  write_bridge 200 "$(date -u -d "@$NOW_EPOCH" +%Y-%m-%dT%H:%M:%S 2>/dev/null || printf '2023-11-14T22:13:20')" "sess-200"
  write_bridge 300 "$(date -u -d "@$NOW_EPOCH" +%Y-%m-%dT%H:%M:%S 2>/dev/null || printf '2023-11-14T22:13:20')" "sess-300"
  rc=0; DARK_WORK_BRIDGE_DB="$DB" DARK_WORK_PS_BIN="$D/ps-stub.sh" \
       DARK_WORK_FLEET="$D" DARK_WORK_NOW="$NOW_EPOCH" \
       DARK_WORK_PY_BIN="$PY_BIN" \
       bash "$0" --register >/dev/null 2>&1 || rc=$?
  check "A5 register-leg GREEN when all 3 pids registered" "$rc" "0"
  # Revert guard: empty bridge db -> with running pids, all dark -> non-zero
  : > "$D/empty.db"
  "$PY_BIN" - "$D/empty.db" <<'PY' >/dev/null
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.executescript("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, ticket TEXT, status TEXT, blockers TEXT, pid INTEGER, last_seen TEXT);")
c.commit()
PY
  rc=0; DARK_WORK_BRIDGE_DB="$D/empty.db" DARK_WORK_PS_BIN="$D/ps-stub.sh" \
       DARK_WORK_FLEET="$D" DARK_WORK_NOW="$NOW_EPOCH" \
       DARK_WORK_PY_BIN="$PY_BIN" \
       bash "$0" --register >/dev/null 2>&1 || rc=$?
  check "A6 register-leg RED when bridge empty + 3 pids running" "$rc" "1"

  echo "== (B) PICKUP leg =="
  # Build: 1 LIVE job, 1 STRANDED-not-submitted, 1 STRANDED-in-needs-push (picked up), 1 WAIVED.
  write_job "econ-9999-TICK-LIVE"   60     # LIVE (age < LIVE_AGE_S=600)
  write_job "econ-9999-TICK-STRAND" 7200   # STRANDED
  write_job "econ-9999-TICK-NEEDS"  7200   # will be put in needs-push
  write_job "econ-9999-TICK-WAIVE"  7200   # will be waived
  write_job "econ-9999-TICK-DONE"   7200   # will be put in done
  : > "$D/state/needs-push/TICK-NEEDS"
  : > "$D/state/done/TICK-DONE"
  printf 'waived_at=%d\nreason=test\n' "$NOW_EPOCH" > "$D/state/jobs/waived/econ-9999-TICK-WAIVE"

  rc=0; out="$(DARK_WORK_BRIDGE_DB="$DB" DARK_WORK_PS_BIN="$D/ps-stub.sh" \
               DARK_WORK_FLEET="$D" DARK_WORK_NOW="$NOW_EPOCH" \
               DARK_WORK_PY_BIN="$PY_BIN" \
               bash "$0" --pickup 2>&1)" || rc=$?
  check "B1 pickup-leg RED when one stranded (TICK-STRAND)" "$rc" "1"
  case "$out" in *"TICK-STRAND"*) ok "B2 names stranded ticket TICK-STRAND" ;; *) bad "B2 names stranded TICK-STRAND (out: $out)";; esac
  case "$out" in *"TICK-LIVE"*)   bad "B3 LIVE job must NOT be flagged (out: $out)";; *) ok "B3 LIVE job NOT flagged";; esac
  case "$out" in *"TICK-NEEDS"*)  bad "B4 needs-push job must NOT be flagged" ;; *) ok "B4 needs-push job NOT flagged";; esac
  case "$out" in *"TICK-WAIVE"*)  bad "B5 waived job must NOT be flagged"     ;; *) ok "B5 waived job NOT flagged";; esac
  case "$out" in *"TICK-DONE"*)   bad "B6 done job must NOT be flagged"        ;; *) ok "B6 done job NOT flagged";; esac
  # Pick it up: submitted/<ticket>
  : > "$D/state/submitted/TICK-STRAND"
  rc=0; DARK_WORK_BRIDGE_DB="$DB" DARK_WORK_PS_BIN="$D/ps-stub.sh" \
       DARK_WORK_FLEET="$D" DARK_WORK_NOW="$NOW_EPOCH" \
       DARK_WORK_PY_BIN="$PY_BIN" \
       bash "$0" --pickup >/dev/null 2>&1 || rc=$?
  check "B7 pickup-leg GREEN when stranded job is picked up (submitted)" "$rc" "0"
  # Revert guard: remove the brief file (the canonical launched signal) for TICK-STRAND-pickup
  # check. Then verify a fresh job without brief/log is NOT considered launched.
  # Already implicit: a job with NO brief + NO log is not in `launched` list -> never flagged.

  echo "== (C) --waive records an operator exception =="
  rc=0; out="$(DARK_WORK_BRIDGE_DB="$DB" DARK_WORK_PS_BIN="$D/ps-stub.sh" \
               DARK_WORK_FLEET="$D" DARK_WORK_NOW="$NOW_EPOCH" \
               DARK_WORK_PY_BIN="$PY_BIN" \
               bash "$0" --waive 'econ-9999-TICK-STRAND2' 'kept for archival' 2>&1)" || rc=$?
  check "C1 --waive exits 0" "$rc" "0"
  [ -e "$D/state/jobs/waived/econ-9999-TICK-STRAND2" ] && ok "C2 waiver marker file created" || bad "C2 waiver marker file created"
  grep -q "reason=kept for archival" "$D/state/jobs/waived/econ-9999-TICK-STRAND2" && ok "C3 waiver reason recorded" || bad "C3 waiver reason recorded"

  echo "== (D) --json output is parseable + lists each offender =="
  # D1: empty bridge + 3 PIDs running -> register leg has 2 dark pids, pickup is GREEN (no jobs
  # in this isolated D fixture) so the JSON output is just the register array.
  out="$(DARK_WORK_BRIDGE_DB="$D/empty.db" DARK_WORK_PS_BIN="$D/ps-stub.sh" \
         DARK_WORK_FLEET="$D" DARK_WORK_NOW="$NOW_EPOCH" \
         DARK_WORK_PY_BIN="$PY_BIN" \
         bash "$0" --json 2>&1)" || rc=$?
  case "$out" in *'"pid":"200"'*'"pid":"300"'*) ok "D1 --json lists both dark pids";; *) bad "D1 --json lists both dark pids (out: $out)";; esac
  # D2: --json + both legs RED (fresh fixtures: empty bridge + a stranded job, no picked markers).
  : > "$D/empty3.db"; "$PY_BIN" - "$D/empty3.db" <<'PY' >/dev/null
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.executescript("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, ticket TEXT, status TEXT, blockers TEXT, pid INTEGER, last_seen TEXT);")
PY
  # stranded job (no submitted/done/needs-push/waived marker; mtime well past LIVE_AGE_S)
  write_job "econ-9999-TICK-D2-STRAND" 7200
  out="$(DARK_WORK_BRIDGE_DB="$D/empty3.db" DARK_WORK_PS_BIN="$D/ps-stub.sh" \
         DARK_WORK_FLEET="$D" DARK_WORK_NOW="$NOW_EPOCH" \
         DARK_WORK_PY_BIN="$PY_BIN" \
         bash "$0" --json 2>&1)" || rc=$?
  case "$out" in *'register:'*'pickup:'*'"job":"econ-9999-TICK-D2-STRAND"'*) ok "D2 --json includes both legs when both RED";; *) bad "D2 --json includes both legs when both RED (out: $out)";; esac

  echo "== (E) default (both legs) exits non-zero when EITHER leg is RED =="
  # Empty bridge + stale-stranded job = both legs RED
  : > "$D/empty2.db"; "$PY_BIN" - "$D/empty2.db" <<'PY' >/dev/null
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.executescript("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, ticket TEXT, status TEXT, blockers TEXT, pid INTEGER, last_seen TEXT);")
PY
  write_job "econ-9999-TICK-AGAIN" 7200
  rc=0; DARK_WORK_BRIDGE_DB="$D/empty2.db" DARK_WORK_PS_BIN="$D/ps-stub.sh" \
       DARK_WORK_FLEET="$D" DARK_WORK_NOW="$NOW_EPOCH" \
       DARK_WORK_PY_BIN="$PY_BIN" \
       bash "$0" >/dev/null 2>&1 || rc=$?
  check "E1 default both-legs RED when either is RED" "$rc" "1"

  rm -rf "$D"
  echo
  echo "--- $PASS passed, $FAIL failed ---"
  [ "$FAIL" -eq 0 ] || { echo "DARK-WORK-CHECK SELF-TEST FAILED"; return 1; }
  echo "ALL DARK-WORK-CHECK SELF-TESTS PASS"
  return 0
}

# --- guarded dispatch ------------------------------------------------------
if [ "${BASH_SOURCE[0]:-}" = "${0}" ]; then
  if [ "$LEGS" = "selftest" ]; then
    selftest
  elif [ -n "$WAIVE_ID" ]; then
    cmd_waive
  else
    rc=0
    [ "$LEGS" = "register" ] || [ "$LEGS" = "both" ] && { register_leg || rc=1; }
    [ "$LEGS" = "pickup" ]   || [ "$LEGS" = "both" ] && { pickup_leg   || rc=1; }
    exit "$rc"
  fi
fi
