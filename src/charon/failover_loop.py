"""Generic candidate-failover primitive (stdlib-only, reusable by composition).

The operator directive: "no tool should be that inflexible." Any caller that invokes an
LLM by picking ONE model and hard-failing is *stiff* — a dead/mis-scoped key or a flaky
provider should fail OVER to the next configured model, not surface an opaque error. That
pattern is not planner-specific, so it lives here as a small reusable helper rather than
inlined in one caller.

``invoke_with_failover`` walks an ORDERED candidate list and, per candidate, runs a bounded
retry loop. Each attempt is classified by the caller into one of three outcomes:

  * ``ok``       — a valid result; return it immediately (first valid wins).
  * ``retry``    — a fault of THIS candidate's *answer* (parse/quality/validation). Re-run
                   the SAME candidate with feedback, up to ``max_retries`` more times.
  * ``failover`` — a PROVIDER-level fault (auth/limit/infra). This candidate can't serve;
                   advance to the NEXT candidate.

Only when EVERY candidate is exhausted does it raise — via the caller-supplied ``error``
factory — a message that names each candidate's failure and ends with the caller's
actionable ``recommendation``. This is the north-star failover invariant (never out of
workers while ≥1 viable) applied as a generic control-flow primitive.

First consumer: ``decompose_planner.plan_decomposition``. Follow-on adopters (see each
module's stiff single-model invoke): ``recommend._ask_model`` and the ``cli.py`` chat path.

Privileged-core rule: stdlib-only. This is a distinct concern from ``failover.py`` (which
is the proxy↔pool-router glue for the running gateway); this module has NO gateway deps.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar, cast

C = TypeVar("C")  # a candidate (opaque to this module; the caller interprets it)
T = TypeVar("T")  # a successful result value

OK = "ok"
RETRY = "retry"
FAILOVER = "failover"


@dataclass
class AttemptResult(Generic[T]):
    """The outcome of one attempt against one candidate.

    ``kind`` is one of ``OK`` / ``RETRY`` / ``FAILOVER``. ``value`` is set only for ``OK``.
    ``feedback`` is threaded into the next ``RETRY`` attempt against the same candidate.
    ``attribution`` is the short per-candidate note recorded for the exhaustion message
    (e.g. ``"auth (HTTP 401): dead key"`` or ``"disjointness: units overlap"``)."""

    kind: str
    value: T | None = None
    feedback: str = ""
    attribution: str = ""


def invoke_with_failover(
    candidates: Sequence[C],
    attempt: Callable[[C, str], AttemptResult[T]],
    *,
    max_retries: int,
    describe: Callable[[C], str],
    recommendation: str,
    error: Callable[[str], Exception],
) -> T:
    """Return the first valid result across ``candidates``, failing over on provider faults.

    For each candidate in order, call ``attempt(candidate, feedback)`` — ``feedback`` starts
    empty and is replaced by the previous attempt's ``feedback`` on a ``RETRY``. ``OK``
    returns its ``value``; ``RETRY`` re-runs the SAME candidate up to ``max_retries`` extra
    times; ``FAILOVER`` (or exhausting the retries) advances to the next candidate. When all
    candidates are exhausted, raise ``error(msg)`` where ``msg`` names every candidate's
    failure (via ``describe``) and ends with ``recommendation``.

    ``max_retries`` is the number of EXTRA attempts per candidate after the first (so a
    candidate gets ``max_retries + 1`` total attempts before failover)."""
    if not candidates:
        raise error(f"no candidates available — {recommendation}")

    attributions: list[str] = []
    for cand in candidates:
        feedback = ""
        note = "no attempts made"
        for _ in range(max_retries + 1):
            res = attempt(cand, feedback)
            if res.kind == OK:
                return cast(T, res.value)
            if res.kind == FAILOVER:
                attributions.append(f"{describe(cand)}: {res.attribution}")
                break
            # RETRY — same candidate, thread feedback into the next attempt.
            note = res.attribution or "quality failure"
            feedback = res.feedback
        else:
            # Retries exhausted without OK or explicit FAILOVER → advance to next.
            attributions.append(f"{describe(cand)}: {note}")

    raise error(
        "all candidates exhausted — " + "; ".join(attributions) + f" — {recommendation}"
    )
