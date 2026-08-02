# Review: 391@charon-private
**PR:** eval(PR-AUTOMATION-EVAL): ADOPT-pr-agent-wrap — pr-agent vs review-pool.sh vs aider vs SaaS reviewers
**URL:** https://github.com/Nnyan/charon-private/pull/391
**Date:** 2026-08-02T04:32:15Z
**Reviewer:** reviewer-Tardis-3691034
**Author:** strong-2841117

## Verdict
NEEDS-REVISION

## Findings
- B4 overstates safety: pr-agent lacks "diff is untrusted" instruction and has no injection test. A malicious diff can steer findings (severity/content) that the wrapper's disposition logic misclassifies as benign. The approve-steering vector is renamed, not removed — the document's own sharp-test section admits LLM-semantic catches are not deterministic.
- ADOPT verdict premature: the AP-12 runtime trial (3 real PRs through gateway) is marked NOT RUN and deferred as the pre-wire gate, yet the verdict is final "ADOPT (wrap)" not "PROVISIONAL-ADOPT pending trial." Merging this invites wiring pr-agent without confirming gateway routing works.
- No supply-chain audit for `pip install pr-agent`: transitive dependencies unaudited despite documented credential-exposure history (v0.36.1 #2445). Ops burden rated "moderate" undersells risk.
- Documentation drift: the short-form summary delegates to the long-form file without pinning a revision hash — independent updates to the long-form silently invalidate the summary.

## Fail-on-revert check
Reverting discards the measured-state evidence (B1 inert on mirror, B3 not in CI, 17/17 production BOUNCEs) and the comparative tool evaluation that justify the direction.

## Status
Pending Manager dispensation
