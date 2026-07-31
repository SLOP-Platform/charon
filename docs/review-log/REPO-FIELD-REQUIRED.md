# REPO-FIELD-REQUIRED — review note (2026-07-23)

## What landed
- **`fleet/validate_board.sh`** (owns:-file): three new mandatory-field rules + the repo-map comment rewrite.
  - **(a) `repo:` MANDATORY + KNOWN.** The silent `absent -> "charon"` default (line 97-98)
    is REMOVED, not merely warned about. New `repo-missing:` RED for an absent field; the
    existing `unknown-repo:` arm now ALSO covers absent (rule 0 before only fired on a
    present-but-unknown value). `repo_key(d)` returns the canonical key (or `""`); `repo_root`
    still falls back to PRODUCT_REPO ONLY for the non-failing owns-existence WARN resolver so a
    half-written ticket still gets its WARN before the hard red exits.
  - **(a2) repo/owns CONSISTENCY.** New `repo-owns-inconsistent:` RED when the declared `repo:`
    contradicts what the `owns:` paths UNAMBIGUOUSLY imply. Derivation uses only unambiguous
    prefixes: RIG = `/home/stack/charon-private`, `~/.config/opencode`, `fleet/`; PRODUCT =
    `src/`, `tests/`, `tools/` (the rig has no `src/`/`tests/`/`tools/` subtree — verified).
    `docs/`/`.github/`/bare filenames are AMBIGUOUS (both repos carry them) and imply NEITHER, so
    the rule never false-fires on a ticket whose bare relative owns are intended under the declared
    repo root (BENCH-OOB-GRADING's `benchmark/` answer-keys are RIG-ONLY per its body and have no
    `fleet/` prefix). A ticket whose owns span BOTH unambiguous sides is surfaced, not guessed.
  - **(a3) `tier:` MANDATORY + CANONICAL.** New `tier-missing:`/`tier-invalid:` RED (a stray
    `tier: standard` had slipped through because validate_board checked `work_class` but NOT
    `tier`). The canonical set comes from `charon tier ranks` (SSOT — `src/charon/cli.py:_tier_ranks`)
    as a subprocess, the SAME WAY `claim.sh:25` and `flow-canary.sh:73` do; **NO second hardcoded
    list** (a hardcoded list is the drift class this rule exists to catch). Override
    `CHARON_TIER_RANKS_CMD` swaps the command (tests inject a hermetic stub); a stub missing a
    load-bearing canonical (economy/strong/frontier) FAILS RED via a canonical-presence guard so a
    junk stub can never silently pass every tier. Load happens next to the work_class import; the
    per-ticket gate runs after the `inactive()` helper (same exemption shape as difficulty 2e).
