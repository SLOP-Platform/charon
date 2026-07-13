---
description: Keep Charon-the-product (ships standalone) strictly separate from the home build-rig (fleet/SLOP/runner that does NOT ship); never let a local dependency leak into the product
metadata: 
name: product-vs-build-rig-boundary
node_type: memory
originSessionId: ebcf9a1e-605b-4f25-ae5c-e6f7580be989
type: project
tags: [build-rig, product]
last_referenced: 2026-07-13
---
Two things that must never be conflated:

- **HOME build/dev infrastructure — does NOT ship.** The fleet rig (`/build-rig/fleet/`,
  droids, board, JOIN-PROMPT), SLOP / mediastack + `tracking.db` + `ms-*` tools, and the
  self-hosted **self-hosted-runner** GitHub runner. This is how Charon gets *built*; none of it installs on
  anyone else's machine.
- **CHARON the PRODUCT — ships, must stand alone.** The gateway, engine, CLI, web console.
  Stdlib core, `pipx install charon`, **zero dependency on the home rig.** It runs on a stranger's
  PC / server / cloud with none of the operator's infrastructure present.

**Tier work respects this:** product-side TIER-1/2/3/4/7 (config, gateway, cli, web-UI, engine
routing) SHIP; rig-side TIER-5/6 (`claim.sh`/`fleet-droid.sh`) are local-only.

**Open product-portability concern — GitHub runners for remote installers:**
- An END-USER who `pipx install`s + runs Charon needs **no runner at all** (no CI in their life).
- A FORKER/CONTRIBUTOR who clones Charon inherits workflows pinned to `[self-hosted, self-hosted-runner]` —
  the operator's runner, which they don't have → their CI jobs queue forever. Fix: a
  GitHub-hosted-runner fallback / fork-friendly workflow, or gate self-hosted jobs to the home
  repo, or document "bring your own runner."

**Also:** the dogfood "read SLOP tickets" adapter must be a GENERAL intake source, NOT
`tracking.db`-hardcoded, or the product picks up a dependency on the home world.

Apply the [[standing-blast-radius-lens]] to catch any local dependency creeping into the product.
