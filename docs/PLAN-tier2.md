# Charon — Tier 2 build plan (pre-review draft)

> Implements ADR-0001 §9 Tier 2 (gateway routing + handoff, second backend) and
> ADR-0002 §5 Tier 2 (service surface + image → Mode B possible). Built on the
> green Tier-1 continuity core (Ledger, fence, ports, coordinator). Bounded by
> the Tier-1 review reconciliation (REVIEW-LOG 2026-06-23), which already pushed
> the network gateway out of the privileged loop pending a supply-chain audit.

## 0. Scope contract (what "Tier 2 done" means)

Tier 2 lights up the two things Tier 1 deferred but built the seams for:

1. **Cross-vendor handoff, live-proven (H3/H4/H5/H6).** Tier 1 built the
   H-predicates and unit-tested them against a single mock. Tier 2 proves the
   *whole loop* end-to-end across **two distinct backends**: backend A makes
   partial progress then exhausts; the coordinator snapshots, re-routes excluding
   A (H6), and backend B — a different "vendor" — rehydrates from `ledger + disk`
   alone (H3), continues without replaying A's committed work (H5), and reaches
   acceptance. The deterministic proof vehicle is a **second mock backend**
   (`mock-a` / `mock-b`); live ACP-to-ACP cross-vendor handoff still needs two
   real ACP agents (not in this env) and stays gated behind `charon doctor`.

2. **HTTP service surface live (Mode B becomes possible).** Tier 1 shipped the
   route *shapes*; Tier 2 makes them real: create a run, fetch a run/ledger, list
   runs — backed by the same public API the CLI uses. The service is the fenced
   boundary the host project talks to in Mode B; its security posture is part of
   this tier.

3. **Container image buildable + CI publish path.** The Tier-1 `Dockerfile` runs
   the service; Tier 2 makes CI build it and (on a version tag) publish to
   `ghcr.io/slop-platform/charon`. Mode B = "pull the image, talk to the API."

Out of Tier 2 (still ports/stubs): live network gateway routing (gated on
`SUPPLY-CHAIN.md`, see §5), consensus plane (Tier 3), autonomy L2/L3 +
parallelism (Tier 4), the host-project-side integration adapter (lives in the host
project's repo,
ADR-0002 §2.5).

## 1. Cross-vendor handoff (ADR-0001 §4 — the only hard build left)

### 1.1 Multi-backend coordinator

Today `coordinator.run` accepts a `Mapping[str, AgentBackend]` but the demo path
wires exactly one. Tier 2 makes multi-backend real:

- `api.run_task` / CLI accept **more than one backend** (`--backend mock-a,mock-b`,
  or a `.charon/backends.json` registry mapping name → adapter spec).
- The router is seeded with the full backend list; `route(..., exclude=exhausted)`
  already returns the first non-excluded candidate (H6).

### 1.2 Fix the exclude-accumulation gap (correctness)

In `coordinator.run`, when a freshly-routed backend reports `health().exhausted`,
the code calls `choose_next_backend(router, task_class, route.backend)` which
excludes **only that one backend**, not the accumulated `exhausted` set. With ≥3
backends and ≥2 exhausted, this can re-pick an already-exhausted backend. Fix:
re-route against the full `exhausted` set (drop `choose_next_backend`'s
single-exclusion signature or pass it the whole set). Add a proven-red test:
three backends, two exhausted, assert the third is chosen and never a repeat.

### 1.3 The handoff proof (proven-red, two backends)

`test_handoff_crossvendor.py`:

- **H4 (exhaustion → handoff, not retry-on-same):** `mock-a` SATISFY for 1 file
  then flips `health().exhausted`; assert the next dispatch goes to `mock-b`, not
  `mock-a` again. `provider_history == ["mock-a", "mock-b"]`.
- **H3 (idempotent rehydration):** after A's checkpoint, assert
  `rehydrate_remaining(ledger)` computed by B equals what A would compute —
  identical `remaining` set, because acceptance is executable (INV-6). Test both
  backends derive the same set from the same `ledger + disk`.
- **H5 (no progress loss):** A's committed file survives the handoff (present on
  disk and at `lkg`/checkpoint commit); B only does the *remaining* delta, never
  re-creates A's file.
- **H2 (boundary, not mid-trajectory):** handoff happens at a checkpoint
  boundary — assert no partial/uncommitted A state leaks into B's dispatch.
- **Completion:** B finishes the remaining acceptance; run status `complete`,
  `lkg` advanced only at full verification (INV-2), at autonomy L1.

This exercises the real privileged path (not just asserted), per the Tier-1
BR-6 discipline.

## 2. HTTP service surface (ADR-0002 §2.4 surface #3, Mode B)

### 2.1 Endpoints (versioned `/v1`)

- `POST /v1/runs` → start a run; returns `{task_id, status, ...}`. Body =
  `RunRequest` (goal, accept[], repo?, autonomy, budget, backends?).
