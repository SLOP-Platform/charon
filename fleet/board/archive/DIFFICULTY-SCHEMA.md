repo: charon-private
tier: economy
difficulty: 1
work_class: ci-infra
branch: feat/difficulty-schema
depends_on:
owns: /home/stack/charon-private/fleet/validate_board.sh, /home/stack/charon-private/fleet/board/
accept: |
  Backfill DONE (157 tickets auto-seeded difficulty from tier, 2026-07-10). This ticket adds the
  ENFORCEMENT: validate_board.sh flags any ticket missing a `difficulty:` (1-5) line, and the ticket
  template carries it. Fail-on-revert: create a ticket without difficulty -> validate_board.sh non-zero.
scope: D1 hybrid (GATEWAY-PROGRAM §1.4) — capture difficulty DATA now, ladder MECHANISM later.
ds: Now (rig-only). Disjoint from all product work.
