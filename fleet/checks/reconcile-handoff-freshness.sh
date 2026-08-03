#!/usr/bin/env bash
# reconcile-handoff-freshness.sh — RIG-META reconciler: handoff-freshness ↔ actual-HEAD.
# Detects the class of failure where the GENERATED-STATE block's machine-printed SHAs
# are stale (origin moved after generation, but the handoff was never re-generated).
#
# Design: UNIFIED-RECONCILIATION-GATE-DESIGN.md §1.x (PR #178, RECONCILE-HANDOFF-FRESHNESS ticket).
# drift-primitive: content-hash/checksum (KS29 leg) — the baked-in SHA in the handoff
# must match the live origin/master SHA. Staleness-probe-TTL (KS29 leg) — the
# `generated=` timestamp must be within N hours of now.
#
# desired-source: fleet/SESSION-HANDOFF-*.md machine-printed lines:
#   origin-master product = <sha>
#   origin-master rig    = <sha>
#   generated = <ISO8601>
#
# actual-source: live `git ls-remote origin refs/heads/master` SHA (product + rig repos).
#
# RED conditions:
#   R-A: the newest handoff's baked-in product SHA != live origin/master product SHA.
#   R-B: the newest handoff's baked-in rig SHA != live origin/master rig SHA.
#   R-C: the newest handoff's `generated=` is older than FRESHNESS_HOURS hours.
#   R-D: any RECENTLY-MODIFIED handoff (touched after its own generation) has a
#        stale baked-in SHA — the session made changes post-generation that moved
#        origin without re-running generation.
#
# Product/rig checkout absent: the relevant axis is UNVERIFIED (fail-closed, never GREEN).
# Exit 0 = GREEN (all axes clean).  Exit 1 = RED or UNVERIFIED.  Exit 2 = usage error.
#
# Self-test seams (env overrides):
#   RHF_FLEET              fleet root directory (default: auto-detected)
#   RHF_PRODUCT_REPO       product repo root (default: /home/stack/code/charon)
#   RHF_RIG_REPO           rig repo root (default: /home/stack/charon-private)
#   RHF_FRESHNESS_HOURS    max age in hours for generated= timestamp (default: 48)
#   RHF_EXTRA_HANDOFFS     colon-separated extra dirs to scan for handoff files
set -uo pipefail
export RHF_FLEET="${RHF_FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export RHF_PRODUCT_REPO="${RHF_PRODUCT_REPO:-/home/stack/code/charon}"
export RHF_RIG_REPO="${RHF_RIG_REPO:-/home/stack/charon-private}"
export RHF_FRESHNESS_HOURS="${RHF_FRESHNESS_HOURS:-48}"

python3 - <<'PY'
import os, sys, re, glob, subprocess, datetime

FLEET         = os.environ["RHF_FLEET"]
PRODUCT_REPO  = os.environ.get("RHF_PRODUCT_REPO") or ""
RIG_REPO      = os.environ.get("RHF_RIG_REPO") or ""

_rh_product_path = os.environ.get("_RHF_PRODUCT_PATH", "") or ""
_rh_rig_path     = os.environ.get("_RHF_RIG_PATH", "") or ""

if not PRODUCT_REPO:
    PRODUCT_REPO = ""
if not RIG_REPO:
    RIG_REPO = ""

product_available = bool(os.environ.get("RHF_PRODUCT_REPO")) and os.path.isdir(PRODUCT_REPO)
rig_available     = bool(os.environ.get("RHF_RIG_REPO"))     and os.path.isdir(RIG_REPO)

UNAVAIL = "UNAVAILABLE"
FRESHNESS_HRS = int(os.environ.get("RHF_FRESHNESS_HOURS", "48"))
EXTRA_HANDOFF = os.environ.get("RHF_EXTRA_HANDOFFS", "").strip()
FRESHNESS_CUTOFF = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=FRESHNESS_HRS)

