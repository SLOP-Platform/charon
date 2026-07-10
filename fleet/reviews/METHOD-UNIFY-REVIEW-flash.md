# ADVERSARIAL REVIEW: Charon work-method vs SLOP/mediastack work-method → one portable "Do work" mechanism?

**Reviewer model:** deepseek-v4-flash  |  **Reviewer session:** mace-windu  |  **Date:** 2026-07-10
**Method:** READ-ONLY; all sources read, zero code/modification performed.

---

## VERDICT

**QUALIFIED YES — the SLOP method is NOT obsolete, but it IS over-engineered for its current project,
and the two methods CAN converge into one portable mechanism (Obol) provided Obol absorbs SLOP's
physics-based progress detection, proof-based close, and tier enforcement before Phase 1 ships.**

Confidence: **MEDIUM** — the gap between Obol's design (OBOL-PHASE-1-DESIGN.md) and what both methods
actually need in production is small but critical; if those gaps are closed before Obol lands, convergence
succeeds. If Obol ships as currently designed, it will be a regression for the mediastack project and the
operator will not migrate.

---

## SxS TABLE

| Axis | Charon (fleet rig) | SLOP/mediastack | Better? |
|---|---|---|---|
| **Ticket store** | Flat-file `.md` in `board/`, key:value frontmatter, parsed by bash awk | SQLite `tracking.db` with migrations, taxonomy, `query.py` CRUD | SLOP ✓ (structured query, schema enforcement, provenance) |
| **Ticket query** | `grep`, `awk`, `validate_board.sh` re-parses every time | `python3 tracking/query.py open\|batch\|optimize` — instant, parameterized | SLOP ✓ |
| **Work decomposition** | WCI contention-driven (wci-contention.sh ADVISORY) + leading budget gate (ADR-DECOMPOSED-BY-DESIGN, designed) | Wave/stream decomposition with pre-flight complexity gating (`wave_complexity.py`) | TIE ~ (both have rigor; Charon's is still designing, SLOP's is operational) |
| **Worker launch** | `fleet-droid.sh <tier>` (Claude tabs) + `charon-run.sh` (opencode, cross-model failover, non-Claude) | `droid_loop.sh --model <sonnet\|opus>` (Claude Code tabs only) | Charon ✓ (multi-model, non-Claude, headless) |
| **Parallelism** | `owns:`-driven disjointness, `validate_board.sh` collision RED (hard fail), `wci-contention.sh` advisory | Wave/stream fan-out with merge-time conflict resolution, keep-both for known additive files | Charon ✓ (preventative; SLOP relies on merge-time reconciliation) |
| **Coordination (inter-agent)** | Session-bridge: typed inbox, epoch-fenced claim, poll/ack | Mailbox (`MAILBOX.md`): append-only, `token.sh post`, social protocol (TEAM-PROTOCOL.md) | SLOP ~ (bridge is cleaner but mailbox has physics-progress detection bridge lacks) |
| **Liveness** | Session-bridge TTL (600s) + `last_seen` timestamp, graduated nudge/escalate/purge | `heartbeat.sh` per-turn + `warden.sh` (physics-based: hashes branch HEAD + diff + message count) + `check_progress.sh` | SLOP ✓ (physics-based progress check catches lying; bridge only sees timestamps) |
| **Review/merge gates** | Adversarial by default, DRAFT PRs via `gh`, `handoff-check.sh` mechanized, `preflight.sh` reds registry, CI = full gate (not pytest alone) | TCPM (Team-Consensus Push Model), independent review for "significant" changes, `merge_wave_to_main.py` with pre-flight, `ms-enforce` | TIE ~ (Charon's is cheaper but less thorough for multi-agent; SLOP's is heavier but catches more) |
| **Handoff/durability** | `handoff-check.sh` validates SHAs + paths + sections exist; `state/done\|claims\|submitted` touch-files | `end_session.sh winddown` fires successor respawn; `continuity/<item>.md` per-item carriers survive reset; `close --proof` validates GROUND refs | SLOP ✓ (proof-based close > touch-file; respawn continuity > handoff doc) |
| **Model routing** | Advisory (`recommend-model-for-droid-work`, COORDINATOR-DOCTRINE-v2 §Rule 7); nothing mechanically blocks weak model from strong work | Tier enforcement at claim time (`tier_route.py` DENIES Sonnet from Opus items); `[sonnet-ok]` tag gate | SLOP ✓ (mechanical enforcement > advisory) |
| **Token/cost discipline** | Detailed empirical measurements (~10k residue break-even, delegation tax measured at ~24s, ~45–160s round-trip), Rule 2 residue floor | "Sonnet for doc/hygiene, Opus for everything else" — no measured break-even | Charon ✓ (measured cost model beats heuristic) |
| **Portability to new project** | Obol designed as stdlib-only, no `/home/stack` paths, no fleet assumptions | Tightly coupled to `.claude/` dir structure, `tracking/query.py`, Claude Code CLI | Charon ✓ (by design; SLOP is inextricable from Claude Code) |
| **Maintenance surface** | ~116 files in `fleet/` + ~163 board tickets; bash-heavy but single-repo scoped | ~114 files in `mailbox/` alone + ~193 wave files + `tracking/` + `.claude/`; extremely heavy | Charon ✓ (SLOP's surface is ~3× larger for one project) |

---

## WHERE SLOP WINS (the refutation — concrete things SLOP does better)

### 1. SQLite tracking.db is genuinely better than flat-file tickets
Charon's `board/*.md` tickets use ad-hoc key:value frontmatter parsed by bash awk every time
(`validate_board.sh:24-28`). No schema enforcement, no migrations, no join queries, no provenance chain.
SLOP's `tracking/query.py` gives structured `open`, `batch`, `add`, `close --proof`, `decisions`,
`optimize` commands against a normalized SQLite schema with taxonomy (`tracking/taxonomy.py`), schema
migrations (`tracking/migrations/`), and GROUND-validated close proofs (`query.py:344-389`).
**This is the single strongest argument against "drop SLOP's method."** A portable method must include
SQLite-backed structured ticket storage. Obol's design (OBOL-PHASE-1-DESIGN.md:94-154) does include this —
so convergence is feasible — but as of today Charon the fleet rig does NOT have it, and the build-rig
still uses flat files.

### 2. Physics-based progress detection (warden) is missing from session-bridge and Obol
SLOP's `check_progress.sh` hashes branch HEAD + uncommitted diff + mailbox POSTED count + heartbeat item
per droid (`TEAM-PROTOCOL.md:37-43`). A droid that says `WORKING` but produces no filesystem change for
≥300s gets nudged, then escalated, then reaped — regardless of its `last_seen` timestamp.
Charon's session-bridge only tracks `last_seen` — a session can claim "in-progress" while doing nothing.
Obol's `sessions.busy_since` + `max_busy_s` (OBOL-PHASE-1-DESIGN.md:164-165) is the same dead-reckoning
timer, NOT a progress detector. **A portable "do work" mechanism that cannot distinguish "working" from
"lying about working" is incomplete.** This is the critical gap in Obol's current design.

### 3. Tier enforcement at claim time (mechanical, not advisory)
SLOP's `claim_work.sh` reads `tier_route.py` which classifies items against the real tracking DB: a
Sonnet droid is PHYSICALLY DENIED any non-sonnet-safe item (`TEAM-PROTOCOL.md:194-206`). The guard goes
RED on attempted violation, proven by `test_tier_route.sh`.
Charon's COORDINATOR-DOCTRINE-v2 §Rule 7 says "right-size with model FLOOR at gates" and §Rule 2a says
"weak coordinators delegate ONLY from whitelist" — but these are DOCTRINE, not MECHANIZED. Nothing in
`fleet-droid.sh` or `claim.sh` physically prevents a Haiku-tier droid from claiming a security-critical
ticket.
Obol's `obol claim --tier <tier>` (OBOL-PHASE-1-DESIGN.md:59) exists but there's no tier-route
enforcement logic in the design — no `tier_route.py` analogue, no "deny weak session from strong work"
invariant.

### 4. Proof-based close discipline
SLOP's `close --proof <ref>` requires a GROUND-resolving reference (committed artifact path or origin/main
commit SHA) validated against the actual git object store (`query.py:344-389`). NO-PROOF closes are counted
by a shrink-only ratchet. A close claiming "done" without a real ref is DISTINGUISHED from a GROUND close.
Charon's `state/done/<ticket>` is an empty touch-file (`touch fleet/state/done/WCI.md`). No proof, no
validation, no distinction between "the work was actually done" and "someone touched a file."
Obol's `obol transition --status done` (OBOL-PHASE-1-DESIGN.md:64) doesn't specify any proof requirement.
This is a regression waiting to happen if Obol ships without close-proof validation.

