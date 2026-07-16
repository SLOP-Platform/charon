"""DEC-PLANNER — the LLM "splitting brain" of the Charon decomposer.

Turn ONE broad, cross-module ticket + the real change-surface facts into N
**single-domain, file-scoped** sub-tickets that weak/cheap executors can each win
(orchestrator-worker; WORK-DECOMPOSER accept). intake.py deliberately REFUSES to
invent units (ADR-0011 D1 input-as-data); this module is the greenfield brain that
does the inventing, then hands its output straight back through the *existing*
mechanical hard gate to be proven collision-free.

ARCHITECTURE (DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD): the planner is a DUMB CLIENT
of the switchboard. It does NOT enumerate providers, does NOT rank by tier, does
NOT HTTP-call a provider itself, and does NOT call ``recommend._find_trusted_models``.
It builds a ``PlannerNeed`` (capability + min context) and submits it through the
``SwitchboardClient`` seam — the same router/forwarder/cost_rank path the gateway
already runs — which returns the cheapest *capable and available* route and forwards
the prompt. The planner's own job is the parse/quality re-prompt loop (re-using
``failover_loop.invoke_with_failover``); provider-level failover lives in the
switchboard (the gateway's own chain-walking logic). This is the
[no-stiff-single-provider-tools] invariant applied to the decomposer.

Reuse (do NOT reinvent):
  * transport — the planner never HTTP-calls anything; ``SwitchboardClient`` is the
    ONLY seam through which a provider is reached. The default implementation loads
    routes via the same ``pools.load_pools`` + ``routing_policy`` machinery the
    gateway already uses, and POSTs over ``urllib`` (the switchboard's job, not the
    planner's).
  * disjointness — the emitted set is validated by ``intake.assert_disjoint_waves``
    (intake.py:691), the real ADR-0008 contract-#1 HARD gate. If it raises, the planner
    re-prompts the model with the violation as feedback; it never returns a plan the
    gate would reject. This module does not re-implement overlap/dependency logic.
  * schema — sub-tickets are emitted as ``intake.PlanUnit`` (intake.py:243), the same
    artifact that feeds ``land.load_units`` and ``engine.board.Unit``.

Trust seam: the planner does NOT trust any specific model — the switchboard picks
the cheapest capable available route. The plan-decomposition request is itself an
``ask`` injection (tests never touch the network; a custom ``SwitchboardClient`` is
the seam). When no injection is provided, ``DefaultSwitchboardClient`` runs.

Privileged-core rule: stdlib-only (mirrors the rest of ``src/charon``).
"""
from __future__ import annotations

import functools
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from . import decompose_sizing
from .failover_loop import (
    FAILOVER,
    OK,
    RETRY,
    AttemptResult,
    invoke_with_failover,
)
from .intake import IntakeError, PlanUnit, assert_disjoint_waves
from .ledger import validate_task_id
from .netutil import BROWSER_UA

DEFAULT_TIER = "high"
DEFAULT_MAX_REPROMPTS = 2

# Capability class the switchboard matches against the model registry. The planner
# is a "strong-model, JSON-emitting, large-context" consumer — distinct from the
# gateway's request-time ``work_class`` ("codegen", "review", etc.) and intentionally
# kept narrow so an operator can route planner traffic to its own pool if desired.
PLANNER_CAPABILITY = "planner"


class PlannerError(RuntimeError):
    """The planner could not produce a valid, collision-free split (bad/absent model
    reply, hallucinated paths, or a disjointness violation that survived re-prompting).
    Callers fall back to a human, exactly like the mechanical intake does."""


# Transport failure taxonomy (fix A). A candidate model can fail two very different
# ways and the failover loop must tell them apart:
#   * PROVIDER-level (auth/limit/infra) — the model never gave us a usable 200 reply.
#     A dead/mis-scoped key (401), an exhausted balance (402/429), or a flaky provider
#     (5xx/timeout) says NOTHING about the ticket; the right move is to try the NEXT
#     configured model. Signalled by raising ``PlannerTransportError``.
#   * PARSE/quality — the model returned a 200 but its body was not a parseable JSON
#     dict. That is a fault of THIS model's answer, so we re-prompt the SAME model
#     (up to ``max_reprompts``) before giving up on it. Signalled by returning ``None``.
# This is the exact distinction the old blanket ``except (...): return None`` collapsed,
# which made a 401 auth failure indistinguishable from an unparseable plan.
_AUTH_STATUSES = frozenset({401, 403, 407})
_LIMIT_STATUSES = frozenset({402, 429})


