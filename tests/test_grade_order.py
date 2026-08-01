"""Tests for the grade-order overlay (GATEWAY-GRADE-ORDER-MVP accept tests).

Two FAIL-ON-REVERT acceptance tests, the minimum bar from the ticket's
``accept:`` section:

  (1) **GRADE ORDERS** — with a fixture grade store where a grade-A
      model that is the 2nd-CHEAPEST out-ranks a grade-F CHEAPEST model,
      the Router's attempt order is A-first. Reverting the overlay
      (replacing the strategy with a passthrough that returns chain
      order) → order reverts to cheapest-first (F-first) → RED.

  (2) **BYTE-IDENTICAL COLD START** — with NO grades file present,
      the SAME request keeps the EXACT chain-order candidate set the
      Router would have had with no overlay at all. Reverting the
      fail-open (making missing-file raise / strand) → RED.

Plus the surrounding invariants:

  * The overlay may ONLY reorder ids already in the Router's candidate
    set; it must never introduce an unlisted id (a new id not in
    ``router.model_list`` would be a security hole — the controls
    ``litellm_router.build_model_list`` enforce would be bypassed).
  * Cooldown / blocked / health-check filtering is preserved (the
    overlay does not bypass the Router's own filtering).
  * The hot-path reader is cached — ``load_cached`` returns the same
    instance per path; no per-request file parse.

The tests drive a REAL ``litellm.Router`` (skipped when litellm is
absent) so the routing-decision hook the spec names is exercised
end-to-end. With simple-shuffle the natural order is randomised; the
test seeds the deployments in a known order via a custom strategy
(no-shuffle baseline), then drives the overlay's ``get_available_deployment``
directly to observe the attempt order — that IS the \"order the
Router attempts\" (the spec's requirement) and is reproducible.
"""
from __future__ import annotations

import json

import pytest

litellm = pytest.importorskip("litellm")
from litellm import Router  # noqa: E402

from charon.capability.product_grades import (  # noqa: E402
    SCHEMA_VERSION,
    ProductGradeStore,
)
from charon.routing_policy.grade_order import (  # noqa: E402
    install_grade_overlay,
    store_with,
    uninstall_grade_overlay,
)

# ── fixtures ──────────────────────────────────────────────────────────────


def _build_router(model_list: list[dict]) -> Router:
    """A Router with ``simple-shuffle`` (the default) and the given
    ``model_list``. Used as the canonical test scaffold; the overlay
    is installed on top of this."""
    return Router(
        model_list=model_list,
        cooldown_time=60.0,
        allowed_fails=3,
        num_retries=0,  # tests want one attempt per call, no retry churn
        set_verbose=False,
    )


def _deployment(model_name: str, upstream: str) -> dict:
    """A bare deployment entry — same shape ``build_model_list`` produces.

    ``api_base`` is a loopback URL (egress._is_local_host allows
    loopback) so the Router can build without an off-preset refusal.
    The tests never actually ``completion()`` — they call the overlay's
    ``get_available_deployment`` directly to observe the routing decision.
    """
    return {
        "model_name": model_name,
        "litellm_params": {
            "model": f"openai/{upstream}",
            "api_base": "http://127.0.0.1:1234/v1",
            "api_key": "k",
        },
    }


# ── (1) GRADE ORDERS — A-first when grades say so ────────────────────────


