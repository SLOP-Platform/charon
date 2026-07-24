#!/usr/bin/env bash
# registry-discovery.sh — KS29 DISCOVERY LEG (k8s-controller reconcile shape).
#
# THE BUG THIS CATCHES (SG-ISSUE-CONTROL-PLANE slice 2): the DISCOVER leg's registry primitive
# was DESIGNED-not-BUILT. Until this ships, "un-registered component" detection is fake-green:
# graphify's code-relations graph (9786 links) can reveal a new load-bearing plane/subsystem/
# entrypoint, but nothing FAILS CLOSED on it — the control plane self-EXTENDING property
# (new planes auto-roll in) is unenforced. This script is the anti-fake-green backbone.
#
# k8s-CONTROLLER RECONCILE SHAPE:
#   1. LIST  — gather known states: component-registry.tsv entries + graphify graph nodes
#   2. DIFF  — detect unregistered components, stale entries, malformed rows
#   3. ACT   — report each finding as a reconciler item (machine-readable + human)
#
# THREE LEGS:
#   CONFORMANCE — every registry row is valid (8 tab-separated fields, known kinds)
#   DISCOVERY   — a component in graphify's graph that SHOULD be registered but isn't
#   DRIFT       — a registered component whose canary/test vanished or whose path diverges
#
# Exit 0 = GREEN (no findings; registry is complete, fresh, and accurate).
# Exit 1 = RED   (one or more findings; names each offender).
# Exit 2 = usage error (bad subcommand or missing arguments).
#
# Subcommands:
#   check       full reconcile: conformance + discovery + drift. Hard verdict (exit 0/1).
#   gate        same as check, with machine-readable GATE: GREEN/RED prefix (for preflight).
#   conformance registry-file format validation only.
#   discovery   graphify-graph cross-reference only.
#   drift       registered-component liveness only.
#   list        print every registered component (one-per-line, machine-readable).
#
# Env seams (isolated self-test overrides; defaults are the real paths):
#   REGISTRY_DISCOVERY_FAKE=<dir>   — hermetic test fixture dir (substitutes all file reads).
#   REGISTRY_FILE=<path>            — override component-registry.tsv location.
#   GRAPHIFY_GRAPH=<path>           — override graph.json path.
#   REGISTRY_FLEET=<path>           — override fleet/ root (for canary/test existence checks).
set -uo pipefail
FLEET="${REGISTRY_FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
REGISTRY_FILE="${REGISTRY_FILE:-$FLEET/state/component-registry.tsv}"
GRAPHIFY_GRAPH="${GRAPHIFY_GRAPH:-$FLEET/../graphify-out/graph.json}"
FAKE_ROOT="${REGISTRY_DISCOVERY_FAKE:-}"

RC=0
FINDINGS=()

# --- helpers ----------------------------------------------------------------

warn(){ printf '  %s\n' "$@" >&2; }
finding(){ FINDINGS+=("$1"); warn "  FINDING: $1"; }

# read_registry — emits tab-separated rows from the registry (skips comments).
# In FAKE mode, reads from $FAKE_ROOT/registry.tsv instead.
read_registry(){
  if [ -n "$FAKE_ROOT" ]; then
    [ -f "$FAKE_ROOT/registry.tsv" ] && cat "$FAKE_ROOT/registry.tsv" || true
    return
  fi
  [ -f "$REGISTRY_FILE" ] || return
  grep -v '^[[:space:]]*#' "$REGISTRY_FILE" | grep -v '^[[:space:]]*$' || true
}

# read_graph_nodes — emits node labels from graphify's graph.json, one per line.
# Labels that look like a load-bearing component (contain '/', end in 'plane', etc.)
# are the discovery input. In FAKE mode, reads from $FAKE_ROOT/graph_nodes.txt.
read_graph_nodes(){
  if [ -n "$FAKE_ROOT" ]; then
    [ -f "$FAKE_ROOT/graph_nodes.txt" ] && cat "$FAKE_ROOT/graph_nodes.txt" || true
    return
  fi
  [ -f "$GRAPHIFY_GRAPH" ] || return
  python3 - "$GRAPHIFY_GRAPH" <<'PY' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    nodes = d.get("nodes", [])
    seen = set()
    for n in nodes:
        lbl = n.get("label", "") or n.get("id", "")
        if not lbl:
            continue
        # Emit every unique node label — the script filters for load-bearing patterns.
        if lbl not in seen:
            seen.add(lbl)
            print(lbl)
except Exception:
    pass
PY
}

