#!/usr/bin/env bash
# inventory-table.sh — KS29 accessor for the shared price-tracked inventory table.
#
# One canonical TSV (fleet/state/price-tracked-inventory.tsv), keyed on
# (provider, normalized_model_id) where normalization reuses the router's own
# charon.proxy._normalize_model_id verbatim.  Two writers, column-partitioned
# (see WRITER PARTITION below).
#
# Usage:
#   inventory-table.sh init                          — ensure TSV exists with header
#   inventory-table.sh read <provider> <model>       — print matching row (empty if none)
#   inventory-table.sh upsert-row <key=value> ...    — upsert one row (see fields below)
#   inventory-table.sh list-by-status <status>       — list rows matching status
#
# upsert-row fields:
#   source=         source_url=     provider=       base_url=
#   model_ids=      funding_class=  cost_in_usd_mtok=  cost_out_usd_mtok=
#   rpd=            rpm=            tpm=            tpd=
#   context_cap=    trains_on_data= personal_only=  exhaustion_signal=
#   first_seen=     last_seen=      status=
# All standard — the §3c column union (see TSV header).  --help for full list.
#
# WRITER PARTITION:
#   DISCOVERY (D7 / INVENTORY-TABLE-SHARE) writes:
#     source, source_url, funding_class, community cost/limit, first_seen,
#     last_seen, status (candidate).
#   CATALOG_REFRESH + METER writes live/measured columns:
#     cost_in_usd_mtok, cost_out_usd_mtok, rpd, rpm, tpm, tpd, context_cap,
#     trains_on_data, personal_only, exhaustion_signal.
#   Never write outside your partition — the other writer's columns are read-only.
#   No parallel store — both writers upsert through THIS accessor.
#
# FAIL-ON-REVERT (self-test):
#   upsert a row then read it back keyed on (provider, normalized_model);
#   corrupt the key-normalization -> read misses -> RED.
#
# Env:
#   INVENTORY_TSV    — path to the TSV (default: <fleet>/state/price-tracked-inventory.tsv)
#   CHARON_SRC       — product src dir on PYTHONPATH (default: /home/stack/code/charon/src)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INVENTORY_TSV="${INVENTORY_TSV:-$HERE/state/price-tracked-inventory.tsv}"
CHARON_SRC="${CHARON_SRC:-/home/stack/code/charon/src}"

die(){ echo "inventory-table: ERROR: $*" >&2; exit 2; }

# Python engine — embeds _normalize_model_id for key identity.
_py_engine() {
  PYTHONPATH="$CHARON_SRC" python3 - "$INVENTORY_TSV" "$@" <<'PYEOF'
import csv, os, re, sys

from charon.proxy import _normalize_model_id

TSV = sys.argv[1]
CMD = sys.argv[2] if len(sys.argv) > 2 else ""

COLUMNS = [
    "source", "source_url", "provider", "base_url", "model_ids",
    "funding_class", "cost_in_usd_mtok", "cost_out_usd_mtok",
    "rpd", "rpm", "tpm", "tpd", "context_cap", "trains_on_data",
    "personal_only", "exhaustion_signal", "first_seen", "last_seen", "status",
]
COL_INDEX = {c: i for i, c in enumerate(COLUMNS)}


def read_rows(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for line in reader:
            # skip comment-only lines; header row (first non-comment) defines schema
            if not line or line[0].startswith("#"):
                continue
            rows.append(line)
    # First row is the header; skip it for data.
    if rows and rows[0] == COLUMNS:
        rows = rows[1:]
    return rows


def row_matches(row, provider, model_id):
    if row[COL_INDEX["provider"]] != provider:
        return False
    raw_ids = row[COL_INDEX["model_ids"]]
    for rid in raw_ids.split("|"):
        if _normalize_model_id(rid) == _normalize_model_id(model_id):
            return True
    return False


def cmd_init():
    if os.path.exists(TSV):
        print(f"init ok — {TSV} already exists")
        return
    os.makedirs(os.path.dirname(TSV), exist_ok=True)
    with open(TSV, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(COLUMNS)
    print(f"init ok — created {TSV}")


def cmd_read():
    if len(sys.argv) < 5:
        print("read requires <provider> <model>", file=sys.stderr)
        sys.exit(2)
    provider = sys.argv[3]
    model = sys.argv[4]
    rows = read_rows(TSV)
    for row in rows:
        if row_matches(row, provider, model):
            print("\t".join(row))
            return
    sys.exit(1)


def cmd_upsert_row():
    if len(sys.argv) < 4:
        print("upsert-row requires key=value pairs", file=sys.stderr)
        sys.exit(2)
    kv_pairs = sys.argv[3:]
    fields = {}
    for kv in kv_pairs:
        k, _, v = kv.partition("=")
        fields[k] = v
    prov = fields.get("provider", "")
    model_ids = fields.get("model_ids", "")
    if not prov:
        print("upsert-row: provider= is required", file=sys.stderr)
        sys.exit(2)
    if not model_ids:
        print("upsert-row: model_ids= is required", file=sys.stderr)
        sys.exit(2)

    first_model = model_ids.split("|")[0]
    norm = _normalize_model_id(first_model)
    if not norm:
        print(f"upsert-row: empty normalized model for {model_ids!r}", file=sys.stderr)
        sys.exit(2)

    rows = read_rows(TSV)
    kept = []
    for row in rows:
        if row_matches(row, prov, first_model):
            continue
        kept.append(row)

    new_row = [fields.get(c, "") for c in COLUMNS]
    kept.append(new_row)

    with open(TSV, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(COLUMNS)
        w.writerows(kept)
    print(f"upserted (provider={prov}, model={norm})")


def cmd_list_by_status():
    if len(sys.argv) < 4:
        print("list-by-status requires a status argument", file=sys.stderr)
        sys.exit(2)
    status_filter = sys.argv[3]
    rows = read_rows(TSV)
    for row in rows:
        if row[COL_INDEX["status"]] == status_filter:
            print("\t".join(row))


def cmd_path():
    print(TSV)


CMDS = {
    "init": cmd_init,
    "read": cmd_read,
    "upsert-row": cmd_upsert_row,
    "list-by-status": cmd_list_by_status,
    "--path": cmd_path,
}
fn = CMDS.get(CMD)
if fn is None:
    print(f"usage: {sys.argv[0]} <init|read|upsert-row|list-by-status> [args...]", file=sys.stderr)
    sys.exit(2)
fn()
PYEOF
}

# ── CLI dispatch ────────────────────────────────────────────────────────────
case "${1:-}" in
  -h|--help)
    sed -n '2,37p' "$0" | sed 's/^# \?//'
    exit 0
    ;;
esac
_py_engine "$@"
