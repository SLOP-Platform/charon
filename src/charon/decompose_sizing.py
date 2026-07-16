"""DECOMPOSE-SIZING-OPTIMIZER — pick the optimal chunk count ``N*`` and a
balanced surface->chunk assignment for a decomposition, replacing the
decomposer's hardcoded "split into 2-4 sub-tickets" guidance with a real
wall-clock (makespan) cost model.

Pure, deterministic, stdlib-only (mirrors the rest of ``src/charon``: no
network, no clock, no RNG). Composes existing bricks, never reinvents them:

  * atomic surfaces come from the change-surface coupling graph emitted by
    ``decompose_surface.change_surface`` (DEC-AST-WRAP) — its
    ``independence_groups`` (already a union-find over the engine's
    independence certificate) is the atomic partition when present; a local
    union-find over ``call_edges``/``blast_radius`` is the fallback for
    lighter callers that only have the raw coupling edges.
  * per-surface effort uses ``decompose_effort.estimate_effort`` (the
    EFFORT-ESTIMATOR, PR #113).
  * disjointness is NOT re-derived here: atomic surfaces are file-disjoint by
    construction (union-find components), and the induced ``owns`` sets are
    still validated by ``intake.assert_disjoint_waves`` downstream (this
    module never claims to be a new collision authority).

Headline insight (see DECOMPOSE-SIZING-DESIGN.md ยง1): independent chunks run
in PARALLEL, so wall-clock is the ``max`` of their durations (a makespan),
not the ``sum`` of effort. Splitting only helps until one of three honest
ceilings is hit: parallel-worker CAPACITY, the ATOMIC FLOOR (the biggest
chunk is already a single atomic surface — it cannot be split further), or
DIMINISHING RETURNS (marginal wall-clock gain per extra chunk decays ~1/N^2
and eventually falls below ``epsilon``).

Every constant in this module (``fixed_overhead``, ``exec_rate``, ``epsilon``,
worker capacities) is a SANE SEEDED DEFAULT, explicitly flagged below as
needing calibration from the actuals ledger (``capability.actuals``,
``wall_clock_ms``) once enough real runs exist — never treated as ground
truth (ties to ``benchmark-not-a-valid-ranker``: real outcomes over guesses).
Defaults are overridable via function args or environment variables (never a
hardcoded dev-box path — REACHABILITY-GATE).
"""
from __future__ import annotations

import heapq
import json
import os
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import decompose_effort

# --------------------------------------------------------------------- constants
#
# TODO(calibration): these are sane SEEDED defaults, not measured truth. Once
# enough real (model, work_class) run data accumulates, recompute:
#   exec_rate      = median(chunk_effort / wall_clock_ms) over real runs
#   O_setup/review/merge = median observed per-chunk branch/review/merge time
# and update the defaults below (or feed calibrated values in via the
# ``overhead=``/``exec_rate=`` kwargs — this module never reads a ledger
# directly so it stays network/clock-free).

DEFAULT_EXEC_RATE = 1.0  # effort-units per minute of build time; TODO calibrate
DEFAULT_EPSILON = 0.05  # diminishing-returns margin (5% of current wallclock)

# Sane default parallel-width inputs when the caller doesn't have fleet
# config handy. Overridable via kwarg or these env vars (never a hardcoded
# dev-box path).
DEFAULT_REVIEW_CAPACITY = 4
DEFAULT_PROVIDER_CONCURRENCY = 4
ENV_REVIEW_CAPACITY = "CHARON_REVIEW_CAPACITY"
ENV_PROVIDER_CONCURRENCY = "CHARON_PROVIDER_CONCURRENCY"
ENV_EXEC_RATE = "CHARON_SIZING_EXEC_RATE"
ENV_EPSILON = "CHARON_SIZING_EPSILON"
ENV_OVERHEAD_SETUP = "CHARON_SIZING_OVERHEAD_SETUP"
ENV_OVERHEAD_REVIEW = "CHARON_SIZING_OVERHEAD_REVIEW"
ENV_OVERHEAD_MERGE = "CHARON_SIZING_OVERHEAD_MERGE"

# Exact DP/branch-and-bound assignment is only attempted below this surface
# count (see ยง3 of the design doc); above it we rely on LPT's 4/3-approx
# guarantee alone to keep this stdlib-pure module's worst case small.
EXACT_ASSIGNMENT_MAX_SURFACES = 8

