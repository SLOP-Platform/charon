# Review: 413@charon-private
**PR:** feat: archive stale rig-root HANDOFF.md with dated pointer + staleness checker
**URL:** https://github.com/Nnyan/charon-private/pull/413
**Date:** 2026-08-02T15:11:55Z
**Reviewer:** reviewer-tab-2540602
**Author:** sim

## Verdict
NEEDS-REVISION

## Findings
- The review log (`docs/review-log/HANDOFF-ROOT-ARCHIVE.md`) overstates what was delivered: it says "Add a staleness checker test so the class cannot silently recur," but the test is fixture-based regression testing only — it does not run as a recurring CI gate, cron job, pre-commit hook, or pytest entry point against the live HANDOFF.md. A recurring automated check (the natural reading of "staleness checker") is not implemented.
- The archive-marker and date-stamp checks in `check_handoff()` are slightly misaligned: the archive-marker check accepts `"This document is historical"` but the date-stamp check accepts `"Archived content"` as a fallback string — a doc could pass one but not the other. These should be unified.
- The `fleet/state/` pointer check uses substring match (`grep -qE "fleet/state/"`), so `fleet/state-foo/` would spuriously match. Low risk given the content, but imprecise.
- The `claim_phrase` regex construction produces leading empty alternations (e.g., `|You are the next Charon Manager`), which work in GNU grep but are fragile.

## Fail-on-revert check
The meta-test proves that removing authority-claim detection causes a stale authoritative doc to pass the checker, confirming the detection logic is load-bearing. A revert would re-expose the archived HANDOFF.md with its authority-claim intact without archive markers, which the test would correctly catch — but only if run manually.

## Status
Pending Manager dispensation
