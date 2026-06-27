#!/usr/bin/env bash
# Charon one-liner bootstrap installer.
#
# Gets a fresh machine from "nothing" to a working `charon` command: it checks
# prerequisites (Python >=3.11, git, pip/pipx), installs whatever is missing via
# the system package manager (apt / dnf / brew), then installs Charon itself with
# pipx (isolated) or a private venv fallback. Re-running it UPDATES an existing
# install in place and never touches your settings in ~/.charon.
#
# Usage (one-liner):
#   curl -fsSL https://github.com/SLOP-Platform/charon/releases/latest/download/install.sh | bash
#   wget -qO- https://github.com/SLOP-Platform/charon/releases/latest/download/install.sh | bash
#
# Or download -> inspect -> run (recommended for the cautious):
#   curl -fsSL .../install.sh -o install.sh && less install.sh && bash install.sh
#
# ⚠️  HONEST WARNING: Charon is a control plane. Its gateway holds your provider
#     keys server-side. The opt-in work-engine can spawn coding agents; its default
#     autonomy is L0 (propose-only) and it never auto-merges. Review the README first.
#
# Run `bash install.sh --help` for flags.
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (overridable from the environment)
# ---------------------------------------------------------------------------
REPO="${CHARON_REPO:-git+https://github.com/SLOP-Platform/charon}"  # source spec for pip/pipx
VENV_DIR="${CHARON_VENV:-$HOME/.charon-venv}"                       # venv-fallback location
CONFIG_DIR="${CHARON_HOME:-$HOME/.charon}"                          # user settings (PRESERVED)
ASSUME_YES=0       # --yes / -y : never prompt, assume "yes"
CLEAN_CONFIG=0     # --reinstall / --clean : also reset config (backs it up first)
TOTAL_STEPS=5

# ---------------------------------------------------------------------------
# Pretty output (pure bash, zero deps; auto-degrades on non-TTY / NO_COLOR)
# ---------------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'
  YLW=$'\033[33m'; BLU=$'\033[34m'; CYN=$'\033[36m'; RST=$'\033[0m'
else
  BOLD=''; DIM=''; RED=''; GRN=''; YLW=''; BLU=''; CYN=''; RST=''
fi
# UTF-8 glyphs only when colors are on AND the locale clearly supports them;
# otherwise fall back to ASCII so logs/CI/old terminals stay clean.
if [ -n "$BOLD" ]; then
  case "${LC_ALL:-}${LC_CTYPE:-}${LANG:-}" in
    *[Uu][Tt][Ff]*) MARK_OK="✓"; MARK_NO="✗" ;;
    *)              MARK_OK="OK"; MARK_NO="X" ;;
  esac
else
  MARK_OK="OK"; MARK_NO="X"
fi

hdr()  { printf '\n%s%s== %s ==%s\n' "$BOLD" "$CYN" "$*" "$RST"; }
step() { printf '%s[%s/%s]%s %s\n' "$BOLD$BLU" "$1" "$TOTAL_STEPS" "$RST" "$2"; }
ok()   { printf '  %s%s%s %s\n' "$GRN" "$MARK_OK" "$RST" "$*"; }
bad()  { printf '  %s%s%s %s\n' "$RED" "$MARK_NO" "$RST" "$*"; }
info() { printf '  %s-%s %s\n' "$DIM" "$RST" "$*"; }
warn() { printf '  %s! %s%s\n' "$YLW" "$*" "$RST"; }
die()  { printf '\n%serror:%s %s\n' "$RED$BOLD" "$RST" "$*" >&2; exit 1; }
kv()   { printf '  %s: %s%s%s\n' "$1" "$BOLD" "$2" "$RST"; }       # key: BOLD value

