"""DEC-AST-WRAP — change-surface adapter over the ``semantic_proof`` AST engine.

A thin, deterministic wrapper that turns a set of change *targets* (owned file
paths) into the **change-surface facts dict** the decomposer planner consumes.

This module performs **no** program analysis of its own.  Every fact it emits is
produced by *calling the existing* deterministic AST engine in
``charon.engine.semantic_proof``:

  * ``_build_import_graph`` / ``_transitive_reachability`` — the real import
    graph + transitive reachability (blast radius & call edges).
  * ``compute_certificate`` — the real pairwise semantic-independence proof
    (the independence split).

Because it only delegates to that engine it inherits the same guarantees:
pure functions of source + config, no LLM, no clock, no RNG, no network
(stdlib-only, ADR-0010 D2).  The engine module is imported, never modified.

Output shape (all lists sorted → deterministic)::

    {
      "files":               [<repo-relative target file>, ...],
      "call_edges":          [[<from_file>, <to_file>], ...],
      "blast_radius":        {<target_file>: [<reachable_file>, ...], ...},
      "independence_groups": [[<file>, ...], ...],
    }

``independence_groups`` partitions the targets: two files land in the **same**
group when the engine could **not** prove them independent (conservative
demotion, per the ``semantic_proof`` docstring), and in **different** groups
only when ``compute_certificate(...).proven`` is True.  Distinct groups are
therefore provably independent and may be scheduled concurrently.
"""
from __future__ import annotations

import pathlib
from collections import defaultdict
from collections.abc import Iterable

from .engine import semantic_proof


def change_surface(
    targets: Iterable[str],
    repo_root: str | None = None,
    config_dir: str | None = None,
) -> dict[str, object]:
    """Compute the change-surface facts dict for a set of change *targets*.

    ``targets`` are repo-relative source file paths (e.g. ``src/charon/foo.py``)
    that a prospective change would touch.  ``repo_root`` is the repo directory
    (defaults to cwd); ``config_dir`` is the Charon config dir passed straight
    through to ``semantic_proof.compute_certificate`` (defaults to ``~/.charon``).

    Returns the facts dict described in the module docstring.  Deterministic:
    the same inputs over the same tree always yield byte-identical output.
    """
    root = pathlib.Path(repo_root or ".")
    files = sorted({_normalize(t) for t in targets})

    # Real import graph from the engine — do not reimplement.
    graph = semantic_proof._build_import_graph(root)

    blast_radius = _blast_radius(files, graph, root)
    call_edges = _call_edges(files, graph, root)
    independence_groups = _independence_groups(files, repo_root, config_dir)

    return {
        "files": files,
        "call_edges": call_edges,
        "blast_radius": blast_radius,
        "independence_groups": independence_groups,
    }


# ----------------------------------------------------------------- blast radius

def _blast_radius(
    files: list[str], graph: dict[str, set[str]], root: pathlib.Path
) -> dict[str, list[str]]:
    """Per-target set of other repo files transitively reachable from it."""
    out: dict[str, list[str]] = {}
    for f in files:
        reachable_modules = semantic_proof._transitive_reachability([f], graph)
        reachable_files = semantic_proof._module_to_files(reachable_modules)
        out[f] = sorted(
            rf for rf in reachable_files if rf != f and (root / rf).is_file()
        )
    return out


# ------------------------------------------------------------------- call edges

def _call_edges(
    files: list[str], graph: dict[str, set[str]], root: pathlib.Path
) -> list[list[str]]:
    """Import/call edges of the subgraph reachable from the targets.

    Only edges whose source module is transitively reachable from a target are
    included, and only when both endpoints resolve to a file that exists.
    """
    involved: set[str] = set()
    for f in files:
        involved |= semantic_proof._transitive_reachability([f], graph)

    edges: set[tuple[str, str]] = set()
    for module in involved:
        src_file = _module_file(module)
        if not (root / src_file).is_file():
            continue
        for imp in graph.get(module, set()):
            dst_file = _module_file(imp)
            if (root / dst_file).is_file():
                edges.add((src_file, dst_file))
    return sorted([src, dst] for src, dst in edges)


# ------------------------------------------------------------ independence split

def _independence_groups(
    files: list[str], repo_root: str | None, config_dir: str | None
) -> list[list[str]]:
    """Partition targets via the engine's pairwise independence certificate.

    Union-find: merge two targets whenever the engine cannot PROVE them
    independent.  Connected components are the groups; distinct groups are
    provably independent (safe to parallelise).  Reverting/weakening the
    ``compute_certificate`` call collapses provably-independent targets back
    into one group — which the fail-on-revert test asserts against.
    """
    parent: dict[str, str] = {f: f for f in files}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for i in range(len(files)):
        for j in range(i + 1, len(files)):
            cert = semantic_proof.compute_certificate(
                [files[i]],
                [files[j]],
                files[i],
                files[j],
                repo_root=repo_root,
                config_dir=config_dir,
            )
            if not cert.proven:
                union(files[i], files[j])

    groups: dict[str, list[str]] = defaultdict(list)
    for f in files:
        groups[find(f)].append(f)
    return sorted(sorted(g) for g in groups.values())


# ------------------------------------------------------------------- primitives

def _normalize(path: str) -> str:
    p = path.strip()
    if p.startswith("./"):
        p = p[2:]
    return p


def _module_file(module: str) -> str:
    return "src/charon/" + module.replace(".", "/") + ".py"
