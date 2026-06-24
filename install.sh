#!/usr/bin/env bash
# Charon local installer (Mode A — standalone).
#
# ⚠️  HONEST WARNING: Charon is a control plane. At autonomy >= L1 it spawns CLI
#     coding agents and can apply their diffs UNATTENDED. The default is L0
#     (propose-only). Do NOT run unattended on a shared machine; for unattended
#     operation use the Mode B container (docker compose up) instead.
set -euo pipefail

REPO="${CHARON_REPO:-git+https://github.com/SLOP-Platform/charon}"

echo "charon installer"
echo "  source: ${REPO}"
echo
echo "  NOTE: this installs a tool that can spawn coding agents and apply diffs."
echo "        Default autonomy is L0 (propose-only). Review the README first."
echo

if command -v pipx >/dev/null 2>&1; then
  echo "==> installing with pipx (isolated)"
  pipx install "${REPO}"
elif command -v pip3 >/dev/null 2>&1; then
  echo "==> pipx not found; installing pipx, then charon"
  pip3 install --user pipx
  python3 -m pipx ensurepath
  python3 -m pipx install "${REPO}"
else
  echo "error: need pipx or pip3 on PATH" >&2
  exit 1
fi

echo
echo "done. Try:  charon run --goal 'create hello' --accept 'test -f hello.txt' --backend mock --autonomy L1"