def _classify_status(code: int) -> str:
    """Map an HTTP status to a provider-level failure class."""
    if code in _AUTH_STATUSES:
        return "auth"
    if code in _LIMIT_STATUSES:
        return "limit"
    return "infra"  # 5xx and any other non-2xx transport-level status


class PlannerTransportError(RuntimeError):
    """A PROVIDER-level transport failure (auth / limit / infra) while invoking a planner
    candidate — distinct from a parse/quality failure of a 200 reply. Carries the failure
    class and HTTP status (when known) so the failover loop can attribute it and advance
    to the next candidate. Never leaks ``urllib`` types to callers (stdlib-only seam)."""

    def __init__(self, failure_class: str, status: int | None, detail: str) -> None:
        self.failure_class = failure_class  # "auth" | "limit" | "infra"
        self.status = status
        self.detail = detail
        super().__init__(detail)


# ----------------------------------------------------------------- input contracts
@dataclass
class BroadTicket:
    """The one broad ticket to split. ``product_acceptance`` is the whole-ticket
    done-condition preserved for the sub-tickets' context; it is NOT a sub-ticket's
    per-chunk fail-on-revert test (the model authors those)."""

    id: str
    goal: str
    body: str = ""
    product_acceptance: str = ""


@dataclass
class ChangeSurface:
    """The bounded change surface for the ticket — DEC-AST-WRAP's output
    (``semantic_proof`` import-graph blast radius). The planner treats ``files`` as the
    CLOSED universe a sub-ticket may own: any ``owns`` path outside it is a
    hallucination and is rejected. Passed in as facts; this module never computes it.

    ``symbols`` / ``notes`` are optional context hints for the prompt only."""

    files: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_facts(cls, facts: Mapping[str, object] | ChangeSurface) -> ChangeSurface:
        """Coerce a plain AST-facts dict (DEC-AST-WRAP's interface) into a ChangeSurface."""
        if isinstance(facts, ChangeSurface):
            return facts
        files = [str(f) for f in _as_list(facts.get("files"))]
        symbols = [str(s) for s in _as_list(facts.get("symbols"))]
        notes = str(facts.get("notes") or "")
        return cls(files=files, symbols=symbols, notes=notes)


def _as_list(v: object) -> list[object]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


# ------------------------------------------------------- DECOMPOSE-SIZING-OPTIMIZER
@dataclass(frozen=True)
class SizingGuidance:
    """Rendered ``decompose_sizing.SizingPlan`` guidance for the prompt: an
    ``instruction`` line REPLACING the old fixed "2-4 sub-tickets" text, and a
    ``grouping_block`` suggesting which files belong in the same sub-ticket."""

    instruction: str
    grouping_block: str


