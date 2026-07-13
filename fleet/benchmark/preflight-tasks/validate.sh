#!/usr/bin/env bash
# validate.sh — self-check for the preflight task-fixture registry (Chunk A).
# Asserts: manifest lists >=12 tasks; every non-"*" grader_key maps to a real
# fixture dir with a PROMPT.md; every fixture dir is registered; trap markers
# reference real fixtures. Exit 0 = OK. Run from anywhere.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"
fail=0
err() { echo "FAIL: $*" >&2; fail=1; }

[ -f manifest.tsv ] || { echo "FAIL: manifest.tsv missing" >&2; exit 1; }

# Collect data rows (skip comments + header).
rows=$(awk -F'\t' '!/^#/ && $1!="task_id" && NF>=4 {print}' manifest.tsv)
task_count=$(echo "$rows" | grep -c '^T' || true)
[ "$task_count" -ge 12 ] || err "manifest has $task_count task rows, need >=12"

# Every non-"*" grader_key must be a real fixture dir with a PROMPT.md.
declare -A registered
while IFS=$'\t' read -r task mode key artifact; do
  [ -z "${key:-}" ] && continue
  if [ "$key" = "*" ]; then continue; fi
  registered["$key"]=1
  [ -d "$key" ] || err "grader_key '$key' ($task): no such fixture dir"
  [ -f "$key/PROMPT.md" ] || err "fixture '$key' missing PROMPT.md"
done <<< "$rows"

# Every fixture dir on disk must be registered in the manifest.
for d in */; do
  d=${d%/}
  [ -d "$d" ] || continue
  [ -n "${registered[$d]:-}" ] || err "fixture dir '$d' is not in manifest.tsv"
done

# Trap markers must reference real fixtures.
if [ -f traps.tsv ]; then
  while IFS=$'\t' read -r key ttype marker; do
    [ -d "$key" ] || err "traps.tsv references missing fixture '$key'"
  done < <(awk -F'\t' '!/^#/ && $1!="grader_key" && NF>=3 {print}' traps.tsv)
fi

if [ "$fail" -eq 0 ]; then
  echo "OK: $task_count tasks registered, all fixture dirs present and cross-checked"
fi
exit "$fail"
