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

## 5. Container images (Tier 2b — publish policy, reconciled)

Reviewed adversarially (REVIEW-LOG references BR2-8; GHCR-publish focused review
2026-06-24). The GitLab Container Registry detour (2026-06-25) was UNWOUND the
same day (HANDOFF §9 — GitLab abandoned for the public GitHub `SLOP-Platform`
org); the registry/provenance path is back to the original GHCR + GitHub-native
SLSA design, which is the cleanest option here. The deterministic guarantees
below are unchanged across all of this — only the host plumbing moved (see
`.github/workflows/release.yml` `publish`). Decisions:

- **Base pinned by digest, resolved at release time.** The `Dockerfile` base is a
  build-arg (`BASE_IMAGE=python:3.12-slim`); the `publish` CI job resolves the
  current digest (`docker buildx imagetools inspect`) and
  builds with `BASE_IMAGE=python:3.12-slim@sha256:…`. The pin is therefore real
  and fresh, recorded in the build log — never a stale hardcoded value, never
  fabricated. The plain tag is used only for the non-publishing CI build-smoke.
- **Installed `charon` is the checked-out source** at the release tag; the
  `publish` job asserts the **git tag matches `pyproject.toml` version** (no
  drift), so the image contains exactly the released version.
- **Trigger = a published GitHub Release** (`on: release: [published]`); the
  `publish` job `needs: [gate, image-smoke]` so the full gate + image build-smoke
  must pass first — an untested image can never be published (BR2-8). The job also
  asserts the release tag `vX.Y.Z` matches the package version. Off the release
  path there is **no publish token surface**.
- **Only `:vX.Y.Z` is pushed** (immutable per semver). `:latest` is **not**
  published — it is a silent-upgrade footgun. Operators pin explicit versions.
  Do not delete/re-create a published tag (silent swap of a different image).
- **Provenance — RESTORED (the GitLab "open item" evaporated).** Back on GitHub,
  the publish job attests build provenance with GitHub-native
  `actions/attest-build-provenance` (OIDC + transparency log), verifiable with
  `gh attestation verify`. No key management: the GitHub OIDC `id-token` is
  minted per-run and scoped to the workflow. **cosign is still deliberately not
  used** (it adds key-management burden without addressing the real threat: a
  compromised runner would hold the cosign key too) — the OIDC path needs no
  stored key. The deterministic integrity guarantees (digest-pinned base,
  tag↔version match, gated-on-tests, immutable tag) hold regardless. Honesty
  (unchanged): provenance attests *build integrity*, **not** dependency safety —
  that is `pip-audit` + this gate's job.
- **Credentials** are the minimum: the publish job logs into GHCR with the
  per-run `${{ secrets.GITHUB_TOKEN }}` (scoped `packages: write` only on the
  release path), never a long-lived personal token; it exists only on that path.
- **Namespace** is lowercase `ghcr.io/slop-platform/charon` (GHCR lowercases org
  names; the public web repo is `github.com/SLOP-Platform/charon`).
- **Multi-arch (arm64)** is deferred (YAGNI until a consumer deploys on arm64);
  v0.1.0 publishes `linux/amd64` only, disclosed as such.
- **Base-digest renewal** is manual + intentional (no auto-bump bot yet): the
  publish job always re-resolves the live digest, so each release pins whatever
  is current; a deliberate base upgrade is just a normal release.
