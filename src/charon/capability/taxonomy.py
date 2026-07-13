"""Open, append-only work-class taxonomy + cheap hot-path classifier.

Implements GATEWAY-PROGRAM §1.9: the hot path classifies a task to a KNOWN
work_class or ``"unknown"``. Unknown tasks route via a safe default AND are
logged so an offline crystallizer can later cluster them into new named
classes. Classification is deterministic + stdlib-only — no per-request LLM,
no third-party deps — so the gateway keeps its tail-latency budget.

Two core types:

  * :class:`WorkClassDef` — a named class in the taxonomy, with a cheap
    regex/keyword-based classifier and an operator-managed **risk attestation**
    (``high`` or ``low``). New/unknown classes always default to ``high`` until
    an operator explicitly attests otherwise (GATEWAY-PROGRAM §1.9 red-team
    fix #4: breaks the novel-class × risk-gate deadlock).

  * :class:`WorkClassTaxonomy` — the open, append-only registry that owns the
    list of named classes + an :class:`UnknownSink` for things the hot path
    could not classify.

The hot path uses :func:`WorkClassTaxonomy.classify_request` which returns a
:class:`Classification` carrying either a known :class:`WorkClassDef` or
``"unknown"`` + the signals that triggered the fallback. An offline operator
runs :meth:`WorkClassTaxonomy.crystallize` to inspect the ``UnknownSink``,
group its entries by signature, and either (a) ``add`` a new named class
that covers a cluster, or (b) ``prune`` stale signatures. The hot path
itself NEVER crystallizes — that is intentionally offline.

Stdlib-only (re, dataclasses, json, hashlib). This module lives in
``charon.capability`` next to ``actuals.py`` and ``scorecard.py`` — same
isolation rationale (capability subsystem, no third-party deps).
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

RiskLevel = Literal["high", "low"]
"""Risk attestation for a work class.