banner() {
  [ -n "$BOLD" ] || return 0   # plain text: skip the ASCII art
  printf '%s' "$CYN$BOLD"
  cat <<'ART'
   ___ _
  / __| |_  __ _ _ _ ___ _ _
 | (__| ' \/ _` | '_/ _ \ ' \
  \___|_||_\__,_|_| \___/_||_|
ART
  printf '%s' "$RST"
}

# Simple pure-bash spinner: spin <pid> <message>. Falls back to a static line
# when not attached to a TTY (so logs/CI stay clean).
spin() {
  # shellcheck disable=SC1003  # the trailing backslash is a literal spinner glyph, not an escape
  local pid="$1" msg="$2" frames='|/-\' i=0 rc
  if [ -z "$BOLD" ]; then
    printf '  %s ... ' "$msg"; wait "$pid"; rc=$?; printf 'done\n'; return "$rc"
  fi
  while kill -0 "$pid" 2>/dev/null; do
    printf '\r  %s%s%s %s' "$CYN" "${frames:i++%${#frames}:1}" "$RST" "$msg"
    sleep 0.1
  done
  wait "$pid"; rc=$?
  printf '\r  %s%s%s %s\n' "$GRN" "$MARK_OK" "$RST" "$msg"
  return "$rc"
}

# Prompt that works under `curl | bash` (reads the user's terminal, not stdin).
ask() {  # ask "question" -> returns 0 for yes
  local q="$1" reply
  [ "$ASSUME_YES" = 1 ] && return 0
  if [ -r /dev/tty ]; then
    printf '  %s? %s [y/N] %s' "$YLW" "$q" "$RST" > /dev/tty
    read -r reply < /dev/tty || reply=""
    case "$reply" in [Yy]*) return 0 ;; *) return 1 ;; esac
  fi
  # No terminal (piped, no /dev/tty): cannot ask — be safe and decline.
  warn "no terminal to confirm '$q' — re-run with --yes to allow, or run the steps manually."
  return 1
}

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
usage() {
  cat <<EOF
${BOLD}Charon installer${RST} — bootstrap, then re-run to update.

${BOLD}Usage:${RST}
  bash install.sh [options]
  curl -fsSL <release-url>/install.sh | bash

${BOLD}Options:${RST}
  -y, --yes          Assume "yes"; never prompt (for non-interactive use).
      --reinstall    Fresh-config reinstall: reset ${CONFIG_DIR} (backed up first).
      --clean        Alias for --reinstall.
  -h, --help         Show this help and exit.

${BOLD}Environment:${RST}
  CHARON_REPO        Source spec to install (default: ${REPO}).
  CHARON_VENV        Venv-fallback dir (default: \$HOME/.charon-venv).
  CHARON_HOME        Config dir to preserve (default: \$HOME/.charon).
  NO_COLOR=1         Disable colors/glyphs (also auto-off when piped).

Re-running this installer UPDATES Charon in place and PRESERVES your settings in
${CONFIG_DIR}. Use --reinstall only if you also want a clean config.
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)           usage; exit 0 ;;
    -y|--yes)            ASSUME_YES=1 ;;
    --reinstall|--clean) CLEAN_CONFIG=1 ;;
    *) die "unknown option: $1  (try --help)" ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# OS / package-manager detection
# ---------------------------------------------------------------------------
OS="$(uname -s)"
PKG=""          # apt | dnf | brew | ""(unknown)
detect_pkg() {
  if command -v brew >/dev/null 2>&1;      then PKG="brew"
  elif command -v apt-get >/dev/null 2>&1; then PKG="apt"
  elif command -v dnf >/dev/null 2>&1;     then PKG="dnf"
  elif command -v yum >/dev/null 2>&1;     then PKG="dnf"   # yum shares dnf's package names here
  else PKG=""
  fi
}

# sudo wrapper: only the package-manager step ever escalates, and only with consent.
SUDO=""
need_sudo() {
  if [ "$(id -u)" = 0 ]; then SUDO=""; return 0; fi
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; return 0; fi
  return 1
}

# Print the exact manual commands for the current package manager.
manual_prereqs() {
  warn "Could not install prerequisites automatically. Run these yourself, then re-run this script:"
  case "$PKG" in
    apt)  echo "      sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv pipx git" ;;
    dnf)  echo "      sudo dnf install -y python3.11 python3-pip git && python3.11 -m pip install --user pipx" ;;
    brew) echo "      brew install python@3.11 pipx git" ;;
    *)    echo "      Install: Python >= 3.11, git, and pipx (or pip) using your OS package manager." ;;
  esac
  echo "      (Ubuntu 22.04 ships Python 3.10; python3.11 may need: sudo add-apt-repository ppa:deadsnakes/ppa)"
}

# Run a package-manager install with consent + sudo. Returns non-zero on failure.
pkg_install() {  # pkg_install <human-summary> <cmd...>
  local summary="$1"; shift
  if [ "$(id -u)" != 0 ] && ! need_sudo; then
    warn "need root to install ${summary}, but 'sudo' is not available."
    return 1
  fi
  info "About to run: ${SUDO:+$SUDO }$*"
  if ! ask "Install ${summary} via ${PKG}?"; then
    warn "Skipped installing ${summary}."
    return 1
  fi
  if [ -n "$SUDO" ]; then "$SUDO" "$@"; else "$@"; fi
}

# ---------------------------------------------------------------------------
# Prerequisite resolution
# ---------------------------------------------------------------------------
PY=""   # path to a Python >= 3.11 interpreter, once found

