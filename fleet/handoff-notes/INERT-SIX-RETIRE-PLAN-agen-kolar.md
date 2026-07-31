# INERT-SIX — dispositions + exact removal diffs (operator approval required before any deletion)

**Session:** agen-kolar · **Date:** 2026-07-24 · **Ticket:** INERT-INSTANCE-DETECT (decision #2)
**Product branch:** `feat/inert-instance-detect`
**NOTHING IN THIS FILE HAS BEEN EXECUTED.** No module code was deleted. Per ticket accept (D3), a
`retire` needs an operator sign-off line on the ticket before the removal lands.

---

## 1. Verdicts

| # | Module | Verdict | Deciding evidence |
|---|---|---|---|
| 1 | `RequestInspector` | **wire** | RFL-3 is a real, live (parked-not-archived) board ticket whose brief specifies `srv.request_inspector.inspect(...)`; 6 of 8 dogfood attempts built the call site |
| 2 | `SessionAffinity` | **retire** | Wiring map's owner **R44 does not exist** as a ticket, and its scope is a test gate, not a consumer |
| 3 | `Observability` | **retire** | Same non-existent R44 owner; the gateway's real observability is `srv.observer` (`GatewayProxy`), a different object |
| 4 | `SpeculativeExecutor` | **retire** | Wiring map's owner **R45 does not exist**, and its scope (startup inert-check) would *report* this module, not call it |
| 5 | `ConsensusRouter` | **retire** | Same non-existent R45 owner; the ~40 live "consensus" hits in the tree are the unrelated agent-plane gate |
| 6 | `VirtualKeyManager` | **retire** | Same non-existent R44 owner; no auth-path consumer anywhere |

### Why R44/R45 do not count as planned consumers

`fleet/state/WIRING-AUDIT-MATRIX.md`'s INERT-to-WIRED map has a "Downstream owner" column naming
R44 (dogfood-gate) and R45 (inert-startup-check). Checked:

- **Neither has a board ticket.** `ls fleet/board/` contains no `R44*` or `R45*` file, live, parked
  or archived. They survive only as `next` rows in old `SESSION-HANDOFF-*.md` roadmap tables.
  (`R46-BALANCE-WIRE` *does* exist as a real ticket — but it owns `BalanceTracker`, none of the six.)
- **Neither is a consumer even by scope.** R44 = "e2e merge-gate: real-config request asserts
  observable effects" (a test gate). R45 = "startup self-check: active vs inert optional components
  (fail-loud)" — a check that would *report* these modules as inert. Assigning them as the
  downstream owners was a mis-attribution in the matrix.
- **Both are already folded away.** `fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md:181` records
  the unified gate as SUBSUMING R44, R45, KS24 and board-trust/auto-retire.

So the wiring map supplies a *recipe* per module but no *owner*. Under the operator's rule (default
retire unless a real consumer is planned), five of the six retire; `RequestInspector` is the single
exception, rescued by RFL-3.

---

## 2. Does anything expect the routing-sounding modules to be live?

Asked explicitly because `SpeculativeExecutor`, `ConsensusRouter` and `SessionAffinity` name
behaviour someone could believe is already routing traffic.

