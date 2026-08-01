"""Grade-order overlay for the adopted ``litellm.Router``.

The OVERLAY half of the GATEWAY-GRADE-ORDER-MVP seam: takes the
per-``(model, work_class)`` grades the product store carries
(``charon.capability.product_grades``) and reorders the Router's
candidate set on the request hot path so a grade-``A`` deployment is
attempted BEFORE a grade-``F`` deployment even when ``F`` is cheaper.

This is the differentiator ADR-0017 (``docs/adr/0017-outcome-graded-gateway.md``)
names and which is currently INERT — ``CapabilityMatrix.get_grade``
(``routing_policy/matrix.py:81``) is called NOWHERE and the matrix is
built EMPTY at ``gateway.py:484``. The overlay makes that grade signal
live on the new commodity plane (GATEWAY-LITELLM-ADOPT
``litellm_plane/litellm_router.py``).

Architecture (why one file, not two):
  The product-grade STORE (``product_grades.py``) and this OVERLAY
  (``grade_order.py``) are deliberately ONE inseparable unit. Splitting
  them across tickets recreated the build-against-a-changing-API defect
  (an overlay built before the store it queries was throwaway — the
  ticket's ``ds`` section calls this out: \"overlay built before the
  store it queries\"). The two together own the novel ~30 % of the
  gateway MVP; the other ~70 % is the adopted ``litellm.Router`` plane
  the overlay wires into.

Wiring (where the overlay hooks in):
  ``litellm.Router`` exposes ``set_custom_routing_strategy(strategy)``
  which replaces its ``get_available_deployment`` /
  ``async_get_available_deployment`` methods wholesale — these are the
  methods ``Router.completion`` (and ``Router.acompletion``) call to pick
  a deployment on every request. The overlay implements both with the
  SAME reorder-by-grade logic so the sync and async paths agree.

  Replacement is wholesale because litellm's strategy dispatch lives
  INSIDE its default ``get_available_deployment`` (it checks the strategy
  name and either calls ``simple_shuffle`` or one of the built-in
  selectors). There is no narrower \"this is the deploy selector, do
  what you want with the candidate set\" hook — the closest is the
  pre-routing hook, but that mutates the request, not the candidate
  ordering. Replacing the method IS the documented integration point;
  we mirror the upstream pattern from
  ``litellm/router_strategy/lowest_cost.py`` etc.

  Cost: replacing the method means we re-implement the cooldown /
  health-check / blocked-deployment filtering ``Router.get_available_
  deployment`` performs. We do that filtering ourselves against the
  ``router.model_list`` (``_cooldown`` / ``cooldown_cache`` accessors)
  so the security controls the Router already enforces still fire on
  the overlay path — they are NOT bypassed by installing the overlay.
  See :meth:`GradeOrderStrategy._candidate_set` for the filter chain.

FAIL-OPEN contract:
  With NO grades file (or the canonical empty store), the overlay
  returns deployments in their ``model_list`` order — byte-identical
  to the Router's natural chain order. This is the gate-level
  \"byte-identical cold start\" requirement: a Router with the overlay
  installed and no grades file behaves EXACTLY as a Router with no
  overlay at all. A missing / empty / unparseable grades file is never
  allowed to strand the request — the overlay's contract is \"never
  introduce an unlisted id, never block on a missing grade\".

  When the grades file IS present, the overlay classifies the request's
  messages with the deterministic ``charon.capability.taxonomy`` (the
  SAME classifier the rest of the gateway uses — no second
  implementation, no per-request LLM) and looks up the grade per
  candidate deployment; it then sorts the candidate set best-first
  and returns the first. A ``(model, work_class)`` with no entry grades
  as ``\"unknown\"`` (the cold-start value) which sorts LAST — the
  overlay prefers a known grade (even a bad one) over no signal.

NEVER-INTRODUCE-UNLISTED-ID:
  The overlay may ONLY reorder ids already in the Router's candidate
  set; it may never introduce an unlisted model id. This is enforced
  by the filter chain in :meth:`_candidate_set` — we read the
  candidate set FROM the Router (``router.model_list`` filtered by
  ``model_name == model``) and sort THAT set. The overlay never
  builds a new candidate.

Stdlib-only (no litellm imports at module load — the overlay imports
litellm.types.router lazily so importing this module is independent of
litellm being installed; the ``set_custom_routing_strategy`` install
path requires litellm and is exercised by tests under ``pytest.importorskip("litellm")``).
"""
from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Local imports — kept stdlib-only by using TYPE_CHECKING for the litellm
# base class. The runtime side never imports litellm.types.router
# (the install path does, lazily, gated on litellm being installed).
if TYPE_CHECKING:
    pass

