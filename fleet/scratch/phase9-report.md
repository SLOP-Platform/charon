# Phase 9 report — public-clean waiver hardening + durable-bridge Phase-2 brief

**Session note:** during this session HEAD advanced (concurrent commit) to `1c54ef4`
("security(gate): wire public-clean guard into gate + pre-commit; populate exceptions")
— that commit is the pre-existing base (line-number-keyed exceptions, guard wired into
`gate_runner.py` CHECKS, already green). Part A below is layered on top of it,
**uncommitted**, per instructions (manager reviews + commits; no push).

---

## PART A — `/home/stack/code/charon` (public repo)

**Problem.** `tools/.public-clean-exceptions.json` keyed waivers by `{file: [line_numbers]}`.
Any future insertion/deletion above an exempted line shifts its content down/up without
moving the recorded line number — silently un-masking an already-reviewed benign line
(new false-positive) or, worse, silently masking whatever new content slides onto that
now-stale line number (a real leak going undetected).

**Fix implemented — option (a), content-based waivers** (`tools/check_public_clean.py`):
- `_load_exceptions()` / `check_file()` now key exemptions by the **exact line content**
  (verbatim raw line text), not line number. A line is skipped only if its full text is
  present in that file's exempted set. If the exempted content is edited or moves, the
  exemption simply stops matching — the line is re-evaluated normally against the
  patterns (fail-safe, not fail-silent). Insertions/deletions elsewhere in the file no
  longer affect any waiver.
