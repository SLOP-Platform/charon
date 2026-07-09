# TIER-SELECT — end-user tier→model selection from a curated catalog (CLI + web)

## Dependencies & sequence
**depends_on: SR-8. Wave: after SR-W3.** This ticket owns `src/charon/proxy_server.py`, which has a
single-owner chain in the SR series — SR-2 (W2) → SR-6 → SR-7 → SR-8 (W3) all own proxy_server.py.
Land this ticket AFTER SR-8 merges so the web-setup edit rebases onto the final proxy_server.py and
is never a concurrent second writer (validate_board reports this as a dep-sequenced owns hand-off,
not a RED collision). The dep is a REAL shared-owns build prereq (marked `real-dep: SR-8` on the
board), not merge-order convenience.

**Concurrency safety of the other owned files (as of 2026-07-03):** `cli.py`, `gateway.py` have NO
other LIVE owner (every prior owner is in state/done). `config.py` is deliberately NOT owned — this
ticket REUSES the existing `config.set_tiers` / `config.set_pool` / `config.add_model` APIs and adds
NO config.py change, so it does not collide with SR-5 (the live config.py owner). `model_catalog.py`
and both test files are NEW.

**Optional phasing (if scheduling wants an earlier win):** the catalog module + CLI picker do not
touch proxy_server.py and can be split into a phase-A ticket with `depends_on:` EMPTY; only the web
`/charon/setup` edit needs the SR-8 sequence. If split, keep the phase-A owns = `model_catalog.py,
cli.py, tests/test_model_catalog.py` and move `proxy_server.py, gateway.py, tests/test_tier_select.py`
into the SR-8-dependent phase-B. Shipping as ONE ticket after SR-8 is also fine.

## Shared context (grounding for a fresh session)
Charon ALREADY lets a user assign models to tiers — this ticket adds the missing **curated options +
picker**, it does not build tiering from scratch. What exists today:

- **Config store (works):** `tiers.json` in the user config dir — `{order:[low,med,high],
  members:{tier:[model_id,...]}, aliases:{name:tier}}`. APIs in `src/charon/config.py`:
  `load_tiers` / `set_tiers` / `resolve_tier` / `tier_members` / `tier_rank`; canonical tiers are
  `low/med/high` with `opus/sonnet/haiku` + `frontier/strong/economy` as ALIASES. Tier members are
  compiled into routable failover chains by `gateway._tier_pools` (`src/charon/gateway.py:138`), so a
  client requesting the tier id (e.g. `high`) already gets that tier's chain. **Routing already
  works** — this ticket only changes HOW a user chooses the members.
- **CLI (works, but blind):** `charon tier init|set|list|ranks|resolve|recommend`
  (`_cmd_tier` / `_tier_*` in `src/charon/cli.py:678-887`). `charon tier set <name> --members
  "id1,id2"` assigns members TODAY — but the user must type raw model ids **from memory**; there is
  no list of recommended options to pick from. `tier recommend <provider>` exists but is an
  LLM-judge over a provider's live catalog (different mechanism; see TIER-RECS).
- **Web (works, but blind):** `/charon/setup` has a **Tiers** fieldset with low/med/high text inputs
  + an aliases box (`_SETUP_HTML` in `src/charon/proxy_server.py:227-233`, JS `setTiers()` at
  `:279-286`) → POST `/charon/tiers` → `make_setup_handler` `tiers` action
  (`src/charon/gateway.py:463-470`) → `config.set_tiers`. Same gap: the user types comma-separated
  ids blind; no picker of recommended options.

**The GAP this ticket closes:** there is NO curated, provider-agnostic catalog of RECOMMENDED models
surfaced as the options a user picks from, at either surface. The user can assign a tier but must
already know the exact model id. Goal: the end-user, from a clean install, SELECTS tier members by
choosing from a curated catalog — at BOTH the CLI and the web UI.

Curated source of truth = the operator/eval list in
`/home/stack/charon-private/fleet/MODEL-ROLE-EVALUATION.md` §4 + §4a (frontier/strong/economy
picks). This is a BUILD-RIG doc, not shippable — the product catalog is a distilled, product-clean
copy of the *facts* (id + tier hint + access note), carrying NO fleet/SLOP/rig references.

