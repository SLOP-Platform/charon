repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
priority: 1
branch: feat/repo-field-required
depends_on: VERIFY-MERGED-REPO-AWARE
real-dep: VERIFY-MERGED-REPO-AWARE — this ticket makes `repo:` MANDATORY; that ticket makes the
  consumers actually HONOUR it. Requiring a field nothing reads correctly would ship a validator rule
  that gives false assurance: tickets would all carry `repo:` while done.sh still resolved the wrong
  tree. Land the repo-awareness first, then require the field. Disjoint owns by design.
owns: fleet/validate_board.sh, fleet/tests/repo-field-required.test.sh, fleet/board/*.md
serial_justified: the rule and the backfill are ONE unit and cannot be split. The new validate_board
  rule makes a missing `repo:` a HARD RED, so the moment it lands every one of the 120 un-backfilled
  tickets fails the board — a rule-first PR leaves the board RED and blocks all launching, and a
  backfill-first PR is unenforced and silently re-drifts. They must land together. The two "owned
  surfaces" are the validator plus a board-wide data migration, not two independent builds, and the
  fail-on-revert fixture tests exercise the rule and the backfilled shape as one invariant.
accept: |
  PROBLEM (measured 2026-07-18, re-measure before starting). 120 of 226 board tickets
  (board/ + board/archive/) carry NO `repo:` field. validate_board.sh:97-98 defaults an absent field
  to "charon" (the PRODUCT repo), and done.sh defaults the same way. So 120 tickets SILENTLY assert
  they live in the product repo, including rig tickets that do not.

  WHY IT MATTERS (a REAL failure, not a hypothetical): REPO-DECL-CENTRAL is a RIG ticket with no
  `repo:` field. It was done-marked with `merged:c44e7bda...`, a sha that does not exist in the rig
  repo at all and resolves in the PRODUCT repo as a DOCS-ONLY merge (#163,
  `docs/review-log/REPO-DECL-CENTRAL.md | 34 ++++`). Zero rig code shipped, the ticket counted done,
  and its worktree was eligible for removal. `verify_merged` GATES DESTRUCTIVE ACTIONS
  (retire-done.sh archives the ticket and deletes its worktree), so a wrong-repo default is a
  data-loss-adjacent defect, not a cosmetic one ([[investigate-and-backup-before-data-loss]]).

  DO.
    (a) validate_board.sh: a new rule requiring an EXPLICIT, KNOWN `repo:` on every ticket. Absent
        field -> RED (today: silently defaults). Unknown value -> RED (rule 0 already does this for
        present-but-unknown values; extend it to cover ABSENT). Reuse the existing REPO_ROOTS map —
        do NOT add a second copy of the repo map (that is REPO-MAP-CONVERGE's whole subject).
    (a2) CONSISTENCY (the recurring "session points work at the RIG" defect, operator-escalated
        2026-07-23): also RED when the declared `repo:` is INCONSISTENT with what the `owns:` paths
        imply — owns `src/charon/*` | `tests/*` | `docs/*` but `repo: charon-private`, or owns `fleet/*`
        but `repo: charon`. This is the exact mis-pointing that recurs when a session files a PRODUCT-code
        fix (e.g. grades.py) as a RIG ticket: the field is present + known (so rule (a) passes) yet points
        at the wrong tree, so the droid checks out the wrong repo and the fix never lands. Derive the
        implied repo from owns exactly as the backfill in (b) does; a ticket whose owns span BOTH repos is
        the same "genuine finding — surface, don't guess" case. Fail-on-revert fixture: a ticket with
        `repo: charon-private` + owns `src/charon/x.py` -> REJECTED; flip repo to `charon` -> GREEN.
    (a3) TIER validation (added 2026-07-23 — a stray `tier: standard` slipped through silently because
        validate_board checks work_class but NOT tier): RED when `tier:` is not in the canonical set
        (economy/strong/frontier + the rank aliases from `charon tier ranks`: low/med/high, haiku/sonnet/
        opus). Same shape as the work_class rule. Fixture: `tier: standard` -> REJECTED; `tier: strong` ->
        GREEN. Reuse `charon tier ranks` as the source of truth — do NOT hardcode a second tier list.
    (b) BACKFILL the 120. Mechanical, but NOT blind: determine each ticket's real repo from its
        `owns:` paths (absolute /home/stack/charon-private/... or fleet/* -> charon-private;
        src/charon/*, tests/* -> charon), not from a guess. Tickets whose owns span both repos are a
        genuine finding — surface them, do not silently pick one.
    (c) Keep the default-to-"charon" behaviour REMOVED, not merely warned about. A warning is what
        the current state effectively is.

  FAIL-ON-REVERT (fleet/tests/repo-field-required.test.sh — REQUIRED):
    (1) MISSING repo: feed validate_board a FIXTURE board containing a ticket with NO `repo:` field
        -> validate_board REJECTS it (non-zero, named RED). Add the field -> GREEN. Revert the rule
        -> the fixture stops failing -> the test itself fails.
    (2) UNKNOWN repo: a fixture ticket with `repo: not-a-real-repo` -> REJECTED.
    Test the VALIDATOR against fixtures. Never assert against the live board's current contents — a
    live-content assertion goes green the moment the backfill lands and proves nothing about the
    rule, which is the durable half of this ticket.

  GREEN-IS-NOT-PROOF: validate_board is GREEN right now with all 120 tickets missing the field —
  that is precisely the defect. A green board is therefore zero evidence for this ticket. Reviewer:
  confirm the two fixture tests above exist and that the backfill was derived from `owns:` paths
  rather than bulk-set to one value.
scope: |
  Make `repo:` a required, explicit, validated field on every board ticket, and backfill the 120
  tickets that lack it. Removes the silent PRODUCT-repo default that let a rig ticket be
  merge-proven by a product commit while gating destructive actions.
  [[always-fix-catalog-mismatches]] [[config-ssot-git-manifest]] [[security-is-a-ratchet-gate]]
  [[gates-must-actually-run]] [[never-ignore-preexisting-issues]]
ds: |
  ## Dependencies & sequence
  depends_on: VERIFY-MERGED-REPO-AWARE only (justified in real-dep: above — require the field only
    once the consumers honour it).
  single-writer: fleet/validate_board.sh has exactly one other declared owner, REPO-MAP-CONVERGE,
    which depends_on this ticket — so the two are dep-sequenced and the file has one writer at a
    time. Touch it ONCE ([[optimize-execution-wallclock-tokens]]).
  checked-not-a-dep: PROJECT-MEMBERSHIP-GATE and CREATION-GATE-DECOMPOSE-WIRE MENTION
    validate_board.sh in their accept prose but do NOT declare it in `owns:` (board-verified
    2026-07-18) — so they are merge-order at most, not real prereqs, and are deliberately NOT
    depended on ([[disjoint-owns-not-no-dependency]] applies in reverse: a prose mention is not an
    ownership claim). If either later claims the file, re-sequence then.
  owns-note: `fleet/board/*.md` is declared as a GLOB because the backfill edits ~120 ticket files.
    validate_board reports glob owns as INFO (cannot partition) — the manager must confirm by hand
    that no other tab is editing board tickets during the backfill pass. Do the backfill as ONE
    commit, not drip-fed.
  boundary: RIG-ONLY ([[product-vs-build-rig-boundary]]). The board and its validator are rig
    artifacts; no product-repo file is edited.
  not-covered-by (checked, genuinely disjoint): REPO-MAP-CONVERGE owns the repo->path/slug MAP's
    duplicate copies (where the map lives); this ticket owns the TICKET FIELD's presence and
    validity (whether a ticket declares its repo at all). Different fact, different failure mode.
    SSOT-DRIFT-GATE composes per-fact SSOTs and does not own board-field presence.
  concurrency: blocked until the three deps land; then runs alone over validate_board.sh + the board
    backfill. Do NOT decompose per-ticket-file — a 120-file backfill split across tabs is exactly
    the multi-writer pattern being fixed.
  wave: rig board correction 2026-07-18.
  repo: charon-private (rig).
note: |
  Created 2026-07-18 during board maintenance, from the REPO-DECL-CENTRAL phantom-merge correction.
  Count 120/226 measured directly (`grep -L '^repo:' board/*.md board/archive/*.md`); live board
  alone is 6/54, so the bulk of the exposure is in archive/ — which still matters because
  verify_merged and reconcile-held-markers read archived tickets when resolving done markers.
  ADVERSARIAL REVIEW REQUIRED (trust/destructive-gate): this rule guards a check that gates worktree
  deletion.