StopReason = str  # "capacity" | "atomic-floor" | "diminishing-returns"


@dataclass(frozen=True)
class Overhead:
    """Per-chunk fixed overhead, paid IN PARALLEL across concurrently
    running chunks (it does not compound with ``N`` — see design ยง1/ยง2).
    Seed defaults (minutes): setup=2, review=2, merge=1 (total 5). TODO:
    calibrate from the actuals ledger once enough rows exist."""

    o_setup: float = 2.0
    o_review: float = 2.0
    o_merge: float = 1.0

    @property
    def total(self) -> float:
        return self.o_setup + self.o_review + self.o_merge


DEFAULT_OVERHEAD = Overhead()


@dataclass(frozen=True)
class AtomicSurface:
    """One atomic, file-disjoint-by-construction unit of change. ``depends_on``
    names sibling atomic-surface ids that must finish before this one starts
    (empty = independent)."""

    id: str
    files: tuple[str, ...]
    effort: float
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class SizingPlan:
    """The optimizer's recommendation: split into ``n_star`` chunks, with
    ``assignment`` mapping chunk id -> the atomic-surface ids it carries."""

    n_star: int
    assignment: dict[str, list[str]]
    chunk_efforts: dict[str, float]
    wallclock_parallel: float
    wallclock_serial: float
    per_chunk_duration: dict[str, float]
    atomic_floor_hit: bool
    stop_reason: StopReason
    rationale: str


EffortFn = Callable[[AtomicSurface], float]


# ============================================================== atomic surfaces

def atomic_surfaces(
    surface: Mapping[str, object],
    *,
    effort_fn: EffortFn | None = None,
) -> list[AtomicSurface]:
    """Derive the atomic (file-disjoint, cannot-split-below) surfaces from a
    change-surface facts mapping.

    Three accepted input shapes, checked in order:

    1. ``{"components": [{"id": ..., "files": [...], "effort": <optional>,
       "depends_on": [...]}, ...]}`` — an already-atomized, advanced/test
       entry point: full control over ids/effort/dependencies (used heavily
       by the fixtures in ``tests/test_decompose_sizing.py`` to pin exact
       wall-clock numbers independent of the noisy effort estimator).
    2. DEC-AST-WRAP's real facts shape (``decompose_surface.change_surface``
       output): ``files`` + ``independence_groups`` — each group IS an atomic
       surface (the engine already proved non-independence within a group).
    3. A lighter raw-graph shape: ``files`` + ``call_edges`` + optionally
       ``blast_radius`` (no ``independence_groups``) — atomic surfaces are the
       connected components of a local union-find over those coupling edges
       (restricted to files inside the change surface; reverting this
       union-find is what the fail-on-revert atomic-surface test catches).

    Optional top-level ``depends_on``: ``{file: [files it must run after]}``,
    lifted to the surface level (a produced surface A depends on surface B
    iff any file in A depends on any file in B, A != B).
    """
    if "components" in surface:
        return _surfaces_from_components(surface["components"], effort_fn=effort_fn)

    files = sorted({str(f) for f in _as_list(surface.get("files"))})
    if not files:
        return []

    groups_raw = surface.get("independence_groups")
    if isinstance(groups_raw, (list, tuple)) and groups_raw:
        groups = [sorted(str(f) for f in _as_list(g)) for g in groups_raw]
    else:
        groups = _union_find_groups(files, surface)

    file_deps = _normalize_file_deps(surface.get("depends_on"))
    fn = effort_fn or _default_effort_fn(surface)

    out: list[AtomicSurface] = []
    for idx, group in enumerate(sorted(groups)):
        sid = f"s{idx}:" + ",".join(group)
        deps: set[str] = set()
        for f in group:
            for dep_file in file_deps.get(f, ()):
                for other_idx, other_group in enumerate(groups):
                    if other_idx != idx and dep_file in other_group:
                        deps.add(f"s{other_idx}:" + ",".join(sorted(other_group)))
        surf_no_effort = AtomicSurface(id=sid, files=tuple(group), effort=0.0,
                                        depends_on=tuple(sorted(deps)))
        out.append(
            AtomicSurface(
                id=sid, files=tuple(group), effort=fn(surf_no_effort),
                depends_on=tuple(sorted(deps)),
            )
        )
    return out


