# Charon — Review Log

One entry per significant change: reviewer, charge, key findings, and the
author's per-finding reconciliation (accept/reject + why). Reviewers are
XREF-class — they flag, they do not vote or veto. The author reconciles against
physics and records it here.

---

## 2026-06-23 — Tier 1 build plan (ADR-0001/0002/0003)

- **Change under review:** `docs/PLAN-tier1.md` — initial standalone repo + the
  continuity core (Ledger, fence, ports, coordinator) before any code.
- **Reviewers:** two independent read-only adversarial subagents (Opus),
  dispatched in parallel — lens A = blast-radius, lens B = out-of-the-box /
  premise-attack. Each derived risks independently from the three ADRs, then
  attacked the plan.
- **Charge (fixed, author could not soften):** find what will hurt; where the
  privileged loop escapes the fence; how the ledger corrupts; supply-chain holes;
  whether the core premise (cross-vendor handoff) is even the valuable problem;
  whether ACP is a safe bet; what to validate BEFORE writing code.

### Findings + reconciliation

| ID | Finding (sev) | Verdict | Reconciliation |
|----|----|----|----|
| BR-1 | Ledger JSON not crash-safe; concurrent coordinators corrupt silently (CRIT) | **ACCEPT** | Atomic write via `tempfile`+`os.replace`; checkpoints are append-only JSONL (one record/line, partial trailing line skipped); per-task lockfile (PID+mtime, stale after TTL); malformed read → raise LOUD, never silent. `schema_version` field from first commit. |
| BR-2 | Fence is a Python predicate, not OS isolation; agent can `cd ..`, poison global git, `LD_PRELOAD` (CRIT) | **ACCEPT, re-scoped** | Tier 1 default autonomy = **L0 propose-only** (nothing applied). L1 apply is guarded: minimal scrubbed env (`env -i`-style: only PATH/HOME=worktree/TERM/CHARON_*), `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_SYSTEM=/dev/null`; post-run escape scan (any path mtime-touched outside the worktree ⇒ run rejected, not applied). True OS isolation is delegated to the **Mode B container** (ADR-0002 §2.3) — the doc does NOT claim a proven structural fence vs a live skip-perms agent in Tier 1. Honesty register updated. |
| BR-3 | Unvetted gateway enters the privileged loop (CRIT) | **ACCEPT** | Tier 1 ships **no network gateway**: routing = static policy file on disk, hard-pinned model ids. Gateway is Tier 2+, optional, gated on a `SUPPLY-CHAIN.md` audit. `pip-audit` runs in CI; runtime deps pinned and minimal (stdlib-first). |
| BR-4 | CI grep for `slop` trivially bypassed; transitive `ms-router` could import SLOP (HIGH) | **ACCEPT** | Boundary check is an **AST import scan** (`ast.walk`, catches `import`, `from`, `__import__("...")` literals), not a grep. Runtime guard: `assert 'slop' not in sys.modules` at startup. No `ms-router` dependency — routing is native/static, so no transitive SLOP path exists. |
| BR-5 | "No prose acceptance" is policy, not enforced (HIGH) | **ACCEPT, structural** | There is no prose field by construction: an acceptance criterion is `{id, cmd}` and `verified` ⇔ `cmd` exits 0. Prose passed as `--accept` is *run as a command*, fails to exit 0, so it can never become falsely "done" — it surfaces as loud, permanent incompletion. A constructor warning nudges the user. |
| BR-6 | Mock-only proof never exercises the privileged path = theater (HIGH) | **ACCEPT** | MockBackend gains **adversarial modes**: emit an incomplete ledger entry, attempt a worktree escape, try to advance `lkg_ref` past an unverified commit. Tests assert the coordinator/ledger **reject** each loudly (proven-red), so the invariants are tested, not just asserted. |
| BR-7 | Install blast radius (curl\|bash, privileged container) unmitigated (MED) | **ACCEPT, docs** | `install.sh` prints a prominent warning (spawns CLI agents / autonomous loop; not for shared machines); README is honest; unattended/L2+ is steered to the Mode B container. GPG/SLSA signing tracked for a later tier. |
| BR-8 | Two `charon run` on one task race (MED) | **ACCEPT** | Covered by the BR-1 lockfile. |
| OOB-C1 | Is cross-vendor handoff even the valuable problem? Possibly over-built vs cross-session resume (FUNDAMENTAL) | **ACCEPT, sequencing** | Tier 1 re-scoped to a **single-backend disciplined loop + Ledger** (which is what ADR-0001/0002 Tier 1 already says). The `AgentBackend` *port* stays (cheap seam, mandated by ports-and-adapters); the handoff H-predicate logic is built + unit-tested vs mock; **live cross-vendor handoff is Tier 2**, built only if the data justifies it. |
| OOB-C2 | ACP maturity unproven; H4 fidelity unvalidated; Tier 0 should precede coordinator code (CRIT) | **ACCEPT, made runnable** | Instead of deferring Tier 0 to "later," ship it as a command: **`charon doctor`** probes a present ACP backend for usage-reporting + resume/fork fidelity and reports gaps. Mock proves the loop; `doctor` grounds the real-backend assumptions on demand. The doc does not claim H4 is validated until `doctor` is run green against a real agent. |
| OOB-C3 | Executable-acceptance ⇒ this is a test-driven task runner, not a general agent (HIGH) | **ACCEPT** | Disclosed as a headline scope statement in README ("Charon runs goals with executable acceptance; prose-only goals are out of scope"). Framed as a deliberate narrowing, not a hidden limitation. |
| OOB-C4 | A ~500-LOC bash script gets 80% of the value (MED) | **REJECT as deliverable, accept as discipline** | The requirement is an installable, versioned, SLOP-embeddable package with three public surfaces — bash is none of those. But the lesson lands: Tier 1 stays genuinely thin, git is the source of truth for `lkg_ref`, no formalism beyond what a public API needs. |
| OOB-C5 | "Charon" collides with Plan 9 / NASA tooling (LOW) | **ACKNOWLEDGE** | Operator-chosen; `SLOP-Platform/charon` namespace is clear; non-blocking. |
| OOB-C6 | ADRs missed: ledger schema-versioning hell; adapter-incompatibility creep | **ACCEPT** | `schema_version` + migrate-on-load from first commit; adapter incompatibility named as a watched class in the honesty register. |
| OOB-C7 | Frontier models may absorb this in months (existential) | **ACCEPT, docs** | README sunset clause: Charon is a tactical bridge; the Ledger is git+JSON and outlives Charon's removal. |

