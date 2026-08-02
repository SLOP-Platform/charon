# Review: 371@charon-private
**PR:** feat: adopt-first spike of work-loop brokers for claim/dispatch (WLS-SPIKE)
**URL:** https://github.com/Nnyan/charon-private/pull/371
**Date:** 2026-08-02T05:15:11Z
**Reviewer:** reviewer-tab-2800517
**Author:** Nnyan

## Verdict
BOUNCE

## Findings
- **Judgment fragment self-contradiction (severity: HIGH):** `fleet/state/judgment/wls-spike-trial-WLS-SPIKE.md` states "Faktory is already adopted" in one field but `BRIEF-ERRORS` documents that claim.sh has zero Faktory references and adoption was never wired. The spike cannot simultaneously be "already adopted" and "never wired." Either the verdict (§1.6, §12) is overstated or the brief-errors is understating a blocker.
- **`.gitignore` blanket glob for runtime output directory (severity: MEDIUM):** `fleet/state/judgment/*` tracks all files in a launcher-produced directory without filter. Generated artifacts, corrupted outputs, or debug dumps placed there by the launcher will be auto-committed by any subsequent PR touching `.gitignore`. Should enumerate specific file types or require explicit per-file un-ignore entries.
- **No wiring in this PR (severity: MEDIUM):** The spike recommends ADOPT + WIRE IT but defers the actual wiring to a separate ticket. The PR creates records about an evaluation but delivers zero code change to the claim loop. The brief-errors field implies this was known — the correct action is to either wire Faktory in this PR or close the spike as incomplete pending a wiring ticket.

## Fail-on-revert check
The judgment fragment's `BRIEF-ERRORS` note documents that claim.sh has zero Faktory references — this finding would be lost on revert, and the ADOPT verdict would become unsubstantiated.

## Status
Pending Manager dispensation