def _surfaces_from_components(
    components: object, *, effort_fn: EffortFn | None
) -> list[AtomicSurface]:
    if not isinstance(components, (list, tuple)):
        return []
    out: list[AtomicSurface] = []
    for i, comp in enumerate(components):
        if not isinstance(comp, Mapping):
            continue
        cid = str(comp.get("id") or f"s{i}")
        cfiles = tuple(sorted(str(f) for f in _as_list(comp.get("files"))))
        cdeps = tuple(sorted(str(d) for d in _as_list(comp.get("depends_on"))))
        raw_effort = comp.get("effort")
        placeholder = AtomicSurface(id=cid, files=cfiles, effort=0.0, depends_on=cdeps)
        effort = (
            float(raw_effort)
            if raw_effort is not None
            else (effort_fn or _default_effort_fn({}))(placeholder)
        )
        out.append(AtomicSurface(id=cid, files=cfiles, effort=effort, depends_on=cdeps))
    return out


def _union_find_groups(files: list[str], surface: Mapping[str, object]) -> list[list[str]]:
    """Union-find over ``call_edges`` + ``blast_radius`` reachability,
    restricted to files that are IN the change surface. This is the coupling
    graph the design doc refers to for callers that only have the raw graph
    (not the engine's ``independence_groups``)."""
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

    fileset = set(files)
    for edge in _as_list(surface.get("call_edges")):
        pair = _as_list(edge)
        if len(pair) == 2:
            a, b = str(pair[0]), str(pair[1])
            if a in fileset and b in fileset:
                union(a, b)

    blast_radius = surface.get("blast_radius")
    if isinstance(blast_radius, Mapping):
        for src, reachable in blast_radius.items():
            if str(src) not in fileset:
                continue
            for dst in _as_list(reachable):
                if str(dst) in fileset:
                    union(str(src), str(dst))

    groups: dict[str, list[str]] = defaultdict(list)
    for f in files:
        groups[find(f)].append(f)
    return sorted(sorted(g) for g in groups.values())


def _normalize_file_deps(raw: object) -> dict[str, list[str]]:
    if not isinstance(raw, Mapping):
        return {}
    return {str(k): [str(v) for v in _as_list(v)] for k, v in raw.items()}


def _default_effort_fn(surface: Mapping[str, object]) -> EffortFn:
    """Wrap ``decompose_effort.estimate_effort`` for one atomic surface: a
    minimal duck-typed ticket (``owns`` = the surface's own files, default
    difficulty, no per-surface accept text — behaviors intentionally 0 since
    no per-surface acceptance text exists at this stage) plus the surface's
    OWN facts subset (so the SIZE signal reflects that component's real
    blast-radius/call-edge counts, not the whole ticket's)."""

    def _fn(comp: AtomicSurface) -> float:
        ticket = {"owns": list(comp.files)}
        blast_radius = surface.get("blast_radius")
        sub_facts: dict[str, object] = {
            "files": list(comp.files),
            "call_edges": [
                e for e in _as_list(surface.get("call_edges"))
                if len(_as_list(e)) == 2
                and str(_as_list(e)[0]) in comp.files
                and str(_as_list(e)[1]) in comp.files
            ],
            "blast_radius": (
                {f: v for f, v in blast_radius.items() if f in comp.files}
                if isinstance(blast_radius, Mapping) else {}
            ),
        }
        return decompose_effort.estimate_effort(ticket, sub_facts).total

    return _fn


def _as_list(v: object) -> list[Any]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return list(v)
    return [v]


# ================================================================== scheduling

