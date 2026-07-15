# ADR: S8 GRACEFUL-DEGRADE — Unified Provider-Health Hold Lifecycle

Status: PROPOSED (design-only). Depends on S6 (forwarder.py collision resolved) + S1 (truthful gate) + ROUTER-CORE status (S2). Money-path → adversarial verify (S11). Ref: `CROSS-AUDIT-SYNTHESIS.md:36,54`, `charon-north-star-engine-mechanism.md:24`.

> Authored 2026-07-14 by the S8 design agent (delegated Plan run), grounded in the current product code (`src/charon`) with file:line citations. Persisted verbatim by session quinlan-vos. Design-only — no code changed.

## Context

The north-star engine invariant is: need → gateway → available providers → tier-approved cheapest-capable worker → HOLD unavailable → re-admit; NEVER out of workers while ≥1 viable (`charon-north-star-engine-mechanism.md:12-18`). Today "HOLD" is implemented by **four** overlapping, independently-keyed mechanisms with no shared state, no shared re-admit policy, and one axis (latency) that is defined but never enforced:

1. **Balance park / drain-then-park (per-PROVIDER).** `BalanceTracker` in `balance.py`. Triggers: pre-flight, a drained class-3 provider (`fc==3 and is_drained`) is parked (`forwarder.py:367`); request-path, a deterministic drained-key 402 calls `record_exhaustion` → `park` (`forwarder.py:575-578`, `balance.py:429-441`). State persisted to `<state_dir>/balance_park.json` as `{"parked": [provider,...]}` (`balance.py:54,464-515`). Re-admit: poll-mode providers auto-re-arm when a fresh balance poll shows funds > 0 (`balance.py:319-325,517-526`); fixed class-3 re-arm via operator `top_up()` (`balance.py:581-597`). Sole-leg guard prevents parking the last leg (`forwarder.py:354-363,577-585`).

2. **Provider cooldown (per-PROVIDER, keyed by `upstream_base`).** `GatewayProxyServer._cooldown: dict[str,float]` (`proxy_server.py:593`). Trigger: any failover-eligible non-200 with `obs.exhausted` calls `set_cooldown(route, obs.retry_after)` (`forwarder.py:559`); connection errors call `set_cooldown(route, None)` → default 60s (`forwarder.py:483,531`). State is **in-memory only**, monotonic-clock deadlines, clamped to `max_cooldown_s=120` (`proxy_server.py:716-727`). Re-admit: implicit/passive — `order_by_cooldown` puts cooled routes last but never removes them, and they become fresh again when the deadline passes (`proxy_server.py:651-676`). No probe.

3. **Latency signal (per-PROVIDER EWMA) — SLOW AXIS, currently INERT as a hold.** `RollingLatency` EWMA recorded on every success (`forwarder.py:642,726,767`). `is_slow`/`is_slow_provider` are DEFINED (`latency.py:47`, `proxy_server.py:679-684`) but **never called** — grep shows zero callers. Latency is used ONLY as a tiebreak inside `order_by_cooldown` (`proxy_server.py:659-676`). So "fail over slow providers" (`latency-is-a-failure-class.md`) is not actually wired: a slow provider is de-prioritized, never held.

4. **`ReviewerCircuitBreaker` (per-Reviewer, NOT per-provider) — DEAD.** `failover.py:73-142`. Full CLOSED→OPEN→HALF_OPEN→CLOSED state machine, but it wraps a code-review `Reviewer` (`ports/reviewer.py`), not a provider route. Instantiated only in tests (`tests/test_failover.py`, `tests/test_consensus_gate.py`); zero production callers. `next_entry`/`proxy_excluded_keys` (`failover.py:31-52`) are likewise test-only (the live path is the in-request forwarder loop, per the ADR-0014 note at `failover.py:55-60`). These are the "built-but-inert" symbols the cross-audit flagged to KEEP+wire (`CROSS-AUDIT-SYNTHESIS.md:25,36`).

Observer exhaustion is keyed per-MODEL (`proxy.py:304` `_exhausted: dict[str, ProxyObservation]`), a fifth notion of "held" at a different granularity. Classification vocabulary that the lifecycle must consume: `exhausted` (429/402/503 or 401+billing), `transient` (503 or self-healing 402 → retry-once), `failover` = `exhausted or pseudo_success or dropped` (`proxy.py:100-112,398-399,436`).

