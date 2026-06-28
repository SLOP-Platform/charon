# ATC — Adversarial Technical/Code review (audit) of ALL committed work

> Interpretation note: "ATC" = a comprehensive ADVERSARIAL audit of everything this body of work
> committed. If you meant something more specific, adjust the scope below — the structure
> (read-only adversarial review → findings doc → fix tickets, run LAST) holds regardless.

## Dependencies & sequence
**depends_on: ADR-0015, OBS-CAPTURE, OBS-UI, CLIENT-CONNECT-GUI, ORCH-ROUTE, WCI, WCI-FOLLOWON
— Wave 4, runs LAST.** It owns NO source files (a review produces a findings doc + fix tickets, it
does not edit product code), so it cannot collide; the dependencies exist purely so it runs AFTER
the work it audits has merged. A fresh Charon will hold it until all listed tickets are DONE, then
claim it — auditing the integrated end state, not a moving target.

## Why
This session shipped a large, interlocking cluster (the autonomous-ticket-runner: gateway auth,
agent bearings, land+review, client-connect, observability — plus the backlog and orchestrator
follow-ons). Each PR was gated individually; nothing has adversarially reviewed the WHOLE,
integrated result. This ticket does.

## What to do (read-only adversarial audit → findings → fix tickets)
Adversarially review the full body of merged work (the #68–#75 cluster + every dependency ticket
above). Try to REFUTE that it is correct/secure/coherent — don't bless it. Cover at least:
1. **Security** — the credential paths: `CHARON_GATEWAY_TOKEN` passthrough (WGW), the per-run proxy
   token (ORCH-ROUTE), the `.gitleaks.toml` allowlist (does it let any REAL secret through?), the
   `charon connect` token-handling (never logged?), and the fence (`scrubbed_env`) still scrubbing
   everything except the one intended credential.
2. **Correctness / integration** — do the cluster pieces COMPOSE? e.g. bearings (body+accept)
   actually reach the agent in BOTH work-path runners; `--open-pr` never auto-merges and is
   fail-closed; the reviewer is the real `GatewayReviewer`; observability progress never pollutes
   stdout JSON; WCI is opt-in/advisory and invisible on a gateway-only install.
3. **Agent/provider-agnosticism & product-cleanliness** — no Claude/opencode hardcoding leaked into
   the engine/gateway path; no SLOP/fleet/rig leak into `src/`; privileged core still stdlib-only.
4. **Regression surface** — anything the cluster could have broken in `charon run`, the gateway hot
   path, or single-task fresh installs.

## Output
A findings report at `docs/review-log/ATC-AUDIT.md` (or rig doc) listing each finding with
severity + file:line + a refute/confirm verdict; for each CONFIRMED issue, stage a fix ticket
(board + prompt) rather than editing code in this ticket. If clean, say so explicitly with the
evidence checked.

## CONSTRAINTS
Read-only audit: owns NO product source. May spawn read-only sub-reviewers (allowed); mutates/merges
nothing. Stdlib assumptions only. Review note/output → `docs/review-log/ATC-AUDIT.md`. No PR to
master from this ticket (it produces findings + fix tickets). BACKLOG (parked) — Wave 4.
