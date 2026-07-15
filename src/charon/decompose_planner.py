"""DEC-PLANNER — the LLM "splitting brain" of the Charon decomposer.

Turn ONE broad, cross-module ticket + the real change-surface facts into N
**single-domain, file-scoped** sub-tickets that weak/cheap executors can each win
(orchestrator-worker; WORK-DECOMPOSER accept). intake.py deliberately REFUSES to
invent units (ADR-0011 D1 input-as-data); this module is the greenfield brain that
does the inventing, then hands its output straight back through the *existing*
mechanical hard gate to be proven collision-free.

Reuse (do NOT reinvent):
  * transport — mirrors ``recommend._ask_model`` (recommend.py:65): a strong model is
    invoked over ``/chat/completions`` and its reply parsed as JSON, code-fence-stripped.
    Model selection reuses ``recommend._find_trusted_models`` and the ``_NoRedirect`` /
    ``BROWSER_UA`` helpers. (``_ask_model`` itself hardcodes a tier-ranking prompt, so it
    is not called verbatim — the planner supplies its own Spec-Kit-shaped prompt.)
  * disjointness — the emitted set is validated by ``intake.assert_disjoint_waves``
    (intake.py:691), the real ADR-0008 contract-#1 HARD gate. If it raises, the planner
    re-prompts the model with the violation as feedback; it never returns a plan the
    gate would reject. This module does not re-implement overlap/dependency logic.
  * schema — sub-tickets are emitted as ``intake.PlanUnit`` (intake.py:243), the same
    artifact that feeds ``land.load_units`` and ``engine.board.Unit``.

Trust seam: the planner must call a STRONG, NON-DETAINED model (WORK-DECOMPOSER ds-note,
ties to DETENTION-REDLINE). No detention module exists in-tree yet, so detention is an
injected ``is_detained`` predicate (default: none detained) — a clear seam to wire the
redline check to when it lands. The model-invoke is likewise an injectable ``ask`` seam
so tests never touch the network.

Privileged-core rule: stdlib-only (mirrors the rest of ``src/charon``).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from . import decompose_sizing
from .intake import IntakeError, PlanUnit, assert_disjoint_waves
from .ledger import validate_task_id
from .netutil import BROWSER_UA

DEFAULT_TIER = "high"
DEFAULT_MAX_REPROMPTS = 2


class PlannerError(RuntimeError):
    """The planner could not produce a valid, collision-free split (bad/absent model
    reply, hallucinated paths, or a disjointness violation that survived re-prompting).
    Callers fall back to a human, exactly like the mechanical intake does."""


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


# ----------------------------------------------------------------- model-invoke seam
class ModelInvoker(Protocol):
    """A strong-model transport: prompt in, parsed-JSON dict out (or None on failure).
    Mirrors the invoke→parse-JSON contract of ``recommend._ask_model``."""

    def __call__(self, prompt: str) -> dict | None:
        ...


# ----------------------------------------------------------------- the public API
def plan_decomposition(
    ticket: BroadTicket,
    surface: Mapping[str, object] | ChangeSurface,
    *,
    ask: ModelInvoker | None = None,
    is_detained: Callable[[str], bool] | None = None,
    config_dir: str | Path | None = None,
    max_reprompts: int = DEFAULT_MAX_REPROMPTS,
) -> list[PlanUnit]:
    """Split ``ticket`` into N single-domain, file-scoped sub-tickets.

    Invokes a strong (non-detained) model with a Spec-Kit ``tasks.md``-shaped prompt over
    the change ``surface``, parses the reply into ``PlanUnit``s, and VALIDATES the set
    through ``intake.assert_disjoint_waves``. On a disjointness violation (or a malformed
    reply, or a path outside the surface) the model is re-prompted with the failure as
    feedback, up to ``max_reprompts`` times. Returns the validated ``PlanUnit`` list.

    Raises ``PlannerError`` if no valid, collision-free split is produced — the caller
    then falls back to a human (never a hallucinated or overlapping plan).
    """
    surf = ChangeSurface.from_facts(surface)
    if not surf.files:
        raise PlannerError("empty change surface: nothing to decompose")

    invoke = ask or _default_invoker(config_dir=config_dir, is_detained=is_detained)
    sizing = _size_surface(surface, surf)

    feedback = ""
    last_error = "no attempts made"
    for _attempt in range(max_reprompts + 1):
        prompt = build_prompt(ticket, surf, feedback=feedback, sizing=sizing)
        raw = invoke(prompt)
        if not isinstance(raw, dict):
            last_error = "model returned no parseable JSON object"
            feedback = last_error
            continue
        try:
            units = _parse_units(raw, surf)
        except PlannerError as e:
            last_error = str(e)
            feedback = last_error
            continue
        try:
            # The existing ADR-0008 contract-#1 HARD gate — the only disjointness
            # authority. Reverting this call is what lets an overlapping split slip
            # through (see tests/test_decompose_planner.py fail-on-revert proof).
            assert_disjoint_waves(units)
        except IntakeError as e:
            last_error = str(e)
            feedback = (
                f"The previous split was REJECTED by the disjoint-owns gate: {e}. "
                "Re-split so that any two sub-tickets that could run at the same time "
                "(neither depends on the other) own DISJOINT files."
            )
            continue
        return units

    raise PlannerError(
        f"planner failed to produce a collision-free split after "
        f"{max_reprompts + 1} attempt(s): {last_error}"
    )


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


# ----------------------------------------------------------------- default transport
def _default_invoker(
    *,
    config_dir: str | Path | None,
    is_detained: Callable[[str], bool] | None,
) -> ModelInvoker:
    """A default ``ask`` built on the ``recommend._ask_model`` transport pattern:
    pick a strong, NON-DETAINED configured model (``recommend._find_trusted_models``) and
    POST the planner prompt to its ``/chat/completions``. Detention filtering is the seam
    for DETENTION-REDLINE. Raises ``PlannerError`` if no trusted, non-detained model is
    configured — the planner refuses to split with an untrusted/absent model."""
    selected = _select_planner_model(config_dir=config_dir, is_detained=is_detained)
    if selected is None:
        raise PlannerError(
            "no trusted, non-detained planner model is configured; "
            "the decomposer requires a strong model to split (WORK-DECOMPOSER)"
        )
    model_id, base_url, api_key = selected

    def _ask(prompt: str) -> dict | None:
        return _post_chat(model_id, base_url, api_key, prompt)

    return _ask


def _select_planner_model(
    *,
    config_dir: str | Path | None,
    is_detained: Callable[[str], bool] | None,
) -> tuple[str, str, str] | None:
    """First configured model with a working key that is NOT detained and NOT an
    Anthropic/Claude model. Reuses ``recommend._find_trusted_models`` for discovery.

    SG-never-Anthropic HARD RULE (PLANNER-ONLY): the planner/decomposer must NEVER
    select a Claude/Anthropic model. Skip any candidate whose base_url contains
    ``anthropic`` or whose model_id starts with ``claude``. This guard does NOT apply
    to the tier-voter path (``recommend.recommend_tiers``), where Anthropic is allowed."""
    from . import recommend
    from .config import tiers as tiers_cfg

    candidates: list[tuple[str, str, str]] = []
    for model_id, base_url, api_key in recommend._find_trusted_models(
        config_dir if config_dir is not None else recommend_default_config_dir()
    ):
        if is_detained is not None and is_detained(model_id):
            continue
        if "anthropic" in base_url.lower() or model_id.lower().startswith("claude"):
            continue
        candidates.append((model_id, base_url, api_key))
    if not candidates:
        return None

    pinned = os.environ.get("CHARON_DECOMPOSE_PLANNER_MODEL")
    if pinned:
        for m, b, k in candidates:
            if m == pinned:
                return m, b, k

    high_ids = set(tiers_cfg.tier_members("high"))
    for m, b, k in candidates:
        if m in high_ids:
            return m, b, k

    return candidates[0]


def recommend_default_config_dir() -> str | Path:
    from . import secrets

    return secrets.config_dir()


def _post_chat(
    model_id: str, base_url: str, api_key: str, prompt: str, timeout: float = 60.0
) -> dict | None:
    """POST ``prompt`` to ``base_url``'s ``/chat/completions`` and parse the reply as JSON.
    Transport copied from ``recommend._ask_model`` (recommend.py:65): browser UA, no-redirect
    opener, code-fence-stripped JSON parse. Returns the parsed dict, or None on any failure."""
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
    try:
        req = urllib.request.Request(
            raw_base + "/chat/completions", data=body, method="POST"
        )
        req.add_header("User-Agent", BROWSER_UA)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + api_key)
        opener = urllib.request.build_opener(recommend._NoRedirect())
        resp = opener.open(req, timeout=timeout)
        raw = resp.read(400_000)
        data = json.loads(raw.decode("utf-8", "replace"))
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
    ):
        return None