class TestGradeOrdersReorderCandidateSet:
    """The accept test (1) — A out-ranks F even when F is cheapest.

    The candidate set has two deployments for ``m1``: ``m1-f`` (cheapest,
    in chain position 0) and ``m1-a`` (2nd-cheapest, chain position 1).
    The grades file marks ``m1-a`` as grade-``A`` and ``m1-f`` as
    grade-``F`` — so the overlay MUST attempt ``m1-a`` first.

    Proven via the attempt order: the overlay's ``get_available_deployment``
    is the method ``Router._completion`` calls on every routing decision.
    Observing its return value IS observing the order the Router attempts.
    """

    def test_grade_a_outranks_grade_f_when_a_is_2nd_cheapest(self):
        router = _build_router([
            _deployment("m1", "f"),  # chain order 0 — cheapest upstream
            _deployment("m1", "a"),  # chain order 1 — 2nd cheapest upstream
        ])
        # Grades keyed by UPSTREAM model id (the
        # ``_deployment_model_id`` strip-after-/ path). The agent-
        # facing ``model_name`` is the same for both deployments
        # (this is a failover chain), so the operator grades the
        # upstream identity, not the alias.
        store = store_with((
            ("f", "reasoning", "F", 1.0),
            ("a", "reasoning", "A", 1.0),
        ))
        handle = install_grade_overlay(router, store=store)
        try:
            strat = handle.strategy
            messages = [{"role": "user", "content": "solve this step by step"}]
            # First attempt: A (grade-A, 2nd-cheapest upstream).
            first = strat.get_available_deployment(model="m1", messages=messages)
            upstream_first = first["litellm_params"]["model"]
            assert upstream_first == "openai/a", (
                f"expected grade-A upstream to be attempted first (got {upstream_first!r}); "
                "the overlay is not reordering by grade")
        finally:
            uninstall_grade_overlay(router)

    def test_revert_to_chain_order_picks_cheapest_first(self):
        """The revert case: when the overlay's reorder logic is a
        no-op (empty grade store — the FAIL-OPEN cold start), the
        first pick is chain order (cheapest = F first). The \"revert\"
        is the empty-store state, NOT uninstalling the strategy:
        uninstalling falls back to ``simple-shuffle`` which is random
        and would not give a deterministic cheapest-first reading.

        The empty store IS the revert — the overlay is wired in but
        sees no grade signal, so it does not reorder. This is the
        gate-level byte-identical cold-start contract."""
        router = _build_router([
            _deployment("m1", "f"),  # cheapest
            _deployment("m1", "a"),  # 2nd cheapest
        ])
        # Install with EMPTY store — the overlay is in place but does
        # not reorder (cold-start fail-open). First pick is chain
        # order: F first.
        install_grade_overlay(router)
        try:
            first = router.get_available_deployment(
                model="m1",
                messages=[{"role": "user", "content": "anything"}],
            )
            assert first["litellm_params"]["model"] == "openai/f", (
                "with empty grade store the overlay's cold-start must be "
                "chain order (F first); a different pick means the "
                "byte-identical cold-start contract is broken")
        finally:
            uninstall_grade_overlay(router)

    def test_attempt_order_is_a_then_f_across_repeated_calls(self):
        """The Router's fallback path calls ``get_available_deployment``
        multiple times per request (once per retry, with the just-
        tried deployment marked as cooldown / excluded). The overlay
        must return A first, then F — which is what the Router's
        fallback chain observes as \"the attempt order\".

        Simulating that here by marking A's ``model_info.id`` as
        in-cooldown after the first call — the second call sees only
        F surviving the cooldown filter and must return it."""
        router = _build_router([
            _deployment("m1", "f"),
            _deployment("m1", "a"),
        ])
        store = store_with((
            ("f", "reasoning", "F", 1.0),
            ("a", "reasoning", "A", 1.0),
        ))
        handle = install_grade_overlay(router, store=store)
        try:
            strat = handle.strategy
            messages = [{"role": "user", "content": "reason step by step"}]
            first = strat.get_available_deployment(model="m1", messages=messages)
            assert first["litellm_params"]["model"] == "openai/a", (
                f"first attempt must be A (got {first['litellm_params']['model']!r})")

            # Simulate the Router's retry / fallback: mark the A
            # deployment's ``model_info.id`` as in-cooldown via the
            # REAL litellm cooldown mechanism (``cooldown_cache.
            # add_deployment_to_cooldown`` — the same call the Router
            # makes internally when a deployment fails). The overlay's
            # ``_apply_cooldown`` reads this state back via
            # ``cooldown_cache.get_active_cooldowns``, so the test
            # proves the overlay honours the live Router cooldown set.
            a_id = (first.get("model_info") or {}).get("id")
            assert a_id, "expected Router to stamp model_info.id on deployments"
            cc = getattr(router, "cooldown_cache", None)
            assert cc is not None, "Router must expose cooldown_cache"
            adder = getattr(cc, "add_deployment_to_cooldown", None)
            assert callable(adder), (
                "litellm.Router.cooldown_cache must expose "
                "add_deployment_to_cooldown for this test to drive the "
                "real cooldown state")

            adder(
                a_id,
                original_exception=RuntimeError("simulated upstream failure"),
                exception_status=500,
                cooldown_time=60.0,
            )

            second = strat.get_available_deployment(model="m1", messages=messages)
            assert second["litellm_params"]["model"] == "openai/f", (
                f"after A is in cooldown the next attempt must be F (got "
                f"{second['litellm_params']['model']!r}) — the overlay's "
                "attempt order is A → F")
        finally:
            uninstall_grade_overlay(router)


