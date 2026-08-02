repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: fix/ticket-check-scope-semantic
owns: fleet/checks/rig-ci-scope.sh, fleet/tests/ticket-check-scope.test.sh
serial_justified: |
  One scoping predicate in one function plus its fail-on-revert suite. Splitting them would land
  a scope change with no proof it still fires on real changes — the exact shape that turns a
  narrowing into a loosening.
substrate: |
  N/A — no external tool models THIS rig's ticket schema, its `_field` line reader, or its
  grandfathering policy. The comparison deliberately reuses the gate's OWN `_field` reader rather
  than introducing a second one (a YAML differ, dyff/yq, would answer a different question: it
  compares documents, while the invariant needed here is "the inputs the CHECKS read did not
  change" — and half the tickets in scope do not parse as YAML at the base ref at all, which is
  precisely why they are being repaired).
substrate-novel: |
  The novel slice is the POLICY, not the diffing: deciding WHICH fields a substrate verdict
  depends on, and that `owns:` compares as a normalised SET while D&S presence compares as a
  one-way RATCHET. No library can supply that; it is this rig's rule.
substrate-retest: |
  Not needed — nothing is adopted and no new dependency is introduced. The only external tool in
  the loop is git (already the gate's sole subprocess).
note: |
  MEASURED 2026-08-01. `rig-ci-scope.sh` substrate-checked every ticket PRESENT IN THE DIFF. That
  conflates two different things:
    (1) this ticket's WORK changed     -> it must justify substrate, D&S, owns-format;
    (2) this ticket's FILE was touched -> may be a pure syntax/format repair.
  Under (2), a meaning-preserving YAML fix re-opens years of accumulated debt on unrelated
  tickets. Concretely: repairing the 23 tickets whose frontmatter did not parse (the fail-open in
  substrate_first_gate.base_board_owns, PR #365) put them in a diff for the FIRST TIME since they
  were written, and 21 pre-existing REDs fired — 13 of them "no 'substrate:' field". The gate made
  the repair of a gate defect UNLANDABLE, and it also blocked the 6-ticket fix that keeps
  fleet/tests/priority-validator.test.sh RED on every PR. That is the
  [[gate-hardening-strands-open-branches]] class, and it is exactly how `--force` habits start.

  THE RULE: a ticket ALREADY PRESENT on the base ref keeps its grandfathered status when none of
  the fields the verdict DEPENDS ON changed. If every input to a check is identical, the check can
  only reach the identical verdict — so re-running it discovers nothing and blocks work that
  changed nothing.

  THIS NARROWS WHEN THE CHECK FIRES. IT DOES NOT LOOSEN WHAT IT CHECKS. Nothing moves to the
  "pass" side: a grandfathered ticket is SKIPPED and narrated, never asserted green. Still fully
  checked, exactly as today: a NEW ticket; any change to work_class / repo / branch / difficulty /
  substrate / substrate-novel / substrate-retest / parked; any change to the SET of `owns:` paths;
  and LOSING a D&S section (a one-way ratchet — gaining one can never make a verdict worse).

  COMPARISON IS SEMANTIC, NOT BYTES. Values come from `_field`, the SAME line reader the checks
  themselves consume, so "the inputs did not change" is literally true of the checks that run.
  `owns:` compares as a normalised SET of repo-relative paths, so a reorder — or rewriting an
  ABSOLUTE dev-box path to its repo-relative form — denotes the same owned files and stays
  grandfathered. An absolute entry is malformed by this gate's OWN owns-format rule, so correcting
  one must not re-open the ticket's unrelated debt: that would be this very defect one level down.
  Normalisation is narrow and fail-closed — leading components are dropped until the remainder
  EXISTS in the repo; an absolute path that resolves NOWHERE here is left alone, compares as
  different, and the ticket is CHECKED. Byte comparison was rejected: it IS the rule that already
  failed.

  EVIDENCE THE RULE IS SOUND FOR THE DIFF THAT MOTIVATED IT: across all 23 repaired tickets the
  line-based readers' view of repo/branch/owns/base/depends_on is BYTE-IDENTICAL before and after.
accept: |
  - `bash fleet/tests/ticket-check-scope.test.sh` — 10/10 green.
  - FAIL-ON-REVERT (`SCOPE_REVERT=1`, the pre-fix "check everything in the diff" rule restored):
    4 assertions FAIL — a pure formatting repair re-opens pre-existing debt (a1), the skip is no
    longer narrated (a2), and an absolute->repo-relative owns rewrite re-opens debt (f, h).
  - THE ANTI-LOOSENING CASES, which must pass in BOTH modes: adding a path to `owns:` still REDs
    (b); changing `work_class` still REDs (c); a NEW ticket is never grandfathered (d); losing a
    D&S section still REDs (e); an unresolvable base still REFUSES outright (g); and an owns path
    that resolves NOWHERE in the repo is treated as a REAL change, never normalised away (i).
  - `shellcheck -S error` clean; `bash -n` clean.

## Dependencies & Sequence

- **depends_on: (none) to build.**
- **Sequence:** land FIRST, then `BOARD-FRONTMATTER-REPAIR-23`, then the 6 priority fixes ride in
  behind it. `GATE-OWNERSHIP-FAILOPEN` (PR #365) is orthogonal and can land in any order — its
  own ordering property is the mirror image of this one (an unparseable ticket can only ADD
  ownership, so it can only change a NEGATIVE verdict).
- **owns-collision — FLAGGED, NOT RESOLVED BY ME.** `fleet/checks/rig-ci-scope.sh` is owned by TWO
  live tickets: `HANDOFF-GATE-NONBYPASSABLE` (with `fleet/land.sh`) and `REVIEWER-TAB-POOL` (which
  has an open worktree on `feat/reviewer-tab-pool`). This change is deliberately surgical — one
  new predicate plus a four-line guard in `cmd_board`, touching neither the land path nor the
  review-pool wiring — but it IS a third writer and the operator should sequence it against those
  two rather than let it merge blind.
- **Deliberate deviation, flagged not hidden:** `set -uo pipefail` kept (not `-e`) — the file
  returns documented exit codes and `-e` would break that contract.
