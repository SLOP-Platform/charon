"""ADR-0008 Phase 1 — the human-reviewed intake → ticket-plan front door
(ADR-0011; ADR-0010 build-seq step 4).

The non-coder entry point. Induct **messy project input** (a markdown work-item
list) → analyze → emit a **rule-abiding ticket plan**: file-disjoint, tier-tagged,
collision-free waves, plus a **top-level product acceptance**. The output is a
*proposal a human approves/edits* — there is **no autonomous run** (that is Phase 2,
deferred behind ADR-0007 D10-C).

Safety posture (ADR-0011 D1): intake reads input as **data** and emits an artifact.
It NEVER runs an acceptance command, spawns a unit, or lands. Execution stays with
the existing fenced ``coordinator.run`` + ``land.py`` gate, downstream, after a human
approves — so there is no code path from input text to execution.

The failure contract (ADR-0008 §failure-contract) is enforced **mechanically**:
overlap → serialize (never parallel-share a path); unprovable independence →
conservatively serialize + flag; missing executable acceptance → propose-only
review item; vague input → "need more detail", never a hallucinated unit; fenced
code blocks are parsed as data (injection-safe).

The emitted plan is COMPATIBLE with both consumers from one artifact: every unit
carries ``owned_paths`` (for ``land.load_units``) and ``owns`` (for
``engine.board.Unit``). The privileged core stays stdlib-only.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from . import decompose, decompose_effort
from .decompose_surface import change_surface
from .land import in_scope
from .ledger import validate_task_id

if TYPE_CHECKING:
    # Type-only import — the runtime import lives inside ``_suggest_split`` to avoid a
    # cycle (``decompose_planner`` imports from ``intake``).
    from .decompose_planner import ModelInvoker

# Headings (outside code fences) whose normalized title names the whole-product
# acceptance section rather than a work item.
_ACCEPTANCE_TITLES = frozenset(
    {"product acceptance", "acceptance", "done means", "definition of done",
     "acceptance criteria", "product done"}
)

# Field labels recognized inside a work item's body. Values accumulate across
# repeated lines. ``accept`` is captured verbatim (never split mid-command).
_PATH_LABELS = frozenset({"files", "file", "paths", "path", "owns", "owned_paths"})
_ACCEPT_LABELS = frozenset({"accept", "acceptance", "test", "tests", "check", "checks"})
_TIER_LABELS = frozenset({"tier"})
_DEP_LABELS = frozenset({"depends", "depends_on", "deps", "on", "after"})
_MERGE_LABELS = frozenset({"merge_after", "merge-order"})
# The source ticket's OWN id. Preserved through import so completion can later be
# reported back to the right external ticket (the write-back/sink seam). Slugified
# to a board-safe id; absent → fall back to the title slug as before.
_ID_LABELS = frozenset({"id", "ticket", "ticket_id"})
# The ticket's 1-5 difficulty (board convention). Fed to the DECOMPOSE-EFFORT-AXIS as
# its heaviest signal; absent → the estimator's own default midpoint.
_DIFFICULTY_LABELS = frozenset({"difficulty", "diff"})
# DECOMPOSE-DEFAULT-GATE escape hatch (recorded, cannot hide — like the detention
# override). ``single-domain: true`` asserts the ticket is one domain; ``no-decompose:
# <reason>`` bypasses with an explicit recorded reason.
_SINGLE_DOMAIN_LABELS = frozenset({"single-domain", "single_domain"})
_NO_DECOMPOSE_LABELS = frozenset({"no-decompose", "no_decompose"})
_TRUTHY = frozenset({"true", "yes", "1", "on", "y"})

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# Label may contain hyphens (e.g. ``single-domain``); still anchored to a leading
# letter, so every pre-existing underscore/word label continues to match.
_FIELD_RE = re.compile(r"^\s*([A-Za-z][\w-]*)\s*:\s*(.*)$")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_PATHISH_RE = re.compile(r"^[\w.][\w./+-]*$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

DEFAULT_TIER = "med"
# Mid-point difficulty used when a ticket declares none — matches the estimator's own
# default so an unspecified ticket scores identically whether or not intake set it.
_DEFAULT_DIFFICULTY = decompose_effort.DEFAULT_DIFFICULTY

# The product repo root, resolved from this module's own location — NOT a hardcoded
# path (public-repo hygiene): src/charon/intake.py → parents[2] == repo root. Handed
# to the DEC-AST-WRAP change-surface engine so the gate measures blast radius against
# the real source tree. Overridable per-call (tests point it at a fixture repo).
_REPO_ROOT = str(Path(__file__).resolve().parents[2])


class IntakeError(RuntimeError):
    """Raised when intake cannot produce a trustworthy plan (e.g. the disjoint-wave
    invariant is violated). Always loud — a plan that cannot be trusted is never
    returned as if it were safe."""


# --------------------------------------------------------------------- raw input
@dataclass
class RawItem:
    """One parsed work item, BEFORE the failure-contract analysis. Pure data —
    field values are stored verbatim, never interpreted."""

    title: str
    body: str = ""
    declared_paths: list[str] = field(default_factory=list)
    inferred_paths: list[str] = field(default_factory=list)
    accept: list[str] = field(default_factory=list)
    tier: str = ""
    declared_deps: list[str] = field(default_factory=list)
    declared_merge: list[str] = field(default_factory=list)
    declared_id: str = ""
    # Raw 1-5 difficulty token verbatim (empty = undeclared); coerced when the
    # PlanUnit is built. Feeds the DECOMPOSE-EFFORT-AXIS.
    declared_difficulty: str = ""
    # DECOMPOSE-DEFAULT-GATE bypass reason (empty = no bypass). Set from a
    # ``single-domain: true`` or ``no-decompose: <reason>`` field.
    bypass_reason: str = ""


# ------------------------------------------------------------- the markdown adapter
def parse_markdown(text: str) -> tuple[str, list[RawItem]]:
    """Adapter: a markdown work-item list → (product_acceptance, items).

    Each ``#``-heading (outside a code fence) opens an item; the body runs to the
    next heading. A heading whose normalized title names an acceptance section
    (e.g. ``## Product acceptance``) is captured as the top-level product
    acceptance instead of a work item. Fenced code blocks are skipped entirely for
    structure parsing — their contents are DATA (injection-safe, ADR-0011 D2.7)."""
    product_acceptance = ""
    items: list[RawItem] = []
    current: RawItem | None = None
    collecting_acceptance = False
    body_lines: list[str] = []
    accept_buf: list[str] = []
    in_fence = False
    fence_marker = ""

    def flush() -> None:
        nonlocal current, body_lines, collecting_acceptance, accept_buf
        nonlocal product_acceptance
        body = "\n".join(body_lines).strip()
        if collecting_acceptance:
            product_acceptance = "\n".join(accept_buf).strip() or body
        elif current is not None:
            current.body = body
            _finalize_item_paths(current)
            items.append(current)
        current = None
        body_lines = []
        accept_buf = []
        collecting_acceptance = False

    for line in text.splitlines():
        fence = _FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
            if current is not None or collecting_acceptance:
                body_lines.append(line)
            continue
        if in_fence:
            # Inside a fence everything is data: no headings, no fields.
            if current is not None or collecting_acceptance:
                body_lines.append(line)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            title = heading.group(2).strip()
            if _normalize(title) in _ACCEPTANCE_TITLES:
                collecting_acceptance = True
            else:
                current = RawItem(title=title)
            continue

        if collecting_acceptance:
            accept_buf.append(line)
            body_lines.append(line)
            continue
        if current is None:
            continue  # preamble before the first heading — ignored

        body_lines.append(line)
        field_m = _FIELD_RE.match(line)
        if field_m:
            label = field_m.group(1).lower()
            value = field_m.group(2).strip()
            _apply_field(current, label, value)

    flush()
    return product_acceptance, items


def _apply_field(item: RawItem, label: str, value: str) -> None:
    if label in _PATH_LABELS:
        item.declared_paths.extend(_split_list(value))
    elif label in _ACCEPT_LABELS:
        item.accept.extend(_split_accept(value))
    elif label in _TIER_LABELS:
        if value:
            item.tier = value.split()[0]
    elif label in _DEP_LABELS:
        item.declared_deps.extend(_split_list(value))
    elif label in _MERGE_LABELS:
        item.declared_merge.extend(_split_list(value))
    elif label in _ID_LABELS:
        # Keep the FIRST id seen (verbatim token); _make_id slugifies it later.
        if value and not item.declared_id:
            tokens = _split_list(value)
            if tokens:
                item.declared_id = tokens[0]
    elif label in _DIFFICULTY_LABELS:
        # Keep the FIRST difficulty token seen; coerced to an int at unit build.
        if value.strip() and not item.declared_difficulty:
            item.declared_difficulty = value.strip().split()[0]
    elif label in _NO_DECOMPOSE_LABELS:
        # An explicit reason always wins (it is the recorded justification).
        if value.strip():
            item.bypass_reason = value.strip()
    elif label in _SINGLE_DOMAIN_LABELS:
        if not item.bypass_reason and value.strip().lower() in _TRUTHY:
            item.bypass_reason = "single-domain: true (operator-declared)"


def _finalize_item_paths(item: RawItem) -> None:
    """Infer owned paths from inline code spans in the body (used only when no
    paths were declared explicitly)."""
    inferred: list[str] = []
    for span in _INLINE_CODE_RE.findall(item.body):
        cand = span.strip()
        if _looks_like_path(cand):
            inferred.append(cand)
    item.inferred_paths = _dedupe(inferred)


def _split_list(value: str) -> list[str]:
    """Split a path/dep field value on commas and whitespace, stripping backticks."""
    parts: list[str] = []
    for chunk in re.split(r"[,\s]+", value.strip()):
        chunk = chunk.strip().strip("`").strip()
        if chunk:
            parts.append(chunk)
    return parts


def _split_accept(value: str) -> list[str]:
    """Capture acceptance commands. Backtick-wrapped spans are each one command
    (so a command may contain commas); otherwise the whole line is one command.
    Stored verbatim — NEVER executed here (ADR-0011 D1)."""
    spans = _INLINE_CODE_RE.findall(value)
    if spans:
        return [s.strip() for s in spans if s.strip()]
    value = value.strip()
    return [value] if value else []


def _looks_like_path(token: str) -> bool:
    if not token or " " in token or not _PATHISH_RE.match(token):
        return False
    return "/" in token or bool(re.search(r"\.[A-Za-z0-9]{1,8}$", token))


# ------------------------------------------------------------------ adapter seam
Adapter = Callable[[str], "tuple[str, list[RawItem]]"]
_ADAPTERS: dict[str, Adapter] = {"markdown": parse_markdown}


def register_adapter(name: str, adapter: Adapter) -> None:
    """Register an input adapter (the brief / backlog / GH-issue seam, ADR-0011 D5).
    v1 ships only ``markdown``; others are a reserved seam, not built here."""
    _ADAPTERS[name] = adapter


def available_adapters() -> list[str]:
    return sorted(_ADAPTERS)


# ----------------------------------------------------------------- the plan model
@dataclass
class PlanUnit:
    """A loadable ticket: has a non-empty ``accept`` (the engine/land contract).
    ``owned_paths`` (land) and ``owns`` (board) mirror each other so one artifact
    feeds both consumers. ``body`` preserves the ticket description for agent
    context — it is NOT used for gating or path-inference (those use ``accept``
    and ``owned_paths`` respectively)."""

    id: str
    goal: str
    accept: list[str]
    body: str = ""
    tier: str = DEFAULT_TIER
    # 1-5 effort difficulty (board convention). Read by the DECOMPOSE-EFFORT-AXIS as
    # its heaviest signal; defaults to the estimator midpoint so undeclared tickets are
    # neutral. Backward-compatible: pre-existing callers that omit it are unaffected.
    difficulty: int = _DEFAULT_DIFFICULTY
    owned_paths: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    merge_after: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    wave: int = 0
    # The id of the broad ticket this unit was decomposed from (the
    # decomposer→sub-ticket linkage). Empty for hand-authored / top-level units,
    # so every existing unit and artifact is unaffected (backward-compatible).
    parent: str = ""
    # DECOMPOSE-DEFAULT-GATE: non-empty iff this unit bypassed the gate via an
    # explicit ``single-domain: true`` / ``no-decompose: <reason>`` escape hatch.
    # Recorded here (and in ``to_dict``) so a bypass can never hide.
    decompose_bypass: str = ""

    @property
    def propose_only(self) -> bool:
        return bool(self.flags)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "body": self.body,
            "accept": list(self.accept),
            "tier": self.tier,
            "difficulty": self.difficulty,
            "owned_paths": list(self.owned_paths),
            "owns": list(self.owned_paths),  # board.Unit reads ``owns``
            "depends_on": list(self.depends_on),
            "merge_after": list(self.merge_after),
            "state": "ready",
            "wave": self.wave,
            "propose_only": self.propose_only,
            "flags": list(self.flags),
            "parent": self.parent,
            "decompose_bypass": self.decompose_bypass,
        }


@dataclass
class ReviewItem:
    """A proposed unit that CANNOT auto-land (no executable acceptance) — captured
    for the human, kept OUT of the loadable ``units`` list so the artifact still
    loads via ``land.load_units`` (ADR-0011 D2.4)."""

    id: str
    goal: str
    kind: str  # e.g. "missing-acceptance"
    reason: str
    owned_paths: list[str] = field(default_factory=list)
    tier: str = DEFAULT_TIER

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "kind": self.kind,
            "reason": self.reason,
            "owned_paths": list(self.owned_paths),
            "tier": self.tier,
            "propose_only": True,
        }


@dataclass
class Issue:
    """A plain-language problem with the input the human must resolve (a
    need-more-detail prompt or an ambiguity), NEVER a silently-invented unit."""

    kind: str  # "need-more-detail" | "no-product-acceptance" | "ambiguous-paths" | ...
    message: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "message": self.message}


@dataclass
class Plan:
    """A durable, diffable ticket plan for a human to approve/edit (ADR-0011 D2.6)."""

    product_acceptance: str
    units: list[PlanUnit] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """True iff the plan is complete enough to act on: a product acceptance is
        captured, at least one loadable unit, and no blocking need-more-detail."""
        blocking = {"need-more-detail", "no-product-acceptance"}
        return bool(self.product_acceptance) and bool(self.units) and not any(
            i.kind in blocking for i in self.issues
        )

    def to_dict(self) -> dict:
        return {
            "schema": "charon-intake-plan/1",
            "ready": self.ready,
            "product_acceptance": self.product_acceptance,
            "units": [u.to_dict() for u in self.units],
            "review_items": [r.to_dict() for r in self.review_items],
            "issues": [i.to_dict() for i in self.issues],
        }

    def write(self, path: str | Path) -> Path:
        """Emit the plan as one JSON artifact (loadable by ``land.load_units`` —
        its ``units`` key holds only loadable units)."""
        p = Path(path)
        p.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return p

    def to_markdown(self) -> str:
        """A human-readable TICKETS-style rendering for review."""
        out: list[str] = ["# Ticket plan (proposed — human approves before any run)", ""]
        pa = self.product_acceptance or "_(none — needs detail)_"
        out.append(f"**Product acceptance:** {pa}")
        out.append(f"**Ready:** {self.ready}")
        out.append("")
        if self.units:
            out.append("## Units")
            for u in self.units:
                dep = f" depends_on={u.depends_on}" if u.depends_on else ""
                flg = f"  ⚠ {u.flags}" if u.flags else ""
                out.append(f"- `{u.id}` (wave {u.wave}, {u.tier}){dep} — {u.goal}")
                out.append(f"    - owns: {u.owned_paths}")
                out.append(f"    - accept: {u.accept}{flg}")
        if self.review_items:
            out.append("")
            out.append("## Needs review (cannot auto-land)")
            for r in self.review_items:
                out.append(f"- `{r.id}` [{r.kind}] {r.goal} — {r.reason}")
        if self.issues:
            out.append("")
            out.append("## Issues (need more detail)")
            for i in self.issues:
                out.append(f"- [{i.kind}] {i.message}")
        return "\n".join(out) + "\n"


# ------------------------------------------------------------------ the front door
def intake(
    text: str,
    *,
    fmt: str = "markdown",
    repo_root: str | None = None,
    config_dir: str | None = None,
    decompose_gate: bool = True,
    auto_decompose: bool = False,
    planner_ask: ModelInvoker | None = None,
    is_detained: Callable[[str], bool] | None = None,
) -> Plan:
    """Induct ``text`` via the ``fmt`` adapter and analyze it into a ticket plan
    (the public entry point). Treats all input as data.

    DECOMPOSE-DEFAULT-GATE (on by default): every new work item is measured against a
    SINGLE-DOMAIN threshold (DEC-AST-WRAP change surface); a broad item that spans >1
    module / crosses a wiring boundary / spans disjoint independence groups is REFUSED
    at intake (fail-loud) unless it carries a ``single-domain: true`` /
    ``no-decompose: <reason>`` escape hatch. ``repo_root``/``config_dir`` point the AST
    engine at the tree (default: the product repo). When ``auto_decompose`` is set (or a
    ``planner_ask`` seam is supplied) the DEC-PLANNER is auto-run to include the proposed
    single-domain sub-tickets in the refusal message. ``decompose_gate=False`` disables
    the gate (used only to prove it is load-bearing)."""
    if fmt not in _ADAPTERS:
        raise IntakeError(f"unknown intake format {fmt!r}; have {available_adapters()}")
    product_acceptance, items = _ADAPTERS[fmt](text)
    return analyze(
        items,
        product_acceptance,
        repo_root=repo_root,
        config_dir=config_dir,
        decompose_gate=decompose_gate,
        auto_decompose=auto_decompose,
        planner_ask=planner_ask,
        is_detained=is_detained,
    )


def intake_file(
    path: str | Path,
    *,
    fmt: str | None = None,
    repo_root: str | None = None,
    config_dir: str | None = None,
    decompose_gate: bool = True,
    auto_decompose: bool = False,
    planner_ask: ModelInvoker | None = None,
    is_detained: Callable[[str], bool] | None = None,
) -> Plan:
    """Induct a file. ``fmt`` defaults to ``markdown`` (the only v1 adapter). The
    DECOMPOSE-DEFAULT-GATE applies exactly as in ``intake`` (same real path)."""
    return intake(
        Path(path).read_text(encoding="utf-8"),
        fmt=fmt or "markdown",
        repo_root=repo_root,
        config_dir=config_dir,
        decompose_gate=decompose_gate,
        auto_decompose=auto_decompose,
        planner_ask=planner_ask,
        is_detained=is_detained,
    )


# ------------------------------------------------------- Phase 2: autonomous mode
# ADR-0008 Phase 2 / ADR-0013. Take input → auto-decompose → run WITHOUT a
# per-plan human gate. HIGH-STAKES, so: defaults OFF (D1); a confidence gate stands
# between decompose and run (D2); runaway/cost bounded by a unit cap + shared
# budget (D5); and if the contract cannot be satisfied we FALL BACK to the Phase-1
# proposal rather than running blind. Decomposition is the SAME mechanical
# ``analyze`` as Phase 1 — input is data, never instructions (D3).
@dataclass
class AutonomousOutcome:
    """Result of an autonomous-intake call. ``mode`` is ``"ran"`` only when the
    plan cleared the confidence gate AND autonomous mode was enabled; otherwise
    ``"proposed"`` — the Phase-1 human-reviewed plan, with ``reason`` explaining
    the fallback in plain language."""

    mode: str  # "ran" | "proposed"
    plan: Plan
    confidence: decompose.Confidence
    run: decompose.AutonomousRunResult | None = None
    reason: str = ""

    @property
    def ran(self) -> bool:
        return self.mode == "ran"

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "confidence": {
                "runnable": self.confidence.runnable,
                "score": self.confidence.score,
                "reasons": list(self.confidence.reasons),
            },
            "plan": self.plan.to_dict(),
            "run": None if self.run is None else {
                "ran": self.run.ran,
                "waves_run": self.run.waves_run,
                "units": list(self.run.units),
                "total_cost_usd": self.run.total_cost_usd,
                "total_tokens": self.run.total_tokens,
                "budget_capped": self.run.budget_capped,
                "note": self.run.note,
            },
        }


def autonomous_intake(
    text: str,
    *,
    fmt: str = "markdown",
    enabled: bool = False,
    max_units: int = decompose.DEFAULT_MAX_UNITS,
    max_cost_usd: float | None = None,
    max_tokens: int | None = None,
    repo: str | None = None,
    autonomy: str = "L0",
    max_parallel: int = 4,
    state_dir: str | None = None,
    runner: decompose.WaveRunner | None = None,
    decompose_units: bool = False,
) -> AutonomousOutcome:
    """Phase-2 front door: induct ``text`` → analyse → (maybe) run, all without a
    per-plan human gate. SAFETY: ``enabled`` defaults False (D1) — the default
    behaviour is identical to Phase 1 (return the plan as a proposal). Even when
    enabled, the plan must clear ``assess_plan`` (D2); on any failure — low
    confidence, propose-only items, scope explosion — we fall back to the proposal
    instead of running blind. The run is wave-by-wave under a shared budget +
    unit cap (D4/D5). Input is treated as DATA throughout (D3)."""
    plan = intake(text, fmt=fmt)
    confidence = decompose.assess_plan(plan, max_units=max_units)

    if not enabled:
        return AutonomousOutcome(
            "proposed", plan, confidence,
            reason="autonomous mode is OFF (default) — plan proposed for human review",
        )
    if not confidence.runnable:
        return AutonomousOutcome(
            "proposed", plan, confidence,
            reason="; ".join(confidence.reasons) or "low confidence — human gate",
        )

    run_kwargs: dict = dict(
        runner=runner,
        max_parallel=max_parallel,
        max_cost_usd=max_cost_usd,
        max_tokens=max_tokens,
        repo=repo,
        autonomy=autonomy,
        decompose_units=decompose_units,
    )
    if state_dir is not None:
        run_kwargs["state_dir"] = state_dir
    result = decompose.run_plan(plan, **run_kwargs)
    return AutonomousOutcome("ran", plan, confidence, run=result)


# ----------------------------------------------------------------- the analysis
def analyze(
    items: Iterable[RawItem],
    product_acceptance: str = "",
    *,
    repo_root: str | None = None,
    config_dir: str | None = None,
    decompose_gate: bool = True,
    auto_decompose: bool = False,
    planner_ask: ModelInvoker | None = None,
    is_detained: Callable[[str], bool] | None = None,
) -> Plan:
    """Apply the ADR-0008 failure contract mechanically to parsed items and emit a
    plan. Pure analysis: nothing is executed, nothing is spawned (ADR-0011 D1).

    The DECOMPOSE-DEFAULT-GATE runs as a final pass (see ``_enforce_decompose_gate``):
    it REFUSES any admitted unit whose change surface exceeds SINGLE-DOMAIN unless the
    unit carries an escape-hatch bypass (recorded on ``PlanUnit.decompose_bypass``)."""
    items = list(items)
    plan = Plan(product_acceptance=product_acceptance.strip())

    if not plan.product_acceptance:
        plan.issues.append(Issue(
            "no-product-acceptance",
            "No top-level product acceptance found. Add a '## Product acceptance' "
            "section describing what the whole thing working looks like.",
        ))

    if not items:
        plan.issues.append(Issue(
            "need-more-detail",
            "No work items found. Provide a markdown list of work items (one per "
            "heading), each with the files it touches and an acceptance command.",
        ))
        return plan

    used_ids: set[str] = set()
    pairs: list[tuple[PlanUnit, RawItem]] = []
    title_to_id: dict[str, str] = {}

    for item in items:
        # Preserve the source ticket's own id when supplied (load-bearing for the
        # future write-back/sink), else fall back to the title slug. Either way it
        # is slugified to a board-safe, deduped id by _make_id.
        uid = _make_id(item.declared_id or item.title, used_ids)
        title_to_id[_normalize(item.title)] = uid
        if item.declared_id:
            title_to_id.setdefault(_normalize(item.declared_id), uid)
        owned = _dedupe(item.declared_paths) or list(item.inferred_paths)

        # contract #5: vague input — no acceptance AND no scope AND no body → never
        # invent a unit; ask for detail.
        if not item.accept and not owned and not item.body.strip():
            plan.issues.append(Issue(
                "need-more-detail",
                f"'{item.title}': need more detail — no files, no acceptance check, "
                "no description. What should change and how is it verified?",
            ))
            continue

        # contract #4: no executable acceptance → propose-only review item (kept out
        # of the loadable units list so the artifact still loads via land).
        if not item.accept:
            plan.review_items.append(ReviewItem(
                id=uid,
                goal=item.title,
                kind="missing-acceptance",
                reason="no executable acceptance check — cannot auto-land; "
                       "add a verifiable command, then it becomes a runnable unit.",
                owned_paths=owned,
                tier=item.tier or DEFAULT_TIER,
            ))
            continue

        flags: list[str] = []
        if not item.declared_paths and item.inferred_paths:
            flags.append("owned paths inferred from prose — confirm scope")
        unit = PlanUnit(
            id=uid,
            goal=item.title,
            accept=list(item.accept),
            body=item.body,
            tier=item.tier or DEFAULT_TIER,
            difficulty=_coerce_difficulty(item.declared_difficulty),
            owned_paths=owned,
            flags=flags,
            merge_after=list(item.declared_merge),
            decompose_bypass=item.bypass_reason,
        )
        pairs.append((unit, item))

    # Resolve declared deps (title → id); drop + flag unknown references (never
    # invent an edge).
    real_units = [u for (u, _it) in pairs]
    by_id = {u.id: u for u in real_units}
    for unit, item in pairs:
        for ref in item.declared_deps:
            target = title_to_id.get(_normalize(ref)) or (ref if ref in by_id else None)
            if target and target != unit.id:
                _add_edge_safe(by_id, unit.id, target)
            elif target != unit.id:
                plan.issues.append(Issue(
                    "ambiguous-paths",
                    f"'{unit.goal}': declared dependency {ref!r} matches no work item "
                    "— edge dropped (no invented dependencies).",
                ))

    # Resolve merge_after edges (title → id); same resolution logic as deps.
    for unit in real_units:
        raw_merge = list(unit.merge_after)
        unit.merge_after.clear()
        for ref in raw_merge:
            target = title_to_id.get(_normalize(ref)) or (ref if ref in by_id else None)
            if target and target != unit.id:
                unit.merge_after.append(target)
            elif target != unit.id:
                plan.issues.append(Issue(
                    "ambiguous-paths",
                    f"'{unit.goal}': declared merge_after {ref!r} matches no work item "
                    "— edge dropped (no invented edges).",
                ))
            target = title_to_id.get(_normalize(ref)) or (ref if ref in by_id else None)
            if target and target != unit.id:
                _add_edge_safe(by_id, unit.id, target)
            elif target != unit.id:
                plan.issues.append(Issue(
                    "ambiguous-paths",
                    f"'{unit.goal}': declared dependency {ref!r} matches no work item "
                    "— edge dropped (no invented dependencies).",
                ))

    # contract #1: file-overlap → serialize (higher id depends on lower id) so no
    # two concurrent units ever share a path.
    scoped = [u for u in real_units if u.owned_paths]
    for i, a in enumerate(scoped):
        for b in scoped[i + 1:]:
            if _overlap(a.owned_paths, b.owned_paths):
                lo, hi = sorted((a, b), key=lambda u: u.id)
                _add_edge_safe(by_id, hi.id, lo.id)

    # contract #2: unprovable independence — a unit with no owned paths cannot be
    # proven disjoint → serialize it after all scoped units + flag for human scoping.
    for u in real_units:
        if not u.owned_paths:
            for s in scoped:
                _add_edge_safe(by_id, u.id, s.id)
            u.flags.append(
                "no owned paths inferred — independence unprovable; serialized "
                "conservatively, confirm scope before running"
            )

    _assign_waves(real_units, by_id)
    plan.units = sorted(real_units, key=lambda u: (u.wave, u.id))

    # Defence in depth: NEVER return a plan whose concurrent units share a path.
    assert_disjoint_waves(plan.units)

    # DECOMPOSE-DEFAULT-GATE (capstone): make decomposition the DEFAULT work-creation
    # path — a broad/god-ticket can never enter the board un-decomposed. Runs on the
    # SAME real path production uses (intake → analyze), never a side function.
    _enforce_decompose_gate(
        plan.units,
        product_acceptance=plan.product_acceptance,
        repo_root=repo_root,
        config_dir=config_dir,
        enabled=decompose_gate,
        auto_decompose=auto_decompose,
        planner_ask=planner_ask,
        is_detained=is_detained,
    )
    return plan


# ----------------------------------------------------------------- graph helpers
def _overlap(a: list[str], b: list[str]) -> bool:
    """True iff any path of ``a`` is the same as / nested under a path of ``b`` (or
    vice-versa). Reuses ``land.in_scope`` so intake, board, and land agree."""
    return any(in_scope(p, b) for p in a) or any(in_scope(p, a) for p in b)


def _depends_transitively(by_id: dict[str, PlanUnit], src: str, dst: str) -> bool:
    """True iff ``src`` already (transitively) depends on ``dst``."""
    seen: set[str] = set()
    stack = list(by_id[src].depends_on) if src in by_id else []
    while stack:
        cur = stack.pop()
        if cur == dst:
            return True
        if cur in seen or cur not in by_id:
            continue
        seen.add(cur)
        stack.extend(by_id[cur].depends_on)
    return False


def _add_edge_safe(by_id: dict[str, PlanUnit], dependent: str, dependency: str) -> None:
    """Add ``dependent`` depends-on ``dependency`` unless it is redundant or would
    create a cycle (i.e. ``dependency`` already depends on ``dependent``)."""
    if dependent == dependency or dependency not in by_id or dependent not in by_id:
        return
    if dependency in by_id[dependent].depends_on:
        return
    if _depends_transitively(by_id, dependency, dependent):
        return  # opposite edge already serializes the pair — adding this loops
    by_id[dependent].depends_on.append(dependency)


def _assign_waves(units: list[PlanUnit], by_id: dict[str, PlanUnit]) -> None:
    """Wave = 1 + max wave of dependencies (longest-path layering). Used for the
    human-readable view; the board derives the same order from ``depends_on``."""
    memo: dict[str, int] = {}

    def wave_of(uid: str, path: frozenset[str] = frozenset()) -> int:
        if uid in memo:
            return memo[uid]
        if uid in path or uid not in by_id:
            return 0
        deps = by_id[uid].depends_on
        w = 0 if not deps else 1 + max(wave_of(d, path | {uid}) for d in deps)
        memo[uid] = w
        return w

    for u in units:
        u.wave = wave_of(u.id)


def assert_disjoint_waves(units: list[PlanUnit]) -> None:
    """Invariant (ADR-0008 contract #1): no two units that could run concurrently
    (neither depends transitively on the other) may share an owned path. Raises
    ``IntakeError`` on violation — a plan that fails this is never returned."""
    by_id = {u.id: u for u in units}
    for i, a in enumerate(units):
        for b in units[i + 1:]:
            if not _overlap(a.owned_paths, b.owned_paths):
                continue
            if _depends_transitively(by_id, a.id, b.id) or _depends_transitively(
                by_id, b.id, a.id
            ):
                continue
            raise IntakeError(
                f"disjoint-wave invariant violated: units {a.id!r} and {b.id!r} "
                f"share a path yet neither depends on the other"
            )


# ------------------------------------------------------ DECOMPOSE-DEFAULT-GATE
def _domain_key(path: str) -> str:
    """A coarse single-domain key: a source file and its co-located test collapse to the
    SAME domain (``src/charon/x.py`` and ``tests/test_x.py`` → ``x``), while two unrelated
    modules are two domains. The heuristic module-count guard that complements the AST
    independence split (a change touching one module plus its own test stays one domain)."""
    base = path.rsplit("/", 1)[-1]
    if base.endswith(".py"):
        base = base[:-3]
    if base.startswith("test_"):
        base = base[len("test_"):]
    return base or path


def _enforce_decompose_gate(
    units: list[PlanUnit],
    *,
    product_acceptance: str,
    repo_root: str | None,
    config_dir: str | None,
    enabled: bool,
    auto_decompose: bool,
    planner_ask: ModelInvoker | None,
    is_detained: Callable[[str], bool] | None,
) -> None:
    """REFUSE to admit any unit that exceeds SINGLE-DOMAIN by change SURFACE **or** by
    EFFORT.

    SURFACE axis: the DEC-AST-WRAP ``change_surface`` is measured over the unit's owned
    paths. "Broad" is the engine's own signal — the AST independence proof splits the owned
    files into MORE THAN ONE provably-independent group (the unit bundles work that could run
    as separate collision-free tickets). Files the engine cannot prove independent stay in
    ONE group and are admitted as a single coherent domain (conservative — coupled modules
    are legitimately one unit). A single (or zero) owned path is single-domain by
    construction, so the common single-file ticket never even builds the import graph.

    EFFORT axis (DECOMPOSE-EFFORT-AXIS): surface breadth != effort. A single-file / coupled
    ticket that is nonetheless LARGE-and-slow (high difficulty, many required behaviors)
    never trips the surface axis at all, yet is the poster child for over-scope. So EVERY
    admitted unit — including the single-file one the surface axis skips — is ALSO scored by
    ``decompose_effort``: a clear over-effort call is REFUSED (fail-loud, like the surface
    refusal); a soft-band call is ADMITTED with a recorded advisory (irreducible
    one-file-but-big work must not be blocked). The effort SIZE signal REUSES the
    ``change_surface`` already computed for the surface axis when there is one (multi-file
    units) — it is never recomputed, so the intake path takes no extra AST pass.

    The escape hatch (``decompose_bypass``, recorded on the unit) admits regardless and
    bypasses BOTH axes, with the reason preserved."""
    if not enabled:
        return
    root = repo_root or _REPO_ROOT
    for unit in units:
        if unit.decompose_bypass:
            continue  # explicit, recorded escape hatch — bypasses BOTH axes, cannot hide

        # SURFACE axis. Only a unit with >1 owned path can span >1 independence group, so
        # the single-file ticket never builds the import graph. ``surface`` is captured and
        # reused by the effort axis below (no second change_surface pass).
        surface: dict | None = None
        if len(unit.owned_paths) > 1:
            surface = change_surface(unit.owned_paths, repo_root=root, config_dir=config_dir)
            groups_val = surface.get("independence_groups")
            groups = groups_val if isinstance(groups_val, list) else []
            if len(groups) > 1:
                files_val = surface.get("files")
                files = files_val if isinstance(files_val, list) else list(unit.owned_paths)
                domains = sorted({_domain_key(str(p)) for p in files})
                suggestion = _suggest_split(
                    unit, surface, product_acceptance, planner_ask, is_detained,
                    config_dir, auto_decompose,
                )
                raise IntakeError(_gate_refusal_message(unit, domains, groups, suggestion))

        # EFFORT axis — runs for EVERY admitted unit (incl. single-file), reusing ``surface``.
        _enforce_effort_axis(
            unit, surface,
            product_acceptance=product_acceptance,
            planner_ask=planner_ask,
            is_detained=is_detained,
            config_dir=config_dir,
            auto_decompose=auto_decompose,
        )


def _enforce_effort_axis(
    unit: PlanUnit,
    surface: dict | None,
    *,
    product_acceptance: str,
    planner_ask: ModelInvoker | None,
    is_detained: Callable[[str], bool] | None,
    config_dir: str | None,
    auto_decompose: bool,
) -> None:
    """Score ``unit`` on the EFFORT axis and act on the verdict.

    ``over-scope`` → REFUSE at intake (fail-loud, naming the effort reason); auto-run the
    planner for a concrete split only when a change surface is available (a single-file
    over-effort ticket has nothing to surface-split — that is exactly why it is over EFFORT,
    not over surface). ``advise-split`` → ADMIT but record an advisory warning on the unit
    (never blocks irreducible one-file-but-big work). ``ok`` → untouched. ``surface`` (when
    the surface axis computed one) feeds the SIZE signal instead of the compute-free
    owned-path fallback — no recompute."""
    score = decompose_effort.estimate_effort(unit, surface=surface)
    tier = unit.tier or None
    verdict = decompose_effort.effort_verdict(score, tier=tier)
    if verdict == "ok":
        return
    threshold = decompose_effort.tier_threshold(tier)
    if verdict == "over-scope":
        suggestion = None
        if surface is not None:
            suggestion = _suggest_split(
                unit, surface, product_acceptance, planner_ask, is_detained,
                config_dir, auto_decompose,
            )
        raise IntakeError(_effort_refusal_message(unit, score, threshold, suggestion))
    # advise-split (soft band) — advisory only: admit, but record a warning that cannot hide.
    unit.flags.append(_effort_advisory_flag(score, threshold))


def _effort_refusal_message(
    unit: PlanUnit,
    score: decompose_effort.EffortScore,
    threshold: decompose_effort.EffortThreshold,
    suggestion: list[PlanUnit] | None,
) -> str:
    """A fail-loud, actionable EFFORT refusal — names what tripped (score vs hard band and
    the underlying signals) and exactly how to proceed."""
    lines = [
        f"DECOMPOSE-EFFORT-AXIS: work item {unit.id!r} ({unit.goal!r}) is OVER-SCOPE by "
        "EFFORT and cannot enter the board un-decomposed.",
        f"  effort score {score.total} >= hard threshold {threshold.hard} (tier {unit.tier!r})",
        f"  signals: difficulty={score.difficulty}, size={score.size:g}, "
        f"behaviors={score.behaviors}",
        f"  detail: {'; '.join(score.notes)}",
    ]
    if suggestion:
        lines.append(
            f"  DEC-PLANNER proposes {len(suggestion)} sub-ticket(s) "
            "(submit these instead of the parent):"
        )
        for sub in suggestion:
            lines.append(f"    - {sub.id}: owns {sub.owned_paths} (parent={sub.parent})")
    lines.append(
        "  FIX: split into smaller sub-tickets (fewer required behaviours / lower difficulty "
        "each), OR add 'single-domain: true' / 'no-decompose: <reason>' to bypass (recorded)."
    )
    return "\n".join(lines)


def _effort_advisory_flag(
    score: decompose_effort.EffortScore,
    threshold: decompose_effort.EffortThreshold,
) -> str:
    """The recorded (never-blocking) advisory for a soft-band unit."""
    return (
        f"effort advisory: score {score.total} is in the advise-split band "
        f"({threshold.soft} <= score < {threshold.hard}) — difficulty={score.difficulty}, "
        f"behaviors={score.behaviors}. Consider splitting; admitted (irreducible "
        "one-file-but-big work is allowed)."
    )


def _suggest_split(
    unit: PlanUnit,
    surface: dict,
    product_acceptance: str,
    planner_ask: ModelInvoker | None,
    is_detained: Callable[[str], bool] | None,
    config_dir: str | None,
    auto_decompose: bool,
) -> list[PlanUnit] | None:
    """AUTO-run the DEC-PLANNER over the broad ticket's change surface to emit disjoint
    single-domain sub-tickets, for the actionable refusal message. Only attempted when a
    planner is available (``planner_ask`` supplied or ``auto_decompose`` set), so the base
    intake path stays network-free and deterministic. Any planner failure (no configured
    model, bad reply, unresolvable split) degrades to ``None`` — the parent is still
    refused, just without a concrete suggestion."""
    if planner_ask is None and not auto_decompose:
        return None
    # Lazy, package-relative import: decompose_planner imports intake at module load, so
    # a static ``from .decompose_planner import ...`` here would trip the arch-lint
    # circular-import check. The ``from . import`` form (as decompose_planner itself uses
    # for recommend/secrets) resolves to the package, breaking the static self-edge; at
    # runtime decompose_planner is fully loaded by the time this runs, so there is no cycle.
    from . import decompose_planner as _dp

    try:
        subs = _dp.plan_decomposition(
            _dp.BroadTicket(
                id=unit.id,
                goal=unit.goal,
                body=unit.body,
                product_acceptance=product_acceptance,
            ),
            surface,
            ask=planner_ask,
            is_detained=is_detained,
            config_dir=config_dir,
        )
    except _dp.PlannerError:
        return None
    for sub in subs:
        sub.parent = unit.id
    return subs


def _gate_refusal_message(
    unit: PlanUnit,
    domains: list[str],
    groups: list,
    suggestion: list[PlanUnit] | None,
) -> str:
    """A fail-loud, actionable refusal: what tripped, and exactly how to proceed."""
    lines = [
        f"DECOMPOSE-DEFAULT-GATE: work item {unit.id!r} ({unit.goal!r}) exceeds "
        "SINGLE-DOMAIN and cannot enter the board un-decomposed.",
        f"  owns spans {len(domains)} domain(s): {domains}",
        f"  AST independence split → {len(groups)} group(s): {groups}",
    ]
    if suggestion:
        lines.append(
            f"  DEC-PLANNER proposes {len(suggestion)} single-domain sub-ticket(s) "
            "(submit these instead of the parent):"
        )
        for sub in suggestion:
            lines.append(f"    - {sub.id}: owns {sub.owned_paths} (parent={sub.parent})")
    lines.append(
        "  FIX: split into single-domain sub-tickets (one module each), OR add "
        "'single-domain: true' / 'no-decompose: <reason>' to bypass (recorded)."
    )
    return "\n".join(lines)


# ----------------------------------------------------------------- small helpers
def _coerce_difficulty(raw: str) -> int:
    """A declared difficulty token → int. Undeclared / unparseable degrades to the
    estimator midpoint (never invents a difficulty). The estimator clamps to 1-5."""
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return _DEFAULT_DIFFICULTY


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _make_id(title: str, used: set[str]) -> str:
    """A board-safe unit id (validated by ``ledger.validate_task_id``) from a title,
    deduped against ``used``."""
    base = _SLUG_RE.sub("-", title.lower()).strip("-")[:48]
    if not base or not base[0].isalnum():
        base = ("u-" + base).strip("-") or "unit"
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base[:60]}-{n}"
        n += 1
    validate_task_id(candidate)
    used.add(candidate)
    return candidate
