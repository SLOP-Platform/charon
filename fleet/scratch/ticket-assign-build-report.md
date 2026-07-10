# Build #14 — ticket→best-agent AUTO-ASSIGNMENT (rig-level WCI)

Status: BUILT, self-tested, not committed (report-only per brief). Rig-level only —
no `src/` touched (product), no push.

## STEP 0 — grounding findings

- **Tickets**: `fleet/board/<ID>.md`, plain-text `key: value` meta lines (`tier`,
  `branch`, `depends_on`, `owns`, `prompt`, `scope`, `accept`) parsed by `board.sh`'s
  awk `meta()` (first matching line wins, no multi-line continuation support — I
  mirrored that exactly in Python). **No ticket declares a `work_class` field today**
  — the taxonomy exists in `model-scorecard.sh`'s `VALID_CLASS` but nothing writes it
  onto tickets yet. `assign.py` supports an *optional* `work_class:` meta key (future
  board authors can add it) and always accepts `--work-class` as an explicit
  override/declaration; if a ticket has neither, it gets an honest generalist
  fallback with a printed NOTE, never a silent guess.
- **D&S**: `depends_on: A, B` (comma-separated, case-insensitive canonicalized against
  board basenames) checked against `state/done/<id>` — this is exactly `_lib.sh`'s
  `deps_done()`, reimplemented in Python (`assign.py::unmet_deps`) so `assign.py` has
  no bash dependency. A ticket with any unmet dep is **refused**, never assigned.
- **model-scorecard.tsv**: 32 data rows today, 4 models with real coverage
  (gpt-5.4, glm-5.2, hy3-preview-or, kimi-k2.6) across 7 work_classes (bugfix,
  money-path, routing, ci-infra, refactor, greenfield-feature, frontend) + 2 older
  `live`-source routing/money-path rows (glm-5.2, deepseek-v4-pro). `model-scorecard.sh`
  is bash/awk and only renders a human text table — I parse the TSV directly in
  Python (`capability/grades.py::ScorecardGradesProvider`) rather than shelling out
  and scraping that table.
- **session-bridge**: confirmed via a live `board(repo="charon")` call during
  grounding — schema is `session_id/name/ticket/repo/status/blockers/branch/files/...`,
  **no `model` field**. Only one live session exists right now: `yoda` (the manager,
  `status=in-progress`, stalled). No live droid/model-tagged sessions to key off of.
  The underlying transport is `python3 /home/stack/.config/opencode/session-bridge/proxy.py`
  speaking JSON-RPC over stdio against a unix socket (`/home/stack/.charon/bridge.sock`)
  — same pattern `fleet/checks/bridge-health.py` already uses, which I reused for the
  live `SessionBridgeAvailability` implementation.
- **Cost-tier data**: not in model-scorecard.tsv (its `tier` column is *benchmark
  difficulty* 0–4, a different axis). Sourced from `src/charon/model_catalog.py`'s
  `catalog()` (read-only import, `id -> tier_hint` low/med/high) + a local copy of
  `config.py`'s `TIER_ALIASES` (frontier/strong/economy -> high/med/low; opus/sonnet/
  haiku likewise) since the `charon` CLI (`charon tier resolve/ranks`, used by
  `claim.sh`) is not importable in this sandbox (`ModuleNotFoundError: charon`) —
  same resilience pattern `fleet-droid.sh` already uses for that exact failure mode.
  2 of the 4 scored models (`gpt-5.4`, `hy3-preview-or`) aren't in the curated
  catalog at all — treated as `tier_hint=None` ("unknown", never wrongly excluded).

## Files (all new, all under `fleet/`, none under `charon/src`)

