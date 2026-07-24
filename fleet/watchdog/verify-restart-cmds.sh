#!/usr/bin/env bash
# verify-restart-cmds.sh — HARD PRE-ENABLE GATE for the service watchdog.
#
# WHY THIS EXISTS (the defect it closes):
#   monit runs as ROOT with cwd=/ and no login shell. Every seed restart_cmd in
#   fleet/state/service-registry.tsv was written from a `stack` interactive-shell point of view and
#   was therefore BROKEN in monit's context:
#     grader-daemon  -> `systemctl restart bench-grader-daemon`  (NO such unit on this box)
#     session-bridge -> `systemctl --user restart session-bridge` (no user unit; --user is
#                                                                  meaningless for root)
#     roci-tunnel    -> `fleet/bridge-reconnect.sh`               (RELATIVE path + file missing)
#     gateway-4lom   -> `ssh 4-LOM sudo systemctl restart ...`    (`4-LOM` is a Host alias in
#                                                                  stack's ~/.ssh/config, not
#                                                                  root's; remote sudo is not
#                                                                  NOPASSWD -> would hang/fail)
#   With those in place, enabling monit means: service dies -> monit runs a command that FAILS ->
#   auto-recovery MISFIRES. That is the 9-day-stale-grader incident relocated to the RESTART step.
#   So: nothing may enable monit until every restart_cmd is proven runnable as root.
#
# WHAT IT CHECKS
#   STATIC (hermetic — registry text only, no filesystem, safe in CI):
#     R1 restart_cmd present and not `none`
#     R2 no ' or " — the generated monit stanza wraps it in /bin/sh -c '<cmd>', so a quote breaks
#        the config (or injects into it)
#     R3 no ~ / $HOME — root's ~ is /root, NOT the service owner's home
#     R4 no `systemctl --user` — root has no user bus for these services
#     R5 every command word is an ABSOLUTE path — monit has no login PATH and cwd=/
#     R6 no `sudo` — monit is already root locally, and the remote leg has no NOPASSWD
#     R7 ssh legs carry -i <key>, BatchMode=yes, an explicit UserKnownHostsFile, a user@host
#        destination (never a ~/.ssh/config Host alias), and never StrictHostKeyChecking=no
#   LIVE (this box — the runnability proof):
#     L1 every command word passes `test -x`
#     L2 `systemctl restart <unit>` -> `systemctl cat <unit>` must resolve (unit really installed)
#     L3 runuser/su/setpriv `-u <user>` -> the user really exists (getent passwd)
#     L4 every /absolute .py/.sh operand exists (and .sh is executable)
#     L5 ssh -i key file exists; UserKnownHostsFile exists AND has a key for the destination host
#     L6 fleet/watchdog/units/*.service: ExecStart binary is executable, its script operand
#        exists, and any User= exists on this box (a shipped unit must not rot)
#
# FAIL-CLOSED / NON-VACUOUS (this gate guards the guard):
#   - registry unreadable, ZERO data rows, or ANY malformed row  -> RED (never a silent pass)
#   - zero checks executed                                       -> RED
#   - it NEVER executes a restart_cmd; it only resolves it
#
# USAGE
#   verify-restart-cmds.sh                # STATIC + LIVE  (the real gate; run before enabling monit)
#   verify-restart-cmds.sh --static-only  # STATIC only — hermetic, no filesystem/box dependency
#   verify-restart-cmds.sh --quiet        # only the verdict line + failures
# EXIT: 0 GREEN (every restart_cmd resolves) · 1 RED (fail-closed) · 2 usage
#
# TEST SEAMS: WD_REGISTRY (registry path, see watchdog-lib.sh), VERIFY_UNITS_DIR (units dir).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WD_FLEET="$(cd "$HERE/.." && pwd)"; export WD_FLEET
# shellcheck source=/dev/null
source "$HERE/watchdog-lib.sh"

MODE="full"; QUIET=0
while [ $# -gt 0 ]; do case "$1" in
  --static-only) MODE="static"; shift;;
  --quiet) QUIET=1; shift;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
  *) echo "verify-restart-cmds: unknown arg '$1'" >&2; exit 2;;
esac; done

UNITS_DIR="${VERIFY_UNITS_DIR:-$HERE/units}"

FAILS=0
CHECKS=0
say(){ [ "$QUIET" -eq 1 ] || printf '%s\n' "$*"; }
okc(){ CHECKS=$((CHECKS+1)); say "    ok   $*"; }
red(){ CHECKS=$((CHECKS+1)); FAILS=$((FAILS+1)); printf '    RED  %s\n' "$*"; }

