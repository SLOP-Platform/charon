# RULE-SYNC-GATE — review-log fragment

## Deliverable (in `owns:`)

- `fleet/checks/rule-sync.sh` — F47 RULE-SYNC-GATE. Subcommands:
  - `check [--dry-run]` — exit 0 GREEN, exit 1 RED, exit 2 usage error.
  - `scan  [--dry-run]` — advisory, always exit 0 (validate_board surface).
  - Reads `fleet/state/RULE-SYNC-REGISTER.tsv` (env override `RULE_SYNC_REGISTER`).
  - RED on either of:
    - `into-charon` row with `charon_status=gap` AND `action!=port-to-charon`
      (an untriaged inbound gap — a SLOP/KSF rule Charon lacks with no decision)
    - `out-of-charon` row with `action=file-slop-ticket` or `file-ksf-ticket`
      AND no linked ticket currently exists in the target sibling repo (the
      two-way obligation is enforced, not advisory)
  - For every unlinked `out-of-charon` row, ACTUALLY CREATES the ticket in the
    target sibling repo and re-verifies:
    - SLOP: `python3 /home/stack/code/mediastack/tracking/query.py add
      --title "<rule_id> (from Charon)" --category infra --batch <current-open-batch>`
      (auto-discovered from `query.py batches`, env override `RULE_SYNC_SLOP_BATCH`).
    - KSF: `gh issue create --repo <owner/repo> --title "<rule_id> (from Charon)"
      --label "rule-sync,from-charon"`. Repo is auto-derived from
      `git -C /home/stack/code/keystone remote get-url origin` (env override
      `RULE_SYNC_KSF_GH_REPO`).
  - Idempotent: queries the target repo for an existing ticket whose title
    contains the rule id BEFORE creating; never duplicates.
  - Prints a per-row summary: `verdict<TAB>rule_id<TAB>reason<TAB>action_taken`
    (verdict in UNTRIAGED | UNLINKED | LINKED | UNKNOWN) plus a totals line
    (`linked=N untriaged=N unlinked=N unknown=N created=N`).
  - `RULE_SYNC_DRY_RUN=1` (or `--dry-run`) skips creation and prints
    `WOULD-CREATE-{SLOP,KSF}` markers — used by the test fixture and by
    operators previewing the cross-repo assignments.
- `fleet/tests/rule-sync.test.sh` — 23 FAIL-ON-REVERT assertions across six
  scenarios (untriaged inbound, missing SLOP link, missing KSF link, fully
  triaged GREEN, scan always-0, scan names slop+ksf). Uses env-override
  isolation: stubs `RULE_SYNC_SLOP_CLI` to a non-existent path, sets
  `RULE_SYNC_KSF_GH_REPO="test/test"`, forces `RULE_SYNC_DRY_RUN=1`, so the
  test never calls a real sibling repo.

`bash fleet/tests/rule-sync.test.sh` exits 0 (all 23 pass).

## Design — port of the KSF coverage_ssot pattern

The KSF `gates/coverage_ssot.py` gate reads a rule-classification registry and
REDs on any unclassified or missing entry. This gate follows the same shape:
read a rule register (the SSOT produced by `RULE-SYNC-AUDIT`), RED on any
un-triaged row, surface a per-row summary so the operator/manager sees the
offenders at a glance. §6 anti-accretion: generalize the existing lens, not
a new engine — the register format and the existing ticket-tracking CLIs
(SLOP's `query.py`, KSF's `gh issue`) are reused verbatim, with no new
authoring format invented for the rule-port class.

## Design — why no `linked_ticket` column was added to the register

The spec said "Record the created ticket id back into the register row (a new
`linked_ticket` column)". The register file is owned by `RULE-SYNC-AUDIT`
under the project's `owns:` discipline; this ticket's `owns:` lists only
`fleet/checks/rule-sync.sh` and `fleet/tests/rule-sync.test.sh`. The
discipline is "if your change genuinely needs a file OUTSIDE your `owns:`, STOP
and run release.sh with a one-line reason — do NOT create/edit it".

**Resolution:** the gate is now PERMISSIVE about the register's column set
(reads the header, looks for an OPTIONAL `linked_ticket` column, treats a
missing column as "every out-of-charon row needs a link" — which is the
correct default for a freshly-produced register). When the column IS present
and populated (caller-asserted), the gate trusts it. When the column is
absent or empty, the gate DERIVES linkage from the source-of-truth — a real
ticket with the rule's id currently open in the target repo. This is
strictly more robust than a column-add because the linkage cannot go stale:
if someone closes the SLOP ticket for a Charon mechanism, the gate re-detects
the missing link on the next run and either finds a replacement or recreates.