def makespan(
    durations: Mapping[str, float],
    deps: Mapping[str, Sequence[str]],
    workers: int,
) -> float:
    """Precedence-constrained list-scheduling makespan of ``durations`` (chunk
    id -> duration) onto ``workers`` identical parallel workers, respecting
    ``deps`` (chunk id -> ids that must finish first). Deterministic:
    ready chunks are started in (duration DESC, id ASC) order (LPT priority)
    whenever a worker is free. Exact for the independent case; a standard
    RCPSP list-scheduling heuristic otherwise. Falls back to fully serial
    (sum of durations) if ``deps`` describes a cycle — a defensive floor, not
    a silent underestimate.
    """
    ids = sorted(durations)
    if not ids:
        return 0.0
    workers = max(1, workers)

    indeg: dict[str, int] = {i: 0 for i in ids}
    dependents: dict[str, list[str]] = {i: [] for i in ids}
    dep_map = {i: list(deps.get(i, ())) for i in ids}
    for i in ids:
        for d in dep_map[i]:
            if d in indeg:
                dependents[d].append(i)
                indeg[i] += 1

    if _has_cycle(ids, dep_map):
        return sum(durations.values())

    remaining = dict(indeg)
    pending_ready = sorted(
        (i for i in ids if remaining[i] == 0), key=lambda i: (-durations[i], i)
    )
    free_at = [0.0] * workers
    heap: list[tuple[float, str]] = []
    finish_time: dict[str, float] = {}
    time_cursor = 0.0

    while len(finish_time) < len(ids):
        free_idxs = [w for w, t in enumerate(free_at) if t <= time_cursor + 1e-9]
        pending_ready.sort(key=lambda i: (-durations[i], i))
        while free_idxs and pending_ready:
            w = free_idxs.pop(0)
            cid = pending_ready.pop(0)
            f = time_cursor + durations[cid]
            free_at[w] = f
            heapq.heappush(heap, (f, cid))
        if not heap:
            # Nothing running, nothing ready, chunks remain: only possible via
            # a dependency graph bug upstream. Defensive serial floor.
            remaining_ids = [i for i in ids if i not in finish_time]
            return time_cursor + sum(durations[i] for i in remaining_ids)
        f = heap[0][0]
        finished_now = []
        while heap and heap[0][0] <= f + 1e-9:
            finished_now.append(heapq.heappop(heap)[1])
        time_cursor = f
        for cid in sorted(finished_now):
            finish_time[cid] = f
            for nxt in dependents[cid]:
                remaining[nxt] -= 1
                if remaining[nxt] == 0:
                    pending_ready.append(nxt)

    return max(finish_time.values())


def _has_cycle(ids: list[str], deps: Mapping[str, list[str]]) -> bool:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {i: WHITE for i in ids}

    def visit(node: str) -> bool:
        color[node] = GRAY
        for d in deps.get(node, ()):
            if d not in color:
                continue
            if color[d] == GRAY:
                return True
            if color[d] == WHITE and visit(d):
                return True
        color[node] = BLACK
        return False

    return any(color[i] == WHITE and visit(i) for i in ids)


# ================================================================= assignment

def lpt_assign(surfaces: Sequence[AtomicSurface], n: int) -> dict[str, list[str]]:
    """Longest-Processing-Time-first greedy bin packing of ``surfaces`` into
    exactly ``n`` chunks, minimizing (approximately, 4/3-competitive) the max
    chunk effort. Deterministic: ties broken by surface id, then by chunk id
    for the least-loaded pick."""
    chunk_ids = [f"c{i + 1}" for i in range(n)]
    loads = {c: 0.0 for c in chunk_ids}
    assignment: dict[str, list[str]] = {c: [] for c in chunk_ids}
    ordered = sorted(surfaces, key=lambda s: (-s.effort, s.id))
    for s in ordered:
        target = min(chunk_ids, key=lambda c: (loads[c], c))
        assignment[target].append(s.id)
        loads[target] += s.effort
    return assignment


def exact_assign(surfaces: Sequence[AtomicSurface], n: int) -> dict[str, list[str]] | None:
    """Exact minimum-makespan assignment via branch-and-bound, only attempted
    for <= :data:`EXACT_ASSIGNMENT_MAX_SURFACES` surfaces (keeps this
    stdlib-pure module's worst case bounded). Returns ``None`` above that
    size (caller then relies on :func:`lpt_assign` alone)."""
    if len(surfaces) > EXACT_ASSIGNMENT_MAX_SURFACES or n <= 0:
        return None
    ordered = sorted(surfaces, key=lambda s: (-s.effort, s.id))
    chunk_ids = [f"c{i + 1}" for i in range(n)]

    best: dict[str, Any] = {"max_load": float("inf"), "assign": None}
    loads = [0.0] * n
    assign_idx: list[int] = []

    def recurse(pos: int) -> None:
        if pos == len(ordered):
            cur_max = max(loads) if loads else 0.0
            if cur_max < best["max_load"] - 1e-9:
                best["max_load"] = cur_max
                best["assign"] = list(assign_idx)
            return
        cur_partial_max = max(loads[: len(assign_idx)] or [0.0])
        if cur_partial_max >= best["max_load"]:
            return
        tried_empty = False
        for ci in sorted(range(n), key=lambda c: loads[c]):
            if loads[ci] == 0.0:
                if tried_empty:
                    continue
                tried_empty = True
            loads[ci] += ordered[pos].effort
            assign_idx.append(ci)
            recurse(pos + 1)
            assign_idx.pop()
            loads[ci] -= ordered[pos].effort

    recurse(0)
    if best["assign"] is None:
        return None
    assignment: dict[str, list[str]] = {c: [] for c in chunk_ids}
    for surf, ci in zip(ordered, best["assign"], strict=True):
        assignment[chunk_ids[ci]].append(surf.id)
    return assignment


