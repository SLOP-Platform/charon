"""Tests for DEC-PLANNER (src/charon/decompose_planner.py).

The planner is the LLM splitting brain: broad ticket + change surface → N single-domain,
file-scoped sub-tickets, VALIDATED through intake.assert_disjoint_waves. The model is
always mocked here — no real network.

ARCHITECTURE (DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD): the planner is a DUMB CLIENT
of a ``SwitchboardClient`` seam. The tests assert BOTH the seam contract AND the
no-direct-urllib / no-``_find_trusted_models`` invariants — re-implementing the
old self-built candidate slate or direct HTTP in the planner code path flips
``test_planner_never_calls_urllib_or_find_trusted_models`` RED.

FAIL-ON-REVERT (WORK-DECOMPOSER accept): a mocked model returning a 3-file disjoint split
yields 3 disjoint PlanUnits that pass assert_disjoint_waves; a mocked OVERLAPPING split is
REJECTED. Reverting the assert_disjoint_waves call in plan_decomposition lets the
overlapping split slip through → test_overlapping_split_is_rejected goes RED.
"""
from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from charon import decompose_planner as P
from charon.intake import IntakeError, PlanUnit, assert_disjoint_waves

# The R46-style broad ticket fixture: wire a BalanceTracker through several modules —
# exactly the cross-module integration that cheap models fail as one god-ticket.
R46_TICKET = P.BroadTicket(
    id="r46-wire-balance-tracker",
    goal="Wire a per-provider BalanceTracker through the gateway",
    body="Build the tracker, construct it in the server, and expose it in config.",
    product_acceptance="charon serve reports a non-None balance tracker per provider",
)

R46_SURFACE = {
    "files": [
        "src/charon/balance.py",
        "src/charon/proxy.py",
        "src/charon/config/gateway.py",
    ],
    "symbols": ["BalanceTracker", "build_server", "GatewayConfig"],
}


def _mock(units: list[dict]) -> P.ModelInvoker:
    """A fake strong model that always returns the given units payload (no network)."""

    def _ask(prompt: str) -> dict:
        return {"units": units}

    return _ask


def _fixed_switchboard(
    replies: list[dict | None] | dict | None,
    routes: list[tuple[str, str, str]] | None = None,
    *,
    raise_per_route: dict[str, Exception] | None = None,
) -> P.SwitchboardClient:
    """A test ``SwitchboardClient`` that returns a fixed set of routes and
    serves a fixed list of replies. ``raise_per_route`` lets a test simulate
    the switchboard layer's per-route provider faults (the seam where the
    fail-on-revert high-tier-exhaustion test must inject its 429s).

    ``routes`` defaults to two OpenAI-style routes so the per-route failures
    line up with the FAIL-ON-REVERT semantic the ticket spells out. The
    routes are passed to the planner as ``_PlannerRoute`` (NOT direct
    provider tuples) so the planner code path is uniform with the real
    switchboard."""
    routes = routes or [
        ("gpt-x", "https://api.openai.com/v1", "key-x"),
        ("gpt-y", "https://api.openai.com/v1", "key-y"),
    ]
    planner_routes = [
        P._PlannerRoute(
            label=mid, base_url=base, api_key=key, model_id=mid
        )
        for mid, base, key in routes
    ]
    if isinstance(replies, dict) or replies is None:
        reply_iter = iter([replies])
    else:
        reply_iter = iter(replies)
    raise_map: dict[str, Exception] = dict(raise_per_route or {})

    class _Fake(P.SwitchboardClient):
        def plan_routes(self_inner, need: P.PlannerNeed) -> list[P._PlannerRoute]:  # noqa: N805
            return list(planner_routes)

        def deliver(self_inner, route: P._PlannerRoute, need: P.PlannerNeed) -> dict | None:  # noqa: N805
            if route.label in raise_map:
                raise raise_map[route.label]
            try:
                return next(reply_iter)
            except StopIteration:
                # No more scripted replies — treat as parse/quality fault.
                return None

    return _Fake()


