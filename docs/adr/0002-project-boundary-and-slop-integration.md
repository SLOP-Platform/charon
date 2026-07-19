# ADR-0002 — Project Boundary & Host-Project Integration

- **Status:** Accepted (2026-06-26)
- **Deciders:** project maintainer
- **Repo:** `github.com/SLOP-Platform/charon` *(name TBD; `charon` is a placeholder)*
- **Relates to:** ADR-0001 (orchestration harness architecture — the prior
  artifact, renumbered into this repo as 0001)
- **Methodology:** ADR + tiered; ports-and-adapters; derive-or-verify;
  structural enforcement over honor-system

---

## 1. Context

The harness is now its own project with its own GitHub repository. It must be
usable two ways without divergence:

1. **Standalone** — an operator runs it against any project, with no host
   project present.
2. **Embedded** — a host project can include it as a first-class capability.

The risk is that "embeddable in a host project" quietly degrades into one of the failure
modes derive-or-verify exists to prevent: a vendored copy that drifts from
upstream, a git submodule that no one keeps pinned, or — worst — a cyclic
dependency where the harness grows host-specific code and stops being
standalone. This ADR fixes the boundary so neither happens.

---

## 2. Decision

### 2.1 Cardinal rule — dependency direction is one-way and acyclic

```
host project  ───depends on──▶  charon    ✅
charon  ───depends on──▶  host project    ❌ never
```

The harness has **zero knowledge of any host project.** No host imports, no host config
keys, no host-shaped assumptions. This is the single property that makes
"standalone and embeddable" coherent rather than contradictory. Everything else
in this ADR follows from it.

### 2.2 Distribution — pinned versioned artifact; never vendored, never submodule'd

A host project consumes the harness as a **pinned, versioned dependency**, in two forms:

- **Python package** — semver-tagged; the host pins
  `charon @ git+https://github.com/SLOP-Platform/charon@vX.Y.Z` (or a registry pin
  if/when published). A deploy key authenticates the published repos.
- **Container image** — published to `ghcr.io/slop-platform/charon:vX.Y.Z` for the
  service consumption mode (§2.3, Mode B).

Vendoring and submodules are **rejected**: both duplicate the source of truth
and reintroduce the version-drift class (a prior governance audit already found
~15 satellite files drifting against one canonical version — do not recreate
that across repos). One true home for the harness is the harness repo; the host
holds only a pinned reference to a released version.

### 2.3 Consumption modes (tiered)

- **Mode A — Standalone.** `pipx install charon` or clone + run the CLI. This
  is the harness's primary identity; it is developed and tested as if no host
  project existed.
- **Mode B — host-managed service (recommended embed).** The host runs the
  harness as one of its orchestrated apps via its existing manifest/executor
  system, behind its control-plane fence. The harness runs as its **own container /
  process**; the host talks to it over the harness's service API. The privileged
  agent-spawning loop (which runs CLI agents with skip-permissions) stays
  isolated from the host's web process, and the host's fence governs access to
  it. This is idiomatic: the host orchestrates self-hosted apps; the harness is
  one of them, with a first-class integration adapter.
- **Mode C — host-native workflows (optional, tighter).** A thin host-side
  client wraps the harness's public API for in-product workflows (e.g. the host
  UI triggering a run). Lives in the host repo; depends only on the harness's
  public API, never its internals.

> **Recommendation: embed via Mode B (service), not in-process library.** The
> harness runs unattended privileged operations; isolating it as a fenced
> service keeps its blast radius out of the host's main process and lets the host's
> existing control-plane fence be the single gate. In-process library embedding
> would pull the privileged loop inside the host's trust boundary for no benefit.

### 2.4 Public API contract

The harness exposes exactly **three** stable, semver-versioned surfaces. A host
project may depend on these and nothing else:

1. **CLI** — the standalone entry point.
2. **Python public API** — one small public module; not internals.
3. **Service interface (HTTP)** — for Mode B.

Everything outside these three is private and may change without a major-version
bump. This is the ports-and-adapters boundary applied across the repo line: the
three surfaces are the *port*; the host's integration is an *adapter* on the
host's side.