py_ok() { "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; }

find_python() {
  local c
  for c in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && py_ok "$c"; then PY="$(command -v "$c")"; return 0; fi
  done
  return 1
}

ensure_python() {
  if find_python; then
    ok "Python $("$PY" -c 'import platform;print(platform.python_version())') ($PY)"
    return 0
  fi
  bad "Python >= 3.11 not found — Charon requires it (requires-python >=3.11)."
  case "$PKG" in
    apt)  pkg_install "Python 3.11" sh -c "apt-get update && apt-get install -y python3.11 python3.11-venv" || true ;;
    dnf)  pkg_install "Python 3.11" dnf install -y python3.11 python3-pip || true ;;
    brew) pkg_install "Python 3.11" brew install python@3.11 || true ;;
  esac
  find_python || { manual_prereqs; die "no usable Python 3.11+. Install it and re-run."; }
  ok "Python $("$PY" -c 'import platform;print(platform.python_version())') ($PY)"
}

ensure_git() {
  if command -v git >/dev/null 2>&1; then ok "git ($(command -v git))"; return 0; fi
  bad "git not found (needed to fetch Charon from its repo)."
  case "$PKG" in
    apt)  pkg_install "git" sh -c "apt-get update && apt-get install -y git" || true ;;
    dnf)  pkg_install "git" dnf install -y git || true ;;
    brew) pkg_install "git" brew install git || true ;;
  esac
  command -v git >/dev/null 2>&1 || { manual_prereqs; die "git is required."; }
  ok "git ($(command -v git))"
}

# Ensure pip exists for the chosen Python (the classic 'No module named pip' fix).
ensure_pip() {
  if "$PY" -m pip --version >/dev/null 2>&1; then return 0; fi
  info "pip missing for $PY — bootstrapping via ensurepip…"
  if "$PY" -m ensurepip --upgrade >/dev/null 2>&1; then return 0; fi
  case "$PKG" in
    apt)  pkg_install "python3-pip" sh -c "apt-get update && apt-get install -y python3-pip" || true ;;
    dnf)  pkg_install "python3-pip" dnf install -y python3-pip || true ;;
  esac
  "$PY" -m pip --version >/dev/null 2>&1
}

PIPX=""   # set to a working pipx invocation if available
ensure_pipx() {
  if command -v pipx >/dev/null 2>&1; then PIPX="pipx"; ok "pipx ($(command -v pipx))"; return 0; fi
  if "$PY" -m pipx --version >/dev/null 2>&1; then PIPX="$PY -m pipx"; ok "pipx (python -m pipx)"; return 0; fi
  info "pipx not found — trying to install it (preferred: isolated app installs)."
  # Prefer the OS package where it exists; otherwise pip --user.
  case "$PKG" in
    apt)  pkg_install "pipx" sh -c "apt-get update && apt-get install -y pipx" || true ;;
    brew) pkg_install "pipx" brew install pipx || true ;;
  esac
  if command -v pipx >/dev/null 2>&1; then PIPX="pipx"
  elif ensure_pip && "$PY" -m pip install --user pipx >/dev/null 2>&1; then
    "$PY" -m pipx ensurepath >/dev/null 2>&1 || true
    PIPX="$PY -m pipx"
  fi
  if [ -n "$PIPX" ]; then ok "pipx ready"; return 0; fi
  warn "pipx unavailable — will fall back to a private venv at $VENV_DIR."
  return 1
}

# ---------------------------------------------------------------------------
# Config handling (PRESERVE by default; reset only on --reinstall/--clean)
# ---------------------------------------------------------------------------
handle_config() {
  if [ "$CLEAN_CONFIG" = 1 ] && [ -d "$CONFIG_DIR" ]; then
    local backup
    backup="${CONFIG_DIR}.bak.$(date +%Y%m%d%H%M%S)"
    warn "--reinstall: resetting config. Backing up $CONFIG_DIR -> $backup"
    mv "$CONFIG_DIR" "$backup"
    ok "config reset (old settings saved at $backup)"
  elif [ -d "$CONFIG_DIR" ]; then
    ok "existing config preserved: $CONFIG_DIR"
  else
    info "no existing config at $CONFIG_DIR (a fresh install)"
  fi
}

# ---------------------------------------------------------------------------
# Install / update Charon
# ---------------------------------------------------------------------------
already_installed() {
  command -v charon >/dev/null 2>&1 && return 0
  [ -x "$VENV_DIR/bin/charon" ] && return 0
  return 1
}