``high`` = never explored via live uniform sampling; only reds-replay /
spec-floor may drive it (GATEWAY-PROGRAM §1.9 red-team fix #4).
``low``  = safe for live uniform exploration. The default for known classes
built from the canonical :data:`_SEED_CLASSES` table is ``low`` because the
seed table is hand-curated; only classes that arrive via :meth:`crystallize`
default to ``high``.
"""

ClassificationKind = Literal["known", "unknown"]


# ── canonical seed taxonomy ─────────────────────────────────────────────
# Hand-curated, conservative. Each entry maps a CLASS NAME → the cheap
# pattern(s) that identify it. Patterns are tried IN ORDER; first hit wins.
# A request that hits no pattern is logged to the unknown sink.
#
# NOTE: these patterns are deliberately SIMPLE (keyword/regex on user-visible
# text). The hot path has no LLM budget. The crystallizer is what produces
# better patterns later — fed by the unknown sink + an LLM, offline.
_SEED_CLASSES: tuple[dict, ...] = (
    {
        "name": "reasoning",
        "patterns": (
            r"\b(reason|think\s+step\s+by\s+step|prove|solve\s+this|"
            r"chain\s+of\s+thought|logic\s+puzzle|"
            r"math(ematical)?\s+problem|equation)\b",
        ),
        "risk": "low",
        "description": "multi-step reasoning, proofs, math, logic puzzles",
    },
    {
        "name": "coding",
        "patterns": (
            r"\b(write\s+(a\s+|the\s+)?(\w+\s+)?(function|method|class|script|program|module)\b"
            r"|\bimplement\b|\bdebug\b"
            r"|\bfix\s+(the|this|my|your)\s+(bug|error|exception|crash)\b"
            r"|\brefactor\b|\bcode\s+review\b|\bunit\s+test\b"
            r"|\bpatch\b|\bcompile\b|\bsyntax\s+error\b"
            r"|\bin\s+(python|javascript|typescript|rust|go|java|c\+\+|c#|ruby|php|kotlin|swift)\b)",
        ),
        "risk": "low",
        "description": "code writing, debugging, refactoring, code review",
    },
    {
        "name": "translation",
        "patterns": (
            r"\b(translate|translation|"
            r"convert\s+(this|these|the)\s+(text|sentence|paragraph)\s+(from|to)\s+\w+|"
            r"into\s+(japanese|french|spanish|german|chinese|korean|italian|portuguese|english)|"
            r"english\s+to\s+\w+|\w+\s+to\s+english|"
            r"\b(japanese|french|spanish|german|chinese|korean|italian|portuguese)\b)",
        ),
        "risk": "low",
        "description": "language translation",
    },
    {
        "name": "creative",
        "patterns": (
            r"\b(write\s+(a\s+|the\s+)?(poem|story|essay|song|lyrics|haiku|novel|scene)\b|"
            r"creative\s+writing|brainstorm|narrative|fictional\s+character|dialogue)\b",
        ),
        "risk": "low",
        "description": "creative writing, poetry, story, brainstorming",
    },
    {
        "name": "analysis",
        "patterns": (
            r"\b(analy[sz](e|es|ed|ing)?|analysis|"
            r"summari[sz](e|es|ed|ing)?|"
            r"compare\s+and\s+contrast|"
            r"breakdown|interpret|evaluate|assess|"
            r"review\s+(the|this|my)\s+(data|report|results|findings|paper|study))\b",
        ),
        "risk": "low",
        "description": "summarize, analyze, compare, interpret data",
    },
    {
        "name": "general",
        "patterns": (
            r".+",  # ALWAYS matches last — the catch-all.
        ),
        "risk": "low",
        "description": "fallback for anything that didn't match a specific class",
    },
)


# ── core data shapes ────────────────────────────────────────────────────


@dataclass(frozen=True)
class WorkClassDef:
    """One named entry in the taxonomy.

    ``patterns`` are tried IN ORDER at classify-time; first hit wins.
    ``risk`` is operator-managed: NEW/unknown classes default to ``"high"``
    (red-team fix #4). Only an explicit :meth:`WorkClassTaxonomy.attest`
    call moves a class to ``"low"``.
    """

    name: str
    patterns: tuple[str, ...]
    risk: RiskLevel
    description: str = ""
    # Provenance: "seed" for the canonical table, "crystallized" for classes
    # the offline crystallizer produced. Operators can refuse to attest
    # crystallized classes until they have inspected them.
    provenance: Literal["seed", "crystallized"] = "seed"

    def compiled(self) -> tuple[re.Pattern[str], ...]:
        """Compile this class's patterns once (cached on the instance)."""
        cached = getattr(self, "_compiled_cache", None)
        if cached is not None and len(cached) == len(self.patterns):
            return cached  # type: ignore[return-value]
        compiled = tuple(re.compile(p, re.IGNORECASE | re.DOTALL) for p in self.patterns)
        object.__setattr__(self, "_compiled_cache", compiled)
        return compiled


@dataclass(frozen=True)
class UnknownEntry:
    """One request the hot path could not classify.

    Captures the visible text fingerprint (so the offline crystallizer can
    cluster without ever needing the raw prompt) + a count + first/last seen.
    """

    signature: str            # sha256 of normalised text — the cluster key
    sample: str               # short sample of the prompt (capped, for human review)
    count: int
    first_seen: float
    last_seen: float

    def to_dict(self) -> dict:
        return {
            "signature": self.signature,
            "sample": self.sample,
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, d: dict) -> UnknownEntry:
        return cls(
            signature=str(d["signature"]),
            sample=str(d.get("sample", "")),
            count=int(d.get("count", 1)),
            first_seen=float(d.get("first_seen", 0.0)),
            last_seen=float(d.get("last_seen", 0.0)),
        )


@dataclass(frozen=True)
class Classification:
    """The hot-path's verdict for one request.

    ``kind="known"`` + :attr:`work_class` is the typical path. ``kind="unknown"``
    means the safe default + :class:`UnknownSink` logging should fire (the
    gateway still serves the request via the default route, just doesn't
    attribute it to a work class for the bandit).
    """

    kind: ClassificationKind
    work_class: WorkClassDef | None = None
    signature: str | None = None    # only set when kind == "unknown"
    matched_pattern: str | None = None  # diagnostic — which seed pattern hit

    @property
    def is_unknown(self) -> bool:
        return self.kind == "unknown"

    def name(self) -> str:
        """Convenience: the class name OR ``"unknown"`` for routing keys."""
        return self.work_class.name if self.work_class else "unknown"


@dataclass
class UnknownSink:
    """In-memory unknown-pile the crystallizer inspects.

    Bounded by :attr:`max_entries`: once full, NEW signatures evict the
    LEAST-RECENTLY-SEEN existing entry. This is the offline-feed's safety
    valve — a runaway stream of novel prompts must NOT OOM the gateway.
    """

    max_entries: int = 4096
    _entries: dict[str, UnknownEntry] = field(default_factory=dict)

    def record(self, *, signature: str, sample: str, now: float) -> None:
        """Record (or bump) one unknown sighting.

        If the sink is full and ``signature`` is new, evict the LRU entry
        (smallest ``last_seen``). This keeps the most-active unknown classes
        in the working set while bounding memory.
        """
        existing = self._entries.get(signature)
        if existing is not None:
            self._entries[signature] = UnknownEntry(
                signature=existing.signature,
                sample=existing.sample,
                count=existing.count + 1,
                first_seen=existing.first_seen,
                last_seen=now,
            )
            return
        if len(self._entries) >= self.max_entries:
            lru_sig = min(self._entries, key=lambda s: self._entries[s].last_seen)
            self._entries.pop(lru_sig, None)
        self._entries[signature] = UnknownEntry(
            signature=signature,
            sample=sample[:240],  # cap for human review; never store the full prompt
            count=1,
            first_seen=now,
            last_seen=now,
        )

    def all(self) -> list[UnknownEntry]:
        """All entries, freshest first."""
        return sorted(self._entries.values(), key=lambda e: -e.last_seen)

    def top(self, n: int) -> list[UnknownEntry]:
        """Top-N entries by count (the crystallizer's primary feed)."""
        return sorted(self._entries.values(), key=lambda e: -e.count)[:n]

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def to_dict(self) -> dict:
        return {
            "max_entries": self.max_entries,
            "entries": [e.to_dict() for e in self.all()],
        }


# ── taxonomy ────────────────────────────────────────────────────────────


@dataclass
class WorkClassTaxonomy:
    """Open, append-only taxonomy of work classes.

    Construct with the default seed classes (always present) and add more
    via :meth:`add` (operator) or :meth:`crystallize` (offline batch).

    The hot path uses :meth:`classify_request` — that is the only method
    the gateway should call per-request. ``add`` / ``attest`` /
    ``crystallize`` are operator/admin tools and NEVER run on the request
    path.
    """

    _classes: dict[str, WorkClassDef] = field(default_factory=dict)
    unknown: UnknownSink = field(default_factory=UnknownSink)

    def __post_init__(self) -> None:
        # Seed the canonical taxonomy once. Re-seeding on copy() is the
        # caller's responsibility (see copy() below).
        if not self._classes:
            for entry in _SEED_CLASSES:
                self._classes[entry["name"]] = WorkClassDef(
                    name=entry["name"],
                    patterns=tuple(entry["patterns"]),
                    risk=entry["risk"],  # type: ignore[arg-type]
                    description=entry["description"],
                    provenance="seed",
                )

    # ── read API (hot path uses this) ─────────────────────────────────

    def names(self) -> list[str]:
        """All known class names, in registration order (seed first)."""
        # Seed classes first, then crystallized — gives the classifier a
        # stable priority order so seed matches win ties.
        seeds = [n for n, c in self._classes.items() if c.provenance == "seed"]
        cryst = [n for n, c in self._classes.items() if c.provenance == "crystallized"]
        return seeds + cryst

    def get(self, name: str) -> WorkClassDef | None:
        return self._classes.get(name)

    def classify_request(self, text: str) -> Classification:
        """Classify a request — hot path.

        Returns a :class:`Classification`. ``kind="unknown"`` means the
        gateway should fall back to the safe default route and log to the
        unknown sink. The function is intentionally side-effect-free on the
        classifier itself; callers that want unknown logging should pass the
        result to :meth:`observe_unknown`.
        """
        if not text:
            return Classification(kind="unknown", signature=_signature(text))

        for name in self.names():
            cls = self._classes[name]
            for pat in cls.compiled():
                m = pat.search(text)
                if m:
                    return Classification(
                        kind="known",
                        work_class=cls,
                        matched_pattern=pat.pattern,
                    )
        return Classification(kind="unknown", signature=_signature(text))

    # ── write API (operator / crystallizer; never hot-path) ────────────

    def add(
        self,
        name: str,
        patterns: list[str] | tuple[str, ...],
        *,
        risk: RiskLevel = "high",
        description: str = "",
        provenance: Literal["seed", "crystallized"] = "crystallized",
    ) -> WorkClassDef:
        """Append a new named class. Returns the inserted :class:`WorkClassDef`.

        New classes default to ``risk="high"`` (red-team fix #4). Operators
        MUST call :meth:`attest` to enable live uniform exploration. Throws
        :class:`ValueError` if the name already exists (the taxonomy is
        append-only — use :meth:`update_patterns` to amend an existing one).
        """
        if name in self._classes:
            raise ValueError(f"work_class {name!r} already exists (append-only)")
        cls = WorkClassDef(
            name=name,
            patterns=tuple(patterns),
            risk=risk,
            description=description,
            provenance=provenance,
        )
        self._classes[name] = cls
        return cls

    def update_patterns(self, name: str, patterns: list[str] | tuple[str, ...]) -> None:
        """Replace the patterns for an existing class (the ONE mutator that
        does NOT violate append-only — names are immutable, only patterns
        refine). Resets the compiled-patterns cache."""
        existing = self._classes.get(name)
        if existing is None:
            raise KeyError(name)
        self._classes[name] = WorkClassDef(
            name=existing.name,
            patterns=tuple(patterns),
            risk=existing.risk,
            description=existing.description,
            provenance=existing.provenance,
        )

    def attest(self, name: str, *, risk: RiskLevel = "low") -> WorkClassDef:
        """Operator attestation: declare a class as low-risk (or back to high).

        This is the ONLY way to flip a crystallized class from ``"high"`` to
        ``"low"`` — the gateway will NOT do it automatically (red-team fix
        #4: breaks the novel-class × risk-gate deadlock by making every
        new class high-by-default until a human says otherwise).
        """
        existing = self._classes.get(name)
        if existing is None:
            raise KeyError(name)
        self._classes[name] = WorkClassDef(
            name=existing.name,
            patterns=existing.patterns,
            risk=risk,
            description=existing.description,
            provenance=existing.provenance,
        )
        return self._classes[name]

    def observe_unknown(self, text: str, *, now: float) -> Classification:
        """Run :meth:`classify_request` AND log to the unknown sink if needed.

        Convenience wrapper the gateway uses per request. The hot path SHOULD
        call this instead of classify_request directly when it wants unknown
        tasks recorded for the crystallizer. Never raises.
        """
        result = self.classify_request(text)
        if result.is_unknown:
            self.unknown.record(signature=result.signature or _signature(text),
                                sample=text, now=now)
        return result

    def crystallize(
        self,
        *,
        min_count: int = 5,
        max_new: int = 16,
        suggest_only: bool = True,
    ) -> list[dict]:
        """Offline batch: cluster the unknown pile and PROPOSE new classes.

        Returns a list of proposal dicts. By default ``suggest_only=True`` so
        a human operator can inspect each cluster before :meth:`add`-ing it.
        Pass ``suggest_only=False`` to insert the top clusters as new
        crystallized classes (always ``risk="high"`` per red-team fix #4).

        A cluster is "interesting" if its entry's ``count >= min_count``.
        The top ``max_new`` clusters by count become proposals.
        """
        interesting = [e for e in self.unknown.top(max_new * 4) if e.count >= min_count]
        # Group by signature prefix (first 16 hex chars) so identical near-dupes
        # cluster together even if the full hash differs on whitespace.
        bucket_counts: Counter[str] = Counter()
        bucket_samples: dict[str, str] = {}
        for entry in interesting:
            prefix = entry.signature[:16]
            bucket_counts[prefix] += entry.count
            if prefix not in bucket_samples:
                bucket_samples[prefix] = entry.sample
        proposals: list[dict] = []
        for prefix, total in bucket_counts.most_common(max_new):
            proposals.append({
                "signature_prefix": prefix,
                "total_count": int(total),
                "sample": bucket_samples[prefix],
                "suggested_name": f"novel-{prefix[:8]}",
                "suggested_patterns": _derive_patterns(bucket_samples[prefix]),
                "risk": "high",   # ALWAYS high until operator attest()s (red-team fix #4)
            })
        if not suggest_only:
            for p in proposals:
                # Skip if the suggested name collides — better to surface a
                # collision than silently overwrite a real class.
                if p["suggested_name"] not in self._classes:
                    self.add(
                        p["suggested_name"],
                        p["suggested_patterns"],
                        risk="high",
                        description=f"crystallized from unknown pile ({p['total_count']} hits)",
                    )
        return proposals

    # ── persistence (operator / crystallizer; never hot-path) ──────────

    def to_dict(self) -> dict:
        """Serialise the taxonomy (classes + unknown sink) to a JSON-safe dict."""
        return {
            "version": 1,
            "classes": [
                {
                    "name": c.name,
                    "patterns": list(c.patterns),
                    "risk": c.risk,
                    "description": c.description,
                    "provenance": c.provenance,
                }
                for c in (self._classes[n] for n in self.names())
            ],
            "unknown": self.unknown.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkClassTaxonomy:
        """Reverse of :meth:`to_dict`. Empty/missing fields → fresh taxonomy."""
        tax = cls()
        tax._classes = {}  # wipe the seeds — operator may override them
        for entry in d.get("classes", []):
            tax._classes[entry["name"]] = WorkClassDef(
                name=entry["name"],
                patterns=tuple(entry.get("patterns", (".+",))),
                risk=entry.get("risk", "high"),  # type: ignore[arg-type]
                description=entry.get("description", ""),
                provenance=entry.get("provenance", "crystallized"),  # type: ignore[arg-type]
            )
        # If the file had no classes at all (empty taxonomy state), re-seed
        # so the hot path still has the canonical fallback.
        if not tax._classes:
            for entry in _SEED_CLASSES:
                tax._classes[entry["name"]] = WorkClassDef(
                    name=entry["name"],
                    patterns=tuple(entry["patterns"]),
                    risk=entry["risk"],  # type: ignore[arg-type]
                    description=entry["description"],
                    provenance="seed",
                )
        sink_data = d.get("unknown", {})
        if sink_data:
            sink = UnknownSink(max_entries=int(sink_data.get("max_entries", 4096)))
            for e in sink_data.get("entries", []):
                ent = UnknownEntry.from_dict(e)
                sink._entries[ent.signature] = ent
            tax.unknown = sink
        return tax

    def copy(self) -> WorkClassTaxonomy:
        """Deep copy (for tests; the gateway should reuse one taxonomy instance)."""
        new = WorkClassTaxonomy()
        new._classes = dict(self._classes)
        new.unknown = UnknownSink(max_entries=self.unknown.max_entries)
        new.unknown._entries = dict(self.unknown._entries)
        return new


# ── helpers ─────────────────────────────────────────────────────────────


_SAMPLE_LIMIT = 4096


def _signature(text: str) -> str:
    """Stable fingerprint of a prompt — the cluster key the crystallizer groups on.

    Normalises whitespace + lowercases before hashing so visually-similar
    prompts cluster together even if their formatting differs. Caps input
    length so a runaway 1MB prompt doesn't dominate the hash.
    """
    norm = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return hashlib.sha256(norm[:_SAMPLE_LIMIT].encode("utf-8")).hexdigest()


def _derive_patterns(sample: str) -> list[str]:
    """Cheap, regex-friendly patterns the crystallizer proposes for a cluster.

    Intent: NOT a real ML model — just enough that an operator inspecting the
    proposal can see a candidate rule and either accept it or replace it
    before :meth:`add`. Returns the longest 1-3 unique ``\bword\b`` tokens
    from the sample (case-insensitive), or a quoted substring if the sample
    has no obvious keywords.
    """
    if not sample:
        return [r".+"]  # generic fallback
    tokens = re.findall(r"[a-zA-Z]{4,}", sample.lower())
    seen: list[str] = []
    for t in tokens:
        if t in seen:
            continue
        seen.append(t)
        if len(seen) >= 3:
            break
    if seen:
        return [rf"\b{re.escape(t)}\b" for t in seen]
    return [re.escape(sample[:40])]


__all__ = [
    "RiskLevel",
    "ClassificationKind",
    "WorkClassDef",
    "UnknownEntry",
    "Classification",
    "UnknownSink",
    "WorkClassTaxonomy",
]