| Module | Anything expecting it live? | Detail |
|---|---|---|
| `SpeculativeExecutor` | **YES — three things, all wrong** | (a) `speculative.json {"enabled": true}` is a real operator on-switch (opt-in gate, `gateway.py:340`) that constructs the executor and changes nothing; (b) `gateway.py:320` docstring calls speculative/consensus "cost-multiplying features that need explicit opt-in", which reads as if opting in turns them on; (c) **`docs/adr/0019-provider-key-egress-choke-point.md:166` lists `speculative_execution.py` as one of "four key-bearing send sites"** the egress choke point must cover — a security ADR treating it as a live egress path. Also: board ticket `DESTIFF-SPECULATIVE` (archived, landed) spent frontier-tier work wiring its upstream call through `failover_loop.invoke_with_failover` — hardening code that has never run. |
| `ConsensusRouter` | **YES — same shape** | `consensus.json {"enabled": true}` on-switch + the `gateway.py:320` docstring. **Distinct and NOT affected:** the ~40 `consensus` references across `fence.py`, `coordinator.py`, `decompose.py`, `ports/reviewer.py` are the agent-plane consensus gate (ADR-0003 §6, autonomy L2), which is genuinely wired. Retiring the gateway module does not touch it. |
| `SessionAffinity` | **YES — partly** | `session_affinity.json`'s `ttl` knob is read at `gateway.py:91`, so an operator can set a TTL and reasonably believe requests are pinned to a provider. They are not: the map is written by nobody and read by nobody. No doc or ADR claims the feature. |
| `Observability` | no (but name-collides) | Nothing claims it. The hazard is naming: the gateway's real, wired observability is `srv.observer` = `GatewayProxy` (`proxy.py:448-493`, called on every served 200). Every "observability" mention in `api.py:282,340` and `failover.py:59` means `srv.observer`. `ADR-0019:166` also lists `observability.py` as a key-bearing send site. |
| `VirtualKeyManager` | **YES — shipped docs do, falsely** | `docs/docker.md:117` tells operators not to mount the config volume read-only because "the quality scorer, the balance tracker's auto-park state, **virtual keys**, and the policy router" persist files there while running. `VirtualKeyManager` takes `state_dir` at construction but nothing ever calls `create()`, so it never writes. |
| `RequestInspector` | no | No claim anywhere; RFL-3 is prospective. |

All six pass their own unit tests in isolation (`tests/test_*.py`, 936 lines total), which is why the
suite has stayed green throughout.

---

## 3. Removal diffs (per retired module) — NOT APPLIED

Line numbers are against `feat/inert-instance-detect` as of this file. `gateway.py` and
`proxy_server.py` are god-files under constant churn — **re-resolve before applying**. All five
retirements touch the same two files, so they must land as ONE change or be strictly serialised.

### Shared shape (every retired module)

| file | edit |
|---|---|
| `src/charon/<module>.py` | delete whole file |
| `tests/test_<module>.py` | delete whole file |
| `src/charon/gateway.py` | delete the `from .<module> import <Class>` line; delete the module's `ModuleSpec(...)` rows from `_MODULE_SPECS` |
| `src/charon/proxy_server.py` | delete the `from .<module> import <Class>` line; delete the ctor kwarg line (490-500 block); drop the name from the `_mod_param_names` tuple (562-564); delete the `self.<attr> = self.modules.get(...)` line (574-581) |
| `tools/check_inert_code.py` | delete the module's row from `KNOWN_INSTANCE_INERT` **in the same commit** (a roster row whose class is gone now fails the gate by design) |
| `tools/inert-code-disposition.json` | delete the module's entry |

### 3a. `SessionAffinity` — 61 + 102 lines

- delete `src/charon/session_affinity.py` (1-61), `tests/test_session_affinity.py` (1-102)
- `gateway.py`: delete L44 (import); delete L90-91 (`ModuleSpec("session_affinity", ...)`)
- `proxy_server.py`: delete L54 (import); delete L497 (kwarg); L563 drop `"session_affinity"` from tuple; delete L578
- no doc/ADR corrections needed

### 3b. `Observability` — 150 + 244 lines

- delete `src/charon/observability.py` (1-150), `tests/test_observability.py` (1-244)
- `gateway.py`: delete L36 (import); delete L80-81
- `proxy_server.py`: delete L37 (import); delete L493 (kwarg); L562 drop `"observability"`; delete L574
- **also:** `src/charon/types.py` `ObsTarget` (L199) and `ObsEvent` (L209) exist only for this
  module's export contract — re-triage both (they currently carry
  `keep-detector-false-positive-module-unreachable-cascade` dispositions that stop being true).
- **also:** `docs/adr/0019-...:166` names `observability.py` as a key-bearing send site — correct it.
- do **not** touch `src/charon/routing_proxy.py`, `console_work.py`, `api.py:282,340`,
  `failover.py:59`, `tool_repair.py:412`, `balance.py:437`, `cli.py:1510` — all say "observability"
  but mean `srv.observer`/unrelated prose.
