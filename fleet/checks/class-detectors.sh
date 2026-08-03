#!/usr/bin/env bash
# class-detectors.sh — UNIFORM MISSING-CLASS DETECTOR HARNESS.
#
# WHY THIS EXISTS
#   "anything with a lifecycle and no terminal gate accumulates" — operator directive
#   2026-08-02. Nine classes measured accumulating with NO detector. One detector per
#   class, uniform contract, consumed by FLEET-STATUS-BOARD's registry + runner.
#
# UNIFORM CONTRACT (same shape stranded-work.sh already emits)
#   Each finding is a line:
#     CLASS[<class-id>] verdict=<OK|FINDING(n)|STALE|BROKEN> summary="<one-line>" recover="<command>"
#   At end, per-class counts and exit 1 if any finding; exit 0 only when all classes OK.
#   BROKEN = detector itself cannot run (tool missing, unreadable state).
#   STALE  = detector ran but its output is older than TTL (heartbeat check: cron cadence leg).
#
# FAIL-ON-REVERT
#   Every class has a test that seeds the exact condition and proves it FIRES. A detector
#   never seen to fire is not a detector — that is the 101-unrun-proof-suites class.
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]
#   CLASS_DETECTOR_ACTIVE short-circuits accidental nesting.
#
# Usage: fleet/checks/class-detectors.sh [--quiet] [--class <id> ...]
# Exit: 0 fully determined, nothing found
#       1 one or more CLASS findings
#       2 usage error
#       3 BROKEN — at least one class BROKEN, no other findings
# Env:
#   CD_REPOS        repo paths to scan (default: "REPO_CHARON REPO_CHARON_PRIVATE" from repo-registry)
#   CD_FLEET_DIR    fleet dir (default: auto-detected)
#   CD_OFFLINE=1    skip checks that need network/gh (deploy-drift, catalog-rot)
#   CD_DEPLOY_HOST  hostname for deploy-drift check (default: 4-LOM)
#   CD_LIMIT        max detail lines per class (default 10; 0 = all)
set -uo pipefail

[ -n "${CLASS_DETECTOR_ACTIVE:-}" ] && { echo "class-detectors: already running (reentrancy guard) — skipping"; exit 0; }
export CLASS_DETECTOR_ACTIVE=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET="${CD_FLEET_DIR:-$(cd "$HERE/.." && pwd)}"
QUIET=0; OFFLINE="${CD_OFFLINE:-0}"; LIMIT="${CD_LIMIT:-10}"
SELECTED_CLASSES=""
while [ $# -gt 0 ]; do
  case "${1:-}" in
    --quiet) QUIET=1; shift ;;
    --class) SELECTED_CLASSES="$SELECTED_CLASSES ${2:-}"; shift 2 ;;
    *) echo "usage: class-detectors.sh [--quiet] [--class <id> ...]" >&2; exit 2 ;;
  esac
done

FOUND=0; BROKEN_COUNT=0
declare -A CLS_N=()
say(){ [ "$QUIET" -eq 1 ] || echo "$*"; }

class_finding(){
  local cls="$1" verdict="$2" summary="$3" recover="$4"
  FOUND=$((FOUND+1))
  local n=$(( ${CLS_N[$cls]:-0} + 1 )); CLS_N[$cls]=$n
  local line="CLASS[${cls}] verdict=${verdict} summary=\"${summary}\" recover=\"${recover}\""
  if [ "$LIMIT" -eq 0 ] || [ "$n" -le "$LIMIT" ]; then
    echo "$line"
  elif [ "$n" -eq $((LIMIT+1)) ]; then
    echo "CLASS[${cls}] ... more of this class suppressed (CD_LIMIT=0 for the full list)"
  fi
}
class_ok(){ local cls="$1" summary="$2"; echo "CLASS[${cls}] verdict=OK summary=\"${summary}\""; }
class_broken(){ local cls="$1" summary="$2" recover="$3"; BROKEN_COUNT=$((BROKEN_COUNT+1)); echo "CLASS[${cls}] verdict=BROKEN summary=\"${summary}\" recover=\"${recover}\""; }
class_stale(){ local cls="$1" summary="$2" recover="$3"; FOUND=$((FOUND+1)); echo "CLASS[${cls}] verdict=STALE summary=\"${summary}\" recover=\"${recover}\""; }