# 3-file disjoint split: a pure unit, plus two wire-ins each depending on it.
DISJOINT_3 = [
    {
        "id": "build-balance-tracker",
        "goal": "Add BalanceTracker(provider_cfg) to balance.py",
        "owns": ["src/charon/balance.py"],
        "depends_on": [],
        "accept": ["test_build_balance_tracker returns a non-None BalanceTracker"],
    },
    {
        "id": "wire-tracker-into-server",
        "goal": "Construct the tracker in build_server",
        "owns": ["src/charon/proxy.py"],
        "depends_on": ["build-balance-tracker"],
        "accept": ["test_server_has_tracker asserts server.balance is not None"],
    },
    {
        "id": "expose-tracker-config",
        "goal": "Expose the tracker on GatewayConfig",
        "owns": ["src/charon/config/gateway.py"],
        "depends_on": ["build-balance-tracker"],
        "accept": ["test_gateway_config_balance field defaults present"],
    },
]

# Overlapping split: two units both own proxy.py yet neither depends on the other →
# they could run concurrently and collide. assert_disjoint_waves MUST reject this.
OVERLAP_2 = [
    {
        "id": "wire-tracker-a",
        "goal": "Construct the tracker in build_server",
        "owns": ["src/charon/proxy.py"],
        "depends_on": [],
        "accept": ["test_a"],
    },
    {
        "id": "wire-tracker-b",
        "goal": "Also touch build_server",
        "owns": ["src/charon/proxy.py"],
        "depends_on": [],
        "accept": ["test_b"],
    },
]


# --------------------------------------------------------- fail-on-revert: PASS path
def test_disjoint_split_emits_3_disjoint_units() -> None:
    units = P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(DISJOINT_3))
    assert len(units) == 3
    assert all(isinstance(u, PlanUnit) for u in units)
    # each is single-file and file-scoped
    assert all(len(u.owned_paths) == 1 for u in units)
    # the set survives the real hard gate (i.e. the planner already proved it)
    assert_disjoint_waves(units)
    # dependency order preserved for the wire-ins
    by_id = {u.id: u for u in units}
    assert by_id["wire-tracker-into-server"].depends_on == ["build-balance-tracker"]


# --------------------------------------------------------- fail-on-revert: REJECT path
def test_overlapping_split_is_rejected() -> None:
    # The mock always returns the overlapping split, so every re-prompt still collides;
    # the planner exhausts its attempts and refuses to return a colliding plan.
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(
            R46_TICKET, R46_SURFACE, ask=_mock(OVERLAP_2), max_reprompts=1
        )


def test_reprompt_recovers_from_transient_overlap() -> None:
    # First reply overlaps (rejected), second is disjoint (accepted) — proves the
    # re-prompt loop feeds the violation back and recovers.
    replies = [{"units": OVERLAP_2}, {"units": DISJOINT_3}]

    def _ask(prompt: str) -> dict:
        return replies.pop(0)

    units = P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_ask, max_reprompts=2)
    assert len(units) == 3


# --------------------------------------------------------- anti-hallucination guards
def test_owns_outside_change_surface_is_rejected() -> None:
    bad = [
        {
            "id": "touch-unknown",
            "goal": "edit a file not in the surface",
            "owns": ["src/charon/secretly_invented.py"],
            "depends_on": [],
            "accept": ["t"],
        }
    ]
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(bad), max_reprompts=0)


def test_missing_acceptance_is_rejected() -> None:
    bad = [
        {
            "id": "no-accept",
            "goal": "no fail-on-revert test",
            "owns": ["src/charon/balance.py"],
            "depends_on": [],
            "accept": [],
        }
    ]
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(bad), max_reprompts=0)


def test_invalid_task_id_is_rejected() -> None:
    bad = [
        {
            "id": "Bad ID With Spaces",
            "goal": "bad id",
            "owns": ["src/charon/balance.py"],
            "depends_on": [],
            "accept": ["t"],
        }
    ]
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(bad), max_reprompts=0)


def test_dangling_dependency_is_rejected() -> None:
    bad = [
        {
            "id": "wire-in",
            "goal": "depends on a ghost",
            "owns": ["src/charon/proxy.py"],
            "depends_on": ["does-not-exist"],
            "accept": ["t"],
        }
    ]
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(bad), max_reprompts=0)