- `GET /v1/runs/{task_id}` → derived ledger state (verified/remaining/lkg/
  provider_history/checkpoints) — reuses `api.show_ledger`.
- `GET /v1/runs` → list known task ids under the state dir.
- `GET /healthz` → liveness + version (exists).

Runs are **synchronous-bounded** in Tier 2 (the coordinator loop is already
bounded by `max_checkpoints`); async/background execution + run cancellation is a
Tier-4 concern (parallelism, PERF-4). Stated honestly, not faked.

### 2.2 Security posture (this is a real decision — see §5)

The service fronts the privileged agent-spawning loop. Tier 2 default posture:

- **Bind `127.0.0.1` by default**; binding `0.0.0.0` requires an explicit env/flag
  and prints a warning. In Mode B the container + the host project's fence are the real
  boundary (ADR-0002 §2.3, INV-B4).
- **Default autonomy L0** on the service path too (nothing applied unless the
  caller explicitly raises it).
- **Optional bearer token** (`CHARON_SERVICE_TOKEN`): if set, required on
  mutating routes. Off by default for localhost dev; documented as REQUIRED for
  any non-loopback bind.
- The service does **not** widen the autonomy ladder — it cannot reach above what
  the caller requests, and never above the fence (INV-B4).

### 2.3 Tests

FastAPI `TestClient` against `service.app`: healthz, a full `POST /v1/runs` →
`GET /v1/runs/{id}` round-trip on the mock backend, 404 for unknown task, token
enforcement when `CHARON_SERVICE_TOKEN` is set. Add `[service]` to the dev extra
so CI exercises it.

## 3. Container image + CI publish (ADR-0002 §5 Tier 2)

- Confirm the existing `Dockerfile` builds and `CMD` launches the service
  (uvicorn on the fenced port). Add a `make image` target.
