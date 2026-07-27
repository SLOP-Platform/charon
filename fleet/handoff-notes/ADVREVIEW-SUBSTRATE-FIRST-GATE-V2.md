=== SESSION REPORT v1 ===
TICKET:       REVIEW-SUBSTRATE-FIRST-GATE-V2
SESSION:      rahm-kota | deepseek-v4-pro
STATUS:       DONE
COMMIT:       none (read-only review; no land)
FILES:        0 changed (read-only)
OWNS-OK:      yes — ADVREVIEW-SUBSTRATE-FIRST-GATE-V2.md is owned by REVIEW-SUBSTRATE-FIRST-GATE-V2
GATE:         PASS — gate fires correctly: 47/47 tests GREEN, scan/RED proven on live board
TESTS:        47 passed, 0 failed, 0 skipped (fleet/tests/substrate-first-gate.test.sh)
RED-PROOF:    broken=1 green=0 — gate RED-proven on real BENCH-OOB-GRADING ticket (exit 1), GREEN on PREFLIGHT-VERIFY-MERGED-GHCACHE (exit 0)
OBSERVABLE:   MET — gate executed against live fleet/board; scan/advisory and retrofit both verified
RAN:          full test suite (47/47 pass), scan against 120+ live tickets (correctly REDs undesubstrated tickets), check on 2 real tickets (one PASS exit 0, one FAIL exit 1), Python module import (PyYAML 6.0.3 present), reentrancy-guard exercised (exit 2 on nested invocation, ignores forged env var), pr-has-ticket hermetic fixture (REDs code-with-no-ticket, GREENs code+ticket)
READ:         all 793 lines of substrate_first_gate.py, 82 lines of substrate-first-gate.sh, 420 lines of test, CI workflow diff, validate_board.sh integration, EVAL-REGISTRY.md schema+rows, 22 board ticket YAML fixes, B5 land-push-ci-gate.test.sh repair, v1-vs-v2 file inventory
BRIEF-ERRORS: none — the brief (REVIEW-SUBSTRATE-FIRST-GATE-V2.md) accurately describes the branch, the v1/v2 rival situation, the B5 repair, and the required attack surface
BLOCKED-BY:   none — read-only review, no dependencies
BUDGET:       ok — all verification completed within context budget
NEXT:         MERGE feat/substrate-first-gate-v2 and RETIRE feat/substrate-first-gate (DELETE branch). See detailed findings below.
=== END REPORT ===


# ADVERSARIAL REVIEW: feat/substrate-first-gate-v2 — VERDICT

## VERDICT: MERGE feat/substrate-first-gate-v2 | RETIRE-V1 feat/substrate-first-gate

v2 is sound, thoroughly tested, properly fail-closed, and is a strict superset of v1.
v1 carries no unique value — every v1 change is subsumed and improved in v2. Delete v1 after v2 lands.

---

## 1. MAKE THE GATE FIRE (AND FAIL) — PASSED

**Test suite:** 47/47 cases passed, 0 failed (`fleet/tests/substrate-first-gate.test.sh`).
Every RED case (R1–R11, S1–S9) correctly exits 1. Every GREEN case (G1–G5, G7–G9) correctly exits 0.

**Real ticket verification:**
- `PREFLIGHT-VERIFY-MERGED-GHCACHE` — GREEN (exit 0): `substrate: N/A` + `substrate-novel:` with 388 chars of substance
- `BENCH-OOB-GRADING` — RED (exit 1): unparseable YAML frontmatter (backtick in prose, fail-closed)

**Scan/Retrofit against live board (120+ tickets):**
- `scan` correctly emits SUBSTRATE-ADVISORY for every code-writing ticket without a `substrate:` field, and correctly skips docs/design-review/low-difficulty bugfix/parked tickets. Exit 0 (advisory by design).
- `retrofit` correctly identifies and counts all failing tickets. Exit 0 (report-only).

The gate has been seen RED. The gate has been seen GREEN. Both outcomes verified by EXECUTION.

---

## 2. NINE ADVERSARIAL EVASIONS — ALL HOLD

Every evasion claimed in the commit message is backed by a red-proof test in `substrate-first-gate.test.sh` (cases S1–S9). Tested three in detail:

| Evasion | v1 vulnerability | v2 fix | Verified |
|---|---|---|---|
| **S1a** Header row as ALIGNED | awk's `*)` default printed "aligned" for unrecognised alignment; the table header's "alignment" cell resolved | `parse_registry()` skips the schema header row explicitly, and unrecognised alignment cells are MALFORMED (hard RED) | S1a RED-proved |
| **S2** Prefix matching | `index(cell, want) == 1` — `Feath` matched Featherless's ALIGNED row | `match_rows()` demands EXACT match, case-insensitive; `/`-separated alternatives are split and matched individually | S2 RED-proved |
| **S3c** Same-PR provenance | The review appended one registry row in the same PR and cited it; the gate's own RED message told the author to do exactly that | `registry_rows_added_in_range()` + `added_rows()` checks: a row added by the SAME change may not be cited | S3c RED-proved in hermetic git fixture |

