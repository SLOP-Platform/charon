"""Charon — a thin orchestrator that ferries a unit of work across swappable
coding-agent backends, keeping one vendor-neutral Work Ledger as the single
source of truth.

This package has ZERO knowledge of any host project (ADR-0002 INV-B1/B5). The runtime guard
below fails loudly if a host project was somehow pulled into the process.
"""
from __future__ import annotations

import sys

try:  # version is owned by pyproject.toml; never duplicated as a literal here
    from importlib.metadata import version as _version

    __version__ = _version("charon")
except Exception:  # pragma: no cover - source checkout without install
    __version__ = "0+unknown"

# ADR-0002 INV-B5 runtime guard: Charon must never share a process with a host project.
if "slop" in sys.modules:  # pragma: no cover - defensive
    raise RuntimeError(
        "charon imported alongside 'slop' — boundary violation (ADR-0002 INV-B1/B5)"
    )

__all__ = ["__version__"]
