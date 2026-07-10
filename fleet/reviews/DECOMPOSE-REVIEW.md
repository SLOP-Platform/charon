# ADVERSARIAL REVIEW — GATEWAY-ROUTING-DECOMPOSE (Wave 1)

**Branch:** `feat/gateway-routing-decompose`
**Commit:** `4e0c89acfd911c74aff8ba06ca8ad2d35234c77c`
**Reviewer:** adversarial session

## VERDICT: MERGE-WITH-FIXES — LOW confidence on seam integrity

The extraction is behavior-preserving for routing decisions. All extracted functions are byte-for-byte identical to their master counterparts. One seam-integrity bug makes the package's `__all__` a lie. No blast-radius issues. Fix is trivial.

---

## FINDINGS

### 1. SEAM: `__all__` lists 7 symbols NOT importable at package level

**Severity: MEDIUM**
**File:** `src/charon/routing_policy/__init__.py:30-45`

`__all__` declares `CapabilityMatrix`, `ModelCapability`, `Grade`, `WorkClass`, `DrainPolicy`, `PoolsSimplificationPolicy`, and `SpillPolicy` — but NONE of them are imported into `__init__.py`. The only imports are:

```python
from .base import DefaultPolicy, Policy
from .cost_rank import derived_cost_rank
```

**Failing input:**
```python
from charon.routing_policy import DrainPolicy    # ImportError
from charon.routing_policy import CapabilityMatrix  # ImportError
```

These are accessible only via sub-module paths (`routing_policy.drain.DrainPolicy`). The existing test `test_routing_policy_exports_public_api` only checks the symbols that ARE actually importable, so it passes despite the mismatch.

**Fix:** Either add the missing imports to `__init__.py`:

```python
from .drain import DrainPolicy
from .matrix import CapabilityMatrix, ModelCapability, Grade, WorkClass
from .pools import PoolsSimplificationPolicy
from .spill import SpillPolicy
```

OR remove them from `__all__` until Wave 2 wires them in.

**Why it matters:** Wave 2 authors will try `from charon.routing_policy import DrainPolicy` and hit ImportError. This is a self-inflicted seam failure.

---

### 2. Minor: `os` + sub-module names leak into package namespace

**Severity: LOW**
**File:** `src/charon/routing_policy/__init__.py:21`

The top-level `import os` (needed by `route_from_spec`) exposes `os` as `routing_policy.os`. Also, the dot-relative sub-module imports (`from .base import ...`, `from .cost_rank import ...`) expose `routing_policy.base` and `routing_policy.cost_rank` as attributes. These are implementation-detail leaks. Not a behavioral issue, but `os` particularly shouldn't be in the public namespace of a routing-policy package.

**Fix:** Prefix with `_` if unwanted in `__all__`, or use `import os as _os`.

---

### 3. BEHAVIOR PRESERVATION — VERIFIED

**Each extracted function is logic-identical to its master counterpart:**

| Master function | Branch function | Verdict |
|---|---|---|
| `_route_from_spec` (gateway.py:93-117) | `route_from_spec` (routing_policy/__init__.py:48-77) | Byte-for-byte identical |
| `_build_routes_and_pools` (gateway.py:120-175) | `build_routes_and_pools` (routing_policy/__init__.py:80-131) | Byte-for-byte identical |
| `_tier_pools` (gateway.py:178-192) | `tier_pools` (routing_policy/__init__.py:134-146) | Identical (import moved from call-time to module-level; `config` has no cycle with routing_policy) |
| Inline fallback-chain block (gateway.py:254-272) | `build_fallback_chain` (routing_policy/__init__.py:149-183) | Identical logic; shallow `dict(pools)` copy is behavior-preserving — no old callers held a reference to the pre-fallback pools dict |
| `derived_cost_rank` (pools.py:62-76) | `derived_cost_rank` (routing_policy/cost_rank.py:9-23) | Byte-for-byte identical |

**Proof:** 35 existing routing/gateway tests pass unchanged (test_gateway.py, test_agent_launch_routing.py, test_gateway_tiers.py). `test_sr6_derived_rank_orders_by_blended_cost` confirms the cost-rank sorted pool ordering is preserved (free-first, then cheapest blended cost).

**No dead/duplicated logic:** Old inline functions completely removed from `gateway.py`. Old `derived_cost_rank` definition completely removed from `pools.py`. No silent divergence risk.

---

### 4. FAIL-ON-REVERT — PARTIAL

**6 of 7 tests would genuinely turn RED on revert:**

| Test | Revert behavior | Verdict |
|---|---|---|
| `test_routing_policy_is_package` | Would fail — package collapsed to single file | TRUE fail-on-revert |
| `test_routing_policy_has_required_submodules` | Would fail — sub-modules missing | TRUE |
| `test_gateway_delegates_to_routing_policy` | Uses `is` identity check on function objects; revert would make them different objects | TRUE |
| `test_derived_cost_rank_moved_to_routing_policy` | Uses `is` identity check; local re-definition in pools.py would break it | TRUE |
| `test_routing_policy_rejects_single_file_import` | Would fail — `__file__` assertions would fail | TRUE |
| `test_gateway_load_config_calls_routing_policy` | Would still pass if functions were moved back intact — it only tests integration behavior | FALSE fail-on-revert |
| `test_routing_policy_exports_public_api` | Only checks successfully-exported symbols; does not catch the `__all__` mismatch | FALSE fail-on-revert (but not the test's fault) |

**Bottom line:** `test_gateway_load_config_calls_routing_policy` passes regardless of where the functions live, so it doesn't detect revert. This is acceptable — it's an integration smoke test, not a revert gate. The 5 identity/structure tests provide genuine revert detection.

---

### 5. BLAST RADIUS — CLEAN

**All backward-compatible re-exports verified:**

- `gateway._build_routes_and_pools` — re-export from `routing_policy.build_routes_and_pools` (gateway.py:47)
- `gateway._route_from_spec` — re-export from `routing_policy.route_from_spec` (gateway.py:48)
- `gateway._tier_pools` — re-export from `routing_policy.tier_pools` (gateway.py:49)
- `pools.derived_cost_rank` — re-export from `routing_policy.cost_rank.derived_cost_rank` (pools.py:20)

**All existing importers work without changes:**
- `tests/test_proxy_server.py:1174` — `from charon.gateway import _build_routes_and_pools`
- `tests/test_agent_launch_routing.py:23` — `from charon.gateway import _build_routes_and_pools`
- `tests/test_gateway.py:455` — `from charon.pools import derived_cost_rank`
- `cli.py:792` — `from .pools import derived_cost_rank`

**No import cycles:** `routing_policy` imports `charon.config` and `charon.providers` — neither imports `routing_policy` or `gateway`. `gateway` imports `routing_policy`, but `routing_policy` does not import `gateway`.

---

## SUMMARY

| Criterion | Result |
|---|---|
| Behavior preservation | YES — routing decisions identical |
| Seam integrity | FAIL — `__all__` lies about 7 symbols |
| Dead/duplicated logic | CLEAN — old code removed everywhere |
| Tests fail-on-revert | MOSTLY — 5/7 genuine; 2 are soft |
| Blast radius | CLEAN — all callers preserved; no cycles |
| Import cycle risk | NONE |

**Recommended action before merge:** Fix `__all__` in `routing_policy/__init__.py` — either import the 7 missing symbols or remove them from `__all__`. The package is otherwise safe.