- CI: a `docker build` job on every push (proves the image isn't bit-rotting);
  a **publish-on-tag** job pushing `ghcr.io/slop-platform/charon:vX.Y.Z` + `:latest`
  using `GITHUB_TOKEN` with `packages: write`. Honest: the image runs the
  fenced service, not the bare privileged loop.
- `docker-compose.yml` updated to bind loopback by default.

## 4. Router evolution (predictive, still native)

Routing stays a **static native policy** in Tier 2 (no network gateway — §5).
The only change: the router is now genuinely multi-backend and its
exclude-routing is exercised by the handoff tests. Success-rate/bandit feedback
remains Tier 4 (PERF-3 keeps routing predictive, never run-all-then-pick).

## 5. Decisions for adversarial review

These are the live forks Tier 2 must resolve before code. The reviewer attacks
each; the author reconciles in REVIEW-LOG.

- **D1 — Gateway now or deferred?** ADR-0001 §9 names "gateway routing" as Tier 2.
  Tier-1 reconciliation BR-3 pushed any *network* gateway out of the privileged
  loop until a `SUPPLY-CHAIN.md` audit exists. **Proposed:** Tier 2 ships
  `SUPPLY-CHAIN.md` (audit criteria + pinning policy) and a gateway **client port**
  (no live network call wired into the loop); live gateway routing is Tier 2.5,
  unblocked only when the audit is green. Routing stays native/static meanwhile.
- **D2 — Proof vehicle for cross-vendor handoff.** No second live ACP agent in
  this env. **Proposed:** a second *mock vendor* is the deterministic proof; the
  H-predicates are vendor-agnostic by construction (portable unit = files+ledger),
  so two mocks prove the contract. Live ACP-to-ACP stays gated on `doctor`.
  Reviewer: is a two-mock proof real, or theater that hides a vendor-specific
  assumption?
- **D3 — Service security default.** Bind loopback + optional token + L0 default,
  leaning on the container/host-project fence for true isolation. Reviewer: does the HTTP
  surface open a privileged-loop hole that the in-process fence can't close, and
  is "container is the boundary" honest for Mode A users who run the bare service?
- **D4 — Sync-bounded runs.** Runs block the request up to `max_checkpoints`.
  Reviewer: acceptable for Tier 2, or does it strand clients / invite timeouts
  badly enough to need background runs now?
- **D5 — Scope size.** Two ADR Tier-2s folded into one build. Reviewer: is this
  too much for one tier — should service+image split to a Tier 2b — or is the
  coupling (Mode B needs both) real enough to ship together?

## 6. Tests (the proof, not the claim) — additions

- `test_handoff_crossvendor.py`: H2/H3/H4/H5 across two mock vendors + completion
  (§1.3); exclude-accumulation with 3 backends (§1.2).
- `test_service.py`: healthz, run round-trip, 404, token enforcement (§2.3).
- `test_boundary.py`: unchanged (still proves planted `import slop` fails) — plus
  assert the new service/gateway-port modules carry no host-project path.
- Existing 36 stay green.

## 7. Non-goals / honesty register (Tier 2 additions)

- Live cross-vendor handoff between two *real* ACP agents is **not** proven here
  (no second live agent) — only the vendor-agnostic contract is, via two mocks +
  `doctor` for real-backend fidelity.
- No live network gateway in the privileged loop (D1); `SUPPLY-CHAIN.md` is the
  gate.
- Service runs are synchronous-bounded; no background execution / cancellation /
  multi-tenant isolation (Tier 4).
- The bare Mode-A service is **not** a hardened multi-user endpoint; true
  isolation is the Mode-B container under the host project's fence (INV-B4).

## 8. Reconciled scope (post-review, 2026-06-24 — supersedes §0–§6 deltas)

Adversarial review (REVIEW-LOG 2026-06-24) **split this tier**. The HTTP run
endpoint + GHCR publish front the privileged loop, have no consumer until the
Tier-3 host-project adapter, and carry CRIT holes — deferred to **Tier 2b**, to ship only
with the Lens-A hardening. This build is **Tier 2a**:

**Tier 2a (this build):**
1. **Multi-backend** coordinator + CLI/API (`--backend a,b`); router seeded with
   all backends.
2. **Exclude-accumulation fix:** `choose_next_backend(router, task_class,
   exclude: set)` re-routes against the full `exhausted` set; backend-coverage
   guard (router backends ⊆ available) → loud, not `KeyError`; **re-verify
   `remaining` immediately before `advance_lkg`** (INV-2 insurance).
3. **`task_id` validation** at the ledger boundary (`^[a-z0-9][a-z0-9-]{0,63}$`) —
   path traversal closed for every surface, now.
4. **Proofs (proven-red), re-shaped to be non-tautological:**
   - exclude-accumulation: 3 backends, 2 exhausted → 3rd chosen, no repeat;
   - restart/no-replay: reload ledger between checkpoints, completed checkpoint
     not replayed, A's committed file not re-created (H3/H5);
   - **lying-backend-across-handoff:** mock-a claims done but satisfies nothing →
     handoff → mock-b rehydrates from ledger+disk, `remaining` still non-empty —
     the lie does not survive the vendor boundary (the real H3 content);
   - happy-path cross-vendor completion (provider_history == [a, b]).
5. **`SUPPLY-CHAIN.md`** — the audit gate that must be green before any network
   gateway enters the privileged loop (the gateway port itself stays unbuilt —
   YAGNI).
6. **Docker build-smoke** in CI (build only, no push); honesty register updated:
   cross-vendor handoff proven as a vendor-agnostic *contract*, not a live result.

**Tier 2b — split into "now" vs "with-consumer" by a DTC (REVIEW-LOG 2026-06-24).**

*Shipped now (consumer-independent, safe):*
- **GHCR publish path** — release-triggered, gated on the full test gate +
  image-smoke, base digest-pinned at release time (recorded in SLSA provenance),
  `:vX.Y.Z` only, native `attest-build-provenance` (no cosign). See
  `SUPPLY-CHAIN.md §5` and the `publish` CI job.
- **Web surface neutered honest:** `service/app.py` is **read-only** (healthz +
  derived ledger read) and **refuses** runs with `501` rather than running the
  privileged loop in-process. A structural test
  (`test_service_app_runs_no_privileged_loop_in_process`) enforces that the web
  module references no privileged-exec symbol (`run_task`/`coordinator`/
  `dispatch`) — the literal ADR-0002 §2.3 / INV-B4 topology.

*Design of record — built WHEN the Tier-3 host-project consumer lands (not ahead of it):*
the **web/worker split**. The exposed web process validates + enqueues one inert
job record (atomic write) and **never imports the privileged loop**; a separate
worker container (`network_mode: none`, shared `.charon` volume only) drains it
and runs `api.run_task`. Request shape drops `repo` entirely (runs only in an
auto-created sandbox — operator-repo branch unreachable from HTTP); `budget`
clamped; `CHARON_SERVICE_TOKEN` required (and startup hard-fails) on any
non-loopback bind; acceptance exec runs **`shell=False`** (parsed argv) on the
service path; service autonomy pinned **L0** unless an operator opts in (with a
logged "live agent RCE in the worker" warning). Explicitly **NOT** built: a
durable queue/lease/reclaim broker, an HMAC-signed policy file, an argv0
allowlist module, or threading service concerns into the zero-dep core — all
rejected on thinness/YAGNI (no consumer yet).

*Honesty (must mirror in README at the opt-in):* the Mode-B **container** is the
only real boundary for a live skip-permissions agent; in-process guards bound the
caller/request, not a determined agent. The shared `.charon` volume is a
**bidirectional integrity seam** — a compromised worker can write ledger records
the web layer serves back as truth; one-way code isolation is not one-way data
isolation.

- Gateway live wiring — separately gated on `SUPPLY-CHAIN.md` green (Tier 2.5).
