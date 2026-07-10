"""(model × work_class) → grade capability MATRIX schema.

Consumed by EXPLORE-PROMOTE and CAPABILITY-ENGINE in downstream waves
(Wave 2+). This module defines the data shape only — the engine that
populates and queries it lands in subsequent waves.
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


@dataclass
class CapabilityMatrix:
    """(model_id, work_class) → grade lookup.

    Wave-2 consumers (EXPLORE-PROMOTE, CAPABILITY-ENGINE) read this schema
    to decide which models are eligible for which work classes. The matrix
    is built incrementally from quality-scorer observations and operator
    overrides.
    """

    entries: dict[tuple[str, WorkClass], ModelCapability] = field(default_factory=dict)

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
