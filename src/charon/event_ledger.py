"""The unified EVENT ledger — one append-only table, two rollups
(docs/CG_PLAN_v2.md §3; capability map #22 "learning substrate").

This is an **extension of the existing cost record**, not a second ledger.
``ledger.py`` stays the per-task, crash-safe write path and
:class:`~charon.types.Usage` stays the authoritative per-dispatch cost span
(ADR-0003 INV-1). What it is missing is the **actor axis** — the per-task
ledger names a *provider* and nothing else, so "which (model, provider) pair
produced this dollar, and did the work hold up?" cannot be answered — and a
**durable cross-task aggregate**: grading needs weeks of history that survives
branch deletion, and a per-task file under a worktree does not.

So an :class:`Event` is a ``Checkpoint``'s cost record plus:

* ``actor_model`` + ``actor_fingerprint`` alongside ``actor_provider`` — who
  did it. Provider is part of the identity, not a label on it: quantization,
  hardware and hidden system prompts mean the same model differs across
  providers, so the *pair* is the atom that gets graded (§2;
  COST-PER-TASK-REPLAY "Provider is part of the identity"). The fingerprint
  pins the served build within a pair (#30 reproducibility/replay).
* ``event_kind`` — what the spend was (original / remediation / review / test /
  integration), so a fix's dollars can be charged back to the actor that
  produced the thing being fixed (§1 amortized dollars-to-correct).
* ``outcome_class`` — routes the signal to the correct target (§2).
* ``defect_class`` + ``escape_stage`` — route *blame* and weight severity (§4/§5).
* ``work_class`` + ``tier`` — so a rollup keys straight into
  :class:`~charon.routing_policy.matrix.CapabilityMatrix` and
  :meth:`~charon.capability.grades_import.GradesImport.reconcile_with_real`
  without a translation layer.

**Two views, both a GROUP BY over the one table** (§3) — there is no second
store, and no number is written twice:

* :meth:`EventLedger.treasury` — Σ cost BY actor. Drives caps / kill-switch.
* :meth:`EventLedger.blame` — Σ cost of every event serving a unit, charged to
  the actor that *originated* that unit. Drives grading. A higher-tier model
  that fixes a cheap model's bug spends real dollars (its own treasury row)
  **and** those dollars land on the cheap model's blame row. One table, both
  truths.

Signal routing is **structural, not advisory** (§2): funding (402) and
rate-limit (429) events are operational and grade *nobody* — excluded from
blame and from grade inputs while still counting in treasury, because the
dollars were really spent. ``unavailable`` grades the **provider** only, never
the model. Only ``quality_*`` outcomes are gradable against the pair. And a
pre-merge failure demotes an actor only when the defect is ``implementation``
(§4) — a bad spec, a bad split or a flake must not teach the rankings garbage.

**Field names.** The row uses the CG_PLAN §3 vocabulary (``actor_provider`` /
``actor_model`` / ``actor_fingerprint`` / ``cost_usd`` / ``wall_clock_ms``),
which is what the author-independent acceptance contract
(``tests/test_event_schema.py``) was written against. The cost-per-task-replay
ADR names the same quantities ``provider`` / ``model_id`` / ``spend_usd``;
those are exposed as read-through aliases so a replay harness written to the
ADR reads this row unchanged. One row, one number, two spellings — never two
fields.

Stdlib only; same crash-safety discipline as ``ledger.py`` (append-only JSONL,
fsync per append, a torn trailing line is skipped and never guessed at).

Scope: this module is the SCHEMA + the store + the rollups. Wiring the dispatch
sites to write events, the replay harness, and the ``landed → confirmed``
transition are separate units.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args

from .ledger import Checkpoint
from .routing_policy.matrix import Grade, WorkClass
from .types import Usage

SCHEMA_VERSION = 1

EVENTS_FILENAME = "events.jsonl"
"""The one table, inside the store root. Named rather than inlined so an
operator (and a future upgraded ``make status``) can find it without reading
this module."""

# ── vocabularies (§3) ────────────────────────────────────────────────────
# Closed sets. An unrecognised value raises rather than being stored: a typo'd
# outcome_class would silently route a signal to the wrong target (or to none),
# which is exactly the failure mode "conflating them poisons the rankings"
# warns about. Loud beats a poisoned ranking discovered weeks later.

EventKind = Literal["original", "remediation", "review", "test", "integration"]
"""What the spend WAS. ``remediation`` is the one that carries a
``target_unit_id`` — it is how a fix's cost finds its way back to the actor
that produced the defect."""

OutcomeClass = Literal[
    "quality_pass",
    "quality_fail",
    "unavailable",
    "funding",
    "ratelimit",
    "environment",
]
"""How the event ended — the field that ROUTES the signal (§2)."""

DefectClass = Literal["spec", "decomposition", "implementation", "environment"]
"""Whose fault, when there is a defect. Only ``implementation`` demotes the
actor; ``decomposition`` charges the splitter (§5.4), ``spec`` charges intake,
``environment`` charges nobody."""

EscapeStage = Literal["test", "review", "production"]
"""How far the defect got before it was caught — the severity weight. A
``production`` escape is the strongest demotion signal (§4)."""

_EVENT_KINDS: frozenset[str] = frozenset(get_args(EventKind))
_OUTCOME_CLASSES: frozenset[str] = frozenset(get_args(OutcomeClass))
_DEFECT_CLASSES: frozenset[str] = frozenset(get_args(DefectClass))
_ESCAPE_STAGES: frozenset[str] = frozenset(get_args(EscapeStage))

# ── signal-routing policy (§2), as data ──────────────────────────────────

OPERATIONAL_OUTCOMES: frozenset[str] = frozenset({"funding", "ratelimit"})
"""Outcomes that grade **nobody**. A key hitting $0 or a 429 bucket emptying is
a treasury/operations event; it says nothing about whether the model can do the
work. Excluded from blame and from grade inputs — never from treasury."""

PROVIDER_ONLY_OUTCOMES: frozenset[str] = frozenset({"unavailable"})
"""Outcomes that grade the **provider** and never the model. A provider being
down is not evidence about the model it failed to serve."""

QUALITY_OUTCOMES: frozenset[str] = frozenset({"quality_pass", "quality_fail"})
"""The only outcomes that are gradable against the (model, provider) PAIR."""

DEMOTING_DEFECT: str = "implementation"
"""The one defect class that means "this actor was tiered too high" (§4)."""


class EventSchemaError(ValueError):
    """Raised when an event violates the schema. Always loud — a silently
    accepted bad event becomes a wrong grade, and a wrong grade is invisible."""


def new_event_id() -> str:
    """A fresh opaque event id. Random rather than a counter: events are
    appended by concurrent units to one shared table, and a counter would need
    a lock the append path deliberately does not take."""
    return uuid.uuid4().hex


# ── the one append-only row ──────────────────────────────────────────────


@dataclass
class Event:
    """One append-only event row (§3). Never mutated after it is written.

    Immutability is what makes the two views trustworthy: "done" is a lifecycle
    that can reopen months later (§4 ``confirmed → defective``), and a
    reopening appends a *new* remediation event rather than editing history —
    so a trailing cost number is always re-derivable from the table.

    The actor triple is flat rather than a nested object because the row is the
    unit of storage and of grouping: every view keys off
    ``(actor_provider, actor_model)``, and a nested actor would put a level of
    indirection between the table and the thing it is grouped by.
    """

    unit_id: str
    actor_provider: str
    actor_model: str
    event_kind: EventKind
    outcome_class: OutcomeClass
    actor_fingerprint: str = ""
    # The cost span — the same four numbers ledger.py's Usage records, kept
    # flat so a row is a row (see `usage` for the Usage view of them).
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    wall_clock_ms: int = 0
    event_id: str = field(default_factory=new_event_id)
    ts: float = field(default_factory=time.time)
    # Set on remediation: the unit being fixed. Its origin actor is who the
    # dollars are charged to in the blame view.
    target_unit_id: str | None = None
    defect_class: DefectClass | None = None
    escape_stage: EscapeStage | None = None
    # Routing/grading context. work_class keys straight into CapabilityMatrix;
    # tier is the work_class tier the unit was dispatched at.
    work_class: WorkClass = "general"
    tier: str = ""
    # Position within the task, mirroring the per-task ledger so an event can
    # be traced back to the Checkpoint it extends.
    attempt_seq: int = 0
    checkpoint_seq: int = 0
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        self._validate()

    # ── validation ──────────────────────────────────────────────────────

    def _validate(self) -> None:
        if not self.unit_id:
            raise EventSchemaError("unit_id is required (an event serves a unit)")
        if not self.actor_model or not self.actor_provider:
            raise EventSchemaError(
                "an event needs BOTH actor_model and actor_provider: the pair is "
                "the grading atom (§2), and provider-only is the gap this "
                f"schema exists to close (got {self.actor_provider!r}/"
                f"{self.actor_model!r})"
            )
        if self.event_kind not in _EVENT_KINDS:
            raise EventSchemaError(
                f"unknown event_kind {self.event_kind!r}; expected one of "
                f"{sorted(_EVENT_KINDS)}"
            )
        if self.outcome_class not in _OUTCOME_CLASSES:
            raise EventSchemaError(
                f"unknown outcome_class {self.outcome_class!r}; expected one of "
                f"{sorted(_OUTCOME_CLASSES)}"
            )
        if self.defect_class is not None and self.defect_class not in _DEFECT_CLASSES:
            raise EventSchemaError(
                f"unknown defect_class {self.defect_class!r}; expected one of "
                f"{sorted(_DEFECT_CLASSES)}"
            )
        if self.escape_stage is not None and self.escape_stage not in _ESCAPE_STAGES:
            raise EventSchemaError(
                f"unknown escape_stage {self.escape_stage!r}; expected one of "
                f"{sorted(_ESCAPE_STAGES)}"
            )
        if self.event_kind == "remediation" and not self.target_unit_id:
            # Without it the fix's dollars cannot reach the actor that caused
            # them, which is the whole point of §1's amortized cost.
            raise EventSchemaError(
                "a remediation event MUST name target_unit_id — otherwise its "
                "cost cannot be charged back to the origin actor (§1)"
            )

    # ── identity ────────────────────────────────────────────────────────

    @property
    def actor(self) -> tuple[str, str]:
        """The grouping key both views use: ``(actor_provider, actor_model)``.

        The pair, not the model: the same model served by two providers is two
        actors, because quantization and hidden prompts make them behave
        differently (§2)."""
        return (self.actor_provider, self.actor_model)

    # ── ADR-aligned aliases (COST-PER-TASK-REPLAY AttemptDetail) ────────
    # Read-through, never a second copy of the number.

    @property
    def provider(self) -> str:
        return self.actor_provider

    @property
    def model_id(self) -> str:
        return self.actor_model

    @property
    def fingerprint(self) -> str:
        return self.actor_fingerprint

    @property
    def spend_usd(self) -> float:
        """Dollars for this event — the ADR's name for ``cost_usd``."""
        return self.cost_usd

    @property
    def usage(self) -> Usage:
        """This row's cost span as the existing :class:`~charon.types.Usage`,
        so code already written against the per-task ledger's cost record reads
        an event without a shim."""
        return Usage(
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            cost_usd=self.cost_usd,
            latency_ms=self.wall_clock_ms,
        )

    # ── outcome semantics ───────────────────────────────────────────────

    @property
    def accepted(self) -> bool:
        """True iff the work held up: a quality pass with no defect recorded.

        The quality floor is load-bearing (COST-PER-TASK-REPLAY): "passed but
        needed changes" is NOT accepted, or cheap degenerates into "fails
        cheaply". A recorded ``defect_class`` is exactly that signal."""
        return self.outcome_class == "quality_pass" and self.defect_class is None

    @property
    def gradable(self) -> bool:
        """Does this event carry a quality signal about the actor pair?

        Only ``quality_pass`` / ``quality_fail`` do. Funding, rate-limit and
        unavailable are operational or provider-level (§2) — treasury records
        their dollars; no grade may be derived from them."""
        return self.outcome_class in QUALITY_OUTCOMES

    @property
    def grades_provider(self) -> bool:
        """Availability signal: names the provider, never the model."""
        return self.outcome_class in PROVIDER_ONLY_OUTCOMES

    @property
    def grades_nobody(self) -> bool:
        """Operational events: funding and rate-limit. Treasury, never grades."""
        return self.outcome_class in OPERATIONAL_OUTCOMES

    @property
    def demotes_actor(self) -> bool:
        """True iff this failure is evidence the actor was tiered too high.

        A quality failure alone is NOT enough (§4): filter by ``defect_class``
        first or the rankings learn from bad specs, bad splits and flakes.
        ``environment`` never demotes even though it is a failure."""
        return (
            self.outcome_class == "quality_fail"
            and self.defect_class == DEMOTING_DEFECT
        )

    # ── serialisation ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d: dict = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "ts": self.ts,
            "unit_id": self.unit_id,
            "actor_provider": self.actor_provider,
            "actor_model": self.actor_model,
            "event_kind": self.event_kind,
            "outcome_class": self.outcome_class,
            "cost_usd": self.cost_usd,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "wall_clock_ms": self.wall_clock_ms,
            "work_class": self.work_class,
        }
        # Optional fields are omitted when unset rather than written as null:
        # the file is append-only history, and "absent" is a smaller, honester
        # row than "present and empty".
        if self.actor_fingerprint:
            d["actor_fingerprint"] = self.actor_fingerprint
        if self.target_unit_id:
            d["target_unit_id"] = self.target_unit_id
        if self.defect_class is not None:
            d["defect_class"] = self.defect_class
        if self.escape_stage is not None:
            d["escape_stage"] = self.escape_stage
        if self.tier:
            d["tier"] = self.tier
        if self.attempt_seq:
            d["attempt_seq"] = self.attempt_seq
        if self.checkpoint_seq:
            d["checkpoint_seq"] = self.checkpoint_seq
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Event:
        version = d.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise EventSchemaError(
                f"event schema_version {version!r} is not readable by this build "
                f"(expected {SCHEMA_VERSION})"
            )
        try:
            return cls(
                unit_id=d["unit_id"],
                actor_provider=d["actor_provider"],
                actor_model=d["actor_model"],
                event_kind=d["event_kind"],
                outcome_class=d["outcome_class"],
                actor_fingerprint=d.get("actor_fingerprint", ""),
                cost_usd=float(d.get("cost_usd", 0.0)),
                tokens_in=int(d.get("tokens_in", 0)),
                tokens_out=int(d.get("tokens_out", 0)),
                wall_clock_ms=int(d.get("wall_clock_ms", 0)),
                event_id=d.get("event_id", ""),
                ts=float(d.get("ts", 0.0)),
                target_unit_id=d.get("target_unit_id"),
                defect_class=d.get("defect_class"),
                escape_stage=d.get("escape_stage"),
                work_class=d.get("work_class", "general"),
                tier=d.get("tier", ""),
                attempt_seq=int(d.get("attempt_seq", 0)),
                checkpoint_seq=int(d.get("checkpoint_seq", 0)),
            )
        except (KeyError, TypeError) as exc:
            raise EventSchemaError(f"event row malformed: {exc}") from exc

    # ── the bridge from the per-task ledger ─────────────────────────────

    @classmethod
    def from_checkpoint(
        cls,
        cp: Checkpoint,
        *,
        unit_id: str,
        actor_model: str,
        actor_fingerprint: str = "",
        event_kind: EventKind = "original",
        outcome_class: OutcomeClass | None = None,
        **kwargs: object,
    ) -> Event:
        """Lift a per-task :class:`~charon.ledger.Checkpoint` into an event.

        This is the "extension" made concrete: the checkpoint already carries
        the provider, the cost span and the reviewer verdict; the caller
        supplies only what the per-task ledger cannot know — which MODEL served
        the dispatch, and its fingerprint.

        ``outcome_class`` defaults from ``cp.reviewer_passed``:
        ``True → quality_pass``, ``False → quality_fail``, ``None →
        environment`` (no reviewer was consulted, so there is no quality signal
        to record — and inventing a pass would manufacture a grade nobody
        earned).
        """
        if outcome_class is None:
            if cp.reviewer_passed is True:
                outcome_class = "quality_pass"
            elif cp.reviewer_passed is False:
                outcome_class = "quality_fail"
            else:
                outcome_class = "environment"
        usage = cp.usage or Usage()
        return cls(
            unit_id=unit_id,
            actor_provider=cp.provider,
            actor_model=actor_model,
            actor_fingerprint=actor_fingerprint,
            event_kind=event_kind,
            outcome_class=outcome_class,
            cost_usd=usage.cost_usd,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            wall_clock_ms=usage.latency_ms,
            checkpoint_seq=cp.seq,
            **kwargs,  # type: ignore[arg-type]
        )