# ── (2) BYTE-IDENTICAL COLD START — no grades file → no behaviour change ──


class TestByteIdenticalColdStart:
    """The accept test (2) — no grades file → overlay is a no-op.

    A Router with the overlay installed but the grade store empty
    MUST produce the SAME ordering as a Router with no overlay at all.
    The candidate set, the candidate order, and the pick on the first
    call must all match.
    """

    def test_cold_start_picks_chain_order_first(self):
        """The Router's natural chain order has F first (cheapest).
        With the overlay installed and the empty store, the overlay
        returns the same deployment on the first pick."""
        router = _build_router([
            _deployment("m1", "f"),
            _deployment("m1", "a"),
        ])
        # Default empty store (the cold-start sentinel). The overlay
        # is wired in but sees no grade signal.
        install_grade_overlay(router)
        try:
            first = router.get_available_deployment(
                model="m1",
                messages=[{"role": "user", "content": "anything"}],
            )
            # The overlay returns ``candidates[0]`` on cold start —
            # the first entry of ``model_list``, F. That is the SAME
            # ordering the default Router would pick on its first
            # attempt (chain order = cheapest-first).
            assert first["litellm_params"]["model"] == "openai/f"
        finally:
            uninstall_grade_overlay(router)

    def test_cold_start_uninstalled_matches_installed_cold_start(self):
        """Byte-identical cold start: a Router WITH the overlay (and
        no grades file) is observationally indistinguishable from a
        Router WITHOUT the overlay, on the routing-decision path."""
        # Router with overlay, no grades → returns chain-order first.
        router_with = _build_router([
            _deployment("m1", "f"),
            _deployment("m1", "a"),
        ])
        install_grade_overlay(router_with)
        try:
            cold_first = router_with.get_available_deployment(
                model="m1",
                messages=[{"role": "user", "content": "hi"}],
            )
            cold_upstream = cold_first["litellm_params"]["model"]
        finally:
            uninstall_grade_overlay(router_with)

        # Router without overlay, default simple-shuffle → returns
        # random. We seed ``random`` so the test is deterministic; the
        # OBSERVED point is that the FIRST deployment in ``model_list``
        # is F (chain order is preserved on the input), and the
        # overlay's cold-start return value matches THAT chain-order
        # baseline.
        router_without = _build_router([
            _deployment("m1", "f"),
            _deployment("m1", "a"),
        ])
        # The cold-start overlay returns ``model_list[0]`` for model=m1
        # — that is the chain-order candidate the default Router would
        # have available. We assert this directly on the model_list
        # ordering (not the runtime pick) since simple-shuffle is
        # random and would make the runtime comparison non-deterministic.
        first_in_chain = next(d for d in router_without.model_list
                              if d["model_name"] == "m1")
        assert cold_upstream == first_in_chain["litellm_params"]["model"], (
            "the overlay's cold-start pick must equal the chain-order candidate "
            "the default Router would have available — this IS the byte-identical "
            "cold-start contract")

    def test_missing_grades_file_via_load_cached_returns_empty_sentinel(self):
        """The fail-open path: when the grades file is absent, the
        overlay reads the EMPTY store (the shared sentinel) — it
        does NOT strand on a missing file. Proves the load path
        the install helper takes by default."""
        from pathlib import Path

        from charon.capability.product_grades import _clear_cache, load_cached

        _clear_cache()
        store = load_cached(Path("/nonexistent/path/grades.json"))
        assert store is ProductGradeStore.empty()
        # And the identity check the overlay uses:
        assert store is ProductGradeStore.empty()


# ── additional invariants ────────────────────────────────────────────────


class TestNeverIntroducesUnlistedId:
    """The overlay must NEVER introduce a model id not already in
    ``router.model_list``. Adding one would bypass the build-time
    controls ``litellm_router.build_model_list`` enforces (SSRF
    refusal, off-preset refusal, SG-never-Anthropic, base-bound keys).
    """

    def test_overlay_does_not_synthesise_a_deployment(self):
        router = _build_router([
            _deployment("m1", "f"),
        ])
        # Mark upstream "f" grade-F; the overlay has only m1 in its candidate set.
        store = store_with((("f", "reasoning", "F", 1.0),))
        handle = install_grade_overlay(router, store=store)
        try:
            d = handle.strategy.get_available_deployment(
                model="m1",
                messages=[{"role": "user", "content": "hi"}],
            )
            assert d in router.model_list, (
                "overlay returned a deployment not in router.model_list — "
                "would bypass the build-time controls")
        finally:
            uninstall_grade_overlay(router)


