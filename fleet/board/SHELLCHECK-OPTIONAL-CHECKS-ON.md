repo: charon-private
tier: economy
priority: 0
difficulty: 3
work_class: ci-infra
branch: fix/shellcheck-optional-checks-on
depends_on:
owns: .shellcheckrc, fleet/gate.sh, fleet/tests/shellcheck-optional.test.sh
serial_justified: |
  Turning the optional checks on and making the gate BLOCK are one change, not two, because
  either half alone is a lie. Optional checks on top of an advisory gate surfaces 15 more
  error-level findings that still cannot fail anything. A blocking gate over the default rule
  set blocks on 9 findings while staying blind to the 15. And the fail-on-revert assertion has
  to ship in the same unit as the flip, because a flip with no assertion is EXACTLY what already
  happened here once — see the fake-done section. One config file, one gate branch, one test.
substrate: N/A
substrate-novel: |
  NO TOOL IS ADOPTED HERE. shellcheck 0.11.0 is already installed, already invoked by
  `fleet/gate.sh:81` over `fleet/*.sh`, and already printing findings on every run. This ticket
  writes a config file for it and repairs the gate branch that consumes its exit code.
  The record on shellcheck in `fleet/state/EVAL-REGISTRY.md` (line 142) is classified **mixed**
  and may not be cited as a settled verdict — but its correction text is the direct evidence for
  this ticket rather than an obstacle to it. That row was reclassified precisely because it ran
  shellcheck at DEFAULT settings and then drew conclusions about what shellcheck can see. Its
  measured correction, on `fleet/fleet-droid.sh` alone: 9 findings at default versus 24 under
  `-o check-set-e-suppressed`, including 15 SC2310 instances never previously seen; and 21 under
  `-o check-extra-masked-returns`. Severity is ORTHOGONAL to the 11 optional checks, and all 11
  are OFF by default. So we are running an adopted linter at roughly a third of its coverage on
  one file, and nobody chose that — a default did.
  No alternative shell linter is proposed and none should be. Adopting a second tool to obtain
  checks the adopted tool already ships behind a flag is the under-scoped-trial anti-pattern the
  registry catalogues at line 150.
  THE NOVEL SLICE: the disposition of the newly-visible findings, the advisory-to-blocking flip
  in `fleet/gate.sh` (a rig-specific control-flow repair no linter ships), and a fail-on-revert
  assertion that proves the gate BLOCKS rather than merely prints. The last of those is the part
  whose absence caused this exact work to be marked done once already without existing.
source: |
  fleet/state/PRIORITY-TODO.md section A, row A4 — "shellcheck -o all on the rig, 15 error-level
  findings invisible today". Verified live 2026-08-01: no `.shellcheckrc` exists anywhere in
  either checkout, and `fleet/gate.sh:81` invokes bare `shellcheck "${shell_scripts[@]}"` with
  no `-o` flags.