The result: three-to-five stores, three keys (provider label, `upstream_base`, model id), two re-admit styles (passive-deadline vs poll/operator), one unenforced axis, and one dead breaker. No single place answers "is this leg available right now, and why not, and when will it be re-probed."

## Decision

Introduce ONE `ProviderHealth` lifecycle — a state machine `ACTIVE → HOLDING{reason} → PROBING → ACTIVE` keyed **per-LEG** (`(provider, base_url)` = the `upstream_base` the cooldown map already uses) — that subsumes park, cooldown, circuit, drain, and the slow-axis. Model it on Envoy outlier-detection / LiteLLM router-cooldown semantics as a self-contained plugin (`charon-core-stdlib-plugins-best-in-class`, `charon-north-star-engine-mechanism.md:24`). Two axes feed one machine:

- **Hard axis** (immediate hold): 402 drained-key, repeated 429/503/5xx, connection errors, 401+billing. Confidence is high per-event → short-cool or park.
- **Slow axis** (evidence-accumulating hold): EWMA latency over `slow_provider_threshold_ms`, and (future) quality-score floor. Requires N-of-M consecutive slow samples before ejecting (Envoy outlier style) so one slow request never ejects a leg.

A single active RE-PROBER drives every HOLDING→PROBING→ACTIVE transition on a per-reason cadence, replacing today's mix of passive deadlines, lazy balance polls, and operator top-ups. The `≥1-viable` invariant is enforced as a hard gate INSIDE the state machine (generalizing today's sole-leg guard from balance-only to all reasons), with an UP-escalation hook when the last viable leg for a needed capability would be held.

`ReviewerCircuitBreaker`'s generic breaker (`failover.py:73-142`) is promoted to the reusable primitive underneath the per-leg machine (it is already a proven CLOSED/OPEN/HALF_OPEN implementation) — wired for the first time. Its reviewer-wrapping façade stays for the fleet coordinator, but the state-machine core becomes provider-health infrastructure.

## Unified state machine

States, per leg:

- **ACTIVE** — eligible for routing; `order_by_cooldown` returns it in the fresh set.
- **HOLDING{reason, since, until, strikes}** — excluded from routing (unless sole-viable, see Invariant). `reason ∈ {DRAINED_402, THROTTLED_429, UPSTREAM_5XX, UNREACHABLE, SLOW, QUALITY, OPERATOR_PARK}`. `until` = earliest re-probe time (reason-derived cadence); `DRAINED_402`/`OPERATOR_PARK` have no fixed `until` (event-driven re-arm).
- **PROBING** — a single in-flight canary is deciding re-admission. Concurrency-1 per leg (mirrors HALF_OPEN's single-probe, `failover.py:78-80,133-137`). Success → ACTIVE (reset strikes); failure → HOLDING (re-arm cadence, back off).

Transitions:

| From | Event | To |
|---|---|---|
| ACTIVE | hard-axis failover event (`obs.exhausted`, non-transient) | HOLDING{hard reason} |
| ACTIVE | slow-axis: `strikes ≥ N` consecutive over threshold | HOLDING{SLOW} |
| ACTIVE | operator park | HOLDING{OPERATOR_PARK} |
| HOLDING | `now ≥ until` (timed reasons) | PROBING |
| HOLDING | evidence re-arm (balance poll > 0; top_up) | PROBING (or ACTIVE if probe cheap/skippable) |
| PROBING | probe success | ACTIVE |
| PROBING | probe failure | HOLDING (back-off `until`) |
| HOLDING/PROBING | sole-viable for a needed capability | ACTIVE (escalated; see Invariant) |

Re-prober design (the genuinely new piece):
- A background thread (or lazy on-request sweep, matching current stdlib-only, no-async-loop style — `balance.py` is fully synchronous) scans legs whose `until` has elapsed and moves them to PROBING.
- **Probe kind is reason-specific:** `DRAINED_402` → a balance poll (`force_poll`, `balance.py:542`), NOT a token spend (probing an empty key wastes a request — the code comment at `forwarder.py:508-511` already makes this point). `THROTTLED_429`/`UPSTREAM_5XX`/`UNREACHABLE`/`SLOW` → a real 1-token/minimal completion canary against the leg's model (this is what `select_live_entry` used to do before ADR-0014 retired it, `failover.py:55-60`).
- **Cadence:** exponential-ish, reason-seeded — `THROTTLED_429` honors `Retry-After` (already captured as `obs.retry_after`), `UPSTREAM_5XX`/`UNREACHABLE` start at `default_cooldown` (60s) and back off to `max_cooldown_s` (120s) on repeated probe failure, `SLOW` re-probes slower (minutes), `DRAINED_402` only re-probes on balance-poll TTL (`_DEFAULT_POLL_TTL=300`, `balance.py:157`) or operator top_up. This preserves every existing clamp (`proxy_server.py:724-725`).
- **Anti-flap:** a leg must pass K consecutive probes (or one probe + a cooldown-free window) before strikes reset — canary re-admit (`charon-north-star-engine-mechanism.md:16`).

## State store

One store, `ProviderHealthStore`, replacing the three current stores. Persist to `<state_dir>/provider_health.json` using the exact atomic-write discipline already proven in `balance.py:464-515` (unique tmp name = pid+tid+uuid, `os.replace`, `_save_lock` serialization, best-effort swallow — this was a real concurrency BLOCKER fix, commit `b8e62d0`; reuse it verbatim).

Record shape, keyed by leg (`upstream_base`):

```
{
  "legs": {
    "<upstream_base>": {
      "provider": "openrouter",
      "state": "ACTIVE|HOLDING|PROBING",
      "reason": "DRAINED_402|THROTTLED_429|UPSTREAM_5XX|UNREACHABLE|SLOW|QUALITY|OPERATOR_PARK|null",
      "since_epoch": 0.0,           // wall-clock for console display + restart survival
      "until_monotonic": 0.0,       // re-probe deadline (timed reasons); derived, not persisted raw
      "strikes": 0,                 // consecutive hard/slow failures (Envoy outlier count)
      "probe_fails": 0,             // consecutive probe failures → back-off
      "manual": false,              // operator park vs auto (preserves balance.py auto_park counter)
      "last_probe_epoch": 0.0
    }
  },
  "counters": { "auto_hold": 0, "auto_readmit": 0, "probe_success": 0, "probe_fail": 0, "escalation": 0, "save_error": 0 }
}
```

Reconciliation of the three existing stores:
- `balance_park.json` `{"parked":[...]}` → migrated into `legs[*].state=HOLDING, reason∈{DRAINED_402,OPERATOR_PARK}, manual=<auto_park vs park>`. A one-shot loader reads the old file if present (back-compat), then writes the new schema. Balance NUMBERS (starting_usd, poll adapters, model_spend) STAY in `BalanceTracker` — that is the balance SENSOR; only its park SET moves out. `BalanceTracker.is_parked/park/unpark` become thin delegations to `ProviderHealthStore` (or are removed and callers repointed).
- `_cooldown: dict[str,float]` (in-memory) → `legs[*].until_monotonic` with `state=HOLDING, reason∈{THROTTLED_429,UPSTREAM_5XX,UNREACHABLE}`. Cooldown gains durability (survives restart) for free — a current gap.
- `RollingLatency` EWMA stays as the slow SENSOR; the store gains `reason=SLOW` holds fed by it. Wire the dead `is_slow_provider` (`proxy_server.py:679`) into the strike counter.
- Observer per-model `_exhausted` (`proxy.py:304`) stays as-is for model-level failover; the leg store is the provider-level authority. `order_by_cooldown` reads the store instead of `_cooldown`.

Wiring point: `_build_balance_tracker` (`gateway.py:282-302`) grows a sibling `_build_provider_health(providers_cfg, state_dir)`; both get the same resolved `state_dir` (the mounted-volume caveat at `balance.py:48-53` applies identically). `GatewayProxyServer.__init__` (`proxy_server.py:502-593`) takes a `provider_health` param; `order_by_cooldown`, `set_cooldown`, `is_slow_provider`, and the forwarder park/cool calls (`forwarder.py:343,367,483,531,559,575`) all route through it.

## Invariant (S10: ≥1-viable)

The store enforces, on every HOLDING/PROBING transition: **never hold the LAST viable leg for a needed capability.** This generalizes today's balance-only sole-leg guard (`forwarder.py:354-363,577-585`, `_has_live_sibling`/`_is_sole_leg` at `forwarder.py:180-233`) to ALL hold reasons.

`escalate(capability)` does, in order:
1. **Relax the hold** — if the only-remaining route for a needed tier is HOLDING for a soft reason (SLOW/QUALITY, or a timed cooldown not yet re-probed), force it back to ACTIVE (a slow-but-alive leg beats a stall — down-substitution/UP-escalation is the north-star rule, `charon-north-star-engine-mechanism.md:18`) and emit a loud `escalation` counter + log.
2. **Admit a costlier tier** — if no at-or-below-tier leg is viable, search at-or-ABOVE the ideal tier for the cheapest capable ACTIVE leg (UP-escalation; a tier is a preference not a wall, `charon-north-star-engine-mechanism.md:18`). This is the S9 selector's job; S8 exposes `viable_legs(capability)` so S9 can ask.
3. **Surface, never silently drop** — if truly zero legs at-or-above the hardest pending tier meet the floor, that tier's work is HELD (deferred, visibly, with reason) while lower tiers keep flowing — the ONLY legitimate stall (`charon-north-star-engine-mechanism.md:18`, `CROSS-AUDIT-SYNTHESIS.md:56,74`).

The DRAINED_402 sole-leg case keeps its existing "keep it in chain + warn" behavior (`forwarder.py:355-363`) as the concrete instance of rule 1.

## Mapping table (existing mechanism → new state/transition)

| Existing mechanism | File:line | New home |
|---|---|---|
| `balance.park()` operator | `balance.py:404`, `forwarder.py:367` | HOLDING{OPERATOR_PARK / DRAINED_402}, `manual` flag |
| `record_exhaustion()` auto-park on 402 | `balance.py:429`, `forwarder.py:575-578` | ACTIVE→HOLDING{DRAINED_402}; `auto_hold` counter |
| poll-recovery auto-unpark | `balance.py:319-325,517-526` | HOLDING{DRAINED_402}→PROBING(balance-poll)→ACTIVE |
| `top_up()` re-arm | `balance.py:581` | evidence re-arm → PROBING/ACTIVE |
| drain pre-flight skip (fc==3, is_drained) | `forwarder.py:351-368` | HOLDING{DRAINED_402} via balance sensor |
| `set_cooldown(retry_after)` on exhaustion | `forwarder.py:559`, `proxy_server.py:716` | ACTIVE→HOLDING{THROTTLED_429 / UPSTREAM_5XX}, `until` |
| `set_cooldown(None)` on unreachable | `forwarder.py:483,531` | ACTIVE→HOLDING{UNREACHABLE}, default cadence |
| `order_by_cooldown` fresh/cooled split | `proxy_server.py:651-676` | reads store: ACTIVE first, HOLDING last (sole-viable override) |
| retry-once transient (503 / self-heal 402) | `forwarder.py:512-552`, `proxy.py:226` | stays in forwarder (pre-hold); NOT a state — transient never holds |
| `is_slow` / `is_slow_provider` (INERT) | `latency.py:47`, `proxy_server.py:679` | wired → slow-axis strike counter → HOLDING{SLOW} |
| `RollingLatency` EWMA | `latency.py`, `forwarder.py:642,726,767` | slow-axis SENSOR (unchanged) |
| `ReviewerCircuitBreaker` CLOSED/OPEN/HALF_OPEN (DEAD) | `failover.py:73-142` | breaker core reused as per-leg primitive; HALF_OPEN = PROBING |
| `next_entry`/`proxy_excluded_keys` (test-only) | `failover.py:31-52` | superseded by live forwarder loop + store; delete or keep as engine-side helper |
| sole-leg guard (balance only) | `forwarder.py:180-233,354-363` | generalized → Invariant `escalate()` for all reasons |
| observer per-model `_exhausted` | `proxy.py:304` | unchanged (model axis); leg store is provider axis |

## Phased plan

**Phase 0 — Reconcile stores (reuse-heavy, low risk).** Build `ProviderHealthStore` (new) borrowing `balance.py`'s atomic-persist verbatim. Migrate `balance_park.json` (loader reads old, writes new). Repoint `is_parked/park/unpark` to the store. NO behavior change yet. Accept: existing `tests/test_balance*.py` + park-persistence tests pass unchanged; migration round-trips old→new file.

**Phase 1 — Unify hard axis (cooldown + park under one machine).** Move `_cooldown` into the store; `order_by_cooldown` and all `set_cooldown` callers (`forwarder.py`) go through `ProviderHealthStore.hold()/viable()`. Cooldowns now persist. Accept: replay the existing forwarder failover tests (429/402/503/unreachable) — same routing decisions; add a restart-survives-cooldown test.

**Phase 2 — Active re-prober.** Add the PROBING state + reason-specific probes (balance-poll for DRAINED_402, 1-token canary for the rest), cadence + back-off + anti-flap. Retire passive-deadline re-admit. Accept: drive a leg to HOLDING, assert a probe fires on cadence, success re-admits, failure backs off; assert DRAINED_402 probes via balance poll not a spend.

**Phase 3 — Slow axis wired.** Feed `is_slow_provider` (`proxy_server.py:679`) into an N-of-M strike counter → HOLDING{SLOW}; slow legs re-probe on a slow cadence. Wire the `ReviewerCircuitBreaker` core as the shared breaker primitive. Accept: N consecutive slow samples eject; one slow sample does not; slow leg re-admits when latency recovers. Confirm `is_slow_provider` is now reachable via `graphify explain` (kills the inert-symbol finding, `CROSS-AUDIT-SYNTHESIS.md:14,25`).

**Phase 4 — Invariant + escalation (S10 gate).** Generalize sole-leg guard to `escalate(capability)` across all reasons; expose `viable_legs(capability)` for S9. Accept (fail-on-revert): hold ALL-BUT-ONE leg, assert a need still routes and never fails while ≥1 viable; assert a soft-held last leg is relaxed to ACTIVE; assert a truly-uncovered hardest tier is HELD (deferred, logged) while lower tiers flow.

**Phase 5 — S11 tool-confirmed adversarial acceptance.** Independent fresh-session reviewer, does not trust SUCCESS lines (`document-model-self-report-lies`), confirms every claim with our own tools (`CROSS-AUDIT-SYNTHESIS.md:63-78`): `graphify explain` (symbols wired, not inert), `check_inert_code.py` (no new dead code, deterministic per S1), `charon.cli gate` + fail-on-revert (green is real), live drive-throughs — drain providers one-by-one to the last survivor (matrix row 3), 1 agent-not-capable-of-hardest-tier held-not-dropped (row 2), quality preserved under down-substitution (row 4), no-stall-gap proof (row 5). Ship "engine complete" only when all five pass adversarially.

## Risks

1. **Re-prober cost/spend on the money path.** A 1-token canary against a paid leg costs money and, if mis-scheduled, can hammer a still-broken upstream. Mitigation: balance-poll (not spend) for DRAINED_402; strict concurrency-1 per leg (HALF_OPEN semantics); exponential back-off honoring `Retry-After`; reuse the `max_cooldown_s` clamp (`proxy_server.py:724`).
2. **Concurrency on the unified store (money path).** The park-persist race was a real BLOCKER (`b8e62d0`); a single hotter store touched by forwarder + re-prober + operator raises the stakes. Mitigation: reuse the proven `_save_lock`+unique-tmp+`os.replace`+best-effort-swallow discipline verbatim (`balance.py:464-515`); never let a persist error reach the client (loud-terminal-503 invariant).
3. **Invariant regression = silent stall or silent drop.** Collapsing four guards into one risks a hole where the last viable leg gets held (stall) or work is dropped instead of deferred. Mitigation: Phase-4 fail-on-revert test is the ship gate (S10); generalize the existing, working sole-leg guard rather than rewrite it; S11 adversarial drive-through must PROVE no-stall-while-capable-route-exists before "engine complete."

## Critical files for implementation
- `src/charon/balance.py`
- `src/charon/proxy_server.py`
- `src/charon/forwarder.py`
- `src/charon/failover.py`
- `src/charon/gateway.py`
