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
  Tier-3 host-project consumer, never ahead of it.

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
