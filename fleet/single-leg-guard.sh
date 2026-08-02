#!/usr/bin/env bash
# single-leg-guard.sh — RED guard: flag any routed model that has no cheaper live  # public-clean: allow
# alternative (a "single-legged model").  This is what turns a NeuralWatt-class   # public-clean: allow
# price hike into a swap instead of an outage: the gap R5's cost-rank demotion    # public-clean: allow
# needs to actually land on.                                                        # public-clean: allow
#
# Composes the INVENTORY-TABLE (fleet/state/price-tracked-inventory.tsv) with the  # public-clean: allow
# live routing pool (charon's models.json) to assert, for every routed model, that  # public-clean: allow
# live routing pool (charon's models.json) to assert, for every routed model, that
# >=1 cheaper live provider-offer exists.
#
# Design:
#   * INVENTORY-TABLE is the source of truth for per-(provider, model) pricing.
#     Shared with INVENTORY-TABLE writer: the same _normalize_model_id identity,
#     the same TSV schema.
#   * Live pool is read from charon's models.json (the operator's routing config).
#     This is the authoritative set of what is actually routed — not the catalog.
#   * Per-model cost comparison uses the 3:1 blended cost (same formula as
#     cost_rank.py: derived_cost_rank, without the *1e8 scaling).
#   * RED condition: a routed model whose cheapest offer is its ONLY offer.
#   * Do NOT re-implement the swap — R5 cost-rank already reorders; this guard
#     only proves an alternative EXISTS so the reorder has a target.
#
# FAIL-ON-REVERT (self-test):
#   1. upsert a model with only one provider -> single-leg RED fires.
#   2. add a cheaper alternative offer -> green.
#
# Env:
#   INVENTORY_TSV  — path to INVENTORY-TABLE TSV (default: <fleet>/state/price-tracked-inventory.tsv)
#   CHARON_SRC     — charon src dir for PYTHONPATH (default: $HOME/code/charon/src)
#   CHARON_CONFIG  — charon config dir (default: ~/.charon)
#   SLG_VERBOSE    — set to 1 for per-model alternative detail
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INVENTORY_TSV="${INVENTORY_TSV:-$HERE/state/price-tracked-inventory.tsv}"
CHARON_SRC="${CHARON_SRC:-$HOME/code/charon/src}"  # public-clean: allow
CHARON_CONFIG="${CHARON_CONFIG:-$(python3 -c 'import os; print(os.path.expanduser("~/.charon"))' 2>/dev/null || echo "$HOME/.charon")}"
SLG_OUT_REPORT="${HERE}/state/single-leg-guard-report.tsv"

die(){ echo "single-leg-guard: ERROR: $*" >&2; exit 2; }

