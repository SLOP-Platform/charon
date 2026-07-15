#!/usr/bin/env bash
# config-drift.sh — DETECTION + VISIBILITY for provider/model config SILOED across sources.
#
# THE PROBLEM (operator directive): provider/model config lives in multiple places and drifts
# INVISIBLY. A session adds a provider (e.g. NVIDIA NIM) into ONE source and it strands there
# unseen — the operator is BLIND to the divergence. Today the sources are the LOCAL CLI config
# (~/.charon) and the 4-LOM CG deploy (docker container volume /data).
#
# WHAT THIS DOES: reads every source in fleet/state/CONFIG-SOURCES.tsv (a REGISTRY — add a deploy
# = add a row, no code change), enumerates each source's providers (name -> base_url, key_env) and
# model count, and RECONCILES them into a table that flags every DRIFT:
#   - a provider present in one source but ABSENT in another
#   - a base_url mismatch across sources
#   - a key_env mismatch across sources
# Plus a models summary (count per source + models unique to one source).
#
# READ-ONLY: NEVER writes to any source. SECRETS: compares key_env NAMES only — providers.json
# carries names, never values; secrets.json is never touched.
#
# GRACEFUL DEGRADE: a source that is unreachable (ssh/docker down, bad JSON) is reported as its own
# UNREACHABLE state and named — it is NOT treated as "in sync" (an unreachable 4-LOM must never
# false-GREEN). One dead source WARNs; it does not crash the whole run.
#
# EXIT: 0 only when every source is reachable AND drift == 0. Non-zero on drift OR any unreachable
# source (so it can GATE). With --advisory it always exits 0 (print + count only, for session boot).
#
# Usage:
#   fleet/config-drift.sh              # full reconcile table; exit non-zero on drift/unreachable
#   fleet/config-drift.sh --advisory   # same output, always exit 0 (wired into preflight boot)
#
# Test hook: CONFIG_SOURCES_TSV=<file> overrides the registry (fleet/tests/config-drift.test.sh).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TSV="${CONFIG_SOURCES_TSV:-$HERE/state/CONFIG-SOURCES.tsv}"
TAB=$'\t'

ADVISORY=0
case "${1:-}" in
  --advisory) ADVISORY=1 ;;
  "" ) ;;
  * ) echo "usage: config-drift.sh [--advisory]" >&2; exit 3 ;;
esac