def _size_surface(
    surface: Mapping[str, object] | ChangeSurface, surf: ChangeSurface
) -> SizingGuidance | None:
    """Pre-LLM sizing pass (DECOMPOSE-SIZING-OPTIMIZER): recommend ``N*`` and a
    suggested file grouping for ``surf``. Returns ``None`` on ANY failure or when
    there is nothing useful to recommend (behavior-safe fallback to the
    original "2-4" prompt guidance) — this pass never blocks or breaks planning.
    """
    try:
        facts: Mapping[str, object] = (
            surface if isinstance(surface, Mapping) else {"files": list(surf.files)}
        )
        plan = decompose_sizing.size_decomposition(facts)
        if plan.n_star <= 0 or not plan.assignment:
            return None
        surfaces = decompose_sizing.atomic_surfaces(facts)
        files_by_surface = {s.id: s.files for s in surfaces}
        groups = [
            sorted({f for sid in ids for f in files_by_surface.get(sid, ())})
            for ids in plan.assignment.values()
        ]
        groups = [g for g in groups if g]
        if not groups:
            return None
        instruction = (
            f"Split ONE broad ticket into EXACTLY {plan.n_star} SINGLE-DOMAIN "
            f"sub-tickets (DECOMPOSE-SIZING-OPTIMIZER recommendation: est wall-clock "
            f"{plan.wallclock_parallel:.1f} vs {plan.wallclock_serial:.1f} serial)."
        )
        grouping_lines = "\n".join(
            f"- group {i + 1}: {', '.join(g)}" for i, g in enumerate(groups)
        )
        grouping_block = (
            "Suggested grouping — files listed together in ONE group are coupled "
            "and should land in the SAME sub-ticket (you may still refine this, but "
            "stay at EXACTLY the recommended sub-ticket count):\n" + grouping_lines
        )
        return SizingGuidance(instruction=instruction, grouping_block=grouping_block)
    except (KeyError, ValueError, TypeError, AttributeError, ZeroDivisionError):
        # Sizing is an advisory pre-pass, never a hard dependency of planning —
        # any failure (bad facts shape, estimator error, etc.) falls back to the
        # original fixed "2-4" guidance untouched.
        return None


# ----------------------------------------------------------------- switchboard seam
@dataclass(frozen=True)
class PlannerNeed:
    """The planner's NEED submitted to the switchboard. The switchboard (NOT the
    planner) decides which provider is cheapest-capable-available.

    ``capability`` is a coarse work-class the switchboard matches against its
    capability matrix; ``min_context`` is the required context window in tokens
    (the switchboard uses it as a max_context filter — see forwarder's R7); the
    rest is payload + dispatch metadata. The planner never sees a provider here."""

    capability: str
    min_context: int
    prompt: str
    model_hint: str | None = None  # operator override (e.g. CHARON_DECOMPOSE_PLANNER_MODEL)
    session: str | None = None


@dataclass(frozen=True)
class _PlannerRoute:
    """One switchboard-picked provider route — populated by the switchboard,
    consumed by the planner. The planner never *creates* these; it only passes
    them back to the switchboard's transport to actually deliver the prompt."""

    label: str               # human-readable, for failover attribution
    base_url: str
    api_key: str
    model_id: str
    wire: str = "openai"     # routing-side; preserved for the switchboard transport


class SwitchboardClient(Protocol):
    """The seam through which the planner reaches a model.

    A real implementation enumerates every configured provider, filters by
    capability + context, ranks cheapest-capable-available, and returns the
    ORDERED list. The planner wraps that list in ``invoke_with_failover`` for
    its own parse/quality re-prompt semantics — the switchboard returns the
    routes, the planner decides retry-vs-failover per attempt.

    Implementations MUST NOT assume the planner cares which provider answers;
    the planner treats every route identically and the switchboard is the
    single source of truth for "which model serves the planner's NEED"."""

    def plan_routes(self, need: PlannerNeed) -> list[_PlannerRoute]:
        """Return the ORDERED switchboard-ranked routes for ``need`` (cheapest
        capable available first). Empty list = no viable provider; the planner
        raises ``PlannerError`` and the operator gets a clean signal."""

    def deliver(self, route: _PlannerRoute, need: PlannerNeed) -> dict | None:
        """Deliver ``need.prompt`` to ``route`` and return the parsed JSON dict
        (or ``None`` on a 200-but-unparseable body — a parse/quality fault
        attributable to THIS model). Provider-level faults (auth/limit/infra)
        are raised as ``PlannerTransportError`` so the planner's
        ``invoke_with_failover`` advances to the next route."""


