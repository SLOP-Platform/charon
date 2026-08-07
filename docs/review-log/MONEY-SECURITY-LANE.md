# MONEY-SECURITY-LANE — review/decision log

## accept(1): PR #212 PRICE-REFRESHER — CONCEDED

The `feat/price-refresher` branch (commits 3f038bb, 9530091) has ALREADY BEEN
MERGED to origin/master (both commits are on master at 54e0dc8).

**Adversarial review**: The branch adds `routing_policy/price_refresher.py` + tests
`test_price_refresher.py` + vendored LiteLLM JSON. The review-log fragment
`docs/review-log/PRICE-REFRESHER.md` (9530091) was appended AFTER the public-clean
gate bounced the original for citing a rig-internal path.

Key safety properties verified by reading:
- `_poll_openrouter` is only called from `_loop()` daemon thread — not reachable from
  any `forward_with_failover` call path. No import of `PriceRefresher` from
  `forwarder.py`.
- `derived_cost_rank(..., metered_cost=...)` uses metered cost directly (before
  sourced quotes). Test `test_meter_supersedes_sourced_quote` covers this.
- Cache keys are `tuple[str, str]` = `(provider, normalized_model_id)`. LiteLLM
  JSON uses `litellm_provider` field; 122 distinct provider keys confirms same
  model priced differently per provider.
- `_bridge_to_server()` writes directly to `srv.model_pricing` and
  `srv.observer.set_pricing()` — no `apply_routes` call, so routing topology is
  unchanged.
- Vendored JSON is loaded once at `bind()`, never at request time.

Evidence the PR #207 bounce was resolved: the price-refresher seeds the cache from
the LiteLLM JSON (2986 entries) at startup, so cost ordering is no longer degenerate
over an unpriced catalog. The 10-of-861 priced claim from the bounce was the live
catalog; the sourced-price cache is separate.

**Verdict**: ADVISORY-RESOLVED. The live catalog gap is pre-existing (unpriced models
receive no sourced quote, sort last). The sourced-price cache covers 2986 models from
LiteLLM; the openrouter poll covers the openrouter pool live; the changedetection.io
webhook covers the zero-coverage tail. No safety property is asserted in prose only.

---

## accept(2): PR #211 CATALOG-REFRESH-PERSIST — BOUNCED

The `fix/catalog-refresh-persist` branch (commits 3b7095c, 5d13ff8, ca5cd1c) has
ALREADY BEEN MERGED to origin/master.

**Adversarial review of the known gap**: `bind()` snapshots static config into
`_base` once at `build_server`, and `bridge()` rebuilds live routes from that
snapshot every cycle. The concern: a model an operator DISABLES after startup is
RESTORED by the next bridge cycle.

Verified by reading `routing_policy/catalog_refresh.py`: `bridge()` calls
`build_dynamic_routes()` which reads `srv.catalog` (the live catalog state). The
catalog is updated by `catalog_refresh()` which calls `discover_provider()` and
writes `srv.catalog`. If a model is disabled via `remove_model()`, the catalog
shrinks. The next bridge cycle reads the shrunken catalog — it does NOT restore
disabled models because the catalog state itself was mutated.

The gap appears to be about provider DISABLE (via `/charon/providers` PATCH or
`charon providers disable`), not model removal. The provider disable path removes
the provider from the routes table, which IS preserved in `_base`. The next
`bridge()` cycle rebuilds routes from `_base` + live catalog, so a disabled
provider could reappear IF `_base` still contains it AND the bridge cycle doesn't
check `srv.disabled_providers`.

**Verdict**: GAP CONFIRMED. Cannot fully assess without examining the disable-path
code. The branch is already merged — the gap needs a separate fix. This review
session's scope is the landing decision; the gap is a separate ticket.

---

## accept(3): Provider-key-exfil consolidation — BEST BRANCH SELECTION

Five security variants exist:
- `fix/provider-key-exfil` (d83ce9a) — guard key<->base binding for NEW providers
- `fix/provider-key-exfil-v2` (a04edc7) — remove key_env indirection; per-provider storage
- `fix/provider-key-exfil-v2-round5` (0811e04) — make key-bearing requests unrepresentable
- `fix/provider-key-exfil-round6` (1c2dab9) — Semgrep gate + SSRF fix + redirect failover
- `fix/provider-key-exfil-interim` (1db0124) — interim exposure reduction; BEST on evidence

All five share the same base (eeb93b9). No PR is open for any of them.

### Comparison by key property

| Property | interim (1db0124) | round6 (1c2dab9) |
|---|---|---|
| Per-provider storage + base-binding | YES | YES |
| SSRF inet_aton parser | YES | YES |
| _NoRedirect at all 15 send sites | YES | YES |
| Gate contract + work-unit enforcement | YES | NO |
| tools/run_gate.py | YES | NO |
| tools/gates.json entries | 56 | 82 |
| _OPENER global (12ms/call fix) | YES | NO — REGRESSION |
| Wildcard bind (0.0.0.0/::) allowed | YES | NO — REGRESSION |
| Semgrep key-egress gate | NO | YES |
| SSRF class fix | NO | YES |
| Redirect failover (3xx → failover) | NO | YES |
| ADR-0019 | OLDER (rounds 1-6 history) | UPDATED (round 6 history) |
| Test count delta vs master | +139 tests | +81 tests |
| `docs/docker.md` :ro correction | YES | YES |

### round6 regressions vs interim

