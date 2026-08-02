repo: charon
tier: strong
priority: 0
difficulty: 4
work_class: ci-infra
branch: fix/mypy-strictness-3-flags
depends_on: RUFF-ARG-C90-ON
dep-kind: merge-order
owns: pyproject.toml, tests/test_mypy_strictness_flags.py
real-dep: |
  real-dep: RUFF-ARG-C90-ON — co-owns `pyproject.toml`; MERGE-ORDER
  [[disjoint-owns-not-no-dependency]], plus a real surface dependency: that ticket's `ARG` pass
  removes dead parameters and its `C90` pass forces complexity down, and both shrink what
  `warn_unreachable` and `warn_return_any` will report here. Landing this first means burning
  down findings that the ruff pass would have deleted for free.
serial_justified: |
  Three mypy flags that share one burn-down. They are inseparable in practice because they
  overlap on the same code: `check_untyped_defs` is what makes bodies visible at all, and
  `warn_unreachable` / `warn_return_any` mostly fire INSIDE the bodies it opens up. Enabling
  them one at a time means three passes over the same functions and three re-measures of the
  same residue. One file, one burn-down, one ratchet.
substrate: N/A
substrate-novel: |
  NO TOOL IS ADOPTED HERE. mypy is already adopted, already configured at `pyproject.toml:54-58`
  (`python_version = "3.11"`, `files = ["src/charon","tools","tests"]`, `ignore_missing_imports`,
  `explicit_package_bases`), and already runs in the pre-push gate. This ticket adds three
  boolean keys to a table that already exists.
  The adjacent substrate question — should we run a DIFFERENT type checker (pyright, pyre, ty) —
  is not opened by this ticket and must not be opened inside it. The reasoning is the same one
  the EVAL-REGISTRY's ANTI-PATTERN row (under-scoped trial) makes explicit: you may not judge an
  incumbent you have configured narrowly. We are currently running mypy with THREE of its
  standard correctness flags off. Any checker comparison run from today's config would be
  comparing a challenger against a deliberately hobbled incumbent and would reach a conclusion
  the evidence cannot support. Enabling the flags is the PREREQUISITE for that question ever
  being asked honestly, not a substitute for it.
  THE NOVEL SLICE is the disposition policy: which of the three flags we take and which we
  explicitly refuse (see the disallow_untyped_defs section — a measured 1952-finding refusal),
  triage of ~176 findings into real-bug versus annotation-noise, a ratchet generated only after
  the real bugs are fixed, and a fail-on-revert assertion per flag. No type checker ships any of
  that; it is exactly the judgment layer we have to write ourselves.
source: |
  fleet/state/PRIORITY-TODO.md section A, row A3: "mypy `check_untyped_defs` +
  `warn_unreachable` + `warn_return_any` — 176 real bugs. SKIP `disallow_untyped_defs`
  (1952 = churn)". Verified live 2026-08-01: `[tool.mypy]` at pyproject.toml:54 carries NONE of
  the three flags.
