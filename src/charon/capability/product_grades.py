"""Product-side outcome-grade store — the NEUTRAL format ADR-0017 names.

The DIFFERENTIATOR for the outcome-graded gateway is a per-(model, work_class)
grade the gateway reads to reorder its routing decisions. ADR-0017
(``docs/adr/0017-outcome-graded-gateway.md``) and the GATEWAY-PROGRAM §0
spec require this grade to live in a **neutral product-owned format** that:

  1. has its OWN on-disk schema (NOT the fleet ``model-scorecard.tsv``);
  2. imports NO fleet code (no ``charon.routing_policy.matrix`` etc. — a
     rig→product leak is forbidden
     [[product-vs-build-rig-boundary]]);
  3. PORTS the contract the fleet grade ledger enforces — refuse-on-empty,
     per-``(model, work_class)`` key, coarse A–F band — without sharing
     the data path. A fresh install seeds it via its own importer; live
     traffic does NOT self-grade (a health/latency/cost response is not an
     outcome, ADR-0017 §\"Why a grade not a leaderboard\").

This module is the data layer. The OVERLAY that consumes it lives in
``charon.routing_policy.grade_order`` (the litellm.Router routing-decision
hook) — these two files together are the novel seam for this ticket; they
are deliberately one inseparable unit so a reviewer cannot ship a router
hook against an undefined grade shape (or vice versa).

On-disk schema (a JSON object the gateway writes, reads, and refuses to
silently truncate):

    {
      \"version\": 1,
      \"entries\": [
        {\"model_id\": \"...\", \"work_class\": \"reasoning\",
         \"grade\": \"A\", \"confidence\": 1.0, \"samples\": 42},
        ...
      ]
    }

* ``entries`` MUST be non-empty — the loader raises
  :class:`EmptyGradeStore` when the file is present but has zero entries
  (the refuse-on-empty contract: an empty product grade is a structural
  misconfiguration, not a no-op).
* ``model_id`` is the agent-facing model id (the same id the litellm
  ``model_name`` carries in ``model_list`` — the overlay keys its reorder
  off it; using any other identity would strand reorder decisions).
* ``work_class`` MUST be one of the canonical taxonomy classes (the same
  set ``charon.capability.taxonomy`` recognises); the loader validates it
  so a typo in the JSON cannot silently degrade ordering.
* ``grade`` is the coarse A–F band (the only signal the overlay reads);
  finer-grained numbers are deliberately NOT a wire field — a grade is
  a coarse ordering token, not a measurement
  [benchmark-not-a-valid-ranker].
* ``confidence`` is OPTIONAL (default 1.0). A < 1.0 entry marks a
  provisional seeding (the cold-start prior's signal flag) so the overlay
  can prefer real outcomes over priors when both exist.
* ``samples`` is OPTIONAL and informational (audit / real-outcome sample
  count). The overlay does not branch on it — coarse grade is enough to
  drive an ordering, and finer signals would mask the ordering decision
  behind a regression-to-mean mean.

Hot-path-readiness: the overlay constructs a :class:`ProductGradeStore`
once at Router build time and looks it up O(1) per
``(model_id, work_class)`` — there is no per-request file parse. The
``load_cached`` helper is the canonical reader; the gate-level
\"byte-identical cold start\" requirement is satisfied by the store being
EMPTY when the file is absent (not missing) so the overlay sees no
ordering signal and falls through to the Router's own chain order.

Stdlib-only (json, pathlib, threading). This module is the product-owned
counterpart to ``charon.capability.grades`` — they share a vocabulary
(``A–F`` bands) but no code, deliberately, so a future product that
re-implements either side stays decoupled.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# The grade vocabulary is OWNED HERE, not imported from
# ``charon.routing_policy.matrix``. This is the load-bearing boundary
# the ADR-0017 spec mandates
# [[product-vs-build-rig-boundary]]: the product-side store is a
# product-owned neutral format and must not import any fleet / build-rig
# code (a rig→product leak would couple the two systems in ways that
# make future decoupling expensive). The vocabulary values match the
# build-side ``matrix.Grade`` Literal by CONVENTION only — if the
# build-side vocabulary ever changes, this is the ONE place that knows
# the product's expectation. The hot-path overlay
# (``routing_policy.grade_order``) consumes these constants directly so
# the comparison never depends on a fleet import either.

Grade = Literal["A", "B", "C", "D", "F", "unknown"]
"""The coarse outcome-grade band the gateway routes on.