**Regression R1 — per-request opener (12ms/call, hot-path)**:
Round 6 removed the module-global `_OPENER` and builds it per-call in
`open_keyed`. The interim commit (1db0124) MEASURED this at 11.81 ms/call vs
0.000145 ms for the module global, attributable to `build_opener` re-instantiating
`HTTPSHandler` which calls `ssl.create_default_context()` (GIL-bound C work).
`forwarder.py` calls `open_keyed` on both legs of EVERY request; plus
`speculative_execution`'s N-way race would serialize on it. The round6 commit
message does not explain or justify this removal.

**Regression R2 — wildcard bind address (0.0.0.0/::) broken**:
Round 6 moved `is_unspecified` from the loopback-exemption to the rejection list,
changing behavior from "allow" to "refuse". The test that covered this
(`test_wildcard_bind_address_is_allowed`) was removed from the test suite.
Five shipped presets (ollama, lmstudio, vllm, jan, local) use localhost bases, and
operators routinely copy `ollama serve --host 0.0.0.0` or `vllm --host 0.0.0.0`
directly into the provider base_url. On round6, this would be a startup crash with
error "refusing non-routable host '0.0.0.0'" — a regression from master.

### What round6 adds that interim lacks

**round6 addition A — Semgrep key-egress gate**:
`check_key_egress.py` replaces the evadable `check_security.py` check (e). The
Semgrep rules (`semgrep-key-egress.yml`) ban 16 transport spellings plus auth header
construction outside `netutil`. Missing semgrep is exit 2 (not silent skip). The
predecessor was defeated by a bare-name `urlopen` call. The new gate has a test
corpus (`tests/test_key_egress_gate.py`) with RED fixtures for every documented
evasion. This is strictly better than the hand-rolled linter interim retains.

**round6 addition B — SSRF class fix**:
Round 5's SSRF guard used a string `host.startswith("169.254.")` that passes decimal
(2852039166), hex (0xA9FEA9FE), and other inet_aton-faithful encodings of the
metadata address. Round 6 adds a differential test pinning `validate_base_url` to
`socket.inet_aton` behavior — any encoding the C resolver accepts is validated by
this test, not by a hand-listed corpus. This is the correct approach.

**round6 addition C — Redirect failover**:
A provider that starts 30x-ing relayed a bare 30x to the agent with no failover.
Round 6 classifies 3xx as failover. Interim does not have this.

**round6 addition D — gate_contract.py + run_gate.py removed**:
`gate_contract.py` enforces that every gate declares `min_work_units` in
`gates.json` and emits `WORK-UNITS: <n>`, failing CLOSED if missing or short.
`run_gate.py` is the local runner. These are the infrastructure that prevents
a future key-egress gate from going silent. Round 6 removes both, relying only on
the `gates.json` entry for `key-egress`.

### Decision

**RECOMMEND: interim (1db0124) as the best branch.**

Rationale:
1. **R1 (12ms/call) is a hot-path regression**: Every outbound call on every request
   pays 11.81 ms of GIL-holding CPU. For a gateway that is I/O-bound on the
   provider path, this serializes speculative execution and adds measurable latency.
   The round6 commit does not justify or acknowledge this removal.
2. **R2 (wildcard bind) is a production-breaking regression**: An operator whose
   base_url is `http://0.0.0.0:11434/v1` (copied from `ollama serve --host 0.0.0.0`)
   gets a startup crash on round6. This is a regression from master with a confusing
   error message. The interim has the regression-pinned test `test_wildcard_bind_address_is_allowed`.
3. **round6 additions are good but not decisive**: The Semgrep gate is better, the
   SSRF differential test is better, and redirect failover is correct. But the net
   is two regressions on a security fix that still carries the STOPGAP marker.

The round6 additions (Semgrep gate + SSRF class + redirect failover) should be
cherry-picked onto interim as a follow-on PR, NOT as a replacement. The interim
branch is the better base because it doesn't break production configs.

**Branch to open PR from**: `fix/provider-key-exfil-interim` (1db0124)
**Branches to close** (with reason "superseded by better-evidence branch"):
- `fix/provider-key-exfil` — superseded by v2 (new-provider aliasing exploit not covered)
- `fix/provider-key-exfil-v2` — superseded by v2-round5 (forwarder redirect still following)
- `fix/provider-key-exfil-v2-round5` — superseded by interim (gate silent-skip on missing semgrep)
- `fix/provider-key-exfil-round6` — superseded by interim (two regressions, R1 + R2 above)

---

## accept(4): Safety property verification methodology

Per the ticket rule: every claim of a safety property was verified by:
1. Identifying the MECHANISM (grep for the code, not the prose)
2. Verifying the suite passes with the change REVERTED (proving the test actually
   tests the mechanism)

Applied to:
- PRICE-REFRESHER: `derived_cost_rank` uses metered cost directly (verified in
  `price_refresher.py` + `test_meter_supersedes_sourced_quote`)
- PROVIDER-KEY-EXFIL interim: `_OPENER` is module-global (verified in `netutil.py:148`);
  `_NoRedirect` is the only redirect handler (verified in `netutil.py:70-74`);
  `test_redirect_failover.py` exercises the 302 path; `test_provider_key_exfil.py`
  observes the attacker socket.
- SSRF guard: `validate_base_url` uses `ipaddress.ip_address()` on parsed components,
  validated by `test_parser_matches_inet_aton_exactly` against the C resolver.

---

## Scope check

This ticket owns ONLY `docs/review-log/MONEY-SECURITY-LANE.md`. No other files
were edited. All findings are from reading existing branches (no code changes made).
