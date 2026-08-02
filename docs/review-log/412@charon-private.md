# Review: 412@charon-private
**PR:** test(fleet): fail-on-revert test for roadmap-html + fix end-session branch-guard regression
**URL:** https://github.com/Nnyan/charon-private/pull/412
**Date:** 2026-08-02T15:15:45Z
**Reviewer:** reviewer-tab-2540602
**Author:** stack

## Verdict
NEEDS-REVISION

## Findings
- **BYPASS EXPOSES SECURITY GUARD**: `END_SESSION_SKIP_BRANCH_GUARD` is an undocumented bypass for the branch-guard protection added in b193381. No enforcement prevents it from being set in production (`END_SESSION_SKIP_BRANCH_GUARD=1 end-session.sh` disables the protection in real runs), contradicting the PR's claim that it's "test-only". This creates a supply-chain regression of the b193381 safeguard.
- **CIRCULAR DEPENDENCY**: The branch-guard (b193381) was added to prevent wrong-branch commits. This PR makes tests pass by bypassing that guard—but the bypass mechanism is publicly available, not test-enforced. The protection is weakened in the same PR that claims to maintain it.
- **SILENT FAILURE ON HTML GENERATION**: The `|| true` on `roadmap-html.sh` call suppresses all errors. The checklist condition `[ -f "$roadmap_html_path" ]` will silently skip if the file isn't created, leaving no indication of failure.

## Fail-on-revert check
The bypass mechanism (END_SESSION_SKIP_BRANCH_GUARD) would be removed, re-breaking the test harness—but the real issue is that a bypass should not exist as an environment-variable toggle without test-only enforcement.

## Status
Pending Manager dispensation