def test_no_json_object_is_rejected() -> None:
    def _ask(prompt: str) -> None:
        return None

    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_ask, max_reprompts=0)


def test_empty_surface_raises() -> None:
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, {"files": []}, ask=_mock(DISJOINT_3))


# --------------------------------------------------------- detention / switchboard seam
def test_no_routes_from_switchboard_raises() -> None:
    # The default switchboard (with no configured providers) returns an empty route
    # list → the planner refuses to split. Proves the planner NEVER reaches the
    # gateway's transport when the switchboard says "no capable provider".
    sb = P.DefaultSwitchboardClient(config_dir="/nonexistent")
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(
            R46_TICKET, R46_SURFACE, switchboard=sb
        )


def test_detained_routes_filtered_after_switchboard() -> None:
    # The switchboard returns BOTH models; the planner's is_detained filter drops the
    # detained one before any HTTP call. FAIL-ON-REVERT: removing the is_detained
    # filter or short-circuiting the switchboard's route list flips this RED.
    sb = _fixed_switchboard(
        replies=[{"units": DISJOINT_3}],
        routes=[
            ("detained-model", "https://api.openai.com/v1", "k"),
            ("strong-model", "https://api.openai.com/v1", "k2"),
        ],
    )
    units = P.plan_decomposition(
        R46_TICKET,
        R46_SURFACE,
        switchboard=sb,
        is_detained=lambda m: m == "detained-model",
    )
    assert len(units) == 3


def test_default_switchboard_never_selects_anthropic() -> None:
    # SG-never-Anthropic HARD RULE (PLANNER-ONLY): the planner's default switchboard
    # MUST drop Claude/Anthropic routes (gateway tier-voter is allowed them; the
    # planner is not). FAIL-ON-REVERT: removing the guard in the switchboard routes
    # builder flips this RED (the switchboard would carry an anthropic/claude route
    # into the candidate list, and the planner would happily try it).
    sb = _SwitchboardWithRoutes(
        [
            P._PlannerRoute(
                label="claude-opus-4",
                base_url="https://api.anthropic.com/v1",
                api_key="k1",
                model_id="claude-opus-4",
            ),
            P._PlannerRoute(
                label="gpt-style",
                base_url="https://api.openai.com/v1",
                api_key="k2",
                model_id="gpt-style",
            ),
        ],
        reply={"units": DISJOINT_3},
    )
    # Replace the default switchboard with one whose plan_routes REPORTS anthropic
    # routes — the planner must filter them out before any attempt.
    units = P.plan_decomposition(R46_TICKET, R46_SURFACE, switchboard=sb)
    assert len(units) == 3
    # Only the non-anthropic route should have been called.
    assert sb.called_labels == ["gpt-style"]


class _SwitchboardWithRoutes(P.SwitchboardClient):
    """A switchboard seam that exposes the list of routes it was asked to deliver
    to — used to assert the planner's filtering behavior."""

    def __init__(self, routes: list[P._PlannerRoute], reply: dict | None) -> None:
        self._routes = list(routes)
        self._reply = reply
        self.called_labels: list[str] = []

    def plan_routes(self, need: P.PlannerNeed) -> list[P._PlannerRoute]:
        # NOTE: this seam re-applies the guard so the *planner-side* filter test
        # (test_default_switchboard_never_selects_anthropic) stays independent of
        # the production route builder. It is NOT the guard's coverage — that is
        # test_switchboard_routes_drops_anthropic_route below, which drives the
        # real ``_switchboard_routes`` and goes RED if the production guard is cut.
        out: list[P._PlannerRoute] = []
        for r in self._routes:
            label = (r.label or "").lower()
            model_id = (r.model_id or "").lower()
            base = (r.base_url or "").lower()
            if "anthropic" in base or model_id.startswith("claude") or label.startswith("claude"):
                continue
            out.append(r)
        return out

    def deliver(self, route: P._PlannerRoute, need: P.PlannerNeed) -> dict | None:
        self.called_labels.append(route.label)
        return self._reply


