# INERT-INSTANCE-DETECT — Teach detector the instance-inert pattern

## Problem

`check_inert_code.py` wraps the KSF `inert_code` detector, which builds an AST
call graph and checks symbol reachability from entrypoints. A module-level class
like `RequestInspector` that is **constructed** (`RequestInspector(...)`) appears
"reachable" even though its **instance methods are never invoked**. Six gateway
modules (RequestInspector, SessionAffinity, Observability, SpeculativeExecutor,
ConsensusRouter, VirtualKeyManager) are constructed in `gateway.py:_MODULE_SPECS`,
stored on `GatewayProxyServer`, and have **zero invocation sites** — but the
detector prints `check_inert_code: OK` because their constructors are reachable.

This means WORK-GATE-UNIVERSAL's Gate B (which runs this detector) would certify
inert code as fully wired.

## Solution

### Detector fix (`tools/check_inert_code.py`)

Added `find_instance_inert_classes()`, a second AST pass after the KSF detector:

1. Parse every production source file and collect all module-level class
   definitions + their public method names.
2. Find which classes are constructed (`ClassName(...)` appears as a call target).
3. Collect every dotted method call `something.method(...)` whose receiver is
   **not a module-level import name** (i.e., is plausibly an instance-variable
   call rather than a module-level function call).
4. A class is **instance-inert** iff it IS constructed AND none of its public
   instance-method names appear in the instance-variable call set.

The check is intentionally conservative: method-name collisions with unrelated
classes prevent flagging (false negatives tolerated over false positives).

### Integration

- `check()` now returns the union of KSF-detected dead symbols and
  instance-inert classes as `all_dead_symbols`.
- Instance-inert entries in `inert-code-disposition.json` carry
  `"inert_class": true` — the stale-entry warning skips these, since they are a
  separate classification from KSF-detected dead symbols.
- Added `retire` to the valid disposition regex.

## Scope split (per ticket)

(a) **Detector fix (mandatory)** — ships in this ticket.
(b) **Wire-or-remove per module (operator decision)** — dispositioned as `wire`
    for all 6 with rationale. The actual wiring is downstream work.

## Dispositions

All 6 modules dispositioned as `wire` with detailed rationale (what wiring would
cost, what the module is for). Chosen over `retire` because each module
represents deliberate functionality that was designed and built; the cost of
wiring is moderate and the benefit (routing hints, session pinning,
observability, speculative execution, consensus, virtual keys) is clear.

## Files changed

| File | Change |
|---|---|
| `tools/check_inert_code.py` | Added `find_instance_inert_classes()`, updated `check()`, `main()`, docstring |
| `tools/inert-code-disposition.json` | Added 6 gateway module entries with `wire` disposition |
| `tests/test_inert_instance_detect.py` | New: 3 FAIL-ON-REVERT test classes |

## Evidence

- Synthetic fixture with constructed-but-never-invoked class → RED
- Same fixture with invocation added → GREEN
- All 6 modules present in disposition file with valid wire|retire + non-empty reason
- Real codebase still passes with existing 65 dead symbols + 6 new disposed entries
