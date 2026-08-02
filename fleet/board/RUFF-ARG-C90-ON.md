repo: charon
tier: economy
priority: 0
difficulty: 3
work_class: ci-infra
branch: fix/ruff-arg-c90-on
depends_on: RUFF-PREVIEW-ON
dep-kind: merge-order
owns: pyproject.toml, tests/test_lint_complexity_args_rules.py
real-dep: |
  real-dep: RUFF-PREVIEW-ON — co-owns `pyproject.toml`; MERGE-ORDER only
  [[disjoint-owns-not-no-dependency]]. There is also a REAL measurement dependency on top of the
  file collision: preview gates some rules, so the ARG/C90 finding counts measured before
  preview lands are not the counts this ticket will burn down. Landing behind preview means
  measuring once instead of twice.
serial_justified: |
  Two rule families that must be enabled together, because the C90 complexity threshold is only
  choosable once you can see what ARG's dead-parameter removal does to the call sites. Splitting
  them means picking `max-complexity` against a tree that is about to change, then re-picking it.
  The pylint comparison cannot be split off either — its whole purpose is to decide whether ARG
  goes on at all, so it has to happen inside the ticket that turns ARG on.
substrate: N/A
substrate-novel: |
  NO NEW TOOL IS ADOPTED HERE and none is proposed, so there is no external substrate to consult
  a registry about. ruff is already adopted, already in CI, already reading this exact config
  table. `ARG` (flake8-unused-arguments) and `C90` (mccabe) are rule families INSIDE it.
  The one genuine adopt-question in the neighbourhood is pylint, and this ticket does NOT settle
  it by assertion — it makes MEASURING it a required deliverable, because the recorded evidence
  is in open conflict and the registry itself flags the record as untrustworthy. Details are in
  the note; the short version is that the pylint EVAL-REGISTRY row is classified DRIFTED and
  says in its own text that it MAY NOT be cited as settled, so neither "pylint is redundant" nor
  "pylint is needed" is available to be asserted here. That is why the comparison is scoped as
  work rather than quoted as a conclusion.
  THE NOVEL SLICE: the adopt-ONE verdict between two overlapping linters on OUR corpus, the
  complexity threshold chosen from measured distribution rather than from a blog default, the
  per-finding disposition of a 400+ finding burn-down, and a fail-on-revert assertion. None of
  those is a thing any tool ships. All of them have to be written here.
source: |
  fleet/state/PRIORITY-TODO.md section A, row A2 (`extend-select = ["S","BLE","ARG","C90"]`, 184
  findings). `S` and `BLE` are already carried by RUFF-SEC-RULES-ON; this ticket is the
  UNCOVERED remainder of that row — ARG and C90. Verified live 2026-08-01: pyproject.toml:52
  `select = ["E","F","I","B","UP"]`, no `extend-select` key, no `[tool.ruff.lint.mccabe]` table.