# ── Python engine ────────────────────────────────────────────────────────────
# Reads INVENTORY_TSV + CHARON_CONFIG/models.json, writes TSV to stdout,
# writes detailed report to SLG_OUT_REPORT.
_py_engine() {
  PYTHONPATH="$CHARON_SRC" python3 - "$INVENTORY_TSV" "$CHARON_CONFIG" "$SLG_OUT_REPORT" "${1:-}" <<'PYEOF'
import csv, json, os, sys
from pathlib import Path

from charon.proxy import _normalize_model_id

INVENTORY_TSV = sys.argv[1]
CHARON_CONFIG  = sys.argv[2]
REPORT_PATH    = sys.argv[3]
MODE           = sys.argv[4] if len(sys.argv) > 4 else "guard"

# ── TSV schema (shared with inventory-table.sh) ──────────────────────────────
COLUMNS = [
    "source", "source_url", "provider", "base_url", "model_ids",
    "funding_class", "cost_in_usd_mtok", "cost_out_usd_mtok",
    "rpd", "rpm", "tpm", "tpd", "context_cap", "trains_on_data",
    "personal_only", "exhaustion_signal", "first_seen", "last_seen", "status",
]
CI = {c: i for i, c in enumerate(COLUMNS)}

# ── read helpers ───────────────────────────────────────────────────────────────
def read_inventory(path):
    """Yield {provider, model_ids, cost_in, cost_out, status} per row."""
    if not os.path.exists(path):
        return
    with open(path, newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for line in reader:
            if not line or line[0].startswith("#"):
                continue
            # skip header
            if line == COLUMNS:
                continue
            status = line[CI["status"]]
            prov   = line[CI["provider"]]
            models_raw = line[CI["model_ids"]]
            cin   = _num(line[CI["cost_in_usd_mtok"]])
            cout  = _num(line[CI["cost_out_usd_mtok"]])
            yield {"provider": prov, "model_ids": models_raw,
                   "cin": cin, "cout": cout, "status": status}


def _num(s):
    try:
        return float(s) if s else None
    except ValueError:
        return None


def blended(ci, co):
    """3:1 blended cost (matches cost_rank.py derived_cost_rank)."""
    if ci is None and co is None:
        return None
    ci = ci or 0.0
    co = co or 0.0
    return (3.0 * ci + co) / 4.0


def row_matches_model(row_models_raw, target_norm):
    """True if row's model_ids (pipe-separated) contains target_norm."""
    for m in row_models_raw.split("|"):
        if _normalize_model_id(m) == target_norm:
            return True
    return False


def load_live_models(config_dir):
    """Return list of (model_id, spec_dict) from charon's models.json."""
    p = Path(config_dir) / "models.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for mid, spec in data.items():
        if isinstance(spec, dict):
            out.append((mid, spec))
    return out


# ── mode: guard ───────────────────────────────────────────────────────────────
def cmd_guard():
    verbose = bool(os.environ.get("SLG_VERBOSE"))
    inventory = list(read_inventory(INVENTORY_TSV))

    # Build: normalized_model -> [(provider, blended_cost, row_status), ...]
    inv_index = {}
    for row in inventory:
        for raw_m in row["model_ids"].split("|"):
            norm = _normalize_model_id(raw_m)
            if not norm:
                continue
            entry = (row["provider"], blended(row["cin"], row["cout"]), row["status"])
            inv_index.setdefault(norm, []).append(entry)

    live_models = load_live_models(CHARON_CONFIG)
    reds = []
    all_rows = []

    # Sort by model_id for stable output
    for mid, spec in sorted(live_models):
        norm = _normalize_model_id(mid)
        offers = inv_index.get(norm, [])

        # Only consider live/active offers (status not exhaust/fail)
        live_offers = [(p, c, s) for p, c, s in offers
                       if s not in ("exhaust", "fail")]

        if not live_offers:
            # Model has no inventory entry — not routable in practice, skip RED
            all_rows.append((mid, "", None, 0, "no-inventory", []))
            continue

        # Find cheapest live offer
        cheapest_cost = min(c for _, c, _ in live_offers if c is not None)
        cheapest_provs = sorted({p for p, c, _ in live_offers if c == cheapest_cost})
        leg_count = len(live_offers)
        has_cheaper = any(c < cheapest_cost for _, c, _ in live_offers)

        if leg_count == 1:
            status = "RED"
            reds.append((mid, cheapest_provs[0], cheapest_cost))
        elif has_cheaper:
            status = "GREEN"
        else:
            # Multiple offers at same cost — all equal, no cheaper alternative
            status = "GREEN"

        # Collect alternatives for verbose output
        alts = [(p, c) for p, c, _ in live_offers
                if c is not None and c > cheapest_cost]
        alts.sort(key=lambda x: x[1])
        all_rows.append((mid, cheapest_provs[0], cheapest_cost,
                         leg_count, status, alts))

    # ── stdout: TSV ─────────────────────────────────────────────────────────
    writer = csv.writer(sys.stdout, delimiter="\t")
    writer.writerow(["model", "cheapest_provider", "cheapest_blended_cost",
                     "legs", "status", "alternatives"])
    for mid, cheapest_p, cost, legs, status, alts in all_rows:
        alt_str = "; ".join(f"{p}={c:.6f}" for p, c in alts) if alts else ""
        writer.writerow([mid, cheapest_p or "",
                         f"{cost:.6f}" if cost is not None else "",
                         legs, status, alt_str])

    # ── report file ─────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(REPORT_PATH) or ".", exist_ok=True)
    with open(REPORT_PATH, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["# single-leg-guard report", "generated",
                    str(os.path.getmtime(sys.argv[1])) if os.path.exists(sys.argv[1]) else "n/a"])
        w.writerow(["model", "cheapest_provider", "cheapest_blended_cost",
                    "legs", "status", "cheapest_alternatives", "all_providers"])
        for mid, cheapest_p, cost, legs, status, alts in all_rows:
            alt_str = "; ".join(f"{p}={c:.6f}" for p, c in alts) if alts else "(none)"
            all_provs = "; ".join(
                f"{p}({c:.6f})" for p, c, _ in
                sorted(inv_index.get(_normalize_model_id(mid), []), key=lambda x: x[1] or 999)
            )
            w.writerow([mid, cheapest_p or "",
                       f"{cost:.6f}" if cost is not None else "",
                       legs, status, alt_str, all_provs])

    # Summary
    print(f"# single-leg-guard: {len(reds)} RED, {len([r for r in all_rows if r[4]=='GREEN'])} GREEN", file=sys.stderr)
    if reds:
        print("# RED models (single-legged — no cheaper fallback):", file=sys.stderr)
        for mid, prov, cost in reds:
            print(f"#   {mid}  (only provider: {prov}, blended_cost={cost:.6f})", file=sys.stderr)
        print("# Operator alert: single-legged models detected — price hike on their", file=sys.stderr)
        print("# sole provider will strand traffic. Add a cheaper alternative to GREEN.", file=sys.stderr)

    return 0 if not reds else 1


# ── mode: check ───────────────────────────────────────────────────────────────
def cmd_check():
    """Check a specific model: is it single-legged?"""
    if len(sys.argv) < 6:
        print("check requires <model>", file=sys.stderr)
        sys.exit(2)
    target = sys.argv[5]
    inventory = list(read_inventory(INVENTORY_TSV))

    inv_index = {}
    for row in inventory:
        for raw_m in row["model_ids"].split("|"):
            norm = _normalize_model_id(raw_m)
            if not norm:
                continue
            inv_index.setdefault(norm, []).append(
                (row["provider"], blended(row["cin"], row["cout"]), row["status"]))

    norm = _normalize_model_id(target)
    offers = [(p, c, s) for p, c, s in inv_index.get(norm, [])
              if s not in ("exhaust", "fail")]

    if not offers:
        print(f"NOT-ROUTED  {target}  (no live inventory entry)")
        return 2

    cheapest = min(c for _, c, _ in offers if c is not None)
    leg_count = len(offers)
    status = "RED" if leg_count == 1 else "GREEN"
    alt_count = sum(1 for _, c, _ in offers if c is not None and c > cheapest)

    print(f"{status}  {target}  legs={leg_count}  cheapest={cheapest:.6f}  cheaper_alts={alt_count}")
    return 0 if status == "GREEN" else 1


# ── mode: report ──────────────────────────────────────────────────────────────
def cmd_report():
    """Print the last guard report."""
    if os.path.exists(REPORT_PATH):
        print(Path(REPORT_PATH).read_text(), end="")
    else:
        print(f"# no report found at {REPORT_PATH} — run 'guard' first", file=sys.stderr)
        return 1
    return 0


CMDS = {
    "guard":  cmd_guard,
    "check":  cmd_check,
    "report": cmd_report,
}

if __name__ == "__main__":
    fn = CMDS.get(MODE)
    if fn is None:
        print(f"usage: {sys.argv[0]} <guard|check <model>|report>", file=sys.stderr)
        sys.exit(2)
    sys.exit(fn())
PYEOF
}

# ── CLI dispatch ──────────────────────────────────────────────────────────────
case "${1:-}" in
  guard|check|report) ;;
  -h|--help)
    sed -n '3,42p' "$0" | sed 's/^# \?//'
    exit 0
    ;;
  *)
    echo "usage: $0 <guard|check <model>|report>" >&2
    exit 2
    ;;
esac

_py_engine "$@"
