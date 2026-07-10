# Charon gateway pools — origin attribution (read-only)

No edits made to `/home/stack/code/charon` or the live 4-LOM gateway. Two layers
attributed separately per the request; `fleet/scratch/pools-analysis.md` (already
on disk) is treated as ground truth for the live shape and is cited, not redone.

## 1. THE CODE (git-tracked design, `/home/stack/code/charon`)

**Foundational design = Claude Opus 4.8, 2026-06-24 → 06-27, all with
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`:**

| SHA | Date | Commit | What it introduced |
|---|---|---|---|
| `13b6ccf` | 06-24 | `feat: ADR-0004 + MVP #1 — free-first cost-ranked role→model-pool router` | Birth of `pools.py` (`PoolEntry`/`load_pools`, free-first-then-cheapest stable sort) AND of `docs/adr/0004-*.md` — the ADR is the actual design origin, code follows same commit |
| `f89f3b2` | 06-24 | `feat: MVP #5 (core) — observing-proxy HTTP server` | Birth of `proxy_server.py` (`GatewayProxyServer`) |
| `d39e807` | 06-26 | `feat(gateway): P1 — charon gateway standalone command` | Birth of `gateway.py` |
| `d2cea2a` | 06-26 | `feat(gateway): P2 — transparent in-request failover` | Birth of `_build_routes_and_pools` (the compiler `derived_cost_rank`/pool-sort still runs through today) |
| `1eef71b` | 06-27 | `feat(connect): add charon connect <client>` | `connect.py` birth |

`git log -S'cost_rank'/-S'pools.json'` (concept-introduction search, not just
file birth) resolves to the **same** `13b6ccf` as the first hit — `cost_rank`
and the `pools.json` schema were part of the single MVP-#1 design commit, not
grown incrementally at first.

**One later foundational-tier commit is a different Claude model:**
`0b584e1` (06-27, `feat(cli): add charon tier init|set|list|ranks|resolve`) —
`Co-Authored-By: Claude Sonnet 4.6`. Still Claude, still inside the original
design week.

