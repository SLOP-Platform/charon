#!/usr/bin/env bash
# Advisory session-end deploy harness. Safe to source: exposes session_end_deploy
# and never blocks a session close, even when lookup/deploy infrastructure is down.

session_end_deploy(){
  local fleet product_repo host ssh_key container deploy_sh tsv today tab
  fleet="${FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
  product_repo="${SESSION_END_PRODUCT_REPO:-${CHARON_PRODUCT_REPO:-/home/stack/code/charon}}"
  host="${CHARON_DEPLOY_HOST:-stack@10.0.1.60}"
  ssh_key="${CHARON_DEPLOY_SSH_KEY:-$HOME/.ssh/4lom}"
  container="${CHARON_DEPLOY_CONTAINER:-charon-gateway-1}"
  deploy_sh="${SESSION_END_DEPLOY_SH:-$fleet/deploy.sh}"
  tsv="${SESSION_END_REDS_TSV:-$fleet/reds.tsv}"
  today="$(date +%F)"
  tab=$'\t'

  _sed_log(){ printf 'session-end-deploy: %s\n' "$*"; }
  _sed_warn(){ printf 'SESSION-END-DEPLOY WARNING: %s\n' "$*" >&2; }
  _sed_status(){ awk -F"$tab" -v id="$1" '$1==id{print $7; exit}' "$tsv" 2>/dev/null; }
  _sed_add_red(){
    local id="$1" sev="$2" area="$3" desc="$4" check="$5" st tmp
    st="$(_sed_status "$id")"
    if [ -z "$st" ]; then
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$id" "$today" "$sev" "$area" "$desc" "$check" "open" "" >> "$tsv" || true
      _sed_log "registered advisory red: $id ($sev/$area)"
    elif [ "$st" = closed ]; then
      tmp="$(mktemp)" || return 0
      awk -F"$tab" -v OFS="$tab" -v id="$id" '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$tsv" > "$tmp" && mv "$tmp" "$tsv" || rm -f "$tmp"
      _sed_log "reopened advisory red: $id ($sev/$area)"
    fi
    return 0
  }
  _sed_unverified(){
    local tag="$1"
    _sed_add_red "deploy-4lom-unverified" P1 gate \
      "session-end deploy skipped: release CI for $tag is not green/known; verify release.yml before deploying 4-LOM" \
      "manual:verify release.yml success for $tag, then close this advisory red"
  }
  _sed_failed(){
    local tag="$1"
    _sed_add_red "deploy-4lom-failed" P1 gate \
      "session-end deploy to $tag failed; fleet/deploy.sh auto-rolled-back, inspect 4-LOM and redeploy manually" \
      "manual:inspect 4-LOM rollback state and rerun fleet/deploy.sh $tag successfully"
  }

  local latest_cmd running_cmd ci_cmd latest_tag running_image running_tag ci_out rc
  # Every external lookup is wrapped in `timeout` so an unreachable/auth-prompting 4-LOM (or a
  # slow gh call) can NEVER hang the session close — the whole point of this harness is to be
  # advisory. The default ssh additionally fails fast (BatchMode, no password prompt).
  local lookup_timeout="${SESSION_END_LOOKUP_TIMEOUT:-15}"
  latest_cmd="${SESSION_END_LATEST_TAG_CMD:-git -C '$product_repo' tag --list 'v*' --sort=-v:refname | head -1}"
  running_cmd="${SESSION_END_RUNNING_TAG_CMD:-ssh -o BatchMode=yes -o ConnectTimeout=5 -i '$ssh_key' '$host' \"docker inspect '$container' --format '{{.Config.Image}}'\"}"

  latest_tag="$(timeout "$lookup_timeout" bash -c "$latest_cmd" 2>/dev/null | head -1)" || latest_tag=""
  if [ -z "$latest_tag" ]; then
    _sed_warn "could not resolve latest released tag; session close continues"
    return 0
  fi

  running_image="$(timeout "$lookup_timeout" bash -c "$running_cmd" 2>/dev/null | head -1)" || running_image=""
  running_tag="${running_image##*:}"
  if [ -z "$running_image" ] || [ -z "$running_tag" ] || [ "$running_tag" = "$running_image" ]; then
    _sed_warn "could not resolve 4-LOM running tag; session close continues"
    return 0
  fi

  if [ "$running_tag" = "$latest_tag" ]; then
    _sed_log "4-LOM already on $latest_tag; no deploy"
    return 0
  fi

  ci_cmd="${SESSION_END_CI_GREEN_CMD:-gh run list --repo SLOP-Platform/charon --workflow release.yml --branch '$latest_tag'}"
  ci_out="$(timeout "$lookup_timeout" bash -c "$ci_cmd" 2>/dev/null)"; rc=$?
  if [ "$rc" -ne 0 ] || ! printf '%s\n' "$ci_out" | grep -qi 'success' || ! printf '%s\n' "$ci_out" | grep -qi 'completed'; then
    _sed_warn "release CI for $latest_tag is not green/known; skipping deploy"
    _sed_unverified "$latest_tag"
    return 0
  fi

  _sed_log "deploying 4-LOM: $running_tag -> $latest_tag"
  if ! "$deploy_sh" "$latest_tag"; then
    _sed_warn "deploy.sh failed for $latest_tag; it auto-rolled-back. Session close continues."
    _sed_failed "$latest_tag"
    return 0
  fi

  _sed_log "deploy complete: $running_tag -> $latest_tag"
  return 0
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  session_end_deploy "$@"
fi