# ---------------------------------------------- default switchboard implementation
def _switchboard_routes(
    need: PlannerNeed, *, config_dir: str | Path | None
) -> list[_PlannerRoute]:
    """Build the switchboard-side route list: load the configured pool routes via
    the SAME ``pools.load_pools`` + ``routing_policy`` machinery the gateway uses,
    filter to planner-capable providers, drop Anthropic (SG-never-Anthropic is a
    planner-only invariant — the gateway's tier-voter is allowed Anthropic), and
    rank cheapest-capable-available. Returns the same routes the gateway's
    ``chain_for`` would emit for the planner's ``work_class``.

    Stdlib-only; mirrors ``routing_policy.build_routes_and_pools`` ordering
    (free-first, then cost-class priority, then cheapest-first)."""

    from . import secrets
    from .config._store import _load as _config_load
    from .routing_policy import build_routes_and_pools
    from .routing_policy.cost_rank import (
        cost_class_priority,
        derived_cost_rank,
    )

    secrets.apply_to_env()
    cd = Path(config_dir) if config_dir is not None else secrets.config_dir()
    from .config import load_models, load_providers

    registry = load_models(config_dir=cd)
    providers_cfg = load_providers(config_dir=cd)
    # pools.json is the gateway's source-of-truth for failover chains. config.load_pools
    # has no config_dir kwarg; reach the underlying file loader directly so the
    # switchboard's view is anchored to the SAME state dir the gateway reads from.
    pool_map = _config_load("pools.json", config_dir=cd) or {}
    # The planner's work_class — distinct from the gateway's task_class — is a
    # synthetic vid ("planner") that the operator can choose to populate in
    # pools.json. Absent → we fall back to a "planner" chain built from every
    # reasoning-capable model in the registry.
    if "planner" in pool_map and pool_map["planner"]:
        pool_map = {"planner": list(pool_map["planner"])}
    else:
        # No explicit planner pool — build one from every non-Anthropic
        # model in the registry. The capability filter happens below.
        pool_map = {"planner": [m for m in registry.keys()
                                 if isinstance(registry.get(m), dict)]}

    try:
        routes, pools, _backends = build_routes_and_pools(
            registry, pool_map, providers_cfg, metered_costs=None
        )
    except (KeyError, TypeError, ValueError):
        return []

    chain = pools.get("planner") or []
    out: list[_PlannerRoute] = []
    for r in chain:
        provider = (r.provider or "").lower()
        mid = (r.model_id or "").lower()
        # SG-never-Anthropic HARD RULE (PLANNER-ONLY): the planner/decomposer
        # must NEVER select a Claude/Anthropic model. The gateway's tier-voter
        # is allowed Anthropic; the planner is not.
        if "anthropic" in provider or "anthropic" in (r.upstream_base or "").lower():
            continue
        if mid.startswith("claude"):
            continue
        if not r.upstream_base or not r.api_key:
            continue
        out.append(_PlannerRoute(
            label=r.model_id or r.pool_id or provider or "<unnamed>",
            base_url=r.upstream_base,
            api_key=r.api_key,
            model_id=r.upstream_model or r.model_id or "",
            wire=r.wire or "openai",
        ))
    if not out:
        return []

    # Pinned model wins, then re-derive ordering from the registry's cost metadata
    # so a stale chain order is corrected at the planner-side (free-first,
    # cost-class priority, cheapest-first; matches the gateway exactly).
    pinned = need.model_hint
    if pinned:
        out = sorted(out, key=lambda rr: rr.model_id != pinned and rr.label != pinned)

    def _rank(rr: _PlannerRoute) -> tuple[int, int, int]:
        spec = registry.get(rr.label) or {}
        return (
            not bool(spec.get("free", False)),
            cost_class_priority(spec),
            derived_cost_rank(spec, metered_cost=None),
        )

    return sorted(out, key=_rank)


