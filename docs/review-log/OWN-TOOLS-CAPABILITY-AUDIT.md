# OWN-TOOLS-CAPABILITY-AUDIT — review fragment

**Date:** 2026-08-01
**Session:** own-tools-capability-audit

## Design decisions

1. **EVAL-REGISTRY.md updates OUT OF SCOPE.** The ticket note says "Verdicts and per-tool rows land in `fleet/state/EVAL-REGISTRY.md`; long-form in the owned file." But `EVAL-REGISTRY.md` is NOT in this ticket's `owns:` (`owns: fleet/state/OWN-TOOLS-CAPABILITY-AUDIT.md` only). Per rule §4b, `owns:` wins over prose. Per-tool findings are recorded in the owned file; a separate ticket must backfill EVAL-REGISTRY.md rows.

2. **TOOL-INVENTORY.md NOT UPDATED.** The inventory is ~60% complete (missing Faktory, session-bridge, basic-memory, pip-audit, yamllint, actionlint, and 30+ installed tools). This audit surfaces the gaps; the fix is a separate ticket (TOOL-INVENTORY-SWEEP or similar). This file is not in this ticket's owns:.

3. **Gate integrity scan WAS EXECUTED** — the INERT list comes from `bash fleet/checks/gate-integrity.sh scan`, not from reading source.

4. **ruff S vs bandit overlap WAS MEASURED** by the prior session (saba-sebatyne in TOOL-UTILIZATION-AUDIT). This audit reuses that measurement rather than re-running it, since the corpus and tool versions are unchanged.

5. **The Faktory exactly-once claim** is verified by: (a) reading Faktory's README (no unique-job guarantee in OSS feature list), (b) reading `lease-exactly-once.test.sh` which codes against the guarantee and guards with PENDING-FAKTORY, (c) the faktory-client.sh source which implements push/reserve/ack/fail/info with no dedup logic.

## Things I did NOT verify

- Product `tools/gates.json` vs umbrella runner divergence (cited from TOOL-INVENTORY.md, not independently verified against the product repo)
- The full litellm.Router parameter surface (~52 params from prior audit, not re-enumerated)
- The 30+ `~/.local/bin` scripts (not enumerated — 0 references in any fleet doc)
- The exact wiring of the product gate umbrella (`charon.cli gate`) — requires product repo access