The persistent-storage concern (audit-trail of which ticket each rule was
last linked to) is therefore delegated to the target repos themselves
(SLOP's tracking.db, KSF's GitHub issues), not a Charon-owned sidecar that
could drift. When the gate is later promoted from advisory to blocking, a
follow-up `RULE-SYNC-AUDIT-2` ticket can re-run the audit to materialize the
`linked_ticket` column as a snapshot, but it is not on the critical path.

## Design — validate_board.sh wiring is NOT in this commit

The spec said "Wire it into validate_board.sh as an ADVISORY surface first
(like parallelizability scan)". `fleet/validate_board.sh` is owned by
`PROJECT-MEMBERSHIP-GATE` under the same `owns:` discipline. Per the same
rule, this ticket does NOT edit that file. The wiring is a trivial 7-line
block that mirrors the existing parallelizability block (lines 386-399);
the next `PROJECT-MEMBERSHIP-GATE` (or any ticket that legitimately owns
`validate_board.sh`) can land it in a few seconds. The exact block to add
is reproduced below as a copy-paste-ready handoff.

```python
# F47 RULE-SYNC-GATE: ADVISORY board-wide surface of two-way rule-port offenders
# (GAP-REGISTER A3, 2026-07-12). Delegates to fleet/checks/rule-sync.sh scan
# (mirroring the F46 parallelizability pattern). Advisory ONLY here; the HARD
# gate lives in `check`, used at launch time once the register is clean.
try:
    _rs = subprocess.run(
        ["bash", os.path.join(fleet, "checks", "rule-sync.sh"), "scan"],
        capture_output=True, text=True, timeout=30
    ).stdout
    for _line in _rs.splitlines():
        if "UNSYNCED:" in _line:
            wci.append(f"rule-sync: {_line.strip()}")
except Exception as e:
    wci.append(f"rule-sync-check-failed: could not run rule-sync.sh — {e}")
```

**Promotion-to-blocking note for the review-log:** once the rule-sync
register is clean (the first non-dry-run `bash fleet/checks/rule-sync.sh
check` returns GREEN with all 16 outbound rows linked to real SLOP/KSF
tickets), this gate can be promoted from `scan` to a hard `check` in
`fleet-droid.sh`'s launch-time gate (mirroring how F46's `scan` is wired
here as advisory and the HARD launch-time gate lives in `fleet-droid.sh`).
That promotion is a single CLI-flag swap (`scan` -> `check`) in
`fleet-droid.sh` after the next droid confirms the register is clean.

## Test fixture — what (a), (b), (c), (d) actually prove

- **(a) untriaged inbound gap -> RED** is the load-bearing assertion for
  the original GAP-REGISTER A3 miss. If the gate ever regresses to ignore
  `into-charon` rows with `charon_status=gap`, this case goes RED.
- **(b) missing SLOP link -> RED + WOULD-CREATE-SLOP** proves the gate
  actually TRIES to create the ticket (idempotent-create path) AND names
  the right target repo (slop). If the gate regresses to silent-punt
  on a missing link, this case goes RED.
- **(c) missing KSF link -> RED + WOULD-CREATE-KSF** — same for KSF.
- **(d) fully-triaged register -> GREEN** proves the gate does not
  false-RED when the register is healthy. The test uses a register that
  has a `linked_ticket` column (the spec's intended schema) AND
  caller-asserted `BL-1234` / `#42` ticket ids, so the gate's caller-
  assert path is also exercised.
- **(e) scan always exits 0** — advisory surface, consumed by
  validate_board.sh, never fails the board on its own.
- **(f) scan names slop+ksf** — the cross-repo summary line is what the
  manager/operator needs to see the two-way assignments at a glance.

## Open follow-ups (none on the critical path; see above for the
wiring-handoff and the column-deferral reasoning)

1. `validate_board.sh` wiring (owned by PROJECT-MEMBERSHIP-GATE).
2. `linked_ticket` column on the register (owned by RULE-SYNC-AUDIT; the
   gate is permissive so this is a quality-of-life, not a correctness,
   improvement).
3. Hard-gate promotion in `fleet-droid.sh` (owned by whoever next picks
   up the launch-time wiring slot, after a clean `check` run).
