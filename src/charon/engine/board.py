"""The work board — a durable, file-backed backlog of units (ADR-0010 D2).

A *unit* is the atom the engine assigns to a warm ACP worker: an id, a tier, the
paths it ``owns``, the units it ``depends_on``, and a coordination ``state``
(ready/claimed/done/blocked). This is COORDINATION STATE ONLY — one Charon-owned,
diffable JSON artifact (ADR-0008 §6), not a worker or a scheduler.

A unit is *claimable* iff (D2):
1. it is ``ready``;
2. every unit in its ``depends_on`` exists and is ``done``; AND
3. it shares no owned path with another running (``claimed``) unit, and is the
   lowest-``id`` member of any colliding set of dep-satisfied ``ready`` units.

Rule 3 mechanizes ``coordinator.py``'s disjoint-``owns`` collision rule: colliding
units never run concurrently, and they serialize deterministically (lowest id
first) so no two ready units deadlock each other. Owned-path overlap reuses
``land.in_scope`` (nested-or-equal), never a fresh matcher.

The board layers over the existing ``ledger`` atomic-write primitive; it adds no
new persistence subsystem.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..land import in_scope
from ..ledger import _atomic_write, validate_task_id

SCHEMA_VERSION = 1

# Coordination states. A unit moves ready -> claimed -> done; a claimed unit may
# be released back to ready (stale-claim reclaim) or sent to blocked; blocked is
# reachable from ready/claimed and returns to ready once unblocked.
READY = "ready"
CLAIMED = "claimed"
DONE = "done"
BLOCKED = "blocked"
STATES = frozenset({READY, CLAIMED, DONE, BLOCKED})

# Allowed state transitions (loud on anything else — phantom progress is refused).
_TRANSITIONS: dict[str, frozenset[str]] = {
    READY: frozenset({CLAIMED, BLOCKED, DONE}),
    CLAIMED: frozenset({DONE, READY, BLOCKED}),
    BLOCKED: frozenset({READY}),
    DONE: frozenset(),  # terminal
}


class BoardError(RuntimeError):
    """Raised when the board on disk cannot be trusted, or an op is illegal."""


def _overlap(a: list[str], b: list[str]) -> bool:
    """True iff any owned path of ``a`` is the same as, or nested under, an owned
    path of ``b`` (or vice-versa). Reuses ``land.in_scope`` so the engine and the
    land gate agree on what "shares a path" means."""
    return any(in_scope(p, b) for p in a) or any(in_scope(p, a) for p in b)


@dataclass
class Unit:
    """One assignable atom of work. ``owns``/``depends_on``/``state`` are the
    coordination fields; ``goal``/``body``/``accept`` are carried for the
    downstream run + land gate (reusing land.py's unit shape) but are not consumed
    here. ``body`` is the ticket prose intake writes into plan.json (via
    ``PlanUnit.to_dict``); the board reads it back so the work path can hand the
    agent full bearings, not just the title."""

    id: str
    tier: str = ""
    owns: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    state: str = READY
    goal: str = ""
    body: str = ""
    accept: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        validate_task_id(self.id)
        if self.state not in STATES:
            raise BoardError(f"unit {self.id!r}: unknown state {self.state!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tier": self.tier,
            "owns": list(self.owns),
            "depends_on": list(self.depends_on),
            "state": self.state,
            "goal": self.goal,
            "body": self.body,
            "accept": list(self.accept),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Unit:
        try:
            return cls(
                id=d["id"],
                tier=d.get("tier", ""),
                owns=list(d.get("owns", [])),
                depends_on=list(d.get("depends_on", [])),
                state=d.get("state", READY),
                goal=d.get("goal", ""),
                body=d.get("body", ""),
                accept=list(d.get("accept", [])),
            )
        except (KeyError, TypeError) as exc:
            raise BoardError(f"unit record malformed: {exc}") from exc


class Board:
    """A durable, file-backed backlog. CRUD + state transitions + the claimable
    predicate. Every mutation is persisted atomically (temp + fsync + replace)."""

    def __init__(self, path: Path, units: dict[str, Unit] | None = None) -> None:
        self.path = Path(path)
        self._units: dict[str, Unit] = units or {}

    # --------------------------------------------------------------- lifecycle
    @classmethod
    def create(cls, path: Path) -> Board:
        path = Path(path)
        if path.exists():
            raise BoardError(f"board already exists at {path}")
        board = cls(path)
        board._save()
        return board

    @classmethod
    def load(cls, path: Path) -> Board:
        path = Path(path)
        if not path.exists():
            raise BoardError(f"no board at {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise BoardError(f"board unreadable: {exc}") from exc
        if data.get("schema_version") != SCHEMA_VERSION:
            raise BoardError(
                f"board schema_version {data.get('schema_version')!r} not "
                f"supported (expected {SCHEMA_VERSION})"
            )
        units: dict[str, Unit] = {}
        for rec in data.get("units", []):
            unit = Unit.from_dict(rec)
            if unit.id in units:
                raise BoardError(f"duplicate unit id {unit.id!r} on board")
            units[unit.id] = unit
        return cls(path, units)

    def _save(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "units": [u.to_dict() for u in self._units.values()],
        }
        _atomic_write(self.path, json.dumps(payload, indent=2))

    # --------------------------------------------------------------------- CRUD
    def add(self, unit: Unit) -> Unit:
        if unit.id in self._units:
            raise BoardError(f"unit {unit.id!r} already on board")
        self._units[unit.id] = unit
        self._save()
        return unit

    def get(self, unit_id: str) -> Unit:
        try:
            return self._units[unit_id]
        except KeyError:
            raise BoardError(f"no unit {unit_id!r} on board") from None

    def units(self) -> list[Unit]:
        """All units, in stable id order (diffable/auditable)."""
        return [self._units[i] for i in sorted(self._units)]

    def remove(self, unit_id: str) -> None:
        if unit_id not in self._units:
            raise BoardError(f"no unit {unit_id!r} on board")
        del self._units[unit_id]
        self._save()

    # --------------------------------------------------------- state transitions
    def set_state(self, unit_id: str, state: str) -> Unit:
        unit = self.get(unit_id)
        if state not in STATES:
            raise BoardError(f"unknown state {state!r}")
        if state != unit.state and state not in _TRANSITIONS[unit.state]:
            raise BoardError(
                f"illegal transition {unit.state!r} -> {state!r} for unit {unit_id!r}"
            )
        unit.state = state
        self._save()
        return unit

    def mark_claimed(self, unit_id: str) -> Unit:
        return self.set_state(unit_id, CLAIMED)

    def mark_done(self, unit_id: str) -> Unit:
        return self.set_state(unit_id, DONE)

    def mark_blocked(self, unit_id: str) -> Unit:
        return self.set_state(unit_id, BLOCKED)

    def mark_ready(self, unit_id: str) -> Unit:
        return self.set_state(unit_id, READY)

    # ------------------------------------------------------- claimable predicate
    def _deps_done(self, unit: Unit) -> bool:
        for dep_id in unit.depends_on:
            dep = self._units.get(dep_id)
            if dep is None:
                raise BoardError(
                    f"unit {unit.id!r} depends on missing unit {dep_id!r}"
                )
            if dep.state != DONE:
                return False
        return True

    def claimable(self, unit_id: str) -> bool:
        """True iff ``unit_id`` may be claimed right now (D2 rules 1-3)."""
        unit = self.get(unit_id)
        if unit.state != READY:
            return False
        if not self._deps_done(unit):
            return False
        for other in self._units.values():
            if other.id == unit.id:
                continue
            if not _overlap(unit.owns, other.owns):
                continue
            # never run concurrently with a unit already claimed...
            if other.state == CLAIMED:
                return False
            # ...and among colliding dep-satisfied ready units, only the lowest
            # id is claimable (deterministic serialization, no deadlock).
            if other.state == READY and other.id < unit.id and self._deps_done(other):
                return False
        return True

    def _unit_depth(self, unit_id: str,
                    memo: dict[str, int] | None = None,
                    path: frozenset[str] = frozenset()) -> int:
        """Critical-path depth: longest dependency chain ending at ``unit_id``.
        A unit with no deps has depth 0; a unit that depends on a depth-*d* unit
        has depth *d*+1. Computed purely from board graph state — no clock, RNG,
        or iteration-order dependence (ADR-0015 R5 / F2)."""
        if memo is None:
            memo = {}
        if unit_id in memo:
            return memo[unit_id]
        if unit_id in path or unit_id not in self._units:
            memo[unit_id] = 0
            return 0
        deps = self._units[unit_id].depends_on
        if not deps:
            memo[unit_id] = 0
            return 0
        d = 1 + max(self._unit_depth(d, memo, path | {unit_id}) for d in deps)
        memo[unit_id] = d
        return d

    def claimable_units(self) -> list[Unit]:
        """The set of units claimable right now, pre-sorted by critical-path depth
        (deepest first) with id as the final injective tiebreak (ADR-0015 R5).

        The claimable *set* is unchanged — only the traversal order differs so the
        longest dependency chain drains first. Depth changes which ready unit a
        free worker picks first, never whether a unit is claimable."""
        claimable = [u for u in self.units() if self.claimable(u.id)]
        memo: dict[str, int] = {}
        return sorted(claimable, key=lambda u: (-self._unit_depth(u.id, memo), u.id))