# The product-grade store is the data the overlay reads. The hot-path
# overlay reads a PRE-BUILT ``ProductGradeStore``; the loader is
# invoked once at Router build time via :func:`install_grade_overlay`
# so per-request lookups are O(1) dict reads.
from charon.capability.product_grades import (
    ENV_OVERRIDE,
    Grade,
    ProductGradeEntry,
    ProductGradeStore,
    WorkClass,
    load_cached,
)

# The classifier the overlay keys off. Deterministic, stdlib-only, hot-
# path-safe — the same one the rest of the gateway uses; importing it
# product-side module too (lives next to ``product_grades.py``).
from charon.capability.taxonomy import WorkClassTaxonomy

# The grade-rank used for ordering. Coarse A→F (best-first); ``unknown``
# sorts last so an absent grade never beats a known grade (even a bad
# one) — a known-bad is structurally different from a no-signal
# (an operator explicitly graded it bad vs an operator has not yet
# graded it).
_GRADE_RANK: dict[str, int] = {
    "A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "unknown": 5,
}


# ── exceptions ────────────────────────────────────────────────────────────


class GradeOverlayError(RuntimeError):
    """The overlay could not install or behave correctly on a Router."""


# ── the strategy ──────────────────────────────────────────────────────────


@dataclass
class GradeOrderStrategy:
    """The litellm.Router custom routing strategy that reorders by grade.

    Implements BOTH ``get_available_deployment`` (sync) and
    ``async_get_available_deployment`` with the same reorder-by-grade
    logic. ``Router.set_custom_routing_strategy`` registers this object
    by reading its two methods and setting them as instance attributes
    on the Router; the strategy must therefore carry the Router
    reference (it is not bound to the Router like a normal method).

    The overlay NEVER introduces an unlisted model id — it reads the
    candidate set from ``router.model_list`` and reorders IT. It also
    honours the Router's cooldown / blocked-deployment / health-check
    state (it filters the candidate set by these signals so the
    overlay cannot select a deployment the Router would have cooled).

    When the grade store is the canonical empty store
    (``store is ProductGradeStore.empty()``), the overlay returns the
    candidate set in ``model_list`` order — byte-identical to the
    Router's natural chain order. This is the FAIL-OPEN cold-start
    behaviour and the gate-level \"byte-identical cold start\"
    requirement.
    """

    router: Any
    store: ProductGradeStore
    taxonomy: WorkClassTaxonomy

    # ── sync + async entry points (the only methods Router calls) ───────

    def get_available_deployment(
        self,
        model: str,
        messages: Any = None,
        input: Any = None,
        specific_deployment: bool = False,
        request_kwargs: Mapping[str, Any] | None = None,
    ) -> dict:
        """Sync routing decision — see class docstring.

        Returns a single deployment dict from ``router.model_list`` (the
        type litellm's ``Router._completion`` expects). Raises
        ``litellm.RouterRateLimitError`` when the filtered candidate set
        is empty — that is the error litellm raises when \"no healthy
        deployment\" is the verdict, so the overlay matches the
        default-strategy error contract exactly.
        """
        return self._pick(model, messages, request_kwargs)

    async def async_get_available_deployment(
        self,
        model: str,
        messages: Any = None,
        input: Any = None,
        specific_deployment: bool = False,
        request_kwargs: Mapping[str, Any] | None = None,
    ) -> dict:
        """Async routing decision — same logic as the sync path; the
        ``async`` form exists because litellm's ``acompletion`` calls
        this name specifically (see
        ``litellm.router.async_get_available_deployment``)."""
        return self._pick(model, messages, request_kwargs)

    # ── core reorder logic ──────────────────────────────────────────────

    def _pick(self, model: str, messages: Any, request_kwargs: Mapping[str, Any] | None) -> dict:
        """The shared reorder logic.

        Steps:
          1. Build the candidate set by reading ``router.model_list`` for
             ``model_name == model`` (the live Router state — never
             cached; the Router may have added deployments mid-run).
          2. Filter by the Router's cooldown / blocked / health signals
             (mirrors what the default ``get_available_deployment``
             would have done before reaching the strategy selector).
          3. If the grade store is the empty sentinel, return the
             filtered candidate set in ``model_list`` order (cold
             start — byte-identical to the natural Router ordering).
          4. Otherwise classify *messages* via the taxonomy, look up
             each candidate's grade, sort best-first (A → unknown)
             with confidence / model-id tiebreaks, return the first.

        Raises ``litellm.RouterRateLimitError`` when the filtered
        candidate set is empty — the same exception the default
        ``Router.get_available_deployment`` raises in that case.
        """
        candidates = self._candidate_set(model, request_kwargs)
        if not candidates:
            self._raise_no_deployment(model)

        # Cold-start: empty store → byte-identical to the Router's
        # natural chain order. This is the FAIL-OPEN gate; do NOT
        # branch on ``store.entries == ()`` (same thing, but the
        # shared-singleton identity check is cheaper and documents
        # the intent).
        if self.store is ProductGradeStore.empty():
            return candidates[0]

        work_class = self._classify(messages)
        ordered = self._reorder(candidates, work_class, model)
        return ordered[0]

    # ── candidate-set construction ──────────────────────────────────────

    def _candidate_set(self, model: str, request_kwargs: Mapping[str, Any] | None) -> list[dict]:
        """The healthy, non-blocked, non-cooldown candidates for *model*.

        Reads ``router.model_list`` and filters it by the SAME signals
        the default ``get_available_deployment`` filters by:

          * ``model_name == model`` (the model group the caller asked for)
          * NOT in the cooldown set (``router.cooldown_cache`` /
            ``_cooldown_deployments``)
          * NOT blocked (``_filter_blocked_deployments``)
          * NOT in the health-check-unhealthy set (best-effort — we
            mirror the default's call but tolerate missing attributes
            so tests that build a Router without health checks still
            work)

        The ``request_kwargs``-based filters (order, exclusion) are
        preserved where the Router exposes them on ``model_list``
        entries; we read them defensively so a missing kwarg never
        crashes the overlay.
        """
        router = self.router
        ml = getattr(router, "model_list", None) or []
        # model_name == model — litellm's per-model-group filter
        candidates = [d for d in ml if d.get("model_name") == model]

        # Cooldown / blocked / health-check filtering (mirrors the
        # default ``get_available_deployment`` pre-strategy logic).
        # We call the Router's own helpers where they exist so the
        # overlay inherits any future improvements in those filters
        # (e.g. the cooldown cache protocol).
        candidates = self._apply_cooldown(candidates)
        candidates = self._apply_blocked(candidates)
        candidates = self._apply_health(candidates)

        # Order-based filter: if the caller pinned ``_target_order``,
        # only deployments with that order survive. The default
        # strategy applies this filter via
        # ``litellm.utils._get_order_filtered_deployments`` — we read
        # the kwarg directly so the overlay stays free of litellm
        # internal imports on the hot path.
        target_order = (request_kwargs or {}).get("_target_order")
        if target_order is not None:
            candidates = [d for d in candidates
                          if (d.get("model_info") or {}).get("order") == target_order]

        # Weighted-failover exclusion: deployments the caller already
        # tried in this request (the Router stamps them on
        # ``request_kwargs['_excluded_deployment_ids']``). Mirror the
        # default's behaviour.
        excluded = set((request_kwargs or {}).get("_excluded_deployment_ids") or ())
        if excluded:
            candidates = [d for d in candidates
                          if (d.get("model_info") or {}).get("id") not in excluded]

        return candidates

    def _apply_cooldown(self, candidates: list[dict]) -> list[dict]:
        """Drop candidates the Router has in cooldown.

        Reads ``router.cooldown_cache.get_cooldown_ids`` if present
        (litellm exposes this for outside callers to introspect
        cooldown state); otherwise falls back to ``_cooldown_deployments``
        (the attribute the default ``get_available_deployment`` reads).
        The Router's cooldown logic is NOT bypassed by the overlay.
        """
        router = self.router
        cd_ids = self._cooldown_ids(router)
        if not cd_ids:
            return candidates
        return [d for d in candidates
                if (d.get("model_info") or {}).get("id") not in cd_ids]

    @staticmethod
    def _cooldown_ids(router: Any) -> set:
        """The set of ``model_info.id`` values the Router has cooled.

        Mirrors the default ``Router.get_available_deployment`` path
        exactly: it reads ``cooldown_cache.get_active_cooldowns`` with
        the Router's own ``get_model_ids()`` and the same
        ``parent_otel_span=None`` the sync default passes. This is the
        ONE cooldown read the overlay uses — it does NOT re-implement
        cooldown semantics, it asks the Router's cache for the current
        cooldown set.

        Returns an empty set when the Router has no cooldown tracking
        (``cooldown_cache`` absent — a Router built without cooldowns
        degenerates to \"all candidates\", matching its own default
        behaviour for such a Router). No attribute-name fallbacks: the
        ``get_active_cooldowns`` protocol is stable across the supported
        litellm range, and guessing at private attribute names is what
        makes a version-adapted filter silently no-op.
        """
        import logging
        logger = logging.getLogger(__name__)
        cache = getattr(router, "cooldown_cache", None)
        if cache is None:
            return set()
        getter = getattr(cache, "get_active_cooldowns", None)
        if not callable(getter):
            logger.warning(
                "grade_order: router.cooldown_cache has no get_active_cooldowns; "
                "cooldown filter is a no-op")
            return set()
        get_ids = getattr(router, "get_model_ids", None)
        model_ids = get_ids() if callable(get_ids) else None
        try:
            active = getter(model_ids=model_ids, parent_otel_span=None)
        except Exception:
            logger.exception(
                "grade_order: cooldown_cache.get_active_cooldowns raised; "
                "cooldown filter is a no-op")
            return set()
        if not active:
            return set()
        return {cid for cid, _ in active if isinstance(cid, str)}

    def _apply_blocked(self, candidates: list[dict]) -> list[dict]:
        """Drop ``model_info.blocked == True`` deployments.

        Mirrors the default ``get_available_deployment`` filter via
        the Router's own helper when present.
        """
        import logging
        logger = logging.getLogger(__name__)
        router = self.router
        helper = getattr(router, "_filter_blocked_deployments", None)
        if callable(helper):
            try:
                return list(helper(candidates))
            except Exception:
                logger.exception(
                    "grade_order: _filter_blocked_deployments raised; "
                    "falling back to inline model_info.blocked scan")
        return [d for d in candidates if not (d.get("model_info") or {}).get("blocked", False)]

    def _apply_health(self, candidates: list[dict]) -> list[dict]:
        """Drop health-check-unhealthy deployments when the Router tracks
        them. Mirrors the default's call defensively so a Router
        without health checks still works."""
        import logging
        logger = logging.getLogger(__name__)
        router = self.router
        helper = getattr(router, "_filter_health_check_unhealthy_deployments", None)
        if callable(helper):
            try:
                return list(helper(healthy_deployments=candidates, parent_otel_span=None))
            except Exception:
                logger.exception(
                    "grade_order: _filter_health_check_unhealthy_deployments raised; "
                    "falling back to no health filtering")
        return candidates

    # ── classification + ordering ───────────────────────────────────────

    def _classify(self, messages: Any) -> WorkClass:
        """The work-class for this request, from the existing
        deterministic classifier.

        Returns ``\"general\"`` (the safe default) when *messages* is
        empty, malformed, or the classifier's verdict is
        ``\"unknown\"``. NEVER blocks — an unclassifiable request still
        gets routed (the gateway's never-strand invariant).
        """
        # Pull the user-visible text out of the messages list — the
        # same projection the gateway uses (concatenate content fields).
        text = self._extract_text(messages)
        if not text:
            return "general"
        verdict = self.taxonomy.classify_request(text)
        return verdict.name()  # \"unknown\" if the classifier missed

    @staticmethod
    def _extract_text(messages: Any) -> str:
        """Concatenate user-visible content from the messages list.

        Tolerant of the openai/chat shape (``{\"role\": ..., \"content\": ...}``)
        and the bare string shape litellm sometimes passes for
        embeddings. NEVER raises; returns ``\"\"`` for unparseable
        shapes (the caller falls through to ``\"general\"``).
        """
        import logging
        logger = logging.getLogger(__name__)
        if isinstance(messages, str):
            return messages
        if not messages:
            return ""
        parts: list[str] = []
        try:
            for msg in messages:
                if isinstance(msg, str):
                    parts.append(msg)
                    continue
                if isinstance(msg, Mapping):
                    content = msg.get("content")
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        # multimodal: ``[{\"type\": \"text\", \"text\": ...}, ...]``
                        for chunk in content:
                            if isinstance(chunk, Mapping) and isinstance(chunk.get("text"), str):
                                parts.append(chunk["text"])
        except Exception:
            logger.exception(
                "grade_order: messages-list parse failed; returning partial text")
        return " ".join(parts)

    def _reorder(self, candidates: list[dict], work_class: WorkClass,
                 model: str) -> list[dict]:
        """Sort *candidates* best-first by grade on *work_class*.

        Tie-break order (best first):
          1. Lower grade rank (A < B < ... < unknown).
          2. Higher confidence (real > provisional at the same grade).
          3. The model-group's ``model_list`` order (stable sort) —
             the chain order is the cheap-default fallback the overlay
             inherits when grades tie.

        NEVER introduces an unlisted id — we only sort *candidates*,
        which were themselves built from ``router.model_list``.
        """
        # Stable sort key (preserves ``model_list`` order on ties).
        def _sort_key(d: dict) -> tuple[int, float, int]:
            mid = self._deployment_model_id(d)
            grade = self.store.grade_for(mid, work_class)
            conf = self.store.confidence_for(mid, work_class)
            return (_GRADE_RANK.get(grade, 5), -conf, 0)

        return sorted(candidates, key=_sort_key)

    @staticmethod
    def _deployment_model_id(deployment: dict) -> str:
        """The model id the product-grade store keys this deployment off.

        The grade store is keyed by the **upstream model id** — the
        ``litellm_params.model`` value with any provider-prefix stripped
        (e.g. ``\"openai/gpt-5\"`` → ``\"gpt-5\"``). That is the id the
        operator grades (the matrix / seed-prior convention
        ``grades_import.py:132-180`` uses — entries name upstream model
        ids like ``\"gpt-5\"``, ``\"claude-opus-4.5\"``, ``\"kimi-k2.6\"``).

        Why upstream and not ``model_name`` (the agent-facing alias)?
        Two deployments under one ``model_name`` represent one
        agent-facing model with different providers; the operator grades
        the QUALITY of the upstream model, not the alias. When an agent
        requests ``model=\"m\"`` and the Router's candidate set has
        ``openai/gpt-3.5-turbo`` (cheap, graded F) and ``openai/gpt-4``
        (2nd-cheapest, graded A) under ``model_name=\"m\"``, the
        overlay must look up ``\"gpt-3.5-turbo\"`` and ``\"gpt-4\"`` in
        the store to differentiate them — using ``model_name=\"m\"``
        for both would collapse the candidate set to one key and the
        overlay could not reorder.

        Returns ``\"\"`` when neither field is present; an empty key
        grades as ``\"unknown\"`` which sorts last (the deliberate
        no-signal fallback — a deployment the operator has not graded
        is NEVER preferred over a known grade).
        """
        params = deployment.get("litellm_params") or {}
        upstream = params.get("model") or ""
        if "/" in upstream:
            upstream = upstream.split("/", 1)[1]
        # Fall back to ``model_name`` if the deployment lacks a
        # ``litellm_params.model`` (a degenerate / direct entry). The
        # agent-facing name is a usable grading key for those cases
        # — better than the empty string which sorts last.
        if not upstream:
            name = deployment.get("model_name")
            return str(name) if name else ""
        return str(upstream)

    # ── error mapping ──────────────────────────────────────────────────

    @staticmethod
    def _raise_no_deployment(model: str) -> None:
        """Raise the same error the default ``get_available_deployment``
        raises when no healthy deployment survives.

        The error is imported lazily (litellm may be absent when this
        module is imported) so importing the module stays clean.
        """
        import logging
        logger = logging.getLogger(__name__)
        try:
            from litellm import RouterRateLimitError
        except Exception as exc:  # pragma: no cover - litellm guaranteed in install path
            logger.exception(
                "grade_order: litellm.RouterRateLimitError unavailable")
            raise GradeOverlayError(
                "no healthy deployment for model="
                f"{model!r} (litellm unavailable)") from exc
        raise RouterRateLimitError(
            model=model,
            cooldown_time=0.0,
            enable_pre_call_checks=False,
            cooldown_list=[],
        )