install_charon() {
  local verb="Installing" log="${TMPDIR:-/tmp}/charon-install.$$.log"
  already_installed && verb="Updating"

  if [ -n "$PIPX" ]; then
    info "${verb} Charon with pipx (isolated) from ${REPO}"
    # --force makes this idempotent: a re-run pulls and reinstalls the latest.
    # shellcheck disable=SC2086  # $PIPX may be 'python -m pipx' (two words) — intentional split
    ($PIPX install --force --python "$PY" "$REPO" >"$log" 2>&1) &
    spin "$!" "${verb} Charon (pipx)" \
      || { warn "pipx install failed; log:"; sed 's/^/      /' "$log" >&2; rm -f "$log"; die "install failed"; }
    rm -f "$log"
  else
    # venv fallback: self-contained, no pipx required.
    ensure_pip || { manual_prereqs; die "need pip in $PY for the venv fallback."; }
    info "${verb} Charon into a private venv at ${VENV_DIR}"
    [ -d "$VENV_DIR" ] || "$PY" -m venv "$VENV_DIR"
    ("$VENV_DIR/bin/pip" install --upgrade pip >/dev/null 2>&1 && \
     "$VENV_DIR/bin/pip" install --upgrade "$REPO" >"$log" 2>&1) &
    spin "$!" "${verb} Charon (venv)" \
      || { warn "venv install failed; log:"; sed 's/^/      /' "$log" >&2; rm -f "$log"; die "install failed"; }
    rm -f "$log"
    # Best-effort: expose `charon` on PATH via ~/.local/bin.
    if [ -d "$HOME/.local/bin" ] || mkdir -p "$HOME/.local/bin" 2>/dev/null; then
      ln -sf "$VENV_DIR/bin/charon" "$HOME/.local/bin/charon" 2>/dev/null || true
    fi
  fi
}

resolve_charon() {  # echo a usable `charon` command for the next-steps text
  if command -v charon >/dev/null 2>&1; then echo "charon"
  elif [ -x "$VENV_DIR/bin/charon" ]; then echo "$VENV_DIR/bin/charon"
  else echo "charon"; fi
}

# ---------------------------------------------------------------------------
# Next steps
# ---------------------------------------------------------------------------
next_steps() {
  local cmd; cmd="$(resolve_charon)"
  hdr "Charon is installed"
  if ! command -v charon >/dev/null 2>&1 && [ -x "$VENV_DIR/bin/charon" ]; then
    warn "If 'charon' isn't found, add it to PATH:  export PATH=\"\$HOME/.local/bin:\$PATH\""
    warn "or call it directly: $cmd"
  fi

  printf '\n%s1) Configure providers & a failover pool%s\n' "$BOLD" "$RST"
  info "$cmd setup            # add providers + keys, models, a pool (or the web form below)"

  printf '\n%s2) Start the gateway%s\n' "$BOLD" "$RST"
  info "$cmd gateway          # serves the OpenAI-compatible API on 127.0.0.1:8080"
  info "Health check:  curl -s http://127.0.0.1:8080/v1/models"
  info "For LAN access:  $cmd gateway --host 0.0.0.0 --token <TOKEN>   (token REQUIRED off-loopback)"

  printf '\n%s3) Point any OpenAI-compatible app at Charon%s\n' "$BOLD" "$RST"
  kv "Base URL"    "http://127.0.0.1:8080/v1   (use http://<host>:8080/v1 over LAN)"
  kv "API key"     "the gateway token if set, else any non-empty value"
  kv "Web console" "http://127.0.0.1:8080/   (setup form at /charon/setup)"

  printf '\n%sNotes%s\n' "$BOLD" "$RST"
  info "Program vs settings:  re-run this installer to UPDATE the program; '$cmd setup'/'reset' only touch your SETTINGS in $CONFIG_DIR."
  info "Update later:  re-run the one-liner, or  pipx reinstall charon"
  info "Help & docs:  https://github.com/SLOP-Platform/charon#readme"
  printf '\n'
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  banner
  printf '%sCharon installer%s  source: %s%s%s\n' "$BOLD" "$RST" "$DIM" "$REPO" "$RST"
  info "OS: $OS | re-run me to update | --help for options"

  hdr "Step 1 — Detect environment"
  step 1 "Detecting OS and package manager"
  detect_pkg
  if [ -n "$PKG" ]; then ok "package manager: $PKG"; else warn "no known package manager (apt/dnf/brew); prereqs must be installed manually."; fi

  hdr "Step 2 — Check & install prerequisites"
  step 2 "Checking prerequisites (Python >=3.11, git, pipx)"
  ensure_git
  ensure_python
  ensure_pipx || true   # falls back to venv inside install_charon

  hdr "Step 3 — Preserve configuration"
  step 3 "Handling user config"
  handle_config

  hdr "Step 4 — Install / update Charon"
  step 4 "Installing Charon"
  install_charon
  ok "Charon installed/updated"

  hdr "Step 5 — Verify"
  step 5 "Verifying the install"
  local cmd; cmd="$(resolve_charon)"
  if "$cmd" --version >/dev/null 2>&1 || "$cmd" --help >/dev/null 2>&1; then
    ok "charon command responds"
  else
    warn "couldn't run '$cmd' yet — you may need a new shell or PATH update (see below)."
  fi

  next_steps
}

main "$@"
