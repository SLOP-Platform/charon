#!/usr/bin/env bash
# deploy-drift.sh — RED when the LIVE gateway on the deploy host is not running what the
# product source says it should run.
#
# THE DRIFT CLASS THIS CLOSES (DEPLOY-MECHANIZE): DEPLOYED IMAGE != SOURCE. The deploy host has
# NO charon git checkout — it pulls immutable ghcr.io/slop-platform/charon:vX.Y.Z images, so no
# ordinary git-based staleness check can ever see it. It has now bitten twice:
#   * 2026-08-04: the gateway ran v0.6.1 while master was 14 commits ahead — including D-012,
#     the fix that stops a fully-parked pool from serving a silent, billed 200. The money leak
#     stayed live in production for the whole time the fix sat merged on master. Nobody was told.
#   * Same day, worse: /home/stack/charon/docker-compose.yml on the host pinned v0.3.3 while the
#     RUNNING container was v0.6.1 — a routine `docker compose up` would have silently rolled
#     production back three minor versions.
#
# WHAT THIS CHECK DOES — compares THREE things, not two (the ticket's rule):
#   RUNNING  the image the gateway container is ACTUALLY running (docker inspect over ssh)
#   PINNED   the image pinned in the host's docker-compose.yml (would replace RUNNING on the
#            next `docker compose up` — the rollback hazard)
#   LATEST   the newest published v* release in the product repo
# plus:      the commits on origin/master that are NOT in the deployed version, NAMED — so
#            "D-012 is not deployed" is legible without reading git.
#
# VERDICT:
#   GREEN (0) only when RUNNING == PINNED == LATEST AND the commits ahead of the deployed
#            version are within MAX_AHEAD.
#   RED   (1) when any of those disagree, or master runs away from the deployed version:
#            - RUNNING != LATEST      a published release is not what production runs
#            - PINNED  != RUNNING     compose would change the running image on the next `up`
#            - AHEAD   >  MAX_AHEAD   master is past the deployed version by more than N commits
#            Each RED names its evidence (versions compared, commits missing).
#   UNKNOWN (2) when a required input could not be read (host unreachable, no container / no
#            compose / no product repo / deployed tag not a known ref). NEVER a false green on a
#            source we could not read.
#
# Usage:
#   fleet/checks/deploy-drift.sh                 # print report; exit 0/1/2
#   fleet/checks/deploy-drift.sh --quiet         # only the verdict line + exit code
#
# HERMETIC TEST HOOKS (every external read is env-overridable — see fleet/tests/deploy-drift.test.sh):
#   CHARON_DEPLOY_HOST        ssh target (default stack@10.0.1.60)
#   CHARON_DEPLOY_SSH_KEY     ssh key path (default $HOME/.ssh/4lom)
#   CHARON_DEPLOY_CONTAINER   gateway container name (default charon-gateway-1)
#   CHARON_DEPLOY_COMPOSE     compose path ON the host (default /home/stack/charon/docker-compose.yml)
#   CHARON_PRODUCT_REPO       product repo checkout (default /home/stack/code/charon)
#   CHARON_PRODUCT_MASTER     ref to diff against (default origin/master)
#   DEPLOY_DRIFT_MAX_AHEAD    max commits master may be ahead of the deployed version (default 5)
#   DEPLOY_DRIFT_RUNNING_CMD  override the running-image lookup (tests inject a fixture image)
#   DEPLOY_DRIFT_PINNED_CMD   override the compose-pin lookup (tests inject a fixture compose line)
#   DEPLOY_DRIFT_FETCH        set to 0 to skip `git fetch` in the product repo (tests are hermetic
#                             and point CHARON_PRODUCT_REPO at a local fixture repo anyway)
set -uo pipefail

HOST="${CHARON_DEPLOY_HOST:-stack@10.0.1.60}"
SSH_KEY="${CHARON_DEPLOY_SSH_KEY:-${HOME}/.ssh/4lom}"
CONTAINER="${CHARON_DEPLOY_CONTAINER:-charon-gateway-1}"
COMPOSE="${CHARON_DEPLOY_COMPOSE:-/home/stack/charon/docker-compose.yml}"
PRODUCT_REPO="${CHARON_PRODUCT_REPO:-/home/stack/code/charon}"
MASTER_REF="${CHARON_PRODUCT_MASTER:-origin/master}"
MAX_AHEAD="${DEPLOY_DRIFT_MAX_AHEAD:-5}"
LOOKUP_TIMEOUT="${DEPLOY_DRIFT_LOOKUP_TIMEOUT:-15}"
IMAGE_REPO="${CHARON_DEPLOY_IMAGE:-ghcr.io/slop-platform/charon}"
QUIET=0

