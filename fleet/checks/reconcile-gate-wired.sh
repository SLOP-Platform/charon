#!/usr/bin/env bash
# reconcile-gate-wired.sh — META-GATE: detects built-but-inert checks
# (checks declared in the desired-source that never fire from any actual firing layer).
#
# Design: UNIFIED-RECONCILIATION-GATE-DESIGN.md $1.3 (PR #178, RANK-0 LEAD).
# drift-primitive: graph-reachability (KS29 leg) — declared nodes MUST be reachable
# from the firing-layer root. stass-allie WLS-7 validation: implement-as-pattern is
# the sanctioned hand-roll (K8s/Terraform desired-vs-observed, ported to the rig).
#
# desired-source = every gate/check/rule declared in:
#   fleet/checks/*.sh + *.py (rig check suite)
#   tools/check_*.py + *.sh (product check suite, cross-repo)
#   RULE-REGISTRY.tsv rows with classification=mechanized
#   EVAL-REGISTRY.md rows with verdict=ADOPT + evidence-link pointing at a check path
#
# actual-source  = the set of check invocations found in firing-layer sources:
#   Rig:  preflight.sh:841 scan dispatch (board_gate, executor_gate, coverage_gate,
#         handoff_gate, done_merge_gate, cmd_detect -> stranded-work, foreman_advisory)
#         land.sh pre-conditions, validate_board.sh, hooks/session-start.sh,
#         foreman-cadence.sh
#   Product: gate_runner.py CHECKS list, .github/workflows/*.yml (cross-repo)
#
# set-diff:
#   R-G (declared but NOT fired -> built-but-inert RED)
#   R-H (fired but NOT declared -> running-but-unregistered RED)
#
# Product-repo-absent: reports UNVERIFIED for the product axis (fail-closed).
#
# Exit 0 = GREEN (all declared checks wired; no unregistered runners; product verified).
# Exit 1 = RED or UNVERIFIED (product-repo absent -> fail-closed, NEVER false-GREEN).
# Exit 2 = usage error.
#
# Self-test seams (env overrides, same pattern as rule-coverage.sh):
#   RCW_FLEET            fleet root directory
#   RCW_PRODUCT_REPO     product repo root (default: /home/stack/code/charon)
#   RCW_REGISTRY         RULE-REGISTRY.tsv path
#   RCW_EVAL_REGISTRY    EVAL-REGISTRY.md path
#   RCW_EXTRA_DECLARED   colon-separated extra dirs to scan for declared checks
#   RCW_EXTRA_FIRING     colon-separated extra firing-layer files to parse
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export RCW_FLEET="${RCW_FLEET:-$FLEET}"
export RCW_PRODUCT_REPO="${RCW_PRODUCT_REPO-/home/stack/code/charon}"
export RCW_REGISTRY="${RCW_REGISTRY:-$FLEET/state/RULE-REGISTRY.tsv}"
export RCW_EVAL_REGISTRY="${RCW_EVAL_REGISTRY:-$FLEET/state/EVAL-REGISTRY.md}"
export RCW_EXTRA_DECLARED="${RCW_EXTRA_DECLARED:-}"
export RCW_EXTRA_FIRING="${RCW_EXTRA_FIRING:-}"

python3 - <<'PY'
import os, sys, glob, re

FLEET = os.environ["RCW_FLEET"]
PRODUCT_REPO = os.environ.get("RCW_PRODUCT_REPO", "") or ""
REGISTRY_PATH = os.environ["RCW_REGISTRY"]
EVAL_PATH = os.environ["RCW_EVAL_REGISTRY"]
EXTRA_DECLARED = os.environ.get("RCW_EXTRA_DECLARED", "").strip()
EXTRA_FIRING = os.environ.get("RCW_EXTRA_FIRING", "").strip()

product_available = bool(PRODUCT_REPO) and os.path.isdir(PRODUCT_REPO)

# Known aliases: a wrapper script's canonical basename may appear in firing layers
# under a shorter name (e.g. gitleaks.sh -> "gitleaks").
ALIASES = {
    "gitleaks": "gitleaks.sh",
}

# ===== STEP 1: Collect declared checks =====
declared = {}  # basename -> (path, source_label)

