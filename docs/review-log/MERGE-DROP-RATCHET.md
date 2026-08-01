# MERGE-DROP-RATCHET review note

| tool | scope | date | verdict | alignment | reason | evidence-link | supersedes |
|---|---|---|---|---|---|---|---|
| Danger (danger-js/danger-ruby) | PR diff policy for board-file lifecycle | 2026-07-31 | REJECT — fallback check | aligned | Danger can inspect PR diffs, but adds a Node/Ruby bot and does not provide the merge-result tree comparison plus archive/declared-retire classification without bespoke glue; the shell check is the smaller, directly testable enforcement point. | fleet/checks/board-file-ratchet.sh | existing Danger row |
| Conftest/OPA | policy over structured merge-result input | 2026-07-31 | REJECT — fallback check | aligned | Conftest evaluates structured input but would require generating a merge-result file-set document and maintaining Rego plus a caller; it does not natively compare both Git parents or classify archive moves. The shell check directly owns the Git-specific invariant with lower exit cost. | fleet/checks/board-file-ratchet.sh | — |