# ---------------------------------------------------------------- registry load (fail-closed)
if [ ! -f "$WD_REGISTRY" ]; then
  echo "verify-restart-cmds: RED — registry not found: $WD_REGISTRY" >&2
  exit 1
fi
# Count DATA lines (non-blank, non-comment) directly, then compare against what the shared
# grammar accepts. wd_rows SKIPS malformed rows with a warning; a skipped money-path row must
# never look like "nothing to check", so a mismatch is RED.
DATA_LINES="$(grep -cve '^[[:space:]]*$' -e '^[[:space:]]*#' "$WD_REGISTRY")"
ROWS="$(wd_rows 2>/dev/null)"
if [ -z "$ROWS" ]; then ROW_COUNT=0; else ROW_COUNT="$(printf '%s\n' "$ROWS" | wc -l)"; fi
if [ "$DATA_LINES" -eq 0 ]; then
  echo "verify-restart-cmds: RED — registry has ZERO service rows ($WD_REGISTRY);" \
       "a watchdog that supervises nothing must never report GREEN" >&2
  exit 1
fi
if [ "$ROW_COUNT" -ne "$DATA_LINES" ]; then
  echo "verify-restart-cmds: RED — $DATA_LINES data row(s) in the registry but only $ROW_COUNT" \
       "well-formed (7-column) row(s); malformed rows are NOT skipped silently here" >&2
  exit 1
fi

