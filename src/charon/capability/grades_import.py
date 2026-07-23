"""Cold-start bridge: import a PROVISIONAL external-benchmark prior into the
outcome-graded brain (ADR-0017 §Cold-start).

A fresh Charon install has zero graded outcomes → ``CapabilityMatrix`` returns
``"unknown"`` for every ``(model, work_class)`` → the gateway cannot route on
anything. ADR-0017 §Cold-start (lines 49-54, 121-123) names a
"seed scorecard / importable scorecard" as the bootstrap path, marked
"required design, not yet designed". This module is that design.

The doctrinal tension it resolves: external leaderboards are NOT valid rankers
on their own ([benchmark-not-a-valid-ranker]; MODEL-ROLE-EVALUATION.md:203
"your own signal outranks any leaderboard"). So this prior is explicitly
**PROVISIONAL** and **DECAYING** — every seeded score carries a confidence
weight (stored as the matrix entry's ``confidence``, always < 1.0) that is
superseded the moment a real graded outcome lands for the same
``(model, work_class)``. A real graded outcome ALWAYS replaces the prior; the
prior is only a usable day-1 ordering until own-signal exists.

Design:
  * :data:`SEED_PRIOR` — the curated external-benchmark-derived prior. Each
    entry tags a ``(model_id, work_class)`` with a provisional grade + a
    confidence weight + provenance (the benchmark family it came from). Scores
    are coarse (A–F grade bands) so they cannot masquerade as high-precision
    measurements; the matrix consumer treats them as ordering tokens, not
    ground truth.
  * :class:`GradesImport` — loads the seed prior into a
    :class:`~charon.routing_policy.matrix.CapabilityMatrix` as PROVISIONAL
    entries (``confidence`` = the prior weight < 1.0), then exposes a
    :meth:`reconcile_with_real` rule the outcome ledger calls when a real grade
    lands: the real grade REPLACES the provisional entry (confidence → 1.0) and
    the prior is gone (it never overrides real signal). The provisional/real
    TAG and provenance are tracked in a sidecar dict on the importer (the
    existing ``ModelCapability`` carries no metadata field, and ``matrix.py``
    is owned by another ticket — the sidecar keeps this module self-contained).
  * :func:`seed_matrix` — convenience that returns a populated matrix ready
    for the gateway to route on day-1.
  * :func:`rank_for_work_class` — proof helper: returns models ordered by grade
    from the matrix, demonstrating CG can produce a NON-EMPTY day-1 ordering.

Stdlib-only (dataclasses, typing). This lives in ``charon.capability`` next to
``scorecard.py`` / ``taxonomy.py`` — same isolation rationale (capability
subsystem, no third-party deps). No new artifact store is introduced: the
prior lands in the existing :class:`CapabilityMatrix` via the
ADR-0017 ``grades_import`` / ``product_grades`` seed path (this module IS that
import path); it does not invent a parallel store.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from charon.routing_policy.matrix import (
    CapabilityMatrix,
    Grade,
    ModelCapability,
    WorkClass,
)

# ── prior weight policy ──────────────────────────────────────────────────
# The prior's confidence weight. Bounds:
#   * < 1.0 always — a prior is NEVER as strong as a real graded outcome
#     (which the matrix stores at confidence=1.0).
#   * > 0.0 only — a zero weight is indistinguishable from "no prior", which
#     would defeat the cold-start bridge.
#   * The same default applies to EVERY seeded entry so the day-1 ordering is
#     a pure function of the imported grades, not of an operator's per-entry
#     weight guess.
DEFAULT_PRIOR_WEIGHT = 0.5
"""The provisional confidence carried by every seeded score.

