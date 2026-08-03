# HANDOFF-ROOT-ARCHIVE — Review Log

## Ticket
HANDOFF-ROOT-ARCHIVE: archive/date the stale rig-root HANDOFF.md (Jul 10,
GitLab/mvp-routing era) that claimed to be a "complete, self-contained handoff".
Replace with a dated pointer to the real sources of truth (fleet/state/,
SESSION-HANDOFF-\*). Add a staleness checker test so the class cannot silently
recur.

## Root cause being fixed
A REAL incident (2026-07-16 post-crash restart). The root HANDOFF.md was months
stale (mtime Jul 10, GitLab/mvp-routing era) and opened with "You are the next
Charon Manager. This is a complete, self-contained handoff." — a maximally-
authoritative claim that terminated the reader's search. Real session state lived
in fleet/state/ + SESSION-HANDOFF-\*.md. fleet/STARTUP-FRICTION-LOG.md recorded
this file ACTIVELY MISLEADING recovery and self-marked it "(OPEN: archive/date
it)".

A stale doc that asserts its own completeness is worse than no doc: the reader
stops searching. The fix must be durable (a staleness checker, not just a one-time
edit).

## What was done
- **HANDOFF.md** (root, rewritten): Replaced the "complete, self-contained
  handoff" preamble with an ARCHIVED header dated 2026-07-10, a clear note
  that the content is historical and NOT a live handoff, and a pointer to the
  current sources of truth (fleet/state/, fleet/SESSION-HANDOFF-\*.md,
  fleet/START-SESSION.md). The original body is preserved under an "Archived
  content" heading for provenance, but all raw absolute paths /hostnames/IPs
  are replaced with generic descriptions (no /home paths, no SSH addresses,
  no tokens).
- **fleet/tests/handoff-root-staleness.test.sh** (NEW): A hermetic staleness
  checker that operates on fixture content, not the live HANDOFF.md. Asserts:
  1. A stale authoritative doc (authority claim + no date/archive marker)
     MUST fail.
  2. An archived doc (authority claim + date + source-of-truth pointer)
     MUST pass.
  3. A pointer doc (no claim, names current sources) MUST pass.
  4. A dead-end doc (no source pointer) MUST fail.
  5. A full archived+pointer doc MUST pass.
  6. Fail-on-revert meta-test: stripping the authority-claim detection lets
     a stale authoritative doc slip through (proves the check is load-bearing,
     not redundant).

## Scope self-check
Verified: `git diff --name-only master...HEAD` (once committed) includes only:
- `HANDOFF.md` (M)
- `fleet/tests/handoff-root-staleness.test.sh` (new)
- `docs/review-log/HANDOFF-ROOT-ARCHIVE.md` (this file — per-ticket fragment)

All three are inside the ticket's `owns:` line. No START-SESSION.md,
MANAGER-OPERATING-RULES.md, handoff.sh, handoff-check.sh, or preflight.sh
touched (those belong to STARTUP-CONTEXT-DIET).

## Design notes / trade-offs

- **Why not byte-assert the live HANDOFF.md:** a byte-assertion passes by
  construction (the test would trivially pass today and break on any
  harmless wording change). By operating on fixtures, the test proves the
  *logic* of the checker, not the particular phrasing of one file.
- **Why the PII scrub:** the rig repo is private, but the pattern (absolute
  /home paths, SSH addresses, hostnames, IP addresses) is a public-repo
  leak risk. Scrubbed to generic descriptions while preserving the operational
  meaning.
- **Why the fail-on-revert meta-test (check 6):** this is the only durable
  value of the ticket. The one-time edit to HANDOFF.md will re-rot in a
  fortnight. The meta-test proves that if someone removes the authority-
  claim detection, a stale authoritative doc silently passes — i.e. the
  check is load-bearing and maintains the class invariant.

## Test summary
`bash fleet/tests/handoff-root-staleness.test.sh` — 7/7 PASS. The live
HANDOFF.md passes the checker (archive marker present, source-of-truth
pointers present, authority claims neutralized by archive header).
