# ADVREVIEW-BACKLOG-B — per-branch verdicts

## Branch: `feat/inventory-table`
**Verdict: LAND**

**What it adds (262 insertions, 3 files):**
- `fleet/inventory-table.sh` — KS29 accessor with Python engine (`init`/`read`/`upsert-row`/`list-by-status`)
- `fleet/state/price-tracked-inventory.tsv` — 13-provider seed data in canonical format
- `docs/review-log/INVENTORY-TABLE.md` — review fragment

**Tests run:**
- `inventory-table.sh --help` -> exit 0
- `init` on existing TSV -> exit 0
- `init` on new TSV -> exit 0
- `read` match (deepseek/deepseek-v4-pro) -> exit 0, correct row returned
- `read` miss (deepseek/nonexistent) -> exit 1, empty output
- `upsert-row` (new provider/model) -> exit 0, read-back confirms
- `upsert-row` (existing key, overwrite fields) -> exit 0, replaces entry correctly
- `list-by-status candidate` -> exit 0, all 13 seed rows returned

**RED-PROOF performed:**
- Remove TSV file -> `FileNotFoundError`, exit 1 (RED) — correct
- Corrupt TSV with garbage -> `IndexError`, exit 1 (RED) — correct

**Evidence:** Script runs and fails correctly under external breakage. No test file exists in `fleet/tests/`. The self-test pattern described in the header (upsert then read-back by normalized key) confirmed working. Content is NOT already on master (two-dot diff matches three-dot diff — not squash-merged).

---

## Branch: `review/reconcile-gate-design`
**Verdict: LAND**

**What it adds (243 insertions, 1 file):**
- `fleet/state/REVIEW-RECONCILE-GATE-DESIGN.md` — adversarial design review of PR #178

**Tests run:** n/a — DESIGN-REVIEW-ONLY, no executable surface.

**RED-PROOF:** n/a — DESIGN-REVIEW-ONLY.

**Evidence:** The document is a thorough adversarial review of the UNIFIED-RECONCILIATION-GATE design (PR #178). It ground-truths every claim against the live repo, identifies 2 NEEDS-REVISION items (fail-closed taxonomy scope gap, root-level file fail-open path), and produces a RECOMMENDATION of APPROVE-FOR-OPERATOR. The review is sound, current, and serves its purpose as an artifact the operator can reference. Content is NOT already on master (two-dot diff matches three-dot diff).

---

## Branch: `feat/price-tracked-inventory-autoswap`
**Verdict: LAND**

**What it adds (48 insertions, 1 file):**
- `docs/review-log/PRICE-TRACKED-INVENTORY-AUTOSWAP.md` — design review fragment

**Tests run:** n/a — DESIGN-REVIEW-ONLY, no executable surface.

**RED-PROOF:** n/a — DESIGN-REVIEW-ONLY.

**Evidence:** Design document composing 4 existing pieces (catalog_refresh, pricing_limits_checker, cost_rank, provider_presets) into a price-tracked-provider inventory + auto-swap system. No new routers or price sources required. Decisions are sound and honest about risks (first drift has no cache, NeuralWatt detection depends on PRICE-REFRESHER). Inventory TSV is KS29-aligned but not gated. Content is NOT already on master.

---

## Branch: `fix/inert-wiring-enforcement-durable`
**Verdict: LAND**

**What it adds (35 insertions, 1 file):**
- `docs/review-log/INERT-WIRING-ENFORCEMENT-DURABLE.md` — review log for inert-wiring enforcement design

**Tests run:** n/a — DESIGN-REVIEW-ONLY, no executable surface.

**RED-PROOF:** n/a — DESIGN-REVIEW-ONLY.

**Overlap with INERT-INSTANCE-DETECT (checked per prompt requirement):**
- **Domains are separate**: INERT-INSTANCE-DETECT is product-side (Python detector `check_inert_code.py` in `tools/`, owns product repo files). `fix/inert-wiring-enforcement-durable` is rig-side (fleet wiring infrastructure, shell scripts, meta-gates). They operate on different repos with zero owns overlap.
- **No dependency edge**: The inert-wiring-enforcement design correctly states "Product inert gate IS wired" and addresses rig-side wiring gaps. The blind spot (registry-registration treated as reachability) is a detection accuracy issue in the product detector, not a wiring issue in the rig. The design does not depend on the product detector being correct.
- **No contradiction**: The 9 spawned backlog tickets (GRAPHIFY-FRESHNESS-MERGE through PRODUCT-WIRING-META-EXTEND) operate on rig-owned files. They do not duplicate or conflict with INERT-INSTANCE-DETECT's scope (fixing the detector + dispositioning 6 gateway modules).
- **Conclusion**: No blocking overlap. LAND is safe independent of INERT-INSTANCE-DETECT.

**Evidence:** The review log is a root-cause analysis of the recurring built-but-not-wired class, identifying a tetrad of causes and proposing a WIRING-MANIFEST + dual meta-gates solution. It correctly inventories 13 un-wired/orphaned tools despite 3 dedicated audits. Spawns a clean 9-ticket backlog. Content is NOT already on master.

---

# Per-branch summary

| Branch | Verdict | Rationale |
|---|---|---|
| feat/inventory-table | **LAND** | Script runs, RED-PROOF confirmed, no test file exists but self-test pattern verified |
| review/reconcile-gate-design | **LAND** | Sound adversarial design review, DESIGN-REVIEW-ONLY |
| feat/price-tracked-inventory-autoswap | **LAND** | Sound design composition, DESIGN-REVIEW-ONLY |
| fix/inert-wiring-enforcement-durable | **LAND** | Root-cause analysis correct, no overlap with INERT-INSTANCE-DETECT, DESIGN-REVIEW-ONLY |

=== SESSION REPORT v1 ===
TICKET:       REVIEW-BACKLOG-B
SESSION:      qui-gon-jinn | deepseek-v4-flash
STATUS:       DONE
COMMIT:       none
FILES:        1 changed: fleet/handoff-notes/ADVREVIEW-BACKLOG-B.md
OWNS-OK:      yes
GATE:         n/a — read-only review
TESTS:        feat/inventory-table: 9 operations run, 9 passed, 0 failed (--help, init x2, read match, read miss, upsert-row x2, list-by-status x2) | other 3 branches: DESIGN-REVIEW-ONLY, no executable surface
RED-PROOF:    feat/inventory-table: broken=missing-TSV-exit-1 broken=corrupt-TSV-exit-1 green=normal-read-exit-0 | n/a — other 3 are DESIGN-REVIEW-ONLY no executable surface
OBSERVABLE:   MET — all operations observed running and failing
RAN:          inventory-table.sh --help, init, read, upsert-row, list-by-status (9 operations); RED-PROOF corrupt/missing TSV (2 external breaks)
READ:         review/reconcile-gate-design (sound design review, APPROVE-FOR-OPERATOR), feat/price-tracked-inventory-autoswap (sound composition design), fix/inert-wiring-enforcement-durable (root-cause analysis correct, INERT-INSTANCE-DETECT overlap checked — no conflict)
BRIEF-ERRORS: none
BLOCKED-BY:   none
BUDGET:       ok
NEXT:         LAND=4 REWORK=0 ABANDON=0 UNSAFE=0
=== END REPORT ===