usage(){ echo "usage: deploy-drift.sh [--quiet]" >&2; exit 3; }
case "${1:-}" in
  --quiet) QUIET=1 ;;
  "" ) ;;
  * ) usage ;;
esac

# ---- external reads (all overridable; all bounded so a dead host can never hang the cron) ----
# Default lookups run over ssh. The single quotes around each value survive to the remote shell
# (the ssh target / compose path must not be re-expanded there); the values themselves are
# injected at assignment time, on this side.
_ssh_prefix(){ printf 'ssh -o BatchMode=yes -o ConnectTimeout=5 -i %q %q ' "${SSH_KEY}" "${HOST}"; }

if [[ -z "${DEPLOY_DRIFT_RUNNING_CMD:-}" ]]; then
  run_cmd="$(_ssh_prefix) docker inspect '${CONTAINER}' --format '{{.Config.Image}}'"
else
  run_cmd="${DEPLOY_DRIFT_RUNNING_CMD}"
fi
# The pinned image in the host's compose file. We grep ALL image: lines and take the charon one;
# a compose that declares several charon services (gateway + charon-service) must not fool us.
if [[ -z "${DEPLOY_DRIFT_PINNED_CMD:-}" ]]; then
  pin_cmd="$(_ssh_prefix) grep -E '^[[:space:]]*image:' '${COMPOSE}' | head -5"
else
  pin_cmd="${DEPLOY_DRIFT_PINNED_CMD}"
fi

# _lookup <name> <cmd>: run a bounded lookup, echoing output on stdout, nothing on failure.
_lookup(){
  local name="$1" cmd="$2" out
  out="$(timeout "${LOOKUP_TIMEOUT}" bash -c "${cmd}" 2>/dev/null)" || { echo "deploy-drift: ${name} lookup FAILED — cannot determine state (never a false green)" >&2; return 1; }
  if [[ -z "${out}" ]]; then
    echo "deploy-drift: ${name} lookup returned EMPTY — cannot determine state (never a false green)" >&2
    return 1
  fi
  printf '%s\n' "${out}"
}

# _tag_of <image-ref>: extract a vX.Y.Z-style tag, or return "" when the ref has no usable tag
# (digest pin, 'latest', empty). A digest pin (@sha256:...) has a tag-looking suffix but must be
# treated as NOT-A-TAG: we cannot compare digests, so an empty tag means UNKNOWN, never equal.
_tag_of(){
  local ref="$1"
  case "${ref}" in
    *@*) return 1 ;;   # digest-pinned
    *:*) ;;
    *) return 1 ;;
  esac
  printf '%s' "${ref##*:}"
}

_vercmp(){ # _vercmp a b -> -1|0|1|99 (99 = not both vX.Y.Z). Uses sort -V.
  local a="$1" b="$2" sorted
  case "${a}|${b}" in
    v[0-9]*.[0-9]*.[0-9]*\|v[0-9]*.[0-9]*.[0-9]*) ;;
    *) printf '99'; return ;;
  esac
  if [[ "${a}" = "${b}" ]]; then printf '0'; return; fi
  sorted="$(printf '%s\n%s\n' "${a}" "${b}" | sort -V | head -1)"
  if [[ "${sorted}" = "${a}" ]]; then printf -- '-1'; else printf '1'; fi
}

# report prints the load-bearing DEPLOY-DRIFT: and VERDICT: lines ALWAYS (even --quiet), so a
# machine consumer can read the three numbers + verdict from a single line. log prints the
# human detail lines only when not quiet.
report(){ echo "$*"; }
log(){ if [[ "${QUIET}" != 1 ]]; then echo "  $*"; fi; }

# ===========================================================================================
# 1. RUNNING — what the container actually runs
# ===========================================================================================
running_image="$(_lookup running "${run_cmd}")" || exit 2
running_tag="$(_tag_of "${running_image}")" || { report "deploy-drift: RUNNING image has no comparable tag (${running_image}) — UNKNOWN, cannot prove alignment"; exit 2; }