def best_assignment(surfaces: Sequence[AtomicSurface], n: int) -> dict[str, list[str]]:
    """The better of :func:`lpt_assign` and (when small enough)
    :func:`exact_assign`, by max chunk effort."""
    lpt = lpt_assign(surfaces, n)
    by_id = {s.id: s for s in surfaces}
    lpt_max = _max_load(lpt, by_id)
    exact = exact_assign(surfaces, n)
    if exact is None:
        return lpt
    exact_max = _max_load(exact, by_id)
    return exact if exact_max <= lpt_max else lpt


def _max_load(assignment: Mapping[str, list[str]], by_id: Mapping[str, AtomicSurface]) -> float:
    if not assignment:
        return 0.0
    return max(sum(by_id[sid].effort for sid in ids) for ids in assignment.values())


def _lift_chunk_dag(
    assignment: Mapping[str, list[str]], by_id: Mapping[str, AtomicSurface]
) -> dict[str, list[str]]:
    """Chunk A depends on chunk B iff any surface in A depends on any surface
    in B (A != B)."""
    surface_to_chunk = {sid: c for c, ids in assignment.items() for sid in ids}
    dag: dict[str, set[str]] = {c: set() for c in assignment}
    for c, ids in assignment.items():
        for sid in ids:
            for dep in by_id[sid].depends_on:
                dep_chunk = surface_to_chunk.get(dep)
                if dep_chunk is not None and dep_chunk != c:
                    dag[c].add(dep_chunk)
    return {c: sorted(v) for c, v in dag.items()}


def _atomic_floor_hit(
    assignment: Mapping[str, list[str]],
    by_id: Mapping[str, AtomicSurface],
    atomic_max: float,
) -> bool:
    """True iff the FINAL chosen assignment's biggest chunk is literally a
    single atomic surface carrying the global maximum effort — the honest
    can't-split-below ceiling (design ยง2). This is a distinct, separately
    load-bearing check from the mid-search ``at_floor`` early-stop: it is
    what a single-monolith ticket (N*==1 trivially, loop never even runs)
    still needs in order to report the ceiling honestly."""
    if _max_load(assignment, by_id) > atomic_max + 1e-9:
        return False
    return any(
        len(ids) == 1 and by_id[ids[0]].effort >= atomic_max - 1e-9
        for ids in assignment.values()
    )


def _parallel_width(review_capacity: int, provider_concurrency: int, n_surfaces: int) -> int:
    """The CAPACITY ceiling ``W`` (design ยง1): the number of chunks that can
    genuinely execute at once. Never more than the review capacity, the
    provider's concurrency limit, or the number of atomic surfaces there are
    to split (splitting past the surface count is meaningless). This is the
    hard ceiling ``N* <= W`` — reverting/bypassing this clamp is what lets
    the optimizer recommend more chunks than can ever run in parallel."""
    return max(1, min(review_capacity, provider_concurrency, n_surfaces))


def _chunk_durations(
    assignment: Mapping[str, list[str]],
    by_id: Mapping[str, AtomicSurface],
    overhead: Overhead,
    exec_rate: float,
) -> dict[str, float]:
    out = {}
    for c, ids in assignment.items():
        effort = sum(by_id[sid].effort for sid in ids)
        out[c] = overhead.total + (effort / exec_rate if exec_rate > 0 else 0.0)
    return out


# ============================================================ N* selection

