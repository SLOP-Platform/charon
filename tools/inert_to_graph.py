#!/usr/bin/env python3
"""Feed the inert/dead-code detector into graphify's code map.

Charon has two independently-built graphs today:

  1. graphify's own AST/semantic graph (``graphify-out/graph.json``) — the
     map used for ``graphify explain/path/diagnose`` and the visual
     ``graph.html``.
  2. ``tools/check_inert_code.py`` (vendored KSF ``ksf_inert_code``) — its
     OWN stdlib ``ast`` call graph + reachability analysis, used only to
     print a pass/fail gate report of 0-caller symbols.

This script does NOT merge those two graph engines (that would mean forking
either graphify's extractor or the inert detector's reachability walk — high
blast radius, not attempted here). Instead it reuses graphify's own existing
extension point for exactly this kind of read-surface annotation: the
"work-memory overlay" sidecar that ``graphify reflect`` already writes
(``graphify-out/.graphify_learning.json``), which ``graphify explain`` and
``graphify export`` (``graph.html``) already load and render at display time
without ever touching the durable structural ``graph.json``
(see ``graphify.reflect.load_learning_overlay`` /
``graphify.exporters.html.to_html``'s ``learning_overlay`` parameter).

Pipeline:
   1. Run the inert detector via ``tools.check_inert_code.find_dead_symbols``
      (reused verbatim — no re-implementation of the AST call graph) to get
      the current dead-symbol list, and ``load_dispositions`` for each
      symbol's tracked ``{reason, disposition}``.
   2. Resolve each dotted symbol (e.g. ``charon.tool_repair.ToolCallRepair``)
      to a graphify node id by matching the node's ``source_file`` (derived
      from the module path) and ``label`` (the bare symbol name) in
      ``graphify-out/graph.json``. graphify's own generic citation resolver
      (``graphify.reflect._resolve_canonical_id``) only disambiguates by bare
      id/label with no file context, which is too coarse here (class/function
      names collide across files) — this script adds file-scoped matching on
      top, it does not re-derive graphify's graph structure.
   3. Write/merge an ``inert``-status entry per resolved node into
      ``.graphify_learning.json``, tagged ``_source: "inert_detector"`` so a
      re-run only replaces entries it owns and never touches entries written
      by ``graphify reflect`` itself.

KNOWN COUPLING RISK (read before wiring into CI): ``graphify reflect``
unconditionally overwrites the entire sidecar file from its own aggregate
(``graphify.reflect.write_learning_sidecar`` calls ``write_text`` on the
whole document, it does not merge). Running ``graphify reflect`` after this
script will silently wipe every entry this script wrote. There is no
core-level opt-out today; the practical mitigation is ordering (always run
this script *after* the last ``graphify reflect``/rebuild in a pipeline) or
a small upstream change (see the module docstring tail below / the written
report for the exact one-line suggestion).

Stdlib only. Does not touch ``src/charon``. Never commits/pushes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_inert_code import find_dead_symbols, load_dispositions  # noqa: E402

SIDECAR_NAME = ".graphify_learning.json"
SOURCE_TAG = "inert_detector"
DEFAULT_GRAPH_PATH = REPO_ROOT / "graphify-out" / "graph.json"


def _resolve_symbol_location(symbol: str, repo_root: Path = REPO_ROOT
                              ) -> tuple[str, str] | None:
    """``charon.tool_repair.ToolCallRepair`` -> (``src/charon/tool_repair.py``,
    ``ToolCallRepair``). Returns None if the symbol has no module component
    (shouldn't happen — the detector only emits ``module.Symbol`` names for
    top-level public functions/classes).

    A dotted module can be either a flat file (``charon.tool_repair`` ->
    ``tool_repair.py``) or a package (``charon.service`` ->
    ``service/__init__.py``, e.g. ``charon.service.get_app``) — both forms
    exist in this codebase, so both are tried, preferring the flat file.
    """
    parts = symbol.split(".")
    if len(parts) < 2:
        return None
    module_parts, name = parts[:-1], parts[-1]
    flat_path = "src/" + "/".join(module_parts) + ".py"
    if (repo_root / flat_path).is_file():
        return flat_path, name
    pkg_path = "src/" + "/".join(module_parts) + "/__init__.py"
    if (repo_root / pkg_path).is_file():
        return pkg_path, name
    return flat_path, name  # fall through; caller's node lookup will just miss


def _index_nodes(nodes: list[dict]) -> dict[tuple[str, str], str]:
    """(source_file, label) -> node id, for every node in the graph.

    Built once and reused per symbol lookup, rather than re-scanning the
    (potentially large — 5800+ node) list per symbol.
    """
    index: dict[tuple[str, str], str] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        sf = n.get("source_file")
        label = n.get("label")
        nid = n.get("id")
        if sf is None or label is None or nid is None:
            continue
        index.setdefault((sf, label), nid)
    return index


def _find_node_id(index: dict[tuple[str, str], str], file_path: str, name: str) -> str | None:
    # Classes/dataclasses/enums are labeled with the bare name; functions get
    # a trailing "()" (observed directly in graph.json for this repo's
    # extractor output) — try both label forms.
    for label in (name, f"{name}()"):
        nid = index.get((file_path, label))
        if nid is not None:
            return nid
    return None


def _content_hash(path: Path) -> str:
    """SHA256 of file bytes, matching graphify.reflect's own fingerprint
    (same algorithm, independently computed here to avoid depending on a
    private graphify function) — so the sidecar's staleness check does not
    spuriously mark a freshly-written inert entry as "code changed" just
    because we skipped the fingerprint field.
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def build_entries(graph_path: Path, repo_root: Path = REPO_ROOT
                   ) -> tuple[dict[str, dict], list[str]]:
    """Run the detector and resolve each dead symbol to a graph node.

    Returns ``(node_id -> overlay entry, unresolved_symbols)``.
    """
    dead = find_dead_symbols(repo_root)
    dispositions = load_dispositions()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    index = _index_nodes(nodes)

    now = datetime.now(timezone.utc).isoformat()
    entries: dict[str, dict] = {}
    unresolved: list[str] = []
    for sym in dead:
        loc = _resolve_symbol_location(sym, repo_root)
        if loc is None:
            unresolved.append(sym)
            continue
        file_path, name = loc
        nid = _find_node_id(index, file_path, name)
        if nid is None:
            unresolved.append(sym)
            continue
        disp_entry = dispositions.get(sym, {})
        disposition = disp_entry.get("disposition", "UNDISPOSED")
        reason = disp_entry.get("reason", "")
        abs_source_path = repo_root / file_path
        entries[nid] = {
            # Schema compatible with graphify.reflect's learning-overlay
            # sidecar (status/score/uses/label/source_file/provenance) so
            # `graphify explain` and `graph.html` render it with zero
            # graphify-core changes. `inert`/`symbol`/`reason`/`disposition`
            # are additive fields graphify ignores but this tool (and any
            # future consumer) can read back.
            "status": "inert",
            "score": 0,
            "uses": 0,
            "last": now,
            "label": name,
            "source_file": file_path,
            "code_fingerprint": _content_hash(abs_source_path),
            "provenance": [],
            "inert": True,
            "symbol": sym,
            "reason": reason,
            "disposition": disposition,
            "_source": SOURCE_TAG,
        }
    return entries, unresolved


