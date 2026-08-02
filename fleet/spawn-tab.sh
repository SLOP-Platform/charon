#!/usr/bin/env bash
# fleet/spawn-tab.sh — open a NAMED, COLOURED Windows Terminal TAB running an arbitrary command.
# Reuses the verified wt.exe invocation from fleet/spawn-worker.sh minus TUI-specific parts
# (no port, no TUI readiness gate, no prompt injection — a reviewer tab has no TUI).
#
# Every choice below is VERIFIED (spawn-worker.sh; RESEARCH-SESSION-SPAWN-2026-07-27.md):
#   * `-w 1` targets the operator's window; `-w 0` follows GUI focus and $WT_SESSION is a PANE guid.
#   * --suppressApplicationTitle stops the child retitling the tab.
#   * Quoted `;` stops wt eating it as a shell separator.
#   * Chained focus-tab stops the spawn eating operator keystrokes.
#
# Env inherited into the tab:
#   CHARON_TAB_ENV   — space-separated VAR=VALUE pairs to export into the tab's shell.
#
# Usage: spawn-tab.sh <TAB-NAME> <COLOR> <CMD> [ARG ...]
set -uo pipefail

NAME="${1:?usage: spawn-tab.sh TAB-NAME COLOR CMD [ARG ...]}"
COLOR="${2:?COLOR is required}"
shift 2

# Resolve wt.exe (same logic as spawn-worker.sh:166-167)
WT=/mnt/c/Users/$(/mnt/c/Windows/System32/cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')/AppData/Local/Microsoft/WindowsApps/wt.exe
[ -x "$WT" ] || WT=$(command -v wt.exe 2>/dev/null) || { echo "spawn-tab: wt.exe not found" >&2; exit 2; }

# Build the tab shell script. This runs in a NON-LOGIN bash, so ~/.local/bin is absent.
# Append (never prepend) so any already-resolvable binary keeps winning.
RUN_SCRIPT=$(mktemp /tmp/spawn-tab-XXXXXX.sh)
{
  echo '#!/usr/bin/env bash'
  echo "case ':'\"\${PATH}\"':' in"
  echo "  *':'\${HOME}'/.local/bin:'*) : ;;"
  echo "  *) [ -d '\${HOME}/.local/bin' ] && export PATH=\"\${PATH}:\${HOME}/.local/bin\" ;;"
  echo "esac"
  # Re-derive gateway token if env-registry.sh is present (same as fleet-droid.sh)
  echo "FLEET=\"\$(cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" && pwd)\" 2>/dev/null || true"
  echo "if [ -n \"\${CHARON_TAB_ENV:-}\" ]; then"
  echo "  for _pair in \$CHARON_TAB_ENV; do"
  echo "    _var=\"\${_pair%%=*}\" _val=\"\${_pair#*=}\""
  echo "    export \"\$_var=\$_val\""
  echo "  done"
  echo "fi"
  # Run the command with remaining args
  printf 'exec %q "$@"\n' "$1"
} > "$RUN_SCRIPT"
chmod +x "$RUN_SCRIPT"

echo "spawn-tab: name='$NAME' color=$COLOR cmd=$*"

"$WT" -w 1 new-tab --title "$NAME" --tabColor "$COLOR" --suppressApplicationTitle \
      wsl.exe -d Ubuntu-24.04 -- bash "$RUN_SCRIPT" "$@" \
      ';' focus-tab -t "${CHARON_WT_HOME_TAB:-0}"

rm -f "$RUN_SCRIPT"