# ---------------------------------------------------------------- helpers
# strip_redirs <cmd> -> command text with shell redirections removed (so `2>&1`/`</dev/null` are
# not mistaken for command words or for the `&` separator).
strip_redirs(){
  printf '%s' "$1" | sed -E 's/[0-9]*>&[0-9]+/ /g; s/[0-9]*>>?[^[:space:]]+/ /g; s/[0-9]*<[^[:space:]]+/ /g'
}
# segments <cmd> -> one shell segment per line (split on ; && || | &).
segments(){
  strip_redirs "$1" | sed -E 's/&&/\n/g; s/\|\|/\n/g; s/;/\n/g; s/\|/\n/g; s/&/\n/g'
}
# cmd_word <segment> -> the command word (skips leading VAR=value assignments); empty if none.
cmd_word(){
  local w
  for w in $1; do
    case "$w" in *=*) case "$w" in /*|./*|../*) printf '%s' "$w"; return;; esac; continue;; esac
    printf '%s' "$w"; return
  done
}

# ---------------------------------------------------------------- per-service checks
check_static(){                       # check_static <name> <cmd>
  local name="$1" cmd="$2" seg w prev dest have_i=0 have_batch=0 have_kh=0 is_ssh=0
  if [ -z "$cmd" ] || [ "$cmd" = "none" ]; then
    red "$name: restart_cmd is empty/none — a supervised service with no restart is un-recoverable"
    return
  fi
  case "$cmd" in
    *\'*) red "$name: restart_cmd contains a single quote — monit renders it inside /bin/sh -c '<cmd>'";;
    *\"*) red "$name: restart_cmd contains a double quote — it would terminate the monit config string";;
    *)    okc "$name: quote-safe for the monit /bin/sh -c '<cmd>' wrapper";;
  esac
  # shellcheck disable=SC2016  # matching the LITERAL text ~ / $HOME in the command, not expanding it
  case "$cmd" in
    *'~'*|*'$HOME'*) red "$name: restart_cmd uses ~ / \$HOME — monit runs as ROOT, so that resolves to /root";;
    *)               okc "$name: no ~ / \$HOME (root-context safe)";;
  esac
  case "$cmd" in
    *'systemctl --user'*|*'--user restart'*) red "$name: uses 'systemctl --user' — meaningless for root (no user bus)";;
    *)                                       okc "$name: no 'systemctl --user'";;
  esac
  case " $cmd " in
    *' sudo '*|*'/sudo '*) red "$name: uses sudo — monit is already root locally, and the 4-LOM leg has NO NOPASSWD (would hang/fail)";;
    *)                     okc "$name: no sudo";;
  esac
  # every command word absolute — INCLUDING the one nested behind a wrapper (setsid/nohup/env) or
  # behind runuser's `--`, which is where a relative path most easily hides.
  while IFS= read -r seg; do
    [ -n "${seg// /}" ] || continue
    w="$(cmd_word "$seg")"
    [ -n "$w" ] || continue
    case "$w" in
      /*) okc "$name: command word is absolute: $w";;
      *)  red "$name: command word '$w' is NOT an absolute path — monit has cwd=/ and no login PATH";;
    esac
    prev=""
    for w in $seg; do
      case "$prev" in
        */setsid|*/nohup|*/env|*/timeout|--)
          case "$w" in
            /*) okc "$name: nested command after '$prev' is absolute: $w";;
            -*) ;;
            *)  red "$name: nested command '$w' after '$prev' is NOT absolute — it would not resolve under monit";;
          esac;;
      esac
      prev="$w"
    done
  done <<< "$(segments "$cmd")"
  # ssh leg hygiene
  case "$cmd" in *'/ssh '*) is_ssh=1;; esac
  if [ "$is_ssh" -eq 1 ]; then
    prev=""; dest=""
    for w in $cmd; do
      case "$w" in
        -i) have_i=1;;
        BatchMode=yes) have_batch=1;;
        UserKnownHostsFile=*) have_kh=1;;
        StrictHostKeyChecking=no) red "$name: ssh leg disables host-key checking — never weaken this to make a gate pass";;
        *@*) [ -z "$dest" ] && dest="$w";;
      esac
      prev="$w"
    done
    : "$prev"
    if [ "$have_i" -eq 1 ]; then okc "$name: ssh leg pins an identity file (-i) — root has no agent/keys of its own"
    else red "$name: ssh leg has no -i <keyfile> — root cannot authenticate"; fi
    if [ "$have_batch" -eq 1 ]; then okc "$name: ssh leg is BatchMode=yes (never prompts under monit)"
    else red "$name: ssh leg is not BatchMode=yes — it could block forever on a prompt"; fi
    if [ "$have_kh" -eq 1 ]; then okc "$name: ssh leg pins UserKnownHostsFile (root's is empty)"
    else red "$name: ssh leg has no explicit UserKnownHostsFile — root's known_hosts is empty"; fi
    if [ -n "$dest" ]; then okc "$name: ssh destination is explicit ($dest), not a ~/.ssh/config Host alias"
    else red "$name: ssh destination is not user@host — a Host alias only exists in stack's ~/.ssh/config"; fi
  fi
}

check_live(){                         # check_live <name> <cmd>
  local name="$1" cmd="$2" seg w unit next prev khf host
  while IFS= read -r seg; do
    [ -n "${seg// /}" ] || continue
    # EVERY absolute binary in the segment, not just the leading command word — a wrapper chain
    # (`setsid runuser -- python3 ...`) hides three more executables behind the first one.
    prev=""
    for w in $seg; do
      case "$prev" in -i|-f|-o|-F|-p|-c|-u|--user|--reuid) prev="$w"; continue;; esac
      case "$w" in
        /*.py|/*.sh) ;;                          # script operands: checked below
        /*) if [ -x "$w" ]; then okc "$name: test -x $w"
            else red "$name: NOT executable/not present: $w"; fi;;
      esac
      prev="$w"
    done
    # systemctl restart <unit> -> the unit must really resolve
    case "$seg" in
      */systemctl\ *|*/systemctl)
        unit=""; next=0
        for prev in $seg; do
          if [ "$next" -eq 1 ]; then unit="$prev"; break; fi
          [ "$prev" = "restart" ] && next=1
        done
        if [ -n "$unit" ]; then
          if systemctl cat -- "$unit" >/dev/null 2>&1; then
            okc "$name: systemctl cat $unit resolves (unit is installed)"
          else
            red "$name: systemd unit '$unit' does NOT exist on this box (systemctl cat failed) — install it first: see $UNITS_DIR/README.md"
          fi
        fi;;
    esac
    # runuser/su/setpriv target user must exist
    case "$seg" in
      */runuser\ *|*/su\ *|*/setpriv\ *)
        unit=""; next=0
        for prev in $seg; do
          if [ "$next" -eq 1 ]; then unit="$prev"; break; fi
          case "$prev" in -u|--user|--reuid) next=1;; esac
        done
        if [ -n "$unit" ]; then
          if getent passwd "$unit" >/dev/null 2>&1; then okc "$name: target user '$unit' exists"
          else red "$name: target user '$unit' does NOT exist on this box"; fi
        fi;;
    esac
  done <<< "$(segments "$cmd")"

  # every absolute .py/.sh operand must exist (this is what the restart actually launches)
  for w in $(strip_redirs "$cmd"); do
    case "$w" in
      /*.py) if [ -r "$w" ]; then okc "$name: test -r $w"
             else red "$name: script operand missing/unreadable: $w"; fi;;
      /*.sh) if [ -x "$w" ]; then okc "$name: test -x $w"
             else red "$name: script operand missing or not executable: $w"; fi;;
    esac
  done

  # ssh identity + known_hosts must really be there for ROOT to use
  case "$cmd" in
    *'/ssh '*)
      khf=""; host=""; next=0
      for w in $(strip_redirs "$cmd"); do
        if [ "$next" -eq 1 ]; then
          if [ -r "$w" ]; then okc "$name: ssh identity file readable: $w"
          else red "$name: ssh identity file missing: $w"; fi
          next=0; continue
        fi
        case "$w" in
          -i) next=1;;
          UserKnownHostsFile=*) khf="${w#UserKnownHostsFile=}";;
          *@*) [ -z "$host" ] && host="${w#*@}";;
        esac
      done
      if [ -n "$khf" ]; then
        if [ ! -r "$khf" ]; then
          red "$name: UserKnownHostsFile not readable: $khf"
        elif [ -n "$host" ] && ssh-keygen -F "$host" -f "$khf" >/dev/null 2>&1; then
          okc "$name: $khf has a host key for $host (root can verify the host)"
        else
          red "$name: $khf has NO host key for '$host' — root's ssh would fail StrictHostKeyChecking"
        fi
      fi;;
  esac
}

check_units(){
  local f execbin p user
  [ -d "$UNITS_DIR" ] || { say "  units: no $UNITS_DIR (nothing shipped) — skipping"; return; }
  shopt -s nullglob
  local units=("$UNITS_DIR"/*.service)
  shopt -u nullglob
  [ "${#units[@]}" -gt 0 ] || { say "  units: no *.service shipped"; return; }
  for f in "${units[@]}"; do
    say "  unit $(basename "$f")"
    if grep -q '^\[Service\]' "$f" && grep -q '^ExecStart=' "$f"; then
      okc "$(basename "$f"): has [Service] + ExecStart"
    else
      red "$(basename "$f"): missing [Service] or ExecStart"
      continue
    fi
    execbin="$(sed -n 's/^ExecStart=//p' "$f" | head -1)"
    # shellcheck disable=SC2086  # deliberate: split ExecStart into binary + operands
    set -- $execbin
    if [ -x "${1:-}" ]; then okc "$(basename "$f"): ExecStart binary executable: $1"
    else red "$(basename "$f"): ExecStart binary missing/not executable: ${1:-<empty>}"; fi
    for p in "$@"; do
      case "$p" in
        /*.py) if [ -r "$p" ]; then okc "$(basename "$f"): ExecStart script readable: $p"
               else red "$(basename "$f"): ExecStart script missing: $p"; fi;;
        /*.sh) if [ -x "$p" ]; then okc "$(basename "$f"): ExecStart script executable: $p"
               else red "$(basename "$f"): ExecStart script missing/not executable: $p"; fi;;
      esac
    done
    user="$(sed -n 's/^User=//p' "$f" | head -1)"
    if [ -n "$user" ]; then
      if getent passwd "$user" >/dev/null 2>&1; then okc "$(basename "$f"): User=$user exists"
      else red "$(basename "$f"): User=$user does NOT exist on this box"; fi
    fi
  done
}

# ---------------------------------------------------------------- run
say "verify-restart-cmds: registry $WD_REGISTRY ($ROW_COUNT service row(s), mode=$MODE)"
while IFS= read -r row; do
  name="$(wd_field "$row" 1)"
  cmd="$(wd_field "$row" 6)"
  say "  service $name"
  say "    restart_cmd: $cmd"
  check_static "$name" "$cmd"
  [ "$MODE" = "full" ] && check_live "$name" "$cmd"
done <<< "$ROWS"

[ "$MODE" = "full" ] && check_units

if [ "$CHECKS" -eq 0 ]; then
  echo "verify-restart-cmds: RED — ZERO checks executed; a vacuous pass is not a pass" >&2
  exit 1
fi

if [ "$FAILS" -eq 0 ]; then
  echo "verify-restart-cmds: GREEN — $ROW_COUNT service(s), $CHECKS check(s), 0 failures (mode=$MODE)"
  exit 0
fi
echo "verify-restart-cmds: RED — $FAILS of $CHECKS check(s) FAILED across $ROW_COUNT service(s)." >&2
echo "  monit MUST NOT be enabled: on a service death it would run a command that fails." >&2
echo "  Fix fleet/state/service-registry.tsv (column 6) and re-run: fleet/watchdog/verify-restart-cmds.sh" >&2
exit 1