def merge_sidecar(graph_path: Path, entries: dict[str, dict]) -> Path:
    """Merge ``entries`` into the sidecar next to *graph_path*.

    Only replaces entries this script previously wrote (tagged
    ``_source: "inert_detector"``); entries written by `graphify reflect`
    (no `_source` tag) are left untouched *by this script* — but note the
    module docstring's coupling risk: `graphify reflect` itself overwrites
    the whole file unconditionally, including our entries, on its own runs.
    """
    sidecar_path = graph_path.parent / SIDECAR_NAME
    try:
        existing = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    nodes = existing.get("nodes")
    if not isinstance(nodes, dict):
        nodes = {}

    # Drop our own previous entries (stale inert markers for symbols no
    # longer dead get dropped this way), then add the current set.
    nodes = {
        nid: e for nid, e in nodes.items()
        if not (isinstance(e, dict) and e.get("_source") == SOURCE_TAG)
    }
    nodes.update(entries)

    existing["version"] = existing.get("version", 1)
    existing["generated_at"] = datetime.now(timezone.utc).isoformat()
    existing["nodes"] = nodes

    sidecar_path.write_text(
        json.dumps(existing, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return sidecar_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH_PATH),
                        help="Path to graphify-out/graph.json (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written without touching the sidecar")
    args = parser.parse_args()

    graph_path = Path(args.graph).resolve()
    if not graph_path.exists():
        print(f"error: graph not found: {graph_path}", file=sys.stderr)
        print("Run `graphify extract` / `graphify update` first.", file=sys.stderr)
        return 1

    entries, unresolved = build_entries(graph_path)

    print(f"inert_to_graph: {len(entries) + len(unresolved)} dead symbol(s) from the detector")
    print(f"  resolved to a graph node : {len(entries)}")
    for nid, e in sorted(entries.items()):
        print(f"    [{e['disposition']}] {e['symbol']} -> node {nid}")
    if unresolved:
        print(f"  unresolved (no matching graph node): {len(unresolved)}")
        for sym in unresolved:
            print(f"    - {sym}")

    if args.dry_run:
        print("(dry run — sidecar not written)")
        return 0

    sidecar_path = merge_sidecar(graph_path, entries)
    print(f"wrote {len(entries)} inert annotation(s) -> {sidecar_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