note: |
  ## PART ONE — THE 11 OPTIONAL CHECKS ARE ALL OFF

  shellcheck ships 11 optional checks that are OFF unless explicitly enabled. There is no
  `.shellcheckrc` in this repo, in the product repo, or anywhere above them. The rig is roughly
  60,000 lines of Bash running `set -euo pipefail` widely, and the check family most relevant to
  that idiom — `check-set-e-suppressed` / SC2310 / SC2311, "this function's failure is suppressed
  by the context it is called in" — is among the ones switched off.

  This is not hypothetical. On ONE file, `fleet/fleet-droid.sh`, the measured delta was 9
  findings at default versus 24 with `-o check-set-e-suppressed`, and 21 with
  `-o check-extra-masked-returns`. PRIORITY-TODO A4 measures 15 error-level findings across the
  rig that are invisible today.

  ## PART TWO — THE COMPANION DEFECT. A FAKE-DONE, AND IT IS THE MORE IMPORTANT HALF.

  READ THIS BEFORE TOUCHING ANYTHING. Enabling more checks on a gate that cannot fail is
  pointless, so this defect has to be fixed in the same ticket.

  `SHELLCHECK-BLOCKING` is marked DONE. It sits in `fleet/board/archive/SHELLCHECK-BLOCKING.md`
  AND has a completion marker at `fleet/state/done/SHELLCHECK-BLOCKING` recording
  `2026-07-23T02:02:53Z merged:0d43908a56e13e7089f88d2081fc7ac9632aeeff
  branch:feat/shellcheck-blocking`. Its stated job was to flip shellcheck from advisory to
  gate-blocking. Its `owns:` line was `fleet/gate.sh, fleet/tests/shellcheck-blocking.test.sh`.

  NEITHER DELIVERABLE EXISTS. Verified live 2026-08-01:

  - `fleet/gate.sh:115-118` still carries the comment block "ADVISORY ONLY … Flipping shellcheck
    to gate-blocking is tracked separately (clean fleet/*.sh first)".
  - `fleet/gate.sh:127` still prints
    `shellcheck: ADVISORY — findings above are non-blocking (shellcheck-clean tracked separately)`.
  - That branch NEVER increments `$FAIL`. The gate's exit code is driven entirely by the
    behavioural bash tests, so a shellcheck regression lands green — which is the precise
    condition the archived ticket claimed to have removed.
  - `fleet/tests/shellcheck-blocking.test.sh`, the other owned path, DOES NOT EXIST AT ALL.

  So a ticket was archived, marked merged with a SHA, and removed from the board while zero of
  its two owned artifacts were present. That is why "is it ticketed?" is the wrong question and
  "does it FIRE?" is the right one — and it is why this ticket's done-contract is written around
  observable gate BEHAVIOUR rather than around the presence of a config line.

  DO NOT REOPEN OR EDIT the archived ticket or its done marker. Those record what happened,
  honestly or not, and rewriting history is not the repair. Fix the code and land the assertion
  that makes the failure impossible to repeat.

  ## SCOPE

  1. Create `.shellcheckrc` at the rig root with the optional checks enabled (`enable=all`).
  2. Run shellcheck across `fleet/*.sh` with that config and enumerate the newly-visible
     findings, bucketed by SC code and by severity.
  3. Fix the error-level findings. Annotate genuine false positives with a SCOPED
     `# shellcheck disable=SCxxxx` carrying a one-line reason on the line above. The rig's
     embedded-python heredocs are the known source of these; a scoped per-site disable with a
     reason is acceptable, a file-level or repo-level blanket disable is not.
  4. FLIP `fleet/gate.sh` from advisory to BLOCKING: the shellcheck branch must increment `$FAIL`
     when shellcheck exits non-zero, so the gate's own exit code reflects it. Update the stale
     comment block at 115-118 and the stale message at 127 — leaving text that says
     "non-blocking" on a blocking gate is how the next reader gets misled.
  5. Add `fleet/tests/shellcheck-optional.test.sh` per the done-contract below.
  6. Do NOT touch `fleet/preflight.sh`. It has EIGHT live co-owners on the board and is not in
     this ticket's `owns:`.

  ## BURN DOWN OR BASELINE — BURN DOWN THE ERRORS, RATCHET THE REST, IN THAT ORDER

  This ticket BURNS DOWN at error level and RATCHETS below it.

  a. Every ERROR-level finding is FIXED or given a scoped disable with a written reason. The 15
     error-level findings are the reason the ticket exists; baselining them wholesale would
     deliver nothing.
  b. Warning/info/style findings from the newly-enabled checks may be ratcheted, but ONLY AFTER
     step (a). PRIORITY-TODO section D4 is explicit that a suppression baseline generated BEFORE
     known defects are fixed "freezes the bugs in permanently". Generating a rig-wide disable
     list first and fixing later would bury all 15 in the same file that makes CI green.
  c. Any ratchet admits NO NEW finding. Record the residue count per SC code — that is the
     visible debt.
  d. Do NOT achieve green by narrowing `enable=` back down. Removing a check to pass is the same
     failure as removing a rule from ruff's `select` to pass.

  ## DONE CONTRACT — RED THEN GREEN, EXTERNALLY RED-PROOFED

  Hermetic. The gate test must drive `fleet/gate.sh` against a THROWAWAY fixture directory
  (`FLEET_TESTS_DIR` is already overridable at gate.sh:19) so it never depends on the live rig
  being clean, and so it cannot fork-bomb — note `CHARON_GATE_ACTIVE` at gate.sh:29 and the
  documented 2026-07-15 fork-bomb incident before invoking the gate from a test.

  a. `.shellcheckrc` exists at the rig root with the optional checks enabled.
  b. THE ONE THAT MATTERS — ASSERT THE GATE BLOCKS, NOT THAT IT PRINTS. Feed `fleet/gate.sh` a
     fixture script carrying a known shellcheck ERROR and assert the gate's EXIT CODE is
     NON-ZERO and that `$FAIL` is reflected in the summary line. An assertion that greps stdout
     for a finding would pass TODAY, against the advisory gate — that is exactly the class of
     test whose absence let the fake-done through.
  c. FAIL-ON-REVERT, three independent reverts, three REDs:
     - restore the advisory branch (stop incrementing `$FAIL`) → RED;
     - delete `.shellcheckrc` → RED (the optional-check assertion below stops holding);
     - narrow `enable=` → RED.
  d. Assert an OPTIONAL check specifically fires: a fixture exercising an SC code that is silent
     at shellcheck's defaults (the SC2310 `set -e`-suppressed family is the natural choice) must
     be reported. This is what distinguishes "config file exists" from "the extra checks are
     actually running".
  e. A clean fixture still passes — the gate must not have become unconditionally red.
  f. The live `bash fleet/gate.sh` run is GREEN at the end, with the blocking branch in place.
  g. Report BOTH counts — green with everything intact, RED on each of the three reverts. A test
     that stays green with the flip removed is worthless; that is the whole lesson here.

## Dependencies & Sequence

- **depends_on: (none). IMMEDIATELY ELIGIBLE — claimable the moment it lands on the board.**
  Nothing blocks it and it blocks nothing. This is deliberate: the board's economy tier has been
  starving, and this ticket plus `GRAPHIFY-AFFECTED-WIRE` are the two in this batch with no
  inbound edges at all.
- **owns-collision: NONE, verified against the live board 2026-08-01.**
  - `fleet/gate.sh` — grepped `^owns:` across all live `fleet/board/*.md`: **zero** live owners.
    The archived `SHELLCHECK-BLOCKING` declared it, but an archived ticket is not a live owner.
  - `.shellcheckrc` — does not exist yet; no owner.
  - `fleet/tests/shellcheck-optional.test.sh` — new path, no owner. Named distinctly from the
    archived ticket's never-created `shellcheck-blocking.test.sh` so the two are not confused.
- **Explicitly NOT owning `fleet/preflight.sh`.** Eight live tickets already declare it
  (`PREFLIGHT-GATE-REGISTRY`, `PREFLIGHT-GATE-RUN-HELPER`, `MARKER-PROOF-MECHANIZE`,
  `RECONCILE-WIRING`, `REPO-MAP-CONVERGE`, `SYNC-SCHEDULE`, `GATE-INTEGRITY-C`,
  `WCI-DEC-FLEET-PREFLIGHT-SH`). Claiming it here would require eight merge-order edges and
  would starve a ticket whose entire purpose is to be immediately claimable. `fleet/gate.sh` is
  the correct and uncontended home: it is where shellcheck is already invoked.
- **Independent of the product `pyproject.toml` chain.** `RUFF-PREVIEW-ON` → `RUFF-ARG-C90-ON` →
  `MYPY-STRICTNESS-3-FLAGS` are all `repo: charon` and share no path with this ticket. This runs
  fully concurrently with all of them.
- **Sequence: NOW, and ahead of `GRAPHIFY-AFFECTED-WIRE` if only one lane is free.** It carries
  `priority: 0` because it is not only an enablement — it repairs a gate that has been reporting
  a guarantee it does not provide since 2026-07-23. Every rig PR merged in that window was
  shellcheck-ungated despite a green gate and a done ticket saying otherwise.
- **Relationship to the archived `SHELLCHECK-BLOCKING` — supersede in code, do NOT reopen.**
  That ticket's completion record stays as it is. Its unfinished work is folded in here.
- **Related, do NOT fold in:** the EVAL-REGISTRY shellcheck row (line 142) is already classified
  `mixed` with its correction written; it needs nothing from this ticket. The `set -e` tab-kill
  novel-slice conclusion recorded there is unaffected and must not be revisited here.
