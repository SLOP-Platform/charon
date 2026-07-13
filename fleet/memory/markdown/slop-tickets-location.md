---
description: "Where the SLOP ticket pool actually lives (reconstructed) + why the migration \"broke\" it"
metadata: 
name: slop-tickets-location
node_type: memory
originSessionId: ebcf9a1e-605b-4f25-ae5c-e6f7580be989
type: project
tags: [mediastack, slop]
last_referenced: 2026-07-13
---
**SLOP = the `mediastack` repo** ("Self-hosted Linux Orchestration Platform"). The outstanding
SLOP tickets are a **SQLite DB**, not GitHub issues / markdown:

- **Canonical store:** `/repo/mediastack/tracking/tracking.db`, table `backlog_items`,
  driven by `python3 tracking/query.py` (subcommands: `open|add|close|batch|batches|decisions|optimize`).
- **Outstanding (as of 2026-06-26):** **31 `open`** + 14 `parked` (760 done). Tickets have
  id (int), status, batch (`BATCH-NN`), intake tier `S/R/D/F`, priority `P0-P5`, category enum.
- The other 6 DBs (`tickets.db`, `slop.db`, `tracker.db`, `backlog.db`, `dev_tracking.db`, root
  `tracking.db`) are **empty 0-byte decoys**. `tracking/paths.py::tracking_db_path()` is the SSOT
  path resolver (env `MS_TRACKING_DB` override → else main-worktree `tracking/tracking.db`).

**Why it seemed "broken" by the SLOP-Platform org migration:** the DB is **gitignored +
main-tree-only** — it never travels in git history. The slop→mediastack split (BATCH-15 S3) and
the org transfer (#1317) carried the *repos* but left the DB behind in the working tree, so the
GitHub repos (`SLOP-Platform/SLOP`, `/mediastack`) have NO ticket pool. The live pool survived
locally at the path above. Any Charon-driven revival must carry the DB explicitly.

**Workflow (SLOP "Manager" method):** find=`query.py open` · claim=`.claude/mailbox/claim_work.sh`
(tier-routed) · work in a worktree · gate=`ms-enforce --fast` GREEN + `mypy --strict` +
PROVEN-RED regression test same-commit + syrupy snapshots + ms-coverage RULES entry for new bug
classes · close=`query.py close <ID> --proof <git-SHA|tracked-path>` (GROUND-validated, refuses
fake proof). Manager charter = `mediastack/docs/MANAGER-HANDOFF.md`.

**DOCTRINE DIVERGENCE vs Charon (discuss before writing the SLOP guide):** SLOP **retired**
"manager never spawns" on 2026-06-13 (manager orchestrates in-session) — the OPPOSITE of Charon's
[[manager-never-spawns-droids]]. SLOP also had a logged incident of the manager acting without
operator approval — the cautionary tale behind [[adversarial-review-must-not-silently-override-operator]].