Order: ``A > B > C > D > F > unknown`` (``A`` is best). ``unknown`` is
the deliberate cold-start value — an absent grade is NEVER confused with
a known-bad grade, so a deployment the operator has not graded is
preferred over one explicitly graded ``F`` (which means \"known bad\")."""

WorkClass = Literal[
    "reasoning",
    "coding",
    "translation",
    "creative",
    "analysis",
    "general",
]
"""The canonical work-class vocabulary the deterministic classifier
(``charon.capability.taxonomy``) returns.

Duplicated here (NOT imported) so this module stays truly product-side:
even if the capability package is later refactored or the taxonomy
expanded, the product-grade schema's wire contract is fixed. Adding a
new work-class to the canonical taxonomy does NOT automatically add it
to this set — operators MUST update the JSON file's entries to match
the new vocabulary (deliberate friction; an accidental mismatch would
silently strand a new work-class's grade)."""

# Mirror the matrix's ``Grade`` order for use in the overlay's sort key
# (best first). Centralised here so a future change to the vocabulary
# (e.g. dropping ``D``) is a one-line edit.
_GRADE_RANK: dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "unknown": 5}
_VALID_GRADES: frozenset[str] = frozenset(_GRADE_RANK)

_CANONICAL_WORK_CLASSES: frozenset[str] = frozenset({
    "reasoning", "coding", "translation", "creative", "analysis", "general",
})

# Schema version. Bump when the wire format changes in a way that needs a
# one-way rejection of older files (the loader raises on an unknown version,
# NEVER silently downgrades — a silent downgrade would mask an operator
# upgrade as a missing-grade cold start).
SCHEMA_VERSION = 1

# The well-known on-disk filename, resolved at overlay build time. Operators
# override via ``CHARON_PRODUCT_GRADES_PATH`` (the env var is honoured by
# :func:`load_cached`, NOT by this module's constructor — keeps the module
# fully under explicit-path control for tests).
DEFAULT_GRADES_FILENAME = "product-grades.json"

ENV_OVERRIDE = "CHARON_PRODUCT_GRADES_PATH"
"""Env var the overlay consults before falling back to the default path."""


# ── exceptions ────────────────────────────────────────────────────────────


class GradeStoreError(ValueError):
    """Base for the product-grade store's load-time failures."""


class EmptyGradeStore(GradeStoreError):
    """The grades file is present but has zero entries.

    The refuse-on-empty contract: an empty product-grade store is a
    structural misconfiguration (an operator meant to seed something and
    shipped an empty list). The overlay would treat it as \"no signal\"
    which is byte-identical to \"no file\" — that ambiguity is exactly what
    the refuse-on-empty guard exists to prevent."""


class InvalidGradeStore(GradeStoreError):
    """The grades file is structurally invalid (bad shape, unknown version,
    unknown work_class, etc.)."""


# ── data shape ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProductGradeEntry:
    """One ``(model_id, work_class) → grade`` row from the product store.

    Immutable so the overlay can cache instances without defensive copies.
    ``confidence`` defaults to 1.0 (a fully-attested grade). The overlay
    treats any value < 1.0 as a provisional seeding and prefers real
    grades (1.0) over priors in a tie — the same prior-vs-real signal
    ``grades_import.PROVISIONAL_TAG`` carries on the build-side ledger.
    """

    model_id: str
    work_class: WorkClass
    grade: Grade
    confidence: float = 1.0
    samples: int = 0

    def __post_init__(self) -> None:
        if not self.model_id:
            raise InvalidGradeStore("model_id must be non-empty")
        if self.work_class not in _CANONICAL_WORK_CLASSES:
            raise InvalidGradeStore(
                f"work_class={self.work_class!r} is not a canonical taxonomy class "
                f"(expected one of {sorted(_CANONICAL_WORK_CLASSES)})")
        if self.grade not in _VALID_GRADES:
            raise InvalidGradeStore(
                f"grade={self.grade!r} is not a valid band (expected one of "
                f"{sorted(_VALID_GRADES)})")
        if not (0.0 <= self.confidence <= 1.0):
            raise InvalidGradeStore(
                f"confidence={self.confidence!r} must be in [0.0, 1.0]")


