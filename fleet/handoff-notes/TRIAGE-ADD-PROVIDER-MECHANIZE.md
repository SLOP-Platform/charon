# Triage: ADD-PROVIDER-MECHANIZE-COMPLETE (d7e03ab)

Disposition: **HAND OFF**

Evidence: The swept WIP is coherent — all 4 files form a single complete change that passes
25/25 fail-on-revert tests, but it overlaps NIM-PROVIDER-CLEANUP's items (a) and (b) 100%.

## Overlap with NIM-PROVIDER-CLEANUP (CRITICAL)
- (a) **false FAILED report** — FIXED. Step 4 now passes `--base-url` explicitly to `providers test`.
- (b) **key echo leak** — FIXED. `read -r` -> `read -rs`, comment flipped from "visible echo is intentional" to "secrets ratchet".
  Key never reaches stdout/stderr. NIM has NOTHING left to fix on its highest-value item.
- (c) **NIM rate limits in free-tier catalog** — UNTOUCHED. Review-log explicitly flags it as follow-up.
  `--free-tier` flag is wired in both scripts but no NIM catalog data exists.

## Ticket requirement gap analysis
| Req | Status |
|-----|--------|
| 1. Real costs via pricing-refresh | DONE: step 7 seeds pricing via CatalogRefresher |
| 2. funding_class auto-set | DONE: `--funding-class` required, passed through config API |
| 3. Routable (not just visible) | DONE: step 8 live chat-completions probe |
| 3b. Rate-limits in free_tier_catalog | NOT DONE: mechanism exists (`--free-tier`), no data |
| 4a. Bug: false FAILED | DONE |
| 4b. Bug: key echo | DONE |

## Abandonment signatures: none
No functions defined-but-unused, no half-updated call sites, no TODOs, no absent tests.
The diff is self-contained, tests are declarative fail-on-revert, and the review-log honestly
reports the one gap (free-tier catalog) rather than hiding it.

## Recommendation
Fold d7e03ab's hunks into NIM-PROVIDER-CLEANUP: entire add-provider.sh diff, entire
add-provider-interactive.sh diff, entire test diff (and drop the review-log file).
NIM then ONLY needs to add NIM to the free-tier catalog. This saves NIM from duplicating
the key-echo and false-FAILED fixes that are already done here.

To unblock NIM today: retire ADD-PROVIDER-MECHANIZE-COMPLETE as a ticket (its work is complete
except the catalog entry), merge d7e03ab's hunks into NIM's branch, and reduce NIM's scope to
item (c) only.