note: |
  ## WHAT IS ACTUALLY UNCOVERED

  PRIORITY-TODO row A2 asks for four families. `RUFF-SEC-RULES-ON` covers exactly two of them,
  `S` and `BLE`, and says so in its own accept block. `ARG` and `C90` are covered by NOTHING on
  the board. This ticket is that remainder and only that remainder.

  ## THE PYLINT QUESTION — MEASURE IT, DO NOT ASSUME IT

  This is the most important paragraph in the ticket. Read it before writing any config.

  `PYLINT-UNUSED-ARGS` sits in `fleet/state/submitted/` with product PR #210 open, adopting
  pylint's W0613 (unused-argument). ruff's `ARG` family targets the same defect class. It LOOKS
  like a duplicate. IT HAS BEEN MEASURED AND THE TWO ARE NOT EQUIVALENT, and the numbers do not
  point the way the "obvious duplicate" reading assumes:

    ruff `--select ARG`   406 findings   (ARG001 198, ARG005 162 lambda, ARG002 45, ARG003 1)
    pylint W0613           46 findings

  ruff is roughly NINE TIMES noisier on this corpus. The reason is a real semantic difference,
  not a tuning artefact: pylint EXCLUDES overridden and abstract methods — a parameter you are
  forced to accept because you are implementing an interface is not an unused argument in any
  useful sense — and ruff's ARG005 (162 of the 406) targets unused LAMBDA arguments, a class
  pylint does not report at all. "More findings" is not "better tool" when the excess is
  structural noise.

  THE EVIDENCE ON RECORD IS ALSO IN CONFLICT, WHICH IS WHY THIS MUST BE RE-RUN, NOT LOOKED UP.
  `fleet/state/EVAL-REGISTRY.md` line 83 (the pylint row) reports `ruff --select ARG` = 50 vs
  pylint 46 — an eight-fold difference from the 406 above, because that measurement was scoped
  to `src` only while 406 spans the wider tree. That same row is classified **drifted** and
  states in its own text that it MAY NOT be cited as settled. So there is no citable verdict in
  either direction. Anyone who resolves this by quoting a number without stating its SCOPE will
  reproduce the exact defect the registry's ANTI-PATTERN row (line 150) exists to catch:
  execution is not completeness, and an eval that does not say how the incumbent was configured
  has not made the comparison it claims.

  REQUIRED DELIVERABLE — a real comparison, run fresh, on identical scope:
  1. Run BOTH tools over the SAME file set. State that file set explicitly in the report. Run
     ruff both with and without `--preview` (RUFF-PREVIEW-ON lands ahead of this; report the
     post-preview numbers as the operative ones).
  2. Produce the intersection and BOTH difference sets by file:line, not just totals. Totals are
     what produced the 50-vs-406 confusion in the first place.
  3. Characterise each difference set. Specifically answer: how many of ruff's excess are
     ARG005 lambda; how many are on methods pylint skipped as overridden/abstract; and are there
     any findings pylint reports that ruff does NOT (if that set is non-empty, ruff cannot
     simply replace pylint and the verdict must say so).
  4. Emit an explicit ADOPT-ONE verdict with the evidence attached. Both outcomes are legitimate
     results: ruff-only (configure ARG to suppress the noise classes), or pylint-only for this
     class (ARG stays off, C90 still goes on). "Adopt both" requires a written justification for
     paying two tools for one defect class and is the outcome to be most suspicious of.
  5. If the verdict changes the pylint record, add or correct the EVAL-REGISTRY row IN A
     SEPARATE COMMIT AND A SEPARATE PUSH from the config change. A registry row minted in the
     same push as the ticket that cites it is self-serving evidence and the substrate gate
     rejects it by design.

  DO NOT CLOSE, MERGE, OR COMMENT ON PR #210 AS PART OF THIS TICKET. Its disposition follows
  from the verdict and belongs to whoever owns that ticket. Producing the evidence is this
  ticket's job; acting on someone else's PR is not.

  ## C90 — PICK THE THRESHOLD FROM THE DISTRIBUTION

  `C90` needs `[tool.ruff.lint.mccabe] max-complexity = N`. Do not copy a default off the
  internet. Measure the complexity distribution across the tree first, then choose N so that it
  catches the genuine outliers without turning into a 200-item refactor backlog. State the
  chosen N and the distribution that justified it. A threshold nobody can pass gets reverted
  within a week, which is worse than not enabling it.

  ## SCOPE

  1. Land the pylint-vs-ARG comparison and its verdict FIRST. The config follows the evidence.
  2. Per the verdict, add `ARG` (and/or leave it off) and add `C90` to the ruff selection in
     `pyproject.toml`. Use `extend-select` so the existing `select` list stays intact and the
     preceding tickets' entries are not disturbed.
  3. Add `[tool.ruff.lint.mccabe] max-complexity = <measured N>`.
  4. Burn down or explicitly baseline (see below).
  5. Add the fail-on-revert test.
  6. Do NOT touch `[tool.mypy]` — that is the ticket sequenced behind this one.

  ## BURN DOWN OR BASELINE — THIS ONE IS EXPLICITLY BASELINED, AND HERE IS THE ORDER

  Unlike RUFF-PREVIEW-ON's 12, this is a 400-scale surface. A full same-sitting burn-down is not
  realistic and pretending otherwise gets the rules reverted. So this ticket BASELINES — but
  under a hard sequencing rule:

  FIX FIRST, GENERATE THE BASELINE SECOND. PRIORITY-TODO section D4 is explicit that a
  suppression baseline generated BEFORE known defects are fixed "freezes the bugs in
  permanently". Concretely:
  a. Fix every finding in the classes the comparison identifies as REAL (genuinely dead
     parameters indicating a mis-wired or stale interface — the pylint row lists real instances
     of exactly this).
  b. THEN generate the allowlist over whatever remains, so it contains only consciously accepted
     residue.
  c. The baseline is a RATCHET: the existing residue is grandfathered, and NO NEW finding is
     permitted. A baseline that silently absorbs new findings is not a baseline, it is an
     `# ruff: noqa` with extra steps.
  d. Record the residue count. That number is the debt this ticket is knowingly leaving, and it
     has to be visible for anyone to ever pay it down.

  ## DONE CONTRACT — RED THEN GREEN, EXTERNALLY RED-PROOFED

  a. The pylint-vs-ARG comparison is reported with intersection + both difference sets + an
     explicit adopt-ONE verdict and its evidence. A verdict with only totals is REJECTED.
  b. `C90` is enabled with a `max-complexity` justified by a stated measured distribution.
  c. `ARG` is enabled, or explicitly NOT enabled with the measured reason.
  d. `ruff check src tests` is GREEN with the ratchet in place.
  e. FAIL-ON-REVERT: `tests/test_lint_complexity_args_rules.py` asserts the enabled families are
     actually active AND that `max-complexity` is set to the chosen value. Removing `C90` from
     the selection goes RED. Removing `ARG` (if adopted) goes RED. Deleting the `mccabe` table
     goes RED. Three independent reverts, three REDs.
  f. The ratchet itself has a test: a NEW finding introduced into a fixture must FAIL, proving
     the baseline grandfathers only what it was generated over.
  g. Report BOTH counts, green intact and RED on each revert.