def _post_chat_openai(
    base_url: str, api_key: str, model_id: str, prompt: str, timeout: float = 60.0
) -> dict | None:
    """Default OpenAI-wire POST. The switchboard's transport — NOT the planner's.

    The planner never reaches this directly: it goes through
    ``DefaultSwitchboardClient.deliver``. This is the only ``urllib`` call in the
    planner module, and the FAIL-ON-REVERT test asserts it is reachable only via
    the switchboard client seam.

    Failure taxonomy (fix A — no longer a blanket ``None``):
      * PROVIDER-level fault (auth 401/403/407, limit 402/429, infra 5xx / URLError /
        timeout) → raise ``PlannerTransportError`` so the failover loop tries the NEXT
        candidate.
      * 200 but the body/content is not a parseable JSON dict → return ``None``
        (parse/quality fault of THIS model → re-prompt the SAME model)."""
    from . import recommend

    raw_base = base_url.rstrip("/")
    body = json.dumps(
        {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 4000,
        }
    ).encode()
    req = urllib.request.Request(
        raw_base + "/chat/completions", data=body, method="POST"
    )
    req.add_header("User-Agent", BROWSER_UA)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + api_key)
    opener = urllib.request.build_opener(recommend._NoRedirect())
    try:
        resp = opener.open(req, timeout=timeout)
        raw = resp.read(400_000)
    except urllib.error.HTTPError as e:
        # HTTPError is a URLError subclass — catch it first to read the status code.
        raise PlannerTransportError(
            _classify_status(e.code), e.code, f"HTTP {e.code} from {model_id}"
        ) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PlannerTransportError(
            "infra", None, f"transport error from {model_id}: {e}"
        ) from e

    try:
        data = json.loads(raw.decode("utf-8", "replace"))
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError, KeyError, IndexError, AttributeError):
        return None
    return parsed if isinstance(parsed, dict) else None


class DefaultSwitchboardClient:
    """The default ``SwitchboardClient`` — the planner's only window to a model.

    Composes:
      * ``_switchboard_routes`` — load the gateway's configured pool routes via
        the same ``routing_policy`` chain the data plane uses, then filter for
        planner-capable, non-Anthropic, available, cost-ranked. The switchboard
        (not the planner) picks the order.
      * ``_post_chat_openai`` — the switchboard's transport. The only ``urllib``
        call in this module, and the FAIL-ON-REVERT test confirms it is
        reachable only through ``deliver``.

    Tests inject a custom ``SwitchboardClient`` via ``plan_decomposition(switchboard=...)``;
    the planner code path NEVER instantiates one for itself. A self-built
    candidate list (the prior ``_ordered_planner_candidates``) is gone."""

    def __init__(self, *, config_dir: str | Path | None = None) -> None:
        self._config_dir = config_dir

    def plan_routes(self, need: PlannerNeed) -> list[_PlannerRoute]:
        return _switchboard_routes(need, config_dir=self._config_dir)

    def deliver(self, route: _PlannerRoute, need: PlannerNeed) -> dict | None:
        # The single urllib call site. Reachable only via the switchboard seam.
        return _post_chat_openai(
            route.base_url, route.api_key, route.model_id, need.prompt
        )


# ----------------------------------------------------------------- model-invoke seam
class ModelInvoker(Protocol):
    """A strong-model transport: prompt in, parsed-JSON dict out (or None on failure).
    Mirrors the invoke→parse-JSON contract of ``recommend._ask_model``.

    DEPRECATED for new call sites: the switchboard seam (``SwitchboardClient``)
    is the planner's transport. ``ModelInvoker`` is retained ONLY for the
    injected-``ask`` test path (``plan_decomposition(ask=...)``) so existing
    tests that mock a single fixed model still work — the planner wraps the
    injected ask in a one-candidate list and lets ``invoke_with_failover`` drive
    the parse/quality re-prompt loop."""

    def __call__(self, prompt: str) -> dict | None:
        ...


def _ask_to_switchboard(ask: ModelInvoker) -> SwitchboardClient:
    """Adapt an injected ``ModelInvoker`` to the ``SwitchboardClient`` seam so the
    planner code path is uniform: it always calls ``switchboard.plan_routes`` and
    ``switchboard.deliver``. The injected ask is a single "test" candidate that
    never HTTP-calls anything; the rest of the failover semantics ride on the
    standard ``invoke_with_failover`` wrapper."""
    sentinel = _PlannerRoute(
        label="<injected-ask>", base_url="", api_key="", model_id="<injected-ask>"
    )

    class _Injected(SwitchboardClient):
        def plan_routes(self_inner, need: PlannerNeed) -> list[_PlannerRoute]:  # noqa: N805
            return [sentinel]

        def deliver(self_inner, route: _PlannerRoute, need: PlannerNeed) -> dict | None:  # noqa: N805
            assert route is sentinel
            return ask(need.prompt)

    return _Injected()