## What to build
1. **`src/charon/model_catalog.py` (NEW — stdlib DATA, no deps, provider-agnostic).**
   A module-level list of catalog entries, each a plain dataclass/dict:
   `{id, tier_hint (low|med|high), access ("Anthropic direct" | "open weights + OpenRouter" | ...),
   note}`. **No vendor branching in LOGIC** — `access` is a descriptive string (data), not a coupling;
   the module must contain zero `if provider == "anthropic"`-style logic. Seed it from
   MODEL-ROLE-EVALUATION §4/§4a (Opus 4.8, Sonnet 5, Haiku 4.5, GPT-5.5, Gemini 3.1 Pro / 3 Flash,
   DeepSeek V4-Pro/Flash, Kimi K2.6, GLM-5.2, MiniMax M2.5/M3, Devstral 2, Qwen3-Coder-Next,
   Qwen3.6-27B, …). Provide `catalog()` → all entries and `catalog_for_tier(tier)` → entries whose
   `tier_hint` folds (via `config.resolve_tier`) to the requested tier. Keep it small + append-only;
   a stale entry is a data edit, never a code change.
2. **CLI picker (`src/charon/cli.py`).** Add a catalog-aware selection path that REUSES
   `config.set_tiers` (do not reimplement persistence):
   - `charon tier catalog [--tier high|strong|…]` — print the curated options grouped by tier hint
     (id · access · note), machine-parseable enough to eyeball and copy.
   - Extend assignment so a user picks FROM the catalog, e.g. `charon tier set high --from-catalog
     opus-4.8,gpt-5.5` (validates each id is IN the catalog; merges into that tier's members) and/or
     an interactive `charon tier pick` that shows the catalog per tier and reads a selection. Assigning
     a catalog model that has no matching served model yet should still record the tier member and
     print a hint to configure the provider/key (`charon providers add …`) — never hard-fail.
3. **Web picker (`src/charon/proxy_server.py` + `src/charon/gateway.py`).**
   - `gateway.make_setup_handler`: add a READ-only `catalog` action returning
     `model_catalog.catalog()` grouped by tier hint (so the page can render options without hardcoding
     them in JS).
   - `proxy_server.py` `_SETUP_HTML`: in the **Tiers** fieldset, render the catalog options per tier
     (datalist/checkbox list populated from the new `catalog` action) so the user CLICKS recommended
     ids into low/med/high, then Save posts the chosen members to the existing `/charon/tiers` action
     (reuse it — do not add a second persistence path). Keep the free-text box as a fallback for
     custom ids.
4. **Persistence + routing:** unchanged mechanics — members land in `tiers.json` via
   `config.set_tiers`; `_reload()` recompiles the routable tier pools via `_tier_pools`. Do not
   duplicate routing.

5. **Custom / off-catalog entry (HARD requirement — "pick from catalog OR enter your own").**
   The catalog is a convenience menu, NOT a whitelist — Charon is provider-agnostic and must never
   fence a user to a hardcoded model set. At BOTH surfaces the user can add an **arbitrary** model to
   a tier: a free-form model id + which provider (or a custom `base_url`) it belongs to + the target
   tier.
   - **CLI:** allow assigning a model id that is NOT in the catalog to a tier (e.g. `charon tier set
     high --members "my-org/custom-70b"`, or a `pick`/add flow that accepts a typed id + provider).
     If the id is unknown to the served catalog (`models.json`), register it via the existing
     `config.add_model(id, provider=…, upstream_base=…, upstream_model=…)` first, then add it as a
     tier member. Reuse the existing config APIs — do not add a config.py change.
   - **Web:** the Tiers fieldset must keep a free-text "or enter your own id" input ALONGSIDE the
     catalog picker (pick-or-type), and the existing **Add model** fieldset (id + provider +
     upstream id + base_url) remains the path to register a custom provider-backed model that then
     becomes selectable for a tier. Selecting/typing a custom id and Save posts it to the existing
     `/charon/tiers` action just like a catalog id.
   - **Validation = advisory, NOT blocking (permissive by design).** A custom id/base_url may be
     probed for reachability (reuse the existing `_probe_key` / provider-test / `validate_provider_key`
     helpers) and a WARNING surfaced if it looks unreachable or the provider isn't configured — but
     the assignment still persists. Power users pinning an id the gateway can't yet resolve are never
     hard-fenced; the warning tells them what to fix (`charon providers add …`).

**OUT OF SCOPE:** the LLM-judge recommender (parked TIER-RECS Phase B — live-catalog ranking); any
change to `config.py` tier storage; any change to the gateway hot request path. The CATALOG itself is
static curated data only — but tier membership is NOT limited to catalog ids (custom ids are
first-class, per item 5).

## Acceptance / tests
New files `tests/test_model_catalog.py`, `tests/test_tier_select.py` (hermetic — tmp config dir, no
network):
- `catalog()` is non-empty; every entry has `id`, a `tier_hint` in `{low,med,high}` (post-resolve),
  `access`, `note`; ids are unique; module imports with stdlib only (assert no third-party import).
- **CLI path:** `charon tier catalog --tier strong` lists the strong-tier options; a
  `set … --from-catalog <ids>` (or `pick`) call writes those ids into the tier's `members` in
  `tiers.json` and `charon tier list` shows them; a non-catalog id is rejected with a clear error.
- **Web path:** the setup handler `catalog` action returns the grouped options; POSTing the picked
  members to the `tiers` action persists them (assert `config.load_tiers()` members match) and
  `_reload()` makes the tier id routable (assert a tier vid appears in the served routes/pools).
- **Custom / off-catalog path (both surfaces):**
  - **CLI:** assigning an id NOT in the catalog (with a provider/base_url) registers it via
    `config.add_model` + records it as a tier member; `charon tier list` shows it; requesting the
    tier id routes to the custom model (assert the custom route/upstream is in the tier's chain).
  - **Web:** registering a custom model (Add-model fieldset) + selecting/typing its id into a tier +
    Save persists it and makes the tier route to it (assert via `_tier_pools` / served routes).
  - **Permissive validation:** a custom id whose provider is unconfigured / base_url unreachable
    still PERSISTS (assert the member is written) and only surfaces an advisory warning — never a
    hard failure / rejection.
- **End-to-end (clean install):** from an empty config dir, for BOTH a catalog pick AND a custom
  off-catalog entry, a CLI assignment AND a web `tiers` POST each result in a tier whose members
  route via `_tier_pools` (request the tier id → get the chain, incl. the custom upstream).
- Full suite green: `PYTHONPATH=src python3 -m pytest -q`.
- `bash /home/stack/charon-private/fleet/validate_board.sh` prints **no new RED** (the
  proxy_server.py owns row must show as a dep-sequenced hand-off via `depends_on: SR-8`, not a
  collision; the SR-8 dep must be marked `real-dep:` so WCI does not flag a false-blocking-dep).

## CONSTRAINTS
- **Owns ONLY:** `src/charon/model_catalog.py`, `src/charon/cli.py`, `src/charon/proxy_server.py`,
  `src/charon/gateway.py`, `tests/test_model_catalog.py`, `tests/test_tier_select.py`. Touch nothing
  else — in particular do NOT edit `config.py` (reuse its existing tier APIs).
- **Provider/agent-agnostic (HARD):** the catalog is DATA; no vendor-specific branching in logic; a
  model is an option across providers, not a coupling. Product-clean — zero fleet/SLOP/rig strings.
- Stdlib-only core (no new deps). Recommendations are ALWAYS user-overridable (free-text fallback
  stays); the catalog never forces a choice.
- Web edit rebases onto SR-8's final proxy_server.py (single-owner hand-off).

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_model_catalog.py tests/test_tier_select.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/model_catalog.py src/charon/cli.py src/charon/proxy_server.py src/charon/gateway.py && mypy src/charon/model_catalog.py && bash /home/stack/charon-private/fleet/validate_board.sh
```
