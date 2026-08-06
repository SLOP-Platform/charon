"""Implementation-side tests for the unified event ledger.

``tests/test_event_schema.py`` is the author-independent CONTRACT (written from
docs/CG_PLAN_v2.md §3 before the implementation, by a different actor) and is
never edited to make anything pass. This file is the implementer's own
coverage, ADDED alongside it: the store's crash behaviour, the signal-routing
rules the contract only samples, the bridge from ``ledger.py``'s existing cost
record, and the proof that grading wires to the modules already on master.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon.capability.grades_import import GradesImport, seed_matrix
from charon.event_ledger import (
    Event,
    EventLedger,
    EventSchemaError,
    grade_for,
)
from charon.ledger import Checkpoint
from charon.routing_policy.matrix import CapabilityMatrix
from charon.types import Usage


def _fields(**over) -> dict:
    """Default event fields; each test overrides only its subject."""
    base = dict(
        unit_id="U1",
        actor_provider="provider-a",
        actor_model="cheap-model",
        event_kind="original",
        outcome_class="quality_pass",
        cost_usd=0.10,
        tokens_in=100,
        tokens_out=50,
        wall_clock_ms=1200,
    )
    base.update(over)
    return base


def _ev(**over) -> Event:
    return Event(**_fields(**over))


class TestActorAxis:
    """The axis the per-task ledger is missing: model + fingerprint."""

    def test_actor_key_is_the_provider_model_pair(self) -> None:
        """The same model on two providers is two actors (§2)."""
        assert _ev().actor == ("provider-a", "cheap-model")
        assert _ev(actor_provider="provider-b").actor != _ev().actor

    def test_actor_model_is_required(self) -> None:
        """A provider-only event is the CURRENT gap; the schema refuses it."""
        with pytest.raises(EventSchemaError, match="actor_model and actor_provider"):
            _ev(actor_model="")

    def test_fingerprint_is_optional_and_omitted_when_unset(self) -> None:
        """A provider reporting no fingerprint must not block recording."""
        ev = _ev()
        assert ev.actor_fingerprint == ""
        assert "actor_fingerprint" not in ev.to_dict()

    def test_adr_aliases_read_through_to_the_row(self) -> None:
        """COST-PER-TASK-REPLAY's names for the same fields — not copies."""
        ev = _ev(actor_fingerprint="fp1", cost_usd=0.42)
        assert ev.model_id == ev.actor_model
        assert ev.provider == ev.actor_provider
        assert ev.fingerprint == "fp1"
        assert ev.spend_usd == 0.42 == ev.cost_usd


class TestExtendsExistingCostRecord:
    """It extends ledger.py's cost record — it does not re-model it."""

    def test_usage_view_returns_the_existing_cost_record(self) -> None:
        """Code written against Usage reads an event without a shim."""
        assert _ev().usage == Usage(
            tokens_in=100, tokens_out=50, cost_usd=0.10, latency_ms=1200
        )

    def test_from_checkpoint_adds_only_the_missing_axis(self) -> None:
        """A Checkpoint already knows provider, cost and the reviewer verdict;
        the caller supplies just the model and fingerprint."""
        cp = Checkpoint(
            seq=3,
            provider="provider-a",
            commit="abc123",
            verified=["c1"],
            remaining=[],
            usage=Usage(tokens_in=10, tokens_out=5, cost_usd=0.03, latency_ms=900),
            reviewer_passed=True,
        )
        ev = Event.from_checkpoint(
            cp, unit_id="U1", actor_model="gpt-x", actor_fingerprint="fp1"
        )
        assert ev.actor == ("provider-a", "gpt-x")
        assert ev.actor_fingerprint == "fp1"
        assert ev.usage == cp.usage
        assert ev.checkpoint_seq == 3
        assert ev.outcome_class == "quality_pass"

    @pytest.mark.parametrize(
        ("reviewer_passed", "expected"),
        [
            (True, "quality_pass"),
            (False, "quality_fail"),
            (None, "environment"),
        ],
    )
    def test_checkpoint_verdict_maps_to_outcome_class(
        self, reviewer_passed: bool | None, expected: str
    ) -> None:
        """No reviewer means NO quality signal — never an invented pass."""
        cp = Checkpoint(
            seq=1,
            provider="provider-a",
            commit=None,
            verified=[],
            remaining=["c1"],
            reviewer_passed=reviewer_passed,
        )
        ev = Event.from_checkpoint(cp, unit_id="U1", actor_model="gpt-x")
        assert ev.outcome_class == expected


