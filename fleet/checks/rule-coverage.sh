#!/usr/bin/env bash
# rule-coverage.sh — COVERAGE META-GATE (build-rig only). MECHANIZES MANAGER-OPERATING-RULES §11:
# "every rule that CAN be a gate MUST be a gate." Ported from the best-in-class reference
# mediastack/tools/enforcement_coverage.py (the Enforcement-Coverage SSOT meta-gate).
#
# WHAT IS PORTED (reused design, adapted to the rig):
#   - The classification taxonomy: every enforceable rule is mechanized | guidance | gap.
#   - The anti-fake-green invariant (ref impl _parse_adrs "enforced" check + cmd_check):
#     a `mechanized` row is only trusted if it points at a REAL, existing enforcing artifact
#     (optionally proven WIRED by a required token) — a row pointing at nothing is RED, never
#     a silent pass. matrix==reality is held BY CONSTRUCTION (re-derived from ground truth).
#   - The FAIL-CLOSED inversion (ref impl id=897): a mechanizable `gap` DEFAULT-BLOCKS. It may
#     be held non-blocking ONLY by a per-row, TIME-BOXED `exempt-until:YYYY-MM-DD` annotation in
#     the row's notes (visible, expiring debt — a force-function, not a snooze button). An
#     expired exemption blocks again. There is no central allowlist to append to.
#
# WHAT IS NEW (rig-specific, not in the ref impl):
#   - The rig's rules live in a hand-authored DOC (MANAGER-OPERATING-RULES.md), not in
#     introspectable ms-enforce registration tuples — so the classification lives in a curated
#     TSV registry (fleet/state/RULE-REGISTRY.tsv), the rig analog of reds.tsv. To keep the
#     registry honest against the doc it classifies, the gate adds two ground-truth cross-checks
#     the ref impl gets for free from introspection: (1) every row's `doc_anchor` must be a live
#     substring of the doc (no phantom/stale rows), and (2) a COMPLETENESS FLOOR — the registry
#     must classify at least as many rules as the doc has enforceable bullets (a newly-added,
#     unclassified rule is a silent GAP → RED).
#
# Registry schema (TSV, tab-separated; '#'/blank lines ignored):
#   rule_id <tab> section <tab> one_line <tab> classification <tab> enforcing_ref <tab> doc_anchor <tab> notes
#     classification : mechanized | guidance | gap
#     enforcing_ref  : mechanized -> "<path>" or "<path>::<required-token>" (path relative to ROOT)
#                      guidance   -> free-text WHY it is judgment-only / unmechanizable
#                      gap        -> free-text target (ticket / gate to build)
#     doc_anchor     : an exact substring of a MANAGER-OPERATING-RULES.md rule line (proves the
#                      row still maps to a live doc rule)
#     notes          : free text; a gap row may carry `exempt-until:YYYY-MM-DD <reason>` to HOLD
#                      it non-blocking until that date (time-boxed visible debt).
#
# Exit 0 = GREEN (every mechanized row is backed by a real wired artifact; no un-exempted
#          mechanizable gap; registry maps 1:1 to the doc). Exit 1 = RED. Exit 2 = usage error.
#
# Self-test seams (defaults are the real fleet; overrides used only by the .test.sh):
#   RULE_COVERAGE_REGISTRY   registry TSV       (default <fleet>/state/RULE-REGISTRY.tsv)
#   RULE_COVERAGE_RULES_DOC  rules doc          (default <fleet>/MANAGER-OPERATING-RULES.md)
#   RULE_COVERAGE_ROOT       artifact-path root (default <fleet>)
#   RULE_COVERAGE_TODAY      exemption anchor   (default: today, YYYY-MM-DD)
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRY="${RULE_COVERAGE_REGISTRY:-$FLEET/state/RULE-REGISTRY.tsv}"
RULES_DOC="${RULE_COVERAGE_RULES_DOC:-$FLEET/MANAGER-OPERATING-RULES.md}"
ROOT="${RULE_COVERAGE_ROOT:-$FLEET}"
TODAY="${RULE_COVERAGE_TODAY:-$(date +%F)}"

export RC_REGISTRY="$REGISTRY" RC_RULES_DOC="$RULES_DOC" RC_ROOT="$ROOT" RC_TODAY="$TODAY"
# NOTE: this script reads the RULE-REGISTRY registry (token asserted by the self-referential rows).
python3 - <<'PY'
import os, re, sys

registry = os.environ["RC_REGISTRY"]
rules_doc = os.environ["RC_RULES_DOC"]
root = os.environ["RC_ROOT"]
today = os.environ["RC_TODAY"]

reds = []          # blocking reasons -> RED
VALID = {"mechanized", "guidance", "gap"}

if not os.path.isfile(registry):
    print(f"RED: registry not found: {registry}", file=sys.stderr)
    sys.exit(1)
if not os.path.isfile(rules_doc):
    print(f"RED: rules doc not found: {rules_doc}", file=sys.stderr)
    sys.exit(1)