# ── install / cache (the canonical Router-side entry point) ──────────────


@dataclass
class InstalledOverlay:
    """The handle returned by :func:`install_grade_overlay`.

    The overlay is a SINGLETON on the Router (one strategy per Router
    instance — re-installing overwrites the previous one), but a
    distinct handle is returned each call so callers can introspect
    what was installed without re-reading the Router.
    """

    strategy: GradeOrderStrategy
    """The strategy object now bound to the Router."""

    store: ProductGradeStore
    """The grade store the strategy was wired with (the same instance
    every call sees — the cache key is the resolved path)."""

    taxonomy: WorkClassTaxonomy
    """The taxonomy the strategy classifies against."""


# A registry of "Router id → installed strategy" so a re-install of the
# SAME Router (e.g. from a test that runs the install twice on the
# same fixture) does not stack strategies. Keyed on ``id(router)``
# (Router is not hashable, but ``id()`` is unique-enough for tests).
_router_overlays: dict[int, InstalledOverlay] = {}


def install_grade_overlay(
    router: Any,
    *,
    store: ProductGradeStore | None = None,
    taxonomy: WorkClassTaxonomy | None = None,
    path: Path | str | None = None,
    home: Path | str | None = None,
) -> InstalledOverlay:
    """Wire the grade-order overlay onto *router*.

    Default behaviour (no kwargs): read the grades from
    :func:`charon.capability.product_grades.resolve_default_path` (env
    var → *home* → cwd), memoised. With *store* passed explicitly, the
    overlay uses that store as-is — useful for tests.

    Returns the :class:`InstalledOverlay` handle. The caller can inspect
    ``handle.strategy`` / ``handle.store`` for assertions.

    Notes:
      * litellm is imported lazily via ``router.set_custom_routing_strategy``
        so this module imports cleanly when litellm is absent; the
        install call ITSELF requires litellm (the Router is a litellm
        object).
      * Idempotent on the same Router: a second call replaces the
        strategy but returns a fresh :class:`InstalledOverlay` handle.
    """
    if store is None:
        if path is None and home is None and not os.environ.get(ENV_OVERRIDE):
            # Use the default resolver so the env-var /
            # home / cwd precedence is honoured. ``load_cached`` returns
            # the shared EMPTY sentinel when the file is absent.
            store = load_cached(home=home)
        else:
            store = load_cached(path=path, home=home)
    if taxonomy is None:
        taxonomy = WorkClassTaxonomy()  # default seed classes
    strategy = GradeOrderStrategy(router=router, store=store, taxonomy=taxonomy)
    # ``set_custom_routing_strategy`` is a Router method that replaces
    # both ``get_available_deployment`` and ``async_get_available_deployment``
    # with the methods on ``strategy``. Importing it lazily here so
    # the module-level import graph stays free of litellm (the
    # overlay module is usable in tests that build a fake router
    # without the library present).
    set_custom = getattr(router, "set_custom_routing_strategy", None)
    if not callable(set_custom):
        raise GradeOverlayError(
            "router does not expose set_custom_routing_strategy — is it a litellm.Router?")
    set_custom(strategy)
    handle = InstalledOverlay(strategy=strategy, store=store, taxonomy=taxonomy)
    _router_overlays[id(router)] = handle
    return handle


