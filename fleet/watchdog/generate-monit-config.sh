#!/usr/bin/env bash
# generate-monit-config.sh — render monit.d/*.conf FROM fleet/state/service-registry.tsv.
#
# THE ADOPT: monit is the best-in-class process-alive + file-freshness + restart + alert
# supervisor. We do NOT hand-roll a liveness loop — we generate monit's config from the
# declarative registry (one stanza per service). Never hand-edit the rendered files; edit the
# registry and re-render. See fleet/board/SERVICE-LIVENESS-WATCHDOG.md.
#
# Each registry row becomes:
#   - a `check process/host/program` stanza (from alive_probe) with a start/restart action, AND
#   - when freshness_probe != none, a `check file <name>-freshness` stanza that exec's the
#     restart_cmd once the output mtime exceeds the TTL (the anti-staleness / hung-service case).
#
# USAGE
#   generate-monit-config.sh                 # render into fleet/watchdog/monit.d/ (default)
#   generate-monit-config.sh --out <dir>     # render into <dir>
#   generate-monit-config.sh --stdout        # print the full config to stdout, write nothing
#   generate-monit-config.sh --check         # render to a temp dir + diff vs committed; RED on drift
#
# TEST SEAMS: WD_REGISTRY overrides the registry (see watchdog-lib.sh).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WD_FLEET="$(cd "$HERE/.." && pwd)"; export WD_FLEET
# shellcheck source=/dev/null
source "$HERE/watchdog-lib.sh"

OUT_DIR="$HERE/monit.d"
MODE="write"
while [ $# -gt 0 ]; do case "$1" in
  --out) OUT_DIR="$2"; shift 2;;
  --stdout) MODE="stdout"; shift;;
  --check) MODE="check"; shift;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
  *) echo "generate-monit-config: unknown arg '$1'" >&2; exit 2;;
esac; done

# render_row <row> -> emit the monit stanza(s) for one registry row on stdout.
render_row(){
  local row="$1"
  local name kind alive fresh ttl restart owner id ap_kind ap_arg
  name="$(wd_field "$row" 1)"; kind="$(wd_field "$row" 2)"
  alive="$(wd_field "$row" 3)"; fresh="$(wd_field "$row" 4)"
  ttl="$(wd_field "$row" 5)"; restart="$(wd_field "$row" 6)"; owner="$(wd_field "$row" 7)"
  id="$(wd_sanitize "$name")"
  ap_kind="${alive%%:*}"; ap_arg="${alive#*:}"

  printf '# --- %s (owner: %s) — GENERATED from service-registry.tsv; do not hand-edit ---\n' "$name" "$owner"
  case "$ap_kind" in
    pgrep)
      printf 'check process %s matching "%s"\n' "$id" "$ap_arg"
      printf '    start program = "/bin/sh -c '\''%s'\''" with timeout 60 seconds\n' "$restart"
      printf '    if not exist for 2 cycles then restart\n'
      printf '    if 4 restarts within 6 cycles then alert\n';;
    pidfile)
      printf 'check process %s with pidfile "%s"\n' "$id" "$(wd_expand "$ap_arg")"
      printf '    start program = "/bin/sh -c '\''%s'\''" with timeout 60 seconds\n' "$restart"
      printf '    if not exist for 2 cycles then restart\n'
      printf '    if 4 restarts within 6 cycles then alert\n';;
    tcp)
      printf 'check host %s address %s\n' "$id" "${ap_arg%%:*}"
      printf '    if failed port %s type tcp for 2 cycles then exec "/bin/sh -c '\''%s'\''"\n' "${ap_arg##*:}" "$restart"
      printf '    if failed port %s type tcp for 3 cycles then alert\n' "${ap_arg##*:}";;
    unixsock)
      printf 'check program %s with path "/usr/bin/test -S %s"\n' "$id" "$(wd_expand "$ap_arg")"
      printf '    start program = "/bin/sh -c '\''%s'\''" with timeout 60 seconds\n' "$restart"
      printf '    if status != 0 for 2 cycles then restart\n';;
    program)
      printf 'check program %s with path "/bin/sh -c '\''%s'\''"\n' "$id" "$ap_arg"
      printf '    start program = "/bin/sh -c '\''%s'\''" with timeout 60 seconds\n' "$restart"
      printf '    if status != 0 for 2 cycles then restart\n';;
    none) : ;;
    *) printf '# WARN: unsupported alive_probe kind "%s" for %s\n' "$ap_kind" "$name";;
  esac

  # Anti-staleness: a HUNG-but-alive service producing nothing must alarm + restart just like a
  # dead one (the 9-day-stale-grader case). freshness_probe file mtime older than TTL -> exec restart.
  case "$fresh" in
    none|"") : ;;
    file:*)
      local fp="${fresh#file:}"
      printf 'check file %s-freshness path "%s"\n' "$id" "$(wd_expand "$fp")"
      printf '    if timestamp > %s seconds for 2 cycles then exec "/bin/sh -c '\''%s'\''"\n' "$ttl" "$restart"
      printf '    if timestamp > %s seconds for 3 cycles then alert\n' "$ttl"
      printf '    if does not exist then alert\n';;
    *) printf '# WARN: unsupported freshness_probe "%s" for %s\n' "$fresh" "$name";;
  esac
  printf '\n'
}

render_all(){
  local row
  wd_rows | while IFS= read -r row; do render_row "$row"; done
}

case "$MODE" in
  stdout)
    render_all
    ;;
  check)
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    "$0" --out "$tmp" >/dev/null
    drift=0
    if [ -d "$OUT_DIR" ]; then
      diff -r "$OUT_DIR" "$tmp" >/dev/null 2>&1 || drift=1
    else
      drift=1
    fi
    if [ "$drift" -eq 0 ]; then echo "generate-monit-config: monit.d is IN SYNC with the registry"; exit 0
    else echo "generate-monit-config: DRIFT — monit.d != registry render; run: fleet/watchdog/generate-monit-config.sh" >&2; exit 1; fi
    ;;
  write)
    mkdir -p "$OUT_DIR"
    # Clear stale generated files (registry is the SSOT; a removed row must remove its stanza).
    find "$OUT_DIR" -maxdepth 1 -name '*.conf' -delete 2>/dev/null || true
    n=0
    while IFS= read -r row; do
      name="$(wd_field "$row" 1)"; id="$(wd_sanitize "$name")"
      render_row "$row" > "$OUT_DIR/$id.conf"
      n=$((n+1))
    done < <(wd_rows)
    echo "generate-monit-config: rendered $n service stanza(s) into $OUT_DIR"
    ;;
esac
