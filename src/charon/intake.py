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

from .land import in_scope
from .ledger import validate_task_id

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

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_FIELD_RE = re.compile(r"^\s*([A-Za-z_]+)\s*:\s*(.*)$")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_PATHISH_RE = re.compile(r"^[\w.][\w./+-]*$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

DEFAULT_TIER = "sonnet"


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
    feeds both consumers."""

    id: str
    goal: str
    accept: list[str]
    tier: str = DEFAULT_TIER
    owned_paths: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    wave: int = 0

    @property
    def propose_only(self) -> bool:
        return bool(self.flags)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "accept": list(self.accept),
            "tier": self.tier,
            "owned_paths": list(self.owned_paths),
            "owns": list(self.owned_paths),  # board.Unit reads ``owns``
            "depends_on": list(self.depends_on),
            "state": "ready",
            "wave": self.wave,
            "propose_only": self.propose_only,
            "flags": list(self.flags),
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
def intake(text: str, *, fmt: str = "markdown") -> Plan:
    """Induct ``text`` via the ``fmt`` adapter and analyze it into a ticket plan
    (the public entry point). Treats all input as data."""
    if fmt not in _ADAPTERS:
        raise IntakeError(f"unknown intake format {fmt!r}; have {available_adapters()}")
    product_acceptance, items = _ADAPTERS[fmt](text)
    return analyze(items, product_acceptance)


def intake_file(path: str | Path, *, fmt: str | None = None) -> Plan:
    """Induct a file. ``fmt`` defaults to ``markdown`` (the only v1 adapter)."""
    return intake(Path(path).read_text(encoding="utf-8"), fmt=fmt or "markdown")


# ----------------------------------------------------------------- the analysis
def analyze(items: Iterable[RawItem], product_acceptance: str = "") -> Plan:
    """Apply the ADR-0008 failure contract mechanically to parsed items and emit a
    plan. Pure analysis: nothing is executed, nothing is spawned (ADR-0011 D1)."""
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
        uid = _make_id(item.title, used_ids)
        title_to_id[_normalize(item.title)] = uid
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
            tier=item.tier or DEFAULT_TIER,
            owned_paths=owned,
            flags=flags,
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


# ----------------------------------------------------------------- small helpers
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