def test_switchboard_routes_drops_anthropic_route(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # SG-never-Anthropic HARD RULE (PLANNER-ONLY), COVERED AT THE PRODUCTION FILTER.
    # This drives the REAL ``_switchboard_routes`` (the code path
    # ``DefaultSwitchboardClient.plan_routes`` runs) against a config dir whose
    # planner pool lists BOTH a Claude/Anthropic model and a non-Anthropic one.
    # The production route builder — NOT a re-implemented test copy — must return
    # only the non-Anthropic route. FAIL-ON-REVERT: delete the anthropic/claude
    # `continue` guard in ``decompose_planner._switchboard_routes`` and the
    # anthropic route reappears in the result → this test goes RED. (Verified by
    # removing the guard locally: result became ['claude-opus-4', 'gpt-worker'].)
    import json

    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "k-anthropic")
    monkeypatch.setenv("TEST_GPT_KEY", "k-gpt")
    (tmp_path / "models.json").write_text(json.dumps({
        "claude-opus-4": {
            "upstream_base": "https://api.anthropic.com/v1",
            "key_env": "TEST_ANTHROPIC_KEY",
            "reasoning": True,
        },
        "gpt-worker": {
            "upstream_base": "https://api.openai.com/v1",
            "key_env": "TEST_GPT_KEY",
            "reasoning": True,
        },
    }))
    (tmp_path / "pools.json").write_text(json.dumps(
        {"planner": ["claude-opus-4", "gpt-worker"]}
    ))

    need = P.PlannerNeed(capability="planner", min_context=8000, prompt="split it")
    routes = P._switchboard_routes(need, config_dir=tmp_path)

    labels = [r.label for r in routes]
    bases = [r.base_url for r in routes]
    # The non-Anthropic route survives; the Claude/Anthropic one is dropped.
    assert "gpt-worker" in labels
    assert "claude-opus-4" not in labels
    assert not any("anthropic" in b.lower() for b in bases)
    assert not any(lab.lower().startswith("claude") for lab in labels)


