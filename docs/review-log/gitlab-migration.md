## 2026-06-25 — GitLab migration (HANDOFF §9): CI port + registry + URLs

- **Change under review:** port the host-specific bits from GitHub to GitLab
  (`gitlab.com/slop-platform/charon`, registry
  `registry.gitlab.com/slop-platform/charon`). No application code changed — the
  code was already host-agnostic; this is `.gitlab-ci.yml` + URL/registry
  rewrites + the supply-chain doc.
- **Process:** mechanical port with two judgment calls recorded below; the gate
  stayed green throughout (114 passing). The pipeline is YAML-valid and
  structurally faithful to the GitHub one, but — disclosed honestly — **is not
  proven until it runs on GitLab** (needs the operator's first push); the first
  pipeline run is the real verification.
- **Faithful port:** all 4 jobs (`gate`, `modeA-isolation`, `image-smoke`,
  `publish`) preserved, including the full gate (boundary/version/ruff/mypy/
  pytest/pip-audit), the Mode-A clean-wheel isolation smoke (INV-B6), and the
  image build-smoke. `gate` now installs `[dev,service]` so the new dashboard
  tests run in CI. `git` is installed in the slim base (the loop makes real
  worktrees). GitHub's `needs: [gate, image-smoke]` is reproduced by **stage
  ordering** (test → image → publish): publish runs only if the prior stages
  passed.
- **Judgment call 1 — provenance (the one real fork).** GHCR policy used
  GitHub-native `actions/attest-build-provenance` (OIDC + transparency log).
  That mechanism is GitHub-specific and **has no drop-in GitLab equivalent that
  honors the policy's no-key-management constraint** (cosign was, and stays,
  deliberately rejected — a compromised runner holds the cosign key too).
  Decision: **preserve every deterministic guarantee** (digest-pinned base via
  `docker pull` + `RepoDigests` — no buildx dependency; tag↔`pyproject` version
  match; gated-on-tests; immutable `:vX.Y.Z` only, never `:latest`; min job-token
  creds) and record SLSA-attestation-for-the-image as an **explicit deferred
  operator decision** (GitLab native attestation vs cosign-keyless via GitLab
  OIDC), tracked in `SUPPLY-CHAIN.md §5`, not silently dropped. This is the
  honest call: I did not fabricate a provenance mechanism that may not fit the
  operator's GitLab tier.
- **Judgment call 2 — dind networking.** A host `-p` port-map under
  `docker:dind` lands on the dind daemon, not the job container, so the GitHub
  `curl 127.0.0.1:8473/healthz` would not reach the service. Reworked the
  image-smoke to curl from a **sidecar sharing the service's network namespace**
  (`docker run --rm --network container:charon-ci curlimages/curl …`) — the
  standard dind pattern.
- **Kept the GitHub workflow during transition** (operator's choice): harmless
  (it only runs on github.com); removable once GitLab is the source of truth.
- **What stays operator-only:** creating the remote + auth and pushing (handed
  over as `!` commands); the SLSA-provenance choice above.

WALK-BACK: none — additive (new `.gitlab-ci.yml`) + URL/registry rewrites; the
GitHub workflow is retained, not removed.
