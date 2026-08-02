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
# Where the tab mirrors its output and publishes its exit status. Callers that need to know
# whether the tab SURVIVED (see reviewer-tab.sh) set this; "$TAB_LOG.rc" appearing means dead.
TAB_LOG="${CHARON_TAB_LOG:-}"

# Resolve wt.exe (same logic as spawn-worker.sh:166-167)
WT=/mnt/c/Users/$(/mnt/c/Windows/System32/cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')/AppData/Local/Microsoft/WindowsApps/wt.exe
[ -x "$WT" ] || WT=$(command -v wt.exe 2>/dev/null) || { echo "spawn-tab: wt.exe not found" >&2; exit 2; }

# Build the tab shell script. This runs in a NON-LOGIN bash, so ~/.local/bin is absent.
# Append (never prepend) so any already-resolvable binary keeps winning.
RUN_SCRIPT=$(mktemp /tmp/spawn-tab-XXXXXX.sh)
{
  echo '#!/usr/bin/env bash'
  # PATH: BAKE the resolved directory in. The previous form tested `[ -d '${HOME}/.local/bin' ]`
  # with SINGLE quotes, so the path never expanded, the -d test was always false, and the append
  # silently no-opped. `gh` lives in ~/.local/bin, so every tab ran WITHOUT gh — review-pool.sh's
  # `gh pr list` failed, the queue truncated to 0 entries, and the pool exited "no claimable
  # review items" in ~2s. Baking removes the expansion hazard entirely.
  if [ -d "$HOME/.local/bin" ]; then
    printf 'case ":${PATH}:" in\n  *:%q:*) : ;;\n  *) export PATH="${PATH}:%q" ;;\nesac\n' \
      "$HOME/.local/bin" "$HOME/.local/bin"
  fi
  # Env: BAKE the pairs in at generation time. wt.exe -> wsl.exe does NOT carry the launcher's
  # environment into the tab (it is WSLENV-gated), so reading $CHARON_TAB_ENV inside the tab
  # always saw an empty value. That is why the pool ran as droid=unknown on default models.
  if [ -n "${CHARON_TAB_ENV:-}" ]; then
    for _pair in $CHARON_TAB_ENV; do
      printf 'export %s=%q\n' "${_pair%%=*}" "${_pair#*=}"
    done
  fi
  # Run the command. "$@" here is the FULL command vector (argv[0] included), so it must be
  # exec'd as-is. The previous form was `exec %q "$@"` with %q of $1 — that re-prepended the
  # command's own argv[0], producing `exec bash bash <script> ...`, which dies rc=126
  # ("cannot execute binary file") the instant the tab opens. Every reviewer tab died there.
  echo 'rc=0'
  printf 'TAB_LOG=%q\n' "$TAB_LOG"
  echo 'if [ -n "$TAB_LOG" ]; then exec > >(tee -a "$TAB_LOG") 2>&1; fi'
  echo '"$@" || rc=$?'
  # FAIL-LOUD: publish the exit status so the LAUNCHER can tell a live tab from a dead one,
  # and hold a failed tab open so the operator sees the error instead of a tab that blinks shut.
  echo '[ -n "$TAB_LOG" ] && printf "%s\n" "$rc" > "$TAB_LOG.rc"'
  echo 'if [ "$rc" -ne 0 ]; then'
  echo '  echo "[spawn-tab] FATAL: command exited rc=$rc — holding tab open 120s so you can read the error above" >&2'
  echo '  sleep 120'
  echo 'fi'
  echo 'exit "$rc"'
} > "$RUN_SCRIPT"
chmod +x "$RUN_SCRIPT"

echo "spawn-tab: name='$NAME' color=$COLOR cmd=$*"
[ -n "$TAB_LOG" ] && echo "spawn-tab: tab log=$TAB_LOG (exit status published to $TAB_LOG.rc)"

"$WT" -w 1 new-tab --title "$NAME" --tabColor "$COLOR" --suppressApplicationTitle \
      wsl.exe -d Ubuntu-24.04 -- bash "$RUN_SCRIPT" "$@" \
      ';' focus-tab -t "${CHARON_WT_HOME_TAB:-0}"

# wt.exe RETURNS IMMEDIATELY — it only hands the command to the WT window. Deleting RUN_SCRIPT
# here raced the tab's `bash RUN_SCRIPT`, so tabs also died with "No such file or directory".
# Clean up out-of-band, well after the tab has read the file.
( sleep 60; rm -f "$RUN_SCRIPT" ) >/dev/null 2>&1 &
disown 2>/dev/null || true
