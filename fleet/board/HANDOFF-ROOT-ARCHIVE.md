repo: charon-private
tier: economy
priority: 2
difficulty: 1
work_class: docs
branch: feat/handoff-root-archive
depends_on:
owns: HANDOFF.md, fleet/tests/handoff-root-staleness.test.sh
accept: |
  PROBLEM (a REAL incident, not a hypothetical). `/home/stack/charon-private/HANDOFF.md` (rig root) is
  months-stale and opens with the maximally-authoritative line:
    "You are the next Charon Manager. This is a complete, self-contained handoff."
  It is dated Jul 10 (mtime verified) and describes a dead GitLab/mvp-routing-era world. Real session
  state lives in fleet/state/ + SESSION-HANDOFF-*.md. fleet/STARTUP-FRICTION-LOG.md records this file
  ACTIVELY MISLEADING the 2026-07-16 post-crash restart and self-marks it "(OPEN: archive/date it)".
  A stale doc that asserts its own completeness is worse than no doc: it terminates the reader's search.

  DO (minutes of work — resist scope creep, this is deliberately tiny):
    (a) ARCHIVE/DATE it. Either move the content under a clearly dated archive heading or replace the
        file with a short POINTER that (i) states it is historical and dated 2026-07-10, (ii) names the
        CURRENT sources of truth (fleet/state/, the newest SESSION-HANDOFF-*.md, fleet/START-SESSION.md),
        and (iii) carries NO instructions a fresh manager could mistake for live procedure. Delete or
        neutralize the "complete, self-contained handoff" claim — that sentence is the actual defect.
    (b) DO NOT rewrite it into a new handoff, and DO NOT touch fleet/START-SESSION.md,
        fleet/MANAGER-OPERATING-RULES.md, fleet/handoff.sh, fleet/handoff-check.sh or fleet/preflight.sh
        — all five are OWNED by STARTUP-CONTEXT-DIET (in review). Root HANDOFF.md ONLY.
    (c) [[public-repo-no-personal-info]]: the rig is private but this pattern leaks. Whatever you retain
        must not carry tokens/IPs/hostnames/absolute /home paths. Scrub while you are in here.

  FAIL-ON-REVERT (fleet/tests/handoff-root-staleness.test.sh — REQUIRED, and it is the whole durable
  value of this ticket; the archive itself is a one-time edit that re-rots by default):
    (1) A root handoff-style doc must not claim live authority while stale. Assert HANDOFF.md does NOT
        contain the authority-claiming phrasing ("You are the next Charon Manager" / "complete,
        self-contained handoff") unless it also carries a date stamp within a freshness window. Restore
        the old undated authoritative text -> RED.
    (2) Assert the file names at least one CURRENT source of truth (fleet/state/ or SESSION-HANDOFF-*),
        so a future edit cannot re-create a dead-end doc. Strip the pointer -> RED.
    Drive the checker with FIXTURE content (a temp file), not by asserting the live HANDOFF.md's exact
    bytes — a byte-assertion is a tautology that passes by construction and goes red on any harmless
    wording change.

  GREEN-IS-NOT-PROOF (explicit): the entire rig suite is green RIGHT NOW with this file actively
  misleading a real session — nothing reads root HANDOFF.md, so no test can go red on it, today or after
  it re-rots. Green is therefore zero evidence here. The staleness checker is the only mechanism that
  makes this fix durable rather than a doc edit that decays in a fortnight.
scope: |
  Archive/date the stale rig-root HANDOFF.md (Jul 10, GitLab/mvp-routing era) that claims to be a
  "complete, self-contained handoff" and misled this session's crash recovery, per the OPEN item
  self-marked in fleet/STARTUP-FRICTION-LOG.md. Replace with a dated pointer to the real sources of
  truth, and add a staleness checker so the class cannot silently recur. Minutes of work; prevents a
  recurring wrong-turn at crash recovery.
  [[confirm-dont-trust-documentation]] [[mechanized-handoff-gate]] [[public-repo-no-personal-info]]
ds: |
  ## Dependencies & sequence
  depends_on: (none) — root HANDOFF.md is UNOWNED by any live ticket (board-verified 2026-07-16:
    `grep -l '^owns:.*HANDOFF\.md' fleet/board/*.md` -> no owner).
  not-covered-by (checked, genuinely disjoint): STARTUP-CONTEXT-DIET (in review) owns
    fleet/MANAGER-OPERATING-RULES.md, fleet/handoff.sh, fleet/handoff-check.sh, fleet/preflight.sh,
    fleet/START-SESSION.md — the STARTUP surface, NOT the rig-root HANDOFF.md. Disjoint by file. No
    build dep either direction: this ticket must NOT edit any of those five files.
  concurrency: RUNS NOW, zero-dep. Owns one root doc + one NEW test -> parallel-safe with every live
    ticket, no shared writer.
  wave: economy refill 2026-07-16. Do FIRST — smallest zero-dep economy item feeding an idle economy tab
    (difficulty 1, minutes).
  repo: charon-private (rig).
note: Created 2026-07-16 from fleet/session-notes/2026-07-16-evidence/audit-harvest.md item 7 +
  fleet/STARTUP-FRICTION-LOG.md's own OPEN marker. Zero-dep, economy, READY NOW. Smallest item on the
  board — good first claim for an idle economy tab.
</content>
</invoke>
