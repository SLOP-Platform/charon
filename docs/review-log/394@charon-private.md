# Review: 394@charon-private
**PR:** triage(RESCUE-TRIAGE-RIG): dispose the 9 un-PR'd rig branches — open PR #392, close 7 dead, hold 1
**URL:** https://github.com/Nnyan/charon-private/pull/394
**Date:** 2026-08-02T05:14:25Z
**Reviewer:** reviewer-tab-2793510
**Author:** strong-3187916

## Verdict
NEEDS-REVISION

## Findings
- Contradictory evidence for `chore/retire-wire-graphify`: the log claims the file is "byte-identical to master (diff: no output)" while also claiming the board file "no longer exists on master at all." A file cannot be byte-identical to a copy that does not exist; the strongest-evidence row is internally self-refuting, so the branch deletion rests on muddled proof.
- HELD verdict for `fix/broker-bare-tier-legs` is inconsistent with the ticket's own taxonomy: the row argues master has moved OPPOSITE the branch premise ("ids now provider-qualified"), which is the identical criterion used to CLOSE-DEAD the other seven — yet this branch is preserved as "held." The blocker hold only justifies keeping a branch that becomes correct after the blocker lands; the author states it never will. This is a zombie branch, not a hold.
- The disposal of the 4 `submit-auto` notes in `salvage/session-notes-20260719` uses class-level guilt-by-category ("a class master deliberately sweeps as dead") instead of per-file content proof — weaker than the byte-identical standard the ticket itself demands, applied to a branch explicitly named *salvage*. Content may have been discarded on category, not evidence.
- Destructive deletes (7 branches) executed out-of-band prior to this log; the diff contains only self-authored claims with no verifiable diffs/transcripts, and every "on master @ 67c7eaa" claim silently rots if master drifts before merge. Merging ratifies irreversible actions on unverifiable testimony.

## Fail-on-revert check
Reverting the merge removes the only accountability record for the seven out-of-band branch deletions, yet cannot restore them — the one-way door (deleted branches, post-hoc unverifiable evidence, and the zombie HELD branch) is entirely missed.

## Status
Pending Manager dispensation