[ -f "$TSV" ] || { echo "config-drift: registry not found: $TSV" >&2; exit 3; }
command -v python3 >/dev/null 2>&1 || { echo "config-drift: python3 not found — cannot reconcile JSON" >&2; exit 3; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
MANIFEST="$WORK/manifest.tsv"; : > "$MANIFEST"

# fetch <read-cmd-template> <filename>: substitute {} -> filename, run READ-ONLY via timeout bash -c.
fetch(){
  local tmpl="$1" file="$2" cmd
  cmd="${tmpl//\{\}/$file}"
  timeout 15 bash -c "$cmd" 2>/dev/null
}
valid_json(){ python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$1" 2>/dev/null; }

echo "== CONFIG DRIFT — reconciling provider/model config across sources ($TSV) =="

# note (4th column) is documentation-only here; read to consume the rest of the row.
# shellcheck disable=SC2034
while IFS="$TAB" read -r sid kind rcmd note; do
  case "$sid" in \#*|"") continue ;; esac
  pfile="$WORK/$sid.providers.json"; mfile="$WORK/$sid.models.json"
  reachable=1
  fetch "$rcmd" providers.json > "$pfile" 2>/dev/null || true
  if [ ! -s "$pfile" ] || ! valid_json "$pfile"; then
    reachable=0
    echo "  WARN: source '$sid' ($kind) UNREACHABLE — could not read a valid providers.json (state=unknown, NOT in-sync)"
  fi
  # models.json is best-effort; an unreadable/invalid one just yields a 0/unknown model count.
  fetch "$rcmd" models.json > "$mfile" 2>/dev/null || true
  { [ -s "$mfile" ] && valid_json "$mfile"; } || : > "$mfile"
  printf '%s\t%s\t%s\t%s\n' "$sid" "$reachable" "$pfile" "$mfile" >> "$MANIFEST"
done < "$TSV"

python3 - "$MANIFEST" <<'PY'
import json, sys, os

manifest = sys.argv[1]
sources = []   # (sid, reachable, providers_dict|None, model_keys|set|None)
for line in open(manifest):
    line = line.rstrip("\n")
    if not line:
        continue
    sid, reach, pfile, mfile = line.split("\t")
    reachable = reach == "1"
    providers = None
    if reachable:
        try:
            providers = json.load(open(pfile))
            if not isinstance(providers, dict):
                providers = {}
        except Exception:
            providers, reachable = None, False
    models = None
    if os.path.getsize(mfile) > 0:
        try:
            m = json.load(open(mfile))
            models = set(m.keys()) if isinstance(m, dict) else set(m)
        except Exception:
            models = None
    sources.append((sid, reachable, providers, models))

reach_sources = [s for s in sources if s[1]]
unreach = [s[0] for s in sources if not s[1]]
sids = [s[0] for s in sources]

def cell(v):  # normalize a base_url/key_env value for display + compare
    return (v or "").strip()

# ---- provider reconcile ----
all_names = set()
for _, ok, prov, _ in reach_sources:
    all_names.update(prov.keys())

drift = 0
rows = []
for name in sorted(all_names):
    present = {}   # sid -> (base_url, key_env)
    for sid, ok, prov, _ in reach_sources:
        if name in prov:
            e = prov[name] or {}
            present[sid] = (cell(e.get("base_url")), cell(e.get("key_env")))
    in_cols = []
    for sid, ok, prov, _ in sources:
        if not ok:
            in_cols.append("?")
        else:
            in_cols.append("yes" if name in prov else "NO")
    # match cols only meaningful when >=2 reachable sources HAVE this provider
    have = list(present.values())
    if len(have) >= 2:
        bu = "yes" if len({b for b, k in have}) == 1 else "NO"
        ke = "yes" if len({k for b, k in have}) == 1 else "NO"
    else:
        bu = ke = "n/a"
    missing = len(reach_sources) >= 2 and len(present) < len(reach_sources)
    is_drift = missing or bu == "NO" or ke == "NO"
    if is_drift:
        drift += 1
    rows.append((name, in_cols, bu, ke, is_drift))

# ---- print table ----
hdr = ["provider"] + [f"in:{s}" for s in sids] + ["base_url?", "key_env?", ""]
namew = max([len(r[0]) for r in rows] + [len("provider")]) if rows else len("provider")
colw = [max(len(f"in:{s}"), 3) for s in sids]

def fmt(name, incols, bu, ke, flag):
    parts = [name.ljust(namew)]
    for c, w in zip(incols, colw):
        parts.append(c.center(w))
    parts.append(bu.center(9))
    parts.append(ke.center(8))
    parts.append(flag)
    return "  " + " | ".join(parts)

print()
print(fmt("provider", [f"in:{s}" for s in sids], "base_url?", "key_env?", ""))
print("  " + "-" * (namew + sum(colw) + 3 * len(colw) + 26))
if not rows:
    print("  (no providers found in any reachable source)")
for name, incols, bu, ke, is_drift in rows:
    print(fmt(name, incols, bu, ke, "<< DRIFT" if is_drift else ""))

# ---- models summary ----
print()
print("  models:")
for sid, ok, prov, models in sources:
    if not ok:
        print(f"    {sid}: UNREACHABLE (unknown)")
    elif models is None:
        print(f"    {sid}: providers OK but models.json unavailable/invalid (count unknown)")
    else:
        print(f"    {sid}: {len(models)} models")
# models unique to exactly one reachable source (notable-only-in-one)
modeled = [(s[0], s[3]) for s in reach_sources if s[3] is not None]
if len(modeled) >= 2:
    for sid, mset in modeled:
        others = set()
        for osid, oset in modeled:
            if osid != sid:
                others |= oset
        only = sorted(mset - others)
        if only:
            ex = ", ".join(only[:5]) + (f", +{len(only)-5} more" if len(only) > 5 else "")
            print(f"    only-in-{sid}: {len(only)} model(s) — {ex}")

# ---- verdict ----
print()
if len(reach_sources) < 2:
    print(f"  NOTE: only {len(reach_sources)} reachable source(s) — cross-source reconcile needs >= 2.")
print(f"DRIFT: {drift}")
print(f"UNREACHABLE: {len(unreach)}" + (f" ({', '.join(unreach)})" if unreach else ""))

# exit non-zero on drift OR any unreachable source (unreachable must not false-GREEN)
sys.exit(1 if (drift > 0 or unreach) else 0)
PY
rc=$?

echo "== end config-drift =="
[ "$ADVISORY" = 1 ] && exit 0
exit $rc