### Net effect on the build (folded into PLAN-tier1 §"Reconciled scope")
1. Ledger: atomic + JSONL checkpoints + lockfile + schema_version + loud-on-corrupt.
2. Fence: L0 default; L1 guarded (scrubbed env + escape scan); OS isolation = Mode B container.
3. No gateway in Tier 1 (static routing policy); `pip-audit` in CI.
4. AST boundary check + runtime SLOP guard; no `ms-router` dep.
5. Adversarial MockBackend modes; coordinator/ledger must reject them (proven-red).
6. `charon doctor` as the runnable Tier-0 backend probe.
7. README discloses: autonomous privileged loop, test-driven scope, sunset clause.

No WALK-BACK-LOG entry required: new repo, all additions/strengthenings.

---

## 2026-06-24 — Tier 2 build plan (cross-vendor handoff + service/image)

- **Change under review:** `docs/PLAN-tier2.md` — fold both ADR Tier-2 scopes
  (ADR-0001 cross-vendor handoff/routing + ADR-0002 HTTP service/image) into one
  build, on top of the green Tier-1 core.
- **Reviewers:** two independent read-only adversarial subagents (Opus),
  dispatched in parallel — lens A = blast-radius/security (the new HTTP service
  fronts the privileged loop), lens B = premise-attack / out-of-the-box
  (sequencing, scope, is the proof real). Each derived risks from the code +
  ADRs, then attacked the plan. Reviewers are XREF-class: they flag, the author
  reconciles against physics.
- **Charge (fixed):** where does the HTTP surface open a privileged-loop hole the
  in-process fence can't close; is the two-mock handoff proof theater; is
  cross-vendor handoff even justified (OOB-C1 deferred it pending data); is
  folding both Tier-2s one tier too big; supply-chain blast radius of GHCR
  publish.

### Findings + reconciliation