def ls_remote_sha(repo):
    if not repo or not os.path.isdir(repo):
        return UNAVAIL
    try:
        r = subprocess.run(
            ["git", "-C", repo, "ls-remote", "origin", "refs/heads/master"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            tokens = r.stdout.strip().split()
            if tokens and re.fullmatch(r"[0-9a-f]{40}", tokens[0]):
                return tokens[0]
    except Exception:
        pass
    return UNAVAIL

def parse_handoff_sha(line):
    m = re.search(r'=\s*([0-9a-f]{40}|UNAVAILABLE)\b', line)
    return m.group(1) if m else None

def parse_generated_timestamp(text):
    m = re.search(r'generated\s*=\s*([\d]{4}-[\d]{2}-[\d]{2}T[\d]{2}:[\d]{2}:[\d]{2}Z)', text)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None

handoff_dirs = [FLEET]
if EXTRA_HANDOFF:
    for d in EXTRA_HANDOFF.split(":"):
        d = d.strip()
        if d and os.path.isdir(d):
            handoff_dirs.append(d)

all_handoffs = []
for d in handoff_dirs:
    for f in glob.glob(os.path.join(d, "SESSION-HANDOFF-*.md")):
        all_handoffs.append(f)

all_handoffs.sort(key=lambda p: os.path.getmtime(p), reverse=True)

if not all_handoffs:
    print("== reconcile-handoff-freshness ==")
    print("  VERDICT: GREEN — no SESSION-HANDOFF-*.md files found")
    sys.exit(0)

newest = all_handoffs[0]
other_recent = all_handoffs[1:]

try:
    newest_text = open(newest, encoding="utf-8", errors="replace").read()
except OSError as e:
    print(f"ERROR: cannot read {newest}: {e}", file=sys.stderr)
    sys.exit(2)

newest_name = os.path.basename(newest)

in_block = False
prod_line, rig_line = "", ""
for line in newest_text.splitlines():
    stripped = line.strip()
    if "GENERATED-STATE" in line and "<!--" in line:
        in_block = True
        continue
    if in_block and "-->" in line:
        in_block = False
        continue
    if in_block:
        if "origin-master product" in line:
            prod_line = line
        elif "origin-master rig" in line:
            rig_line = line

baked_product = parse_handoff_sha(prod_line) if prod_line else None
baked_rig    = parse_handoff_sha(rig_line)    if rig_line else None

live_product = ls_remote_sha(PRODUCT_REPO) if product_available else UNAVAIL
live_rig     = ls_remote_sha(RIG_REPO)      if rig_available     else UNAVAIL

gen_ts = parse_generated_timestamp(newest_text)
ts_red = False
ts_detail = ""
if gen_ts is None:
    ts_detail = "no generated= timestamp found"
    ts_red = True
elif gen_ts < FRESHNESS_CUTOFF:
    age_h = (datetime.datetime.now(datetime.timezone.utc) - gen_ts).total_seconds() / 3600
    ts_detail = f"generated {gen_ts.strftime('%Y-%m-%dT%H:%M:%SZ')} is {age_h:.1f}h old (limit {FRESHNESS_HRS}h)"
    ts_red = True

reds = []

if baked_product and baked_product != UNAVAIL:
    if live_product == UNAVAIL:
        reds.append("R-A UNVERIFIED: product checkout absent — product axis unverifiable (fail-closed)")
    elif baked_product != live_product:
        reds.append(f"R-A: product SHA DRIFT — baked={baked_product} != live={live_product}")
elif not product_available:
    reds.append("R-A UNVERIFIED: no product SHA line in handoff and product checkout absent")

if baked_rig and baked_rig != UNAVAIL:
    if live_rig == UNAVAIL:
        reds.append("R-B UNVERIFIED: rig checkout absent — rig axis unverifiable (fail-closed)")
    elif baked_rig != live_rig:
        reds.append(f"R-B: rig SHA DRIFT — baked={baked_rig} != live={live_rig}")
elif not rig_available:
    reds.append("R-B UNVERIFIED: no rig SHA line in handoff and rig checkout absent")

if ts_red:
    reds.append(f"R-C: timestamp STALE — {ts_detail}")

for path in other_recent:
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    name = os.path.basename(path)
    for line in text.splitlines():
        stripped = line.strip()
        if "origin-master" not in stripped:
            continue
        baked = parse_handoff_sha(stripped)
        if not baked or baked == UNAVAIL:
            continue
        if "product" in stripped and baked != live_product and live_product != UNAVAIL:
            reds.append(f"R-D [{name}]: product SHA DRIFT after file modification — baked={baked} != live={live_product}")
        elif "rig" in stripped and baked != live_rig and live_rig != UNAVAIL:
            reds.append(f"R-D [{name}]: rig SHA DRIFT after file modification — baked={baked} != live={live_rig}")

print("== reconcile-handoff-freshness (handoff-freshness ↔ actual-HEAD) ==")
print(f"  handoffs scanned : {len(all_handoffs)}")
print(f"  newest handoff   : {newest_name}")
print(f"  generated        : {gen_ts.strftime('%Y-%m-%dT%H:%M:%SZ') if gen_ts else 'NOT FOUND'}")
print(f"  freshness window : {FRESHNESS_HRS}h")
print(f"  product checkout : {'AVAILABLE' if product_available else 'ABSENT (UNVERIFIED)'}")
print(f"  rig checkout     : {'AVAILABLE' if rig_available else 'ABSENT (UNVERIFIED)'}")
print()
print(f"  [desired]  baked product SHA : {baked_product or 'N/A'}")
print(f"  [actual]   live product SHA  : {live_product}")
print(f"  [desired]  baked rig SHA     : {baked_rig or 'N/A'}")
print(f"  [actual]   live rig SHA      : {live_rig}")
print()
print(f"  RED conditions : {len(reds)}")
unverif = [r for r in reds if "UNVERIFIED" in r]
drift   = [r for r in reds if "UNVERIFIED" not in r]
if unverif:
    print("  UNVERIFIED (fail-closed, not GREEN):")
    for r in unverif:
        print(f"    {r}")
if drift:
    print("  DRIFT (declared != actual):")
    for r in drift:
        print(f"    {r}")

has_red     = bool(drift)
has_unverif = bool(unverif)

if has_red:
    print("\nVERDICT: RED — handoff SHAs do not match live origin/master")
    sys.exit(1)

if has_unverif:
    print("\nVERDICT: UNVERIFIED — one or more axes unverifiable (fail-closed, not GREEN)")
    sys.exit(1)

print("\nVERDICT: GREEN — all handoff SHAs match live origin/master and generated= is fresh")
sys.exit(0)
PY
