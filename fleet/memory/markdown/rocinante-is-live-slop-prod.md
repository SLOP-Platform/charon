---
description: Rocinante (<LEGACY_HOST>) is an OLD SUPERSEDED SLOP box (current SLOP runs on BB-8/.61); being repurposed as the Charon durable-bridge coordinator after backing up its config
metadata: 
name: rocinante-is-live-slop-prod
node_type: memory
originSessionId: fbcc2b18-3ba9-4057-b3fd-af8c3e6ffb84
type: reference
tags: [ci, mediastack, slop]
last_referenced: 2026-07-13
---
**Rocinante = <LEGACY_HOST> was an OLD, SUPERSEDED SLOP/mediastack deployment — current live SLOP now runs on BB-8 (<COORDINATOR_SUBNET_HOST>).** It LOOKS live (containers up, long uptime) but is frozen/stale; verified read-only 2026-07-06/07.

Evidence it's superseded (safe to repurpose): git HEAD `c3316bd6` (Jun 19), remote points at the **defunct `Nnyan/SLOP`** (not active `SLOP-Platform/mediastack`, pushed 2026-07-07); all 11 containers frozen since **May 23** (~6wk, never restarted); its GH Actions runner "rocinante" died Jun 26 (active pool is self-hosted-runner/2/3); `/mnt/media` empty & unmounted (no media data).

**DECISION (2026-07-06): repurpose Roci as the neutral Charon durable-bridge COORDINATOR host.** Before the destructive decommission, back up the only Roci-only data: `/srv/mediastack/config/*` (~310MB, single tar → `~/backups/roci-decommission/`) + root spot-check `/var/lib/mediastack/komodo/periphery` for keys (needs sudo — Roci has NO passwordless sudo for user `stack`; operator runs it). Then `docker compose down` + disable `mediastack.service` + de-register the dead runner, add avahi/scoped-sudo, deploy the daemon. SSH: alias `rocinante` now DIRECT (jumpbox removed), key `~/.ssh/mediastack`. Follows [[investigate-and-backup-before-data-loss]]; see [[durable-bridge-rework]].