class TestVocabularies:
    """Closed sets — a typo must raise, never route a signal nowhere."""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("event_kind", "refactor"),
            ("outcome_class", "ok"),
            ("defect_class", "vibes"),
            ("escape_stage", "staging"),
        ],
    )
    def test_unknown_vocabulary_value_raises(self, field: str, value: str) -> None:
        """Loud beats a poisoned ranking found weeks later."""
        with pytest.raises(EventSchemaError, match=f"unknown {field}"):
            _ev(**{field: value})

    def test_remediation_requires_a_target_unit(self) -> None:
        """Without it the fix's dollars cannot reach the origin actor (§1)."""
        with pytest.raises(EventSchemaError, match="target_unit_id"):
            _ev(event_kind="remediation")

    def test_unit_id_is_required(self) -> None:
        """Every event serves a unit; an orphan event is unattributable."""
        with pytest.raises(EventSchemaError, match="unit_id"):
            _ev(unit_id="")

    def test_a_bad_event_is_refused_at_record_time(self, tmp_path: Path) -> None:
        """Validation fires when recording, not when someone tries to grade."""
        led = EventLedger(tmp_path / "events")
        with pytest.raises(EventSchemaError):
            led.record(**_fields(outcome_class="ok"))
        assert led.events() == []


class TestSignalRouting:
    """§2: three signals, three targets. Conflating them poisons rankings."""

    @pytest.mark.parametrize("outcome", ["funding", "ratelimit"])
    def test_operational_outcomes_grade_nobody(self, outcome: str) -> None:
        """A dead key or an empty 429 bucket is not a capability judgement."""
        ev = _ev(outcome_class=outcome)
        assert ev.grades_nobody
        assert not ev.gradable
        assert not ev.grades_provider

    def test_unavailable_grades_the_provider_only(self) -> None:
        """A provider being down is no evidence about the model."""
        ev = _ev(outcome_class="unavailable")
        assert ev.grades_provider
        assert not ev.gradable

    @pytest.mark.parametrize("outcome", ["quality_pass", "quality_fail"])
    def test_quality_outcomes_are_gradable(self, outcome: str) -> None:
        """Only quality signal reaches the (provider, model) pair."""
        assert _ev(outcome_class=outcome).gradable

    @pytest.mark.parametrize(
        ("defect", "demotes"),
        [
            ("implementation", True),
            ("spec", False),
            ("decomposition", False),
            ("environment", False),
            (None, False),
        ],
    )
    def test_only_implementation_defects_demote(
        self, defect: str | None, demotes: bool
    ) -> None:
        """§4: a bad spec, a bad split or a flake must not move a tier."""
        assert _ev(outcome_class="quality_fail", defect_class=defect).demotes_actor is (
            demotes
        )

    def test_a_pass_with_a_recorded_defect_is_not_accepted(self) -> None:
        """The quality floor: 'passed but needed changes' does not count."""
        assert _ev().accepted
        assert not _ev(defect_class="implementation").accepted