# ── target repos ─────────────────────────────────────────────────────────────────────────
resolve_repos(){
  if [ -n "${CD_REPOS:-}" ]; then
    printf '%s\n' "$CD_REPOS" | tr ' ' '\n' | while IFS= read -r p; do [ -n "$p" ] && echo "$p"; done
    return
  fi
  # shellcheck source=/dev/null
  source "$FLEET/repo-registry.sh" 2>/dev/null || true
  local k; for k in charon charon-private; do
    repo_resolve "$k" "" >/dev/null 2>&1 || continue
    echo "$RR_PATH"
  done
}

is_class_selected(){ local c="${1:-}"; [ -z "$SELECTED_CLASSES" ] && return 0; case " $SELECTED_CLASSES " in *" $c "*) return 0;; *) return 1;; esac; }

# ═══════════════════════════════════════════════════════════════════════════════════════════
# CLASS DETECTORS — one function per class, uniform contract
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── class 1: UNCOMMITTED-TOOLS ───────────────────────────────────────────────────────────
# Tools/scripts built but never committed to git. PURE LOCAL GIT — cheapest detection class.
# Measured: 3 files, 362 lines, never in git AT ALL (today on the live rig).
detect_uncommitted_tools(){
  local cls="uncommitted-tools"
  is_class_selected "$cls" || return 0
  local repo found_any=0
  while IFS= read -r repo; do
    [ -n "$repo" ] || continue
    [ -d "$repo/.git" ] || [ -f "$repo/.git" ] || continue
    local tools_dir="$repo/tools"
    [ -d "$tools_dir" ] || { class_ok "$cls" "repo $repo: no tools/ dir — nothing to check"; continue; }
    local untracked
    untracked="$(git -C "$repo" ls-files --others --exclude-standard -- "$tools_dir" 2>/dev/null || true)"
    if [ -n "$untracked" ]; then
      found_any=1
      local total_lines=0 f lines
      while IFS= read -r f; do
        [ -n "$f" ] || continue
        lines=$(wc -l < "$repo/$f" 2>/dev/null || echo 0)
        total_lines=$((total_lines + lines))
        class_finding "$cls" "FINDING(1)" "$repo: uncommitted tool '$f' ($lines lines) — built but never in git" "git -C $repo add $f && git -C $repo commit -m 'tools: add uncommitted $f' # or rm $repo/$f if dead"
      done <<< "$untracked"
    fi
  done < <(resolve_repos)
  if [ "$found_any" -eq 0 ]; then
    class_ok "$cls" "all tools/ files tracked by git"
  fi
}

