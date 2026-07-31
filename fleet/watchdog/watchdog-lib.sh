# shellcheck shell=bash
# watchdog-lib.sh — SSOT for the service-watchdog probe grammar.
# `source` this AFTER the caller sets WD_FLEET (defaults derived if unset).
#
# WHY ONE LIB: the registry probe grammar (how an `alive_probe` / `freshness_probe`
# string is interpreted) MUST be defined once. generate-monit-config.sh renders it into
# monit stanzas; discover-services.sh evaluates it directly (monit-independent, so the
# 9-day-stale-grader case is still caught on a box where monit is not yet installed);
# monit-selfwatch.sh reuses the freshness primitive for monit's own heartbeat. Three
# consumers, one grammar — never re-parsed per caller (the drift class _lib.sh exists to
# kill). See fleet/board/SERVICE-LIVENESS-WATCHDOG.md.
#
# REGISTRY ROW (TAB-separated, fleet/state/service-registry.tsv):
#   name  kind  alive_probe  freshness_probe  freshness_ttl_s  restart_cmd  owner
#
# alive_probe grammar:
#   pgrep:<ere>          process whose `pgrep -f` ERE matches at least one live pid
#   pidfile:<path>       pid in <path> is a live process
#   tcp:<host>:<port>    a TCP connect to host:port succeeds (bash /dev/tcp, no nc dep)
#   unixsock:<path>      <path> exists and is a unix socket
#   program:<cmd>        <cmd> exits 0 (arbitrary custom probe)
#   none                 no alive dimension (freshness-only service)
#
# freshness_probe grammar:
#   file:<path>          <path> mtime must be within freshness_ttl_s
#   none                 no freshness dimension (alive-only service)
#
# Paths may start with ~ or $HOME (expanded by wd_expand). TTL is integer seconds.
#
# TEST SEAMS (never used in normal operation):
#   WD_REGISTRY=<path>   override the registry file
#   WD_NOW=<epoch>       override "now" for freshness math
#   WD_TCP_TIMEOUT=<s>   TCP connect timeout (default 3)

WD_FLEET="${WD_FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WD_REGISTRY="${WD_REGISTRY:-$WD_FLEET/state/service-registry.tsv}"
WD_TCP_TIMEOUT="${WD_TCP_TIMEOUT:-3}"
WD_TAB="$(printf '\t')"

wd_now(){ echo "${WD_NOW:-$(date +%s)}"; }

# wd_expand <path> -> path with a leading ~ / $HOME expanded.
wd_expand(){ local p="$1"; case "$p" in
  "~"/*|"~") p="${HOME}${p#\~}";;
  '$HOME'/*) p="${HOME}${p#\$HOME}";;
esac; printf '%s' "$p"; }

# wd_mtime <file> -> epoch mtime, or empty string if the file does not exist.
wd_mtime(){ [ -e "$1" ] || return 1; date -r "$1" +%s 2>/dev/null || stat -c %Y "$1" 2>/dev/null; }

# wd_probe_alive <alive_probe> -> 0 ALIVE, 1 DEAD, 3 UNKNOWN/unsupported.
wd_probe_alive(){
  local spec="$1" kind="${1%%:*}" arg="${1#*:}"
  case "$spec" in none|"") return 3;; esac
  case "$kind" in
    pgrep)    pgrep -f -- "$arg" >/dev/null 2>&1 && return 0 || return 1;;
    pidfile)  local pf; pf="$(wd_expand "$arg")"; [ -f "$pf" ] || return 1
              local pid; pid="$(head -1 "$pf" 2>/dev/null | tr -dc '0-9')"
              [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && return 0 || return 1;;
    tcp)      local host="${arg%%:*}" port="${arg##*:}"
              timeout "$WD_TCP_TIMEOUT" bash -c "exec 3<>/dev/tcp/$host/$port" 2>/dev/null && return 0 || return 1;;
    unixsock) local sp; sp="$(wd_expand "$arg")"; [ -S "$sp" ] && return 0 || return 1;;
    program)  ( eval "$arg" ) >/dev/null 2>&1 && return 0 || return 1;;
    *)        return 3;;
  esac
}

# wd_probe_fresh <freshness_probe> <ttl_s> -> 0 FRESH, 1 STALE, 2 MISSING, 3 N/A(none).
wd_probe_fresh(){
  local spec="$1" ttl="${2:-0}" kind="${1%%:*}" arg="${1#*:}"
  case "$spec" in none|"") return 3;; esac
  case "$kind" in
    file) local fp mt now age; fp="$(wd_expand "$arg")"
          mt="$(wd_mtime "$fp")" || return 2
          [ -n "$mt" ] || return 2
          now="$(wd_now)"; age=$(( now - mt ))
          [ "$age" -le "$ttl" ] && return 0 || return 1;;
    *)    return 3;;
  esac
}

# wd_rows -> emit validated registry rows (TAB-separated), comments/blank stripped.
# A row without exactly 7 columns is a malformed registry entry -> warn to stderr, skip
# (fail-closed at the caller: a malformed money-path row must not silently vanish).
wd_rows(){
  [ -f "$WD_REGISTRY" ] || { echo "watchdog-lib: registry not found: $WD_REGISTRY" >&2; return 1; }
  local line n
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue;; esac
    n="$(awk -F"$WD_TAB" '{print NF}' <<<"$line")"
    if [ "$n" -ne 7 ]; then
      echo "watchdog-lib: MALFORMED registry row ($n cols, want 7): ${line:0:60}" >&2
      continue
    fi
    printf '%s\n' "$line"
  done < "$WD_REGISTRY"
}

# wd_field <row> <n> -> column n (1-based) of a TAB row.
wd_field(){ awk -F"$WD_TAB" -v n="$2" '{print $n}' <<<"$1"; }

# wd_sanitize <name> -> a monit-safe identifier (alnum + dash).
wd_sanitize(){ printf '%s' "$1" | tr -c 'a-zA-Z0-9_-' '-' | sed 's/-\{1,\}/-/g; s/^-//; s/-$//'; }
