repo: charon
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: fix/inert-code-disposition-backlog
depends_on:
owns: tools/inert-code-disposition.json, docs/review-log/INERT-CODE-DISPOSITION-BACKLOG.md
serial_justified: |
  ONE disposition file. Parallel lanes would each append entries to the same JSON and conflict on
  every write, and two reviewers would classify the same symbol differently.
substrate: N/A
substrate-novel: |
  Nothing to adopt — the detector already exists and already runs (`charon.cli gate` fails on it
  today). This is the BACKLOG the detector found, not a new mechanism. Each entry is a human
  DISPOSITION judgement about our own code, which no external tool can make.
execution: |
  Off-Claude, SG droid tab. Use BARE model ids only — never provider-pinned (`-go`, `-ds`,
  `-groq`). Verified serving 2026-08-02: kimi-k2.6, deepseek-v4-flash, minimax-m2.5.
source: |
  Operator, 2026-08-02, verbatim - "WE ALWAYS FIX PRE-EXISTING." The product gate
  `PYTHONPATH=src python3 -m charon.cli gate` FAILS with
  "18 dead symbol(s) not present in inert-code-disposition.json — every 0-caller symbol must be
  tracked with a {reason, disposition} entry", and that failure is BLOCKING an unrelated
  money-path fix (fix/soleleg-guard-blocks-autopark, which makes auto-park reachable at all).
note: |
  ## WHY THIS IS P0 DESPITE BEING A CHORE
  It is a RED on the product's own gate, so it blocks EVERY product push — including a fix to a
  core broker guarantee. A pre-existing red that blocks unrelated work is not "someone else's
  problem"; it is a toll on all future landings. Operator rule - we always fix pre-existing.

  ## WHAT THE GATE WANTS
  Every symbol with ZERO callers must carry a `{reason, disposition}` entry in
  `tools/inert-code-disposition.json`. Known examples from the live failure:
    [keep-pending-phase2-credproxy]  charon.egress.nginx_credproxy_template_stub
    [delete]                          charon.pricing_limits_checker.load_configured
    [keep-detector-false-positive-module-unreachable-cascade] charon.types.SpendDecision
  Run the gate to get the CURRENT full list — do not work from this excerpt, it is a sample:
    PYTHONPATH=/home/stack/code/charon/src python3 -m charon.cli gate

  ## HOW TO DISPOSITION — this is judgement, not bookkeeping
  For EACH of the 18, pick ONE and give a REASON that would convince a reviewer:
    * `delete`  — genuinely dead. Then DELETE IT in this PR. An entry saying "delete" that leaves
      the code in place converts a dead-code finding into a permanent annotation, which is worse
      than the finding: it looks resolved.
    * `keep-pending-<phase>` — real future use, with the ticket/phase NAMED. "Might need it later"
      is not a reason; name what will call it and when.
    * `keep-detector-false-positive-<why>` — the detector is wrong (dynamic dispatch, entry point,
      re-export, typing-only). SAY WHY it is unreachable to a static scan.
  **DO NOT blanket-`keep` the list to turn the gate green.** That is the single failure mode here:
  it would make the gate permanently useless while looking fixed, which is the inert-check class
  this repo already has nine instances of.
  Where a symbol IS reachable but the detector cannot see it, prefer fixing the REACHABILITY
  (an explicit export/registration) over annotating an exception.

  ## SANITY-CHECK THE DETECTOR WHILE YOU ARE HERE
  If several of the 18 are false positives of the SAME shape (e.g. a module-unreachable cascade —
  one unreferenced module making all its symbols look dead), say so plainly. A detector producing
  systematic false positives is a finding worth more than the 18 entries, and belongs in the
  review-log even if the fix is out of scope.
accept: |
  a. `PYTHONPATH=/home/stack/code/charon/src python3 -m charon.cli gate` exits 0.
  b. Every one of the 18 has a disposition AND a specific reason. No bare "keep".
  c. Every `delete` disposition has the code ACTUALLY DELETED in the same change.
  d. Full suite green: `pytest -q` from the product root.
  e. ANTI-REGRESSION: add or confirm a test that the gate still FAILS when a new 0-caller symbol
     is introduced without an entry. The gate must stay able to go RED — a gate turned green by
     annotation and never seen to fail again is the defect, not the fix.
  f. `docs/review-log/INERT-CODE-DISPOSITION-BACKLOG.md` records the per-symbol judgement, and
     any systematic detector false-positive pattern found.
scope: |
  The 18 flagged symbols, their dispositions, and deletion of those judged dead. Does NOT change
  the detector's logic and does NOT touch `src/charon/forwarder.py` or `src/charon/proxy.py`
  (both in flight on other lanes).

## Dependencies & Sequence

- **depends_on: none.**
- **BLOCKS `fix/soleleg-guard-blocks-autopark`** (auto-park dead for all 17 providers) and every
  other product push, because it is a product-gate RED. Land it FIRST.
- Disjoint from the live park lanes: they own `forwarder.py` / `proxy.py`; this owns the
  disposition JSON only.