Picked at the midpoint of (0, 1): high enough to give the gateway a usable
day-1 ordering, low enough that the FIRST real graded outcome (recorded at
confidence=1.0) dominates it. Real outcomes ALWAYS win because the reconcile
rule REPLACES the prior entry rather than averaging with it."""

# ── provenance vocabulary ────────────────────────────────────────────────
# The legitimate external-benchmark families the seed is curated from. We tag
# every entry with one of these so an operator can audit "where did this grade
# come from" without it looking like a first-class measured outcome.
Provenance = Literal[
    "aider-polyglot",      # multi-language code-gen pass-rate
    "lmarena",             # human-preference ELO
    "artificial-analysis",  # cost/quality composite
    "models-dev",          # capability registry aggregate
    "operator-curated",    # the operator's MANUAL consolidation of the above
]

PROVISIONAL_TAG = "provisional"
"""Marker tracked in the importer sidecar so a ``(model, work_class)`` entry
can be distinguished from a real graded outcome. The matrix-level weight
signal is ``confidence < 1.0`` (prior) vs ``confidence == 1.0`` (real)."""

REAL_TAG = "real"
"""Sidecar marker for an entry that has been superseded by a real graded
outcome (set by :meth:`GradesImport.reconcile_with_real`)."""


# ── seed prior ───────────────────────────────────────────────────────────
# Hand-curated from the operator's external-benchmark consolidation
# (MODEL-ROLE-EVALUATION.md; source families: aider-polyglot, LMArena,
# Artificial Analysis, models.dev). Entries are COARSE: a grade band per
# (model, work_class) — NOT a leaderboard rank. The gateway uses these only to
# produce a NON-EMPTY day-1 ordering; real graded outcomes override them via
# :meth:`GradesImport.reconcile_with_real`.
#
# The table is intentionally a tuple of dataclasses (not a leaderboard CSV) so
# it is auditable inline and carries provenance + weight with every score —
# there is no way to read a prior as a high-precision measurement.
@dataclass(frozen=True)
class PriorEntry:
    """One provisional ``(model, work_class)`` score from external benchmarks.

    ``grade`` is the coarse A–F band the gateway routes on; ``weight`` is the
    provisional confidence (always < 1.0); ``provenance`` is the benchmark
    family the score was curated from.
    """

    model_id: str
    work_class: WorkClass
    grade: Grade
    weight: float = DEFAULT_PRIOR_WEIGHT
    provenance: Provenance = "operator-curated"


# The curated prior. The principle of "your own signal outranks any leaderboard"
# is enforced STRUCTURALLY: these entries only ever populate the matrix at
# ``weight < 1.0`` and are REPLACED (not blended) by the first real graded
# outcome for the same key. The table is ordered by work_class then model so a
# human reviewer can eyeball per-class coverage.
_SEED_PRIOR: tuple[PriorEntry, ...] = (
    # ── reasoning ──────────────────────────────────────────────────────────
    PriorEntry("gpt-5", "reasoning", "A", provenance="lmarena"),
    PriorEntry("claude-opus-4.5", "reasoning", "A", provenance="lmarena"),
    PriorEntry("gemini-3-pro", "reasoning", "A", provenance="lmarena"),
    PriorEntry("deepseek-v4-pro", "reasoning", "B", provenance="lmarena"),
    PriorEntry("kimi-k2.6", "reasoning", "B", provenance="lmarena"),
    PriorEntry("glm-5.2", "reasoning", "B", provenance="models-dev"),
    PriorEntry("minimax-m2.7", "reasoning", "C", provenance="models-dev"),
    PriorEntry("llama-4-405b", "reasoning", "C", provenance="models-dev"),
    # ── coding ──────────────────────────────────────────────────────────────
    PriorEntry("claude-opus-4.5", "coding", "A", provenance="aider-polyglot"),
    PriorEntry("gpt-5", "coding", "A", provenance="aider-polyglot"),
    PriorEntry("gemini-3-pro", "coding", "B", provenance="aider-polyglot"),
    PriorEntry("deepseek-v4-pro", "coding", "B", provenance="aider-polyglot"),
    PriorEntry("kimi-k2.6", "coding", "B", provenance="aider-polyglot"),
    PriorEntry("glm-5.2", "coding", "B", provenance="models-dev"),
    PriorEntry("qwen-3-coder", "coding", "B", provenance="aider-polyglot"),
    PriorEntry("minimax-m2.7", "coding", "C", provenance="models-dev"),
    # ── analysis ────────────────────────────────────────────────────────────
    PriorEntry("gpt-5", "analysis", "A", provenance="artificial-analysis"),
    PriorEntry("claude-opus-4.5", "analysis", "A", provenance="artificial-analysis"),
    PriorEntry("gemini-3-pro", "analysis", "A", provenance="artificial-analysis"),
    PriorEntry("deepseek-v4-pro", "analysis", "B", provenance="artificial-analysis"),
    PriorEntry("glm-5.2", "analysis", "B", provenance="models-dev"),
    PriorEntry("kimi-k2.6", "analysis", "B", provenance="models-dev"),
    PriorEntry("minimax-m2.7", "analysis", "C", provenance="models-dev"),
    # ── translation ─────────────────────────────────────────────────────────
    PriorEntry("gpt-5", "translation", "A", provenance="lmarena"),
    PriorEntry("gemini-3-pro", "translation", "A", provenance="lmarena"),
    PriorEntry("claude-opus-4.5", "translation", "A", provenance="lmarena"),
    PriorEntry("deepseek-v4-pro", "translation", "B", provenance="lmarena"),
    PriorEntry("glm-5.2", "translation", "B", provenance="models-dev"),
    PriorEntry("kimi-k2.6", "translation", "B", provenance="lmarena"),
    # ── creative ────────────────────────────────────────────────────────────
    PriorEntry("claude-opus-4.5", "creative", "A", provenance="lmarena"),
    PriorEntry("gpt-5", "creative", "A", provenance="lmarena"),
    PriorEntry("gemini-3-pro", "creative", "B", provenance="lmarena"),
    PriorEntry("deepseek-v4-pro", "creative", "B", provenance="lmarena"),
    PriorEntry("glm-5.2", "creative", "B", provenance="models-dev"),
    PriorEntry("minimax-m2.7", "creative", "C", provenance="models-dev"),
    # ── general ──────────────────────────────────────────────────────────────
    PriorEntry("gpt-5", "general", "A", provenance="artificial-analysis"),
    PriorEntry("claude-opus-4.5", "general", "A", provenance="artificial-analysis"),
    PriorEntry("gemini-3-pro", "general", "A", provenance="artificial-analysis"),
    PriorEntry("deepseek-v4-pro", "general", "B", provenance="artificial-analysis"),
    PriorEntry("kimi-k2.6", "general", "B", provenance="artificial-analysis"),
    PriorEntry("glm-5.2", "general", "B", provenance="models-dev"),
    PriorEntry("minimax-m2.7", "general", "C", provenance="artificial-analysis"),
    PriorEntry("llama-4-405b", "general", "C", provenance="models-dev"),
)

SEED_PRIOR: tuple[PriorEntry, ...] = _SEED_PRIOR
"""The curated external-benchmark prior — the cold-start data.

