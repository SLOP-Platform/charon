# DIFFICULTY-SCHEMA — difficulty field enforcement in validate_board.sh

**Date:** 2026-07-12
**Ticket:** DIFFICULTY-SCHEMA (tier: economy, difficulty: 1)

## What was done

Added `difficulty:` (1-5) enforcement to `validate_board.sh` PREFLIGHT GATE. Every live
ticket must carry a `difficulty:` field — missing or out-of-range (not 1-5) triggers RED
and a non-zero exit. Parked (`.md.parked`) and done tickets are exempt.

Backfill: 157 active board tickets auto-seeded `difficulty` from `tier` (economy=1,
standard=2, strong=3, peak=4, frontier=5) on 2026-07-10.

## Enforcement rules

- **Missing** → `difficulty-missing: <id> has no 'difficulty:' field (required — integer 1-5, auto-seeded from tier)`
- **< 1 or > 5** → `difficulty-invalid: <id> difficulty '<value>' is outside 1-5 range (got <int>)`
- **Non-integer** → `difficulty-invalid: <id> difficulty '<value>' is not a valid integer 1-5`

## Fail-on-revert verified

Isolated test: created a ticket without `difficulty:` → validate_board.sh exits 1,
outputs `difficulty-missing` RED. Invalid values (0, 6, "hard") all flagged correctly.

## Gate

validate_board.sh exits GREEN on live board (all 47 non-parked tickets carry valid
difficulty). board-correctness.test.sh: 7/7 pass.

## Scope

Change is in `fleet/validate_board.sh` (charon-private, commit 3e5f834) and board/*.md
ticket backfill (commit 8cd9851). No product code touched. Disjoint from all product work
(rig-only).