### 5. Respawn/continuity — session death doesn't lose context
SLOP's `end_session.sh winddown` fires a fresh-context successor in the same tab (`TEAM-PROTOCOL.md:216-239`).
`continuity/<item>.md` per-item carriers (append-only, keyed by item, not by session) survive role resets
and session death. A successor reads "what my predecessor left in-flight" from the item, not from the dead
session's memory.
Charon's handoff is a single markdown file (`HANDOFF-2026-07-10.md`) validated by `handoff-check.sh`
— rigorous for what it is, but it's session-scoped. If the session dies mid-handoff without writing the
file, the continuity is lost. No per-item carriers.
Obol has no respawn mechanism at all. Obol's Phase 1 design ("one daemon per project, human-gated")
explicitly excludes autonomous execution and session lifecycle management.

---

## WHERE CHARON WINS

### 1. Multi-model, non-Claude worker launch
`charon-run.sh` (fleet/charon-run.sh:1-41) is a headless multi-model launcher that fails over across
models (not just providers). It routes through the Charon Gateway (4-LOM), which connects to OpenAI,
OpenRouter, and other provider types — zero dependency on Claude Code CLI.
SLOP is entirely Claude Code (Anthropic-only). If Claude were unavailable, SLOP stops. If Anthropic
changes its API, SLOP must adapt. Charon can route work to any model on any provider.

