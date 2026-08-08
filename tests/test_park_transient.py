"""PARK-TRANSIENT — a provider park is a BOUNDED COOLDOWN, not a terminal state.

The live incident: 7 providers parked since Aug 3 06:52, none of them out of
funds, and ``_maybe_auto_unpark`` reachable ONLY via ``mode == "poll"`` which
no live provider carries — a parked provider with no ``mode`` was parked
forever. This test proves the deadline mechanism that re-arms them:

1. Every ``park()`` sets a wall-clock deadline (base 15 min, doubling per
   re-park, capped at 6h).
2. ``is_parked()`` / ``parked_providers()`` expire parks whose deadline has
   passed — a viable provider re-enters rotation with NO operator action.
3. A legacy ``{"parked": [...]}`` file (no deadlines) re-arms every provider in
   it on the first read — the live-incident migration.
4. Strikes survive expiry (next park backs off further); ``unpark()`` is a
   clean re-arm and resets them.
5. Expiry persists to disk; ``parked_providers()`` and ``is_parked()`` agree.
6. D-012 invariant: ``balance_park.json`` keeps a top-level ``"parked"`` list.
7. ``_has_viable_leg`` hides an alias whose every leg is parked, lists one
   with a live leg, and lists everything when no balance tracker exists.

Every test injects ``park_clock`` so time is deterministic. Each test is
FAIL-ON-REVERT — reverting the source hunk named in its docstring turns it red.
"""
from __future__ import annotations

import json
from pathlib import Path

from charon.balance import (
    _PARK_COOLDOWN_BASE_S,
    _PARK_COOLDOWN_MAX_S,
    BalanceTracker,
)
from charon.console_router import _has_viable_leg
from charon.proxy_server import UpstreamRoute


class _Clock:
    """Deterministic wall-clock for park deadlines."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def test_park_then_immediately_parked():
    """park() → is_parked() True while inside the cooldown window.

    FAIL-ON-REVERT: removing the ``_park_until[p] = park_clock() + ...`` line
    in ``park()`` makes this False (or, if the deadline is not set at all,
    ``_expire_due`` treats the park as immediately expired)."""
    clock = _Clock()
    bt = BalanceTracker(park_clock=clock)
    bt.park("openrouter")
    assert bt.is_parked("openrouter")
    # Still well inside the 900s window — a deadline set at park time keeps it.
    clock.advance(300)
    assert bt.is_parked("openrouter")


def test_park_expires_after_cooldown_no_human_touch():
    """Advance the clock past the deadline → is_parked() False. ← the ticket.

    FAIL-ON-REVERT: reverting ``_expire_due()``'s deadline comparison (or its
    call in ``is_parked()``) leaves the provider parked forever — this goes
    red with ``assert bt.is_parked("openrouter") is False``."""
    clock = _Clock()
    bt = BalanceTracker(park_clock=clock)
    bt.park("openrouter")
    assert bt.is_parked("openrouter")
    clock.advance(_PARK_COOLDOWN_BASE_S + 1)
    assert bt.is_parked("openrouter") is False, (
        "park must auto-expire once its cooldown passes — no operator action")


def test_legacy_park_file_without_deadlines_rerarms_on_read():
    """Legacy ``{"parked": [...]}`` with no deadlines → is_parked() False.

    ← the live incident: all 7 stuck providers re-enter rotation on the first
    read.

    FAIL-ON-REVERT: ``_expire_due`` treats a park with no ``park_until`` entry
    as EXPIRED. If a deadline-less park were read as fresh (e.g. only comparing
    a present-but-future deadline, or not calling ``_expire_due`` from
    ``is_parked``), this goes red."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "balance_park.json").write_text(
            json.dumps({"parked": ["openrouter"]}), encoding="utf-8")
        bt = BalanceTracker(state_dir=p, park_clock=_Clock())
        assert bt.is_parked("openrouter") is False, (
            "a legacy park with no deadline must be treated as already expired")