class TestViews:
    """One table, two GROUP BYs (§3) — beyond the contract's two samples."""

    def test_operational_events_count_in_treasury_but_never_in_blame(
        self, tmp_path: Path
    ) -> None:
        """The dollars were really spent; the grade is still nobody's."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields(cost_usd=1.0))
        led.record(
            **_fields(event_kind="review", outcome_class="funding", cost_usd=2.0)
        )
        assert led.treasury()[("provider-a", "cheap-model")] == pytest.approx(3.0)
        assert led.blame()[("provider-a", "cheap-model")] == pytest.approx(1.0)

    def test_review_and_test_spend_charges_the_units_origin(
        self, tmp_path: Path
    ) -> None:
        """Every event serving a unit lands on that unit's origin, not just
        remediations — verification is part of dollars-to-correct (§1)."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields(cost_usd=0.10))
        led.record(
            **_fields(
                actor_provider="provider-b",
                actor_model="reviewer-model",
                event_kind="review",
                cost_usd=0.05,
            )
        )
        assert led.blame()[("provider-a", "cheap-model")] == pytest.approx(0.15)

    def test_origin_does_not_move_on_a_later_attempt(self, tmp_path: Path) -> None:
        """First-wins, so a defect cannot be laundered by retrying elsewhere."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields(actor_model="first-model"))
        led.record(**_fields(actor_provider="provider-b", actor_model="second-model"))
        assert led.origins()["U1"] == ("provider-a", "first-model")

    def test_events_for_an_unknown_unit_are_skipped_not_guessed(
        self, tmp_path: Path
    ) -> None:
        """A remediation whose target has no recorded original charges no one."""
        led = EventLedger(tmp_path / "events")
        led.record(
            **_fields(
                unit_id="F9",
                event_kind="remediation",
                target_unit_id="ghost-unit",
                cost_usd=0.5,
            )
        )
        assert led.blame() == {}

    def test_availability_is_a_separate_provider_signal(self, tmp_path: Path) -> None:
        """The provider is demoted; the model it served is untouched."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields(actor_provider="flaky", outcome_class="unavailable"))
        led.record(**_fields(unit_id="U2", actor_provider="flaky"))
        assert led.provider_availability()["flaky"] == (1, 2)


class TestDurableStore:
    """Cross-task history that outlives the branch that produced it."""

    def test_every_field_survives_the_round_trip(self, tmp_path: Path) -> None:
        """Including the classification fields the views read."""
        led = EventLedger(tmp_path / "events")
        eid = led.record(
            **_fields(
                outcome_class="quality_fail",
                defect_class="implementation",
                escape_stage="production",
                work_class="coding",
                tier="high",
                attempt_seq=2,
                actor_fingerprint="fp_x",
            )
        )
        got = EventLedger(tmp_path / "events").get(eid)
        assert got.defect_class == "implementation"
        assert got.escape_stage == "production"
        assert got.work_class == "coding"
        assert got.tier == "high"
        assert got.attempt_seq == 2
        assert got.actor_fingerprint == "fp_x"

    def test_missing_store_reads_as_empty(self, tmp_path: Path) -> None:
        """A fresh install has no history — that is not corruption."""
        assert EventLedger(tmp_path / "nope").events() == []

    def test_get_raises_on_a_missing_event(self, tmp_path: Path) -> None:
        """A missing event is a real error, never an empty row."""
        with pytest.raises(KeyError):
            EventLedger(tmp_path / "events").get("nope")

    def test_torn_trailing_line_is_skipped_not_guessed(self, tmp_path: Path) -> None:
        """A crash mid-append tears only the last line; earlier rows stand."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields())
        with open(led.path, "a", encoding="utf-8") as fh:
            fh.write('{"unit_id": "U2", "actor_pro')
        events = led.events()
        assert len(events) == 1
        assert events[0].unit_id == "U1"

    def test_history_is_append_only(self, tmp_path: Path) -> None:
        """Two records leave two lines; nothing is rewritten in place."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields())
        led.record(**_fields(unit_id="U2"))
        assert len(led.path.read_text().strip().splitlines()) == 2

    def test_unreadable_schema_version_raises(self) -> None:
        """A future row is never silently reinterpreted by an older build."""
        row = _ev().to_dict()
        row["schema_version"] = 99
        with pytest.raises(EventSchemaError, match="schema_version"):
            Event.from_dict(row)

    def test_checkpoint_position_survives_the_round_trip(
        self, tmp_path: Path
    ) -> None:
        """An event must stay traceable to the Checkpoint it extends, or the
        per-task ledger and the cross-task table cannot be reconciled."""
        cp = Checkpoint(
            seq=7,
            provider="provider-a",
            commit="abc",
            verified=[],
            remaining=[],
            usage=Usage(cost_usd=0.02),
            reviewer_passed=True,
        )
        led = EventLedger(tmp_path / "events")
        ev = led.append(
            Event.from_checkpoint(cp, unit_id="U1", actor_model="gpt-x", attempt_seq=2)
        )
        got = EventLedger(tmp_path / "events").get(ev.event_id)
        assert got.checkpoint_seq == 7
        assert got.attempt_seq == 2

    def test_a_row_missing_a_required_field_raises(self) -> None:
        """A truncated or hand-edited row is refused, not half-read."""
        row = _ev().to_dict()
        del row["actor_model"]
        with pytest.raises(EventSchemaError, match="malformed"):
            Event.from_dict(row)

    def test_blank_lines_are_skipped(self, tmp_path: Path) -> None:
        """Whitespace between rows is not data and is not corruption."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields())
        with open(led.path, "a", encoding="utf-8") as fh:
            fh.write("\n\n")
        led.record(**_fields(unit_id="U2"))
        assert [ev.unit_id for ev in led.events()] == ["U1", "U2"]

    def test_row_is_plain_json(self, tmp_path: Path) -> None:
        """The table stays greppable and tool-readable, not a pickle."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields())
        row = json.loads(led.path.read_text().splitlines()[0])
        assert row["actor_model"] == "cheap-model"
        assert row["actor_provider"] == "provider-a"
        assert row["cost_usd"] == pytest.approx(0.10)