**Verdict on layer 1:** the pool *model itself* — `PoolEntry`, the
free-first/cheapest-first stable sort, the `pools.json`+`models.json`+
`providers.json` flat-file schema, the proxy's failover walk — was designed
and built end-to-end by **Claude Opus 4.8** in a single tight design→build arc
(ADR-0004 same commit as MVP #1), not accreted piecemeal by many models.

**Later accretion onto that base is NOT Claude, and is where the sharp edges
live:**
- `model_catalog.py` birth (`c4c418`, 07-03, `feat(TIER-SELECT): Phase-A
  catalog module`) — **no `Co-Authored-By` trailer at all.**
  `fleet/SESSION-TIER-SELECT-A.md` names the session explicitly: **DeepSeek
  V4 Pro**, run in parallel with an unrelated chain specifically because it
  doesn't touch `gateway.py`/`proxy_server.py`. This is the THIRD curated-list
  concept `pools-analysis.md` §3 flags as drifting from the other two — built
  by a different model on a different day with no cross-check against
  `pools.json`.
- `derived_cost_rank` / `cost_class` (SR-6, the mechanism that's supposed to
  make `cost_rank` a real signal instead of the inert `1000` default) —
  **two non-Claude attempts:**
  1. `208545e` (07-05) committed by the operator directly, built by
     **glm-5.2**. `model-scorecard.tsv`: `#6 sr6-auto-cost-rank … glm-5.2
     BLOCK … feature inert`.
  2. Redo by **deepseek-v4-pro**, also initially `BLOCK`
     (`reviews/REVIEW-06b-sr6-deepseek-fix.md`: fix was correct but left
     entirely **uncommitted**, "confabulated false commit history when
     asked" per the scorecard note). The fix eventually landed at merge
     commit `6ee354f` (07-05): *"Fix authored by deepseek-v4-pro,
     adversarially reviewed + verified."*
  Net: the mechanism that's supposed to make `cost_rank` real (and thus make
  the boilerplate list-order hack in §3 of `pools-analysis.md`
  unnecessary) is GLM/DeepSeek work, not Claude — and it shipped as a
  patch onto Opus's original schema rather than a redesign of it.

## 2. THE DATA (50 live pools on 4-LOM `/data`, not in git)

Cannot be git-blamed — `pools.json`/`models.json` live only on the container
volume. What's recoverable is from fleet records, and it draws a clean line:

- **No fleet coding-droid session (`model-scorecard.tsv`: glm-5.2,
  deepseek-v4-pro, kimi-k2.6, gpt-5.4, …) ever touches `/data` on 4-LOM.**
  Every scorecard row is a git-worktree build (branch, gate, pytest, "do NOT
  push"). Droids only ever produce the *code* in §1.
- **Live pool-data edits are executed by Claude manager/sub-agent sessions**
  running read-only-investigation-turned-apply-plan work — the same pattern
  as this very task. Concrete, dated evidence:
  - `fleet/POOLS-EDIT-PLAN.md` (07-03) — "READ-ONLY investigation done
    2026-07-03… This is an apply-plan for the manager to execute," followed
    by literal `curl -X POST /charon/{providers,models,pools}` commands.
  - `fleet/scratch/zen-demote-report.md` (07-07) — live 4-LOM pool reorder,
    references `POOLS-EDIT-PLAN.md §5`'s apply pattern; backs up
    `/data/*.json` before writing.
  - `fleet/scratch/dead-free-go-prune-report.md` (07-07) — same pattern,
    same backup discipline, "confirmed non-empty and valid JSON… Off-host
    copies pulled."
  All three are manager/Claude-sub-agent-executed, curl-driven, one apply-plan
  at a time.
- **The ORIGINAL ~46-50 pool population (pre-07-03, already fully formed by
  the time `POOLS-EDIT-PLAN.md` was written) has NO discoverable session
  record in `fleet/`.** No `SESSION-*.md`/`HANDOFF-*.md` before 07-03
  describes bulk-populating `models.json`/`pools.json`. The only git-tracked
  mechanism capable of it is `charon models import --all`/`charon setup`
  (Opus-authored, see §1) — but whether the operator ran that interactively,
  or an early unlogged manager session did, is **not recoverable from
  available records.** This is the honest gap: layer 2's *first* 46 pools
  predate the fleet's own session-logging discipline (or the logs were never
  written / didn't survive) — everything from 07-03 onward is well
  evidenced, everything before it is inferred from the git-tracked tooling
  only.

## 3. WHY it's shaped this way — evidence for the mechanism, not just the shape

`pools-analysis.md` §2/§5 already established the *symptom*: 82% of the 49
non-`auto` pools are one of exactly two boilerplate 4-provider-fanout
templates, `cost_rank` ties at 1000 for ~95% of routes so raw array order is
the real (undocumented) priority signal, and there's no consolidation commit
anywhere in git for the pools schema (`13b6ccf`'s shape is still today's
shape). This investigation adds the mechanism evidence for *why*:

1. **The apply-plan documents themselves are hand-authored per-model
   templates, not a generator.** `POOLS-EDIT-PLAN.md` §2b writes out 7
   `models.json` entries and 2 `pools.json` array edits by hand, one
   `curl -X POST` per model, explicitly modeled on the *existing* suffix
   convention ("bare = opencode-zen…`-go`=opencode-go…`-ng`=nanogpt…`-or`
   =openrouter") rather than replacing it. This is (a) from the user's
   framing: extending by **copying the existing template via the API**,
   never refactoring the schema to `template × override-list`.
2. **`derived_cost_rank` (SR-6) was built specifically because list-order was
   discovered to be silently load-bearing** (`208545e`'s commit message:
   "Routing defaults go cheap-first automatically instead of the hand-set
   `cost_rank:1000`") — i.e., even the one commit that tried to replace the
   order-as-priority hack with a real signal was itself layered ON TOP of the
   existing per-model-array shape rather than restructuring it, and (per
   `REVIEW-06b`) shipped **inert on the real path for months of use** because
   `add_model`/`add_models_bulk` kept stamping the same default `1000` every
   new model entry — the exact accretion habit it was meant to fix.
3. **Every dated live-edit report (`zen-demote-report.md`,
   `dead-free-go-prune-report.md`) is a single-purpose, single-session,
   backup-then-hand-edit operation against 1-2 pools at a time** — sequential
   single-pool/single-model live changes over days (07-03 → 07-07), not a
   batch redesign. No report proposes or executes a schema consolidation.
4. **No "collapse the template" commit or report exists anywhere in git or
   `fleet/`.** `pools-analysis.md §5.1` names the fix that was never done: "a
   `for any model, try [zen → go → nanogpt → openrouter] unless overridden`
   default rule would collapse ~40 of the 50 pool entries… with zero loss of
   routing behavior." Its absence, next to 15+ dated sessions that each
   *added to* the pattern instead, is itself the evidence — every session
   (Claude manager doing live data edits, DeepSeek/GLM doing code accretion)
   pattern-matched the surrounding structure rather than abstracting it,
   consistent with the user's hypothesis (a) *and* (b) simultaneously: (a)
   copy-the-template accretion at the data layer, (b) pattern-match-not-
   abstract at the code layer (SR-6 added a rank *formula* but didn't touch
   the one-array-per-model *shape* it computes ranks for).

## Honest limits

- Layer 1 (code) is fully git-blameable and precisely dated; confidence high.
- Layer 2 (data) is well evidenced from **07-03 onward** (three dated,
  named, backed-up sessions, all Claude-executed via curl) but the
  **original ~46-pool population before 07-03 has no recoverable session
  record** in `fleet/` — attribution for that earliest slice is inference
  from available tooling (Opus-built `charon setup`/`models import --all`),
  not a traced session log. If an earlier, un-retained session or manual
  operator action built it, that's not recoverable from what's on disk today.
