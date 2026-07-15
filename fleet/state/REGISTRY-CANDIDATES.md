# REGISTRY CANDIDATES — anti-accretion sweep for charon + fleet RIG + KSF

**Owner ticket:** FN5-REGISTRY-SWEEP (tier: economy, difficulty 3, work_class: ci-infra)
**Date:** 2026-07-14
**Reuse baseline:** KS29 component-registry-primitive (DESIGNED, see `state/ROADMAP.tsv:KS29`) +
F29 module-registry (DONE, PR #100/085e74f, `src/charon/gateway.py:_MODULE_SPECS`).
**Collision data source:** `bash fleet/wci-actions.sh` (run 2026-07-14T08:33:41Z).

---

## 0. Thesis — what a "registry candidate" is

A site is a registry candidate when **adding one new thing today requires edits to a
central file**, and converting it to data-driven means **adding one row + one file
with ZERO edits to a central file**. The cost of the new-row model is bounded by
the cost of the primitive (one discoverable registry declaration), not the cost of
opening the central file. The accretion class that gets eliminated is the
**N-things-edited-per-addition** cost (which the Smart-Routing F29 refactor
demonstrably collapsed from ~13 to 1).

Two anti-patterns are *not* covered (and should not be tagged as candidates):
- **Already registry-based** (e.g. `tools/gates.json`, `_MODULE_SPECS`, `_CATALOG`,
  `_POLL_ADAPTERS`, `_SCANNERS`, `_ADAPTERS`, `WorkClassTaxonomy`, `_TRANSITIONS`,
  `REGISTRY` in `connect.py`, CLI sub-commands via `argparse.set_defaults`,
  `LifecycleSeams` Callable-injection, `Scheduler.classify` Callable-injection,
  `CapacityLimiter` Protocol, `preflight-tasks/manifest.tsv` + `traps.tsv` + `units.tsv`).
- **Trivial N-branch literals** that exist for type-safety, not for routing logic
  (e.g. the 3-branch `stop_reason` in `decompose_sizing.py:659`, the 4-state
  `Autonomy` enum in `types.py:20`). A registry here would be more code, not less.

The F29 reference row in this audit (Candidate #1) is the **sealed template** for
all other conversions. Each candidate below is compared against the F29 shape:

> "Adding a new X = one data row in the registry + one module file. Editing ZERO
> god-files in <central>."

---

## 1. F29 baseline — Smart-Routing module registry (REFERENCE, ALREADY SHIPPED)

**Files:** `src/charon/gateway.py:55-111` (`ModuleSpec` + `_MODULE_SPECS`) +
`src/charon/gateway.py:305-332` (`_module_inst` loop) + `src/charon/gateway.py:154-162`
(`GatewayConfig.__getattr__` for backward-compat attribute access).
**Size:** 13 module rows, 1 factory function, 1 dataclass.
**Collision class eliminated:** the prior GatewayConfig had ~13 N-optional
module fields, and the constructor threaded each one by hand. Adding a 14th module
meant editing 4+ files. After: add one `ModuleSpec(...)` row + one module file.
**Effort to convert (already done):** 2.
**Sealed shape:** 1 dataclass (`ModuleSpec`) + 1 list (`_MODULE_SPECS`) + 1 factory
function (`_module_inst(name, state_dir)`) + 1 backward-compat `__getattr__`. The
F29 result IS the KS29 primitive instantiated for one specific scope (Smart
Routing modules). Reuse this shape literally for every other candidate below.

The KS29 primitive in the abstract would lift `ModuleSpec` to a generic
`RegistryEntry` (`name`, `schema: dict`, `scope: list[path|query]`,
`conformance: check_fn | None`, `drift: check_fn | None`,
`discovery: check_fn | None`) and feed `.ksf/registries/*.toml` files through
`ksf/registry.py:check_registry` (KS29 review-confirmed: conformance + drift
green; discovery leg flagged for fix per `state/overnight/KS29-REVIEW.md`).

---

## 2. Top-leverage candidates — ranked

Rank = (collision class eliminated × accretion frequency) ÷ effort. Anti-tie
breakers: candidates that (a) consolidate multiple existing per-instance
proliferation sites, (b) have a near-zero-risk pattern (small, isolated, tests
cover), and (c) enable downstream tickets (KS28 pattern-guard, KS20
anti-accretion, F29 second wave) win.

### Candidate #2 — `gateway.py` setup-action dispatch (HTTP path)

| Field | Value |
|---|---|
| File | `src/charon/gateway.py:416-546` |
| Pattern | if-ladder on `action: str` (10 outer + 3 inner) |
| Size | 130 lines, 10 top-level actions + 3 sub-actions inside `balance` |
| Already-registry? | NO. CLI sibling (`cli.py`) IS registry via `argparse.set_defaults(func=...)`; the HTTP path is the only odd one out. |
| Conversion | `{action: handler_fn}` dict; register CLI `_cmd_*` functions alongside so the HTTP and CLI paths share one source. Reuse the `ModuleSpec` shape — a `HandlerSpec(name, func)` per row. |
| Collision class eliminated | gateway.py is a 2-owner god-file (`PRICING-LIMITS-CHECKER`, `PROVIDER-PROBE-FIX`); adding a new setup action today means editing the same 130-line if-ladder that the two owners are already touching. After: each owner adds 1 row, no collision. |
| Effort | 2 (hours, pure mechanical extraction; existing tests already cover each branch) |
| Downstream enables | removes one of the two gateway.py collisions; F29-style second-wave cleanup |
| Reuse-check | YES — reuses the F29 `ModuleSpec` shape literally. A KS29 `Registry` with a `scope: ["http://gateway/setup/<action>"]` and per-row `conformance` could even generate the CLI subcommand argparser. |

### Candidate #3 — `intake.py` field-label dispatch + 8 parallel frozensets

| Field | Value |
|---|---|
| File | `src/charon/intake.py:201-229` + `intake.py:53-69` |
| Pattern | if-ladder on `label: str` (8 branches) + 8 parallel `_*_LABELS` frozensets |
| Size | 28 lines of dispatch + ~30 string-literal synonyms across 8 frozensets |
| Already-registry? | NO. The two halves (dispatch + synonyms) are coupled by name convention only. |
| Conversion | `dict[str, FieldDef(name=..., synonyms=..., writer=...)]` — one row per ticket field, both the dispatch and the frozenset are data-derived. |
| Collision class eliminated | "Second dimension of accretion": every new ticket-field needs both a label-set update AND a new elif branch. Two edits per addition. After: one row, both halves update. |
| Effort | 2 (hours; synonyms scattered across 8 frozensets need consolidating) |
| Reuse-check | YES — `FieldDef` is structurally `ModuleSpec` minus the factory. Could literally be a `ModuleSpec` with `factory: Callable[[Any], None]`. |

### Candidate #4 — `tool_repair.py` JSON-schema ptype dispatch (duplicated)

| Field | Value |
|---|---|
| File | `src/charon/tool_repair.py:131-154` + `tool_repair.py:195-207` |
| Pattern | if/elif on `ptype: str` (6+ branches) HARDCODED TWICE — once for coercion, once for validation |
| Size | 24 lines of duplicated dispatch, 6 types |
| Already-registry? | NO. The two chains are not linked — adding a 7th JSON-schema type (e.g. `null`) means editing BOTH sites, in lockstep, with the risk of skew. |
| Conversion | `TYPE_HANDLERS: dict[str, (coerce_fn, validate_fn)]` — one row per ptype, both halves co-located. |
| Collision class eliminated | The coercion/validation skew class — any future ptype addition that updates only one half would silently pass invalid data. |
| Effort | 2 (hours) |
| Reuse-check | YES — `(coerce_fn, validate_fn)` is a `(factory, check_fn)` tuple; matches the F29 + KS29 shape. |

### Candidate #5 — `observability.py` export target dispatch (4 full impls)

| Field | Value |
|---|---|
| File | `src/charon/observability.py:58-66` + `observability.py:80-148` |
| Pattern | if-ladder on `ObsTarget` enum (4 branches: JSONL, PROMETHEUS, WEBHOOK, LANGFUSE) + 4 full implementations |
| Size | 9 lines of dispatch + 68 lines of distinct impls (4 separate code paths) |
| Already-registry? | NO. The enum is the only seam; the impls are bound at module-load. |
| Conversion | `BaseExporter` Protocol with 4 implementations + `{target: ExporterClass}` dict. Adding a 5th (Datadog, OTLP) = one row + one file. |
| Collision class eliminated | "Adding-an-exporter-always-touches-observability.py" — currently true. After: exporter files live alongside the data row that registers them. |
| Effort | 2 (hours; the 4 impls are already separated) |
| Reuse-check | YES — `{target: ExporterClass}` is exactly the KS29 registry pattern. |

### Candidate #6 — `lifecycle.py` + `recommend.py` tier-keyword lists (duplicated, admitted-rot)

| Field | Value |
|---|---|
| File | `src/charon/lifecycle.py:333-353` + `src/charon/recommend.py:142-148` |
| Pattern | two parallel `_HIGH_KEYS` / `_LOW_KEYS` tuple-lists + duplicated `any(k in name_lower for k in _HIGH_KEYS)`-style loops |
| Size | 2 × ~10-11 string literals, logic in 2 modules |
| Already-registry? | NO. `recommend.py:140-141` EXPLICITLY admits it WILL rot as providers ship new models ("Replace with a data-driven ranking (cost × capability) when available"). |
| Conversion | `TIER_NAME_PATTERNS: dict[tier, list[str]]` (or data file); `lifecycle` and `recommend` both consume it. `_CATALOG` in `model_catalog.py` already has tier info — reuse it as the SoT, the heuristic becomes a fallback only. |
| Collision class eliminated | The "model-tiers-by-name-keyword" guess class — currently a comment-admitted rot pattern. After: a single source of truth that grows by row. |
| Effort | 2 (hours) |
| Reuse-check | YES — this is exactly KS29's stated first instance ("catalog/providers"). The KS29 row in `state/ROADMAP.tsv` calls it out. |

### Candidate #7 — `cli.py` tier sub-action dispatch

| Field | Value |
|---|---|
| File | `src/charon/cli.py:1016-1036` |
| Pattern | if-ladder on `action: str` (7 branches: init, ranks, list, resolve, set, recommend, catalog, pick) |
| Size | 20 lines, 7 actions + the 7 sub-parsers above it (`cli.py:1761-1790`) |
| Already-registry? | NO. Top-level `build_parser` is registry-shaped; only `_cmd_tier`'s body is the if-ladder. |
| Conversion | `{action: handler_fn}` dict at module scope, registered alongside the sub-parser definition. |
| Collision class eliminated | "Per-tier-sub-action code lives in the dispatch function" — after: each action file is its own module. |
| Effort | 1 (tiny one-liner-per-row) |
| Reuse-check | YES — same shape as Candidate #2. Roll into a shared `register_handler(name, fn)` helper used by both the gateway HTTP and the CLI. |

### Candidate #8 — `balance.py` mode dispatch (×3 sites in one file)

| Field | Value |
|---|---|
| File | `src/charon/balance.py:280-326` + `balance.py:604-620` |
| Pattern | if-ladder on `mode: str` (`"fixed"` vs `"poll"`) repeated 3× in this file (`remaining`, `force_poll`, `configure`) |
| Size | 3 chains × ~12 lines |
| Already-registry? | NO. `_POLL_ADAPTERS` (line 151-155) IS registry-shaped for poll adapters, but the mode dispatch itself is not. |
| Conversion | `{mode: Strategy}` with `Strategy.remaining()`, `Strategy.poll()`, `Strategy.configure()` — registered in a dict. Backward-compat: if mode not in the dict, raise a clear error. |
| Collision class eliminated | "Adding a new funding mode = editing `balance.py` in 3+ places" — currently true. After: one file per mode + one dict row. |
| Effort | 2 (hours) |
| Reuse-check | YES — `Strategy` is `ModuleSpec` with three methods. |

### Candidate #9 — `decompose.py` parallel stage lists (small)

| Field | Value |
|---|---|
| File | `src/charon/decompose.py:45` (`ROLE_DAG = ["triage","plan","implement","review","validate","close"]`) + `decompose.py:49-56` (`_ROLE_TASK_CLASS`) |
| Pattern | two parallel hardcoded lists of 6 items |
| Size | ~10 lines, 6 entries |
| Already-registry? | NO. The two lists are not linked — adding a 7th stage requires updating both. |
| Conversion | `STAGES: dict[str, Stage(role, task_class, deps)]` — one row per stage, both halves co-located. |
| Collision class eliminated | The skew class — same as Candidate #4. |
| Effort | 1 (small) |
| Reuse-check | YES — `Stage` is a `ModuleSpec` variant. |

### Candidate #10 — Fleet RIG: 49 ad-hoc shell scripts

| Field | Value |
|---|---|
| File | `fleet/*.sh` (49 files) |
| Pattern | per-instance proliferation — one script per lifecycle stage (claim/done/submit/land/release/...) |
| Size | 49 files |
| Already-registry? | PARTIAL — `canon()` centralizes ID lookup, and `repo-registry.sh` is a partial file-based registry. The dispatcher layer is the only one not registry-shaped. |
| Conversion | A `fleet/commands.tsv` or `.json` with `(cmd_name, script_path, requires_id, takes_args)`; the universal dispatcher (`fleet-droid.sh`, JOIN-PROMPT) iterates this. New lifecycle stage = 1 row + 1 file (currently 1 file with no row, dispatcher must be hand-edited). |
| Collision class eliminated | "Adding a new lifecycle stage = editing JOIN-PROMPT + handoff.md + SESSION-START + 2-3 dispatcher scripts" — currently true. After: 1 row. |
| Effort | 3 (refactor of JOIN-PROMPT and the dispatchers; the leaf scripts are fine) |
| Reuse-check | YES — reuses the F29 `ModuleSpec` shape adapted for shell. A `CmdSpec` dataclass is one line of new code. |

### Candidate #11 — Fleet RIG: 199 board `.md` files (no central ticket table)

| Field | Value |
|---|---|
| File | `fleet/board/*.md` (46 live + 45 parked + 108 archive = 199) |
| Pattern | per-ticket god-files; 6+ dispatchers (wci-actions.sh:21, wci-contention.sh:30+, claim.sh:36-65, board.sh:9-22, done.sh:18, submit.sh:11, validate_board.sh, parallelizability-gate.sh) glob `board/*.md` literally |
| Size | 199 files, 46 active owners |
| Already-registry? | NO. The only structural field is `owns:` parsed ad hoc by `awk` in `wci-actions.sh`. |
| Conversion | `tickets.json` / `tickets.tsv` with `(id, tier, work_class, owns[], branch, depends_on, status, parked)`. The `board/*.md` files become narrative, the TSV becomes the dispatch source. |
| Collision class eliminated | 4-owner `handoff.sh` collision + 3-owner `handoff-check.sh` + 2-owner `preflight.sh` (all stemming from "8 dispatchers glob the same dir"); per `bash fleet/wci-actions.sh` output 2026-07-14. After: dispatchers read the TSV once; the only file each owner edits is their own. |
| Effort | 3-4 (claim/done/submit/board/wci-actions all key off the same fields today; `validate_board.sh` has its own parser that must be merged) |
| Reuse-check | YES — reuses the same Registry schema. Tickets become a row, not a file. The `owns:` field becomes a typed list (with KS29 drift-check: did any listed file change SHA without a re-declared ticket?). |

### Candidate #12 — KS29 registry primitive ITSELF (the namesake, unbuilt)

| Field | Value |
|---|---|
| File | `state/ROADMAP.tsv:KS29` (DESIGNED, Wave F) + `state/overnight/KS29-REVIEW.md` (FIX-REQUIRED) |
| Pattern | The PRIMITIVE itself. The 3-gate primitive (conformance + discovery + drift) is the substrate that all other candidates REUSE. |
| Size | n/a — 1 abstraction + 1 reference impl |
| Already-registry? | IT IS the registry. |
| Conversion | Implement the discovery leg (`ksf/registry.py:_check_discovery` enumerating in-scope items, diffing against registered entry ids, RED on unknowns). Fix the lying docstrings. Add the red-proof test for the discovery leg. |
| Collision class eliminated | The N-registry-implementations-per-site class. Without KS29 shipped, every candidate above hand-rolls a slightly different `ModuleSpec`/`FieldDef`/`TypeHandler`/etc. After: 1 primitive, N data files. |
| Effort | 4 (it's a primitive — 1-2 days of careful design + tests + red-proof) |
| Reuse-check | THIS IS the reuse-check. Build it first; everything else is a row. |

### Candidate #13 — Fleet benchmark: 21 S0-S6 files in lockstep (3 dirs × 7 sections)

| Field | Value |
|---|---|
| File | `fleet/benchmark/graders/s[0-6].{py,js}` (7+1) + `fleet/benchmark/prompts/s[0-6].txt` (7) + `fleet/benchmark/fixtures/sections/s[0-6]/` (7) + `fleet/benchmark/selftest/goldens/s[0-6]/` (7) + `fleet/benchmark/units.tsv` (24 lines) |
| Pattern | per-instance proliferation — 4 files in 4 dirs per section, all named identically; coupled by convention, not by manifest |
| Size | 21 files in lockstep |
| Already-registry? | PARTIAL — `units.tsv` has 1 row per section (good), but no `grader_path`, `prompt_path`, `fixture_path`, `golden_path` columns. The dispatchers (`bench.sh`, `grader-daemon.py`) find files by path-string matching. |
| Conversion | Extend `units.tsv` with `grader_path, prompt_path, fixture_path, golden_path` columns. The preflight-task pattern (Candidate #14) is the reference. |
| Collision class eliminated | "Adding a new section = create 4 files in 4 dirs in lockstep, all by hand" — currently true. After: 1 row + 4 paths. |
| Effort | 3 (refactor `bench.sh`/`grader-daemon.py` path-string logic to read the columns) |
| Reuse-check | YES — reuses the preflight-tasks/manifest.tsv shape verbatim. |

### Candidate #14 — Fleet capability: `WORK_CLASSES` enum duplicated in 3+ files

| Field | Value |
|---|---|
| File | `fleet/capability/grades.py:25-40` (source) + `fleet/model-scorecard.sh:20-21` (consumes) + `fleet/BRIEF-TEMPLATE.md` (documents) + `brief_templates/*.md` (other documents) |
| Pattern | hardcoded enum literal scattered |
| Size | 6-7 work classes; duplicated ≥3 times |
| Already-registry? | NO. `grades.py` is the de-facto source but it's not enforced. |
| Conversion | `fleet/capability/work-classes.tsv` (or extend `units.tsv` with a `work_class` enum section); `grades.py` reads it; `model-scorecard.sh` reads it; the template references it. |
| Collision class eliminated | The "two tickets silently disagree on what work classes exist" class. |
| Effort | 2 (small, isolated, with a KS29 conformance check that rejects undeclared work classes) |
| Reuse-check | YES — pure enum-as-data. |

### Candidate #15 — Fleet benchmark: 11 ad-hoc selftest scripts

| Field | Value |
|---|---|
| File | `fleet/benchmark/selftest/*.py` (11 files) |
| Pattern | per-instance proliferation — discovered via `run_selftests.py` import + literal glob |
| Size | 11 files |
| Already-registry? | NO. `run_selftests.py` enumerates by import. |
| Conversion | `fleet/benchmark/selftest/manifest.tsv` (or extend `units.tsv` with a `kind=selftest` section). |
| Collision class eliminated | "Adding a new selftest = edit `run_selftests.py` import block" — currently true. |
| Effort | 2 |
| Reuse-check | YES — reuses the units.tsv pattern. |

### Candidate #16 — Fleet wave/phase definitions: split across 3 formats

| Field | Value |
|---|---|
| File | `state/ROADMAP.tsv` (TSV, has `wave` col) + `waves/smart-routing.json` (JSON, separate) + `state/ROADMAP-WCI-AUDIT.md` (prose) + `state/DEMAND-DRIVEN-BUILD-WAVE.md` (prose) + `state/RUN-NOW-WAVE.md` (prose) |
| Pattern | same concept, 3+ formats |
| Size | ~250 lines of wave-def data + ~300 lines of wave prose |
| Already-registry? | TSV is the SoT for status; wave-strategy lives in 3 places. |
| Conversion | Unify into `waves/*.tsv` with a `wave_id, ticket_id, gate_kind` schema; `wci-actions.sh` consumes it. |
| Collision class eliminated | "Operator asks 'what's in wave 4?' → 3 different files give 3 different answers." |
| Effort | 2 |
| Reuse-check | YES — pure TSV-as-registry, no new code. |

### Candidate #17 — Fleet denylists scattered in 5+ files

| Field | Value |
|---|---|
| File | `fleet/land.sh` (header comment "deny-listed") + `fleet/no-claude-executor.sh` (EXECUTORS array) + `fleet/leak-guard.sh` (worktree rules) + `tools/check_workflows.py` (action-pin) + `tools/check_public_clean.py` (patterns) + `tools/hooks/pre-commit` (calls the above) |
| Pattern | parallel denylist-shaped behaviors encoded as data-in-comments or small arrays |
| Size | ~5-10 entries per list, 5+ files |
| Already-registry? | NO. |
| Conversion | `policies/denylists.tsv` with `(scope, pattern, source_ref, last_reviewed)`. Each check_*.py loads its slice. |
| Collision class eliminated | The "three denylists silently disagree on what's forbidden" class. |
| Effort | 2-3 (5+ files to touch; KS29 conformance check enforces consistency) |
| Reuse-check | YES — pattern-as-data is KS28's stated scope (collapse pattern-scanning gates into one registry-driven pattern_guard). |

### Candidate #18 — `gateway.py:305-332` `_module_inst` itself (KS29 instance)

| Field | Value |
|---|---|
| File | `src/charon/gateway.py:305-332` |
| Pattern | The F29 module factory, hand-rolled. Same shape as KS29's `Registry`. |
| Size | 28 lines, hardcoded for the Smart-Routing scope |
| Already-registry? | YES (it's a registry), but it's hand-rolled, not KS29-instantiated. |
| Conversion | Replace `_module_inst` body with `Registry.from_toml("_MODULE_SPECS.toml").resolve(name)`. Drift-check: `tools/check_module_specs.py` enforces that every ModuleSpec.attr is consumed by `__getattr__` and vice versa. |
| Collision class eliminated | "The F29 registry and the future KS29 registry drift apart in shape" — currently a latent risk. |
| Effort | 2 (mechanical; the existing 14 tests cover the behavior) |
| Reuse-check | YES — this IS the reuse-check. F29 IS the first KS29 instance; explicitly making it a KS29 instance removes the latent drift risk. |

---

## 3. Sites NOT in scope (deliberately)

| Site | Why excluded |
|---|---|
| `_MODULE_SPECS` itself | Already the reference; further refactor is Candidate #18. |
| `tools/gates.json` (17 entries) | Already registry. |
| `provider_presets/*.py` (27 entries) | Already registry (4 category files merged in `__init__.py`). |
| `model_catalog.py` (16 entries) | Already registry. Comment at line 29 correctly states "APPEND-ONLY". |
| `connect.py:389-424` (5 clients) | Already registry (`REGISTRY: dict[str, ClientSpec]`). |
| `scanners.py:202-206` (3 scanners) | Already registry. |
| `balance.py:151-155` (3 poll adapters) | Already registry. |
| `response_adapters.py:100` (1 adapter) | Already registry. |
| `intake.py:272` (1 adapter) | Already registry. |
| `engine/board.py:44-49` (4 states) | Already registry. |
| `capability/taxonomy.py` (6 classes) | Already registry (`WorkClassTaxonomy`). |
| `decompose_sizing.py:659-661` (3 stop-reason branches) | Trivial literal; a registry would be more code. |
| `engine/scheduler.py:73-86` (3-branch `classify`) | Trivial + already Callable-injected. |
| `types.py:20-29` (`Autonomy` enum) | Declarative, not routing. |
| `lifecycle.py` core | All 4 components are seam-injected (`LifecycleSeams`); no if-ladder. |
| `engine/claim.py`, `engine/capacity.py`, `engine/reconcile.py`, `engine/semantic_proof.py` | Protocol-based, no if-ladder. |

---

## 4. Cross-cutting observations

### 4.1 The pattern is the same everywhere

Strip the F29 prose and every candidate reduces to the same shape:

```
_specs: list[Spec] = [
    Spec("name_a", factory_or_check_a, ...),
    Spec("name_b", factory_or_check_b, ...),
    ...
]

def _resolve(name: str) -> Any:
    for spec in _specs:
        if spec.name == name:
            return spec.invoke(...)
    return None  # or raise
```

The 18 candidates are 18 instantiations of this pattern across 18 different
scopes. **Ship KS29 once; the next 17 candidates become "register this scope"
tickets, not "design a registry" tickets.**

### 4.2 The collision hotspots validate the ranking

From `bash fleet/wci-actions.sh` (run 2026-07-14T08:33:41Z):

- `fleet/handoff.sh` (4 owners: HANDOFF-MECHANIZE, HANDOFF-PIPEFAIL, REPO-DECL-CENTRAL, STARTUP-CONTEXT-DIET) — directly addressed by Candidate #11 (tickets table = 1 row per owner)
- `fleet/handoff-check.sh` (3 owners) — same
- `fleet/preflight.sh` (2 owners) — same
- `src/charon/gateway.py` (2 owners: PRICING-LIMITS-CHECKER, PROVIDER-PROBE-FIX) — directly addressed by Candidate #2 (HTTP setup dispatch = 1 row per owner)
- `src/charon/forwarder.py` (2 owners: FAIL-LOUD-CONTRACT, FORWARDER-RECONCILE) — out of scope (money path; refactor risk > benefit)
- `src/charon/gate_runner.py` (2 owners: GATE-INTEGRITY-B, WIRE-MOCKLINT-ENFORCE) — addressed indirectly by Candidate #12 (KS29 ships; both owners consume the registry instead of editing the dispatcher)
- `src/charon/config.py` (2 owners: DELETE-STATIC-RANK, PROVIDER-URL-HELPER) — note: refers to `charon-private/fleet/config.py`, not the product

The 4-owner and 3-owner collisions on `fleet/handoff*.sh` are the **single highest-leverage target** (Candidate #11) because one conversion unblocks 4 currently-serialized tickets.

### 4.3 KS28 (consolidate-pattern-guard) is a special case

KS28's stated goal: "collapse the pattern-scanning gates (leak_guard, no_pipe_mask
+ KS13 security, KS19 fragility, revert-patterns) into ONE registry-driven
pattern_guard meta-gate." This is **literally Candidate #17 + a KS29 conformance
check that every pattern row has a `last_reviewed` timestamp < 90 days**. The
candidate is the data; KS28 is the gate that consumes the data.

KS20 (lens-anti-accretion) is the same pattern one level up: it's the META gate
that checks **every other gate file is itself a row in a registry, not a hand-rolled
script**. Candidate #15 (selftest manifest) is one instance; Candidates #13, #14
are others.

### 4.4 The RIG candidates are not blocking, but the PRODUCT candidates are

The fleet RIG candidates (#10, #11, #13-#17) are quality-of-life wins — they
reduce future friction but don't unlock any single ticket that can't ship
without them. The PRODUCT candidates (#2-#9, #18) directly address the
2-owner `src/charon/gateway.py` collision and the F29 second-wave cleanup
explicitly called out in `state/ROADMAP.tsv:KS29 row: "Instances: ... catalog/providers"`.

### 4.5 Anti-tie-breaker: which candidates are KS29-bootstrap-blockers?

**None.** KS29 is the substrate; every other candidate is an instance. Build
KS29 first, then run the candidates in dependency order (each adds a row to
`.ksf/registries/`).

---

## 5. Recommended build order

**Build order = KS29 dependency order**, not anti-accretion leverage order. The
highest-leverage candidates (#2, #11) can be retrofitted to KS29 post-hoc;
building them on the hand-rolled F29 shape first would create the very drift
risk Candidate #18 is meant to prevent.

| Step | What | Why this order | Eff |
|---|---|---|---|
| 1 | Ship **KS29** (Candidate #12): conformance + drift + discovery gates; fix lying docstrings; red-proof the discovery leg per `state/overnight/KS29-REVIEW.md` FIX-REQUIRED #1+#2. | Without this, every step below hand-rolls. | 4 |
| 2 | **F29 → KS29 instance** (Candidate #18): rewrite `_module_inst` to consume `.ksf/registries/modules.toml`; add a KS29 drift check that the 13 specs match `__getattr__`'s consumed names. | F29 is the reference; explicit alignment removes the latent drift. | 2 |
| 3 | **Catalog/providers → KS29 instance** (Candidate #6): move `lifecycle.py:_HIGH_KEYS` + `recommend.py:142-148` + `_CATALOG` tier info into a single `.ksf/registries/catalog.toml`; `lifecycle` and `recommend` consume it. | KS29's stated first instance ("catalog/providers" in `state/ROADMAP.tsv:KS29`). | 2 |
| 4 | **HTTP setup dispatch → registry** (Candidate #2): `{action: handler_fn}` dict; CLI `_cmd_*` functions register alongside. | Unblocks the 2-owner `gateway.py` collision. | 2 |
| 5 | **Tickets table → TSV/JSON** (Candidate #11): `tickets.json`; 8 dispatchers read it; `board/*.md` becomes narrative only. | Unblocks the 4-owner `handoff.sh` + 3-owner `handoff-check.sh` + 2-owner `preflight.sh` collisions. | 3-4 |
| 6 | **Pattern-guard → KS28/29** (Candidate #17 + KS28): one `pattern_guard` meta-gate, patterns as data. | Delivers KS28. | 2-3 |
| 7 | Smaller wins: #3 (intake), #4 (tool_repair ptype), #5 (observability exporters), #7 (cli.py tier), #8 (balance mode), #9 (decompose stages), #13 (benchmark sections), #14 (work_classes), #15 (selftest manifest), #16 (waves unify). | Each is independent; can fan out across multiple droids. | 1-3 each |

After step 5, `bash fleet/wci-actions.sh` should report zero 2+ owner collisions
on the top files. The remaining candidates are quality-of-life.

---

## 6. Output feeds

- **F29 second wave** (post-merge): candidates #2, #3, #4, #5, #7, #8, #9, #18.
- **KS20 anti-accretion** (Wave E): candidates #10, #11, #13, #15, #16, #17 — every fleet site that passes KS20's "this file is hand-rolled" check.
- **KS28 pattern-guard** (Wave E): candidate #17 specifically (collapse pattern-scanning gates into one registry-driven meta-gate).
- **KS29 component-registry-primitive** (Wave F): candidate #12 (ship it) + all the other candidates become "register this scope" tickets instead of "design a registry" tickets.
- **KS24 lens-drift** (Wave E): candidates #11 and #18 specifically (the drift-check that declared-owns-files match actually-edited-files is exactly the drift leg of KS29 applied to ticket scope).

---

## 7. Audit metadata

- Sweep covered: `/home/stack/code/charon/src/charon/` (71 modules, ~18,900 lines), `/home/stack/charon-private/fleet/` (49 .sh scripts + 199 board files + 18 benchmark subdirs), `/home/stack/code/charon/.ksf/`, `/home/stack/code/charon/tools/` (18 files including `gates.json` registry + `inert-code-disposition.json` exception registry + 16 `check_*.py` enforcers), `/home/stack/code/charon/tools/_vendor/` (KSF surface: 2 vendored modules).
- Sweep date: 2026-07-14
- Collision data: live `bash fleet/wci-actions.sh` output captured 2026-07-14T08:33:41Z (8 collision hotspots, 4 of which the candidates directly address).
- Sites inventoried: ~85 (18 in-scope, ~20 already-registry, ~47 trivially excluded).
- Reuse-check: **all 18 candidates reuse the KS29 primitive shape** (or, for #12, ARE the primitive). No candidate hand-rolls a new registry mechanism.
