#!/usr/bin/env bash
# config-ssot-gate.sh — REDS when any provider-config source diverges from the SSOT manifest.
#
# THE PROBLEM (operator directive, 2026-07-14): provider/model config lives in multiple sources
# and was drifting INVISIBLY. The local ~/.charon/providers.json (1 provider) was a STALE MIRROR
# of the 4-LOM gateway (11 providers) — the manager read the LOCAL view and concluded a "thin
# pool" existed, which was WRONG. The drift was the artifact, not reality.
#
# THE FIX (this script): the git-tracked MANIFEST (fleet/config-manifest.tsv) is now the SSOT.
# Every other source (LOCAL ~/.charon, the 4-LOM gateway /data volume) is a CACHED MIRROR. The gate
# REDs when any source diverges from the manifest — naming the drift AND the fix command.
#
# DRIFT CLASSES (each is a separate row in the report):
#   - MISSING-LOCALLY: manifest declares <P> but local ~/.charon/providers.json has no row for <P>.
#   - MISSING-ON-GATEWAY: manifest declares <P> but the 4-LOM gateway /data/providers.json has no row.
#   - BASE-URL MISMATCH: manifest's base_url for <P> differs from the source's base_url.
#   - KEY-ENV MISMATCH: manifest's key_env for <P> differs from the source's key_env.
#   - UNEXPECTED-LOCAL: source declares <P> but the manifest does NOT (orphaned; possibly a stale
#     local entry from a removed provider — flag and let the operator decide).
#   - UNREACHABLE: a source's read-cmd failed / no valid providers.json (must not false-GREEN;
#     an unreachable 4-LOM is always a HARD RED, not a satisfied source).
#
# EXIT: 0 = every source is reachable AND matches the manifest. Non-zero on ANY drift OR an
# unreachable source (so this script can GATE).
#
# WIRING (stated honestly — the previous text here was FALSE). This script claimed to be "Wired
# into validate_board.sh as an advisory (auto-runs on every preflight)". validate_board.sh has
# ZERO references to it and it does NOT auto-run on preflight. The claim was caught by
# fleet/checks/gate-integrity.sh (G2 FALSE-CLAIM) on 2026-07-19 and corrected rather than
# quietly left, because a false wiring claim is worse than no claim: a reader greps the header,
# sees wiring, and stops looking. Actual caller: fleet/config-sync.sh. Wiring it into preflight
# is a real change with its own blast radius and is NOT done here.
#
# USAGE:  fleet/config-ssot-gate.sh
#         fleet/config-ssot-gate.sh --advisory    # same output, always exit 0 (advisory mode)
#         fleet/config-ssot-gate.sh --report      # human-readable report, always exit 0
#
# Test hook: CONFIG_MANIFEST_TSV=<file> overrides the SSOT (fleet/tests/config-ssot.test.sh).
#
# SAFE: this script is READ-ONLY by default. It never writes to any source. The companion
# `config-sync.sh` is the write path (propagates manifest -> sources) and is gated behind an
# explicit operator invocation. An unreachable source is HARD-RED here, never silently
# satisfied (a stuck 4-LOM must not false-GREEN — that is the EXACT bug this gate exists to
# close).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Manifest path: git SSOT (env-overridable for tests; default is the committed file).
MANIFEST="${CONFIG_MANIFEST_TSV:-$HERE/config-manifest.tsv}"

# LOCAL source: the operator's own ~/.charon/providers.json. Override with CHARON_LOCAL_CONFIG
# (or CHARON_LOCAL_PROVIDERS / CHARON_LOCAL_SECRETS) for hermetic testing.
LOCAL_PROVIDERS="${CHARON_LOCAL_PROVIDERS:-${CHARON_LOCAL_CONFIG:-$HOME/.charon/providers.json}}"
LOCAL_SECRETS="${CHARON_LOCAL_SECRETS:-$HOME/.charon/secrets.json}"