note: |
  ## THE FINDING

  `[tool.mypy]` sets `python_version`, `files`, `ignore_missing_imports` and
  `explicit_package_bases`. It sets no strictness flags at all. Three of mypy's standard
  correctness checks are therefore off, and MEASURED they account for roughly 176 real bugs:

    check_untyped_defs   type-checks the BODIES of unannotated functions. Without it mypy walks
                         straight past an entire function the moment its signature is bare —
                         the body is not checked, it is SKIPPED. This is the big one, and it is
                         why the other two under-report today.
    warn_unreachable     flags code that can never execute. Unreachable code is either a dead
                         branch or a logic error, and it is never intentional.
    warn_return_any      flags a function declared to return a concrete type that actually
                         returns `Any`. This is the exact shape of a silently-broken contract:
                         the annotation claims a guarantee the body does not provide.

  ## EXPLICITLY SKIPPED — `disallow_untyped_defs`. THIS IS A DELIBERATE REFUSAL.

  It is the flag everyone reaches for and it is NOT in this ticket. State this in the PR so
  nobody "helpfully" adds it.

  MEASURED: `disallow_untyped_defs` produces **1952 findings**, versus 176 for the three flags
  above combined. That is an eleven-fold larger surface, and the difference is not degree, it is
  KIND:

  - The three adopted flags report BEHAVIOUR — this branch cannot run, this function lies about
    its return type, this body was never checked at all. Each finding is a candidate defect.
  - `disallow_untyped_defs` reports the ABSENCE OF AN ANNOTATION. Every one of its 1952 findings
    is satisfied by typing a signature. That work fixes no bug on its own; the actual bug-finding
    is what `check_untyped_defs` already does to those same bodies WITHOUT requiring the
    annotation first.
  - So the two overlap on WHERE they point and diverge completely on WHAT THEY BUY. We take the
    one that reports defects and refuse the one that reports missing paperwork.

  Cost is the second half of the reason and it is not incidental. A 1952-item annotation sweep
  across `src/charon`, `tools` and `tests` is weeks of mechanical diff touching nearly every
  file in the tree. It would collide with every other in-flight ticket, it would bury real
  review under churn, and it would be reverted the first time it blocked a hotfix. Enabling it
  in the same ticket as the 176 real bugs would also HIDE those bugs — 176 signal in 2128 total
  is a 92% noise floor, and nobody triages that. Refusing it is what makes the 176 visible.

  Gradual typing stays available. Nothing here forbids annotating a module later, and
  `check_untyped_defs` means an unannotated body is checked in the meantime instead of skipped.
  That is the honest incremental path; `disallow_untyped_defs` is the big-bang one.

  ## WHY THIS TICKET IS `tier: strong` WHILE ITS THREE SIBLINGS ARE `economy`

  Deliberate, and worth stating because the rest of this batch is economy on purpose. The other
  A-row tickets are config flips with mechanical or ratchetable burn-downs. This one is ~176
  REAL BUGS requiring per-finding judgment: is this unreachable branch dead code to delete or a
  guard whose condition is inverted? Is this `Any` return a missing annotation upstream or a
  genuine contract violation? Getting that wrong does not produce a lint failure, it produces a
  behaviour change. That is not mechanical work and it should not be priced as if it were.

  ## SCOPE

  1. Add `check_untyped_defs = true`, `warn_unreachable = true`, `warn_return_any = true` to
     `[tool.mypy]` in `pyproject.toml`.
  2. Run mypy over the configured `files` set. Bucket every finding by flag and by error code.
  3. TRIAGE, do not sweep. For each finding decide: REAL BUG (fix it), ANNOTATION GAP (annotate),
     or ACCEPTED RESIDUE (ratchet it, with a reason).
  4. Do NOT add `disallow_untyped_defs`. Do NOT add `strict = true` (which turns it on).
  5. Do NOT touch the three existing `[[tool.mypy.overrides]]` blocks at pyproject.toml:62-72
     unless a finding proves one is now wrong — those are narrowly scoped per-module error-code
     suppressions and widening them is the failure mode this ticket is guarding against.
  6. Do NOT touch the `[tool.ruff]` tables — those belong to the tickets sequenced ahead.
  7. Add the fail-on-revert test.

  ## BURN DOWN OR BASELINE — BOTH, IN THIS ORDER, AND THE ORDER IS THE SAFEGUARD

  EXPLICITLY BASELINED at the end, but ONLY after the real bugs are fixed.

  PRIORITY-TODO section D4 states the rule and the reason: a suppression baseline generated
  BEFORE known defects are fixed "freezes the bugs in permanently". A 176-finding surface is
  exactly big enough to tempt a `--install-types`-style generated ignore file on day one, and
  that single act would convert 176 discovered bugs into 176 permanently invisible ones while
  producing a green CI that looks like progress. Therefore:

  a. FIX every finding triaged as a REAL BUG. `warn_unreachable` and `warn_return_any` findings
     are expected to be overwhelmingly real — treat "baseline it" on those two as needing a
     written justification per finding.
  b. THEN generate the ratchet over the surviving residue (largely `check_untyped_defs`
     annotation gaps in long-untyped modules).
  c. The ratchet grandfathers existing residue and admits NO NEW finding. Use scoped
     `[[tool.mypy.overrides]]` blocks in the existing narrow style — per-module, per-error-code.
     A blanket `ignore_errors` or a repo-wide `# type: ignore` sweep FAILS this ticket.
  d. Record the residue count per flag. That is the visible debt.

  ## DONE CONTRACT — RED THEN GREEN, EXTERNALLY RED-PROOFED

  a. All three flags present and true in `[tool.mypy]`.
  b. `disallow_untyped_defs` is ABSENT, and the PR states the measured reason (1952 vs 176).
  c. mypy is GREEN over the configured files with the ratchet in place.
  d. FAIL-ON-REVERT, per flag, THREE independent reverts and THREE REDs:
     `tests/test_mypy_strictness_flags.py` asserts each of the three flags is enabled in the
     configuration mypy actually resolves. Removing `check_untyped_defs` → RED. Removing
     `warn_unreachable` → RED. Removing `warn_return_any` → RED. A single test that only asserts
     "mypy exits 0" is worthless — it is green TODAY, with all three flags off.
  e. The test must also assert `disallow_untyped_defs` is NOT enabled, so a later `strict = true`
     that silently drags it in goes RED rather than landing a 1952-item churn wave unnoticed.
  f. A per-flag triage ledger in the review-log: findings, fixed, annotated, ratcheted.
  g. Report BOTH counts — green intact, RED on each of the four reverts.

