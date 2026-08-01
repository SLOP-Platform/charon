#!/usr/bin/env python3
# @covers: catalog-persist
"""CATALOG-PERSIST-SAFETY gate — the catalog write-back must never be able to
empty ``models.json``.

``CatalogRefresher._persist_unlocked`` does a read-modify-write of the ONE file
every route is built from. If a degraded upstream can drive that write to an
empty (or all-disabled) catalog, every route on the gateway dies at once — the
single highest-blast-radius failure in the router.

This gate is BEHAVIOURAL, not a source grep: it drives the real
:class:`CatalogRefresher` against a throwaway state dir with the three degraded
upstreams that actually occur in production, and fails if the on-disk catalog
is damaged. It runs independently of the unit tests, so deleting
``tests/test_catalog_refresh_persist.py`` does not silently retire the
invariant.

Attacks exercised (each one was a REAL defect caught in review):
  1. provider answers HTTP 200 with an EMPTY ``data: []`` (lapsed key /
     downgraded plan / soft rate-limit) → must NOT withdraw its catalog.
  2. existing ``models.json`` is unparseable (torn write) → must REFUSE to
     write rather than replace it with ``{}``.
  3. every provider poll raises → must not create an empty catalog.
  4. an auto-withdrawal must be REVERSIBLE — a model that comes back must
     re-enable without a hand edit.

Exit 0 = green, 1 = red (with the damaged catalog printed).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from charon.routing_policy.catalog_refresh import CatalogRefresher  # noqa: E402


def _catalog(d: Path) -> dict:
    p = d / "models.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _live(cat: dict) -> set[str]:
    """Ids that would still be routable (gateway drops ``enabled: false``)."""
    return {k for k, v in cat.items()
            if not (isinstance(v, dict) and v.get("enabled") is False)}


def _attack_empty_200(problems: list[str]) -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        calls = {"n": 0}

        def poll(name: str, overrides: dict | None) -> list[dict]:
            calls["n"] += 1
            return ([{"id": "alpha"}, {"id": "beta"}] if calls["n"] == 1 else [])

        r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=d,
                             list_models_fn=poll)
        r.refresh_now()
        before = _live(_catalog(d))
        r.refresh_now()
        after = _live(_catalog(d))
        if after != before:
            problems.append(
                f"empty-200 poll withdrew models: {sorted(before)} -> {sorted(after)}")


def _attack_corrupt_existing(problems: list[str]) -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        corrupt = '{"hand-tuned": {"provider": "p", "upstream_mo'
        (d / "models.json").write_text(corrupt)
        r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=d,
                             list_models_fn=lambda n, o: [{"id": "found"}])
        r.refresh_now()
        if (d / "models.json").read_text() != corrupt:
            problems.append(
                "unparseable models.json was OVERWRITTEN instead of preserved")


def _attack_total_failure(problems: list[str]) -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)

        def boom(name: str, overrides: dict | None) -> list[dict]:
            raise RuntimeError("connection refused")

        r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=d,
                             list_models_fn=boom)
        r.refresh_now()
        if _catalog(d) == {} and (d / "models.json").exists():
            problems.append("total provider failure wrote an EMPTY models.json")


def _attack_withdrawal_is_reversible(problems: list[str]) -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        seq = [[{"id": "rot"}], [{"id": "other"}], [{"id": "rot"}]]
        calls = {"n": 0}

        def poll(name: str, overrides: dict | None) -> list[dict]:
            out = seq[min(calls["n"], len(seq) - 1)]
            calls["n"] += 1
            return list(out)

        r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=d,
                             list_models_fn=poll)
        r.refresh_now()
        r.refresh_now()
        withdrawn = _catalog(d).get("rot", {})
        if withdrawn.get("enabled") is not False:
            problems.append("a model absent from /models was left routable")
        if withdrawn.get("refresh_disabled") is True:
            problems.append(
                "auto-withdrawal set refresh_disabled (operator opt-out flag) "
                "— the withdrawal is permanent and needs a hand edit to undo")
        r.refresh_now()
        back = _catalog(d).get("rot", {})
        if back.get("enabled") is not True:
            problems.append(
                "a re-advertised model did NOT come back automatically")


def main() -> int:
    problems: list[str] = []
    attacks = (_attack_empty_200, _attack_corrupt_existing,
               _attack_total_failure, _attack_withdrawal_is_reversible)
    run = 0
    for attack in attacks:
        try:
            attack(problems)
        except Exception as exc:  # noqa: BLE001 — a crashing attack is a RED
            problems.append(f"{attack.__name__} raised {type(exc).__name__}: {exc}")
        run += 1

    # Gate contract: report the count actually examined, so a gate that silently
    # stops scanning is distinguishable from one that passed.
    print(f"WORK-UNITS: {run}")

    if problems:
        print("check_catalog_persist_safety: catalog write-back can DAMAGE "
              "models.json:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("check_catalog_persist_safety: OK "
          "(4 degraded-upstream attacks, catalog intact)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