# GATEWAY source: the 4-LOM CG deploy, /data/providers.json on container charon-gateway-1.
# Read-cmd is a docker exec cat; overridable for tests. The read-cmd template substitutes {} ->
# the file path. Production default substitutes the basename into /data; tests pass a full path
# via GATEWAY_PROVIDERS_PATH. We assign the default with a separate [ -z ] check (NOT a
# ${VAR:-default} expansion with `{}` in the default) — bash's parser eats the `{}` in the
# default as if it were a nested parameter expansion and the resulting default has an extra `}`.
GATEWAY_PATH="${GATEWAY_PROVIDERS_PATH:-providers.json}"
if [ -n "${GATEWAY_PROVIDERS_RCMD:-}" ]; then
  GATEWAY_RCMD="$GATEWAY_PROVIDERS_RCMD"
else
  GATEWAY_RCMD='docker exec -i charon-gateway-1 cat /data/{}'
fi

ADVISORY=0
REPORT=0
case "${1:-}" in
  --advisory) ADVISORY=1 ;;
  --report)   REPORT=1 ;;
  "")         ;;
  *) echo "usage: config-ssot-gate.sh [--advisory|--report]" >&2; exit 3 ;;
esac

[ -f "$MANIFEST" ] || { echo "config-ssot-gate: manifest not found: $MANIFEST" >&2; exit 3; }
command -v python3 >/dev/null 2>&1 || { echo "config-ssot-gate: python3 not found — cannot compare JSON" >&2; exit 3; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# load_manifest <manifest.tsv> <out.json>: parses the 5-column TSV into a JSON object on stdout.
# Tolerates comment lines (leading '#') and blank rows. Strips whitespace from each field. A
# malformed row (NF != 5) is a HARD ERROR — the manifest is SSOT and must be well-formed.
load_manifest() {
  python3 - "$1" "$2" <<'PY'
import json, sys
tsv, out = sys.argv[1], sys.argv[2]
prov = {}
with open(tsv) as f:
    for ln, raw in enumerate(f, 1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # TSV-aware split: a manual split is wrong if a field legitimately contains a tab. We
        # treat the manifest as a strict 5-column TSV (operator policy: do not embed tabs in
        # any column; verified by the header row below).
        parts = line.split("\t")
        if len(parts) != 5:
            sys.exit(f"config-ssot-gate: manifest {tsv}:{ln} malformed (expected 5 tab-separated fields, got {len(parts)}): {line!r}")
        name, key, url, tiers, note = (p.strip() for p in parts)
        if not name:
            sys.exit(f"config-ssot-gate: manifest {tsv}:{ln} has empty provider name")
        prov[name] = {"key_env": key, "base_url": url, "tiers": tiers, "note": note}
# Header-line check: if the FIRST non-blank/non-comment line is the literal 'provider\t...' we
# skip it. This is the documented header; we tolerate it being there because every editor's
# default-mode for TSVs is to add one.
items = list(prov.items())
if items and items[0][0] == "provider":
    prov.pop("provider", None)
json.dump(prov, open(out, "w"))
PY
}

# fetch_source <label> <path> <read-cmd-template> <out-providers.json> <out-meta>: writes the
# providers.json content to <out-providers.json> (empty on failure) and a meta line to <out-meta>:
#   "REACHABLE <label> <path>"  on success (valid JSON, parseable)
#   "UNREACHABLE <label> <path> <reason>"  on failure (network/read/parse error)
# Treats an UNREACHABLE source as a HARD RED, never as an in-sync source.
fetch_source() {
  local label="$1" path="$2" rcmd="$3" out="$4" meta="$5" raw
  raw="$(timeout 15 bash -c "${rcmd//\{\}/$path}" 2>/dev/null || true)"
  if [ -z "$raw" ] || ! printf '%s' "$raw" | python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1; then
    printf 'UNREACHABLE %s %s %s\n' "$label" "$path" "no valid JSON" > "$meta"
    : > "$out"
    return 1
  fi
  printf '%s' "$raw" > "$out"
  printf 'REACHABLE %s %s\n' "$label" "$path" > "$meta"
  return 0
}

# fetch_local_secrets: a separate, best-effort read of LOCAL secrets.json. We only compare
# key_env NAMES (never values) — a source whose key_env name is on the manifest but whose
# value is missing in secrets.json is a separate, operator-acted drift class (key-rotation
# gap) and is out of scope for THIS gate (the SYNC tool surfaces it).
fetch_local_secrets() {
  [ -f "$LOCAL_SECRETS" ] || return 1
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert isinstance(d,dict); sys.stdout.write(json.dumps(sorted(d.keys())))' "$LOCAL_SECRETS" 2>/dev/null
}

echo "== CONFIG SSOT GATE — reconciling sources vs manifest =="
echo "  manifest: $MANIFEST"
echo "  local:    $LOCAL_PROVIDERS"
echo "  gateway:  (4-LOM charon-gateway-1 /data)"

MANIFEST_JSON="$WORK/manifest.json"
load_manifest "$MANIFEST" "$MANIFEST_JSON" || { echo "config-ssot-gate: failed to parse manifest (run `awk -F'\t' 'NF!=5' $MANIFEST` to see malformed rows)" >&2; exit 3; }

LOCAL_PROV_JSON="$WORK/local.providers.json"
LOCAL_META="$WORK/local.meta"
fetch_source "local" "$LOCAL_PROVIDERS" "cat {}" "$LOCAL_PROV_JSON" "$LOCAL_META"
LOCAL_REACH=$?
LOCAL_SECRETS_KEYS="$(fetch_local_secrets || true)"

GATEWAY_PROV_JSON="$WORK/gateway.providers.json"
GATEWAY_META="$WORK/gateway.meta"
fetch_source "gateway" "$GATEWAY_PATH" "$GATEWAY_RCMD" "$GATEWAY_PROV_JSON" "$GATEWAY_META"
GATEWAY_REACH=$?

python3 - "$MANIFEST_JSON" "$LOCAL_PROV_JSON" "$LOCAL_META" "$GATEWAY_PROV_JSON" "$GATEWAY_META" \
               "$LOCAL_SECRETS_KEYS" <<'PY'
import json, sys, os
GATE_RC = 0
manifest_json, local_p, local_meta, gw_p, gw_meta, local_secret_keys = sys.argv[1:7]
manifest = json.load(open(manifest_json))  # {name: {key_env, base_url, tiers, note}}
def meta_status(p):
    if not os.path.exists(p): return ("UNKNOWN", "", "")
    line = open(p).read().strip()
    parts = line.split(None, 3)
    if not parts: return ("UNKNOWN", "", "")
    return (parts[0], parts[1] if len(parts) > 1 else "",
            " ".join(parts[3:]) if len(parts) > 3 else "")

def safe_load(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return {}
    try:
        d = json.load(open(path))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

local_status, local_label, local_path = meta_status(local_meta)
local_provs = safe_load(local_p)
gw_status, gw_label, gw_path = meta_status(gw_meta)
gw_provs = safe_load(gw_p)

manifest_names = set(manifest.keys())
local_names = set(local_provs.keys())
gw_names = set(gw_provs.keys())

drift = []
unreach = []

# (1) manifest vs local
for name in sorted(manifest_names - local_names):
    drift.append(("MISSING-LOCALLY", name, "",
                  f"manifest declares '{name}' (key_env={manifest[name].get('key_env','')}); run: fleet/config-sync.sh"))
for name in sorted(local_names - manifest_names):
    drift.append(("UNEXPECTED-LOCAL", name, local_provs[name].get("key_env", ""),
                  f"local ~/.charon has '{name}' but manifest does NOT — remove from local or add to manifest (sync will overwrite)"))
# (1b) shared names: base_url + key_env parity
for name in sorted(manifest_names & local_names):
    m = manifest[name]; s = local_provs[name] or {}
    murl = (m.get("base_url") or "").strip()
    surl = (s.get("base_url") or "").strip()
    mkey = (m.get("key_env") or "").strip()
    skey = (s.get("key_env") or "").strip()
    if murl and surl and murl != surl:
        drift.append(("BASE-URL MISMATCH", name, mkey,
                      f"manifest base_url={murl!r} but local base_url={surl!r} — run: fleet/config-sync.sh"))
    if mkey and skey and mkey != skey:
        drift.append(("KEY-ENV MISMATCH", name, mkey,
                      f"manifest key_env={mkey!r} but local key_env={skey!r} — run: fleet/config-sync.sh"))

# (2) manifest vs gateway — only if gateway is REACHABLE. An unreachable gateway is its own
# HARD-RED state, not a synthetic "missing" claim (we cannot prove missing without reading).
if gw_status == "REACHABLE":
    for name in sorted(manifest_names - gw_names):
        drift.append(("MISSING-ON-GATEWAY", name, "",
                      f"manifest declares '{name}' (key_env={manifest[name].get('key_env','')}); gateway /data/providers.json has no row — re-sync (operator: this is the WRITE-PATH to the live 4-LOM; gated on operator decision per ticket note)"))
    for name in sorted(gw_names - manifest_names):
        drift.append(("UNEXPECTED-ON-GATEWAY", name, gw_provs[name].get("key_env", ""),
                      f"gateway has '{name}' but manifest does NOT — add to manifest or remove from gateway (sync will overwrite)"))
    for name in sorted(manifest_names & gw_names):
        m = manifest[name]; s = gw_provs[name] or {}
        murl = (m.get("base_url") or "").strip()
        surl = (s.get("base_url") or "").strip()
        mkey = (m.get("key_env") or "").strip()
        skey = (s.get("key_env") or "").strip()
        if murl and surl and murl != surl:
            drift.append(("BASE-URL MISMATCH", name, mkey,
                          f"manifest base_url={murl!r} but gateway base_url={surl!r} — re-sync (live 4-LOM WRITE-PATH; gated on operator decision)"))
        if mkey and skey and mkey != skey:
            drift.append(("KEY-ENV MISMATCH", name, mkey,
                          f"manifest key_env={mkey!r} but gateway key_env={skey!r} — re-sync (live 4-LOM WRITE-PATH; gated on operator decision)"))

# (3) unreachable source = HARD RED (must not false-GREEN; the exact bug this gate closes).
if local_status == "UNREACHABLE":
    unreach.append(("local", local_path, "read-failed or invalid JSON"))
if gw_status == "UNREACHABLE":
    unreach.append(("gateway", gw_path, "read-failed or invalid JSON"))

# ---- report ----
print()
print(f"  manifest:   {len(manifest_names)} provider(s)")
if local_status == "REACHABLE":
    print(f"  local:      {len(local_names)} provider(s) (reachable)")
else:
    print(f"  local:      UNREACHABLE — {local_path} ({meta_status(local_meta)[2]})")
if gw_status == "REACHABLE":
    print(f"  gateway:    {len(gw_names)} provider(s) (reachable)")
else:
    print(f"  gateway:    UNREACHABLE — {gw_path} ({meta_status(gw_meta)[2]})")
print()
print(f"  DRIFT ({len(drift)}):")
if not drift:
    print("    (none — every source is in sync with the manifest)")
for cls, name, key, fix in drift:
    line = f"    {cls:<22} {name}"
    if key: line += f" (key_env={key})"
    print(line)
    print(f"      -> fix: {fix}")
print()
print(f"  UNREACHABLE ({len(unreach)}):")
if not unreach:
    print("    (none)")
for src, path, reason in unreach:
    print(f"    {src}: {path} — {reason}")

# Verdict
if unreach or drift:
    GATE_RC = 1
print()
if GATE_RC:
    print(f"SSOT-GATE: RED — {len(drift)} drift, {len(unreach)} unreachable")
else:
    print("SSOT-GATE: GREEN — every source matches the manifest")
sys.exit(GATE_RC)
PY
GATE_RC=$?

echo "== end config-ssot-gate =="
if [ "$ADVISORY" = 1 ] || [ "$REPORT" = 1 ]; then exit 0; fi
exit "$GATE_RC"
