#!/usr/bin/env bash
# deploy-preflight-graders.sh — install the LOAD-BEARING MODEL-PREFLIGHT graders
# into $KEYS/preflight/ (mode 0700, bench-grader-owned).
#
# WHY THIS EXISTS (design §1.4): preflight graders gate tier entry, so their
# hidden assertions/expected values/baselines MUST be out of the model's reach —
# exactly like the reds-replay keys. The git-tracked graders/preflight_checks/
# tree is the DEPLOY SOURCE ONLY. This script copies each grader, the shared
# _pf_common.py, and each task's PRISTINE-fixture baseline into $KEYS/preflight/.
#
# RUN AS bench-grader (NOT stack):
#     sudo -u bench-grader KEYS=/home/bench-grader/keys \
#          fleet/benchmark/deploy-preflight-graders.sh
#
# It REFUSES to run as any other user (a stack-owned $KEYS would defeat isolation).
# Idempotent: re-running re-installs from source.
set -euo pipefail

KEYS="${KEYS:-/home/bench-grader/keys}"
DEST="$KEYS/preflight"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$here/graders/preflight_checks"
TASKS="$here/preflight-tasks"
MANIFEST="$TASKS/manifest.tsv"

me="$(id -un)"
if [ "$me" != "bench-grader" ]; then
  echo "REFUSING: must run as bench-grader (am '$me'). Load-bearing keys must be" >&2
  echo "  owned by bench-grader mode 0700, or model isolation is defeated." >&2
  echo "  Run: sudo -u bench-grader KEYS=$KEYS $0" >&2
  exit 2
fi

[ -d "$SRC" ]      || { echo "FAIL: source dir missing: $SRC" >&2; exit 1; }
[ -f "$MANIFEST" ] || { echo "FAIL: manifest missing: $MANIFEST" >&2; exit 1; }

install -d -m 0700 "$KEYS"
install -d -m 0700 "$DEST"

# Shared library (imported by every grader).
install -m 0600 "$SRC/_pf_common.py" "$DEST/_pf_common.py"

deployed=0
# One grader + one pristine baseline per non-"*" grader_key in the manifest.
while IFS=$'\t' read -r task mode key artifact; do
  case "$task" in ''|'#'*|task_id) continue ;; esac
  [ -z "${key:-}" ] && continue
  [ "$key" = "*" ] && continue

  grader="$SRC/$key.py"
  fixture="$TASKS/$key"
  [ -f "$grader" ]   || { echo "FAIL: no grader for '$key' ($task): $grader" >&2; exit 1; }
  [ -d "$fixture" ]  || { echo "FAIL: no fixture for '$key' ($task): $fixture" >&2; exit 1; }

  # the grader (executable, 0700)
  install -m 0700 "$grader" "$DEST/$key.py"

  # the pristine-fixture baseline the grader checksums/diffs/reverts against.
  # Exclude runner sidecars and caches; the baseline is the STARTING worktree.
  rm -rf "${DEST:?}/$key.baseline"
  install -d -m 0700 "$DEST/$key.baseline"
  ( cd "$fixture" && \
    tar --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc' \
        --exclude='MODEL_RESPONSE.md' -cf - . ) | ( cd "$DEST/$key.baseline" && tar -xf - )
  chmod -R go-rwx "$DEST/$key.baseline"

  deployed=$((deployed + 1))
  echo "  deployed: $key  ($task $mode)"
done < "$MANIFEST"

chmod -R go-rwx "$DEST"
echo "OK: deployed $deployed preflight graders + baselines + _pf_common.py to $DEST (0700, bench-grader)"
