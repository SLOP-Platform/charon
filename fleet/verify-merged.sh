#!/usr/bin/env bash
# verify-merged.sh <id> — exit 0 iff <id> is genuinely LANDED in the product origin/master.
# Thin CLI over _lib.sh:verify_merged so reds.tsv check_cmds and every gate share ONE test
# (no three drifting copies). Offline-tolerant; honours VERIFY_MERGED_FIXTURE / VERIFY_MERGED_REPO.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$FLEET/_lib.sh"
verify_merged "${1:?usage: verify-merged.sh <id>}"