doc_text = open(rules_doc, encoding="utf-8").read()
# Enforceable rule bullets = top-level markdown list items under the doc's rule sections.
doc_bullets = [ln for ln in doc_text.splitlines() if ln.startswith("- ")]

rows = []
seen_ids = set()
for raw in open(registry, encoding="utf-8"):
    line = raw.rstrip("\n")
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    parts = line.split("\t")
    if len(parts) < 6:
        reds.append(f"malformed registry row (<6 tab fields): {line[:70]!r}")
        continue
    rid, section, one_line, cls, ref, anchor = (p.strip() for p in parts[:6])
    notes = parts[6].strip() if len(parts) > 6 else ""
    if rid in seen_ids:
        reds.append(f"duplicate rule_id: {rid}")
    seen_ids.add(rid)
    if cls not in VALID:
        reds.append(f"{rid}: invalid classification {cls!r} (want mechanized|guidance|gap)")
        continue
    rows.append((rid, section, one_line, cls, ref, anchor, notes))

# ── Ground-truth cross-check 1: no phantom/stale rows (every anchor lives in the doc) ──
for rid, _sec, _ol, _cls, _ref, anchor, _notes in rows:
    if not anchor:
        reds.append(f"{rid}: empty doc_anchor (cannot prove it maps to a live rule)")
    elif anchor not in doc_text:
        reds.append(f"{rid}: doc_anchor not found in {os.path.basename(rules_doc)} "
                    f"(phantom/stale row): {anchor!r}")

# ── Ground-truth cross-check 2: completeness floor (no unclassified rule) ──
if len(rows) < len(doc_bullets):
    reds.append(f"completeness floor: {len(rows)} registry rows < {len(doc_bullets)} rule "
                f"bullets in {os.path.basename(rules_doc)} — an unclassified rule is a silent GAP")

# ── Per-classification verification ──
EXEMPT_RE = re.compile(r"exempt-until:(\d{4}-\d{2}-\d{2})")
n_mech = n_guid = n_gap = 0
n_gap_exempt = n_gap_blocking = 0

for rid, _sec, _ol, cls, ref, _anchor, notes in rows:
    if cls == "mechanized":
        n_mech += 1
        # Anti-fake-green: the artifact must EXIST, and (if a token is given) contain it.
        path_spec, _, token = ref.partition("::")
        path_spec = path_spec.strip()
        if not path_spec:
            reds.append(f"{rid}: mechanized but no enforcing artifact path given (fake-green)")
            continue
        art = path_spec if os.path.isabs(path_spec) else os.path.join(root, path_spec)
        if not os.path.exists(art):
            reds.append(f"{rid}: mechanized -> {path_spec} but that artifact does NOT exist "
                        f"(fake-green: points at nothing)")
            continue
        if token:
            try:
                body = open(art, encoding="utf-8", errors="replace").read()
            except OSError as e:
                reds.append(f"{rid}: mechanized -> {path_spec} unreadable ({e})")
                continue
            if token not in body:
                reds.append(f"{rid}: mechanized -> {path_spec} exists but is NOT wired "
                            f"(required token {token!r} absent — fake-green)")
    elif cls == "guidance":
        n_guid += 1
        if not ref:
            reds.append(f"{rid}: guidance but no WHY given (a guidance rule must state why it "
                        f"is judgment-only / unmechanizable)")
    elif cls == "gap":
        n_gap += 1
        m = EXEMPT_RE.search(notes)
        if m and m.group(1) >= today:
            n_gap_exempt += 1  # held non-blocking by an ACTIVE time-boxed exemption
        else:
            n_gap_blocking += 1
            why = "expired exemption" if m else "no exemption"
            reds.append(f"{rid}: mechanizable GAP with {why} — build the gate or add a "
                        f"time-boxed `exempt-until:` ({ref})")

mechanizable = n_mech + n_gap
coverage = 100.0 if mechanizable == 0 else (n_mech / mechanizable) * 100.0

print("== rule-coverage meta-gate (MANAGER-OPERATING-RULES §11) ==")
print(f"  rules classified : {len(rows)}  (doc rule-bullets: {len(doc_bullets)})")
print(f"  mechanized       : {n_mech}")
print(f"  guidance         : {n_guid}  (judgment-only, explicitly flagged)")
print(f"  gap              : {n_gap}  ({n_gap_exempt} time-boxed/exempt, {n_gap_blocking} BLOCKING)")
print(f"  coverage         : {coverage:.1f}%  (mechanized / mechanizable[{mechanizable}])")

if reds:
    print("\n-- RED (coverage meta-gate FAILED) --", file=sys.stderr)
    for r in reds:
        print(f"  RED: {r}", file=sys.stderr)
    sys.exit(1)

print("\nGREEN: every mechanized rule is backed by a real wired artifact; no un-exempted "
      "mechanizable GAP; registry maps 1:1 to the doc.")
sys.exit(0)
PY
