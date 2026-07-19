# ADR-0007 — Parallel work engine: safe landing first, engine deferred in stages

> Post-MVP per ADR-0017 (fleet orchestration deferred; gateway MVP first).

Status: **Accepted** (2026-06-26). Builds on ADR-0005 (gateway-first), ADR-0006
(PERF-4). Reconciles the 2026-06-26 DTC (4 lenses) + a 3-lens adversarial review of
the first plan (feasibility / security / scope) — see REVIEW-LOG.

> **Accepted = the safe-landing-first increment + the staged-deferral strategy.** The
> shipped scope is realized: D2 per-unit worktree (PR #12), D3/D4/D6 propose-default
> gated landing + units loader (PR #13), D12 end-product Validator (PR #14), and L3
> unattended autonomy escalation gate (PR #15 / ADR-0009). The engine items (D5
> batch-atomic auto-land, board/claim/scheduler, `WorkerBackend` port, auto-decompose,
> AIMD capacity, scanner matrix) remain **deliberately deferred behind their D10
> tripwires** — accepting this ADR accepts that deferral, not their construction.

> **AMENDED by ADR-0010 (2026-06-26).** D10 over-reached: it folded the **coordination
> substrate** (board + atomic claim/lease + worker-liveness + `WorkerBackend` port +
> spawn-to-demand scheduler) into indefinite deferral, inverting the operator's decision
> that the work-engine is **core, built native, sooner** ([[charon-own-work-engine]]).
> ADR-0010 promotes that substrate to a roadmapped native build (the fleet rig is its
> reference impl); the D10 tripwires for those items become **sequencing, not deferral**.
> The **trust-extending** items the review was right about — D5 auto-land,
> scanner-as-required, ADR-0008 Phase-2 autonomous run, AIMD — **stay gated**. See
> ADR-0010 for the substrate design + the intelligent (lightweight/measured) scanner
> matrix.

## Context
Operator vision (settled): Charon is a **work engine** — *analyze* work → *decompose*
it → *assign* to multiple parallel workers → land safely, so work runs concurrently
instead of serially, "safely and much faster." The **gateway stays the fresh-install
default**; the work engine is an **opt-in orchestrator capability**.

A first plan proposed an ephemeral process-per-unit, board-claimed, **auto-landing**
engine. A 3-lens adversarial review found it does not survive contact with reality
(claims verified against the code):
- It is a **second, contradictory architecture**: the shipped code is thread-per-unit
  (`ThreadPoolExecutor`), subprocess-**reuse** (`AcpBackend`), container-isolated, with
  **no merge logic** — not process-per-unit / PID-monitored / board-claimed / auto-land.
- Its spine — **auto-decomposition into independent, file-disjoint, tier-correct
  units — does not exist** (`decompose.py` wraps one goal into 6 sequential role-copies
  on one shared worktree).
- Its safety claim is **false on the real path**: the ACP backend re-injects the
  operator's real `HOME`/`XDG`/keys (`_ACP_BASE_PASSTHROUGH`/`_ACP_KEY_PASSTHROUGH`), so
  "scrubbed env, HOME→worktree" is fiction; the container, not env-munging, is the
  boundary.
- Its default (**auto-land**) inverts ADR-0003 default-deny / L0-propose, on a gate
  that is an **integrity check, not an adversary model** (it catches broken/secret-
  leaking code, not clean, in-scope, test-passing, hostile code) — multiplied by N via
  parallelism + ticket injection.
- It over-builds a **distributed work-queue (board + claim/lease + scheduler) for
  consumers that do not exist**; the `ThreadPoolExecutor` already does bounded
  spawn-to-demand for the one present consumer.

This ADR keeps the vision as the north star but commits only to the **honest first
increment**, deferring the engine in stages — each gated by a present consumer + a
measurement, not a belief.

## Decisions

**D1 — Vision is the direction; this ADR commits only to the lean increment.** Build
the smallest real thing; defer the engine in stages.

**D2 — Close the real isolation gap: per-unit `git worktree` off base (BUILD NOW).**
`_prepare_repo` only nests a per-unit worktree for the demo sandbox; a real `--repo` is
used as-is, so N units share one tree + `guard_dir`, silently defeating CONC-1. Charon
must `git worktree add` per unit off base for real repos too (or refuse >1 unit on a
shared real repo). This is the one genuinely-missing isolation primitive and the
prerequisite for branch-based landing.

**D3 — Units are consumer-supplied; auto-decomposition is a separate, deferred ADR.**
`run_parallel(units)` already takes a caller-supplied list (ADR-0006 D6 step 1). Keep
that. A real splitter (independent, file-disjoint, tier-correct units) is the hardest
unsolved AI-quality problem and does not exist; defer it to its own ADR **with an
explicit failure contract** (what happens on overlapping files / mis-tier / hidden
inter-unit dependency). Until then, do not claim auto-decompose.

A **unit** is one independent work item — `{goal, acceptance checks, tier,
declared owned-paths}` → one `WorkUnit` / ledger / worktree (the data shape we used
by hand in the private TICKETS.md). A **unit list** is the set `run_parallel` fans out
concurrently. Until the splitter exists it is **consumer-supplied**: hand-authored (a
file → `--units`, or repeated flags), **drafted by a manager/LLM session and
human-reviewed before the run**, or pulled from an existing source (issues/backlog) via
a thin adapter. The first-increment contract is *"give Charon independent units; it runs
them in parallel and lands them safely"* — **decomposition is the input, supplied by the
user, not yet Charon's job.** (This is also the experiment that generates the conflict-
rate data gating D10's auto-decompose tripwire.)

**D4 — Default is PROPOSE, not auto-land** (reverses the first plan). One PR/diff per
unit; a human merges. Preserves ADR-0003 default-deny / L0-propose. The gate detects
*broken/secret-leaking* code, not *clean-and-hostile*; the ticket is the primary attack
surface; parallelism multiplies one injection into N landings. For public installs or
untrusted ticket origins, propose-only is the only default.

**D5 — Auto-land, when opted in, is batch-atomic + allowlisted + fail-closed.**
- **Batch-atomic:** stage all unit merges on a throwaway integration branch, run the
  gate ONCE on the integrated tip, fast-forward only if green, else discard (per-unit
  green ≠ integrated green; no orphaned half-land). Idempotent.
- **Allowlist** the paths that may auto-land (source dirs); HOLD everything else. The
  hold set includes every path executed by the gate/git/CI/tooling: `.git/hooks`,
  `core.hooksPath`, `.gitattributes` filters, `conftest.py`/`tests/` (the gate runs
  pytest → worker test code executes *inside* the gate), `pyproject.toml`/`setup.py`/
  `[project.scripts]`, `package.json` scripts/`.npmrc`, `Makefile`/`justfile`/`noxfile`/
  `tox.ini`, `.github/workflows`+other CI, `Dockerfile`, install/setup scripts,
  pre-commit config, `.claude/`, `CODEOWNERS`, `.envrc`.
- **Gate config read from outside the worktree** (engine-owned, immutable); every
  scanner-ignore/suppression file and inline `# noqa`/`# nosec` is a held path; a
  missing-but-expected scanner **fails closed** (hold), never silently skips.
- The gate's tests run in a **throwaway sandbox/container**; worker-authored
  test/conftest never auto-lands.
- One decomposition lands as **one atomic, human-gated unit**, not N independent
  auto-lands.

**D6 — Land gate: minimal stdlib core + optional layers.** Core (always): diff-scope
guard (writes outside a unit's declared paths → hold), sensitive-path hold (D5),
executable acceptance + tests, gitleaks if present. Optional/advisory (run if installed
+ relevant, fail-closed when expected): semgrep, shellcheck, actionlint, osv/CVE,
license — fired conditionally on the file types changed. Scanners stay pluggable and
out of the privileged gateway path.

**D7 — Worker lifetime is a POLICY, not a dogma** (revises "ephemeral spine"). Default
to a **warm pool per tier** (reuse the ACP subprocess across units — as `AcpBackend`
already does — resetting via `session/new` + a fresh per-unit worktree, which is what
prevents contamination). Reserve **ephemeral** (process teardown per unit) for
untrusted-origin / L2+ units where teardown is the safety argument. Decide the default
with a **measurement**: cold start vs median unit runtime on one real agent (if cold
start > ~15% of runtime, ephemeral loses for small/numerous units).

**D8 — Liveness = ACP deadline + checkpoint `kill()`** (not new PID machinery). The
ledger PID-lock tracks the coordinator, not the agent; under the thread pool all units
share one PID, and a real ACP agent forks children — so PID-liveness gives no per-unit
crash discrimination. The existing ACP request deadline + checkpoint-boundary kill is
the brake. Build process-group/zombie reaping only when a true out-of-process backend
exists.

**D9 — Tier→pool is env-wiring + adaptive capacity** (trims "tier == gateway pool").
Pin a worker via `OPENAI_BASE_URL=<gateway>` + `model=<pool-id>` in its env. Either
validate at config-load that a pool's members share a tier, or drop the "failover stays
within the tier" guarantee (gateway chains can span tiers). Per-tier capacity is
**adaptive, not declared**: a per-pool concurrency limiter that backs off (AIMD) on
observed 429/quota signals; there is no `capacity[tier]` input until a request fails.
"Model in no pool" is a loud config error.

**D10 — DEFER behind explicit tripwires.** A parked item builds only when its tripwire
trips; a meantime stopgap holds until then; **absorbable** items build only if the agent
platform hasn't shipped them first.
- **Board + atomic claim/lease + spawn-to-demand scheduler** — *tripwire:* **≥2
  independent processes** (separate tabs/machines) must pull from **one shared
  Charon-owned backlog**. *Meantime:* in-process `ThreadPoolExecutor` assignment;
  external workers each take a **disjoint unit-list**. *Absorbable* (skip if the
  platform ships native multi-session work-claiming). *Deferred-wrong signal:* repeated
  hand-partitioning across tabs + collisions.
- **New `WorkerBackend` port + headless-CLI + external-lease backends** — *tripwire:* a
  worker a blocking `AgentBackend.dispatch()` **can't drive** (out-of-process/poll-based:
  a headless CLI agent, an external worker, remote). Arrives **with** the board (same consumer).
  *Meantime:* ACP backend + mock. *Absorbable.*
- **Auto-decomposition** (its own ADR + failure contract) — *tripwire, BOTH:* (1)
  hand-authoring unit lists is real recurring friction, **and** (2) the **PR-per-unit
  conflict rate** (from the propose-default increment) shows consumer-supplied units
  integrate cleanly often enough to be worth automating. **If PRs conflict frequently,
  do NOT build it** (it would only produce garbage faster). *Meantime:* units are
  consumer-/manager-authored (D3); the measured conflict rate IS the gate.
- **Per-tier adaptive (AIMD) capacity** — *tripwire:* a real run **saturates a tier**
  (repeated 429/quota) or visibly leaves throughput idle. *Meantime:* a conservative
  **fixed per-tier concurrency cap** in config + the gateway's cooldown/failover.
  *Deferred-wrong signal:* hand-tuning the cap every run.
- **Heavy scanner matrix** (semgrep/shellcheck/actionlint/osv/license) — **feature-gated,
  not time-gated:** *tripwire:* **auto-land enabled for a repo** → its language-relevant
  scanners become **required (fail-closed)**. In propose-mode they stay **advisory** (the
  human merging is the gate).

**D11 — Reaffirm gateway-first (anti-dilution).** The work engine is ONE opt-in
consumer of the same pools/proxy core; it must never import into or bloat the gateway
request path or install footprint (ADR-0005 R3). "Charon is a work engine" is the
orchestrator's charter, not a redefinition of the product whose default is the gateway.

**D12 — End-product validation is a distinct role (Validate), after units land, before
close.** Per-unit acceptance verifies *each unit*; the integration land-gate (D5/D6)
verifies *mechanical integration*; **neither verifies the assembled product meets the
original goal.** Add a **Validator worker** (a tier-appropriate model; role=Validate in
the role-DAG) that exercises the integrated result against the **top-level acceptance
captured at intake** (ADR-0008) and reports pass/fail. It is a **quality gate (does it
work) — explicitly NOT a security/trust boundary**: an automated validator is
gameable/prompt-injectable (cf. coordinator D-GATE-6 — the reviewer "can be wrong or
gamed, NOT a security boundary"), so it catches *broken/incomplete*, not *hostile*.
It **complements, never replaces** per-unit acceptance, the land-gate, and human review
of sensitive paths. In propose mode its report accompanies the PR (informs the human);
in opt-in auto-land it is a **required pass**. Distinct from a per-unit L2 reviewer: the
validator runs once on the *whole product*, not per unit.

## Invariants preserved
ADR-0003 default-deny / L0-propose default (D4); L2+ container-gated; fence escape-scan
per unit; INV-1 one ledger per task. ADR-0005 R3 (gateway never imports the
orchestrator). The container — not env-munging — is the isolation boundary (D7 corrects
the first plan's false HOME→worktree claim).

## Risks / honesty register
- Auto-decompose is deferred → "analyze→assign" is operator-supplied units, not
  automatic, until D3's successor ADR ships.
- The gate is an integrity check, not an adversary model → auto-land extends trust to
  code whose provenance is the primary attack surface; hence propose-default +
  allowlist + container-for-untrusted.
- Ephemeral cold-start economics are unmeasured → D7 is a measurement, not a belief.

## Build sequence (the honest first increment)
1. D2 — per-unit `git worktree` off base for real repos (the missing primitive).
2. D3 — consumer-supplied units (no auto-decompose).
3. D4/D6 — propose default: PR/diff per unit, human merges; gate = diff-scope +
   sensitive-path hold + acceptance/tests + gitleaks.
4. Measure ACP cold-start vs unit runtime (D7) → set warm/ephemeral default with data.
Then behind triggers: D5 opt-in batch-atomic auto-land; D9 adaptive capacity; D10 the
board/ports/decompose work.

## Reconciliation
3-lens adversarial review reconciled in REVIEW-LOG (2026-06-26). The review overturned
two first-plan decisions the operator had approved — **ephemeral-as-spine** (→ policy,
D7) and **auto-land-as-default** (→ propose-default, D4/D5) — on feasibility
(cold-start; subprocess-reuse) and security (default-deny inversion; integrity-vs-
adversary gate; false env-isolation claim) grounds, all verified against the code.
Recorded for the operator's objection; status **Proposed**.
