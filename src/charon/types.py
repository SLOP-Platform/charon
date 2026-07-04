"""Core value types shared across the harness.

These are deliberately small and JSON-serializable: the Work Ledger persists
them, and three public surfaces (CLI / Python API / HTTP service) exchange them.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Tier(enum.Enum):
    """Capability tier a unit is routed to. Maps to model strength."""

    LOW = "low"
    MED = "med"
    HIGH = "high"


class Autonomy(enum.IntEnum):
    """Operator-set autonomy ladder (ADR-0001 §6 / ADR-0003 §7).

    Ordered so that ``level >= required`` is a valid gate test.
    """

    L0 = 0  # propose-only: diffs produced, nothing applied
    L1 = 1  # apply reversible: commit in worktree, lkg rollback; no delete/deploy
    L2 = 2  # apply with consensus
    L3 = 3  # full-auto within fence


class PrivilegedOp(enum.Enum):
    """The privileged actions that must cross the control-plane fence."""

    PROPOSE = "propose"
    APPLY_REVERSIBLE = "apply_reversible"
    DELETE = "delete"
    DEPLOY = "deploy"


@dataclass(frozen=True)
class Budget:
    """Bounds a run so 'always working' cannot mean 'unbounded cost'.

    ``max_cost_usd`` / ``max_tokens`` are CUMULATIVE caps across checkpoints
    (Tier 3): the coordinator stops before the next dispatch would exceed them.
    ``None`` means uncapped on that axis."""

    max_checkpoints: int = 8
    max_seconds: int | None = None
    max_cost_usd: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class Usage:
    """Resource spend reported by a backend for one dispatch (Tier 3).

    Vendor-neutral and additive: the ledger sums these across checkpoints, so
    cumulative cost is derived truth (INV-1 extended to cost), the same for any
    backend that picks the task up (H3-for-cost). Live numbers come from ACP
    ``session/usage``; the mock reports deterministic values to prove the
    accounting contract. All-zero by default (a backend that reports nothing
    costs nothing in the ledger, honestly)."""

    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    def to_dict(self) -> dict:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> Usage | None:
        if not d:
            return None
        return cls(
            tokens_in=int(d.get("tokens_in", 0)),
            tokens_out=int(d.get("tokens_out", 0)),
            cost_usd=float(d.get("cost_usd", 0.0)),
            latency_ms=int(d.get("latency_ms", 0)),
        )


@dataclass(frozen=True)
class Health:
    """A backend's self-reported state, used for exhaustion detection (H4)."""

    budget_remaining: bool = True
    rate_limited: bool = False
    context_pressure: bool = False

    @property
    def exhausted(self) -> bool:
        return (not self.budget_remaining) or self.rate_limited or self.context_pressure


@dataclass(frozen=True)
class CapSet:
    """Task-classes a backend declares competence at."""

    classes: frozenset[str] = field(default_factory=frozenset)

    def covers(self, task_class: str) -> bool:
        return not self.classes or task_class in self.classes


@dataclass(frozen=True)
class WorkUnit:
    """One dispatchable unit of work.

    ``body`` and ``accept_text`` carry the ticket's full bearings (the prose
    description and the acceptance criteria) so a backend can give the dispatched
    agent more than the one-line ``goal``. They live on the base type — not on an
    orchestrator-layer subclass — so the engine work path can populate them
    without importing ``api`` (which would trip the engine→orchestrator boundary
    guard). Both default to empty, so plain ``goal``-only callers are unaffected."""

    task_id: str
    goal: str
    task_class: str = "codegen"
    role: str = "coder"  # selects the model-pool for cross-model failover (ADR-0004)
    body: str = ""  # ticket prose; full bearings beyond the one-line goal
    accept_text: str = ""  # acceptance criteria text (the gate's checks, joined)


class OutcomeStatus(enum.Enum):
    PROGRESSED = "progressed"  # made changes toward acceptance
    BLOCKED = "blocked"  # could not progress
    EXHAUSTED = "exhausted"  # backend ran out (handoff signal)


@dataclass
class Outcome:
    """What a single dispatch produced. Adapters report this to the Ledger;
    they never own progress truth (ADR-0003 §3)."""

    status: OutcomeStatus
    provider: str
    # commit SHA in the target repo produced by this dispatch, if any.
    commit: str | None = None
    note: str = ""
    # Resource spend for this dispatch (Tier 3); None if the backend reports none.
    usage: Usage | None = None


# ── Gateway feature types (ADOPT-GATEWAY-FEATURES Track B) ──────────────


@dataclass(frozen=True)
class CachedResponse:
    """In-memory cache entry: raw upstream response bytes + metadata."""

    content: bytes
    headers: dict = field(default_factory=dict)
    created_at: float = 0.0
    ttl: float = 300.0


@dataclass
class CacheStats:
    """Snapshot of cache state for operator inspection."""

    hits: int = 0
    misses: int = 0
    size: int = 0
    evictions: int = 0


@dataclass(frozen=True)
class RequestHints:
    """Lightweight request inspection — cheap enough for every call."""

    has_images: bool = False
    has_tools: bool = False
    estimated_tokens: int = 0
    preferred_context_window: int | None = None


@dataclass(frozen=True)
class SpendDecision:
    """Result of a pre-flight spend-cap check."""

    allowed: bool
    remaining: float
    reason: str = ""


class ObsTarget(enum.Enum):
    """Observability export backends."""

    JSONL = "jsonl"
    PROMETHEUS = "prometheus"
    WEBHOOK = "webhook"
    LANGFUSE = "langfuse"


@dataclass(frozen=True)
class ObsEvent:
    """One observability event emitted at a gateway hook point."""

    event_type: str
    provider: str | None = None
    model: str | None = None
    timestamp: float = 0.0
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GuardrailViolation:
    """A single guardrail hit — request or response."""

    severity: str  # "WARN" or "BLOCK"
    pattern: str
    location: str
    message: str = ""


@dataclass
class QualityRecord:
    """Persistent per-provider quality data."""

    provider: str = ""
    calls: int = 0
    successes: int = 0
    latency_ewma_ms: float = 0.0
    reliability_score: float = 0.5  # bootstrap default (cold-start safe)
