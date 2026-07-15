# FN5-REGISTRY-SWEEP — Review Log

## Ticket

FN5-REGISTRY-SWEEP: sweep the charon PRODUCT + fleet RIG + KSF for "smart module
registry" candidates — sites where a data-driven registry would replace
accretion-prone code so that adding a thing = 1 data row + 1 file with ZERO
edits to a central file.

## What was done

- **Audit deliverable** written to `fleet/state/REGISTRY-CANDIDATES.md` (~30 KB,
  7 sections, 18 candidates ranked by leverage).
- **Reuse-check performed** (hard): the existing F29 module-registry
  (`src/charon/gateway.py:_MODULE_SPECS`, PR #100/085e74f) and the DESIGNED
  KS29 component-registry-primitive (`state/ROADMAP.tsv:KS29`) are the
  single source of truth. Every candidate reuses the F29 `ModuleSpec` shape
  directly (or, for #12, IS the primitive). No candidate hand-rolls a new
  registry mechanism.
- **Collision data integrated** from a live `bash fleet/wci-actions.sh` run
  2026-07-14T08:33:41Z: 8 hotspots, 4 of which the candidates directly
  address (2-owner `src/charon/gateway.py`, 4-owner `fleet/handoff.sh`,
  3-owner `fleet/handoff-check.sh`, 2-owner `fleet/preflight.sh`).
- **Sweep coverage**: 71 product modules (~18,900 LOC), 49 fleet shell scripts,
  199 board files, 18 benchmark subdirs, the full KSF surface
  (`tools/gates.json` + `inert-code-disposition.json` + 16 `check_*.py` + 2
  vendored KSF modules). ~85 sites inventoried, 18 in-scope, ~20 already
  registry-shaped, ~47 trivially excluded.
- **Build order emitted**: KS29 first (substrate), then F29→KS29 alignment
  (Candidate #18), then catalog/providers (Candidate #6, KS29's stated first
  instance), then the high-leverage collision unblocks (#2, #11), then the
  smaller wins fan out.

## Key decisions

- **F29 is the reference template (Candidate #1), not a separate candidate.**
  The ticket says "Candidate #1 = the Smart-Routing module registry (F29,
  already ACCEPTED)". F29 is sealed; the audit generalizes its shape, not its
  body. The 17 other candidates are all "F29 shape, different scope."

- **KS29 is the substrate blocker (Candidate #12), explicitly prioritized in
  the build order.** The `state/overnight/KS29-REVIEW.md` FIX-REQUIRED #1+#2
  (discovery leg missing, lying docstrings) is the literal blocker: without
  the discovery leg, every candidate below hand-rolls a slight variant of
  `ModuleSpec`. Build KS29 first; the next 17 candidates become "register this
  scope" tickets, not "design a registry" tickets.

- **Build order ≠ anti-accretion leverage order.** The 2 highest-leverage
  candidates (#2 gateway HTTP dispatch, #11 tickets table) are scheduled AFTER
  the lower-leverage but substrate-blocking #12 (KS29) and #18 (F29→KS29
  alignment). Building them on the hand-rolled F29 shape first would create
  the very drift risk Candidate #18 is meant to prevent.

- **KS28 (consolidate-pattern-guard) is realized as Candidate #17 + a KS29
  conformance check.** KS28's scope (collapse 4 pattern-scanning gates into
  one registry-driven meta-gate) IS the denylist-as-data row + the drift
  check that all rows have `last_reviewed < 90d`. The candidate is the data;
  KS28 is the gate that consumes it.

- **The RIG candidates (#10, #11, #13-#17) are quality-of-life, not
  blocking.** They reduce future friction; they don't unlock a single
  ticket that can't ship without them. The PRODUCT candidates (#2-#9, #18)
  directly address the live 2-owner `gateway.py` collision and the F29
  second-wave cleanup (`state/ROADMAP.tsv:KS29 row: "Instances: ... catalog/providers"`).

- **Trivial if-ladders are explicitly excluded** (3-branch `stop_reason` in
  `decompose_sizing.py:659`, 4-state `Autonomy` enum in `types.py:20`,
  Callable-injected `Scheduler.classify`). A registry there is more code, not
  less. Listing them in §3 (Sites NOT in scope) for the next reviewer to
  confirm.

- **`balance.py:151-155` `_POLL_ADAPTERS` is already registry-shaped** but
  `balance.py` ALSO has 3 if-ladders on `mode: str` (Candidate #8). Mixed
  file: registry exists for the data, if-ladder exists for the dispatch.
  Candidate #8 generalizes the dispatch the same way `_POLL_ADAPTERS`
  generalizes the data.

## Scope discipline (per owns: + LAUNCHER NOTE)

- The ticket `owns:` is exactly one absolute path:
  `/home/stack/charon-private/fleet/state/REGISTRY-CANDIDATES.md`.
- The LAUNCHER NOTE forbids editing the main checkout
  `/home/stack/charon-private`; the file lives in the worktree at the
  relative path `fleet/state/REGISTRY-CANDIDATES.md` (same path, worktree
  branch `feat/fn5-registry-sweep`).
- This review-log fragment is the per-ticket exception
  (`docs/review-log/FN5-REGISTRY-SWEEP.md`).
- No other files were created or modified. No `fleet/SMART-ROUTING.md`,
  no `state/ROADMAP.tsv`, no source code edits, no fleet/*.sh, no
  tools/check_*.py. Scope-clean.

## Verification

- `git -C <worktree> diff --name-only master...HEAD` (to be run at commit
  time) should show exactly:
  - `fleet/state/REGISTRY-CANDIDATES.md` (new)
  - `docs/review-log/FN5-REGISTRY-SWEEP.md` (new)
- No tests, no gate runs needed — this is a pure documentation ticket (a
  registry of registry candidates, not code). The `wci-actions.sh` and
  `tools/gates.json` referenced in the audit are read-only evidence, not
  the ticket's deliverable.

## Output feeds (downstream tickets)

- **F29 second wave** (post-merge): #2, #3, #4, #5, #7, #8, #9, #18.
- **KS20 anti-accretion** (Wave E): #10, #11, #13, #15, #16, #17.
- **KS28 pattern-guard** (Wave E): #17 (delivered via this candidate).
- **KS29 component-registry-primitive** (Wave F): #12 (build it) + the rest
  become data rows.
- **KS24 lens-drift** (Wave E): #11, #18 (drift-check on declared-owns-files
  vs actually-edited-files is KS29's drift leg applied to ticket scope).
