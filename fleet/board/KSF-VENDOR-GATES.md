repo: charon-private
tier: strong
difficulty: 4
priority: 0
work_class: rig-meta
branch: feat/ksf-vendor-gates
owns: /home/stack/code/charon/tools/_vendor/ksf_gates/redproof.py,
  /home/stack/code/charon/tools/_vendor/ksf_gates/wiring_alignment.py,
  /home/stack/code/charon/tools/_vendor/ksf_gates/coverage_ssot.py,
  /home/stack/code/charon/tools/_vendor/ksf_gates/no_vacuous.py,
  /home/stack/code/charon/tools/_vendor/ksf_gates/fail_loud.py,
  /home/stack/code/charon/tools/check_redproof.py,
  /home/stack/code/charon/tools/check_wiring_alignment.py,
  /home/stack/code/charon/tools/check_coverage_ssot.py,
  /home/stack/code/charon/tools/check_no_vacuous.py,
  /home/stack/code/charon/tools/check_fail_loud.py,
  /home/stack/code/charon/.ksf/manifest.toml,
  /home/stack/code/charon/tools/gate_runner.py,
  /home/stack/code/charon/tests/test_ksf_vendor_gates.py
source: fleet/state/META-TOOL-WIRED-AND-WORKING.md VERDICT + "Adoption plan" step 2 (KS5 —
  apply the KSF framework to Charon, not just vendor one gate). Read-only research, all claims
  file:line-verified against /home/stack/code/keystone and /home/stack/code/charon.
work_class_note: rig-meta — this vendors an OWN in-house framework's remaining gates into the
  product repo's gate suite; it is gate-integrity tooling, not a product feature.
note: |
  Charon has vendored exactly ONE of KSF's gates (tools/check_inert_code.py, wired at
  gate_runner.py:47) out of ~11. This ticket vendors the remaining anti-theater/completeness
  gates that close the "EXERCISED-WITH-OBSERVABLE-EFFECT" property for GATES (already solved in
  KSF itself, just not applied here): `redproof` (every gate/module must ship a companion
  negative test that actually goes RED), `wiring_alignment` (prod-path == test-path), `coverage_ssot`
  (every declared gate is implemented AND wired), `no_vacuous` (0 tests/0 gates discovered = RED),
  `fail_loud` (runner must exit non-zero on a failing fixture). Source gates:
  /home/stack/code/keystone/ksf/gates/{redproof,wiring_alignment,coverage_ssot,no_vacuous,
  fail_loud}.py — vendor verbatim (same pattern as check_inert_code.py's existing
  tools/_vendor/ksf_inert_code.py shim), do not reimplement KSF's logic by hand.
  EXTENDS, DOES NOT REPLACE fleet/board/RECONCILE-GATE-WIRED.md: KSF's gates are a Python-AST
  reachability/anti-theater engine; reconcile-gate-wired.sh is the bash/cross-repo
  declared-vs-fired axis KSF's AST cannot see (fleet/*.sh firing layers, RULE-REGISTRY.tsv,
  native required-checks). Keep both; this ticket does not touch reconcile-gate-wired.sh.
  Reject list re-confirmed by the source doc (do not re-litigate): Vulture (misses
  mutually-referencing dead islands, dedicated fixture-backed eval already reversed a tentative
  adopt), import-linter/tach (wrong invariant — layer contracts, not entrypoint-reachability),
  deptry (Charon core `dependencies=[]`, near-no-op). [[audit-hand-rolled-vs-best-in-class]]
  [[ksf-modular-plugin-best-in-class]]
accept: |
  - Vendor the 5 named KSF gates verbatim into tools/_vendor/ksf_gates/ (same shim pattern as the
    existing tools/_vendor/ksf_inert_code.py -> tools/check_inert_code.py wrapper), each with its
    own tools/check_<gate>.py wrapper.
  - .ksf/manifest.toml + entrypoints config for Charon's actual layout (KSF expects `.ksf/`;
    Charon already shims this at check_inert_code.py:71 for inert_code alone — extend the same
    shim to cover all 5 new gates, do not fork a second config mechanism).
  - tools/gate_runner.py: register all 5 new checks in CHECKS (same registration shape as the
    existing check_inert_code.py entry at :47) so `charon gate` runs them.
  - `ksf --repo-root . gate && ksf verify-self` runs clean against Charon (or the honest current
    gap is documented if it can't yet — no silent partial-pass).
  - fail-on-revert test (tests/test_ksf_vendor_gates.py): (a) a fixture module with a gate/check
    that has NO companion negative test -> redproof RED; add the negative test -> GREEN;
    (b) a fixture prod-path/test-path mismatch -> wiring_alignment RED; align them -> GREEN;
    (c) a fixture declared-but-unimplemented gate -> coverage_ssot RED; implement it -> GREEN;
    (d) 0 tests collected in a fixture run -> no_vacuous RED; (e) a failing fixture check that
    exits 0 anyway (the exact #200 gate_contract-class bug) -> fail_loud catches it (non-zero
    forced). Revert any fix -> RED again.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — edits the load-bearing
    tools/gate_runner.py CHECKS registration (the merge-blocking spine every other gate rides);
    manager gates, PR does NOT merge on the builder's self-report.
scope: |
  Vendor + wire the 5 named KSF gates only. Does not touch fleet/checks/reconcile-gate-wired.sh
  (RECONCILE-GATE-WIRED owns it, EXTENDS not replaces) and does not build diff-cover/mutmut
  (DIFF-COVER-MUTMUT-ADOPT owns that, depends_on this for the shared gate_runner.py edit point).
ds: |
  ## Dependencies & sequence
  No hard depends_on (disjoint owns from RECONCILE-GATE-WIRED.md — different files, complementary
  engines per the source doc's "EXTEND, not replace" verdict). Recommended human sequencing per
  the adoption plan (land+wire reconcile-gate-wired FIRST, then this) is operational, not a code
  prereq — both are independently parallelizable. DIFF-COVER-MUTMUT-ADOPT depends_on THIS (shares
  the tools/gate_runner.py edit point — real build/correctness prereq, marked there).