# ----------------------------------------------------------------- the public API
def plan_decomposition(
    ticket: BroadTicket,
    surface: Mapping[str, object] | ChangeSurface,
    *,
    ask: ModelInvoker | None = None,
    is_detained: Callable[[str], bool] | None = None,
    config_dir: str | Path | None = None,
    switchboard: SwitchboardClient | None = None,
    max_reprompts: int = DEFAULT_MAX_REPROMPTS,
) -> list[PlanUnit]:
    """Split ``ticket`` into N single-domain, file-scoped sub-tickets.

    The planner is a DUMB CLIENT of the switchboard: it builds a ``PlannerNeed``
    and submits it through ``switchboard`` (the default ``DefaultSwitchboardClient``
    routes through the gateway's router/forwarder path — capability + cost-rank
    + cheapest-capable-available). The switchboard picks the model; the planner
    parses the reply, validates disjointness, and re-prompts on parse/quality
    faults via ``invoke_with_failover``.

    ``ask`` (legacy test seam) is adapted to a one-candidate ``SwitchboardClient``
    when no ``switchboard`` is injected. ``is_detained`` filters routes after
    the switchboard returns them — a planner-side concern (the gate that keeps
    a detained model out of every worker's hands) that is NOT a routing
    decision the switchboard should be making.

    Raises ``PlannerError`` if no valid, collision-free split is produced — the
    caller then falls back to a human (never a hallucinated or overlapping plan)."""
    surf = ChangeSurface.from_facts(surface)
    if not surf.files:
        raise PlannerError("empty change surface: nothing to decompose")

    sizing = _size_surface(surface, surf)

    if switchboard is None:
        switchboard = (
            _ask_to_switchboard(ask) if ask is not None
            else DefaultSwitchboardClient(config_dir=config_dir)
        )

    need = PlannerNeed(
        capability=PLANNER_CAPABILITY,
        min_context=0,
        prompt="",  # filled per-attempt (varies with feedback)
        model_hint=os.environ.get("CHARON_DECOMPOSE_PLANNER_MODEL"),
    )

    routes = switchboard.plan_routes(need)
    if is_detained is not None:
        routes = [r for r in routes
                  if not is_detained(r.model_id or r.label)]
    if not routes:
        raise PlannerError(
            "no capable+available provider is configured for planner work; "
            "the decomposer requires the switchboard to find one"
        )

    candidates: list[_Candidate] = [
        _Candidate(r.label, functools.partial(_deliver_via, switchboard, r))
        for r in routes
    ]

    def _attempt(cand: _Candidate, feedback: str) -> AttemptResult[list[PlanUnit]]:
        prompt = build_prompt(ticket, surf, feedback=feedback, sizing=sizing)
        return _attempt_candidate(cand.call, ticket, surf, sizing, feedback, prompt)

    return invoke_with_failover(
        candidates,
        _attempt,
        max_retries=max_reprompts,
        describe=lambda c: c.model_id,
        recommendation=(
            "switchboard pool exhausted — configure a chat-capable provider or set "
            "CHARON_DECOMPOSE_PLANNER_MODEL to a working model"
        ),
        error=PlannerError,
    )


def _deliver_via(switchboard: SwitchboardClient, route: _PlannerRoute,
                 prompt: str) -> dict | None:
    """Single-attempt delivery through the switchboard seam. The planner never
    calls this directly — it is always wrapped in a ``functools.partial`` bound
    to a specific route by ``plan_decomposition``."""
    return switchboard.deliver(
        route,
        PlannerNeed(
            capability=PLANNER_CAPABILITY,
            min_context=0,
            prompt=prompt,
            model_hint=os.environ.get("CHARON_DECOMPOSE_PLANNER_MODEL"),
        ),
    )