- `fleet/capability/grades.py` — `GradesProvider` interface + `ScorecardGradesProvider`
  (today's impl, reads `model-scorecard.tsv` directly) + `WORK_CLASSES`/`GENERALIST`
  taxonomy (duplicated from `model-scorecard.sh`'s `VALID_CLASS`, documented as
  must-stay-in-lockstep) + `get_tier_hint()`/`resolve_tier_alias()`.
- `fleet/capability/availability.py` — `AvailabilityProvider` interface,
  `StaticAvailability` (fake, dependency-injectable), `SessionBridgeAvailability`
  (live, shells to `proxy.py`). Documents the "no `model` field" gap plainly.
- `fleet/capability/assign.py` — `assign()` core + CLI. Ticket-meta reader
  (`read_ticket_meta`), D&S dep checker (`unmet_deps`), ranking/rationale.
- `fleet/capability/selftest.py` — the proof-of-effect gate (below).
- `fleet/assign.sh` — thin wrapper (`exec python3 capability/assign.py "$@"`).

## `assign()` logic

1. **D&S gate first**: unmet `depends_on` -> `refused=True`, no pick, ever.
2. **Grade** every candidate model at the requested `work_class` via the provider.
   Score = `merge% - block%` (a `FIXES` verdict counts toward neither numerator, so
   it drags the score down without an explicit BLOCK — "partial credit is not a
   clean win"). No direct data for that class -> generalist aggregate (all rows for
   that model), flagged `fallback_used=True` in the rationale, never silently mixed
   in as if it were direct evidence.
3. **Filter**: cost-tier (only excludes when the model's tier is *known* and
   mismatches — unknown tier passes through, documented) and availability (only
   excludes `busy`; `unknown` passes through).
4. **Sort** eligible candidates: score desc -> mean bench score desc -> mean cost
   asc -> mean time asc -> model id (deterministic tie-break chain, no randomness).
5. **Rationale** names the pick's stats, the runner-up, and any excluded candidate
   that out-scored the pick (so a human can audit *why* the top-graded model wasn't
   chosen — never a black box).

CLI: `fleet/assign.sh --work-class ci-infra`, `fleet/assign.sh SR-13`,
`fleet/assign.sh SR-13 --work-class refactor --tier strong`, `--claim SESSION_ID`
(claim-on-recommend, behind an explicit flag, not the default — MVP is RECOMMEND).

## PROOF-OF-EFFECT — results (real `model-scorecard.tsv`, `python3 capability/selftest.py`)

All 8 checks **PASS**. Per-class picks on real data:

| work_class | picked | why |
|---|---|---|
| ci-infra | **glm-5.2** | only model with a clean MERGE (others: FIXES, scores 0) — landslide |
| money-path | **glm-5.2** | tied at 100 with gpt-5.4/kimi-k2.6/deepseek-v4-pro; cheapest ($0.0088) |
| routing | **kimi-k2.6** | tied at 100 with gpt-5.4/hy3-preview-or; cheapest ($0.0027) |
| refactor | **hy3-preview-or** | tied at 100 with 3 others; cheapest by cost, then fastest |
| bugfix | **glm-5.2** | tied at 100; cheapest ($0.0029) |
| greenfield-feature | **kimi-k2.6** | tied at 100; cheapest ($0.0000) |
| frontend | **kimi-k2.6** | tied at 100; cheapest ($0.0048) |

**Differentiation is real, not inert**: 3 distinct models win across 7 classes
(glm-5.2, kimi-k2.6, hy3-preview-or) — not everyone routes to the same model.
`money-path` never picks `hy3-preview-or` (its lone BLOCK verdict) and ranks it
dead last (`['glm-5.2','kimi-k2.6','gpt-5.4','deepseek-v4-pro','hy3-preview-or']`).

**Availability changes the pick**: marking `money-path`'s ungated top pick
(`glm-5.2`) `busy` via an injected `StaticAvailability` moves the recommendation to
`kimi-k2.6` (next-best eligible), and `glm-5.2` shows up visibly `EXCLUDED` in the
ranked list rather than silently vanishing.

**D&S**: an injected unmet blocker refuses assignment outright (`refused=True`,
`picked=None`).

### Honest caveat (stated, not hidden)

The availability-changes-the-pick proof uses an **injected fake**, not a live
`SessionBridgeAvailability` assertion — the real board today has zero model-tagged
sessions (only the manager `yoda`), so there is nothing live to differentiate on
yet. The live path (`--live-availability`) IS wired and was smoke-tested against
the real bridge during this build (`assign.sh --work-class routing
--live-availability` -> connects, sees 1 session, correctly resolves `unknown` for
every model since none match `yoda`) — it just has no live signal to prove
differentiation with *today*. This will start producing real signal automatically
once droid sessions register with model-identifying names/tickets; no code change
needed then.

## Live CLI smoke tests (this session, all against the real repo/board, non-destructive)

- `assign.sh --work-class ci-infra` -> picks glm-5.2, shows runner-up kimi-k2.6.
- `assign.sh SR-13 --work-class refactor` -> refused, blocked on `DRAIN-ROUTING`
  (real unmet dep from the real board) — proves the D&S gate reads real ticket state.
- `assign.sh WCI-FOLLOWON` -> no declared `work_class`, NOTE printed, generalist
  fallback picks gpt-5.4; separately shows `kimi-k2.6 scored >= pick but was EXCLUDED:
  tier mismatch` (ticket declares `tier: opus`/frontier, kimi-k2.6 resolves to `med`)
  — proves the cost-tier filter + exclusion-transparency both work against a real
  ticket.
- `assign.sh NOPE-DOES-NOT-EXIST --work-class bugfix` -> clean error, exit 2.
- `assign.sh` (no args) -> argparse usage error, exit 2.
- `assign.sh --work-class docs` / `--work-class tests` (zero ledger rows for either
  class) -> generalist fallback engages correctly, doesn't crash or return nothing.
- `--claim` was **not** exercised against the live bridge (code-reviewed only) —
  claiming a real ticket during this build session risked colliding with the actual
  fleet's in-flight work; the claim call itself is the same one-line JSON-RPC POST
  pattern already proven live by the `board`/`--live-availability` smoke test above.

## Proposed commit message (not committed — manager's call)

```
feat(fleet): ticket->best-agent auto-assignment (build #14, rig-level WCI)

Shared capability brain (grades.py's GradesProvider interface, backed today by
ScorecardGradesProvider reading model-scorecard.tsv; availability.py's
AvailabilityProvider, backed by SessionBridgeAvailability) + assign() ranking/
rationale + assign.py/assign.sh CLI entrypoint. First consumer of the capability
layer described in POOLS-REDESIGN-ADR-v2.md's "two consumers" section, ahead of
the gateway-routing consumer (gated separately on decision-differentiation).

Proof-of-effect (capability/selftest.py, all PASS): 3 distinct models win across
7 work_classes on real scorecard data (not inert); money-path never picks the one
model with a BLOCK verdict; marking the top pick unavailable demonstrably moves
the recommendation to next-best; a blocked ticket is refused, never assigned.
```

## Open items / next-session flags

- `work_class:` is not yet a board-ticket meta convention — someone (a future
  ticket-authoring pass, or a board-file lint) needs to start declaring it for
  `assign.py TICKET-ID` (no `--work-class` override) to be genuinely automatic
  rather than falling back to generalist or requiring the caller to know the class.
- `gpt-5.4`/`hy3-preview-or` aren't in `model_catalog.py` yet, so cost-tier
  filtering can't act on them (`tier_hint=None`, passes every tier filter). Low risk
  today (small candidate pool) but will matter once more benchmark-only ids appear.
- Availability is genuinely inert on *today's* live board (no model-tagged
  sessions) — this is a data gap, not a code gap; the wiring is real and will start
  differentiating the moment droid sessions carry model-identifying names/tickets.