def test_repark_after_expiry_backs_off_doubled():
    """Re-park after expiry → cooldown doubles (strikes survive expiry).

    FAIL-ON-REVERT: if ``park()`` read strikes from a set that ``_expire_due``
    cleared (or never recorded them), the second park would be back at the
    base 900s, not 1800s — asserting it is still parked at t+900+450 then
    expired at t+1800 goes red."""
    clock = _Clock()
    bt = BalanceTracker(park_clock=clock)
    bt.park("p")
    assert bt.is_parked("p")
    clock.advance(_PARK_COOLDOWN_BASE_S + 1)
    assert not bt.is_parked("p")  # expired, strikes KEPT
    clock.advance(1)
    bt.park("p")  # strike 2 → 1800s
    clock.advance(_PARK_COOLDOWN_BASE_S)  # base window alone would have expired it
    assert bt.is_parked("p"), (
        "re-park after expiry must back off to 2x base — strikes were lost on expiry")
    clock.advance(_PARK_COOLDOWN_BASE_S + 1)  # now past the doubled deadline
    assert not bt.is_parked("p")


def test_unpark_resets_strikes_back_to_base():
    """unpark() clears strikes → the next park is back at the base cooldown.

    FAIL-ON-REVERT: if ``unpark()`` did NOT clear ``_park_strikes``, the next
    park after one expiry would carry strike 2 (1800s); asserting it expires
    at base+1 after an unpark-→-repark cycle goes red."""
    clock = _Clock()
    bt = BalanceTracker(park_clock=clock)
    bt.park("p")
    assert bt.is_parked("p")
    bt.unpark("p")
    assert not bt.is_parked("p")
    clock.advance(1)
    bt.park("p")  # clean re-arm → strike 1 → base cooldown
    clock.advance(_PARK_COOLDOWN_BASE_S + 1)
    assert not bt.is_parked("p"), (
        "unpark() must reset the strike counter — a genuine recovery is a clean re-arm")


def test_expiry_persists_across_restart():
    """After expiry, a NEW tracker over the same state_dir does not see the park.

    FAIL-ON-REVERT: if ``is_parked()``/``parked_providers()`` expired a park
    in memory but did NOT persist the shrink, a restarted tracker reloads the
    still-parked provider from disk and this goes red."""
    clock = _Clock()
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        bt1 = BalanceTracker(state_dir=p, park_clock=clock)
        bt1.park("openrouter")
        clock.advance(_PARK_COOLDOWN_BASE_S + 1)
        assert not bt1.is_parked("openrouter")  # expires and persists the shrink
        bt2 = BalanceTracker(state_dir=p, park_clock=clock)
        assert not bt2.is_parked("openrouter"), (
            "expired park was not persisted — a restarted tracker still sees it parked")


def test_parked_providers_agrees_with_is_parked():
    """parked_providers() and is_parked() never disagree on an expired park.

    FAIL-ON-REVERT: if ONLY ``is_parked()`` called ``_expire_due`` (and
    ``parked_providers()`` did not), one surface would report the provider
    parked while the other did not."""
    clock = _Clock()
    bt = BalanceTracker(park_clock=clock)
    bt.park("a")
    bt.park("b")
    clock.advance(_PARK_COOLDOWN_BASE_S + 1)
    parked = bt.parked_providers()
    assert "a" not in parked and "b" not in parked
    assert not bt.is_parked("a") and not bt.is_parked("b")
    assert parked == bt.parked_providers()  # idempotent, stable


def test_park_until_capped_at_max_however_many_strikes():
    """No matter how many strikes, a park_until never exceeds the 6h cap.

    FAIL-ON-REVERT: dropping the ``_PARK_COOLDOWN_MAX_S`` clamp (or the n clamp
    in ``_cooldown_for``) makes a high strike count park for 2**n × 900s — this
    goes red on the ``<=`` cap assert."""
    clock = _Clock()
    bt = BalanceTracker(park_clock=clock)
    for _ in range(40):  # far beyond the 32 clamp
        bt.park("p")
    deadline = bt._park_until["p"]  # type: ignore[attr-defined]
    assert deadline - clock.t <= _PARK_COOLDOWN_MAX_S, (
        "park deadline must never exceed _PARK_COOLDOWN_MAX_S, however many strikes")