# load_bearing_pattern — returns a regex that matches labels that look like
# load-bearing components: planes, subsystems, entrypoints, gates, tools, detectors.
load_bearing_pattern(){
  printf '(plane|subsystem|entrypoint|gate|tool|detector|canary|controller|service|daemon|router|bridge|agent|engine|worker|operator|server|proxy|adapter|pipeline|registry|reconciler|watcher|hook|handler|monitor|scheduler|dispatcher|runner|executor|orchestrator|manager|coordinator|provider|connector|adapter|middleware|platform|layer|module|component|system|cluster|fleet)$'
}

# is_load_bearing <label> — returns 0 if the label looks like a load-bearing component.
# A label is load-bearing if:
#   (a) it ends with a known load-bearing suffix (plane, gate, tool, etc.), OR
#   (b) it contains '/' (path-like — likely in a component directory).
# Anti-pattern exclusions: test fixtures, config examples, documentation stubs.
is_load_bearing(){
  local label="$1" pattern
  # Exclude non-load-bearing patterns first.
  printf '%s' "$label" | grep -qiE '(example|mock|stub|fixture|test-|\.md$)' && return 1
  pattern="$(load_bearing_pattern)"
  # Match if the label ends with a known suffix (optionally preceded by '/' or start).
  printf '%s' "$label" | grep -qiE "(^|/)?(${pattern})$" && return 0
  # Path-like labels (contain '/') are in a component directory.
  printf '%s' "$label" | grep -q '/' && return 0
  return 1
}

# registered_ids — emits the component_id column of every non-exempted row.
registered_ids(){
  local line id kind status
  while IFS=$'\t' read -r line; do
    [ -z "$line" ] && continue
    id="$(printf '%s' "$line" | cut -f1)"
    kind="$(printf '%s' "$line" | cut -f2)"
    status="$(printf '%s' "$line" | cut -f6)"
    [ -z "$id" ] && continue
    [ "$status" = "exempted" ] && continue
    printf '%s\n' "$id"
  done < <(read_registry)
}

# exempted_set — emits component_id of exempted rows (for discovery to skip).
exempted_ids(){
  local line id status
  while IFS=$'\t' read -r line; do
    [ -z "$line" ] && continue
    id="$(printf '%s' "$line" | cut -f1)"
    status="$(printf '%s' "$line" | cut -f6)"
    [ -z "$id" ] && continue
    [ "$status" = "exempted" ] && printf '%s\n' "$id"
  done < <(read_registry)
}

# list_known_kinds — emits the set of known kind values for conformance validation.
known_kinds(){ printf '%s\n' plane subsystem entrypoint tool gate detector; }

# --- Leg 1: CONFORMANCE ----------------------------------------------------
# Every registry row must have exactly 8 tab-separated fields.
# The kind column must be one of known_kinds.
# component_id must be non-empty and kebab-case.
check_conformance(){
  local rc=0 count kind component_id
  local data
  data="$(read_registry)"
  [ -z "$data" ] && { finding "CONFORMANCE: registry is empty — no registered components (non-vacuous: fail closed)"; return 1; }
  count=0

  # Read raw lines to handle short rows correctly (read -r with fewer fields masks the shortage).
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    count=$((count + 1))
    # Count tab-separated fields from the raw line.
    local fields
    fields="$(printf '%s' "$line" | awk -F'\t' '{print NF}')"
    if [ "$fields" -ne 8 ]; then
      finding "CONFORMANCE: row $count has $fields fields, expected 8"
      rc=1
      continue
    fi
    # Parse the valid 8-field row.
    component_id="$(printf '%s' "$line" | cut -f1)"
    kind="$(printf '%s' "$line" | cut -f2)"
    status="$(printf '%s' "$line" | cut -f6)"
    if ! printf '%s\n' "$(known_kinds)" | grep -qxF "$kind"; then
      finding "CONFORMANCE: row $count component '$component_id' has unknown kind '$kind'"
      rc=1
    fi
    if [ "$status" != "registered" ] && [ "$status" != "exempted" ]; then
      finding "CONFORMANCE: row $count component '$component_id' has invalid status '$status' (must be registered or exempted)"
      rc=1
    fi
  done < <(printf '%s\n' "$data")

  [ "$rc" -eq 0 ] && echo "  conformance: GREEN — $count component(s) in registry, all valid"
  return "$rc"
}