# 1a. fleet/checks/*.sh + *.py (the rig check suite)
for ext in ("*.sh", "*.py"):
    for f in sorted(glob.glob(os.path.join(FLEET, "checks", ext))):
        bn = os.path.basename(f)
        if bn not in declared:
            declared[bn] = (f, f"fleet/checks/{bn}")

# 1b. Extra declared dirs (test seams — inject fixture checks)
if EXTRA_DECLARED:
    for d in EXTRA_DECLARED.split(":"):
        d = d.strip()
        if not d or not os.path.isdir(d):
            continue
        for ext in ("*.sh", "*.py"):
            for f in sorted(glob.glob(os.path.join(d, ext))):
                bn = os.path.basename(f)
                if bn not in declared:
                    rel = os.path.relpath(f, FLEET) if f.startswith(FLEET) else f
                    declared[bn] = (f, f"extra:{rel}")

# 1c. Product tools/check_*.py + *.sh (cross-repo, if available)
if product_available:
    tools_dir = os.path.join(PRODUCT_REPO, "tools")
    if os.path.isdir(tools_dir):
        for ext in ("check_*.py", "check_*.sh"):
            for f in sorted(glob.glob(os.path.join(tools_dir, ext))):
                bn = os.path.basename(f)
                if bn not in declared:
                    declared[bn] = (f, f"product:tools/{bn}")

