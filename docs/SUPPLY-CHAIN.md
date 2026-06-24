# Supply chain — the gate before anything enters the privileged loop

Charon at autonomy ≥ L1 spawns CLI coding agents and can apply their diffs. Any
dependency that runs *inside that loop* is part of the trust boundary. This
document is the **gate**: a dependency or external service does not enter the
privileged loop until it passes the criteria below and is signed off here.

It exists because the Tier-1 review (REVIEW-LOG, BR-3/BR-4) pushed the network
**gateway** (OpenAI-compatible routing) out of the loop until such a gate
existed, and the Tier-2 review (OOB2-6) required the "green" criteria be defined
rather than left implicit. Routing stays **native/static** until the gateway
passes this gate.

## 1. Current state (Tier 2a)

- **Core / privileged loop runtime deps: none.** `pyproject.toml` `dependencies =
  []` — the coordinator, ledger, fence, handoff, and adapters are stdlib-only.
  This is the property that makes the privileged loop auditable: there is nothing
  third-party in it to vet.
- **`[service]` extra** (FastAPI / uvicorn / pydantic) is **not** in the
  privileged path — it is the optional Mode-B HTTP surface, installed separately,
  and (Tier 2b) will front the loop only behind the hardening enumerated in
  `PLAN-tier2.md §8`.
- **`[dev]` extra** (pytest / ruff / mypy / pip-audit) never ships to a runtime.
- **No network gateway is wired into the loop.** Routing is a static native
  policy (`router.py`). This is deliberate, not pending.

## 2. Gate criteria — a dependency MAY enter the privileged loop only if ALL hold

1. **Boundary-clean.** The AST boundary scan (`tools/check_boundary.py`) shows no
   `slop`/`mediastack` import path, directly or transitively (INV-B1/B5).
2. **Protocol-only coupling.** It is reached through a standard protocol
   (OpenAI-compatible HTTP, ACP, MCP) behind an internal port — never a
   vendor-specific API baked into the coordinator (INV-P0).
3. **Pinned.** Pinned to an exact version (and, for container bases, a digest).
   No floating ranges on anything in the loop.
4. **Audited.** `pip-audit` is clean for the resolved set; a human has read the
   changelog/source surface for the pinned version.
5. **Minimal & justified.** It earns its place — there is no stdlib or
   already-present way to do the job. Transitive footprint is reviewed, not just
   the top-level package.
6. **Revocable.** Removing it returns the system to a working state (the port
   stays; only the adapter goes). No dependency becomes load-bearing for the
   Ledger, which is git + JSON and outlives any of them (sunset clause).

## 3. Verification SOP (run before sign-off, and in CI where possible)

```bash
python3 tools/check_boundary.py src    # criterion 1 (also a CI gate)
pip-audit                              # criterion 4 (CI runs it advisory today)
pip install --dry-run <pinned-spec>    # inspect the transitive resolution
# read the diff of what the pin pulls in; confirm protocol-only usage in code
```

## 4. Sign-off register

No third-party dependency has entered the privileged loop. When one is proposed
(first candidate: the OpenAI-compatible gateway client, Tier 2.5), add a row:

| Date | Dependency @ pin | For | Criteria 1–6 | Reviewer | Verdict |
|------|------------------|-----|--------------|----------|---------|
| —    | (none)           | —   | —            | —        | —       |

## 5. Container images (Tier 2b, when publish lands)

- Pin the base by digest: `FROM python:3.12-slim@sha256:<digest>`.
- Pin the installed `charon` version in the image.
- Publish only `:vX.Y.Z` (immutable); `:latest` is a moving target, not for
  production.
- Attach SLSA provenance / attestation at publish time.
- Until then, CI only **builds** the image (no registry push), so there is no
  publish token surface to compromise.