def test_unpark_on_never_parked_writes_no_file():
    """unpark() on a never-parked provider must NOT write the park file.

    FAIL-ON-REVERT: the redundant-save fix — if ``unpark()`` always called
    ``_save_parked()`` (the pre-fix behaviour), the request path would rewrite
    the park file on every positive-balance leg once balance config lands."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        bt = BalanceTracker(state_dir=Path(d), park_clock=_Clock())
        bt.unpark("ghost")
        assert not (Path(d) / "balance_park.json").exists(), (
            "unpark() on a never-parked provider must not touch disk")


def test_save_parked_keeps_top_level_parked_list_and_d012_invariant():
    """balance_park.json keeps a top-level ``"parked"`` LIST, and
    gateway._has_persisted_parks still returns True for it.

    FAIL-ON-REVERT: if ``_save_parked`` moved the parked set under a new key
    (e.g. a nested dict), ``gateway._has_persisted_parks`` (which reads exactly
    ``data["parked"]``) would stop firing — the D-012 money leak re-opens."""
    import tempfile

    from charon.gateway import _has_persisted_parks
    with tempfile.TemporaryDirectory() as d:
        bt = BalanceTracker(state_dir=Path(d), park_clock=_Clock())
        bt.park("openrouter")
        data = json.loads((Path(d) / "balance_park.json").read_text())
        assert isinstance(data.get("parked"), list)
        assert "openrouter" in data["parked"]
        assert _has_persisted_parks(Path(d)) is True, (
            "gateway._has_persisted_parks must still fire — 'parked' must stay a "
            "top-level list (D-012 money-leak invariant)")


def test_has_viable_leg_hides_fully_parked_alias():
    """_has_viable_leg: all legs parked → alias hidden; one live leg → listed;
    balance_tracker None → every alias listed (backward compat).

    FAIL-ON-REVERT: without the ``_has_viable_leg`` filter, a fully-parked
    alias would still be listed in /v1/models but unreachable — the exact
    catalog/router split the ticket's serial_justification warns about."""
    bt = BalanceTracker(park_clock=_Clock())
    bt.park("a")
    bt.park("b")
    srv = _Srv(
        balance_tracker=bt,
        pools={
            "m": [
                UpstreamRoute("http://a", "ka", provider="a", upstream_model="ma"),
                UpstreamRoute("http://b", "kb", provider="b", upstream_model="mb"),
            ],
        },
        routes={},
    )
    assert _has_viable_leg("m", srv) is False, (
        "an alias whose every leg is parked must not be listed")

    srv_live = _Srv(
        balance_tracker=bt,
        pools={
            "m": [
                UpstreamRoute("http://a", "ka", provider="a", upstream_model="ma"),
                UpstreamRoute("http://c", "kc", provider="c", upstream_model="mc"),
            ],
        },
        routes={},
    )
    assert _has_viable_leg("m", srv_live) is True, (
        "an alias with at least one non-parked, non-drained leg must be listed")

    srv_notrack = _Srv(balance_tracker=None, pools={
        "m": [UpstreamRoute("http://a", "ka", provider="a", upstream_model="ma")],
    }, routes={})
    assert _has_viable_leg("m", srv_notrack) is True, (
        "with no balance tracker every alias must be listed (backward compat)")

    # Fall back through routes (no pool entry) — single non-parked route.
    srv_route = _Srv(balance_tracker=bt, pools={}, routes={
        "solo": UpstreamRoute("http://c", "kc", provider="c", upstream_model="mc"),
    })
    assert _has_viable_leg("solo", srv_route) is True


def test_corrupt_park_until_loads_without_raising_and_expires():
    """Corrupt park_until entries (string, null, missing key) load without
    raising and the park expires.

    FAIL-ON-REVERT: a raw ``float(val)`` without the try/except would raise on
    a non-numeric deadline; and if a present-but-corrupt deadline were not
    skipped (left out of ``_park_until``), the park would be treated as
    deadlined-and-fresh forever instead of expired."""
    import tempfile
    cases = [
        {"parked": ["p"], "park_until": {"p": "not-a-number"}, "park_strikes": {"p": 3}},
        {"parked": ["p"], "park_until": {"p": None}, "park_strikes": {"p": 3}},
        {"parked": ["p"], "park_until": {"other": 5.0}, "park_strikes": {"p": 3}},
        {"parked": ["p"], "park_until": "junk", "park_strikes": {"p": 3}},
    ]
    for payload in cases:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "balance_park.json").write_text(
                json.dumps(payload), encoding="utf-8")
            bt = BalanceTracker(state_dir=Path(d), park_clock=_Clock())
            assert bt.is_parked("p") is False, (
                "corrupt/missing park_until must never raise and must read as expired")


class _Srv:
    """Minimal stand-in for the gateway server object consumed by
    ``_has_viable_leg`` (it only reads ``balance_tracker``/``pools``/``routes``)."""

    def __init__(self, balance_tracker, pools, routes):
        self.balance_tracker = balance_tracker
        self.pools = pools
        self.routes = routes