def size_decomposition(
    surface: Mapping[str, object],
    *,
    effort_fn: EffortFn | None = None,
    review_capacity: int | None = None,
    provider_concurrency: int | None = None,
    overhead: Overhead = DEFAULT_OVERHEAD,
    exec_rate: float | None = None,
    epsilon: float | None = None,
) -> SizingPlan:
    """The public entry point: pick ``N*`` and a balanced surface->chunk
    assignment for ``surface`` (a change-surface facts mapping, see
    :func:`atomic_surfaces` for accepted shapes).

    Returns a :class:`SizingPlan`. An empty change surface yields the trivial
    zero-work plan (``n_star=0``) rather than raising — callers decide what
    "nothing to decompose" means for them.
    """
    surfaces = atomic_surfaces(surface, effort_fn=effort_fn)
    review_capacity = _resolve_int(review_capacity, ENV_REVIEW_CAPACITY, DEFAULT_REVIEW_CAPACITY)
    provider_concurrency = _resolve_int(
        provider_concurrency, ENV_PROVIDER_CONCURRENCY, DEFAULT_PROVIDER_CONCURRENCY
    )
    exec_rate = _resolve_float(exec_rate, ENV_EXEC_RATE, DEFAULT_EXEC_RATE)
    epsilon = _resolve_float(epsilon, ENV_EPSILON, DEFAULT_EPSILON)

    if not surfaces:
        return SizingPlan(
            n_star=0, assignment={}, chunk_efforts={}, wallclock_parallel=0.0,
            wallclock_serial=0.0, per_chunk_duration={}, atomic_floor_hit=False,
            stop_reason="capacity", rationale="empty change surface: nothing to size",
        )

    by_id = {s.id: s for s in surfaces}
    w = _parallel_width(review_capacity, provider_concurrency, len(surfaces))
    atomic_max = max(s.effort for s in surfaces)

    def plan_for(n: int) -> tuple[dict[str, list[str]], float, dict[str, float]]:
        assignment = best_assignment(surfaces, n)
        durations = _chunk_durations(assignment, by_id, overhead, exec_rate)
        dag = _lift_chunk_dag(assignment, by_id)
        wc = makespan(durations, dag, w)
        return assignment, wc, durations

    n_star = 1
    assignment, wallclock, durations = plan_for(1)
    wallclock_serial = wallclock
    best_assignment_seen = assignment
    best_durations = durations
    stop_reason: StopReason = "capacity"

    # Scan every candidate N up to the capacity ceiling W, comparing each
    # against the last ACCEPTED baseline (not merely N-1): bin-packing is a
    # step function, so a non-improving N (e.g. 4 equal-sized atomic units
    # into 3 bins forces a 2+1+1 lump, same max-load as 2 bins) must not
    # permanently stop the search — the next N can still clear the epsilon
    # bar over the last real improvement (operator's worked example: 2->3
    # is flat, but 2->4 is a genuine 40% cut). We only hard-stop early on
    # the atomic floor, since no further N can ever help once hit.
    for n in range(2, w + 1):
        cand_assignment, cand_wc, cand_durations = plan_for(n)
        max_load = _max_load(cand_assignment, by_id)
        at_floor = max_load <= atomic_max + 1e-9
        delta = wallclock - cand_wc
        improves = delta >= epsilon * wallclock if wallclock > 0 else delta > 0

        if improves:
            n_star = n
            wallclock = cand_wc
            best_assignment_seen = cand_assignment
            best_durations = cand_durations

        if at_floor:
            # Nothing beyond this N can ever help (the biggest chunk is
            # already a single atomic surface) — stop scanning either way.
            # But the HONEST reason differs: if this floor candidate itself
            # cleared epsilon, the floor is why we stop; if it didn't, the
            # real reason we settled on the last accepted N is diminishing
            # returns (the floor is just why continuing further is moot).
            stop_reason = "atomic-floor" if improves else "diminishing-returns"
            break
    else:
        stop_reason = "capacity" if n_star == w else "diminishing-returns"

    atomic_floor_hit = _atomic_floor_hit(best_assignment_seen, by_id, atomic_max)
    if atomic_floor_hit:
        stop_reason = "atomic-floor"

    chunk_efforts = {
        c: sum(by_id[sid].effort for sid in ids) for c, ids in best_assignment_seen.items()
    }
    rationale = _rationale(
        n_star=n_star, w=w, wallclock=wallclock, wallclock_serial=wallclock_serial,
        stop_reason=stop_reason, atomic_max=atomic_max, atomic_floor_hit=atomic_floor_hit,
    )

    kept = {c: ids for c, ids in best_assignment_seen.items() if ids}
    return SizingPlan(
        n_star=n_star,
        assignment={c: list(ids) for c, ids in kept.items()},
        chunk_efforts={c: chunk_efforts[c] for c in kept},
        wallclock_parallel=wallclock,
        wallclock_serial=wallclock_serial,
        per_chunk_duration={c: best_durations[c] for c in kept},
        atomic_floor_hit=atomic_floor_hit,
        stop_reason=stop_reason,
        rationale=rationale,
    )