class TestGradeInputs:
    """The handoff to grading — a key the existing matrix already speaks."""

    @staticmethod
    def _two_models(tmp_path: Path) -> EventLedger:
        """A cheap model that passes 1 of 4; a dear one that lands first time."""
        led = EventLedger(tmp_path / "events")
        for i in range(3):
            led.record(
                **_fields(
                    unit_id=f"C{i}",
                    outcome_class="quality_fail",
                    defect_class="implementation",
                    escape_stage="review",
                    work_class="coding",
                )
            )
        led.record(**_fields(unit_id="C3", work_class="coding"))
        led.record(
            **_fields(
                unit_id="D0",
                actor_provider="provider-b",
                actor_model="dear-model",
                work_class="coding",
                cost_usd=0.30,
            )
        )
        return led

    def test_pair_stats_key_carries_provider_and_work_class(
        self, tmp_path: Path
    ) -> None:
        """Provider is in the identity; work_class keys into the matrix."""
        stats = self._two_models(tmp_path).pair_stats()
        assert ("provider-a", "cheap-model", "coding") in stats
        assert ("provider-b", "dear-model", "coding") in stats

    def test_cost_per_accepted_task_punishes_cheap_but_failing(
        self, tmp_path: Path
    ) -> None:
        """$0.40 for one pass loses to $0.30 for one pass — the §1 metric."""
        stats = self._two_models(tmp_path).pair_stats()
        cheap = stats[("provider-a", "cheap-model", "coding")].cost_per_accepted_task
        dear = stats[("provider-b", "dear-model", "coding")].cost_per_accepted_task
        assert cheap is not None and dear is not None
        assert cheap == pytest.approx(0.40)
        assert dear == pytest.approx(0.30)
        assert cheap > dear

    def test_never_accepted_has_no_cost_per_accepted_task(
        self, tmp_path: Path
    ) -> None:
        """None, not zero — 'fails cheaply' must not sort to the top."""
        led = EventLedger(tmp_path / "events")
        led.record(
            **_fields(outcome_class="quality_fail", defect_class="implementation")
        )
        stats = led.pair_stats()[("provider-a", "cheap-model", "general")]
        assert stats.cost_per_accepted_task is None
        assert stats.acceptance_rate == 0.0
        assert stats.demotions == 1

    def test_operational_and_availability_events_never_reach_the_pair(
        self, tmp_path: Path
    ) -> None:
        """One grades nobody, one grades the provider — neither the pair."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields(outcome_class="funding"))
        led.record(**_fields(unit_id="U2", outcome_class="unavailable"))
        assert led.pair_stats() == {}

    def test_grade_bands_map_acceptance_rate_to_the_matrix_vocabulary(
        self, tmp_path: Path
    ) -> None:
        """A–F, the same coarse bands grades_import already uses: the dear
        model passed its one graded task (1.0 → A), the cheap one passed one of
        four (0.25 → D)."""
        stats = self._two_models(tmp_path).pair_stats()
        assert grade_for(stats[("provider-b", "dear-model", "coding")]) == "A"
        assert grade_for(stats[("provider-a", "cheap-model", "coding")]) == "D"

    def test_an_actor_that_almost_never_passes_grades_f(
        self, tmp_path: Path
    ) -> None:
        """Below the lowest band there is a floor, and it is F — a rate of
        1-in-5 must not fall through to 'unknown' and read as no evidence."""
        led = EventLedger(tmp_path / "events")
        for i in range(4):
            led.record(
                **_fields(
                    unit_id=f"U{i}",
                    outcome_class="quality_fail",
                    defect_class="implementation",
                )
            )
        led.record(**_fields(unit_id="U4"))
        stats = led.pair_stats()[("provider-a", "cheap-model", "general")]
        assert stats.acceptance_rate == pytest.approx(0.2)
        assert grade_for(stats) == "F"

    def test_operational_events_are_absent_from_availability(
        self, tmp_path: Path
    ) -> None:
        """A funding stall is not an outage: it must not count against the
        provider's availability denominator either (§2)."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields(outcome_class="funding"))
        led.record(**_fields(unit_id="U2", outcome_class="unavailable"))
        led.record(**_fields(unit_id="U3"))
        assert led.provider_availability()["provider-a"] == (1, 2)

    def test_grade_is_unknown_below_min_samples(self, tmp_path: Path) -> None:
        """Too little history is 'unknown' — the value the matrix means by it."""
        stats = self._two_models(tmp_path).pair_stats()
        dear = stats[("provider-b", "dear-model", "coding")]
        assert grade_for(dear, min_samples=5) == "unknown"


