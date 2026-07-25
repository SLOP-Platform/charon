repo: charon-private
tier: strong
difficulty: 2
work_class: bugfix
priority: 2
branch: fix/bandit-preexisting-findings
depends_on:
owns: fleet/benchmark/lib/charon_cost.py, fleet/benchmark/selftest/run_isolation_selftest.py, fleet/benchmark/selftest/session_cost_selftest.py
work_class_note: |
  security-hygiene — 3 pre-existing MEDIUM bandit findings surfaced 2026-07-22 by a FULL-TREE bandit
  run (the newly-adopted BANDIT-ADOPT gate is diff-scoped, so it did NOT flag these; they are real and
  would fire the day bandit goes tree-scoped or these files are touched). NOT ignored — ticketed per
  [never-ignore-preexisting-issues].
accept: |
  Resolve each finding — FIX (preferred) or an inline `# nosec <TESTID>` with a one-line justification
  (never a blanket suppression):
    - fleet/benchmark/lib/charon_cost.py:189 (B310, urllib.urlopen): the URL is a fixed provider https
      endpoint — assert/validate the scheme is https before opening (or nosec B310 with the reason).
    - fleet/benchmark/selftest/session_cost_selftest.py:114 (B310, urllib.urlopen): same class.
    - fleet/benchmark/selftest/run_isolation_selftest.py:299 (B103, os.chmod 0o755): a script needs +x,
      but tighten to 0o750 if group/other-read is not required, or nosec B103 with the reason.
  VERIFY: `bash fleet/checks/bandit.sh` (TREE mode) reports 0 findings at/above MEDIUM across fleet/ + tools/
  (or every remaining finding carries a justified nosec). This is the pre-req for making the bandit gate
  tree-scoped later.
scope: |
  Clear the 3 pre-existing MEDIUM bandit findings the diff-scoped BANDIT-ADOPT gate does not catch, so the
  rig's own Python is clean at MEDIUM+ and bandit can eventually run tree-scoped. [[security-is-a-ratchet-gate]]
  [[never-ignore-preexisting-issues]]
ds: |
  ## Dependencies & sequence
  - depends_on: (none). DISJOINT owns from GRADER-REAL-SHELL-INJECTION-FIX (real.py) and
    GRADER-SECFIX-RECONCILE (grader-daemon.py/reds_replay.py/test_grader_daemon.py). No file overlap.
  - relationship: follow-on to BANDIT-ADOPT — that gate is intentionally diff-scoped (won't red on
    untouched code); this clears the pre-existing backlog so a future tree-scoped bandit is green.
