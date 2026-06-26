"""Continuity plane — the handoff contract (ADR-0001 §4 / ADR-0003 §4).

The H-predicates as code. Tier 1 builds and unit-tests these against the mock;
live cross-vendor handoff is Tier 2 (reconciliation OOB-C1). The portable unit
is always ``(files-on-disk + ledger entry)`` — never a vendor's internal
session (H2/H3).
"""
from __future__ import annotations

from dataclasses import dataclass

from .ledger import Ledger
from .router import Route, StaticRouter

_REQUIRED_FIELDS = ("goal", "acceptance", "target_repo", "base_ref", "lkg_ref")


@dataclass
class Resumability:
    ok: bool
    missing: list[str]


def is_resumable(ledger: Ledger) -> Resumability:
    """H1: a unit is resumable iff its ledger entry is complete. A unit lacking
    any required field is NOT handoff-eligible and must be repaired first."""
    missing = [f for f in _REQUIRED_FIELDS if not getattr(ledger, f, None)]
    if not ledger.acceptance:
        missing.append("acceptance(empty)")
    return Resumability(ok=not missing, missing=missing)


def rehydrate_remaining(ledger: Ledger) -> set[str]:
    """H3: derive ``remaining`` from ledger + disk alone. Idempotent and
    provider-independent — any backend computes the same set because acceptance
    is executable (INV-6)."""
    return ledger.remaining()


def choose_next_backend(
    router: StaticRouter, task_class: str, exclude: set[str]
) -> Route:
    """H6: the next provider is chosen by re-running the router with **all**
    exhausted providers excluded — not a static fallback list, and not just the
    most-recently-exhausted one (reconciliation BR2-4: excluding only the last
    one can re-pick an already-exhausted backend when ≥2 are down)."""
    return router.route(task_class, exclude=set(exclude))