@dataclass
class _Candidate:
    """One planner candidate: a switchboard-attributed label and its per-prompt
    transport ``call`` (prompt → parsed dict, ``None`` on a 200-but-unparseable
    reply, raising ``PlannerTransportError`` on a provider-level
    auth/limit/infra fault)."""

    model_id: str
    call: Callable[[str], dict | None]


def _attempt_candidate(
    call: Callable[[str], dict | None],
    ticket: BroadTicket,
    surf: ChangeSurface,
    sizing: SizingGuidance | None,
    feedback: str,
    prompt: str,
) -> AttemptResult[list[PlanUnit]]:
    """One planner attempt against one candidate, classified for the failover loop:
    provider-level transport faults → ``FAILOVER`` (try the next model); a 200 whose body
    is unparseable, a hallucinated/invalid unit, or a disjointness violation → ``RETRY``
    (re-prompt the SAME model with the fault as feedback)."""
    try:
        raw = call(prompt)
    except PlannerTransportError as e:
        status = f" (HTTP {e.status})" if e.status is not None else ""
        return AttemptResult(kind=FAILOVER, attribution=f"{e.failure_class}{status}: {e.detail}")

    if not isinstance(raw, dict):
        fb = "model returned no parseable JSON object"
        return AttemptResult(kind=RETRY, feedback=fb, attribution="quality: unparseable 200 reply")
    try:
        units = _parse_units(raw, surf)
    except PlannerError as e:
        return AttemptResult(kind=RETRY, feedback=str(e), attribution=f"quality: {e}")
    try:
        # The existing ADR-0008 contract-#1 HARD gate — the only disjointness authority.
        # Reverting this call is what lets an overlapping split slip through (see
        # tests/test_decompose_planner.py fail-on-revert proof).
        assert_disjoint_waves(units)
    except IntakeError as e:
        fb = (
            f"The previous split was REJECTED by the disjoint-owns gate: {e}. "
            "Re-split so that any two sub-tickets that could run at the same time "
            "(neither depends on the other) own DISJOINT files."
        )
        return AttemptResult(kind=RETRY, feedback=fb, attribution=f"disjointness: {e}")
    return AttemptResult(kind=OK, value=units)


# ----------------------------------------------------------------- reply → PlanUnits
def _parse_units(raw: dict, surf: ChangeSurface) -> list[PlanUnit]:
    """Parse a model reply into ``PlanUnit``s with anti-hallucination guards:
    valid board ids, ≥1 owned path, ≥1 acceptance, and every owned path drawn from the
    closed change surface. Raises ``PlannerError`` (→ re-prompt) on any violation."""
    raw_units = raw.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise PlannerError("reply has no non-empty 'units' array")

    allowed = set(surf.files)
    units: list[PlanUnit] = []
    seen_ids: set[str] = set()
    for i, ru in enumerate(raw_units):
        if not isinstance(ru, dict):
            raise PlannerError(f"unit #{i} is not an object")

        uid = str(ru.get("id") or "").strip()
        try:
            validate_task_id(uid)
        except Exception as e:  # ledger raises ValueError for a bad id
            raise PlannerError(f"unit #{i} has an invalid id {uid!r}: {e}") from e
        if uid in seen_ids:
            raise PlannerError(f"duplicate unit id {uid!r}")
        seen_ids.add(uid)

        owns = [str(p).strip() for p in _as_list(ru.get("owns")) if str(p).strip()]
        if not owns:
            raise PlannerError(f"unit {uid!r} owns no files")
        outside = [p for p in owns if p not in allowed]
        if outside:
            raise PlannerError(
                f"unit {uid!r} owns files outside the change surface: {outside}"
            )

        accept = [str(a).strip() for a in _as_list(ru.get("accept")) if str(a).strip()]
        if not accept:
            raise PlannerError(
                f"unit {uid!r} has no fail-on-revert acceptance test description"
            )

        depends_on = [
            str(d).strip() for d in _as_list(ru.get("depends_on")) if str(d).strip()
        ]
        goal = str(ru.get("goal") or "").strip() or f"sub-ticket {uid}"
        tier = str(ru.get("tier") or DEFAULT_TIER).strip() or DEFAULT_TIER
        body = str(ru.get("body") or "").strip()

        units.append(
            PlanUnit(
                id=uid,
                goal=goal,
                accept=accept,
                body=body,
                tier=tier,
                owned_paths=owns,
                depends_on=depends_on,
            )
        )

    # depends_on must reference sibling units only (a dangling dep breaks board load).
    ids = {u.id for u in units}
    for u in units:
        dangling = [d for d in u.depends_on if d not in ids]
        if dangling:
            raise PlannerError(f"unit {u.id!r} depends on unknown units: {dangling}")
    return units


