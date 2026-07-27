#!/usr/bin/env python3
# @covers: dogfood
"""Dogfood gate — asserts observable routing effects through the real selection path.

GROUND: drives two production paths:

  (1) ``CatalogCache.registry_and_pool_map`` — the catalog-refresh folding path
      the gateway uses for discovered advertised ids. The fold's observable
      effect lives here: a variant spelling of a model that has a base pool
      MUST resolve to the SAME routable pool id with BOTH members present, and
      there MUST be no orphan variant-only pool. This is the path that
      catches a fp4-fold regression (the 2026-07-26 miss): a real advertised
      id like ``MiniMaxAI/MiniMax-M2.5-FP4`` plus its base
      ``MiniMaxAI/MiniMax-M2.5`` MUST collapse to one routable pool
      ``minimax-m2.5`` with both members. Same shape for the
      ``:low|:medium|:high|:max`` capacity tier family and the aistudio
      ``-preview`` alias.

  (2) ``load_pools`` → ``choose_from_pool`` — the operator's static-pool path,
      asserting pool ordering, failover, exhaustion, and code-safe filtering
      on a real config (so a zero-catalog and a dry pool are RED by
      construction; NON-VACUOUS).

The gate FAILS when an effect is absent, not merely when code throws.

Exit 0 when every asserted effect matches; exit non-zero on any mismatch.
Emits WORK-UNITS: <n> for the gate runner contract.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
# Put the worktree's src/ at the FRONT of sys.path so `import charon` resolves
# to THIS checkout's src/charon/proxy.py, not whatever `charon` an editable
# install or system .pth file made shadow it. Without this, a gate run inside
# a git worktree silently exercises a different tree's fold logic — the exact
# defect this ticket exists to catch (see tools/run_gate.py for the same
# reasoning applied to the gate runner).
_REPO_SRC = _REPO_ROOT / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.gate_contract import emit_work_units  # noqa: E402

from charon.pools import PoolConfigError, choose_from_pool, load_pools  # noqa: E402
from charon.routing_policy.catalog_refresh import CatalogCache, ProviderEntry  # noqa: E402

_FINDINGS: list[tuple[str, str]] = []


def _fail(label: str, detail: str) -> None:
    _FINDINGS.append((label, detail))


def _check(condition: bool, label: str, detail: str = "") -> None:
    if not condition:
        _fail(label, detail)


def _put(cache: CatalogCache, provider: str,
         advertised_ids: list[str]) -> None:
    """Seed the catalog cache with one ProviderEntry per advertised id."""
    entries = {f"{provider}/{raw}":
               ProviderEntry(provider=provider, upstream_model=raw)
               for raw in advertised_ids}
    cache.put(provider, entries)


def _assert_catalog_fold(cache: CatalogCache) -> int:
    """Assert the catalog-refresh fold's observable effect on pool_map. This is
    RED-PROOF #1 for the 2026-07-26 miss: the fp4 fold MUST collapse the fp4
    variant and its base into one routable pool with both members, and there
    MUST be no orphan fp4-only pool. Same shape for the tier family and the
    preview alias.

    Returns the count of work units exercised.
    """
    units = 0

    registry, pool_map = cache.registry_and_pool_map()
    units += 1

    # ── 1. fp4 fold (the 2026-07-26 acceptance test) ──
    # Discriminator: with the fold intact, the fp4 variant normalizes to the
    # BASE id ('minimax-m2.5') and joins the base pool. With the fold reverted,
    # the variant normalizes to 'minimax-m2.5-fp4' and forms its own orphan
    # pool; the base pool then holds only the base member.
    fp4_pool = pool_map.get("minimax-m2.5", [])
    _check(
        len(fp4_pool) >= 2,
        "FOLD-FP4-BOTH-MEMBERS",
        f"base 'minimax-m2.5' pool has {len(fp4_pool)} member(s); expected "
        ">=2 (the fp4 variant AND the base) — one of the two advertised ids "
        "never joined the pool, so the fp4 fold did not collapse them together",
    )
    _check(
        "minimax-m2.5-fp4" not in pool_map,
        "FOLD-FP4-NO-ORPHAN",
        f"orphan pool 'minimax-m2.5-fp4' exists in pool_map — the fp4 fold "
        "regressed; the variant normalized to its OWN id instead of the base, "
        "so a funded provider advertised as MiniMaxAI/MiniMax-M2.5-FP4 will not "
        "reach the base pool. Pool-map keys seen: "
        f"{sorted(k for k in pool_map if 'm2.5' in k)}",
    )

    # ── 2. Capacity tiers (:low|:medium|:high|:max) ──
    # Discriminator: with the tier regex intact, every tier normalizes to the
    # base id 'claude-opus-4' AND the base pool exists with all 4 tier members.
    # With the regex reverted, no 'claude-opus-4' base pool exists at all —
    # only the raw-id orphan pools.
    tier_pool = pool_map.get("claude-opus-4", [])
    _check(
        "claude-opus-4" in pool_map and len(tier_pool) == 4,
        "FOLD-CAPACITY-TIERS",
        f"'claude-opus-4' base pool expected to exist with 4 tier members; "
        f"got keys={sorted(k for k in pool_map if 'claude' in k)} — the tier "
        "fold regressed; a request for the base id cannot reach any "
        "tier-deployed leg",
    )

    # ── 3. aistudio -preview alias ──
    # Discriminator: with the alias intact, gemini-3-pro-preview normalizes to
    # 'gemini-3-pro' and joins the base pool. With the alias removed, the
    # -preview member is missing from the base pool.
    preview_pool = pool_map.get("gemini-3-pro", [])
    _check(
        len(preview_pool) >= 2,
        "FOLD-PREVIEW-ALIAS",
        f"gemini-3-pro pool has {len(preview_pool)} member(s); expected >=2 "
        "(-preview AND the base id) — the alias fold did not collapse them; "
        f"the aistudio endpoint loses its only path to the model. Chain: "
        f"{preview_pool}",
    )

    # ── 4. SELECTION PATH — load_pools/choose_from_pool on the collapsed fp4
    #       pool. With the fold intact, BOTH advertised ids are in the
    #       'minimax-m2.5' chain as registered models, so an operator who
    #       lists the MEMBER ids under a pool named 'fp4-fold' sees a 2-entry
    #       pool. With the fold broken, only one member is in the chain and
    #       this assertion goes RED with the fold's effect named.
    fp4_member_ids = pool_map.get("minimax-m2.5", [])
    fp4_models = {
        mid: {"agent": "opencode", "cost_tier": "flat",
              "cost_input": 0.000001, "cost_output": 0.000003,
              "code_safe": True, "free": False}
        for mid in fp4_member_ids
    }
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "models.json").write_text(json.dumps(fp4_models))
        (d / "pools.json").write_text(json.dumps(
            {"fp4-fold": list(fp4_models.keys())}))
        fp4_loaded = load_pools(d).get("fp4-fold", [])
        units += 1
        _check(
            len(fp4_loaded) >= 2,
            "POOL-FP4-FOLD-HAS-BOTH",
            f"collapsed fp4 pool has {len(fp4_loaded)} member(s); expected "
            ">=2 (the catalog fold should have placed both advertised ids "
            "under 'minimax-m2.5') — the fold did not produce a 2-member pool",
        )
        if len(fp4_loaded) >= 2:
            units += 1
            second = choose_from_pool(
                fp4_loaded, exclude={fp4_loaded[0].key})
            _check(
                second.key != fp4_loaded[0].key,
                "ROUTE-FP4-FAILOVER",
                f"failover after excluding first got {second.model!r}; "
                "expected the OTHER collapsed member — the fold joined them "
                "but the second leg is no longer reachable",
            )

            allkeys = {e.key for e in fp4_loaded}
            units += 1
            try:
                choose_from_pool(fp4_loaded, exclude=allkeys)
                _fail(
                    "ROUTE-COLLAPSED-EXHAUSTED",
                    "collapsed fp4 pool exhausted but did not raise — a silent "
                    "wrong choice from a dry folded pool would go unreported",
                )
            except RuntimeError:
                pass  # expected: loud error on dry pool

    return units


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

    # ── REAL CONFIG ── CATALOG FOLD (the 2026-07-26 acceptance path) ──
    cache = CatalogCache()
    _put(cache, "minimax",
         ["MiniMaxAI/MiniMax-M2.5-FP4", "MiniMaxAI/MiniMax-M2.5"])
    _put(cache, "anthropic",
         ["claude-opus-4:low", "claude-opus-4:medium",
          "claude-opus-4:high", "claude-opus-4:max"])
    _put(cache, "aistudio",
         ["gemini-3-pro-preview", "gemini-3-pro"])
    units += _assert_catalog_fold(cache)

    # ── REAL CONFIG ── OPERATOR POOL (pool ordering, failover, code-safe) ──
    op_models = {
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
    op_pools = {"coder": ["zen/claude-opus", "openrouter/qwen3-coder",
                          "opencode-go/glm", "nano-gpt/kimi-k2"]}

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "models.json").write_text(json.dumps(op_models))
        (d / "pools.json").write_text(json.dumps(op_pools))

        loaded = load_pools(d)
        units += 1
        _check(
            "coder" in loaded,
            "POOL-LOADING-ROLE",
            "pool 'coder' not found in loaded pools — the role the operator "
            "configured is absent from the routing surface",
        )
        _check(
            len(loaded["coder"]) == 4,
            "POOL-LOADING-COUNT",
            f"expected 4 pool entries, got {len(loaded.get('coder', []))} — "
            "models configured in the catalog are not appearing in the pool",
        )

        pool = loaded["coder"]
        order = [e.model for e in pool]
        units += 1
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
            pass

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

    # ── REPORT ──
    for label, detail in _FINDINGS:
        print(f"  DOGFOOD-RED: [{label}] {detail}", file=sys.stderr)
    emit_work_units(units)

    if _FINDINGS:
        print(f"\n  DOGFOOD-GATE: {len(_FINDINGS)} assertion(s) failed",
              file=sys.stderr)
        return 1

    print("  DOGFOOD-GATE: all routing assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())