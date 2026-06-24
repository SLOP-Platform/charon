"""Execution-port adapters. MockBackend is the deterministic proof/demo vehicle;
AcpBackend speaks the real Agent Client Protocol."""
from __future__ import annotations

from .acp import AcpBackend
from .mock import MockBackend, MockMode

__all__ = ["MockBackend", "MockMode", "AcpBackend"]