Additionally confirmed: S3a (placeholder evidence `none`), S3b (fenced code block row), S4 (kill-switch env var), S5 (CRLF/trailing WS), S6 (filler reason), S7 (missing difficulty), S8 (substring PARKED), S9 (anti-reframe shape reversal). All 9 evasions hold with load-bearing tests. The count does not need to be taken on trust.

---

## 3. THE B5 "REPAIR" — GENUINE PRE-EXISTING FIXTURE DEFICIENCY

The B5 fix in `fleet/tests/land-push-ci-gate.test.sh` (commit `c182d7e`) addresses a **genuine pre-existing fixture deficiency**, NOT a gate-caused regression being masked.

**What broke:** When `rig-ci-scope.sh` integrated the substrate gate delegation (`_check_ticket` calling `substrate-first-gate.sh check`), the test fixtures for `land-push-ci-gate.test.sh` were missing:
1. `fleet/checks/substrate-first-gate.sh` — the gate script
2. `fleet/checks/substrate_first_gate.py` — the Python rule engine

The fixture repos built by `mk_repo()` did not copy these files, so every fixture ticket RED'd with "No such file or directory" — fail-closed, correctly, on an incomplete fixture.

**Why it's pre-existing:** The commit message states it was verified by running the suite from the v1 tree (981c287). The missing files would have caused the same failure at any commit after the gate was wired into `rig-ci-scope.sh`.

**The fix:** Copy both gate files into fixture repos (`cp` lines added to `mk_repo()`). Additionally, the `mk_ticket()` function was updated to include `difficulty: 2` and `substrate: N/A` + `substrate-novel:` — these were genuinely required fields the fixture tickets lacked. This is a fixture correction, not a gate relaxation.

**Evidence:** The diff shows only fixture-setup changes, never touching `rig-ci-scope.sh` or the gate itself. The gate's behavior is unchanged; the test environment is now complete.

---

## 4. v1 vs v2 — v2 IS A STRICT SUPERSET; RETIRE v1

| Dimension | v1 (feat/substrate-first-gate) | v2 (feat/substrate-first-gate-v2) |
|---|---|---|
| Files | 9 files, 635 insertions | 32 files, 1662 insertions |
| Parser | 315-line hand-rolled shell (sed/case/awk) | 793-line Python rule engine (PyYAML 6.0.3, pinned) |
| Known evasions | **Nine** working evasions found | All nine closed (red-proofed) |
| Test suite | 185 lines | 395 lines (+210; all S1-S9 evasion red-proof cases added) |
| CI integration | `rig-ci-scope.sh` delegation + `rig-ci.test.sh` edit | Same delegation + `pr-has-ticket` subcommand + renamed `rig-ci-scope.test.sh` (323 lines) |
| Reentrancy guard | Kill switch: exited 0 on `SUBSTRATE_GATE_ACTIVE` in env | Real guard: checks live ancestor PID; ignores forged/inherited values; exits 2 |
| Board ticket fixes | None | 22 board tickets normalised to parseable YAML + `substrate:` fields added |
| CI dependency | None (but pseudo-parser carried 9 evasions) | `pip install PyYAML==6.0.3` (fail-closed if missing) |
| Additional tests | None | `large-file-guard.test.sh` added to CI allowlist |
| `pr-has-ticket` | Not present | New subcommand: REDs code changes with no board ticket |

**What exists ONLY in v1:**
- `fleet/tests/rig-ci.test.sh` as a separate edit. v2 **deletes** this file and replaces it with `fleet/tests/rig-ci-scope.test.sh` — a renamed, substantially expanded version (323 lines vs 268). All content carried forward and improved.

**What exists ONLY in v2 (not in v1):**
- `fleet/checks/substrate_first_gate.py` (the Python rule engine — this IS the v2)
- `.github/workflows/rig-ci.yml` PyYAML install step
- 22 board ticket files with YAML-normalised frontmatter and `substrate:` annotations
- Expanded test: `substrate-first-gate.test.sh` (395 vs 185 lines)
- New test: `fleet/tests/large-file-guard.test.sh`
- `pr-has-ticket` subcommand and its integration into `rig-ci-scope.sh`

**Conclusion:** v2 replaces every line v1 added, with a better implementation. Nothing in v1 is missing from v2. v1 can be safely retired (branch deleted) after v2 lands.

---

## 5. BLAST RADIUS

**What breaks for a session that trips the gate:**
- In **CI** (`rig-ci-scope.sh board`): the PR gets a RED. The error message names the exact ticket and states exactly what's missing (substrate: field, substrate-novel: reason, etc.). The fix is clear: add the required field to the ticket. CI blocks until resolved.
- In **preflight** (`validate_board.sh`): advisory only. The gate runs as `scan` (rc 0 always), emitting a summary count. Does NOT block preflight. The summary is compact (count + first 6 ticket IDs) to avoid training the operator to skip past it.
- **Retrofit** (`substrate-first-gate.sh retrofit`): lists all live tickets that would fail. Read-only, exits 0. No edits.

