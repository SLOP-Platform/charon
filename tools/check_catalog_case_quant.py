#!/usr/bin/env python3
"""Catalog case/quant-mismatch detector (mechanizes directive #30).

The pseudo-success compare (`proxy._normalize_model_id`) is case- and
quant-insensitive: a provider echoing `Kimi-K2.7-Code` / `GLM-5.2-FP8` for pool
`kimi-k2.7-code` / `glm-5.2` is the SAME model, NOT a silent downgrade. That
tolerance is a live-response safety net — it must NOT become an excuse for the
CURATED catalog to carry non-canonical ids. Two catalog entries that differ only
by case or a quant suffix (`glm-5.2` and `GLM-5.2-FP8`) collapse to one model
after normalization: a duplicate the tier menu should never ship. And a lone
non-canonical id (`Kimi-K2.7-Code`) is a latent mismatch waiting to confuse any
surface-form compare that has not yet been normalized.

This detector enforces that every catalog id is ALREADY canonical — the exact
form `_normalize_model_id` folds to (final path segment, lower-cased, quant
stripped) — and that no two entries collide under normalization. It is pure over
its input, so a test can seed a mismatch and assert it is flagged.

Exit 0 = clean, exit 1 = at least one mismatch (usable as a gate step).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from collections.abc import Iterable

# stdlib-only; imported for the shared normalization primitive (single source of
# truth with the live compare, so the detector can never drift from proxy.py).
from charon.proxy import _QUANT_SUFFIX, _normalize_model_id


def _is_non_canonical(model_id: str) -> str:
    """Return a human reason the id is NOT canonical, or "" if it is clean.

    Canonical = already equal to its normalized form: bare final segment,
    lower-case, no trailing quant suffix. We report the SPECIFIC defect (case vs
    quant vs namespace) so a catalog author can fix it directly."""
    seg = model_id.rsplit("/", 1)[-1]
    reasons: list[str] = []
    if "/" in model_id:
        reasons.append("carries a provider/namespace prefix")
    if seg.lower() != seg:
        reasons.append("has upper-case characters")
    if _QUANT_SUFFIX.search(seg.lower()):
        reasons.append("carries a quantization suffix (-fp8/-bf16/-q4…/-int8)")
    return "; ".join(reasons)


def find_mismatches(model_ids: Iterable[str]) -> list[str]:
    """Return one message per catalog defect: non-canonical ids AND
    normalization collisions (distinct surface ids folding to one model)."""
    ids = list(model_ids)
    problems: list[str] = []

    for mid in ids:
        reason = _is_non_canonical(mid)
        if reason:
            problems.append(
                f"non-canonical catalog id {mid!r}: {reason} "
                f"(canonical: {_normalize_model_id(mid)!r})")

    collisions: dict[str, list[str]] = defaultdict(list)
    for mid in ids:
        collisions[_normalize_model_id(mid)].append(mid)
    for norm, group in collisions.items():
        if len(group) > 1:
            problems.append(
                f"catalog collision: {group!r} all normalize to {norm!r} "
                f"— same model shipped under {len(group)} surface ids")

    return problems


def _catalog_ids() -> list[str]:
    """The live curated catalog ids (import kept local so `--help` / a seeded
    unit test never depends on the catalog module loading cleanly)."""
    from charon.model_catalog import catalog

    return [e.id for e in catalog()]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        ids = _catalog_ids()
    except Exception as exc:  # noqa: BLE001 — surface the load failure, do not mask
        print(f"check_catalog_case_quant: could not load catalog: {exc}",
              file=sys.stderr)
        return 2

    problems = find_mismatches(ids)
    if problems:
        print("check_catalog_case_quant: catalog case/quant mismatch(es):",
              file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"check_catalog_case_quant: OK ({len(ids)} ids canonical, no collisions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