# ── grade inputs ─────────────────────────────────────────────────────────


@dataclass
class PairStats:
    """Grade input for one ``(actor_provider, actor_model, work_class)``.

    The shape grading consumes: ``accepted`` / ``graded`` give the acceptance
    rate, ``cost_usd`` is the total across ALL attempts (accepted or not — a
    model that burns five failed attempts before one pass pays for all six),
    and :attr:`cost_per_accepted_task` is the routing sort key
    COST-PER-TASK-REPLAY defines. ``work_class`` is carried so a caller can
    hand the key straight to
    :meth:`~charon.capability.grades_import.GradesImport.reconcile_with_real`.
    """

    actor_provider: str
    actor_model: str
    work_class: WorkClass
    accepted: int = 0
    graded: int = 0
    cost_usd: float = 0.0
    demotions: int = 0

    @property
    def model_id(self) -> str:
        """ADR alias — the name ``reconcile_with_real`` takes."""
        return self.actor_model

    @property
    def acceptance_rate(self) -> float:
        return self.accepted / self.graded if self.graded else 0.0

    @property
    def cost_per_accepted_task(self) -> float | None:
        """Total spend ÷ accepted tasks. ``None`` when nothing was accepted —
        a model that never passes has no cost-per-*accepted*-task, and
        reporting its spend as if it were one would rank "fails cheaply" top,
        which is precisely the degenerate case the quality floor exists to
        catch."""
        return self.cost_usd / self.accepted if self.accepted else None


