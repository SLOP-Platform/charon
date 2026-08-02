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

---

## 2026-07-24 — disposition executed: five retired, one kept for wiring

The `wire`-for-all-six disposition above was re-litigated against the actual
board and reversed for five of the six. The wiring map named "downstream owners"
R44 and R45; neither exists as a ticket (live, parked or archived), and neither
is a consumer even by scope — R44 is a test gate, R45 is a start-up check that
would *report* these modules as inert. Under the operator's default (retire
unless a real planned consumer exists), five retire.

| Module | Verdict | Why |
|---|---|---|
| `RequestInspector` | **kept, to be wired** | RFL-3 (parked, not archived) specifies `srv.request_inspector.inspect()`; 6 of 8 dogfood attempts independently built that call site. Still constructed, still on the roster. **The wiring is RFL-3's work, not this change's.** |
| `Observability` | retired | Name-collides with the gateway's real, wired `srv.observer` (`GatewayProxy`) |
| `SpeculativeExecutor` | retired | Never raced a request |
| `SessionAffinity` | retired | Nothing ever pinned |
| `ConsensusRouter` | retired | Distinct from the live agent-plane consensus gate, which is untouched |
| `VirtualKeyManager` | retired | Never authenticated anything; removes a security surface that provided no security |

### Three documents asserted behaviour that never happened

Corrected in a separate, standalone commit ahead of the removals:

- **`docs/adr/0019` §4** listed `speculative_execution.py` and `observability.py`
  as key-bearing egress send sites. Neither ever sent a byte. A security ADR
  claiming egress from dead code misleads anyone auditing key handling.
- **`docs/docker.md`** told operators virtual keys persist state while running.
  `VirtualKeyManager` never called `create()`, so it never wrote.
- **`speculative.json` / `consensus.json` `{"enabled": true}`** were real
  operator on-switches that silently did nothing, advertised as opt-in features
  by `_module_inst`'s docstring; `session_affinity.json`'s `ttl` implied pinning
  that never occurred. All these files are now unread, and `docs/docker.md` says
  so where an operator would look.

### Coverage

Removing the modules removed their unit tests. Two tests in
`tests/test_redirect_failover.py` were **not** simply dropped: `observability`
was the tree's only caller of `netutil.keyed_request(auth_scheme=...)` with a
non-Bearer scheme, so that arm is re-homed as
`test_basic_auth_scheme_does_not_follow_redirect`, asserted directly against the
choke point. That is stronger than what it replaces — it no longer depends on
any particular caller existing.

### Detector

`KNOWN_INSTANCE_INERT` shrinks to one row. The non-vacuity guard
(`find_stale_roster_symbols`) forced the roster rows and the code to be deleted
in the same commit. Because the surviving row is heuristic-visible, the proof
that the roster is *load-bearing* no longer rides on "the heuristic misses one
of the six"; it is now asserted against the mechanism, using a real class the
heuristic cannot see (`PolicyRouter`) as a probe. A new instance-inert class
with no roster row still reds on the heuristic alone — asserted separately.