class TestGradingWiresToExistingModules:
    """Compatibility proof: no translation layer needed on master's grader."""

    def test_pair_stats_feed_reconcile_with_real(self, tmp_path: Path) -> None:
        """A real outcome from the event ledger REPLACES the seeded prior."""
        matrix: CapabilityMatrix = seed_matrix()
        importer = GradesImport()
        importer.load_into(matrix)

        led = EventLedger(tmp_path / "events")
        for i in range(4):
            led.record(
                **_fields(unit_id=f"U{i}", actor_model="glm-5.2", work_class="coding")
            )
        stats = led.pair_stats()[("provider-a", "glm-5.2", "coding")]

        importer.reconcile_with_real(
            matrix,
            model_id=stats.model_id,
            work_class=stats.work_class,
            grade=grade_for(stats),
            samples=stats.graded,
        )
        assert matrix.get_grade("glm-5.2", "coding") == "A"
        assert not importer.is_provisional(
            matrix, model_id="glm-5.2", work_class="coding"
        )
        assert importer.real_samples("glm-5.2", "coding") == 4

    def test_work_class_vocabulary_matches_the_matrix(self, tmp_path: Path) -> None:
        """The event's work_class is the matrix's WorkClass, not a parallel set."""
        led = EventLedger(tmp_path / "events")
        led.record(**_fields(actor_model="m", work_class="reasoning"))
        matrix = CapabilityMatrix()
        (stats,) = led.pair_stats().values()
        matrix.set_grade(stats.model_id, stats.work_class, grade_for(stats))
        assert matrix.get_grade("m", "reasoning") == "A"
