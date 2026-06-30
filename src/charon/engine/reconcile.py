"""WCI-1 static reconciler (ADR-0015 R2 / R8).

Consolidates the EXISTING redundancy / contradiction / overlap checks from
``validate_board.sh``, :meth:`board.Board.claimable`, and :func:`intake.analyze`
into ONE deterministic function. Re-port only (per R8 / M1) — no new intelligence.

Checks:
1. **bad_dep** — unit depends on a non-existent unit id.
2. **duplicate** — two units share the same branch, or two live units declare the
   identical non-empty owns set (redundancy).
3. **owns_overlap** — two non-done units whose owned paths overlap with no
   transitive dep ordering (concurrent collision).
4. **contradiction** — a live unit depends on another live unit whose owns are
   disjoint (possible false-blocking dep; per the WCI enforcer).

The ``obsolete`` kind is reserved for the semantic pass (WCI-5) — no static check
produces it in the MVP.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..land import in_scope


class FindingKind(Enum):
    DUPLICATE = "duplicate"
    OBSOLETE = "obsolete"
    CONTRADICTION = "contradiction"
    OWNS_OVERLAP = "owns_overlap"
    BAD_DEP = "bad_dep"


class Severity(Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


@dataclass(frozen=True)
class ReconcileFinding:
    unit_id: str
    kind: FindingKind
    severity: Severity
    detail: str
    related_unit_id: str | None = None


def _overlap(a: list[str], b: list[str]) -> bool:
    """True iff any path of ``a`` nests-in or equals a path of ``b`` (or vice
    versa). Reuses ``land.in_scope`` so the engine and the land gate agree."""
    return any(in_scope(p, b) for p in a) or any(in_scope(p, a) for p in b)


def _reaches(by_id: dict[str, dict[str, Any]], src: str, dst: str,
             seen: frozenset[str] | None = None) -> bool:
    """True if ``src`` transitively depends on ``dst`` through ``depends_on`` edges."""
    if seen is None:
        seen = frozenset()
    if src in seen or src not in by_id:
        return False
    seen = seen | {src}
    for dep in by_id[src].get("depends_on", []):
        if dep == dst or _reaches(by_id, dep, dst, seen):
            return True
    return False


def _normalize(unit: Any) -> dict[str, Any] | None:
    """Extract id / owns / depends_on / branch / state from a ``Unit`` or plain
    dict. Returns ``None`` when ``id`` is missing (silently skip)."""
    if isinstance(unit, dict):
        uid = unit.get("id", "")
        if not uid:
            return None
        return {
            "id": uid,
            "owns": list(unit.get("owns", [])),
            "depends_on": list(unit.get("depends_on", [])),
            "branch": unit.get("branch", ""),
            "state": unit.get("state", "ready"),
        }
    uid = getattr(unit, "id", "")
    if not uid:
        return None
    return {
        "id": uid,
        "owns": list(getattr(unit, "owns", [])),
        "depends_on": list(getattr(unit, "depends_on", [])),
        "branch": getattr(unit, "branch", ""),
        "state": getattr(unit, "state", "ready"),
    }


def reconcile_static(units: Iterable[Any],
                     board_state: dict[str, str] | None = None) -> list[ReconcileFinding]:
    """Consolidate static integrity checks across all ``units``.

    ``board_state`` is an optional ``{unit_id: state}`` override — when a unit
    carries its own ``state`` field that value wins; ``board_state`` is consulted
    as a fallback for units lacking an explicit state (reserved for future wiring,
    e.g. passed from a fleet marker directory).

    Returns a (possibly empty) list of findings. The function is deterministic: for
    the same ordered input it always returns the same ordered output.
    """
    norm: dict[str, dict[str, Any]] = {}
    for u in units:
        n = _normalize(u)
        if n is None:
            continue
        uid = n["id"]
        if board_state and n["state"] == "ready" and uid in board_state:
            n["state"] = board_state[uid]
        norm[uid] = n

    findings: list[ReconcileFinding] = []

    # 1. Bad deps — depends_on references a non-existent unit id.
    for uid, info in norm.items():
        for dep in info["depends_on"]:
            if dep not in norm:
                findings.append(ReconcileFinding(
                    unit_id=uid,
                    kind=FindingKind.BAD_DEP,
                    severity=Severity.ERROR,
                    detail=f"depends on missing unit '{dep}'",
                    related_unit_id=dep,
                ))

    # 2. Duplicate branches — two units on the same branch.
    branch_map: dict[str, list[str]] = {}
    for uid, info in norm.items():
        br = info["branch"]
        if br:
            branch_map.setdefault(br, []).append(uid)
    for br, ids in sorted(branch_map.items()):
        if len(ids) > 1:
            for uid in ids[1:]:
                findings.append(ReconcileFinding(
                    unit_id=uid,
                    kind=FindingKind.DUPLICATE,
                    severity=Severity.ERROR,
                    detail=f"duplicate branch '{br}' (also used by {ids[0]})",
                    related_unit_id=ids[0],
                ))

    # 3. Owns overlap — concurrent (non-done, non-sequenced) units sharing a path.
    live: dict[str, dict[str, Any]] = {
        uid: info for uid, info in norm.items() if info["state"] != "done"
    }
    live_ids = sorted(live)
    for i in range(len(live_ids)):
        a_id = live_ids[i]
        a = live[a_id]
        for j in range(i + 1, len(live_ids)):
            b_id = live_ids[j]
            b = live[b_id]
            if not _overlap(a["owns"], b["owns"]):
                continue
            if _reaches(live, a_id, b_id) or _reaches(live, b_id, a_id):
                continue
            findings.append(ReconcileFinding(
                unit_id=a_id,
                kind=FindingKind.OWNS_OVERLAP,
                severity=Severity.ERROR,
                detail=f"path collision with '{b_id}' — concurrent units share "
                       "owned paths without dep ordering",
                related_unit_id=b_id,
            ))

    # 4. Contradiction (WCI false-blocking dep) — live unit depends on a unit whose
    #    owns are disjoint (justified-only check; semantic judgment is WCI-5).
    for uid, info in norm.items():
        if info["state"] == "done":
            continue
        for dep in info["depends_on"]:
            if dep not in norm:
                continue  # already flagged as bad_dep
            dep_info = norm[dep]
            if _overlap(info["owns"], dep_info["owns"]):
                continue  # shared owns — plausible true dependency
            findings.append(ReconcileFinding(
                unit_id=uid,
                kind=FindingKind.CONTRADICTION,
                severity=Severity.WARN,
                detail=f"depends on '{dep}' but owns are disjoint — possibly "
                       "a false-blocking dependency (disjoint owns != a genuine "
                       "build prerequisite)",
                related_unit_id=dep,
            ))

    # 5. Redundancy — two live units with the identical non-empty owns set.
    for i in range(len(live_ids)):
        a_id = live_ids[i]
        a = live[a_id]
        for j in range(i + 1, len(live_ids)):
            b_id = live_ids[j]
            b = live[b_id]
            oa = set(a["owns"])
            ob = set(b["owns"])
            if oa and oa == ob:
                findings.append(ReconcileFinding(
                    unit_id=a_id,
                    kind=FindingKind.DUPLICATE,
                    severity=Severity.WARN,
                    detail=f"identical owns set with '{b_id}' — likely duplicate "
                           "or contradictory work",
                    related_unit_id=b_id,
                ))

    return findings
