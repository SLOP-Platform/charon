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
| OOB2-4 / BR2-1,2,3,6,9 | Service fronts the privileged loop with no consumer until the Tier-3 host-project adapter, and carries CRIT holes: `accept[]` are shell commands (`acceptance.py:54` `shell=True`) run from an untrusted caller; `repo` param = arbitrary FS path/SSRF; `task_id` path-traversal in `Ledger.load`; DoS via unbounded `budget`/concurrency; no auth by default. | **ACCEPT — SPLIT to Tier 2b** | The in-process fence explicitly does **not** bound a determined local agent (README already says only the Mode-B container does), so a bare Mode-A HTTP run-endpoint is genuinely dangerous, and it has **no consumer** until the Tier-3 host-project adapter. Shipping it rushed = net liability. This build (**Tier 2a**) ships the handoff core + a Docker **build-smoke** (image doesn't bit-rot) only. The live `POST /v1/runs` endpoint + GHCR **publish-on-tag** become **Tier 2b**, gated on the full Lens-A hardening: reject untrusted `repo` on the service path; cap `budget`/concurrency + request size; require `CHARON_SERVICE_TOKEN` for any non-loopback bind; sandbox or operator-trust-document the acceptance exec; real subprocess HTTP test. Enumerated in PLAN-tier2 §"Reconciled scope" as 2b prerequisites. |
| BR2-9 | `task_id` path-traversal: `Ledger.load` joins `state_dir / task_id` unvalidated (`ledger.py:119`) — `../etc` escapes the state dir. | **ACCEPT — fix now** | Cheap and reachable from any surface; not deferred with the rest of the service. Validate `task_id` against `^[a-z0-9][a-z0-9-]{0,63}$` and reject `/`/`..` at the ledger boundary, so the hole is closed regardless of which surface calls in. |
| OOB2-1 | No data that backends exhaust mid-task → handoff may be a sophisticated answer to a non-problem (OOB-C1 redux). Demands measuring exhaustion on 20 live ACP tasks first. | **ACCEPT in spirit, REJECT the gate** | The demanded data is **uncollectable in this env** (no live ACP agent — stated since Tier 1), so it cannot gate the build. But exhaustion (rate-limit / context-pressure / budget cap) is not speculative — ACP exposes `session/usage` precisely because it happens, and ADR-0001 §9 names handoff as the Tier-2 core. Reconciliation: build the handoff loop (cheap; the seam exists) but keep it **minimal and honestly framed** — proven as a vendor-agnostic *contract*, never as a live cross-vendor result. Honesty register reaffirmed. |
| OOB2-2 | Two well-behaved mocks agreeing on file-based acceptance is a **tautology** — you wrote both to agree; it proves nothing the Tier-1 single-mock loop didn't. | **ACCEPT — re-shape the proof** | Drop the happy-path two-mock test as the centerpiece. Replace with two honest proofs: (a) **restart/no-replay** (single backend, reload ledger between checkpoints, assert the completed checkpoint is **not** replayed and A's committed file is **not** re-created — real H3/H5); (b) **adversarial handoff** (mock-a **lies**: claims done, satisfies nothing → handoff → mock-b rehydrates from ledger+disk and `remaining` is still non-empty; the lie does **not** survive the vendor boundary). (b) is not tautological: it proves progress truth lives in the ledger, not any backend's claim, *across* a switch — the actual H3 content. |
| OOB2-8 | §1.3 tests are all well-behaved; no adversarial mode across a handoff. | **ACCEPT** | Folded into OOB2-2(b) above — the lying-backend-across-handoff test. |
| BR2-4 / OOB2-3 | Exclude-accumulation: `coordinator.py:73` re-routes excluding only the just-exhausted backend, not the accumulated set → with ≥3 backends and ≥2 exhausted it can re-pick an exhausted one. | **ACCEPT** | `choose_next_backend` takes the full `exclude: set[str]`; coordinator re-routes against the whole `exhausted` set. Proven-red test: 3 backends, 2 exhausted → 3rd chosen, never a repeat. |
| BR2-5 | `lkg` advances using a `remaining` computed one step earlier; a between-checkpoint disk change could advance past an unverified state (INV-2). | **ACCEPT — cheap insurance** | Re-derive `remaining` immediately inside the `advance_lkg` guard; advance only if still empty. Strengthens INV-2 at near-zero cost even though the window is narrow single-threaded. |
| BR2-11 | A router backend missing from the `backends` dict → uncaught `KeyError` mid-run. | **ACCEPT** | Assert `backends.keys() ⊇ router.backends` before the loop; treat a lookup miss as `exhausted` with a loud note, never a crash. |
| BR2-8 | GHCR publish with `GITHUB_TOKEN packages:write`; unpinned base image; no provenance. | **ACCEPT — deferred with 2b** | Publish-on-tag is Tier 2b. When it lands: pin base image by digest, pin the installed `charon` version, add SLSA provenance, document `:vX.Y.Z` over `:latest`. Tier 2a CI only **builds** the image (no push), so no token/publish surface yet. |
| OOB2-6 / D1 | Gateway deferral (BR-3) has no defined "green" criteria → Tier 2.5 is blocked-by-undefined, not blocked-by-process. | **ACCEPT** | Ship `SUPPLY-CHAIN.md` now: audit criteria (no host-project import path via AST scan, OpenAI-compat only, pinned version, `pip-audit` clean), verification SOP, and sign-off gate. The gateway **client port** itself stays unbuilt until needed (YAGNI — no unused port clutter); the doc is the gate. |
| BR2-7 / OOB2-5 | Service-layer code path untested by in-process tests; TestClient ≠ real HTTP. | **ACCEPT — moot for 2a, required for 2b** | The service endpoint is deferred (OOB2-4); when 2b ships it, a real out-of-process HTTP test (subprocess + socket) is a landing requirement, not TestClient-only. |
| BR2-10 | Lock-stealing via future-mtime / PID reuse on a shared `.charon/`. | **ACKNOWLEDGE — Mode-B isolates** | Real only on a shared state dir; the Mode-B container isolates it (INV-B4). Tracked as a watched class; not a 2a blocker. PID-liveness check folded into the 2b/Tier-4 hardening list. |
| D5 | Is folding both Tier-2s one tier too big? | **RESOLVED: yes — split.** | Tier 2a = handoff + multi-backend (serves Mode A now, low blast radius). Tier 2b = service + publish (gated on hardening + a consumer). The coupling "Mode B needs both" is real but Mode B's consumer is the Tier-3 host-project adapter — no reason to ship the endpoint ahead of it. |

### Net effect on the build (Tier 2a — folded into PLAN-tier2 §"Reconciled scope")
1. Multi-backend coordinator + CLI/API; router seeded with all backends.
2. Exclude-accumulation fix (full set) + backend-coverage guard + re-verify-before-advance.
3. `task_id` validation at the ledger boundary (path-traversal closed everywhere).
4. Proofs re-shaped to be non-tautological: restart/no-replay + lying-backend-across-handoff (proven-red), plus exclude-accumulation.
5. `SUPPLY-CHAIN.md` as the gateway gate; gateway port itself deferred (YAGNI).
6. Docker build-smoke in CI (no publish); honesty register: cross-vendor proven as a *contract* only, live endpoint + GHCR publish = Tier 2b with enumerated security prerequisites.

No WALK-BACK-LOG entry: all additions/strengthenings; the only scope change is a deferral (service → 2b), recorded above.