def uninstall_grade_overlay(router: Any) -> None:
    """Restore the Router's default ``get_available_deployment``.

    Useful for the FAIL-ON-REVERT tests (asserting the order reverts
    to chain order when the overlay is removed). Not used on the live
    money path — the overlay is permanent once installed.
    """
    _router_overlays.pop(id(router), None)
    reset = getattr(router, "_reset_custom_routing_strategy", None)
    if callable(reset):
        reset()
        return
    # Manual reset fallback (older litellm versions without the helper).
    # Re-set the strategy to a no-op that returns the chain-order first
    # candidate — equivalent to \"the overlay is gone, route on natural
    # order\" for the FAIL-ON-REVERT test.
    ml = getattr(router, "model_list", None) or []

    class _Passthrough:
        def get_available_deployment(self, model: str, **_: Any) -> dict:
            for d in ml:
                if d.get("model_name") == model:
                    return d
            return ml[0] if ml else {}

        async def async_get_available_deployment(self, model: str, **_: Any) -> dict:
            return self.get_available_deployment(model)

    if callable(getattr(router, "set_custom_routing_strategy", None)):
        router.set_custom_routing_strategy(_Passthrough())


# ── helper: build a fixture store for tests / cold-start seeding ──────────


def store_with(
    entries: Iterable[tuple[str, WorkClass, Grade, float | None]] | None = None,
) -> ProductGradeStore:
    """Build an in-memory :class:`ProductGradeStore` from ``(model, wc, grade, confidence?)``
    tuples.

    Convenience for tests + the operator seeding CLI. Returns the
    EMPTY store when *entries* is ``None`` / empty (the cold-start
    no-signal value, FAIL-OPEN). NEVER returns a silently-empty
    constructed store — the ``ProductGradeStore`` constructor's
    empty-refuse guard routes empty input through :meth:`empty`
    so callers cannot accidentally produce a no-signal store they
    think is populated.
    """
    if not entries:
        return ProductGradeStore.empty()
    return ProductGradeStore(
        entries=tuple(
            ProductGradeEntry(
                model_id=mid, work_class=wc, grade=g,
                confidence=1.0 if conf is None else float(conf),
            )
            for (mid, wc, g, conf) in entries
        ),
    )


__all__ = [
    "GradeOverlayError",
    "GradeOrderStrategy",
    "InstalledOverlay",
    "install_grade_overlay",
    "uninstall_grade_overlay",
    "store_with",
]
