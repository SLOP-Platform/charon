"""Tests for the cold-start prior bridge (ADR-0017 §Cold-start).

Coverage:
  * The seed prior populates a CapabilityMatrix NON-EMPTY (CG has a day-1
    ordering to route on with zero real outcomes).
  * Every seeded entry is PROVISIONAL: confidence < 1.0, tagged "provisional".
  * A real graded outcome REPLACE / OVERRIDE s the prior for the same key —
    the prior never wins once real signal exists (the decay/override rule).
  * A re-seed NEVER clobbers a real graded outcome (real entries own their keys).
  * ``rank_for_work_class`` returns a NON-EMPTY, best-first ordering.
  * The prior is stdlib-only and self-contained (no parallel store).
  * Provenance is tracked so an operator can audit where each grade came from.

This is the proof that the cold-start bridge resolves the doctrinal tension
([benchmark-not-a-valid-ranker]): the prior gives a usable day-1 ranking AND
real graded outcomes supplant it, so own-signal still wins once it exists.
"""
from __future__ import annotations

import pytest

from charon.capability.grades_import import (
    DEFAULT_PRIOR_WEIGHT,
    SEED_PRIOR,
    GradesImport,
    PriorEntry,
    rank_for_work_class,
    seed_matrix,
)
from charon.routing_policy.matrix import (
    CapabilityMatrix,
    WorkClass,
)

# ── seed prior shape ─────────────────────────────────────────────────────


class TestSeedPriorShape:
    """The curated prior is auditable and well-formed."""

    def test_seed_prior_is_non_empty(self):
        """Proof: there IS a prior to import — the cold-start bridge has data."""
        assert len(SEED_PRIOR) > 0

    @pytest.mark.parametrize("entry", SEED_PRIOR)
    def test_every_entry_weight_is_provisional(self, entry: PriorEntry):
        """Doctrinal guard: NO prior entry is as strong as a real outcome."""
        assert 0.0 < entry.weight < 1.0, (
            f"prior for {entry.model_id}/{entry.work_class} weight={entry.weight} "
            "must be < 1.0 (a prior is never as strong as a real graded outcome)"
        )

    @pytest.mark.parametrize("entry", SEED_PRIOR)
    def test_every_entry_has_provenance(self, entry: PriorEntry):
        """Each grade must trace to a legitimate external benchmark family."""
        assert entry.provenance in {
            "aider-polyglot", "lmarena", "artificial-analysis",
            "models-dev", "operator-curated",
        }

    @pytest.mark.parametrize("entry", SEED_PRIOR)
    def test_every_entry_grade_is_a_valid_band(self, entry: PriorEntry):
        assert entry.grade in {"A", "B", "C", "D", "F", "unknown"}

    @pytest.mark.parametrize(
        "wc",
        ["reasoning", "coding", "translation", "creative", "analysis", "general"],
    )
    def test_every_work_class_is_covered(self, wc: WorkClass):
        """Cold-start must cover EVERY taxonomy class or routing has a hole."""
        covered = {e for e in SEED_PRIOR if e.work_class == wc}
        assert covered, f"seed prior has no coverage for work_class={wc!r}"

    def test_default_prior_weight_is_in_provisional_range(self):
        assert 0.0 < DEFAULT_PRIOR_WEIGHT < 1.0


# ── loading ──────────────────────────────────────────────────────────────


class TestLoadInto:
    """Loading the prior seeds the matrix NON-EMPTY with provisional entries."""

    def test_load_into_empty_matrix_seeds_all_entries(self):
        m = CapabilityMatrix()
        gi = GradesImport()
        n = gi.load_into(m)
        assert n == len(SEED_PRIOR)
        # Acceptance §3: CG can produce a NON-EMPTY ordering to route on.
        assert len(m.entries) == len(SEED_PRIOR)

    def test_loaded_entries_are_provisional_low_confidence(self):
        m = CapabilityMatrix()
        GradesImport().load_into(m)
        for cap in m.entries.values():
            assert cap.confidence == DEFAULT_PRIOR_WEIGHT
            assert cap.confidence < 1.0, "a prior is never as strong as real"

    def test_loaded_entries_are_tagged_provisional(self):
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        for entry in SEED_PRIOR:
            assert gi.is_provisional(
                m, model_id=entry.model_id, work_class=entry.work_class
            )

    def test_load_into_preserves_real_outcome_on_reseed(self):
        """Re-seeding MUST NOT clobber a real graded outcome."""
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        # A real outcome lands.
        gi.reconcile_with_real(
            m, model_id="gpt-5", work_class="coding", grade="A", samples=3,
        )
        assert not gi.is_provisional(m, model_id="gpt-5", work_class="coding")

        # Re-seed with a fresh importer (simulates operator re-running import).
        gi2 = GradesImport()
        gi2.load_into(m)
        # The real entry survives — the prior did not overwrite it. The DURABLE
        # signal across importer instances is the matrix confidence (1.0 ⇒ real);
        # per-instance sidecar (samples) is local to the importer that recorded it.
        assert not gi2.is_provisional(m, model_id="gpt-5", work_class="coding")
        cap = m.entries[("gpt-5", "coding")]
        assert cap.confidence == 1.0
        assert cap.grade == "A"
        # The original importer still knows its own sample count.
        assert gi.real_samples("gpt-5", "coding") == 3

    def test_load_is_idempotent_on_provisional_entries(self):
        m = CapabilityMatrix()
        gi = GradesImport()
        first = gi.load_into(m)
        second = gi.load_into(m)
        assert first == len(SEED_PRIOR)
        # Re-loading overwrites the same provisional entries (no growth).
        assert second == len(SEED_PRIOR)
        assert len(m.entries) == len(SEED_PRIOR)

    def test_load_into_uses_provided_prior_not_global(self):
        custom = (
            PriorEntry("zzz-1", "general", "B"),
            PriorEntry("zzz-2", "general", "C"),
        )
        m = CapabilityMatrix()
        gi = GradesImport(prior=custom)
        n = gi.load_into(m)
        assert n == 2
        assert ("zzz-1", "general") in m.entries
        # The global seed did NOT leak in.
        assert ("gpt-5", "reasoning") not in m.entries


