# REVIEW — fleet #17 `feat/balance-drain` (balance tracker / drain-before-move)

- Date: 2026-07-05
- Reviewer: adversarial (fleet manager)
- Branch HEAD: `71e8281`  Worktree: /home/stack/code/charon-balance
- Base: origin/master `f79a898`
- Verdict: **ALREADY-MERGED — DELETE BRANCH** (no unmerged content)
- Gate: PASS  |  Tests: 1177 passed

## 1. STATE — is there anything left to merge? NO.

`71e8281` (this branch's HEAD) **is the second parent of the merge commit that IS origin/master**:

```
f79a898 (origin/master)  parents: 377d4a3 71e8281
  "merge(#17): balance tracker module (drain-before-move; module only, proxy wiring deferred)"
```

- `git merge-base --is-ancestor 71e8281 origin/master` → YES (fully contained).
- `git log origin/master..HEAD --oneline` → empty.
- `git diff --stat origin/master...HEAD` → empty.
- `git branch --contains 71e8281` → feat/balance-drain **and** master/origin-master.

Conclusion: the branch was already merged into master via `f79a898`. It carries **zero** new commits or diff over master. **Recommendation: delete `feat/balance-drain` (local + remote). Nothing to merge; do NOT re-open a PR.**

The review below audits the content that landed on master (money-path, so worth a real look; findings become follow-up tickets, not merge blockers since it's already in).

## 2. GATE + TESTS

- `PYTHONPATH=src python3 -m charon.cli gate` → all checks passed (ruff, mypy, SLOP-boundary, version, gate-registry). EXIT 0.
- `PYTHONPATH=src python3 -m pytest -q` → **1177 passed** in ~82s. No failures, no skips of note.
- (Note: running the gate WITHOUT `PYTHONPATH=src` gives ModuleNotFoundError but exit 0 — a harness invocation quirk, not a branch defect.)

## 3. ADVERSARIAL CORRECTNESS

Files added (both now on master): `src/charon/balance.py` (308 LOC), `tests/test_balance.py` (333 LOC).

- **Module-only, proxy wiring deferred — CONFIRMED.** `grep` of `src/` for any import/use of `BalanceTracker`/`record_spend`/`should_drain`/`is_drained` outside `balance.py` → nothing. No live routing change. Claim holds.
- **Auto-decrement math — CORRECT, no double-count.** `record_spend` decrements fixed balances by real `usd` and floors at 0 via `max(cur-usd, 0.0)`. It is an explicit **no-op for poll providers and unconfigured providers** (their balance API is authoritative) — so no double-counting. Negative/zero spend ignored. Thread-safe under `Lock` (concurrent-spend test present).
- **Poll error handling — SAFE (does not zero the balance).** Adapters catch all exceptions internally and return `None`; `remaining()` returns `None` for an unreachable poll provider; `is_drained` then returns `False` (neutral, not "drained") and `should_drain` returns `False`. So a provider being down neither zeroes nor drains it. Good.
- **Drained → demote without thrash — OK for fixed.** Fixed balances are monotonically decreasing, so the ~0 → skip transition (via `is_drained`, tested) cannot thrash. `floor` param gives hysteresis headroom.
- **Configured starting balance for dashboard-only providers — HANDLED.** `mode:"fixed"` + `starting_usd` (opencode-zen/Together/NeuralWatt), coerced to float with fallback 0.0; `configure()` allows runtime add/update.

### FINDINGS (follow-up, not blockers — already merged)

1. **[HIGH / money-path] No persistence of the running balance across restarts.** Fixed balances live only in `self._fixed_balances` (in-memory) — there is **no save/load** (grep confirms no file/json.dump/Path). On process restart the tracker re-initializes every fixed provider back to `starting_usd`. Effect once wired: a **drained** dashboard-only provider (e.g. opencode-zen at ~$0) **resets to full balance on restart**, so Charon would resume "drain-first" routing to a provider whose real prepaid balance is already exhausted → wasted/failed attempts and a false spend picture. This is inherent to a drain-before-move feature and MUST be closed in the proxy-wiring ticket (persist decremented balance to the mounted `/data` volume, per the deploy-drift lesson SR-10 D024). Poll providers are unaffected (they re-fetch truth).
2. **[LOW] `poll_error` counter is largely dead in `remaining()`.** Adapters swallow their own exceptions and return `None` rather than raising, so the outer `try/except` in `remaining()` almost never fires; the `poll_error` counter mostly won't reflect real unreachable-provider events there (it only increments in `force_poll` when an adapter is monkeypatched to raise, as the test does). Observability gap, not a correctness bug.
3. **[LOW, for wiring] Poll `remaining()` makes a synchronous network call on every call.** `should_drain`/`is_drained` each trigger a live poll with no caching (default timeout 20s). If the wiring ticket calls these on the routing hot-path, that's blocking I/O + repeated polling per decision. Add a TTL cache / background refresh when wiring.
4. **[NIT] `remaining()` reads `self._config` outside the lock** while `configure()` writes it under lock. Benign under CPython (atomic dict get) but inconsistent locking discipline.

## 4. BLAST RADIUS / BOUNDARY

- Blast radius at rest: **zero** — nothing imports the module; purely additive, inert unless configured.
- Test coverage: solid for what exists (decrement, floor, drain→skip transition, adapter parsing + error paths, no-double-count for poll, thread safety). **Gap:** no restart/persistence test (because there is no persistence — finding #1).
- Product/build-rig boundary: **clean.** No `/home/stack`, `fleet`, `SLOP`, `runner` strings in `balance.py`/`test_balance.py`. Stdlib only (`urllib`, `json`, `threading`), no network at import, config-gated OFF by default. SLOP-boundary gate check passes.

## VERDICT

**ALREADY-MERGED-DELETE.** The branch has no unmerged content — its HEAD is the merged second parent of origin/master. Delete `feat/balance-drain`. The merged module is correct, gated, and tested as a module-only landing; open a follow-up ticket to (a) **persist fixed balances to /data across restart** before any proxy wiring, and (b) add caching + real error-counting to poll mode when wiring.