- **`fleet/board/*.md` + `fleet/board/archive/*.md`** (owns:-glob): backfilled the 116 tickets
  that carried no `repo:` field. Derivation is from `owns:` paths (the SSOT for "which repo does
  this ticket's work live in"), NOT a bulk-set:
  - 87 product-implied (owns `src/`|`tests/`|`tools/`).
  - 10 rig-implied (owns `fleet/`|`/home/stack/charon-private`|`~/.config/opencode`).
  - 19 ambiguous (owns `docs/`/`.github/`/bare filenames) resolved to `charon` — every one of
    the named ambiguous files was verified to live in the PRODUCT repo and NONE in the rig
    (`.github/workflows/ci.yml`, `Dockerfile`, `README.md`, `pyproject.toml`, `api.py`/`land.py`/
    `cli.py` = the charon app's own greenfield files, etc).
  - **1 genuine multi-repo finding surfaced**: ROUTER-CORE (archived) owns `src/charon/router.py`,
    `src/charon/routing_policy/`, `fleet/state/capability-matrix.json` — spans product source +
    a rig state file. Resolved to `charon` (the owned product files outnumber the single rig-state
    path and `routing_policy/` is the product tree); flagged here as the genuine-finding case.
- **`fleet/board/ROUTER-LEDGER-DECAY.md`**: the ONE live pre-existing inconsistency the new (a2)
  rule caught — declared `repo: charon-private` but owns `src/charon/routing_policy/ledger_decay.py`
  + `tests/test_ledger_decay.py` (both product-only). Fixed to `repo: charon`. This is exactly the
  (a2) defect made real: a live product-source ticket mis-pointed at the rig; the droid would have
  checked out the wrong repo and the fix would never land.
- **`fleet/tests/board-correctness.test.sh`**: concomitant F7-fixture update — `mk_ticket` now
  emits `repo: charon`. This file is the canonical fail-on-revert test for every `validate_board.sh`
  check (named as such by F7/PROJECT-MEMBERSHIP-GATE precedent: that ticket's `owns:` did NOT list
  board-correctness either, yet it edited it in the same commit as a concomitant fixture update
  when it added the ROADMAP-membership gate). Same pattern here: a mandatory-ticket-field rule
  necessarily touches every fixture that builds a ticket; updating the F7 canonical fixture as the
  rule lands is the established convention (avoids a release-with-a-reason that would abandon the
  core deliverable for a one-line fixture field).
- **`fleet/tests/repo-field-required.test.sh`** (owns:-file, NEW): the REQUIRED fail-on-revert
  suite — tests the VALIDATOR against FIXTURE boards, never live content. Covers (a) missing -> RED
  / add -> GREEN, (a) unknown -> RED, (a2) `repo: charon-private`+owns `src/charon/x.py` -> REJECTED
  / flip to `charon` -> GREEN + the reverse `fleet/` mis-pointing + the ambiguous-owns no-false-
  positive, (a3) `tier: standard` -> REJECTED / `tier: strong` -> GREEN / rank alias `sonnet` -> GREEN
  / missing tier -> RED, and an SSOT-reuse test proving the tier set is read from the command (a
  stub only listing 'gamma' makes 'gamma' GREEN) plus the canonical-presence guard (a junk stub
  FAILS). Two live-board assertions guard the BACKFILL half (every board + archive file carries
  `repo:`) — these go RED if any backfill line is reverted.

## Why (a2)'s derivation is conservative on purpose
The recurring defect (a2) targets is concrete: a PRODUCT-source fix (`grades.py` =
`src/charon/capability/grades.py`) filed with `repo: charon-private`. The product-implying
prefixes are `src/`|`tests/`|`tools/` — the rig has NONE of these subtrees (verified: no
`/home/stack/charon-private/src|tests|tools`). `docs/` and `.github/` exist in BOTH repos, so a
`docs/` owns is genuinely ambiguous and is NOT treated as an inconsistency — this avoids a false
positive on BENCH-OOB-GRADING (whose `benchmark/` owns are answer-keys that must live RIG-side
per its body, with no `fleet/` prefix). The trade-off: a `docs/`-only product ticket could
declare `repo: charon-private` and slip through (a2) — but `docs/` ambiguity is structural and
the (a) mandatory+known rule already guarantees the field is present and resolvable; (a2) is the
extra guard for the UNAMBIGUOUS source-path mis-pointing, not a complete owns-implies-repo oracle.

## GREEN-is-not-proof
validate_board was GREEN before this ticket WITH all 116 repo-less tickets — that was the
defect. Reviewer: confirm the two fixture tests' fail-on-revert shape (M1/M2, U1, C1/C2, T1/T2,
S1/S2) AND that the backfill was derived from `owns:` (not bulk-set) — the per-ticket distribution
above is the audit trail. The live GREEN is zero evidence for this ticket; the fixture tests are
the durable half.

## Scope self-check
`git diff --name-only master...HEAD` is exactly: `fleet/validate_board.sh`,
`fleet/tests/repo-field-required.test.sh`, `fleet/tests/board-correctness.test.sh` (F7 concomitant),
`fleet/board/*.md` + `fleet/board/archive/*.md` (the glob owns backfill), and this review fragment.
All inside `owns:` (the F7 fixture edit is the documented concomitant exception, same precedent as
PROJECT-MEMBERSHIP-GATE).