# Acceptance-rate bands for the coarse, matrix-compatible grade. Coarse on
# purpose: these feed a matrix whose vocabulary is A–F (grades_import keeps the
# same bands), and a finer number would masquerade as precision this many
# samples cannot support.
_GRADE_BANDS: tuple[tuple[float, Grade], ...] = (
    (0.9, "A"),
    (0.75, "B"),
    (0.5, "C"),
    (0.25, "D"),
)


def grade_for(stats: PairStats, *, min_samples: int = 1) -> Grade:
    """Map a pair's acceptance rate onto the matrix's A–F vocabulary.

    Returns ``"unknown"`` below ``min_samples`` — an actor with too little
    history has no grade, and "unknown" is the value
    :class:`~charon.routing_policy.matrix.CapabilityMatrix` already means it
    by. This function does not write to the matrix (that is grading's job, via
    ``reconcile_with_real``); it only translates a rollup into the matrix's
    vocabulary.
    """
    if stats.graded < min_samples or stats.graded == 0:
        return "unknown"
    rate = stats.acceptance_rate
    for floor, grade in _GRADE_BANDS:
        if rate >= floor:
            return grade
    return "F"


# ── the durable cross-task store ─────────────────────────────────────────


class EventLedger:
    """Append-only event store + the views over it.

    Durable and **cross-task**: ONE table for all units, under a store root the
    caller chooses — deliberately not inside a worktree, because the whole
    point is history that outlives the branch that produced it (§3). A fresh
    instance pointed at the same root reads everything a previous instance
    wrote; nothing lives only in memory.

    Crash-safety mirrors ``ledger.py``: appends are fsync'd JSONL, and a torn
    trailing line (the only line a crash can tear) stops the read rather than
    being guessed at.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def path(self) -> Path:
        """The one table: ``<root>/events.jsonl``."""
        return self.root / EVENTS_FILENAME

    # ── write ───────────────────────────────────────────────────────────

    def record(self, **fields: object) -> str:
        """Append one event from its field values; returns its ``event_id``.

        The recording path callers use: a dispatch site knows its numbers, not
        an ``Event`` object. Validation happens in the row's constructor, so a
        bad event is refused at the moment of recording rather than at the
        moment someone tries to grade from it.
        """
        return self.append(Event(**fields)).event_id  # type: ignore[arg-type]

    def append(self, event: Event) -> Event:
        """Durably append an already-built event. Returns it for chaining."""
        line = json.dumps(event.to_dict(), separators=(",", ":")) + "\n"
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return event

    # ── read ────────────────────────────────────────────────────────────

    def events(self) -> list[Event]:
        """Every event, in append order. A torn trailing line is skipped."""
        if not self.path.exists():
            return []
        out: list[Event] = []
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                # torn write (only ever the last line); stop — do not guess.
                break
            out.append(Event.from_dict(d))
        return out

    def get(self, event_id: str) -> Event:
        """The event with ``event_id``. Raises :class:`KeyError` if absent —
        a missing event is a real error, never an empty row."""
        for ev in self.events():
            if ev.event_id == event_id:
                return ev
        raise KeyError(f"no event {event_id!r} in {self.path}")

    def gradable_events(self, events: list[Event] | None = None) -> list[Event]:
        """Only the events a grade may be derived from (§2).

        Funding, rate-limit and unavailable outcomes are filtered out here, at
        the source, so no consumer can accidentally grade a model for a dead
        key or a provider outage."""
        return [ev for ev in (self.events() if events is None else events) if ev.gradable]

    # ── view 1: treasury ────────────────────────────────────────────────

    def treasury(
        self, events: list[Event] | None = None
    ) -> dict[tuple[str, str], float]:
        """Σ ``cost_usd`` GROUP BY actor — what each pair actually cost us.

        Keyed ``(actor_provider, actor_model)``. Includes operational events
        (funding, rate-limit): those dollars were really spent, and treasury is
        about the money, not about blame."""
        rows: dict[tuple[str, str], float] = {}
        for ev in self.events() if events is None else events:
            rows[ev.actor] = rows.get(ev.actor, 0.0) + ev.cost_usd
        return rows

    # ── view 2: blame ───────────────────────────────────────────────────

    def origins(self, events: list[Event] | None = None) -> dict[str, tuple[str, str]]:
        """unit_id → the actor of its FIRST ``original`` event.

        The origin is who blame charges. First-wins: if a unit is re-attempted
        by a different pair, the later attempt is its own event and the unit's
        origin does not move — otherwise a defect could be laundered by
        retrying it elsewhere."""
        out: dict[str, tuple[str, str]] = {}
        for ev in self.events() if events is None else events:
            if ev.event_kind == "original" and ev.unit_id not in out:
                out[ev.unit_id] = ev.actor
        return out

    def blame(
        self, events: list[Event] | None = None
    ) -> dict[tuple[str, str], float]:
        """Amortized dollars-to-correct, keyed by the ORIGIN actor (§1).

        Every event serving a unit is charged to whoever originated that unit:
        a cheap model's bug, fixed by an expensive one, puts the expensive
        model's dollars on the cheap model's row — while the fixer's own
        treasury row still shows what it spent. That is what makes "$0.10 model
        that needs five $0.40 fixes" lose to "$1.00 model that succeeded once".

        Remediation events resolve through ``target_unit_id``; every other kind
        charges the origin of the unit it served. Operational events (funding /
        rate-limit) are excluded — they grade nobody (§2), and blame drives
        grading. An event whose unit has no recorded ``original`` is skipped
        rather than charged to a guess.
        """
        evs = self.events() if events is None else events
        origin_of = self.origins(evs)
        rows: dict[tuple[str, str], float] = {}
        for ev in evs:
            if ev.grades_nobody:
                continue
            origin = origin_of.get(ev.target_unit_id or ev.unit_id)
            if origin is None:
                continue
            rows[origin] = rows.get(origin, 0.0) + ev.cost_usd
        return rows

    # ── the handoff to grading ──────────────────────────────────────────

    def pair_stats(
        self, events: list[Event] | None = None
    ) -> dict[tuple[str, str, str], PairStats]:
        """``(actor_provider, actor_model, work_class)`` → :class:`PairStats`.

        Only gradable outcomes count toward ``graded``; availability and
        operational events never reach the pair (§2). Cost counts every
        non-operational event by the actor, so failed attempts are paid for in
        the cost-per-accepted-task numerator — that is what makes "cheap but
        needs five fixes" lose.
        """
        rows: dict[tuple[str, str, str], PairStats] = {}
        for ev in self.events() if events is None else events:
            if ev.grades_nobody or ev.grades_provider:
                continue
            key = (ev.actor_provider, ev.actor_model, ev.work_class)
            row = rows.setdefault(
                key,
                PairStats(
                    actor_provider=ev.actor_provider,
                    actor_model=ev.actor_model,
                    work_class=ev.work_class,
                ),
            )
            row.cost_usd += ev.cost_usd
            if ev.gradable:
                row.graded += 1
                if ev.accepted:
                    row.accepted += 1
                if ev.demotes_actor:
                    row.demotions += 1
        return rows

    def provider_availability(
        self, events: list[Event] | None = None
    ) -> dict[str, tuple[int, int]]:
        """provider → (unavailable_events, total_non_operational_events).

        The availability signal, kept strictly separate from quality: it names
        a provider and never a model (§2), so a provider being down cannot
        demote a model that was merely routed to it."""
        rows: dict[str, list[int]] = {}
        for ev in self.events() if events is None else events:
            if ev.grades_nobody:
                continue
            counts = rows.setdefault(ev.actor_provider, [0, 0])
            counts[1] += 1
            if ev.grades_provider:
                counts[0] += 1
        return {p: (c[0], c[1]) for p, c in rows.items()}


__all__ = [
    "SCHEMA_VERSION",
    "EVENTS_FILENAME",
    "EventKind",
    "OutcomeClass",
    "DefectClass",
    "EscapeStage",
    "OPERATIONAL_OUTCOMES",
    "PROVIDER_ONLY_OUTCOMES",
    "QUALITY_OUTCOMES",
    "DEMOTING_DEFECT",
    "EventSchemaError",
    "Event",
    "PairStats",
    "EventLedger",
    "new_event_id",
    "grade_for",
]