| ID | Finding (sev) | Verdict | Reconciliation |
|----|----|----|----|
| OOB2-4 / BR2-1,2,3,6,9 | Service fronts the privileged loop with no consumer until Tier 3 (SLOP-side), and carries CRIT holes: `accept[]` are shell commands (`acceptance.py:54` `shell=True`) run from an untrusted caller; `repo` param = arbitrary FS path/SSRF; `task_id` path-traversal in `Ledger.load`; DoS via unbounded `budget`/concurrency; no auth by default. | **ACCEPT — SPLIT to Tier 2b** | The in-process fence explicitly does **not** bound a determined local agent (README already says only the Mode-B container does), so a bare Mode-A HTTP run-endpoint is genuinely dangerous, and it has **no consumer** until the Tier-3 SLOP adapter. Shipping it rushed = net liability. This build (**Tier 2a**) ships the handoff core + a Docker **build-smoke** (image doesn't bit-rot) only. The live `POST /v1/runs` endpoint + GHCR **publish-on-tag** become **Tier 2b**, gated on the full Lens-A hardening: reject untrusted `repo` on the service path; cap `budget`/concurrency + request size; require `CHARON_SERVICE_TOKEN` for any non-loopback bind; sandbox or operator-trust-document the acceptance exec; real subprocess HTTP test. Enumerated in PLAN-tier2 §"Reconciled scope" as 2b prerequisites. |
| BR2-9 | `task_id` path-traversal: `Ledger.load` joins `state_dir / task_id` unvalidated (`ledger.py:119`) — `../etc` escapes the state dir. | **ACCEPT — fix now** | Cheap and reachable from any surface; not deferred with the rest of the service. Validate `task_id` against `^[a-z0-9][a-z0-9-]{0,63}$` and reject `/`/`..` at the ledger boundary, so the hole is closed regardless of which surface calls in. |
| OOB2-1 | No data that backends exhaust mid-task → handoff may be a sophisticated answer to a non-problem (OOB-C1 redux). Demands measuring exhaustion on 20 live ACP tasks first. | **ACCEPT in spirit, REJECT the gate** | The demanded data is **uncollectable in this env** (no live ACP agent — stated since Tier 1), so it cannot gate the build. But exhaustion (rate-limit / context-pressure / budget cap) is not speculative — ACP exposes `session/usage` precisely because it happens, and ADR-0001 §9 names handoff as the Tier-2 core. Reconciliation: build the handoff loop (cheap; the seam exists) but keep it **minimal and honestly framed** — proven as a vendor-agnostic *contract*, never as a live cross-vendor result. Honesty register reaffirmed. |
| OOB2-2 | Two well-behaved mocks agreeing on file-based acceptance is a **tautology** — you wrote both to agree; it proves nothing the Tier-1 single-mock loop didn't. | **ACCEPT — re-shape the proof** | Drop the happy-path two-mock test as the centerpiece. Replace with two honest proofs: (a) **restart/no-replay** (single backend, reload ledger between checkpoints, assert the completed checkpoint is **not** replayed and A's committed file is **not** re-created — real H3/H5); (b) **adversarial handoff** (mock-a **lies**: claims done, satisfies nothing → handoff → mock-b rehydrates from ledger+disk and `remaining` is still non-empty; the lie does **not** survive the vendor boundary). (b) is not tautological: it proves progress truth lives in the ledger, not any backend's claim, *across* a switch — the actual H3 content. |
| OOB2-8 | §1.3 tests are all well-behaved; no adversarial mode across a handoff. | **ACCEPT** | Folded into OOB2-2(b) above — the lying-backend-across-handoff test. |
| BR2-4 / OOB2-3 | Exclude-accumulation: `coordinator.py:73` re-routes excluding only the just-exhausted backend, not the accumulated set → with ≥3 backends and ≥2 exhausted it can re-pick an exhausted one. | **ACCEPT** | `choose_next_backend` takes the full `exclude: set[str]`; coordinator re-routes against the whole `exhausted` set. Proven-red test: 3 backends, 2 exhausted → 3rd chosen, never a repeat. |
| BR2-5 | `lkg` advances using a `remaining` computed one step earlier; a between-checkpoint disk change could advance past an unverified state (INV-2). | **ACCEPT — cheap insurance** | Re-derive `remaining` immediately inside the `advance_lkg` guard; advance only if still empty. Strengthens INV-2 at near-zero cost even though the window is narrow single-threaded. |
| BR2-11 | A router backend missing from the `backends` dict → uncaught `KeyError` mid-run. | **ACCEPT** | Assert `backends.keys() ⊇ router.backends` before the loop; treat a lookup miss as `exhausted` with a loud note, never a crash. |
| BR2-8 | GHCR publish with `GITHUB_TOKEN packages:write`; unpinned base image; no provenance. | **ACCEPT — deferred with 2b** | Publish-on-tag is Tier 2b. When it lands: pin base image by digest, pin the installed `charon` version, add SLSA provenance, document `:vX.Y.Z` over `:latest`. Tier 2a CI only **builds** the image (no push), so no token/publish surface yet. |
| OOB2-6 / D1 | Gateway deferral (BR-3) has no defined "green" criteria → Tier 2.5 is blocked-by-undefined, not blocked-by-process. | **ACCEPT** | Ship `SUPPLY-CHAIN.md` now: audit criteria (no SLOP path via AST scan, OpenAI-compat only, pinned version, `pip-audit` clean), verification SOP, and sign-off gate. The gateway **client port** itself stays unbuilt until needed (YAGNI — no unused port clutter); the doc is the gate. |
| BR2-7 / OOB2-5 | Service-layer code path untested by in-process tests; TestClient ≠ real HTTP. | **ACCEPT — moot for 2a, required for 2b** | The service endpoint is deferred (OOB2-4); when 2b ships it, a real out-of-process HTTP test (subprocess + socket) is a landing requirement, not TestClient-only. |
| BR2-10 | Lock-stealing via future-mtime / PID reuse on a shared `.charon/`. | **ACKNOWLEDGE — Mode-B isolates** | Real only on a shared state dir; the Mode-B container isolates it (INV-B4). Tracked as a watched class; not a 2a blocker. PID-liveness check folded into the 2b/Tier-4 hardening list. |
| D5 | Is folding both Tier-2s one tier too big? | **RESOLVED: yes — split.** | Tier 2a = handoff + multi-backend (serves Mode A now, low blast radius). Tier 2b = service + publish (gated on hardening + a consumer). The coupling "Mode B needs both" is real but Mode B's consumer is Tier-3 SLOP-side — no reason to ship the endpoint ahead of it. |