### 2. Disjoint-owns parallelism (preventative collision avoidance)
Charon's `validate_board.sh` HARD-FAILs on `owns-collision LIVE (no dep ordering)` — it mathematically
ensures two concurrent tickets cannot touch the same file unless one explicitly depends on the other
(`validate_board.sh:134-153`). The WCI enforcer further flags `false-blocking-dep` (a ticket blocking on
another where owns are disjoint and the dep is unjustified) — ensuring the dep graph is honest
(validate_board.sh:174-198).
SLOP resolves collisions at MERGE TIME via keep-both-whole-block for known additive files
(`AUTONOMOUS-DEFAULTS.md:286-332`). This works but it's reactive — the work has already been done and
must be reconciled. Charon prevents the collision from happening.

### 3. Token economy discipline (measured, not guessed)
COORDINATOR-DOCTRINE-v2 is the result of 4 adversarial reviews + an empirical measurement. It contains
concrete numbers: delegation break-even at ~10k residue tokens, ~24s measured round-trip (~45–160s
estimated), prompt caching discount factor f≈0.1, cold-cache spawn tax paid in full. The
`coordinator-context-preservation + parallelism` reframing is backed by a natural experiment (~222k tokens
kept out of coordinator).
SLOP's model selection rubric (`ROBOT.md:1282-1295`) says "Sonnet for bounded implementation, Haiku for
mechanical, Opus for irreducible judgment" — which is reasonable but has NO measured cost basis. No
token accounting, no break-even analysis, no empirical delegation threshold.

### 4. Decomposed-by-design leading gate (prevents god-files)
ADR-DECOMPOSED-BY-DESIGN.md is a four-lever system that makes decomposition the default at creation time:
required creation-time module layout, leading budget gate (400/600 line thresholds), reuse-by-composition
lint, and creation scaffolder. The leading gate prevents the "god-file → reactive decompose" loop.
SLOP's equivalent is `wci-contention.sh`-style reactive detection (which Charon ALSO has, as the safety
net). SLOP has no leading gate — waves decompose work at wave-design time by human judgment, not
mechanized budget enforcement.

### 5. CI gate discipline
Charon's merge gate is "FULL CI gate (ruff + mypy + `PYTHONPATH=src python3 -m charon.cli gate`), NEVER
pytest-alone" (`MANAGER-OPERATING-RULES.md:75-76`). Tests must fail on revert (`MANAGER-OPERATING-RULES.md:76`).
These are specific, mechanized rules with concrete verification paths.
SLOP's `ms-enforce` is comprehensive but its rules are mixed between HARD (blocking) and warn-only.
The `not-mechanically-enforced` annotation appears ~40+ times across ROBOT.md + AUTONOMOUS-DEFAULTS.md
— many rules are advisory only, unenforced.

---

## UNIFY DECISION: One portable "Do work" mechanism?

### Feasibility: YES, with the right convergence point

