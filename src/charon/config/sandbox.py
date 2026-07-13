"""Worker sandbox policy (D013 / ADR-0010)."""
from __future__ import annotations

import enum
import os
from collections.abc import Mapping


class SandboxPolicy(enum.StrEnum):
    """Worker sandbox posture (D013 / ADR-0010).

    ``hybrid``   — default; host OK for ≤L1, container or loud override required for L2+.
    ``container`` — ALL rungs ≥L1 require the verified container; uncontained override refused.
    ``host``      — host is declared; L0/L1 free; L2+ requires the loud override flag
                    (container flag alone is not sufficient — explicit acknowledgement required).
    """

    HYBRID = "hybrid"
    CONTAINER = "container"
    HOST = "host"


_SANDBOX_ENV = "CHARON_SANDBOX"


def load_sandbox_policy(env: Mapping[str, str] | None = None) -> SandboxPolicy:
    """Read the active sandbox policy from ``CHARON_SANDBOX`` (or ``env``).

    Unknown values fall back to ``hybrid`` so a misconfigured var never silently
    weakens the gate — it reverts to the safe default."""
    e = os.environ if env is None else env
    raw = e.get(_SANDBOX_ENV, SandboxPolicy.HYBRID.value).lower()
    try:
        return SandboxPolicy(raw)
    except ValueError:
        return SandboxPolicy.HYBRID
