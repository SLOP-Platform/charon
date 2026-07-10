"""Capability tracking — actuals ledger and freeze-ring scorecard.

These modules record real outcomes from headless charon sub-sessions and
provide a freeze-ring reader that returns the latest good scorecard artifact
with a last-known-good fallback. They live in their own sub-package to isolate
the scorecard's freeze-ring protocol from the ledgers and quality scorers used
by the main orchestrator path.
"""
from __future__ import annotations