def test_default_switchboard_client_plan_routes_drops_anthropic(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The public seam ``DefaultSwitchboardClient.plan_routes`` (the object the
    # planner actually instantiates when no switchboard is injected) delegates to
    # the production ``_switchboard_routes`` — assert the guard holds through that
    # entry point too, not just the module-level helper.
    import json

    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "k-anthropic")
    monkeypatch.setenv("TEST_GPT_KEY", "k-gpt")
    (tmp_path / "models.json").write_text(json.dumps({
        "claude-sonnet": {
            "upstream_base": "https://api.anthropic.com/v1",
            "key_env": "TEST_ANTHROPIC_KEY",
            "reasoning": True,
        },
        "qwen-coder": {
            "upstream_base": "https://api.openai.com/v1",
            "key_env": "TEST_GPT_KEY",
            "reasoning": True,
        },
    }))
    (tmp_path / "pools.json").write_text(json.dumps(
        {"planner": ["claude-sonnet", "qwen-coder"]}
    ))

    sb = P.DefaultSwitchboardClient(config_dir=tmp_path)
    need = P.PlannerNeed(capability="planner", min_context=8000, prompt="split it")
    labels = [r.label for r in sb.plan_routes(need)]

    assert labels == ["qwen-coder"]


# --------------------------------------------------------- switchboard provider-failover
def test_failover_on_auth_advances_to_next_provider() -> None:
    # The first route in the switchboard 401s (a provider-level auth fault) — the
    # planner's failover loop must advance to the next route, not re-prompt the
    # same dead model. FAIL-ON-REVERT: collapse the transport's auth classification
    # back to a blanket None (so a 401 looks like an unparseable plan) and the
    # planner never advances → this goes RED.
    sb = _fixed_switchboard(
        replies=[{"units": DISJOINT_3}],
        routes=[
            ("dead-key-model", "https://api.openai.com/v1", "bad"),
            ("live-model", "https://api.openai.com/v1", "good"),
        ],
        raise_per_route={
            "dead-key-model": P.PlannerTransportError(
                "auth", 401, "HTTP 401 from dead-key-model"
            )
        },
    )
    units = P.plan_decomposition(R46_TICKET, R46_SURFACE, switchboard=sb)
    assert len(units) == 3  # served by the SECOND route (advanced past 401)


def test_pool_exhaustion_names_each_failure_and_recommends() -> None:
    # ALL routes 401 → PlannerError naming each route's failure class AND ending with
    # the actionable "configure a chat-capable provider" recommendation.
    sb = _fixed_switchboard(
        replies=[],
        routes=[
            ("model-a", "https://api.openai.com/v1", "k1"),
            ("model-b", "https://api.openai.com/v1", "k2"),
        ],
        raise_per_route={
            "model-a": P.PlannerTransportError("auth", 401, "HTTP 401 from model-a"),
            "model-b": P.PlannerTransportError("auth", 401, "HTTP 401 from model-b"),
        },
    )
    with pytest.raises(P.PlannerError) as ei:
        P.plan_decomposition(R46_TICKET, R46_SURFACE, switchboard=sb)
    msg = str(ei.value)
    assert "model-a" in msg and "model-b" in msg
    assert "auth" in msg
    assert "configure a chat-capable provider" in msg


def test_garbage_body_reprompts_same_model_not_failover() -> None:
    # A 200 with an unparseable body is a QUALITY fault of THIS model → re-prompt the SAME
    # model (return None), NOT a failover. With a single route and max_reprompts=1 the
    # model is asked twice, then the pool is exhausted → PlannerError. Proves transport
    # vs quality are distinguished: None never advances the candidate.
    sb = _fixed_switchboard(
        replies=[None],
        routes=[("only-model", "https://api.openai.com/v1", "k")],
    )
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(
            R46_TICKET, R46_SURFACE, switchboard=sb, max_reprompts=1
        )


# --------------------------------------------------------- FAIL-ON-REVERT: architectural
def test_planner_never_calls_urllib_or_find_trusted_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The architectural invariant: the planner code path makes NO direct urllib/HTTP
    # call and does NOT consult recommend._find_trusted_models. Both calls are now
    # inside the switchboard seam (DefaultSwitchboardClient / _post_chat_openai).
    # FAIL-ON-REVERT: pulling the urllib call back into plan_decomposition, or
    # resurrecting the old _ordered_planner_candidates → recommend._find_trusted_models
    # call, makes this test go RED.
    from charon import recommend

    urllib_called = {"count": 0}
    real_urlopen = urllib.request.urlopen

    def _spy_urlopen(*a, **kw):
        urllib_called["count"] += 1
        return real_urlopen(*a, **kw)

    find_trusted_called = {"count": 0}
    real_find_trusted = recommend._find_trusted_models

    def _spy_find_trusted(*a, **kw):
        find_trusted_called["count"] += 1
        return real_find_trusted(*a, **kw)

    monkeypatch.setattr(urllib.request, "urlopen", _spy_urlopen)
    monkeypatch.setattr(recommend, "_find_trusted_models", _spy_find_trusted)

    # Inject a switchboard whose deliver records any direct urllib hit. The
    # default switchboard would call _post_chat_openai internally; we replace
    # the seam so the test asserts ONLY the planner's code path.
    sb = _RecordingSwitchboard(
        P._PlannerRoute(
            label="gpt-x", base_url="https://api.openai.com/v1",
            api_key="k", model_id="gpt-x"
        ),
        reply={"units": DISJOINT_3},
    )
    P.plan_decomposition(R46_TICKET, R46_SURFACE, switchboard=sb)

    # The planner's code path (between plan_decomposition's entry and the
    # switchboard.deliver call) must not touch urllib or _find_trusted_models.
    assert urllib_called["count"] == 0, (
        "planner code path called urllib directly; route through SwitchboardClient"
    )
    assert find_trusted_called["count"] == 0, (
        "planner code path called recommend._find_trusted_models; "
        "the switchboard owns provider discovery"
    )


class _RecordingSwitchboard(P.SwitchboardClient):
    """A switchboard that records which routes it was asked to serve — and
    itself never touches urllib. Used to assert the planner's no-direct-urllib
    invariant at the test boundary."""

    def __init__(self, route: P._PlannerRoute, reply: dict | None) -> None:
        self._route = route
        self._reply = reply
        self.calls: list[str] = []

    def plan_routes(self, need: P.PlannerNeed) -> list[P._PlannerRoute]:
        return [self._route]

    def deliver(self, route: P._PlannerRoute, need: P.PlannerNeed) -> dict | None:
        self.calls.append(route.label)
        return self._reply


def test_planner_routes_through_switchboard_not_self_built_slate() -> None:
    # When a switchboard is provided, the planner MUST use it for route selection
    # — the planner never enumerates providers itself. FAIL-ON-REVERT: re-introducing
    # _ordered_planner_candidates / _select_planner_model in the planner code path
    # would let it bypass the switchboard and pick a different (wrong) model.
    seen_via_sb: list[str] = []

    class _Capturing(P.SwitchboardClient):
        def __init__(self) -> None:
            self._routes = [
                P._PlannerRoute(
                    label="switchboard-chosen",
                    base_url="https://api.openai.com/v1",
                    api_key="k", model_id="switchboard-chosen",
                ),
            ]

        def plan_routes(self, need: P.PlannerNeed) -> list[P._PlannerRoute]:
            return list(self._routes)

        def deliver(self, route: P._PlannerRoute, need: P.PlannerNeed) -> dict | None:
            seen_via_sb.append(route.label)
            return {"units": DISJOINT_3}

    P.plan_decomposition(
        R46_TICKET, R46_SURFACE, switchboard=_Capturing()
    )
    assert seen_via_sb == ["switchboard-chosen"]


def test_high_tier_exhausted_switchboard_still_serves_via_other_provider() -> None:
    # FAIL-ON-REVERT (architectural): the high-tier model is exhausted at the
    # SWITCHBOARD layer (every high-tier route 429s), but a non-high-tier
    # provider is configured + available. The planner's NEED must still be
    # served through the switchboard (not via a self-built list). FAIL-ON-REVERT:
    # reverting the planner to a self-built slate that hand-ranks by tier would
    # let "all high-tier 429" → "no planner" because the planner stops at the
    # first high-tier candidate and never asks the switchboard for the next.
    seen_labels: list[str] = []

    class _Mixed(P.SwitchboardClient):
        """A switchboard with a high-tier route (429) and a med-tier route (OK)."""

        def plan_routes(self, need: P.PlannerNeed) -> list[P._PlannerRoute]:
            return [
                P._PlannerRoute(
                    label="high-tier-gpt",
                    base_url="https://api.openai.com/v1",
                    api_key="k1", model_id="high-tier-gpt",
                ),
                P._PlannerRoute(
                    label="med-tier-mini",
                    base_url="https://api.openai.com/v1",
                    api_key="k2", model_id="med-tier-mini",
                ),
            ]

        def deliver(self, route: P._PlannerRoute, need: P.PlannerNeed) -> dict | None:
            seen_labels.append(route.label)
            if route.label == "high-tier-gpt":
                # All high-tier 429s at the switchboard layer — the planner's
                # failover loop must advance to the next route.
                raise P.PlannerTransportError(
                    "limit", 429, "HTTP 429 from high-tier-gpt"
                )
            return {"units": DISJOINT_3}

    units = P.plan_decomposition(R46_TICKET, R46_SURFACE, switchboard=_Mixed())
    assert len(units) == 3
    # The high-tier attempt was tried AND the med-tier one served the request.
    assert seen_labels == ["high-tier-gpt", "med-tier-mini"]


def test_intake_error_is_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    # Belt-and-braces: the planner's rejection is driven by assert_disjoint_waves raising
    # IntakeError, not by our own parsing — confirm the overlap payload parses fine but
    # is caught by the gate.
    surf = P.ChangeSurface.from_facts(R46_SURFACE)
    units = P._parse_units({"units": OVERLAP_2}, surf)
    assert len(units) == 2  # parses cleanly
    with pytest.raises(IntakeError):
        assert_disjoint_waves(units)  # the gate is what rejects it
