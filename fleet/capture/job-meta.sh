# shellcheck disable=SC2034
# fleet/capture/job-meta.sh — brief .meta.json convention + loader (Chunk B).
#
# Convention: a brief file <brief>.meta.json carries the structured job metadata
# that the capture pipeline needs but that charon-run.sh does not currently emit.
# Format:
#   {"work_class": "routing", "ref": "BRIDGE-PUSH", "difficulty": "2"}
#
# This file is sourced (NOT executed). After sourcing, the following variables
# are available:
#   JM_WORK_CLASS  JM_REF  JM_DIFFICULTY
#
# Load order:
#   1. <brief>.meta.json (if the file exists and is readable)
#   2. Env fallbacks: CHARON_JOB_WORK_CLASS, CHARON_JOB_REF, CHARON_JOB_DIFFICULTY
#   3. If nothing resolved, variables remain empty — caller should validate.

JM_WORK_CLASS=""
JM_REF=""
JM_DIFFICULTY=""

_load_brief_meta() {
  local meta_file="${1:-}"
  local json_work_class json_ref json_difficulty

  if [ -n "$meta_file" ] && [ -f "$meta_file" ] && [ -r "$meta_file" ]; then
    # minimal JSON extraction — no jq dependency; pure POSIX
    json_work_class=$(sed -n 's/.*"work_class"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$meta_file" | head -1)
    json_ref=$(sed -n 's/.*"ref"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$meta_file" | head -1)
    json_difficulty=$(sed -n 's/.*"difficulty"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$meta_file" | head -1)
    [ -n "$json_work_class" ] && JM_WORK_CLASS="$json_work_class"
    [ -n "$json_ref" ]        && JM_REF="$json_ref"
    [ -n "$json_difficulty" ] && JM_DIFFICULTY="$json_difficulty"
  fi

  [ -z "$JM_WORK_CLASS" ] && JM_WORK_CLASS="${CHARON_JOB_WORK_CLASS:-}"
  [ -z "$JM_REF" ]        && JM_REF="${CHARON_JOB_REF:-}"
  [ -z "$JM_DIFFICULTY" ] && JM_DIFFICULTY="${CHARON_JOB_DIFFICULTY:-}"
}

# Example usage from enqueue-capture.sh:
#   source "${SCRIPT_DIR}/job-meta.sh"
#   _load_brief_meta "${BRIEF_META:-}"  # optional path to <brief>.meta.json
#   # Now JM_WORK_CLASS, JM_REF, JM_DIFFICULTY are available
#   # Validate: [ -z "$JM_WORK_CLASS" ] && echo "missing work_class" >&2 && exit 1
