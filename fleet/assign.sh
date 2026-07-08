#!/usr/bin/env bash
# Thin entrypoint: ticket -> best-agent recommendation. See capability/assign.py
# for the actual logic; this wrapper exists only so the manager/operator has
# the one-command form the rest of fleet/*.sh follows.
#   assign.sh <TICKET-ID> [--work-class WC] [--tier T] [--claim SESSION_ID]
#   assign.sh --work-class WC [--tier T]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/capability/assign.py" "$@"