The two methods can collapse into ONE portable mechanism, but the convergence point must be Obol
(the designed stdlib-only coordination store), NOT either project's current implementation.

**What the unified mechanism MUST include** to not lose either method's strengths:

1. **SQLite-backed structured ticket store** (from SLOP) — Obol's schema (OBOL-PHASE-1-DESIGN.md:94-154)
   covers this. ✓

2. **Proof-based close discipline** (from SLOP) — Obol's `transition --status done` must require a
   GROUND-resolving ref (committed file path or commit SHA), with NO-PROOF closes counted by a ratchet.
   **GAP — not in current Obol design.**

3. **Physics-based progress detection** (from SLOP) — Obol's `sessions.busy_since` is not enough. Need
   `poll()` to also report a session's `head_sha + diff_hash + message_count` and have the daemon
   STALL sessions that claim WORKING but whose hashes haven't changed. **GAP — not in current Obol design.**
   The `sessions` table already has `head_sha`, `diff_hash` columns (OBOL-PHASE-1-DESIGN.md:126-127) — the
   COLUMNS exist but the ENFORCEMENT (stall detection) is not designed. Partial. ✓/~

4. **Tier enforcement at claim time** (from SLOP) — `obol claim --tier` must DENY weak-tier sessions
   from claiming strong-tier work when strong work remains or a strong session is live. Need a
   `tier_route.py`-equivalent configuration. **GAP — not in current Obol design.**

5. **Disjoint-owns collision prevention** (from Charon) — Obol's readiness derivation already includes
   owns-disjointness check (OBOL-PHASE-1-DESIGN.md:173-176). ✓