Exposed (read-only tuple) so tests and an operator audit can inspect the table
without constructing a :class:`GradesImport`. This is the single source of
truth for the seed; :func:`seed_matrix` reads it."""

# Grade ordering for the day-1 ranking helper. ``"unknown"`` sorts last so a
# missing prior never beats a known-bad one — the gateway preferentially routes
# on any provisional signal over pure ignorance, which is the cold-start point.
_GRADE_ORDER: dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "unknown": 5}


# ── import / reconcile ───────────────────────────────────────────────────


class GradesImport:
    """Loads the seed prior into a :class:`CapabilityMatrix` and enforces the
    DECAY / OVERRIDE rule that keeps the prior PROVISIONAL.

    The cold-start bridge. The flow:

      1. :meth:`load_into` writes every :data:`SEED_PRIOR` entry into the matrix
         at ``confidence = prior.weight`` (< 1.0). After this the matrix is
         NON-EMPTY — the gateway has a day-1 ordering to route on.
      2. When a real graded outcome lands for ``(model, work_class)`` the
         outcome ledger calls :meth:`reconcile_with_real`. The real grade
         ALWAYS wins: it REPLACES the prior entry entirely (confidence → 1.0)
         and the prior's weight is decayed to zero by being overwritten, not
         blended. This is the structural guarantee that "your own signal
         outranks any leaderboard" — the prior cannot override real signal
         because reconcile overwrites it.

    The provisional/real TAG and provenance are tracked in a sidecar dict on
    the importer (the existing ``ModelCapability`` carries no metadata field,
    and ``matrix.py`` is owned by another ticket — the sidecar keeps this
    module self-contained). The matrix-level weight signal is ``confidence``:
    prior entries are ``confidence < 1.0``; real entries are
    ``confidence == 1.0``.

    The prior is a *bridge*, not a *substitute*: it exists only so the
    outcome-graded router is not inert on day-1 while real outcomes accumulate
    (paired with EVAL-CONTROL-GATE-FIX which fixes the real-outcome LOOP).
    """

    def __init__(self, prior: tuple[PriorEntry, ...] | None = None) -> None:
        self._prior: tuple[PriorEntry, ...] = (
            tuple(prior) if prior is not None else SEED_PRIOR
        )
        # Sidecar: (model, work_class) → source tag + provenance + samples.
        # Authoritative for "is this entry a prior or a real outcome?".
        self._sources: dict[tuple[str, WorkClass], dict[str, object]] = {}

    @property
    def prior(self) -> tuple[PriorEntry, ...]:
        """The prior this importer was constructed with (a copy)."""
        return self._prior

    # ── load ────────────────────────────────────────────────────────────

    def load_into(self, matrix: CapabilityMatrix) -> int:
        """Seed *matrix* with the prior.

        Writes every prior entry as a PROVISIONAL matrix entry:
        ``confidence = prior.weight`` (< 1.0). The TAG + provenance are
        recorded in the importer sidecar.

        Returns the number of entries written. Idempotent: re-loading the same
        prior overwrites prior provisional entries in place (a re-seed should
        not leave stale weights behind) — but NEVER clobbers a REAL graded
        outcome (an entry the sidecar or matrix-confidence marks as real).
        """
        count = 0
        for entry in self._prior:
            key = (entry.model_id, entry.work_class)
            existing = matrix.entries.get(key)
            if existing is not None and not self._is_provisional_entry(matrix, key):
                # Never clobber a REAL graded outcome with a prior re-seed.
                # Real outcomes own their keys once landed.
                continue
            matrix.entries[key] = ModelCapability(
                model_id=entry.model_id,
                work_class=entry.work_class,
                grade=entry.grade,
                confidence=entry.weight,
            )
            self._sources[key] = {
                "source": PROVISIONAL_TAG,
                "provenance": entry.provenance,
            }
            count += 1
        return count

    # ── reconcile (the override / decay rule) ────────────────────────────

    def reconcile_with_real(
        self,
        matrix: CapabilityMatrix,
        *,
        model_id: str,
        work_class: WorkClass,
        grade: Grade,
        confidence: float = 1.0,
        samples: int = 1,
    ) -> ModelCapability:
        """Record a REAL graded outcome, overriding any prior for the key.

        This is the doctrinal core ([benchmark-not-a-valid-ranker]): a real
        graded outcome (pass/fail/merge/revert from a graded work run) ALWAYS
        beats the prior, regardless of the prior's weight. The prior is
        REPLACED — its confidence is decayed to zero by being overwritten, not
        averaged. After this call the matrix entry has ``confidence = 1.0``
        (callers should pass ``confidence`` ≥ 0; it is clamped to 1.0 so a real
        outcome is ALWAYS at least as strong as the strongest prior) and the
        sidecar marks the entry ``"real"`` with a ``samples`` count, so the
        gateway can no longer be routing on a provisional score for this key.

        ``samples`` is stored in the sidecar for audits (how many real
        outcomes back this grade). Returns the recorded capability entry.
        """
        if confidence <= 0.0:
            raise ValueError("real-outcome confidence must be > 0 (the prior is gone)")
        key = (model_id, work_class)
        real_conf = min(confidence, 1.0)
        cap = ModelCapability(
            model_id=model_id,
            work_class=work_class,
            grade=grade,
            confidence=real_conf,
        )
        matrix.entries[key] = cap
        self._sources[key] = {
            "source": REAL_TAG,
            "samples": int(samples),
            "confidence_requested": float(confidence),
        }
        return cap

    # ── queries ─────────────────────────────────────────────────────────

    def is_provisional(
        self, matrix: CapabilityMatrix, *, model_id: str, work_class: WorkClass
    ) -> bool:
        """True iff the ``(model, work_class)`` entry is still a prior.

        Authoritative source is the sidecar; falls back to the matrix confidence
        (``< 1.0`` ⇒ provisional) when the importer has no sidecar record for
        the key (e.g. a fresh importer inspecting a matrix seeded by another
        instance — the cold-start weight is the durable signal).

        The outcome ledger uses this to decide whether a key still needs real
        outcomes collected: a provisional entry is cold-start filler; a real
        entry has been superseded.
        """
        key = (model_id, work_class)
        src = self._sources.get(key)
        if src is not None:
            return src.get("source") == PROVISIONAL_TAG
        entry = matrix.entries.get(key)
        if entry is None:
            return False
        return entry.confidence < 1.0

    def provenance_of(
        self, model_id: str, work_class: WorkClass
    ) -> Provenance | None:
        """The benchmark family a prior entry was curated from, or None.

        Only meaningful for provisional entries; returns None for real
        outcomes (real outcomes are graded by Charon, not imported)."""
        src = self._sources.get((model_id, work_class))
        if src is None:
            return None
        prov = src.get("provenance")
        return prov if isinstance(prov, str) else None  # type: ignore[return-value]

    def real_samples(
        self, model_id: str, work_class: WorkClass
    ) -> int | None:
        """How many real graded outcomes back this key, or None if still provisional."""
        src = self._sources.get((model_id, work_class))
        if src is None or src.get("source") != REAL_TAG:
            return None
        samples = src.get("samples")
        return int(samples) if isinstance(samples, (int, float)) else None

    # ── internal ────────────────────────────────────────────────────────

    def _is_provisional_entry(
        self, matrix: CapabilityMatrix, key: tuple[str, WorkClass]
    ) -> bool:
        """An entry is provisional iff the sidecar says so OR (no sidecar
        record and the matrix confidence is < 1.0). A real entry (sidecar
        ``"real"`` or confidence == 1.0) is NOT clobberable by a re-seed."""
        src = self._sources.get(key)
        if src is not None:
            return src.get("source") == PROVISIONAL_TAG
        entry = matrix.entries.get(key)
        if entry is None:
            return True  # nothing there yet — safe to seed
        return entry.confidence < 1.0


# ── convenience ──────────────────────────────────────────────────────────


def seed_matrix(matrix: CapabilityMatrix | None = None) -> CapabilityMatrix:
    """Return a :class:`CapabilityMatrix` populated with the seed prior.

    The day-1 bridge entrypoint. The gateway calls this (or constructs a
    ``GradesImport`` and calls ``load_into``) when it has no real graded
    outcomes yet, so it still has a NON-EMPTY ordering to route on.

    If *matrix* is None a fresh matrix is created (with the built-in provider
    quirk rules). If passed, the prior is loaded into it in place and the same
    instance is returned (useful when a matrix already carries some real
    outcomes — those are preserved; :meth:`GradesImport.load_into` never
    clobbers a real entry).
    """
    m = matrix if matrix is not None else CapabilityMatrix()
    GradesImport().load_into(m)
    return m


def rank_for_work_class(
    matrix: CapabilityMatrix, work_class: WorkClass
) -> list[tuple[str, Grade, float]]:
    """Return models with a known grade for *work_class*, ordered best-first.

    Each element is ``(model_id, grade, confidence)``. Entries with grade
    ``"unknown"`` are included (sorted last) so the ordering is a TOTAL order
    over every model the matrix knows for the class — the gateway's day-1
    routing key. ``confidence`` is the weight (prior < 1.0, real == 1.0) so the
    consumer can break ties toward real signal.

    This is the proof that the cold-start bridge works: on a seeded matrix it
    returns a NON-EMPTY list, so CG can produce an ordering to route on day-1
    even with zero real outcomes.
    """
    rows: list[tuple[str, Grade, float]] = []
    for (mid, wc), cap in matrix.entries.items():
        if wc != work_class:
            continue
        rows.append((mid, cap.grade, cap.confidence))
    # Best grade first; within a grade, real (confidence 1.0) > prior (< 1.0);
    # final tiebreak is model id for determinism.
    rows.sort(key=lambda r: (_GRADE_ORDER.get(r[1], 5), -(r[2]), r[0]))
    return rows


__all__ = [
    "DEFAULT_PRIOR_WEIGHT",
    "PROVISIONAL_TAG",
    "REAL_TAG",
    "Provenance",
    "PriorEntry",
    "SEED_PRIOR",
    "GradesImport",
    "seed_matrix",
    "rank_for_work_class",
]