- `tests/test_work_observability.py` is unrelated (work-plane) — keep.

### 3c. `SpeculativeExecutor` — 237 + 302 lines

- delete `src/charon/speculative_execution.py` (1-237), `tests/test_speculative_execution.py` (1-302)
- `gateway.py`: delete L45 (import); delete L92-95
- `proxy_server.py`: delete L55 (import); delete L498 (kwarg); L564 drop `"speculative_executor"`; delete L579
- **also:** `gateway.py:320` docstring — drop "speculative" from "cost-multiplying features that need
  explicit opt-in"; **`docs/adr/0019-...:166`** — remove `speculative_execution.py` from the
  key-bearing send-site list; **`src/charon/netutil.py:85`** — comment cites
  `speculative_execution`'s N-way thread race as motivation for the module-global opener; the
  optimisation stays valid but the citation goes stale.
- **also:** mark `fleet/board/archive/DESTIFF-SPECULATIVE.md` as retired-with-its-subject so the
  landed failover hardening is not later mistaken for live coverage.

### 3d. `ConsensusRouter` — 60 + 79 lines

- delete `src/charon/consensus.py` (1-60), `tests/test_consensus.py` (1-79)
- `gateway.py`: delete L33 (import); delete L96-100
- `proxy_server.py`: delete L33 (import); delete L499 (kwarg); L564 drop `"consensus_router"`; delete L580
- **also:** `gateway.py:320` docstring (same line as 3c — one edit covers both).
- **KEEP, DO NOT TOUCH:** `tests/test_consensus_gate.py`, `fence.py`, `coordinator.py`,
  `decompose.py`, `ledger.py:68`, `ports/reviewer.py`, `recommend.py`, `types.py:28` — agent-plane
  consensus, unrelated and live.

### 3e. `VirtualKeyManager` — 122 + 78 lines

- delete `src/charon/virtual_keys.py` (1-122), `tests/test_virtual_keys.py` (1-78)
- `gateway.py`: delete L48 (import); delete L101-102
- `proxy_server.py`: delete L57 (import); delete L500 (kwarg); L564 drop `"virtual_key_manager"`; delete L581
- **also:** `docs/docker.md:117` — remove "virtual keys" from the list of components that persist
  state while running (the claim is false today and would be false-by-absence after).

### Totals if all five retire

630 lines of `src/charon` + 805 lines of tests + 12 import/kwarg/tuple/attr edits across two
god-files + 4 doc/ADR corrections. `RequestInspector` (45 + 131 lines) stays.

### Verification after applying

```
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 -m charon.cli gate
python3 tools/check_inert_code.py     # must be rc=0 with the roster rows removed too
```

---

## 4. Gate-B hole (closed on `feat/inert-instance-detect`)

The heuristic in `find_instance_inert_classes` tolerates false negatives, and measurement showed it
**missed 3 of the 6**: `SessionAffinity`, `ConsensusRouter`, `VirtualKeyManager` (their method names
— `resolve`, `create`, `verify`, `revoke`, `list_keys` — collide with unrelated instance calls
elsewhere in the tree). Their disposition entries were therefore decorative: deleting them left the
gate GREEN.

Measured, both directions:

| detector | disposition entry removed | rc |
|---|---|---|
| pre-fix (HEAD `699be71`) | `SessionAffinity` | **0 — false green** |
| pre-fix | `ConsensusRouter` | **0 — false green** |
| pre-fix | `VirtualKeyManager` | **0 — false green** |
| post-fix | each of the six, one at a time | **1 (RED) for all six** |
| post-fix | none removed (restored) | **0 (GREEN)** |

Fix: a hand-audited `KNOWN_INSTANCE_INERT` roster in `tools/check_inert_code.py` that the gate
requires a disposition for, independent of the heuristic — plus `find_stale_roster_symbols`, which
fails the gate if a roster row's class no longer exists, so the roster cannot quietly go vacuous and
pass over an empty set. Scoped to this repo via `roster_for()` so fixture trees do not inherit it.