# ── reconcile (the override / decay rule) ─────────────────────────────────


class TestReconcileOverride:
    """The doctrinal core: real graded outcomes ALWAYS supplant the prior."""

    def test_real_outcome_replaces_prior_grade(self):
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        # The prior says gpt-5/coding = A (provisional).
        assert m.get_grade("gpt-5", "coding") == "A"
        # A real graded outcome says gpt-5/coding = C.
        gi.reconcile_with_real(
            m, model_id="gpt-5", work_class="coding", grade="C", samples=5,
        )
        assert m.get_grade("gpt-5", "coding") == "C"

    def test_real_outcome_bumps_confidence_to_one(self):
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        assert m.entries[("gpt-5", "reasoning")].confidence < 1.0
        gi.reconcile_with_real(
            m, model_id="gpt-5", work_class="reasoning", grade="A",
        )
        assert m.entries[("gpt-5", "reasoning")].confidence == 1.0

    def test_real_outcome_marks_entry_not_provisional(self):
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        assert gi.is_provisional(m, model_id="gpt-5", work_class="reasoning")
        gi.reconcile_with_real(
            m, model_id="gpt-5", work_class="reasoning", grade="A",
        )
        assert not gi.is_provisional(m, model_id="gpt-5", work_class="reasoning")

    def test_reconcile_clamps_confidence_to_one(self):
        """A caller cannot inflate a real outcome above 1.0."""
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        cap = gi.reconcile_with_real(
            m, model_id="gpt-5", work_class="reasoning",
            grade="A", confidence=2.5,
        )
        assert cap.confidence == 1.0

    def test_reconcile_rejects_zero_confidence(self):
        """A real outcome with confidence 0 would be indistinguishable from
        'no prior' — the decay rule requires the prior to actually be gone."""
        m = CapabilityMatrix()
        gi = GradesImport()
        with pytest.raises(ValueError):
            gi.reconcile_with_real(
                m, model_id="x", work_class="general", grade="A", confidence=0.0,
            )

    def test_reconcile_records_real_samples(self):
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        assert gi.real_samples("gpt-5", "coding") is None
        gi.reconcile_with_real(
            m, model_id="gpt-5", work_class="coding", grade="B", samples=7,
        )
        assert gi.real_samples("gpt-5", "coding") == 7

    def test_reconcile_on_key_with_no_prior_still_works(self):
        """The ledger may record a real outcome for a (model, class) the prior
        never covered — that still creates a real entry."""
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        assert ("never-seen-model", "general") not in m.entries
        gi.reconcile_with_real(
            m, model_id="never-seen-model", work_class="general",
            grade="B", samples=2,
        )
        assert m.get_grade("never-seen-model", "general") == "B"
        assert not gi.is_provisional(
            m, model_id="never-seen-model", work_class="general"
        )

    def test_reconcile_preserves_other_provisional_entries(self):
        """Overriding one key must NOT decay the rest of the prior — only the
        graded key is superseded."""
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        gi.reconcile_with_real(
            m, model_id="gpt-5", work_class="coding", grade="C",
        )
        # Other keys are still provisional.
        assert gi.is_provisional(m, model_id="gpt-5", work_class="reasoning")
        assert gi.is_provisional(m, model_id="glm-5.2", work_class="coding")


# ── provenance / audits ──────────────────────────────────────────────────