# ===========================================================================================
# 2. PINNED — what compose would put in charge on the next `up`
# ===========================================================================================
pinned_image="$(_lookup pinned "${pin_cmd}")" || exit 2
# keep only charon-image refs; a host compose with unrelated images must not confuse us
pinned_refs="$(printf '%s\n' "${pinned_image}" | grep -E "image:[[:space:]]*['\"]?${IMAGE_REPO}" || true)"
pinned_ref="$(printf '%s\n' "${pinned_refs}" | head -1 | sed -E "s/^[[:space:]]*image:[[:space:]]*['\"]?([^'\"[:space:]]+).*/\1/")"
if [[ -z "${pinned_ref}" ]]; then
  report "deploy-drift: no charon image pin found in host compose (${IMAGE_REPO}) — UNKNOWN, cannot prove compose safety"
  exit 2
fi
pinned_tag="$(_tag_of "${pinned_ref}")"

# ===========================================================================================
# 3. LATEST — newest published v* release in the product repo
# ===========================================================================================
if [[ ! -d "${PRODUCT_REPO}/.git" ]]; then
  report "deploy-drift: product repo missing: ${PRODUCT_REPO} — UNKNOWN"
  exit 2
fi
if [[ "${DEPLOY_DRIFT_FETCH:-1}" != "0" ]]; then
  timeout 10 git -C "${PRODUCT_REPO}" fetch --quiet origin --tags --prune 2>/dev/null || log "WARN: git fetch in ${PRODUCT_REPO} failed — reading existing tags (may be stale)"
fi
latest_tag="$(git -C "${PRODUCT_REPO}" tag --list 'v*' --sort=-v:refname | head -1)"
if [[ -z "${latest_tag}" ]]; then
  report "deploy-drift: no v* tags found in ${PRODUCT_REPO} — UNKNOWN"
  exit 2
fi

# ===========================================================================================
# 4. AHEAD — commits on master that are NOT in the deployed version, named
# ===========================================================================================
if git -C "${PRODUCT_REPO}" rev-parse --verify --quiet "refs/tags/${running_tag}" >/dev/null 2>&1; then
  ahead_log="$(git -C "${PRODUCT_REPO}" log --oneline "refs/tags/${running_tag}..${MASTER_REF}" 2>/dev/null || true)"
else
  report "deploy-drift: deployed tag '${running_tag}' is not a known ref in ${PRODUCT_REPO} — cannot count master-ahead commits, UNKNOWN"
  exit 2
fi
ahead_count="$(printf '%s\n' "${ahead_log}" | grep -cE '^[0-9a-f]{7,}' || true)"
ahead_count="${ahead_count:-0}"

# ===========================================================================================
# 5. VERDICT
# ===========================================================================================
red=0
reason=""
cmp_rl="$(_vercmp "${running_tag}" "${latest_tag}")"
if [[ "${running_tag}" != "${latest_tag}" ]]; then
  red=1
  case "${cmp_rl}" in
    -1) reason="running ${running_tag} is BEHIND the latest published release ${latest_tag}" ;;
    1)  reason="running ${running_tag} is AHEAD of any published release (latest ${latest_tag}) — unreleased tag deployed?" ;;
    *)  reason="running ${running_tag} != latest published release ${latest_tag}" ;;
  esac
fi
if [[ "${pinned_tag}" != "${running_tag}" ]]; then
  red=1
  reason="${reason}; compose pins ${pinned_tag:-<none>} but the container runs ${running_tag} — a 'docker compose up' would change production (downgrade hazard)"
fi
if [[ "${ahead_count}" -gt "${MAX_AHEAD}" ]]; then
  red=1
  reason="${reason}; master is ${ahead_count} commits ahead of ${running_tag} (max ${MAX_AHEAD})"
fi

report "DEPLOY-DRIFT: RUNNING=${running_tag} PINNED=${pinned_tag} LATEST=${latest_tag} AHEAD=${ahead_count}"
if [[ "${red}" -eq 0 ]]; then
  report "VERDICT: GREEN — production matches the latest published release and compose; ${ahead_count} un-released commit(s) within budget."
  if [[ -n "${ahead_log}" ]]; then
    log "  commits on master not in ${running_tag} (within budget):"
    printf '%s\n' "${ahead_log}" | sed 's/^/    /'
  fi
  exit 0
fi

report "VERDICT: RED — ${reason#; }"
if [[ "${ahead_count}" -gt 0 ]]; then
  log "  commits on master NOT deployed (${ahead_count}):"
  printf '%s\n' "${ahead_log}" | sed 's/^/    /'
fi
exit 1