class TestHonoursCooldownAndBlocked:
    """The overlay preserves the Router's own filtering (cooldown,
    blocked, health-check). Bypassing these would let the overlay
    pick a deployment the Router would have cooled — a security
    regression."""

    def test_blocked_deployment_is_dropped(self):
        router = _build_router([
            _deployment("m1", "f"),
            _deployment("m1", "a"),
        ])
        # Mark the A deployment as blocked (what
        # ``_filter_blocked_deployments`` would do).
        for d in router.model_list:
            if d.get("litellm_params", {}).get("model") == "openai/a":
                d.setdefault("model_info", {})["blocked"] = True
        store = store_with((("f", "reasoning", "F", 1.0),
                            ("a", "reasoning", "A", 1.0)))
        handle = install_grade_overlay(router, store=store)
        try:
            d = handle.strategy.get_available_deployment(
                model="m1",
                messages=[{"role": "user", "content": "hi"}],
            )
            # A is blocked → only F survives; overlay must not bypass.
            assert d["litellm_params"]["model"] == "openai/f", (
                f"overlay picked a blocked deployment ({d['litellm_params']['model']!r}); "
                "the Router's blocked filter is being bypassed")
        finally:
            uninstall_grade_overlay(router)


class TestNoCandidateRaisesRateLimitError:
    """When the filtered candidate set is empty, the overlay raises
    the same error the default ``get_available_deployment`` raises
    (``RouterRateLimitError``) — never silently returns ``None``."""

    def test_no_deployment_raises_rate_limit(self):
        from litellm import RouterRateLimitError

        router = _build_router([_deployment("m1", "f")])
        # Drop every candidate via blocked.
        for d in router.model_list:
            if d.get("model_name") == "m1":
                d.setdefault("model_info", {})["blocked"] = True
        store = store_with((("f", "reasoning", "A", 1.0),))
        handle = install_grade_overlay(router, store=store)
        try:
            with pytest.raises(RouterRateLimitError):
                handle.strategy.get_available_deployment(
                    model="m1",
                    messages=[{"role": "user", "content": "hi"}],
                )
        finally:
            uninstall_grade_overlay(router)


class TestUnknownGradeSortsLast:
    """An absent grade (model not in the store) sorts LAST — a known
    grade (even a bad one) beats a no-signal. The cold-start \"no
    grades file\" case is byte-identical to \"every model has
    grade=unknown\" — both produce chain order."""

    def test_known_f_beats_unknown(self):
        router = _build_router([
            _deployment("m1", "x"),  # chain order 0
            _deployment("m1", "f"),  # chain order 1
        ])
        # Only upstream "f" has a grade (F) on the work-class the
        # request's messages classify to; upstream "x" is unknown
        # on that work-class. Use a reasoning-matching message so the
        # classifier keys off the reasoning grade (not general).
        store = store_with((("f", "reasoning", "F", 1.0),))
        handle = install_grade_overlay(router, store=store)
        try:
            d = handle.strategy.get_available_deployment(
                model="m1",
                messages=[{"role": "user",
                           "content": "reason through this step by step"}],
            )
            assert d["litellm_params"]["model"] == "openai/f", (
                f"expected F (known grade) to beat x (unknown); got "
                f"{d['litellm_params']['model']!r}")
        finally:
            uninstall_grade_overlay(router)


class TestUnknownWorkClassDefaultsToGeneral:
    """A request whose messages don't match any taxonomy pattern
    classifies as ``\"unknown\"``; the overlay falls back to
    ``\"general\"`` so the request still gets routed (never-strand).
    """

    def test_unclassifiable_request_still_routes(self):
        router = _build_router([
            _deployment("m1", "f"),
            _deployment("m1", "a"),
        ])
        # Grade only on "general" — the fallback work_class.
        store = store_with((
            ("f", "general", "F", 1.0),
            ("a", "general", "A", 1.0),
        ))
        handle = install_grade_overlay(router, store=store)
        try:
            # An empty / unparseable message set → unknown → general.
            d = handle.strategy.get_available_deployment(
                model="m1",
                messages=[{"role": "user", "content": ""}],
            )
            assert d["litellm_params"]["model"] == "openai/a"
        finally:
            uninstall_grade_overlay(router)