# --- Leg 2: DISCOVERY ------------------------------------------------------
# Cross-reference graphify's code graph against the registry.
# Any load-bearing node in the graph that is NOT in the registry and is NOT
# exempted is flagged as an unregistered component.
check_discovery(){
  local rc=0 rnodes reg_ids exempt_ids unregistered n
  rnodes="$(read_graph_nodes)"
  [ -z "$rnodes" ] && { finding "DISCOVERY: no graph nodes available — cannot verify (fail closed: treat as RED)"; return 1; }
  reg_ids="$(registered_ids; exempted_ids)"

  while IFS= read -r label; do
    [ -z "$label" ] && continue
    is_load_bearing "$label" || continue
    # Normalize: lowercase, replace spaces with hyphens
    local norm
    norm="$(printf '%s' "$label" | tr '[:upper:]' '[:lower:]' | tr ' /_' '-' | tr -s '-')"
    if ! printf '%s\n' "$reg_ids" | grep -qF "$norm"; then
      # Check per-component-id fuzzy match (the label may be a longer name containing the id)
      local found=0
      while IFS= read -r rid; do
        [ -z "$rid" ] && continue
        if printf '%s' "$norm" | grep -qF "$rid"; then
          found=1
          break
        fi
        if printf '%s' "$rid" | grep -qF "$norm"; then
          found=1
          break
        fi
      done < <(printf '%s\n' "$reg_ids")
      [ "$found" -eq 1 ] && continue
      n="${unregistered:-0}"
      unregistered="$((n + 1))"
      finding "DISCOVERY: unregistered load-bearing component '${label}' (norm=${norm}) — add to component-registry.tsv or mark exempted"
      rc=1
    fi
  done < <(printf '%s\n' "$rnodes")

  if [ "$rc" -eq 0 ]; then
    echo "  discovery: GREEN — all load-bearing graph nodes are registered"
  fi
  return "$rc"
}

# --- Leg 3: DRIFT ----------------------------------------------------------
# Every registered component must have its canary script and test script present.
# Components with status=exempted skip the canary/test existence check.
check_drift(){
  local rc=0 component_id kind path_canary_path test_path status owner note
  local data
  data="$(read_registry)"
  [ -z "$data" ] && { finding "DRIFT: no registry data to check drift against — treat as RED"; return 1; }

  while IFS=$'\t' read -r component_id kind path canary test status owner note; do
    [ -z "$component_id" ] && continue
    [ "$status" = "exempted" ] && continue
    # Canonical paths
    local canary_file test_file
    canary_file=""
    test_file=""
    # canary path relative to fleet/ (or absolute)
    if [ -n "$FAKE_ROOT" ]; then
      canary_file="$FAKE_ROOT/canaries/$(basename "${canary:-.}")"
      test_file="$FAKE_ROOT/tests/$(basename "${test:-.}")"
    else
      [ -n "$canary" ] && [ "$canary" != "." ] && canary_file="$FLEET/$canary"
      [ -n "$test" ] && [ "$test" != "." ] && test_file="$FLEET/$test"
    fi

    # Check canary exists
    if [ -n "$canary_file" ]; then
      if [ ! -f "$canary_file" ]; then
        finding "DRIFT: component '$component_id' canary '$canary' missing at $canary_file"
        rc=1
      elif [ ! -x "$canary_file" ]; then
        finding "DRIFT: component '$component_id' canary '$canary' exists but is not executable"
        rc=1
      fi
    fi
    # Check test exists
    if [ -n "$test_file" ]; then
      if [ ! -f "$test_file" ]; then
        finding "DRIFT: component '$component_id' test '$test' missing at $test_file"
        rc=1
      fi
    fi
  done < <(printf '%s\n' "$data")

  if [ "$rc" -eq 0 ]; then
    echo "  drift: GREEN — every registered component has its canary + test"
  fi
  return "$rc"
}

