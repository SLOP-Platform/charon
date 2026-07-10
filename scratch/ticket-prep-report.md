# Ticket-prep report — 4-fix wave (2026-07-09)

Board-management sub-session. Product source untouched; no droids launched; no product commits.
Follows `scratch/fix-wave-plan.md` (plan of record).

## 1. Reconciliation (the 3 flagged overlaps)

| Overlap | Action taken | Result |
|---|---|---|
| `CLINE-UNWRAP-SHIM.md.parked` | Annotated SUPERSEDED (by RESPONSE-ADAPTER-UNIVERSAL, per ADR) and moved to `fleet/archive/CLINE-UNWRAP-SHIM.md.superseded`; removed from `board/`. Not activated. | Resolved — no longer on the board. |
| `DTC-8-TEST-PATTERNS` owns-collision on `check_test_patterns.py`+`test_check_test_patterns.py` | No action needed: DTC-8 is already DONE (`state/done/DTC-8-TEST-PATTERNS` marker, dated Jul 1). TEST-HARDEN-CONTRACT is now the sole LIVE owner → validate reports these as done/live hand-offs (INFO, not RED). | Resolved (already done). |
| `TEST-EXERCISES-CHANGE-GUARD.md.parked` | Left parked as-is. Confirmed owns = `.git/hooks/pre-push, scripts/gate-hook.sh, .github/workflows/ci.yml` — disjoint from Fix 3's owns; parked files aren't scanned anyway. | No collision; left parked. |

## 2. Briefs written (prompt files)
- `/home/stack/charon-private/scratch/briefs/BILLING-EST-COST-FIX.md`
- `/home/stack/charon-private/scratch/briefs/NORMALIZE-CASE-QUANT-FIX.md`
- `/home/stack/charon-private/scratch/briefs/TEST-HARDEN-CONTRACT.md`
- `/home/stack/charon-private/scratch/briefs/RESPONSE-ADAPTER-UNIVERSAL.md`

Each carries: scope, files OWNED, exact file:line changes, acceptance criteria incl. the named
FAIL-ON-REVERT test (client-observable), the model, a `## Dependencies & sequence` section
(satisfies validate_board.sh D&S rule), the full-CI merge gate (ruff+mypy+`charon.cli gate`, not
pytest-alone), and a LAST STEP commit+report-SHA with "do NOT push/merge" on its own line.

## 3. Tickets created (board/*.md, all LIVE)

| Ticket | tier | work_class | depends_on | owns (key) |
|---|---|---|---|---|
| `BILLING-EST-COST-FIX` | frontier | money-path | (none) | forwarder.py, test_forwarder_billing.py |
| `NORMALIZE-CASE-QUANT-FIX` | frontier | money-path | (none) | proxy.py, test_normalize_model_id.py, check_catalog_case_quant.py |
| `TEST-HARDEN-CONTRACT` | strong | tests | (none) | conftest.py, test_provider_response_contract.py, check_test_patterns.py, test_check_test_patterns.py |
| `RESPONSE-ADAPTER-UNIVERSAL` | frontier | bugfix | `BILLING-EST-COST-FIX` | response_adapters.py, providers.py, gateway.py, proxy_server.py, forwarder.py, test_response_adapters.py, test_proxy_server.py |

RESPONSE-ADAPTER-UNIVERSAL carries a `real-dep:` line justifying the forwarder.py hand-off. It is
left LIVE (not parked): `claim.sh` gates it on `state/done/BILLING-EST-COST-FIX`, so the frontier
pool auto-claims it the instant Fix 1 is merged + `done.sh`'d — no manual un-park needed.

## 4. Validation

- `fleet/validate_board.sh`: my 4 tickets are STRUCTURALLY CLEAN —
  - `forwarder.py` <- BILLING-EST-COST-FIX, RESPONSE-ADAPTER-UNIVERSAL → "dep-sequenced/historical, ok" (the depends_on edge legalizes the shared file).
  - `proxy.py`, `gateway.py`, `providers.py`, `proxy_server.py`, `conftest.py`,
    `check_test_patterns.py`, `test_check_test_patterns.py`, `test_proxy_server.py` all report as
    legal INFO hand-offs (done/live or dep-sequenced). ZERO owns-collision RED, ZERO WCI
    false-blocking-dep RED for this batch. The 3 Wave-1 tickets share NO file (max concurrency 3).
- `fleet/wci-contention.sh 4`: the DECOMPOSE-CANDIDATE god-files (proxy_server.py ×26, etc.)
  count historical+parked owners; among the LIVE Wave-1 batch there is no shared file, matching
  the wave-plan. Pre-existing refactor debt, not a launch blocker for this batch.

### Pre-existing RED (NOT introduced here — flagged for the manager)
`validate_board.sh` exits RED on 6 **orphan-markers**, all pre-dating this session:
`state/done/{SR-13, PROXY-SERVER-DECOMPOSE, BENCH-PROVISIONAL-SCORING, SR-6, BENCH-AGGREGATE-N,
BENCH-REGROUND-LIVE}`. Each is a ticket that was completed (done marker) then re-parked
(`board/<ID>.md.parked`), so the marker matches no live `*.md`. Confirmed via `git status` these
are not in my diff. They do NOT affect `claim.sh` (which scans `board/*.md` independently) so they
do NOT block launching the 4 new tickets — but they keep the global gate RED.
Remediation (manager decision, 1 line each): either drop the stale done markers
(`rm fleet/state/done/<ID>`) if the work should re-run, or rename the parked file back to `*.md`
if the done work should show as historical. Not fixed here because it changes done-state semantics
for unrelated tickets.

## 5. Operator tab commands (launch order)

fleet-droid is a self-feeding tier pool; one tab claims any at-or-below-tier ticket and rides
through dependency gaps. Open Wave-1 concurrency = 2 frontier tabs + 1 strong tab. Keep a
frontier tab alive through Wave 1→2 so it auto-claims RESPONSE-ADAPTER-UNIVERSAL once Fix 1 lands.

```
# Tab A — frontier pool (claims BILLING-EST-COST-FIX, then RESPONSE-ADAPTER-UNIVERSAL after Fix 1 merges)
cd /home/stack/charon-private && fleet/fleet-droid.sh frontier --wait 3 --retries 10

# Tab B — second frontier pool (claims NORMALIZE-CASE-QUANT-FIX in parallel)
cd /home/stack/charon-private && fleet/fleet-droid.sh frontier --wait 3 --retries 10

# Tab C — strong pool (claims TEST-HARDEN-CONTRACT)
cd /home/stack/charon-private && fleet/fleet-droid.sh strong --wait 3 --retries 10
```

Per-ticket mapping:
- `BILLING-EST-COST-FIX` → frontier (Tab A or B)
- `NORMALIZE-CASE-QUANT-FIX` → frontier (the other of A/B)
- `TEST-HARDEN-CONTRACT` → strong (Tab C)
- `RESPONSE-ADAPTER-UNIVERSAL` → frontier — auto-claimed by a freed Tab A/B once
  `BILLING-EST-COST-FIX` is merged + `fleet/done.sh BILLING-EST-COST-FIX`. No extra tab.

Manager marks each merged ticket done: `cd /home/stack/charon-private && fleet/done.sh <TICKET-ID>`
(requires a MERGED PR). Money-path tickets (1, 2, 4) → ADVERSARIAL review before merge.