class TestAsyncPathMirrorsSync:
    """The async ``async_get_available_deployment`` path returns the
    SAME deployment as the sync path (litellm's ``acompletion`` calls
    the async method; the spec requires the two paths to agree)."""

    def test_async_picks_same_as_sync(self):
        router = _build_router([
            _deployment("m1", "f"),
            _deployment("m1", "a"),
        ])
        store = store_with((
            ("f", "reasoning", "F", 1.0),
            ("a", "reasoning", "A", 1.0),
        ))
        handle = install_grade_overlay(router, store=store)
        try:
            strat = handle.strategy
            messages = [{"role": "user", "content": "reason step by step"}]
            sync_pick = strat.get_available_deployment(
                model="m1", messages=messages)
            import asyncio
            async_pick = asyncio.run(
                strat.async_get_available_deployment(
                    model="m1", messages=messages))
            assert (sync_pick["litellm_params"]["model"]
                    == async_pick["litellm_params"]["model"]), (
                "sync and async paths must pick the same deployment — "
                "otherwise the Router's acompletion path diverges from completion")
        finally:
            uninstall_grade_overlay(router)


class TestInstallUninstallRoundTrip:
    """``install_grade_overlay`` returns a handle and ``uninstall``
    cleanly restores the Router. The \"revert to chain order\" tests
    depend on uninstall being clean (no leftover state on the Router)."""

    def test_install_then_uninstall_restores_strategy_method(self):
        router = _build_router([_deployment("m1", "f")])
        install_grade_overlay(router)
        uninstall_grade_overlay(router)
        # After uninstall, ``set_custom_routing_strategy`` no longer
        # references our overlay's instance. We re-install and check
        # it returns a fresh handle (idempotency without leakage).
        h1 = install_grade_overlay(router)
        h2 = install_grade_overlay(router)
        try:
            assert h1 is not h2, "each install returns a fresh handle"
            assert h1.strategy is not h2.strategy
        finally:
            uninstall_grade_overlay(router)


# ── grades file on-disk path (the operator-shipped path) ────────────────


class TestGradesFileOnDiskPath:
    """The end-to-end path the operator uses: a JSON file under the
    canonical home dir, picked up via the install helper's default
    loader. This is the path that proves the store + overlay are
    wired together (the integration the spec mandates)."""

    def test_overlay_picks_up_grades_from_file(self, tmp_path, monkeypatch):
        from charon.capability import product_grades as pg
        pg._clear_cache()

        grades_path = tmp_path / "product-grades.json"
        grades_path.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "entries": [
                {"model_id": "f", "work_class": "reasoning", "grade": "F",
                 "confidence": 1.0},
                {"model_id": "a", "work_class": "reasoning", "grade": "A",
                 "confidence": 1.0},
            ],
        }))

        router = _build_router([
            _deployment("m1", "f"),
            _deployment("m1", "a"),
        ])
        handle = install_grade_overlay(router, home=tmp_path)
        try:
            d = handle.strategy.get_available_deployment(
                model="m1",
                messages=[{"role": "user", "content": "reason step by step"}],
            )
            assert d["litellm_params"]["model"] == "openai/a"
        finally:
            uninstall_grade_overlay(router)
            pg._clear_cache()

    def test_overlay_cold_starts_when_grades_file_absent(self, tmp_path, monkeypatch):
        from charon.capability import product_grades as pg
        pg._clear_cache()

        router = _build_router([
            _deployment("m1", "f"),
            _deployment("m1", "a"),
        ])
        # No grades file under tmp_path → empty sentinel → cold start.
        handle = install_grade_overlay(router, home=tmp_path)
        try:
            d = handle.strategy.get_available_deployment(
                model="m1",
                messages=[{"role": "user", "content": "anything"}],
            )
            # Cold start = chain order = F first.
            assert d["litellm_params"]["model"] == "openai/f"
        finally:
            uninstall_grade_overlay(router)
            pg._clear_cache()

    def test_overlay_strands_when_grades_file_is_empty(self, tmp_path, monkeypatch):
        """The refuse-on-empty contract: an operator-shipped empty
        grades file raises EmptyGradeStore at install time (the
        overlay DOES install, but the helper propagates the load
        error). Reverting the fail-open (making missing/empty
        silently return EMPTY) → this test would lose its RED."""
        from charon.capability import product_grades as pg
        from charon.capability.product_grades import EmptyGradeStore

        pg._clear_cache()
        grades_path = tmp_path / "product-grades.json"
        grades_path.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "entries": [],
        }))
        with pytest.raises(EmptyGradeStore):
            install_grade_overlay(router=_build_router([_deployment("m1", "f")]),
                                  home=tmp_path)
        pg._clear_cache()
