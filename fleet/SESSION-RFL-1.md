# DeepSeek build session — RFL-1 proactive quota tracking (module ONLY, defer the wiring)

You are a Charon build session (DeepSeek V4 Pro). Repo: `/home/stack/code/charon`. Branch off `master`.
Implement **RFL-1 Phase-1 ONLY** — the standalone `src/charon/quota.py` module + its tests + a clean
public API. **Do NOT wire it into `proxy_server.py`** — that hook is explicitly DEFERRED to a follow-up
ticket so this session never touches the proxy hot path.

**This session runs in PARALLEL with the SR-12 and TOOL-REPAIR sessions — that is SAFE:** all three
build NEW standalone modules and touch disjoint files (this one: `quota.py` only), none of them edits
`src/charon/proxy_server.py`.

## 1. Ground yourself first (read these)
- `/home/stack/code/charon/AGENTS.md` — standing orders (mandatory).
- `src/charon/response_normalizer.py` — the REFERENCE for the module style you must match: a stdlib-only,
  self-contained, deterministic module with a small public class, no network, no external deps. Mirror its
  shape (a public class + private helpers, `from __future__ import annotations`, stdlib imports only).

## 2. The idea — proactive free-tier quota tracking
Charon is a free-tier failover gateway but is purely **reactive** today: it only learns a provider is
exhausted *after* burning a request → 429 → cooldown. RFL-1 adds a **pre-flight** sliding-window quota
tracker so the router can SKIP a provider it predicts would exceed its configured limit — avoiding the
wasted round-trip, latency, and 429 failover-thrash. It **complements** (does NOT replace) the existing
Retry-After cooldown, and is a **different axis** from the client-side virtual-key `max_rpm`/`max_tpm`
(that throttles the *client*; this tracks *upstream provider* quota).

## 3. Scope — the `quota.py` module ONLY
- branch: `feat/rfl-1-quota-tracking` (off latest `master`).
- **owns:** `src/charon/quota.py` (NEW), `tests/test_quota.py` (NEW). Touch NOTHING else.
- **DO build** `src/charon/quota.py` — a stdlib (`collections.deque` + `time.monotonic`, thread-locked
  with `threading.Lock`) per-provider sliding-window tracker:
  - Track four rolling windows per provider: **RPM** and **TPM** (requests / tokens in the last 60s) and
    **RPD** and **TPD** (requests / tokens in the last 24h = 86400s). Store request timestamps and
    (timestamp, token_count) in deques; evict entries older than the window on each read/write.
  - **Config-driven limits, OFF/advisory by default.** Limits come from config (a plain dict:
    `{provider: {"rpm": int, "rpd": int, "tpm": int, "tpd": int}}`, any subset). A provider with **no
    configured limit is never skipped** — the tracker still records usage (so counters are meaningful) but
    `should_skip` returns `False` for any window that has no limit set. No limits configured anywhere →
    the tracker is inert (pure advisory bookkeeping).
  - **Clean public API** (this is the seam the deferred proxy wiring will call):
    - `should_skip(provider: str, est_tokens: int) -> bool` — `True` iff sending a request of
      ~`est_tokens` would push ANY configured window over its limit (i.e. current_count + 1 > rpm/rpd, or
      current_tokens + est_tokens > tpm/tpd). No configured limit for a window ⇒ that window can't trip.
    - `record(provider: str, tokens: int) -> None` — record one request of `tokens` tokens against all
      windows (called on each response; token counts are already available at the call site).
    - Optionally also expose `get_wait_time(provider, est_tokens) -> float` returning the shortest seconds
      until `should_skip` would flip back to `False` (the oldest in-window entry's expiry). Nice-to-have —
      keep it if it stays simple; skip if it complicates the deque bookkeeping.
  - **Per-rule observability counters:** keep an internal counter dict keyed by the reason a skip fired
    (e.g. `"skip_rpm"`, `"skip_tpm"`, `"skip_rpd"`, `"skip_tpd"`), incremented inside `should_skip`, and a
    read-only accessor (e.g. `counters() -> dict[str, int]`) so the deferred wiring / console can surface
    which limit is doing the skipping. Match how `response_normalizer.py` keeps everything self-contained.
  - Key strictly on the `provider` string as the public API dictates. (A future ticket may widen the key to
    the full `(provider, model)` tuple — leave a one-line comment noting that, but do NOT build it now.)
- **DO NOT** import or edit `src/charon/proxy_server.py`, `pools.py`, `config.py`, or anything else. If you
  believe the module needs a change outside `quota.py` + its test, **STOP and flag it** — do not create/edit
  it. The proxy `_handle` exclude/order hook is a SEPARATE follow-up ticket.
- **Stdlib-only:** `collections`, `time`, `threading` — no third-party imports. No fleet/SLOP/runner/
  `/home/stack`/personal strings anywhere in `src/`.

## 4. Tests — `tests/test_quota.py` (hermetic, no network, no sleep-based flakiness)
- Inject/mock time (accept an optional injectable clock, e.g. a `now: Callable[[], float]` constructor arg
  defaulting to `time.monotonic`, OR monkeypatch) so windows can be advanced deterministically — **do not**
  rely on real `time.sleep`.
- `should_skip` returns `False` for a provider with no configured limit even after many `record` calls.
- With `rpm=2`: two `record`s then `should_skip` is `True` for RPM; advance the clock past 60s → `False`.
- With `tpm=1000`: `record(p, 900)` then `should_skip(p, 200)` is `True` (900+200>1000); `should_skip(p, 50)`
  is `False`.
- RPD / TPD trip on the 24h window and reset past 86400s.
- `counters()` reflects which reason fired (e.g. an RPM skip increments `skip_rpm`, not `skip_tpm`).
- Assert the module imports stdlib-only (no third-party module in its imports).

## 5. Rules — non-negotiable
- **Gate before commit** — BOTH of these must be green:
  ```
  python3 -m charon.cli gate && PYTHONPATH=src python3 -m pytest -q
  ```
  `python3 -m charon.cli gate` runs ruff/mypy/boundary/version/gate-registry; pytest is the separate test
  pass. Do NOT use a bare `mypy src/charon` — it misses the test files and reddens CI.
- Commit with a conventional message (e.g. `feat(RFL-1): proactive per-provider quota tracker (module + tests)`).
- **Commit your work but DO NOT push and DO NOT open a PR.** Stop after committing — a Claude reviewer + the
  operator gate every merge.

When committed, report the branch name + final `pytest` counts, then stop.

## Dependencies & Sequence
NEW standalone file (`src/charon/quota.py` + `tests/test_quota.py`), **disjoint from `proxy_server.py`**
(the proxy wiring hook is explicitly deferred to a follow-up ticket, so this session never touches it).
**Parallel-safe** with SESSION-SR-12 (edits `providers.py`) and SESSION-TOOL-REPAIR (new `tool_repair.py`)
— no shared files, run all three concurrently.