## Dependencies & Sequence

- **depends_on: RUFF-ARG-C90-ON — merge-order on `pyproject.toml`, plus a real surface
  dependency.** ARG deletes dead parameters and C90 forces complexity down; both shrink what
  `warn_unreachable` and `warn_return_any` report here. Running this first means burning down
  findings the ruff pass would have removed for free.
- **THE owns-COLLISION, stated in full.** `pyproject.toml` is wanted by FOUR live tickets:
  `RUFF-SEC-RULES-ON`, `RUFF-PREVIEW-ON`, `RUFF-ARG-C90-ON`, and this one. THEY CANNOT RUN IN
  PARALLEL. `fleet/validate_board.sh` REDs an unordered live owns-collision, and four agents
  editing one TOML file is a guaranteed conflict independent of any gate.
- **The chain, and why this ticket is LAST.**
  `RUFF-SEC-RULES-ON` → `RUFF-PREVIEW-ON` → `RUFF-ARG-C90-ON` → **MYPY-STRICTNESS-3-FLAGS**.
  Security ratchet anchors (already live, already owns the file). Preview second — cheapest (12
  findings, 7 mechanical) and it changes what everything behind it measures. ARG/C90 third — a
  large burn-down that shrinks this ticket's surface. This one last, deliberately: it is the
  largest (176), the least mechanical, and the only one whose findings require behavioural
  judgment. Running it against the smallest possible residue is the point. It is also the only
  member of the chain that is not `tier: economy`, so putting it last keeps three economy-sized
  units flowing before the expensive one is reached.
- **Blocks / unblocks:** blocked by `RUFF-ARG-C90-ON`. Blocks nothing — it is the tail of the
  chain and releases `pyproject.toml` when it lands.
- **Independent of the rig tickets.** `SHELLCHECK-OPTIONAL-CHECKS-ON` and
  `GRAPHIFY-AFFECTED-WIRE` are `repo: charon-private` and share no path with this chain. They
  run concurrently with all four of these.
- **Concurrency safety:** `tests/test_mypy_strictness_flags.py` is a NEW path owned by no other
  live ticket; verified against the live board 2026-08-01.
- **Related, do NOT fold in:** any type-checker replacement evaluation (pyright/pyre/ty). That
  question cannot be asked honestly until these flags are on — see the substrate-novel field.