# ── class 2: UNTRACKED-REVIEWS ──────────────────────────────────────────────────────────
# Review-log entries that lack a reviewed/ marker in fleet/state/reviewed/. A review written
# but never linked to the review gate means its verdict (NEEDS-REVISION, CONCERN, APPROVE)
# never enters the reconcile gate — the review exists but the safety claim is not enforced.
# PURE LOCAL GIT + filesystem.
detect_untracked_reviews(){
  local cls="untracked-reviews"
  is_class_selected "$cls" || return 0
  local found_any=0
  while IFS= read -r repo; do
    [ -n "$repo" ] || continue
    [ -d "$repo/.git" ] || [ -f "$repo/.git" ] || continue
    local review_dir="$repo/docs/review-log"
    [ -d "$review_dir" ] || { class_ok "$cls" "repo $repo: no docs/review-log/ dir — nothing to check"; continue; }

    local reviewed_dir="$repo/fleet/state/reviewed"
    [ -d "$reviewed_dir" ] || reviewed_dir="$FLEET/state/reviewed"

    local f id
    for f in "$review_dir"/*.md; do
      [ -f "$f" ] || continue
      id="$(basename "$f" .md)"
      if [ -n "$reviewed_dir" ] && [ -f "$reviewed_dir/$id" ]; then continue; fi
      found_any=1
      class_finding "$cls" "FINDING(1)" "$repo: review-log '$id' has NO reviewed/ marker — verdict not tracked" "touch $reviewed_dir/$id && echo 'reviewed_sha=<sha>' >> $reviewed_dir/$id # or link to reconcile-review-gate"
    done
  done < <(resolve_repos)
  if [ "$found_any" -eq 0 ]; then
    class_ok "$cls" "all review-log entries have reviewed/ markers"
  fi
}

# ── class 3: CRONTAB-REGISTRATION ───────────────────────────────────────────────────────
# Scheduled job registration in crontab. The crontab entry is machine-local, untracked
# config — it can drift, vanish, or point at a checkout path that no longer has the script.
# PURE LOCAL — crontab(1) + filesystem.
# Two legs, both required: leg A = entry REGISTERED, leg B = target SCRIPT EXISTS.
detect_crontab_registration(){
  local cls="crontab-registration"
  is_class_selected "$cls" || return 0
  local cron_out
  cron_out="$(crontab -l 2>/dev/null || true)"
  if [ -z "$cron_out" ]; then
    # No crontab at all — the whole class is missing.
    class_finding "$cls" "FINDING(1)" "NO crontab registered — no scheduled jobs will fire between sessions" "(crontab -l 2>/dev/null; echo '*/20 * * * * $FLEET/checks/stranded-work-cron.sh >/dev/null 2>&1') | crontab -"
    return
  fi

  # Check each entry for a valid script path. Non-comment, non-empty lines only.
  local found_any=0
  local line path
  while IFS= read -r line; do
    [ -n "$line" ] || continue; [[ "$line" == \#* ]] && continue
    # Extract likely script path — crontab entries vary; we extract the first absolute
    # or relative path that looks like a script or binary after the schedule fields.
    path="$(printf '%s' "$line" | grep -oP '(?:^|\s)\K(?:\S+/)?[^/\s]*\.sh(?=\s|$)' | head -1 || true)"
    [ -n "$path" ] || continue
    if ! command -v "$path" >/dev/null 2>&1 && [ ! -x "$path" ]; then
      found_any=1
      class_finding "$cls" "STALE" "crontab entry references '$path' which does NOT exist on this box — the scheduled job is a no-op" "update the crontab entry or land the referenced script"
    fi
  done <<< "$cron_out"

  # Count valid crontab entries that reference fleet/ scripts
  local fleet_entries; fleet_entries="$(printf '%s\n' "$cron_out" | grep -c 'fleet/' || true)"
  if [ "${fleet_entries:-0}" -eq 0 ]; then
    class_finding "$cls" "FINDING(1)" "crontab exists but has NO fleet/ entries — no rig scheduled jobs registered" "(crontab -l 2>/dev/null; echo '*/20 * * * * $FLEET/checks/stranded-work-cron.sh >/dev/null 2>&1') | crontab -"
    return
  fi

  if [ "$found_any" -eq 0 ]; then
    class_ok "$cls" "crontab registered with $fleet_entries fleet entry(s), all script paths exist"
  fi
}

# ── class 4: CONFIG-SSOT-KEYS ───────────────────────────────────────────────────────────
# Config keys that code READS but the SSOT (CONFIG-SOURCES.tsv) lacks. When code reads a
# key and the SSOT doesn't define it, every downstream consumer fails closed — the spill-up
# cost ceiling was missing and every tab's spill-up silently failed.
# Uses the existing CONFIG-SOURCES.tsv + a code scan for config reads.
detect_config_ssot_keys(){
  local cls="config-ssot-keys"
  is_class_selected "$cls" || return 0
  local ssot="$FLEET/state/CONFIG-SOURCES.tsv"
  if [ ! -f "$ssot" ]; then
    class_broken "$cls" "CONFIG-SOURCES.tsv not found at $ssot — cannot verify SSOT coverage" "land the CONFIG-SSOT-CANARY-REGISTER ticket so the SSOT file exists"
    return
  fi

  # Scan fleet scripts and src/charon for config key reads (os.environ.get / ${VAR:-} patterns)
  # that read known config keys. Compare against the SSOT.
  local found_any=0 repo
  while IFS= read -r repo; do
    [ -n "$repo" ] || continue
    [ -d "$repo/.git" ] || [ -f "$repo/.git" ] || continue

    # Collect SSOT keys from CONFIG-SOURCES.tsv
    local ssot_keys; ssot_keys="$(cut -f1 "$ssot" 2>/dev/null | grep -v '^#' | grep -v '^$' | sort -u)"

    # Scan for env-var reads of known config key shape in fleet/ and src/
    local code_keys
    code_keys="$(grep -rhoP '(?:os\.environ(?:\[|\.get\()[^)]*|(?:CHARON|FLEET|SESSION|CLAIM|STRANDED|GATE|REVIEW|BOARD|PENDING|RIG|CD_)[A-Z_]{2,}' \
      "$repo/fleet/" "$repo/src/" 2>/dev/null \
      | sed -E 's/os\.environ(?:\[|\.get\()["'\'']([^"'\'']+)["'\'']\).*/\1/; s/^([A-Z][A-Z_]{2,}).*/\1/' \
      | grep -v '^#' | sort -u || true)"

    # Cross-reference: keys in code but NOT in SSOT
    local missing_keys key
    while IFS= read -r key; do
      [ -n "$key" ] || continue
      printf '%s\n' "$ssot_keys" | grep -qxF "$key" && continue
      found_any=1
      class_finding "$cls" "FINDING(1)" "$repo: config key '$key' is READ by code but NOT in $ssot" "add '$key' to $ssot with its source and default"
    done < <(printf '%s\n' "$code_keys" | grep -E '^(CHARON|FLEET|SESSION|CLAIM|STRANDED|GATE|REVIEW|BOARD|PENDING|RIG|CD_)[A-Z_]{2,}$' || true)
  done < <(resolve_repos)

  if [ "$found_any" -eq 0 ]; then
    if [ "${BROKEN_COUNT:-0}" -eq 0 ] || true; then
      class_ok "$cls" "all config keys read by code are present in CONFIG-SOURCES.tsv"
    fi
  fi
  [ "$BROKEN_COUNT" -gt 0 ] && return; true
}

# ── class 5: DEPLOY-DRIFT ──────────────────────────────────────────────────────────────
# Deployed artifact (4-LOM build_sha) drifts behind master. ADOPT gh REST — no reimpl.
# 4-LOM was on build_sha 9659998, far behind master, at measurement time.
detect_deploy_drift(){
  local cls="deploy-drift"
  is_class_selected "$cls" || return 0
  local deploy_host="${CD_DEPLOY_HOST:-4-LOM}"

  if [ "$OFFLINE" -eq 1 ] || ! command -v gh >/dev/null 2>&1; then
    class_broken "$cls" "offline or gh unavailable — cannot check deploy drift against $deploy_host" "run with CD_OFFLINE=0 and gh authenticated; or check manually: ssh $deploy_host cat /opt/charon/build_sha"
    return
  fi

  # Get the deployed sha from the deploy host (gh REST: check the deployment API or
  # the deploy host's build_sha file via ssh/gh). This is ADOPTED — using gh REST
  # for the deployment status endpoint.
  local product_repo repo_slug deployed_sha
  # shellcheck source=/dev/null
  source "$FLEET/repo-registry.sh" 2>/dev/null || true
  repo_resolve charon "" >/dev/null 2>&1 || { class_broken "$cls" "cannot resolve charon repo path" "verify repo-registry.sh is present"; return; }
  product_repo="$RR_PATH"
  repo_slug="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || git -C "$product_repo" remote get-url origin 2>/dev/null | sed -E 's#.*[:/]([^/]+/[^/.]+)(\.git)?$#\1#')"
  [ -n "$repo_slug" ] || { class_broken "$cls" "cannot resolve repo slug for deploy-drift check" "verify origin remote on $product_repo"; return; }

  # Get latest deployment via gh REST
  deployed_sha="$(gh api "repos/$repo_slug/deployments?environment=production&per_page=1" --jq '.[0].sha' 2>/dev/null || true)"
  if [ -z "$deployed_sha" ]; then
    # Fallback: try the deploy host directly if it's a local box
    if [ -f "/opt/charon/build_sha" ]; then
      deployed_sha="$(cat /opt/charon/build_sha 2>/dev/null)"
    fi
  fi
  [ -n "$deployed_sha" ] || { class_broken "$cls" "cannot determine deployed sha — no deployment found via gh REST and no /opt/charon/build_sha" "check deployment at https://github.com/$repo_slug/deployments"; return; }

  local master_sha; master_sha="$(git -C "$product_repo" rev-parse origin/master 2>/dev/null || git -C "$product_repo" rev-parse master 2>/dev/null)"
  [ -n "$master_sha" ] || { class_broken "$cls" "cannot resolve master sha in $product_repo" "fetch origin/master first"; return; }

  if [ "$deployed_sha" = "$master_sha" ]; then
    class_ok "$cls" "deployed sha $deployed_sha matches master"
  else
    local behind; behind="$(git -C "$product_repo" rev-list --count "$deployed_sha..$master_sha" 2>/dev/null || echo "?")"
    class_finding "$cls" "FINDING(1)" "deployed sha $deployed_sha is $behind commit(s) behind master $master_sha" "deploy master to the production environment via the deploy workflow"
  fi
}

# ── class 6: CATALOG-ROT ──────────────────────────────────────────────────────────────
# Catalog/pricing entries missing or stale. Measured: 10 of 861 priced; a `-free` model
# billed $0.15. ADOPT the existing catalog readers (pricing CSV/config) — no reimpl.
detect_catalog_rot(){
  local cls="catalog-rot"
  is_class_selected "$cls" || return 0

  # Look for catalog/pricing data in the product repo
  local product_repo pricing_dir
  # shellcheck source=/dev/null
  source "$FLEET/repo-registry.sh" 2>/dev/null || true
  repo_resolve charon "" >/dev/null 2>&1 || { class_broken "$cls" "cannot resolve charon repo path" "verify repo-registry.sh"; return; }
  product_repo="$RR_PATH"

  pricing_dir="$product_repo/src/charon/data"
  [ -d "$pricing_dir" ] || { class_broken "$cls" "no pricing data dir at $pricing_dir" "check catalog location in the product repo"; return; }

  # Count known models from pricing files
  local pricing_files; pricing_files="$(find "$pricing_dir" -name '*.csv' -o -name '*.json' -o -name '*.tsv' 2>/dev/null || true)"
  if [ -z "$pricing_files" ]; then
    class_broken "$cls" "no pricing files found in $pricing_dir" "the catalog data source may have moved — update the detector path"
    return
  fi

  local total_models=0 priced=0 unpriced=0
  while IFS= read -r pf; do
    [ -n "$pf" ] || continue
    local rows; rows="$(grep -c '^[^#]' "$pf" 2>/dev/null || true)"
    total_models=$((total_models + (rows>0?rows-1:0)))  # minus header
    # Check for zero-price rows or missing price columns
    local zero_priced; zero_priced="$(awk -F',' 'NR>1 && ($NF == "0" || $NF == "" || $NF == "0.0")' "$pf" 2>/dev/null | grep -c . || true)"
    [ "${zero_priced:-0}" -gt 0 ] && { priced=$((priced + zero_priced)); unpriced=$((unpriced + zero_priced)); }
  done <<< "$pricing_files"

  if [ "$unpriced" -gt 0 ]; then
    class_finding "$cls" "FINDING($unpriced)" "$unpriced of $total_models models have zero/missing price — catalog rot detected" "audit pricing in $pricing_dir: run 'grep -rn \",0$\" $pricing_dir' for zero-price entries"
  elif [ "$total_models" -eq 0 ]; then
    class_broken "$cls" "catalog appears empty — $total_models models found in $pricing_dir" "verify pricing data is populated"
  else
    class_ok "$cls" "$total_models models with pricing data — no zero-price entries"
  fi
}

# ── class 7: DAEMON-LIVENESS ───────────────────────────────────────────────────────────
# Daemons/sidecars running past their retirement date. Session-bridge retirement slated
# 2026-07-26, still dual-running at measurement time. ADOPT process table + service registry.
detect_daemon_liveness(){
  local cls="daemon-liveness"
  is_class_selected "$cls" || return 0

  local service_registry="$FLEET/state/service-registry.tsv"
  if [ ! -f "$service_registry" ]; then
    class_broken "$cls" "service-registry.tsv not found at $service_registry — cannot check daemon retirement" "land the SERVICE-LIVENESS-WATCHDOG ticket so the registry exists"
    return
  fi

  # For now: check if session-bridge process is running (the known stale daemon)
  local found_any=0
  if pgrep -f 'session.bridge' >/dev/null 2>&1; then
    found_any=1
    class_finding "$cls" "FINDING(1)" "session-bridge process still running — retirement was slated 2026-07-26" "verify the replacement is live, then stop the old session-bridge: pkill -f session.bridge"
  fi

  # Generic check: scan service-registry.tsv for retired services still running
  local line service retire_date
  while IFS=$'\t' read -r line; do
    [ -n "$line" ] || continue
    [[ "$line" == \#* ]] && continue
    service="$(printf '%s' "$line" | cut -f1)"
    retire_date="$(printf '%s' "$line" | cut -f5 2>/dev/null || true)"
    [ -n "$retire_date" ] || continue
    local today retire_epoch today_epoch
    today="$(date +%s)"
    retire_epoch="$(date -d "$retire_date" +%s 2>/dev/null || echo 0)"
    [ "$retire_epoch" -gt 0 ] || continue
    if [ "$today" -gt "$retire_epoch" ] && pgrep -f "$service" >/dev/null 2>&1; then
      found_any=1
      class_finding "$cls" "FINDING(1)" "service '$service' is still running past its retirement date $retire_date" "stop the service or update its retirement date in $service_registry"
    fi
  done < "$service_registry"

  if [ "$found_any" -eq 0 ]; then
    class_ok "$cls" "no daemons/sidecars running past retirement"
  fi
}

# ── class 8: NAME-POOL-EXHAUSTION ──────────────────────────────────────────────────────
# Identity/name pool exhaustion. 48% burned by claim stubs, ~9 names left before sessions
# fail. ADOPT claim-jedi-name.sh — the existing name allocator answers this class directly.
detect_name_pool_exhaustion(){
  local cls="name-pool-exhaustion"
  is_class_selected "$cls" || return 0

  local claim_script="$FLEET/claim-jedi-name.sh"
  if [ ! -f "$claim_script" ]; then
    class_broken "$cls" "claim-jedi-name.sh not found at $claim_script" "land the claim-jedi-name script"
    return
  fi

  # Ask claim-jedi-name.sh for pool stats. If it can report available names, use them.
  # The pool is a list of available Jedi names; claim-jedi-name.sh's list command gives
  # the remaining pool.
  local pool_out available total pct
  pool_out="$(bash "$claim_script" list 2>/dev/null || true)"
  available="$(printf '%s\n' "$pool_out" | grep -c . || true)"
  # Total pool size — hardcoded from claim-jedi-name.sh's pool length (the known pool)
  if command -v python3 >/dev/null 2>&1 && [ -f "$claim_script" ]; then
    total="$(grep -c '^[[:space:]]*[a-z]' "$claim_script" 2>/dev/null || true)"
  fi
  total="${total:-0}"

  if [ "${total:-0}" -gt 0 ] && [ "${available:-0}" -le $((total / 4)) ]; then
    pct=$(( 100 - (available * 100 / total) ))
    class_finding "$cls" "FINDING(1)" "name pool exhaustion: $available/$total names remaining (~$pct% consumed) — ~$available sessions before claim failures" "prune stale claim stubs: run fleet/claim-jedi-name.sh gc; or expand the pool in claim-jedi-name.sh"
  elif [ "$available" -gt 0 ]; then
    class_ok "$cls" "$available/$total names remaining in the Jedi name pool"
  else
    class_broken "$cls" "claim-jedi-name.sh exists but could not determine pool size" "run 'bash $claim_script list' manually to verify"
  fi
}

# ── class 9: OPERATOR-STALENESS ────────────────────────────────────────────────────────
# Operator-action items with no age signal. OPERATOR-ACTIONS at #30, no staleness signal
# means items can sit indefinitely without escalation.
detect_operator_staleness(){
  local cls="operator-staleness"
  is_class_selected "$cls" || return 0

  local ops_file="$FLEET/state/OPERATOR-ACTIONS.md"
  if [ ! -f "$ops_file" ]; then
    class_ok "$cls" "no OPERATOR-ACTIONS.md — nothing to stale"
    return
  fi

  local total_items; total_items="$(grep -c '^[A-Z#]' "$ops_file" 2>/dev/null || true)"
  if [ "${total_items:-0}" -eq 0 ]; then
    class_ok "$cls" "OPERATOR-ACTIONS.md is empty — no pending items"
    return
  fi

  # The file has no timestamps on individual items — that IS the finding.
  # Items are labels (A-Z, #N) — check for items that have been sitting
  # by comparing against git log (when they were added).
  local found_any=0
  local label text
  while IFS=$'\t' read -r label text; do
    [ -n "$label" ] || continue
    # Check when this label was added via git log
    local added; added="$(git -C "$FLEET/.." log --oneline --diff-filter=A -- "$ops_file" \
      | grep -c "${label}[^A-Za-z0-9]" 2>/dev/null || true)"
    # This is approximate — the real fix is adding timestamps to the file.
    # For now, report any item count above a threshold.
    if [ "${total_items:-0}" -gt 10 ]; then
      found_any=1
      class_finding "$cls" "FINDING($total_items)" "$total_items pending operator actions with NO age signal — items can sit indefinitely" "add timestamps to OPERATOR-ACTIONS.md items; run 'bash $FLEET/pending.sh list' to triage"
      break
    fi
  done < "$ops_file"

  if [ "$found_any" -eq 0 ]; then
    class_ok "$cls" "$total_items operator action(s) — within threshold"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════════════════
# MAIN — run all class detectors
# ═══════════════════════════════════════════════════════════════════════════════════════════

[ "$QUIET" -eq 0 ] && echo "--- class-detectors: missing-class detector harness ---"

detect_uncommitted_tools
detect_untracked_reviews
detect_crontab_registration
detect_config_ssot_keys
detect_deploy_drift
detect_catalog_rot
detect_daemon_liveness
detect_name_pool_exhaustion
detect_operator_staleness

if [ "$FOUND" -gt 0 ]; then
  [ "$QUIET" -eq 0 ] && echo ""
  for c in "${!CLS_N[@]}"; do echo "class-detectors: ${CLS_N[$c]} x CLASS[$c]"; done
  echo "class-detectors: $FOUND finding(s) — see recovery commands above"
  echo "class-detectors: $BROKEN_COUNT class(es) BROKEN (detector could not run)"
  exit 1
fi
if [ "$BROKEN_COUNT" -gt 0 ]; then
  echo "class-detectors: $BROKEN_COUNT class(es) BROKEN (detector could not run) — this is NOT a clean receipt"
  exit 3
fi
echo "clean: class-detectors ($(for c in uncommitted-tools untracked-reviews crontab-registration config-ssot-keys deploy-drift catalog-rot daemon-liveness name-pool-exhaustion operator-staleness; do printf '%s ' "$c"; done) — all classes OK)"
exit 0