def _rationale(
    *, n_star: int, w: int, wallclock: float, wallclock_serial: float,
    stop_reason: StopReason, atomic_max: float, atomic_floor_hit: bool,
) -> str:
    parts = [
        f"N*={n_star} (parallel width W={w}): est wall-clock {wallclock:.2f} vs "
        f"{wallclock_serial:.2f} serial (N=1).",
    ]
    if stop_reason == "capacity":
        parts.append(f"stopped: reached parallel-worker capacity (W={w}).")
    elif stop_reason == "atomic-floor":
        parts.append(
            f"stopped: the largest chunk is already a single atomic surface "
            f"(effort={atomic_max:g}) — cannot split further without breaking "
            f"file-disjointness."
        )
    else:
        parts.append("stopped: marginal wall-clock gain from one more chunk fell below epsilon.")
    if atomic_floor_hit:
        parts.append("atomic floor reached.")
    return " ".join(parts)


def _resolve_int(value: int | None, env_var: str, default: int) -> int:
    if value is not None:
        return int(value)
    raw = os.environ.get(env_var)
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


def _resolve_float(value: float | None, env_var: str, default: float) -> float:
    if value is not None:
        return float(value)
    raw = os.environ.get(env_var)
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return default


def _resolve_overhead() -> Overhead:
    def _f(env_var: str, default: float) -> float:
        raw = os.environ.get(env_var)
        if raw:
            try:
                return float(raw)
            except ValueError:
                pass
        return default

    return Overhead(
        o_setup=_f(ENV_OVERHEAD_SETUP, DEFAULT_OVERHEAD.o_setup),
        o_review=_f(ENV_OVERHEAD_REVIEW, DEFAULT_OVERHEAD.o_review),
        o_merge=_f(ENV_OVERHEAD_MERGE, DEFAULT_OVERHEAD.o_merge),
    )


def plan_to_dict(plan: SizingPlan) -> dict[str, object]:
    """JSON-friendly rendering matching the CLI/F46-gate contract."""
    return {
        "n_star": plan.n_star,
        "assignment": plan.assignment,
        "est_wallclock": plan.wallclock_parallel,
        "serial_wallclock": plan.wallclock_serial,
        "chunk_efforts": plan.chunk_efforts,
        "per_chunk_duration": plan.per_chunk_duration,
        "atomic_floor_hit": plan.atomic_floor_hit,
        "stop_reason": plan.stop_reason,
        "rationale": plan.rationale,
    }


# ======================================================================= CLI

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m charon.decompose_sizing",
        description="DECOMPOSE-SIZING-OPTIMIZER: recommend N* and a balanced "
        "surface->chunk assignment for a change-surface facts file.",
    )
    parser.add_argument(
        "--surface", required=True,
        help="path to a change-surface facts JSON file (decompose_surface.change_surface "
        "shape, or {'components': [...]} advanced shape)",
    )
    parser.add_argument("--review-capacity", type=int, default=None)
    parser.add_argument("--provider-concurrency", type=int, default=None)
    parser.add_argument("--exec-rate", type=float, default=None)
    parser.add_argument("--epsilon", type=float, default=None)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    with open(args.surface, encoding="utf-8") as fh:
        facts = json.load(fh)

    plan = size_decomposition(
        facts,
        review_capacity=args.review_capacity,
        provider_concurrency=args.provider_concurrency,
        overhead=_resolve_overhead(),
        exec_rate=args.exec_rate,
        epsilon=args.epsilon,
    )

    if args.json:
        print(json.dumps(plan_to_dict(plan), indent=2, sort_keys=True))
    else:
        print(plan.rationale)
        for c, ids in plan.assignment.items():
            print(f"  {c}: {ids} (effort={plan.chunk_efforts.get(c, 0):g})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
