"""(model × work_class) → grade capability MATRIX + provider-level quirk rules.

Consumed by EXPLORE-PROMOTE and CAPABILITY-ENGINE in downstream waves
(Wave 2+). This module defines the data shape and **statically-known**
provider quirk rules — the engine that populates and queries it from live
observations lands in subsequent waves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── capability grade vocabulary ──────────────────────────────────────────
# Grades are ordered monotonically (A > B > C > D > F).
Grade = Literal["A", "B", "C", "D", "F", "unknown"]

# ── work-class vocabulary ────────────────────────────────────────────────
# Work classes partition prompts into capability buckets that can be
# satisfied at different grade levels. ``general`` is the universal fallback.
WorkClass = Literal[
    "reasoning",
    "coding",
    "translation",
    "creative",
    "analysis",
    "general",
]


@dataclass
class ModelCapability:
    """One model's grade for one work class.

    The optional ``confidence`` (0.0–1.0) lets the scoring engine express
    certainty — useful for cold-start / explore-promote decisions.
    """

    model_id: str
    work_class: WorkClass
    grade: Grade = "unknown"
    confidence: float = 1.0


# ── statically-known provider quirk rules ────────────────────────────────
# Populated from ROUTER-DESIGN.md § Capability matrix.
# Providers listed here are KNOWN to be incapable of the given work-class
# capabilities (e.g. reasoning_content round-trip).
_DEFAULT_PROVIDER_DENIES: dict[str, set[WorkClass]] = {
    # OpenRouter does NOT return reasoning_content on the response → round-trip
    # breaks thinking-mode models (e.g. deepseek-v4-pro).
    "openrouter": {"reasoning"},
    # Novita has the same reasoning_content gap as OpenRouter.
    "novita": {"reasoning"},
}


@dataclass
class CapabilityMatrix:
    """(model_id, work_class) → grade lookup WITH provider-level quirk rules.

    Wave-2 consumers (EXPLORE-PROMOTE, CAPABILITY-ENGINE) read this schema
    to decide which models are eligible for which work classes. The matrix
    is built incrementally from quality-scorer observations and operator
    overrides, but it ALSO carries **static provider quirk rules** (e.g.
    "openrouter is incapable of reasoning") so the router can proactively
    skip known-bad providers.
    """

    entries: dict[tuple[str, WorkClass], ModelCapability] = field(default_factory=dict)
    # provider → set of denied work-classes (anything NOT denied is assumed ok)
    provider_denies: dict[str, set[WorkClass]] = field(default_factory=dict)

    def __post_init__(self):
        # Seed the built-in provider denials if the caller didn't override them.
        for prov, denied in _DEFAULT_PROVIDER_DENIES.items():
            if prov not in self.provider_denies:
                self.provider_denies[prov] = set(denied)

    # ── query API ─────────────────────────────────────────────────────────

    def get_grade(self, model_id: str, work_class: WorkClass) -> Grade:
        """Return the grade for *model_id* on *work_class*, or ``"unknown"``."""
        entry = self.entries.get((model_id, work_class))
        return entry.grade if entry else "unknown"

    def set_grade(
        self,
        model_id: str,
        work_class: WorkClass,
        grade: Grade,
        confidence: float = 1.0,
    ) -> None:
        self.entries[(model_id, work_class)] = ModelCapability(
            model_id=model_id,
            work_class=work_class,
            grade=grade,
            confidence=confidence,
        )

    def supports(self, provider: str, work_class: WorkClass) -> bool:
        """Return ``False`` when *provider* is **known-incapable** of *work_class*.

        A ``False`` means the router should proactively exclude this provider
        for requests requiring the capability. ``True`` means either
        known-capable or unknown (safe default for unlisted providers).
        """
        return work_class not in self.provider_denies.get(provider, set())

    def deny(self, provider: str, work_class: WorkClass) -> None:
        """Declare that *provider* does **not** support *work_class*."""
        self.provider_denies.setdefault(provider, set()).add(work_class)

    def allow(self, provider: str, work_class: WorkClass) -> None:
        """Explicitly remove a denial (operator override / recovery)."""
        self.provider_denies.get(provider, set()).discard(work_class)