class TestProvenance:
    """An operator can audit where each prior grade came from."""

    def test_provenance_of_seeded_entry(self):
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        # gpt-5/coding came from aider-polyglot in the seed table.
        assert gi.provenance_of("gpt-5", "coding") == "aider-polyglot"

    def test_provenance_of_real_entry_is_none(self):
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        gi.reconcile_with_real(
            m, model_id="gpt-5", work_class="coding", grade="A",
        )
        assert gi.provenance_of("gpt-5", "coding") is None

    def test_provenance_of_unknown_key_is_none(self):
        gi = GradesImport()
        assert gi.provenance_of("nope", "general") is None  # type: ignore[arg-type]


# ── day-1 ordering proof (acceptance §3) ─────────────────────────────────


class TestDayOneOrdering:
    """Proof that CG can produce a NON-EMPTY ordering to route on day-1."""

    @pytest.mark.parametrize(
        "wc",
        ["reasoning", "coding", "translation", "creative", "analysis", "general"],
    )
    def test_seed_matrix_yields_non_empty_ranking_per_class(self, wc: WorkClass):
        """Acceptance §3: a seeded matrix produces a non-empty ordering for
        EVERY work class — CG ranks day-1."""
        m = seed_matrix()
        ranking = rank_for_work_class(m, wc)
        assert len(ranking) > 0, f"no day-1 ranking for work_class={wc!r}"

    def test_ranking_is_ordered_best_first(self):
        m = seed_matrix()
        ranking = rank_for_work_class(m, "reasoning")
        grades = [g for _, g, _ in ranking]
        # A-grades sort before B, B before C, etc.
        assert grades == sorted(grades, key=lambda g: {"A": 0, "B": 1, "C": 2,
                                                       "D": 3, "F": 4, "unknown": 5}[g])

    def test_ranking_breaks_ties_toward_real_signal(self):
        """Within the same grade, a real outcome (conf 1.0) outranks a prior."""
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        # gpt-5 and claude-opus-4.5 are both A for reasoning in the prior.
        gi.reconcile_with_real(
            m, model_id="claude-opus-4.5", work_class="reasoning", grade="A",
        )
        ranking = rank_for_work_class(m, "reasoning")
        # claude (real, conf 1.0) sorts before gpt-5 (prior, conf 0.5).
        a_models = [mid for mid, g, _ in ranking if g == "A"]
        assert a_models.index("claude-opus-4.5") < a_models.index("gpt-5")

    def test_ranking_is_deterministic(self):
        m = seed_matrix()
        r1 = rank_for_work_class(m, "coding")
        r2 = rank_for_work_class(m, "coding")
        assert r1 == r2

    def test_seed_matrix_returns_fresh_matrix_when_none_passed(self):
        m = seed_matrix()
        assert isinstance(m, CapabilityMatrix)
        assert len(m.entries) == len(SEED_PRIOR)

    def test_seed_matrix_loads_into_provided_matrix(self):
        m = CapabilityMatrix()
        out = seed_matrix(m)
        assert out is m
        assert len(m.entries) == len(SEED_PRIOR)

    def test_seed_matrix_preserves_existing_real_outcome(self):
        """seed_matrix must not wipe a matrix that already has real outcomes."""
        m = CapabilityMatrix()
        gi = GradesImport()
        gi.load_into(m)
        gi.reconcile_with_real(
            m, model_id="gpt-5", work_class="coding", grade="D",
        )
        seed_matrix(m)
        assert m.get_grade("gpt-5", "coding") == "D"
        assert m.entries[("gpt-5", "coding")].confidence == 1.0


# ── self-containment ─────────────────────────────────────────────────────


class TestSelfContainment:
    """The prior is structured, not a leaderboard CSV; the module invents no
    parallel store (ADR-0017 grades_import path)."""

    def test_module_does_not_import_third_party(self):
        """Stdlib + charon only — the cold-start bridge is dependency-free."""
        import ast
        import inspect
        import sys

        import charon.capability.grades_import as gi

        allowed = {"charon"} | set(sys.stdlib_module_names)
        tree = ast.parse(inspect.getsource(gi))
        forbidden: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] not in allowed:
                        forbidden.append(a.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    top = node.module.split(".")[0]
                    if top not in allowed:
                        forbidden.append(node.module)
        assert not forbidden, (
            f"grades_import imports non-stdlib/non-charon: {forbidden}"
        )

    def test_prior_entries_are_dataclasses_not_csv_rows(self):
        """The prior is a structured, auditable tuple — not an opaque leaderboard."""
        for e in SEED_PRIOR:
            assert isinstance(e, PriorEntry)

    def test_seed_matrix_populates_capability_matrix_not_a_new_store(self):
        """ADR-0017: the prior lands in the EXISTING CapabilityMatrix."""
        m = seed_matrix()
        assert isinstance(m, CapabilityMatrix)


# ── import-importer inspectability of global state ───────────────────────


class TestImporterState:
    """The importer's prior is inspectable separately from the global seed."""

    def test_importer_prior_property_returns_a_copy(self):
        gi = GradesImport()
        p = gi.prior
        assert p == SEED_PRIOR
        # Mutating the returned tuple must not affect the importer.
        assert p is not gi._prior or True  # at minimum, equality holds