# You are working a SLOP ticket

Read `GROUNDING-CHARON.md` first — the *discipline* of working a ticket (touch only what you own,
satisfy the executable `accept` literally, gate green every commit, draft PR never merge, STOP if
blocked) is IDENTICAL. This doc covers only what's DIFFERENT about SLOP.

## What SLOP is (and where its tickets live)
SLOP = the **mediastack** repo (`/home/stack/code/mediastack`). Tickets do NOT live in markdown —
they live in a sqlite DB **`tracking/tracking.db`**, read/written via **`tracking/query.py`** (the
DB is gitignored / local-only). Key ticket fields (`backlog_items`): `id, title, status, priority,
description, surface, tier, kind, notes`.
- **`surface`** = a repo-relative path GLOB. It is SLOP's `owns` — the files you may touch. Treat it
  exactly like Charon's `owns`: edit ONLY within `surface`; need more → STOP and report.
- **`status`**: `open` = workable. `parked` = on-hold, don't auto-work. `closed/done/cancelled` = finished.
- **Dependencies & Sequence (D&S)**: every ticket's `description` has a `--- D&S ---` … `--- /D&S ---`
  block (depends_on / wave / owns / concurrency). USE IT to order work and avoid collisions — same
  as Charon's D&S.

## Reading a ticket
`python3 tracking/query.py <subcommand>` (run `--help`). Find your ticket, read its `description`
(goal + the D&S block) and `surface`. There may not be a single executable `accept` string like a
Charon ticket — derive the verification from the ticket text + mediastack's own tests; the bar is
"the change does what the ticket says AND mediastack's gate stays green."

## Two ways to work a SLOP ticket
- **Directly in mediastack:** branch mediastack, implement within the `surface`, keep **mediastack's
  own gate/enforcement** green (it has CI + numbered, checksum-gated migrations — do NOT `ALTER
  TABLE` ad-hoc; add a numbered migration), open a DRAFT PR to `main`. Never merge.
- **Via Charon (bridge):** export the SLOP ticket to Charon intake format (the DOGFOOD exporter —
  spec at `dogfood/SLOP-EXPORT-SPEC.md`; may not be built yet, check) → `charon intake import` →
  `charon work`. Then it behaves exactly like a Charon ticket.

## SLOP-specific cautions
- The DB is **local/gitignored**: your ticket-field edits (status, D&S) are local; only tooling
  changes (`query.py`, source) commit to `main`. **Back up before any bulk DB write**
  (`cp tracking.db tracking.db.bak-<date>`).
- Respect mediastack's enforcement: migration discipline, ratchets, and the run-alone / serialize
  flags in the D&S blocks (e.g. tests/-surface tickets that must not run concurrently).
- Never commit the DB, backups, or secrets.

Everything else — touch only your surface, satisfy the verification, gate green, draft PR, never
merge, STOP when blocked — is the same as the Charon grounding.