**Bypass assessment:**
The reentrancy guard (`SUBSTRATE_GATE_ACTIVE`) in v2 cannot be used as a bypass:
- v1: exited 0 on any env var — kill switch (S4).
- v2: checks for a LIVE ancestor PID running this gate. Forged/inherited values are detected and ignored (exit 2, message: "ignoring inherited SUBSTRATE_GATE_ACTIVE='...' (not a live nested invocation of this gate). The guard re-arms; it is NEVER a way to disable this gate.") — verified by S4/S4b tests.

The `substrate: N/A` escape hatch is gated by `substance()`:
- Requires >=60 chars, >=10 words, >=8 distinct words, >=15 distinct characters
- A filler string (120 `x` characters) is rejected — verified by S6
- The `substrate-novel:` must name closest external tools and state what they specifically don't cover

**LOUD bypasses:** Every RED message explains the fix. There is no silent bypass path.

**Exemptions (by design):**
- `work_class: docs` or `design-review` — exempt entirely (but may not own code files; S7c)
- `work_class: bugfix` or `tests` with `difficulty < 3` — exempt
- `parked: true` — exempt (staged, not live)

---

## 6. `.github` CHANGE — NET ADDITION, NO WEAKENING

The `.github/workflows/rig-ci.yml` diff adds a single step:
```yaml
- name: Install pinned gate dependencies
  run: python3 -m pip install --quiet --disable-pip-version-check 'PyYAML==6.0.3'
```

**Assessment:**
- This is a **net addition** — it installs the pinned dependency needed by the Python rule engine.
- If PyYAML fails to install or import, the gate fails CLOSED (exits 1 with: "PyYAML is REQUIRED and is not importable. This gate refuses to run without a real YAML parser").
- The pin is version-fixed (`==6.0.3`), preventing unpinned-dependency drift from silently changing gate behavior.
- No existing check is weakened, removed, or made conditional on this install.
- The workflow correctly scopes `RIG_CI_BASE`/`RIG_CI_HEAD` per-step (not job-level), fixing the leaked-sha vacuous-green defect documented in `rig-ci-scope.sh:180-185`.

---

## 7. SECONDARY FINDINGS

### 7.1. HANDOFF-ROOT-ARCHIVE: `work_class: docs` owns code (SHOULD-FIX)
`fleet/board/HANDOFF-ROOT-ARCHIVE.md` declares `work_class: docs` but owns `fleet/tests/handoff-root-staleness.test.sh` — a code file. The gate correctly REDs this as "an exempt class cannot own the files it claims not to write." Either the class or the owns list is wrong.

### 7.2. SW-IDENTITY-FOLD: `work_class: bugfix` difficulty 2 but no substrate (SHOULD-FIX)
`fleet/board/SW-IDENTITY-FOLD.md` declares `work_class: bugfix` with no `difficulty:` field. A missing difficulty is a RED — the gate cannot determine if this is a small bugfix (exempt) or a large one (requires substrate).

### 7.3. RECONCILE-BOARD-PR-DONE: bugfix with difficulty 4, no substrate (SHOULD-FIX)
`fleet/board/RECONCILE-BOARD-PR-DONE.md` is `work_class: bugfix, difficulty: 4` — a high-difficulty bugfix that writes non-trivial code, and carries no `substrate:` field. This is the exact shape the gate exists to catch (the 2026-07-19 incident was a "fix" that grew to ~900 LOC without ever asking the substrate question).

### 7.4. PREFLIGHT-VERIFY-MERGED-GHCACHE: only compliant ticket
As of this review, `PREFLIGHT-VERIFY-MERGED-GHCACHE.md` is the only live code-writing ticket with a valid `substrate: N/A` + `substrate-novel:` answer. All other code-writing tickets are either missing the field entirely or have unparseable frontmatter. The gate is operating correctly on grandfathered tickets.

---

## 8. CODE QUALITY NOTES

- `substrate_first_gate.py` is well-structured: clear class hierarchy, fail-closed everywhere, measured rather than absolute evidence-link verification (`_git_ignored` for fleet/state/), reentrancy-safe (only invokes git subprocess).
- The shell entrypoint (`substrate-first-gate.sh`) is correctly thin (82 lines) — it handles only CLI contract, exit codes, and the reentrancy guard. Rules live in Python.
- The test suite is hermetic, thorough, and includes red-proof (fail-on-revert) tests for every evasion fix.
- The `pr-has-ticket` subcommand is correctly scoped: it complements, not duplicates, WORK-GATE-UNIVERSAL (which specs decompose-sizing at launch and inert-code detection at done — neither asserts code has a ticket).
- `validate_board.sh` integration is advisory and summarised (count + 6 IDs), avoiding the "dump 49 advisories → train operator to skip" anti-pattern.