# ── the store ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProductGradeStore:
    """An immutable, hot-path-ready view over the on-disk grades.

    Constructed once at Router build time via :meth:`load` or
    :meth:`load_cached`. The overlay reads ``entries`` as a flat tuple and
    never holds the source file open — lookups are O(n) on the (small)
    candidate set, no per-request parse. A cached dict index is built
    lazily by the overlay when it needs more than one lookup per
    decision.

    Two factory paths:

      * :meth:`load` (always re-reads the file) — for tests and operator
        audits; never hot-path.
      * :meth:`load_cached` (memoised) — the canonical hot-path reader.
        ``Path`` is the cache key, so distinct test fixtures do not
        collide.
    """

    entries: tuple[ProductGradeEntry, ...] = ()

    def __post_init__(self) -> None:
        # Reject the empty-on-construct path: the *constructor* (and by
        # extension ``save`` of an empty list) must never produce a
        # silently-empty store — that is what :meth:`empty` is for and
        # the only legitimate way to get an empty store. An empty
        # constructor is a structural misconfiguration: callers who
        # \"want no grades\" must reach for :meth:`empty`, which
        # returns a SHARED sentinel whose identity the overlay uses
        # for \"no signal\" detection.
        if not self.entries:
            raise EmptyGradeStore(
                "ProductGradeStore refuses empty construction; use ProductGradeStore.empty() "
                "for the cold-start no-file signal")

    # ── canonical empty store (the byte-identical cold-start signal) ────

    @classmethod
    def empty(cls) -> ProductGradeStore:
        """Return the SHARED empty store — the cold-start no-signal value.

        The overlay treats ``store is EMPTY`` (or equivalently an empty
        ``entries`` tuple) as \"no grade signal, fall through to chain
        order\". Using a shared singleton avoids one allocation per
        empty-store construction (which would dominate wall-clock on
        Router build) AND gives callers a single identity to compare
        against (``store is ProductGradeStore.empty()``)."""
        return _EMPTY

    # ── lookups (hot path) ──────────────────────────────────────────────

    def grade_for(self, model_id: str, work_class: WorkClass) -> Grade:
        """Return the grade for *model_id* on *work_class*, or ``\"unknown\"``.

        This is the ONLY method the overlay calls per routing decision.
        It is O(n) over the store, where ``n`` is the number of
        seeded entries (typically small per work-class — the overlay
        filters by ``work_class`` first). ``\"unknown\"`` is the
        deliberate fallback — the overlay treats unknown-grade models
        as last-priority (a known grade beats an unknown grade beats
        the absent cold-start, which beats nothing).
        """
        for entry in self.entries:
            if entry.model_id == model_id and entry.work_class == work_class:
                return entry.grade
        return "unknown"

    def confidence_for(self, model_id: str, work_class: WorkClass) -> float:
        """Return the confidence for *model_id* on *work_class*, or 1.0 when
        the entry is absent (an absent entry is treated as fully-attested
        unknown — the overlay's tie-break rule prefers real signal over
        priors, so a missing key is \"no provisional\")."""
        for entry in self.entries:
            if entry.model_id == model_id and entry.work_class == work_class:
                return entry.confidence
        return 1.0

    def models_for(self, work_class: WorkClass) -> tuple[str, ...]:
        """All model ids with an entry for *work_class*, in insertion order.

        Diagnostic / audit helper; the overlay does not call it on the
        hot path."""
        seen: list[str] = []
        for entry in self.entries:
            if entry.work_class == work_class and entry.model_id not in seen:
                seen.append(entry.model_id)
        return tuple(seen)

    # ── persistence ─────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path | str) -> ProductGradeStore:
        """Load and validate the grades file at *path*.

        Raises :class:`EmptyGradeStore` when the file is present but has
        zero entries (the refuse-on-empty contract). Raises
        :class:`InvalidGradeStore` on bad shape / unknown schema /
        unknown work_class. A MISSING file returns :meth:`empty` (the
        FAIL-OPEN cold-start signal) — never raises.

        The caller passes the path explicitly (no implicit HOME-relative
        resolution here); the env-var / default-path resolution lives in
        :func:`resolve_default_path` / :func:`load_cached` so tests can
        bypass it without monkeypatching.
        """
        p = Path(path)
        if not p.exists():
            return cls.empty()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InvalidGradeStore(f"grades file {p} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise InvalidGradeStore(
                f"grades file {p} must be a JSON object, got {type(data).__name__}")
        version = data.get("version")
        if version != SCHEMA_VERSION:
            raise InvalidGradeStore(
                f"grades file {p} has version={version!r}, expected {SCHEMA_VERSION} "
                "(unknown versions are rejected — a silent downgrade would mask "
                "an operator upgrade as a missing-grade cold start)")
        raw_entries = data.get("entries")
        if not isinstance(raw_entries, list):
            raise InvalidGradeStore(
                f"grades file {p} 'entries' must be a list, got {type(raw_entries).__name__}")
        if not raw_entries:
            raise EmptyGradeStore(
                f"grades file {p} has zero entries (refuse-on-empty: an empty store "
                "is a structural misconfiguration, not a no-op)")
        entries: list[ProductGradeEntry] = []
        for i, raw in enumerate(raw_entries):
            if not isinstance(raw, dict):
                raise InvalidGradeStore(
                    f"grades file {p} entries[{i}] must be an object, got {type(raw).__name__}")
            try:
                # ``cast`` to the Literal type — the runtime validator
                # in ``ProductGradeEntry.__post_init__`` (not the
                # type checker) is the authority for \"is this string
                # one of the canonical values\". mypy cannot prove a
                # string is one of a Literal set, so we cast.
                from typing import cast
                entries.append(ProductGradeEntry(
                    model_id=str(raw["model_id"]),
                    work_class=cast(WorkClass, str(raw["work_class"])),
                    grade=cast(Grade, str(raw["grade"])),
                    confidence=float(raw.get("confidence", 1.0)),
                    samples=int(raw.get("samples", 0)),
                ))
            except (KeyError, InvalidGradeStore) as exc:
                raise InvalidGradeStore(
                    f"grades file {p} entries[{i}] invalid: {exc}") from exc
        return cls(entries=tuple(entries))

    def save(self, path: Path | str) -> None:
        """Serialise the store to *path* (overwrites). The inverse of
        :meth:`load`; round-trips through :meth:`load` produce an equal
        store."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SCHEMA_VERSION,
            "entries": [
                {
                    "model_id": e.model_id,
                    "work_class": e.work_class,
                    "grade": e.grade,
                    "confidence": e.confidence,
                    "samples": e.samples,
                }
                for e in self.entries
            ],
        }
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                     encoding="utf-8")

    # ── copy / extend ───────────────────────────────────────────────────

    def with_entries(self, extra: Iterable[ProductGradeEntry]) -> ProductGradeStore:
        """Return a new store with *extra* appended (immutable update).

        Useful for tests and operator tooling; the overlay never calls
        this on the hot path (the store is constructed once at build
        time and never mutated)."""
        new_entries = tuple(self.entries) + tuple(extra)
        if not new_entries:
            return self.empty()
        return ProductGradeStore(entries=new_entries)


# The singleton empty store. Built via ``object.__new__`` so the
# ``__post_init__`` empty-refuse rule does NOT fire on the shared
# sentinel (the sentinel exists ONLY to materialise the empty
# \"no-signal\" state that the overlay keys off).
_EMPTY = object.__new__(ProductGradeStore)
object.__setattr__(_EMPTY, "entries", ())


# ── path resolution + cached load (the canonical overlay entry point) ────


def resolve_default_path(home: Path | str | None = None) -> Path:
    """The canonical on-disk path for the product grades file.

    Resolution order (first hit wins):

      1. The ``CHARON_PRODUCT_GRADES_PATH`` env var (operator override;
         absolute path; never relative).
      2. ``<home>/product-grades.json`` when *home* is given.
      3. The default :data:`DEFAULT_GRADES_FILENAME` under the current
         working directory (preserved for the small / single-host
         deployment; production uses env var or explicit *home*).

    The function does NOT touch the filesystem — it only computes the
    path. The caller decides whether to load (and gets :meth:`empty` when
    the file is absent, by design)."""
    import os

    env = os.environ.get(ENV_OVERRIDE)
    if env:
        return Path(env)
    if home is not None:
        return Path(home) / DEFAULT_GRADES_FILENAME
    return Path.cwd() / DEFAULT_GRADES_FILENAME


# Cache for ``load_cached``. Keyed on the resolved path so distinct
# fixtures do not collide. The lock makes the cache safe to populate
# concurrently from multiple threads (the Router build path is single-
# threaded in practice, but a test fixture that builds two routers in
# parallel must not race).
_cache: dict[Path, ProductGradeStore] = {}
_cache_lock = threading.Lock()


def load_cached(path: Path | str | None = None,
                *, home: Path | str | None = None) -> ProductGradeStore:
    """Return the grades store at *path*, memoised.

    *path* None → :func:`resolve_default_path` (env var, then *home*,
    then cwd). Subsequent calls with the same resolved path return the
    same :class:`ProductGradeStore` instance — the hot path relies on
    this so the overlay's per-routing-decision lookups never re-parse the
    file.

    ``home`` is passed through to :func:`resolve_default_path` and is
    the recommended way to point at a per-test fixture dir without
    touching the env (tests should NEVER rely on cwd).
    """
    resolved = Path(path) if path is not None else resolve_default_path(home=home)
    with _cache_lock:
        cached = _cache.get(resolved)
        if cached is not None:
            return cached
        store = ProductGradeStore.load(resolved)
        _cache[resolved] = store
        return store


def _clear_cache() -> None:
    """Drop the memoised store. Tests-only — never called on the hot path."""
    with _cache_lock:
        _cache.clear()


__all__ = [
    "Grade",
    "WorkClass",
    "SCHEMA_VERSION",
    "DEFAULT_GRADES_FILENAME",
    "ENV_OVERRIDE",
    "GradeStoreError",
    "EmptyGradeStore",
    "InvalidGradeStore",
    "ProductGradeEntry",
    "ProductGradeStore",
    "resolve_default_path",
    "load_cached",
]