# ----------------------------------------------------------------- prompt (Spec-Kit)
def build_prompt(
    ticket: BroadTicket, surf: ChangeSurface, *, feedback: str = "",
    sizing: SizingGuidance | None = None,
) -> str:
    """Build the strong-planner prompt in the Spec-Kit ``tasks.md`` shape: each task is a
    single-domain, file-scoped sub-ticket with an id, disjoint ``owns``, dep-ordered
    ``depends_on``, and its own fail-on-revert test description.

    ``sizing`` (DECOMPOSE-SIZING-OPTIMIZER, when available) REPLACES the old hardcoded
    "2-4 sub-tickets" guidance with the optimizer's actual ``N*`` and a suggested file
    grouping; ``None`` (empty/unreadable surface, or the sizing pass raised) falls back
    to the original fixed "2-4" instruction, unchanged."""
    files_block = "\n".join(f"- {f}" for f in surf.files) or "- (none)"
    sym_block = ("\nRelevant symbols:\n" + "\n".join(f"- {s}" for s in surf.symbols)
                 if surf.symbols else "")
    notes_block = f"\nNotes: {surf.notes}\n" if surf.notes else ""
    pa_block = (f"\nWhole-ticket product acceptance (context, not a sub-test):\n"
                f"{ticket.product_acceptance}\n" if ticket.product_acceptance else "")
    fb_block = (f"\nCORRECTION FROM LAST ATTEMPT — you MUST fix this:\n{feedback}\n"
                if feedback else "")
    size_instruction = (
        sizing.instruction if sizing is not None
        else "Split ONE broad ticket into 2-4 SINGLE-DOMAIN sub-tickets so that a cheap "
        "model can win each one alone."
    )
    size_grouping_block = f"\n{sizing.grouping_block}\n" if sizing is not None else ""

    return (
        f"You are the PLANNER of a code-work decomposer. {size_instruction}\n\n"
        f"BROAD TICKET [{ticket.id}]: {ticket.goal}\n"
        f"{ticket.body}\n"
        f"{pa_block}"
        "\nCHANGE SURFACE — the CLOSED set of files this work may touch. Every sub-ticket "
        "MUST own only files from THIS list (never invent a path):\n"
        f"{files_block}"
        f"{sym_block}"
        f"{notes_block}"
        f"{size_grouping_block}"
        f"{fb_block}"
        "\nRULES (Spec-Kit tasks.md shape):\n"
        "- Each sub-ticket is ONE self-contained domain: one module, or one config edit.\n"
        "- 'owns' = the file(s) that sub-ticket edits. Any two sub-tickets that could run "
        "at the SAME time (neither in the other's 'depends_on') MUST own DISJOINT files.\n"
        "- Prefer ONE file per sub-ticket. Put integration/wire-in work in a LATER "
        "sub-ticket that 'depends_on' the units it wires together.\n"
        "- 'depends_on' lists sibling sub-ticket ids only, in dependency order.\n"
        "- 'accept' = a concrete FAIL-ON-REVERT test description: a test that PASSES with "
        "this chunk's change and FAILS if it is reverted.\n\n"
        "Reply with ONLY valid JSON, no prose:\n"
        '{"units": [\n'
        '  {"id": "kebab-id", "goal": "one line", "owns": ["path/from/surface.py"], '
        '"depends_on": [], "accept": ["fail-on-revert test description"], "tier": "high"}\n'
        "]}\n"
    )


# End of module — the planner's only window to a model is the SwitchboardClient seam.