- Regenerated `tools/.public-clean-exceptions.json` (script-migrated from the old
  line-number data: read each old `file:line`, replace the integer with that line's
  literal text, dedupe identical lines within a file via `set()`). Net effect: same
  *files* covered, same *legitimate* hits waived (4-lom label, pinned Action SHAs, doc
  dev-meta, test fixtures, `check_public_clean.py`'s own pattern-source lines) — nothing
  broadened, nothing narrowed. Duplicate identical lines (e.g. the same
  `# Maintainer sets CI_RUNNER=...` comment repeated across jobs in one workflow file)
  now collapse to a single entry, since content-matching naturally covers every
  occurrence of that exact text.
- **New self-reference issue found and fixed:** storing raw content verbatim means the
  exceptions JSON itself now *contains* the previously-elsewhere-flagged substrings
  (`4-lom`, `charon-private`, pinned SHAs, etc.), which made the guard flag its own
  ledger file. Fixed by excluding `tools/.public-clean-exceptions.json` from the
  tracked-files scan in `main()` (with an inline comment explaining why — same rationale
  as excluding a detect-secrets baseline file from its own scan; none of the restated
  text is a *new* disclosure, it's already public at its original location).
- **Added the floor test too (option c), as defense in depth:**
  `test_shipped_exceptions_match_tracked_file_content` in `tests/test_public_clean.py`
  loads the real shipped exceptions file and asserts every entry's content is still
  verbatim-present in its target file — names the specific stale file+snippet if not.
  Also added `test_exception_content_no_longer_present_stops_suppressing` (unit-level
  proof that drifted content re-exposes the line) and updated the two pre-existing
  exception tests (`test_exception_config_suppresses_violation`,
  `test_exception_config_only_suppresses_specific_lines`) from the old
  `{rel: {1}}` (line-number) signature to the new `{rel: {"<content>"}}` signature.
- One new test-fixture line (`tests/test_public_clean.py:157`, the updated
  `check_file(f, {rel: {'{"rig": "charon-private"}'}})` call) needed its own waiver —
  used the existing inline `# public-clean: allow` mechanism rather than adding a new
  exceptions-file entry, since it's a Python line that can host a same-line comment.
- Updated `docs/review-log/PUBLIC-CLEAN-LINT.md`'s description of the exceptions config
  to match (content-keyed, not line-number-keyed; mentions the new regression test).

**Files changed:**
- `tools/check_public_clean.py` (+25/-4)
- `tools/.public-clean-exceptions.json` (+143/-26 — regenerated, content-based)
- `tests/test_public_clean.py` (+56/-3 — updated 2 tests, added 3 new tests)
- `docs/review-log/PUBLIC-CLEAN-LINT.md` (+7/-1 — doc accuracy)

**Verification:**
```
$ cd /home/stack/code/charon && PYTHONPATH=src python3 -m charon.cli gate
CHARON GATE — running all validation checks...
  [ruff] OK
  [mypy] OK
  [SLOP-boundary] OK
  [version] OK
  [gate-registry] OK
  [public-clean] OK
CHARON-GATE: all checks passed

$ PYTHONPATH=src python3 -m pytest -q tests/test_public_clean.py
.........................                                                [100%]
25 passed in 0.10s

$ PYTHONPATH=src python3 -m pytest -q          # full suite, sanity check
...
1246 passed in 88.71s
```

**Proposed commit message** (manager's call whether/when to commit):
```
security(gate): key public-clean waivers by line content, not line number

.public-clean-exceptions.json waivers were keyed by {file: [line_numbers]} — a
future insertion/deletion anywhere above an exempted line shifts its content
without moving the recorded number, silently un-masking a reviewed-benign line
or masking whatever new content lands on that now-stale line number.

Switch to content-based waivers: exemptions are now keyed by exact line text.
If the exempted content moves or changes, the waiver simply stops matching and
the line is re-evaluated normally (fail-safe, not fail-silent). Migrated the
existing exceptions 1:1 (same files, same legitimate hits, nothing broadened
or narrowed); excluded the exceptions ledger itself from the guard's own scan
(it necessarily restates already-elsewhere-exempted text, which is not a new
disclosure). Added a regression test asserting every shipped exception is
still verbatim-present (drift guard) plus a unit test proving stale content
stops being suppressed.

Gate: 6/6 green. pytest: 1246 passed (25 in test_public_clean.py).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## PART B — durable-bridge Phase-2 brief

Written: `/home/stack/charon-private/fleet/DURABLE-BRIDGE-PHASE-2-BRIEF.md`

Captures the 5 deferred items pulled from `DURABLE-BRIDGE-REVIEW-v3.md` and
`scratch/bridge-phase01-review.md`, each with problem / concrete approach / files /
acceptance test, grounded against the live `daemon.py` (851 lines) and cross-referenced
to design-v3 section numbers:

1. **NB3 — renewer immortalizing a hard-crashed session.** Same-host `os.kill(pid, 0)`
   liveness check before each renewal (session PID written by `SessionStart` into its
   active-sessions line), plus a bounded max-renewals-without-liveness-proof fallback.
2. **120s bounded auto-ack — message-loss policy decision.** Recommended: keep 120s,
   add stderr logging on auto-ack (closes the "silent" part of silent loss) + a doc note;
   optionally make the window configurable per-message-type.
3. **Destructive→non-destructive nudge-read cutover note.** Docs-only: one paragraph in
   the daemon-restart runbook about the one-time 120s legacy-reread window after cutover.
4. **Wire `idempotency.py` into its actual consumer.** Confirmed unwired-by-design (its
   own docstring says so; consumer `bridge-watch.sh` doesn't exist yet). Brief specifies
   building the watcher first, then wrapping its wake-handling dispatch with
   `claim()`/`ack()` per design-v3 §8-AMEND's exact sequence.
5. **Phase-3 leftovers.** `status` RPC (reuse `_row_to_dict`'s NB1 allowlist — do not
   hand-roll a second serialization path), `bridge-status` CLI, kill-switch (file
   sentinel + `bridge-killswitch.sh`, flags the pre-existing `unregister`
   read-vs-write-labeling ambiguity for the implementer to resolve explicitly), and the
   `AGENTS.md` G3 heartbeat-section rewrite (Repo B, public — noted the two near-duplicate
   sections at lines 195 and 307 for the builder to reconcile or confirm intentional).

Suggested build order and per-item acceptance tests are in the brief; Repo-A items are
scoped to the non-git `~/.config/opencode/session-bridge/` build-rig dir, item 5d is the
only Repo-B (public, git-tracked) piece.