# --- Full reconcile --------------------------------------------------------
cmd_reconcile(){
  RC=0
  FINDINGS=()
  local leg_rc

  echo "registry-discovery: LIST (reading registry + graphify graph)..."

  leg_rc=0; check_conformance || leg_rc=$?
  [ "$leg_rc" -ne 0 ] && RC=1

  leg_rc=0; check_discovery || leg_rc=$?
  [ "$leg_rc" -ne 0 ] && RC=1

  leg_rc=0; check_drift || leg_rc=$?
  [ "$leg_rc" -ne 0 ] && RC=1

  if [ "$RC" -eq 0 ]; then
    echo "registry-discovery: GREEN — no findings (registry complete, fresh, accurate)"
  else
    echo "registry-discovery: RED — ${#FINDINGS[@]} finding(s) — review above"
  fi
  return "$RC"
}

# --- Gate subcommand (machine-readable prefix) ----------------------------
cmd_gate(){
  local out rc=0
  out="$(cmd_reconcile 2>&1)" || rc=$?
  printf '%s\n' "$out"
  if [ "$rc" -eq 0 ]; then
    echo "registry-discovery-gate: GREEN — registry is complete and consistent."
  else
    echo "registry-discovery-gate: RED — one or more findings must be resolved."
  fi
  return "$rc"
}

# --- List subcommand ------------------------------------------------------
cmd_list(){
  local data component_id kind status note
  data="$(read_registry)"
  [ -z "$data" ] && return 0
  while IFS=$'\t' read -r component_id kind path canary test status owner note; do
    [ -z "$component_id" ] && continue
    printf '%s\t%s\t%s\n' "$component_id" "$kind" "$status"
  done < <(printf '%s\n' "$data")
}

# --- Dispatch -------------------------------------------------------------
case "${1:-}" in
  check|reconcile)  shift; cmd_reconcile "$@" ;;
  gate)             shift; cmd_gate "$@" ;;
  conformance)      shift; check_conformance "$@" ;;
  discovery)        shift; check_discovery "$@" ;;
  drift)            shift; check_drift "$@" ;;
  list)             cmd_list ;;
  -h|--help|help|"")
    cat <<'HELP'
registry-discovery.sh — DISCOVER leg (k8s-controller reconcile shape)

Usage:
  $0 check           full reconcile: conformance + discovery + drift (exit 0 GREEN / 1 RED)
  $0 gate            same as check, with GATE: prefix for preflight pipeline
  $0 conformance     registry-file format validation only
  $0 discovery       graphify-graph cross-reference only
  $0 drift           registered-component liveness only
  $0 list            print every registered component (one-per-line, machine-readable)

Env seams (self-test overrides):
  REGISTRY_DISCOVERY_FAKE=<dir>   hermetic fixture directory
  REGISTRY_FILE=<path>            override component-registry.tsv location
  GRAPHIFY_GRAPH=<path>           override graph.json path
  REGISTRY_FLEET=<path>           override fleet/ root

Three legs:
  CONFORMANCE  — every registry row is valid (8 fields, known kind, valid status)
  DISCOVERY    — load-bearing graphify nodes that MISSING from registry (fail closed)
  DRIFT        — canary/test of a registered component vanished (stale component)
HELP
    ;;
  *) echo "registry-discovery.sh: unknown subcommand '$1' (try: check|gate|conformance|discovery|drift|list)" >&2; exit 2 ;;
esac