### 2.5 Integration glue lives in the host project, not in the harness

No host-specific code ships in the harness repo. The host app manifest, the
fence wiring, and any Mode-C client are owned by the **host** repo. The harness
documents its API contract; it does not ship a sample host manifest (that would
be a second copy of a fact the host owns — a derive-or-verify violation across
the repo boundary).

---

## 3. Invariants

- **INV-B1.** The dependency graph is acyclic; `host project → charon` only.
- **INV-B2.** A host project depends only on the harness's three public
  surfaces (§2.4), never on internals.
- **INV-B3.** The harness is consumed as a pinned versioned artifact; it is
  never vendored or added as a submodule.
- **INV-B4.** In Mode B, the harness runs as a fenced service; the host's
  control-plane fence governs access. The host gets no back door around the
  autonomy ladder defined in ADR-0001 §7.
- **INV-B5.** No host-specific code exists in the harness repo; host
  integration lives in the host repo.
- **INV-B6.** The harness's CI proves Mode A in isolation (no host project on
  the build path), guaranteeing standalone never bit-rots behind the embed.

---

## 4. New-repo hygiene (decisions carried from a prior governance audit)

That governance audit surfaced specific failure classes; the new repo starts
clean of them by construction:

- **README honesty.** The README must disclose what the system actually does —
  including that it spawns CLI agents and runs an autonomous privileged loop.
  (The audit found a substantial agent subsystem hidden from the README, MAP,
  and compose file; the new repo does not get to start with that debt.)
- **CI/CD from day one.** The audited project shipped without CI enforcement.
  The new repo lands with CI on first commit: test suite, version-consistency
  check, and a boundary check that fails the build if any `import`/reference to
  a host project appears (enforces INV-B1/B5 structurally rather than on the
  honor system).
- **One true home for version.** A single canonical version source; checkers
  enforce agreement across any satellite (`pyproject.toml`, image tag, ADR
  references).
- **MIT license**, consistent with the other projects.

---

## 5. Tiered implementation plan

- **Tier 1 — Repo + standalone.** Stand up `SLOP-Platform/charon`, src-layout
  package, CLI, CI (incl. the host-import boundary check). **Mode A works.**
  Aligns with ADR-0001 Tier 1 (single adapter + Work Ledger + fence).
- **Tier 2 — Service surface + image.** Define the HTTP service interface;
  publish the container image to GHCR. **Mode B becomes possible.**
- **Tier 3 — host integration adapter (in the host repo).** The host installs
  the harness as a managed app behind its control-plane fence and talks to its
  service API. **Mode B live.**
- **Tier 4 — Optional Mode C.** Host-native UI workflows over the public API.

---

## 6. Alternatives considered

- **Git submodule / subtree.** Rejected: pin-drift and merge friction;
  reintroduces the satellite-drift class.
- **Vendored copy inside the host.** Rejected: duplicates the source of truth;
  guarantees divergence over time.
- **In-process library embed (no service).** Rejected as the *default*: pulls the
  privileged loop into the host's trust boundary with no upside. Retained only as a
  possible future optimization for non-privileged read paths, if one ever
  exists.
- **Build it inside the host, extract later.** Rejected: extraction-after-the-fact
  is where host-shaped assumptions leak in and cyclic dependencies are born.
  Separating now is cheaper than de-tangling later.

---

## 7. Consequences

**Positive.** The harness is useful on its own (to the operator and to anyone
else) and gains nothing it must later shed to stay standalone. A host acquires the
capability without absorbing the privileged loop into its core, and governs it
through the fence it already has. The boundary is enforced by CI, not goodwill.

**Cost.** A published API contract and a release process for a second repo;
discipline to keep host-specific needs out of the harness (the boundary check
makes that automatic for code, but design pressure to "just add one host hook"
will recur and must be refused).

**Reversibility.** If the embed is never built, Mode A stands alone with no dead
host code to remove. If a host project is retired, the harness is unaffected.