## Dependencies & Sequence

- **depends_on: RUFF-PREVIEW-ON — merge-order on `pyproject.toml`, PLUS a real measurement
  dependency.** Preview gates rules; the EVAL-REGISTRY bandit row records `S404` as
  preview-gated and measuring 9 only under `--preview`. Measuring ARG/C90 before preview lands
  means measuring twice.
- **THE owns-COLLISION, stated in full.** `pyproject.toml` is wanted by FOUR live tickets:
  `RUFF-SEC-RULES-ON`, `RUFF-PREVIEW-ON`, this one, and `MYPY-STRICTNESS-3-FLAGS`. THEY CANNOT
  RUN IN PARALLEL — `fleet/validate_board.sh` REDs an unordered live owns-collision, and
  concurrent edits to one TOML table conflict by construction.
- **The chain, and why this order.**
  `RUFF-SEC-RULES-ON` → `RUFF-PREVIEW-ON` → **RUFF-ARG-C90-ON** → `MYPY-STRICTNESS-3-FLAGS`.
  Security ratchet anchors (it already holds the file). Preview second because it is cheapest
  (12 findings, 7 mechanical) and it changes what everything behind it measures. THIS ticket
  third: it is a large burn-down whose ARG pass strips dead parameters and whose C90 pass forces
  complexity down, and both of those SHRINK the mypy surface sitting behind it. mypy last, run
  against the smallest residue. Every step reduces the next step's work.
- **Blocks / unblocks:** blocked by `RUFF-PREVIEW-ON`; blocks `MYPY-STRICTNESS-3-FLAGS`.
  Independent of `SHELLCHECK-OPTIONAL-CHECKS-ON` and `GRAPHIFY-AFFECTED-WIRE` (different repo,
  no shared path) — those may run concurrently with this entire chain.
- **Relationship to `PYLINT-UNUSED-ARGS` (submitted, PR #210) — EVIDENCE COUPLING, NOT a
  depends_on edge.** They share NO owned path, so there is no file collision and no merge order
  to enforce. What they share is a decision. This ticket produces the measurement that decides
  it; it does NOT act on that PR. Deliberately not a `depends_on`, because making it one would
  deadlock two tickets against each other over a question neither has answered yet.
- **Concurrency safety:** `tests/test_lint_complexity_args_rules.py` is a NEW path owned by no
  other live ticket; verified against the live board 2026-08-01.