### Net effect on the build (Tier 2a — folded into PLAN-tier2 §"Reconciled scope")
1. Multi-backend coordinator + CLI/API; router seeded with all backends.
2. Exclude-accumulation fix (full set) + backend-coverage guard + re-verify-before-advance.
3. `task_id` validation at the ledger boundary (path-traversal closed everywhere).
4. Proofs re-shaped to be non-tautological: restart/no-replay + lying-backend-across-handoff (proven-red), plus exclude-accumulation.
5. `SUPPLY-CHAIN.md` as the gateway gate; gateway port itself deferred (YAGNI).
6. Docker build-smoke in CI (no publish); honesty register: cross-vendor proven as a *contract* only, live endpoint + GHCR publish = Tier 2b with enumerated security prerequisites.

No WALK-BACK-LOG entry: all additions/strengthenings; the only scope change is a deferral (service → 2b), recorded above.

---

## 2026-06-24 — Tier 2b: DTC on the privileged-loop HTTP exposure model

- **Change under review:** how to safely expose Charon's privileged coordinator
  loop (it spawns CLI agents and runs `shell=True` acceptance exec) over the
  Mode-B HTTP surface.
- **Process (DTC — Decision-Theoretic Committee):** a multi-agent workflow, not a
  single reviewer, because this fixes the security architecture of the whole
  service surface. 3 independent architects each steelmanned a competing
  exposure model; each was judged by 3 adversarial lenses (security / ADR-honesty
  / thinness-YAGNI); a high-effort synthesis reconciled against physics. 13
  agents total. Scores (of 15): minimal-sandbox 11, isolated-worker 10,
  capability-policy 9.
- **Author reconciliation (against physics, not the vote):** accepted the
  synthesis. Three physics facts dominated: (1) no in-process Python layer bounds
  a determined spawned agent — only the Mode-B container does (INV-B4), so the
  max honest security score was 3/5 for every design and the contest turned on
  *caller-surface reduction* + *honesty*, not "containing the agent"; (2)
  today's `app.py` calls `api.run_task` in-process, which literally contradicts
  ADR-0002 §2.3 — the honest answer is "the web process must not run the loop
  in-process"; (3) OOB2-4 already deferred the live endpoint to ship *with* the
  Tier-3 SLOP consumer, never ahead of it.

### Decision

- **Base:** minimal-sandbox (drop `repo` from the wire → sandbox-only by
  construction; clamp budget; token-gate non-loopback).
- **Graft (load-bearing):** isolated-worker's topology — the exposed web process
  must not import the privileged loop; a separate no-network worker container
  runs it. This makes ADR-0002 §2.3 structurally true.
- **Exec hardening:** `shell=False` parsed-argv on the service path (delete the
  metacharacter denylist — leaky antipattern); service autonomy pinned L0.
- **Rejected (thinness):** durable queue/lease/reclaim broker; HMAC-signed policy
  file; bespoke argv0 allowlist module; threading `allowed_argv0` into the
  zero-dep core; and **shipping any live `POST /v1/runs` now**.

### Shipped now (consumer-independent) vs deferred

| Now (this commit) | Deferred to "with Tier-3 consumer" |
|---|---|
| GHCR publish path (digest-pin at release, gated on tests, SLSA provenance, `:vX.Y.Z`) | Web/worker split + enqueue-only web process |
| Web surface **neutered**: read-only + `501` on runs; no in-process privileged call | `shell=False` service exec; L0-pinned service autonomy; token + non-loopback startup guard |
| Structural test: `service/app.py` references no privileged-exec symbol | Real out-of-process HTTP test (subprocess+socket); compose web/worker split |

Honesty register entries (mirror in README at the live opt-in): the container is
the only real agent boundary; in-process guards bound the caller not the agent;
the shared `.charon` volume is a bidirectional integrity seam (a compromised
worker can write ledger "truth"). Full DTC transcript: workflow `dtc-service-exposure`.

WALK-BACK note: `service/app.py`'s pre-DTC `POST /v1/run` called `api.run_task`
in-process (ADR-0002 §2.3 violation, though behind the optional `[service]`
extra and `pragma: no cover`). It is walked back to a `501` refusal — the only
behavior change to existing code; everything else is additive.