# 1d. RULE-REGISTRY.tsv mechanized rows (enforcing_ref points at artifact)
if os.path.isfile(REGISTRY_PATH):
    for line in open(REGISTRY_PATH, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        cls = parts[3].strip()
        if cls != "mechanized":
            continue
        ref = parts[4].strip()
        path_spec = ref.split("::")[0].strip()
        if not path_spec:
            continue
        bn = os.path.basename(path_spec)
        if bn not in declared:
            declared[bn] = (path_spec, f"RULE-REGISTRY:mechanized:{bn}")

# 1e. EVAL-REGISTRY.md ADOPT rows whose evidence-link points at a check path
if os.path.isfile(EVAL_PATH):
    for line in open(EVAL_PATH, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8:
            continue
        verdict = parts[4] if len(parts) > 4 else ""
        evidence = parts[7] if len(parts) > 7 else ""
        if not verdict.upper().startswith("ADOPT"):
            continue
        if not evidence or evidence in ("evidence-link", "—", "-", ""):
            continue
        for token in re.split(r'[,;]\s*', evidence):
            token = token.strip()
            # Only count actual check scripts (.sh/.py files), not deps files
            if not token.endswith((".sh", ".py")):
                continue
            if "checks/" in token or "check_" in token:
                bn = os.path.basename(token.rstrip(".:"))
                if bn and bn not in declared:
                    declared[bn] = (token, f"EVAL-REGISTRY:ADOPT:{bn}")

# ===== STEP 2: Build firing-layer file list =====
firing_layers = []

for fname in ["preflight.sh", "land.sh", "validate_board.sh",
              "hooks/session-start.sh", "foreman-cadence.sh"]:
    fpath = os.path.join(FLEET, fname)
    if os.path.isfile(fpath):
        firing_layers.append(fpath)

if product_available:
    gr_path = os.path.join(PRODUCT_REPO, "src", "charon", "gate_runner.py")
    if os.path.isfile(gr_path):
        firing_layers.append(gr_path)
    wf_dir = os.path.join(PRODUCT_REPO, ".github", "workflows")
    if os.path.isdir(wf_dir):
        for wf in sorted(glob.glob(os.path.join(wf_dir, "*.yml"))):
            firing_layers.append(wf)

if EXTRA_FIRING:
    for f in EXTRA_FIRING.split(":"):
        f = f.strip()
        if f and os.path.isfile(f):
            firing_layers.append(f)

# Remove duplicates (e.g. extra layer that matches a default)
seen = set()
unique_layers = []
for fl in firing_layers:
    if fl not in seen:
        seen.add(fl)
        unique_layers.append(fl)
firing_layers = unique_layers

# ===== STEP 3: Determine fired set =====
R_H_PATTERN = re.compile(
    r'/checks/([\w.-]+\.(?:sh|py))'
    r'|/(check_[\w.-]+\.(?:sh|py))'
)

fired = {}       # basename -> set of layer file basenames
fired_aliases = {}  # alias text -> set of layers

# Special invocations embedded in firing layers that use variable indirection
# e.g. "$HERE/checks/no-claude-executor.sh" or "$VALIDATE_BOARD"
# We match on the actual filename regardless of the variable wrapping.
DECLARED_BASENAMES = set(declared.keys())
KNOWN_OUTPUT_DIRS = {"checks/", "tools/"}

for fl in firing_layers:
    try:
        text = open(fl, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    layer_bn = os.path.basename(fl)

    # Direct substring match: declared basename appears anywhere in firing layer
    for bn in DECLARED_BASENAMES:
        if bn in text:
            fired.setdefault(bn, set()).add(layer_bn)

    # Alias resolution: a declared check's shorter alias appears in firing layer
    for alias, canonical in ALIASES.items():
        if alias in text and canonical in declared:
            fired.setdefault(canonical, set()).add(f"{layer_bn} (via alias '{alias}')")

# ===== STEP 4: Find unregistered invocations (R-H candidates) =====
unreg = {}  # basename -> set of layer file basenames

for fl in firing_layers:
    try:
        text = open(fl, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    layer_bn = os.path.basename(fl)

    for m in R_H_PATTERN.finditer(text):
        matched_bn = m.group(1) or m.group(2)
        if matched_bn and matched_bn not in DECLARED_BASENAMES:
            unreg.setdefault(matched_bn, set()).add(layer_bn)

# ===== STEP 5: Compute set-diff =====
rg_items = []   # (basename, path, source_label)
for bn, (path, src_label) in sorted(declared.items()):
    if bn not in fired:
        rg_items.append((bn, path, src_label))

rh_items = []   # (basename, layer_set)
for bn, layers in sorted(unreg.items()):
    rh_items.append((bn, layers))

# ===== STEP 6: Report =====
has_red = False

print("== reconcile-gate-wired (declared-vs-actually-fired) ==")
print(f"  declared checks  : {len(declared)}")
print(f"  firing layers    : {len(firing_layers)}")
for fl in firing_layers:
    tag = "rig" if fl.startswith(FLEET) else "product"
    show = os.path.relpath(fl, FLEET) if fl.startswith(FLEET) else fl
    print(f"    [{tag}] {show}")
print(f"  verified fired   : {len(fired)}")
print(f"  R-G (unwired)    : {len(rg_items)}")
print(f"  R-H (unreg)      : {len(rh_items)}")
print(f"  product-repo     : {'AVAILABLE' if product_available else 'UNVERIFIED (fail-closed)'}")

if not product_available:
    print("\n  WARNING: product-side firing ground truth UNVERIFIED — cross-repo")
    print("  checkout at RCW_PRODUCT_REPO not found. Product-side declared checks")
    print("  and firing layers are NOT included. This check NEVER reports a false-GREEN")
    print("  when the product axis is unverifiable (fail-closed).")

if rg_items:
    has_red = True
    print("\n" + "=" * 60, file=sys.stderr)
    print("R-G: DECLARED BUT NOT FIRED (built-but-inert)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    for bn, path, src_label in rg_items:
        print(f"  RED    {bn}", file=sys.stderr)
        print(f"         source: {src_label}", file=sys.stderr)
        print(f"         path:   {path}", file=sys.stderr)
        print(f"         ACTION: wire into preflight.sh:841 scan chain,", file=sys.stderr)
        print(f"                 land.sh pre-conditions, or CI workflow", file=sys.stderr)
        print(file=sys.stderr)

if rh_items:
    has_red = True
    print("=" * 60, file=sys.stderr)
    print("R-H: FIRED BUT NOT DECLARED (running but unregistered)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    for bn, layers in rh_items:
        layers_str = ", ".join(sorted(layers))
        print(f"  RED    {bn}", file=sys.stderr)
        print(f"         layers: [{layers_str}]", file=sys.stderr)
        print(f"         ACTION: declare this check in RULE-REGISTRY.tsv or", file=sys.stderr)
        print(f"                 add to fleet/checks/", file=sys.stderr)
        print(file=sys.stderr)

if has_red:
    print("VERDICT: RED (reconciliation gate-wired FAILED)", file=sys.stderr)
    sys.exit(1)

if not product_available:
    print("\nVERDICT: RIG-SIDE GREEN — product side UNVERIFIED (fail-closed, non-passing)")
    sys.exit(1)

print("\nVERDICT: GREEN — all declared checks are wired into a firing layer; "
      "no unregistered runners.")
sys.exit(0)
PY
