#!/usr/bin/env python3
# @covers: dogfood
"""Dogfood gate — asserts observable routing effects through the real selection path.

GROUND: sets up a temporary config (models.json + pools.json) with real model
entries, then runs the production ``load_pools`` → ``choose_from_pool`` path and
asserts every observable surface an operator would inspect: pool ordering,
selection decisions, exhaustion behaviour, and code-safe filtering. This is NOT
a mocked router returning a mocked pool — every function in the call chain is the
production code. A zero-provider / empty-catalog case runs first and is RED by
construction (NON-VACUOUS). The gate FAILS when an effect is absent, not merely
when code throws.

Exit 0 when every asserted effect matches; exit non-zero on any mismatch.
Emits WORK-UNITS: <n> for the gate runner contract.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.gate_contract import emit_work_units  # noqa: E402
from charon.pools import PoolConfigError, choose_from_pool, load_pools  # noqa: E402

_MODELS = {
    "openrouter/qwen3-coder": {
        "agent": "opencode", "cost_tier": "free",
        "code_safe": False, "free": True,
    },
    "nano-gpt/kimi-k2": {
        "agent": "opencode", "cost_tier": "flat",
        "cost_input": 0.0000001, "cost_output": 0.0000001,
        "code_safe": True, "free": False,
    },
    "opencode-go/glm": {
        "agent": "opencode", "cost_tier": "flat",
        "cost_input": 0.0000003, "cost_output": 0.0000003,
        "code_safe": True, "free": False,
    },
    "zen/claude-opus": {
        "agent": "claude-code", "cost_tier": "premium",
        "cost_input": 0.000001, "cost_output": 0.000003,
        "code_safe": True, "free": False,
    },
}
_POOLS = {"coder": ["zen/claude-opus", "openrouter/qwen3-coder",
                    "opencode-go/glm", "nano-gpt/kimi-k2"]}

_FINDINGS: list[tuple[str, str]] = []  # (label, detail)


def _fail(label: str, detail: str) -> None:
    _FINDINGS.append((label, detail))


def _check(condition: bool, label: str, detail: str = "") -> None:
    if not condition:
        _fail(label, detail)


def _write_config(d: Path, models: dict | None = None,
                  pools: dict | None = None) -> None:
    (d / "models.json").write_text(json.dumps(models if models is not None
                                              else _MODELS))
    (d / "pools.json").write_text(json.dumps(pools if pools is not None
                                             else _POOLS))


def run() -> int:
    """Run the dogfood gate and return exit code."""
    units = 0

    # ── NON-VACUOUS: empty catalog is RED ──
    with tempfile.TemporaryDirectory() as td:
        empty_dir = Path(td) / "empty"
        empty_dir.mkdir()
        pools = load_pools(empty_dir)
        units += 1
        _check(
            pools == {},
            "VACUUM-PROOF-EMPTY-CATALOG",
            f"empty config dir returned pools={pools!r}, expected {{}} — "
            "a zero-model catalog must not silently pass",
        )

        # empty models.json with a pools.json naming nonexistent models → LOUD error
        (empty_dir / "models.json").write_text("{}")
        (empty_dir / "pools.json").write_text(json.dumps({"a": ["nonesuch"]}))
        units += 1
        try:
            load_pools(empty_dir)
            _fail(
                "VACUUM-PROOF-MISSING-MODEL",
                "pool named a model absent from models.json but load_pools "
                "did not raise — a gate that swallows misconfiguration is "
                "the theater this ticket exists to end",
            )
        except PoolConfigError:
            pass  # expected: loud error on broken config

    # ── REAL CONFIG ── SELECTION PATH ──
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _write_config(d)

        # 1. Pool loading — the surface an operator inspects via /charon/status
        pools = load_pools(d)
        units += 1
        _check(
            "coder" in pools,
            "POOL-LOADING-ROLE",
            "pool 'coder' not found in loaded pools — the role the operator "
            "configured is absent from the routing surface",
        )
        _check(
            len(pools["coder"]) == 4,
            "POOL-LOADING-COUNT",
            f"expected 4 pool entries, got {len(pools.get('coder', []))} — "
            "models configured in the catalog are not appearing in the pool",
        )

        # 2. Pool ordering — free-first, cheapest-first (ADR-0016)
        pool = pools["coder"]
        order = [e.model for e in pool]
        unit = 1  # count one unit per assertion within the pool path
        _check(
            order[0].endswith("qwen3-coder") if order else False,
            "POOL-ORDER-FREE-FIRST",
            f"free model not first in pool order: {order} — the operator's "
            "free-first policy is not observable in the routing surface",
        )
        _check(
            order == ["openrouter/qwen3-coder", "nano-gpt/kimi-k2",
                      "opencode-go/glm", "zen/claude-opus"],
            "POOL-ORDER-COST-RANK",
            f"pool order not free-first, cheapest-first: {order}",
        )

        # 3. Routing decision — which provider/model is SELECTED
        first = choose_from_pool(pool)
        units += 1
        _check(
            first.model == "openrouter/qwen3-coder",
            "ROUTE-FREE-WINS",
            f"first choice was {first.model!r}, expected free model — "
            "the demand-routed selection did not pick the free model",
        )
        _check(
            first.agent == "opencode",
            "ROUTE-AGENT",
            f"first choice agent={first.agent!r}, expected 'opencode' — "
            "the selected provider agent is wrong",
        )

        # 4. Failover — H6: exhaust one, get the next
        second = choose_from_pool(pool, exclude={first.key})
        units += 1
        _check(
            second.model == "nano-gpt/kimi-k2",
            "ROUTE-FAILOVER-H6",
            f"failover after exclude got {second.model!r}, expected "
            "'nano-gpt/kimi-k2' — cross-model failover is not advancing",
        )

        third = choose_from_pool(pool, exclude={first.key, second.key})
        units += 1
        _check(
            third.model == "opencode-go/glm",
            "ROUTE-FAILOVER-CHAIN",
            f"third choice was {third.model!r}, expected 'opencode-go/glm' — "
            "failover chain not walking the full pool",
        )

        # 5. Exhaustion — the observable effect of a fully-dry pool
        allkeys = {e.key for e in pool}
        units += 1
        try:
            choose_from_pool(pool, exclude=allkeys)
            _fail(
                "ROUTE-EXHAUSTED",
                "pool exhausted all entries but did not raise — a silent "
                "wrong choice (an exhausted pool) would go unreported",
            )
        except RuntimeError:
            pass  # expected: "pool exhausted"

        # 6. Code-safe filtering — observable on the routing surface
        safe = choose_from_pool(pool, code_safe_only=True)
        units += 1
        _check(
            safe.model == "nano-gpt/kimi-k2",
            "ROUTE-CODE-SAFE",
            f"code_safe_only picked {safe.model!r}, expected 'nano-gpt/kimi-k2' "
            "(the first code-safe entry, skipping the unsafe free model) — "
            "code-safe filtering is broken",
        )
        _check(
            safe.code_safe is True,
            "ROUTE-CODE-SAFE-FLAG",
            f"code_safe_only returned entry with code_safe={safe.code_safe}",
        )

        # 7. Cost-class priority — observable on the metering surface
        # (the cost_class_priority axis is checked by verifying the sort key)
        cost_class_models = {
            "a-free": {"agent": "opencode", "free": True, "cost_tier": "free"},
            "a-metered": {
                "agent": "opencode", "cost_tier": "flat",
                "cost_input": 0.000001, "cost_output": 0.000003,
                "cost_class": "metered", "free": False,
            },
            "a-prepaid": {
                "agent": "opencode", "cost_tier": "flat",
                "cost_input": 0.000001, "cost_output": 0.000003,
                "cost_class": "prepaid", "free": False,
            },
        }
        (d / "models.json").write_text(json.dumps(cost_class_models))
        (d / "pools.json").write_text(json.dumps(
            {"coder": ["a-metered", "a-prepaid", "a-free"]}))
        cc_pools = load_pools(d)
        units += 1
        cc_order = [e.model for e in cc_pools["coder"]]
        _check(
            cc_order[0] == "a-free",
            "COST-CLASS-FREE-FIRST",
            f"cost-class pool order: {cc_order} — free model not first",
        )
        # prepaid (priority 3) before metered (priority 4) at same cost
        _check(
            "a-prepaid" in cc_order and "a-metered" in cc_order
            and cc_order.index("a-prepaid") < cc_order.index("a-metered"),
            "COST-CLASS-PRIORITY",
            f"cost-class pool order: {cc_order} — prepaid not before metered "
            "at the same cost rank",
        )

    # ── REPORT ──
    for label, detail in _FINDINGS:
        print(f"  DOGFOOD-RED: [{label}] {detail}", file=sys.stderr)
    emit_work_units(units)

    if _FINDINGS:
        print(f"\n  DOGFOOD-GATE: {len(_FINDINGS)} assertion(s) failed", file=sys.stderr)
        return 1

    print("  DOGFOOD-GATE: all routing assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