6. **Token economy + cost model** (from Charon) — Obol has no cost-tracking columns in its schema.
   Need `issues.cost_estimate`, `sessions.tokens_consumed`, or a separate `actuals` table.
   **GAP — not in current Obol design.** (It's out of scope per ADR-0008.)

7. **Respawn/continuity** (from SLOP) — Obol has no session lifecycle management (out of scope for Phase 1).
   Acceptable for Phase 1 (human-gated), but Phase 2 must add `obol respawn --session <id>` that atomically
   transfers claims and inbox from dying session to fresh successor. **GAP — deferred, but must be designed
   before Phase 2.**

### What Obol currently gets RIGHT (no changes needed)

- SQLite WAL store with atomic epoch-fenced claim (`BEGIN IMMEDIATE`, `claim_epoch`, `rowcount` guard)
- Typed inbox with poll/ack and visibility timeout
- Derived readiness (blocker graph, tier, disjoint-owns)
- Quorum adversarial review (votes table, findings, operator override)
- Stdlib-only (no Pydantic, no Redis, no web framework)
- No `/home/stack`, fleet, SLOP, or Claude assumptions in product code
- One daemon per project, local-only transport

### Key design gaps in Obol vs what BOTH methods need

| Gap | Severity | Fix |
|---|---|---|
| No proof-based close | HIGH — regression from SLOP | `obol transition` checks `--proof <ref>`; NO-PROOF ratchet |
| No progress-hash stall detection | HIGH — regression from SLOP | `obold` compares `head_sha+diff_hash` across poll cycles; STALL after N unchanged cycles |
| No tier enforcement at claim | MEDIUM — regression from SLOP | `obol claim` reads `tier_route` config; denies weak tier from strong work |
| No broadcast/team-wall | MEDIUM — loss of mailbox social awareness | `obol broadcast <type> <payload>` + `obol wall` shows recent team activity |
| No per-item continuity carriers | MEDIUM — loss of SLOP's durability | `continuity/<item>` append-only carriers seeded on claim, preserved on release |
| No cost/actuals tracking | LOW (deferred) — Charon has it via actuals-ledger | Add `cost_estimate` to `issues`, `tokens_consumed` to `sessions` |

---

## MIGRATION RISK: What breaks if mediastack adopts the Charon/obol method

### Hazard 1: Loss of physics-based progress detection (CRITICAL)
Current: SLOP's warden detects lying (says WORKING but no file changes) within 5 minutes.
Post-migration (as-designed Obol): `obol poll` only checks `last_seen`. A stuck/lying session stays
"in-progress" for up to `max_busy_s` = 1800 seconds (OBOL-PHASE-1-DESIGN.md:165).
**Impact:** False green on stalled work for 30 minutes. Multi-droid mediastack would lose its primary
anti-rot mechanism. Operator would not trust the board.
**Fix:** Implement progress-hash stall detection (head_sha + diff_hash comparison across `poll()` calls)
before migration Phase 1, not after.

### Hazard 2: Loss of ad-hoc queryability (HIGH)
Current: `python3 tracking/query.py open --tier S --batch BATCH-30` gives instant structured results.
Post-migration: `obol status` covers common cases but has no WHERE clause, no JOIN, no aggregation.
Power users who audit the backlog or generate reports would lose a key capability.
**Fix:** Ship `obol sql <query>` as a read-only power-user escape hatch (warned: "read-only; mutations
cause DRIFT"). This is standard in every serious dev tool (datadog, honeycomb, sentry all offer it).

### Hazard 3: Loss of mailbox social coordination (MEDIUM)
Current: SLOP's shared mailbox (`MAILBOX.md`) gives every droid ambient awareness of who's doing what.
"r2-d2 claimed #1310; ig-11 claimed #1311" is visible to all.
Post-migration: Obol's inbox is per-session (point-to-point via `nudge` + `poll`). No team-wide
activity feed without N separate nudges. Multi-droid teams lose awareness.
**Impact:** Droids would duplicate work (both investigating the same issue) because neither knows the
other is already on it.
**Fix:** Add broadcast message type + `obol wall` command showing recent team activity. The `messages`
table schema (OBOL-PHASE-1-DESIGN.md:131-142) could support a `to_session='*'` wildcard with minimal
changes.

---

## TOP 3 RECOMMENDATIONS

### 1. Slow-roll Obol: add proof-based close + progress-hash stall detection + tier enforcement BEFORE Phase 1 ships
These three gaps are not nice-to-haves — they are REGRESSIONS from SLOP's current capability and would
prevent mediastack from ever adopting Obol. The operator's hypothesis ("one portable method across all
projects") fails if the portable method is weaker than what it replaces. Each gap is a ~1-2 day build
(proof validation reuses `handoff-check.sh` SHA resolution; progress-hash reuses `check_progress.sh`
logic; tier enforcement reuses `tier_route.py`). Close them before marking Phase 1 as "done."

**Rationale:** A portable method that cannot detect lying, cannot prove work was done, and cannot
prevent weak models from touching security work will not be adopted by any project that takes quality
seriously.

### 2. Dogfood Obol on Charon FIRST; only then offer migration to mediastack
Let Charon's fleet be Obol's first production user. Import the current `board/*.md` tickets into Obol,
run the fleet tabs against Obol claims for one wave, and validate that progress-hash stall detection
actually catches a stalled session before `max_busy_s` fires. Only after a clean wave on Charon should
mediastack be offered an opt-in migration path. The two projects have different coordination cultures
(Charon: single-manager + session-bridge vs SLOP: multi-droid + mailbox); Obol must demonstrate it
handles BOTH patterns before being declared universal.

**Rationale:** Premature convergence creates a lowest-common-denominator that serves neither project
well. Obol must prove it handles Charon's parallel disjoint-owns WORSHIP AND SLOP's multi-agent
social coordination before being marketed as "the one method."

### 3. Keep flat-file tickets in Charon fleet/board as an import source, NOT a runtime store
Charon's `board/*.md` flat files are optimized for bash parsing (`validate_board.sh:24-28` reads them
with `line.startswith(key + ":")` — sub-millisecond per file). The fleet preflight tools are
deliberately bash-only (zero dependencies, runs in CI, runs on the operator's laptop). Replacing them
with SQL calls would add latency and a Python runtime dependency to what is currently a pure-bash gate.
Keep the flat files as the SOURCE OF TRUTH for the build rig, and have Obol import them into its store
for cross-project queries and reporting. The import pathway is already designed (OBOL-PHASE-1-DESIGN.md
§Migration Plan, Phase 0). Do not force the build rig to adopt Obol's daemon — let the build rig keep
its bash-native format and bridge to Obol at the export boundary.

**Rationale:** The build-rig's flat-file format is not a weakness for its use case (preflight gates,
collision detection, tier targeting). It's a strength — zero deps, trivially debugged, git-friendly.
Forcing SQL on it adds complexity with no benefit. The portable "do work" mechanism should have formats
at both levels (flat for the build rig, SQL for everything else) connected by an idempotent import bridge.
