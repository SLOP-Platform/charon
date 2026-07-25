# SG-ISSUE-CONTROL-PLANE implementation ticketing — STATUS / RESUME NOTE

Session: agen-kolar · 2026-07-24 · **stopped on coordinator budget-exhaustion before any file was
written to `fleet/board/`.** Nothing was created, nothing was half-written, the board is exactly as
it was found. This note is the complete spec so the next session TRANSCRIBES rather than re-derives.

---

## 0. STATE OF THE BOARD — read this before anything

**TICKETS CREATED THIS SESSION: NONE.** Analysis complete, transcription not started.

`bash fleet/validate_board.sh` → **rc=1, PRE-EXISTING, NOT FROM THIS SESSION** (this session wrote
nothing tracked, so it cannot be). Run TWICE, ~40 min apart, and the board moved under me between runs
because other lanes were committing concurrently:

- **First run (master `4e1715f`): rc=1, 10 issues** — (a) the `fleet/preflight.sh` owns-collision
  below, and (b) `gate-parity: BOARD-WRITE-LOCK would be refused at launch — SPLITTABLE (difficulty=3,
  3 owned surfaces)`. At that moment `fleet/board/BOARD-WRITE-LOCK.md` was UNTRACKED (`??`) — another
  lane's uncommitted WIP in the shared main checkout. I deliberately did NOT touch it: editing or
  committing another lane's untracked file is the `--commit-dirty` sweep class.
- **Second run: rc=1, ONE issue.** That lane landed BOARD-WRITE-LOCK with its `serial_justified:` in
  the interim, so (b) is gone. **The single remaining RED is:**

```
RED owns-collision LIVE (no dep ordering): fleet/preflight.sh <- MARKER-PROOF-MECHANIZE
    PREFLIGHT-GATE-RUN-HELPER RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE
```

Five live owners of the rig's most contended file with no `depends_on` ordering between them.
Longstanding, and the fix is a sequencing decision across FIVE other lanes' tickets — out of scope
for a ticketing session and collision-prone to attempt unilaterally.

**Consequence for the next session: rc=0 is NOT reachable without ordering those five tickets.**
Treat rc=1 / 1 issue as the baseline, and prove your own additions contribute ZERO new issues by
diffing the full issue list before and after. **This also matters for T4** (§2 below), which must
anchor into `preflight.sh` — it must NOT become the sixth concurrent owner.

---

## 1. THE GAP, RE-STATED FROM EVIDENCE

`SG-ISSUE-CONTROL-PLANE` (P0, `feat/sg-issue-control-plane` @ `b9d314b`) is design-only: 3 files,
466 insertions, no executable line anywhere. Its design of record is
`fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md` (403 lines, on that branch only — **not on master**).

**What ALREADY has tickets (verified on master — do NOT re-create these):**

| slice | ticket | pri | state |
|---|---|---|---|
| SURFACE (§6 step 2) | `ISSUE-BOARD-SURFACE` | 1 | **already re-scoped 2026-07-24** — `owns:` no longer names `fleet/state/issue-board.tsv`; carries an explicit anti-fork `bar:`. **Design §8's B1 is DONE**, so §6 step 2's BAR is CLEARED. |
| DISCOVER (§6 step 3) | `KS29-DISCOVERY-LEG` | 0 | live, but **B2 NOT done** — its `ds:` records neither §6-step-3 precondition. See §4 below. |
| SELF-HEAL (§6 step 4) | `ISSUE-SELF-HEAL-RULES` | 0 | live, `depends_on: ISSUE-BOARD-SURFACE` with a real-dep line. Fine as-is. |

**What has NO ticket — this is the work to create.** §6 step 0b/1 (the registry anchor) and every one
of §14.1's five SG-OWNED failure classes. Those five are the classes the design itself says have **no
owning detector anywhere**, and they are the reason the plane would not have caught any of the twelve
failures confirmed on 2026-07-24.

---

## 2. THE DECOMPOSITION — 5 tickets, all P0, one wave, kept SEPARATE

Split rationale (keep this split; do not re-invent one):
- **One ticket per §14.1 registry row**, because each row is a distinct sensor with its own
  `check_cmd`, its own `min_scanned` floor, its own red-proof, and its own owned files — genuinely
  parallel and file-disjoint once the registry anchor lands.
- **Rows 1 and 2 are merged into ONE ticket** (not two). §14.3 states rows 1, 2, 6, 7 share one shape
  ("a check that reports success while not actually checking"); rows 1 and 2 additionally share one
  mechanism — *the RED branch is unreachable because a guard resolves to a pass*. Two tickets here
  would hand-roll the same enumerate-and-disposition primitive twice, which is BRIEF-PREAMBLE §2
  (fix the CLASS as ONE shared primitive) and §3 (anti-accretion). Row 6 stays separate because its
  mechanism is a **latency-budget headroom ledger**, not a guard enumeration.
- **The registry is its own ticket and lands FIRST**, per §6 step 0b and
  [[anchor-lines-serialize-parallel-work]]. It is a genuine build prereq, not sequencing dressing:
  every other slice's `check_cmd`, `min_scanned` and — critically — §10's **declared-floor** bar
  (the suite asserts the count of §5 clauses it exercised against a floor *declared in that slice's
  `detector-registry.tsv` row*) are read out of the registry row. Row 7's `check_cmd` literally
  iterates the registry file.

Wave for all five: **`Wave I — SG issue control plane`**.

### T1 — `SG-ICP-DETECTOR-REGISTRY`  (P0, difficulty 3, work_class rig-meta)
- `branch: feat/sg-icp-detector-registry`
- `owns: fleet/detector-registry.tsv, fleet/tests/detector-registry.test.sh`
- `depends_on: SG-ISSUE-CONTROL-PLANE` · `dep-kind: build` · **real-dep**: the row contents are
  specified ONLY in §14 of a design doc that exists on `feat/sg-issue-control-plane` and **not on
  master**; a builder on master cannot read the spec. Genuine, not ordering.
- **Scope:** §6 step 0b anchor + step 1. Generalize `fleet/plane-canary-registry.tsv` into
  `fleet/detector-registry.tsv` with columns `class, sensor_script, graph_anchor, cadence, severity,
  check_cmd, min_scanned, safe_to_auto_fix, remediation_recipe, owner_ticket` **plus §14.3's
  `proves_execution`** and §4's `auto_launch_gate` / `heal_launched_at` / `heal_blocked_reason`.
  Seed all 12 classes of §14: 5 SG-OWNED full rows, 5 REFERENCED pointer rows (`sensor_script` =
  the incumbent, `check_cmd` invokes the incumbent, **new detector count = 0**), 2 recorded as
  handed back (B5/B6) with no row.
- **PATH DECISION, carry it verbatim:** the registry goes at `fleet/`, **NOT `fleet/state/`**.
  Design §2 says so explicitly and §8 gives the reason — `reds.tsv` and `plane-canary-registry.tsv`
  live at `fleet/` precisely so no `.gitignore` negation is needed. `.gitignore` is the single most
  contended file in the repo (owned by MARKER-PROOF-MECHANIZE **and** TIER-BALANCE). Keeping every
  new registry at `fleet/` **dissolves the anchor-commit contention edge entirely** — which is why
  §6 step 0b collapses to "land the registry" for these five tickets. Same rule for T2's and T3's
  ledgers (see below).
- **Priority-why (one line):** it is the anchor the other four P0 slices are blocked on, and the
  design's own §6 sequences it before any slice can start — a P1 here would leave four P0s unclaimable.
- **Accept:** registry file with all 12 rows; `fleet/tests/detector-registry.test.sh` (`*.test.sh`
  name is MANDATORY, see §3 below) proves schema conformance, proves an SG-OWNED row missing a
  `check_cmd` or a `min_scanned` is RED, and proves an EMPTY registry is RED `vacuous-pass` (§5c).

### T2 — `SG-ICP-GATE-CANNOT-RED`  (P0, difficulty 4, work_class rig-meta) — §14.1 rows 1 + 2
- `branch: feat/sg-icp-gate-cannot-red` · `depends_on: SG-ICP-DETECTOR-REGISTRY` · dep-kind: build
- `owns: fleet/checks/gate-red-reachable.sh, fleet/fail-open-disposition.tsv,
  fleet/tests/gate-red-reachable.test.sh`
  (ledger at `fleet/`, not `fleet/state/`, per the T1 path decision — design §14 row 2 wrote
  `fleet/state/fail-open-disposition.tsv`; deviate deliberately and say so in the ticket.)
- **Row 1 `gate-cannot-red`:** live instance — `0a759a8` wired a tier-drift check into
  `validate_board.sh` that is WARN by default and RED only for ids in `fleet/state/tier-drift-red.txt`,
  **a file that does not exist**. Every tier mismatch in fleet history was advisory at rc 0.
  RED condition: RED-set source absent/empty (§5a `source-unresolvable`) **or** a seeded-mismatch
  case exits 0. `min_scanned`: ≥1 RED-set member AND ≥1 executed mismatch case.
  **Note the hand-back:** SG-ICP does NOT ship `tier-drift-red.txt` — `TIER-BALANCE.owns` already
  names it (B7). This row stays RED until TIER-BALANCE ships it, and that is intended behaviour.
- **Row 2 `gate-fails-open`:** live instances — `fleet/wci-contention.sh:40,41,42` (bad N, N<1, and a
  **missing board directory** each `exit 0`); `fleet/watchdog/discover-services.sh:62-63`
  (`[ -x "$SURFACE" ] || return 0` **and** the call ends `|| true`, so the watchdog's whole surfacing
  leg is a silent no-op). Approach: enumerate every early-return-0 guard across the firing layers,
  diff against the disposition ledger; a disposition is `fail-closed` / `justified:<reason>` /
  `accepted:<ticket>` — **never silence**. Empty `found` set ⇒ RED (the regex broke), never GREEN.
- **Priority-why:** these two are why gates in this rig have been reporting success without being able
  to fail at all — the highest-order defect on a board whose entire P0 set is enforced by gates.
- **Dependency to STATE, not assume:** the generalized detector's eventual home is a new
  `gate-creation-standard.sh` S-assertion, but that is only possible **after `META-GATE-CALLSITE-ENUM`
  lands** (`a92019d` on `feat/meta-gate-callsite-enum`, **UNLANDED**) — `gate-creation-standard.sh:155`
  decides membership by DIRECTORY, so `preflight.sh`'s inline `*_gate()` functions and
  `wci-contention.sh` are outside its addressing scheme entirely. Ship standalone now, carry a
  follow-up to fold in. **Record as a note, NOT as `depends_on`** — it is a quality improvement, not
  a build prereq.

### T3 — `SG-ICP-BUDGET-BREACH-DETECT`  (P0, difficulty 3, work_class rig-meta) — §14.1 row 6
- `branch: feat/sg-icp-budget-breach-detect` · `depends_on: SG-ICP-DETECTOR-REGISTRY` · dep-kind: build
- `owns: fleet/checks/budget-headroom.sh, fleet/budget-headroom.tsv,
  fleet/tests/budget-headroom.test.sh`
- **Live instance, confirmed by execution this session:** `fleet/validate_board.sh:393` runs
  `parallelizability-gate.sh` under `timeout=15`; `:399` catches the expiry and appends the advisory
  string `parallelizability-check-failed: could not run parallelizability-gate.sh — {e}`. Measured
  cost of that gate is ~21.7 s. **The gate never runs, the caller's rc stays 0, the board reads
  GREEN while an enforcement check has stopped executing.**
- Two required legs: **(i) instance** — assert POSITIVE evidence the sub-check ran (absence of the
  error string is NOT proof); **(ii) class** — enumerate every budgeted call site
  (`grep -rnE 'timeout[= ][0-9]+' fleet/*.sh fleet/*.py fleet/checks/*.sh`) against a headroom ledger.
- RED condition includes a **headroom alarm at ≥ 0.8 × declared budget** — fires BEFORE the check
  silently trips, not after. `min_scanned`: ≥1 budgeted call site AND ≥1 item actually classified.
- **Priority-why:** the design names it "the most dangerous shape in this section" — strictly worse
  than rows 1/2 because it is a check that *stopped* firing after previously working, with no
  transition signal; and its live instance is currently degrading the rig's own merge gate.

### T4 — `SG-ICP-VACUOUS-PASS-FLOOR`  (P0, difficulty 3, work_class rig-meta) — §14.1 row 5
- `branch: feat/sg-icp-vacuous-pass-floor` · `depends_on: SG-ICP-DETECTOR-REGISTRY` · dep-kind: build
- `owns: fleet/checks/vacuous-pass-floor.sh, fleet/tests/vacuous-pass-floor.test.sh`
- Target surfaces: `fleet/gate.sh` (`tests=("$TESTS_DIR"/*.test.sh)` glob at `:33`),
  `preflight.sh cmd_scan`, `validate_board.sh` — each reports success on an empty population without
  naming a scanned count. Assert non-zero exit AND the literal red id on an empty population, and
  that every GREEN line NAMES its scanned count. `min_scanned`: all 3 surfaces exercised — fewer is
  itself a vacuous pass.
- **OWNS / ANCHOR SEPARATION — copy `ISSUE-BOARD-SURFACE.ds:`'s pattern.** The CHECK is read-only over
  the three surfaces and is what this ticket owns. Making those surfaces *print* their scanned count
  is at most a ONE-LINE ANCHOR in files this ticket does NOT own and MUST NOT become a concurrent
  writer of: `fleet/preflight.sh` (**5 live owners, already a validate_board RED**),
  `fleet/validate_board.sh` (PROJECT-MEMBERSHIP-GATE + TIER-BALANCE), `fleet/gate.sh`. Coordinate;
  do not restructure.
- **Do NOT restate `META-GATE-FINDINGS-ZERO`.** That ticket owns the *per-gate instance*
  (`fleet/GATE-CREATION-STANDARD.md`, `fleet/tests/large-file-guard.test.sh`,
  `fleet/tests/rig-ci-scope.test.sh`) and carries `depends_on: GITHUB-LIMITS-HARDENING,
  HANDOFF-GATE-NONBYPASSABLE`. This ticket is the **fleet-wide-surface generalization** and must
  CITE it, not duplicate it.
- **Priority-why:** a zero-item GREEN on `gate.sh` / `preflight.sh` / `validate_board.sh` invalidates
  every other P0's evidence — this is the floor the whole board's greens rest on.

### T5 — `SG-ICP-DETECTOR-INERT`  (P0, difficulty 3, work_class rig-meta) — §14.1 row 7
- `branch: feat/sg-icp-detector-inert` · `depends_on: SG-ICP-DETECTOR-REGISTRY` · dep-kind: build
  (**hardest dep of the five** — the `check_cmd` iterates `fleet/detector-registry.tsv` row by row and
  its `min_scanned` IS the registry's non-comment row count)
- `owns: fleet/checks/detector-inert.sh, fleet/tests/detector-inert.test.sh`
- Three distinct sub-ids, because the remediations differ: **`detector-uncalled`** (zero non-test call
  sites), **`detector-rc-discarded`** (only call site drops rc via `|| true`, unchecked `&`, or
  output-to-var), **`detector-surface-missing`** (surfacing target absent on disk).
- Live instances: `fleet/plane-canary.sh` — the detector the design's §0 leans on for its founding
  evidence — has **zero non-test call sites on master** (its wiring is `aed5fc2` on the **UNLANDED**
  `feat/plane-canary-wire`); `fleet/stale-check.sh` has zero callers and says so in its own trailer;
  `fleet/dark-work-check.sh` IS called (`discover-services.sh:132-138`) but surfaces through
  `wd_surface` → `fleet/issue-board.sh` (`:53`), **a file that does not exist** — and note WHICH file:
  the struck fork. **A builder must not create `fleet/issue-board.sh`/`fleet/state/issue-board.tsv` to
  satisfy this; the correct fix is to repoint the surface at `reds.tsv` via `ISSUE-BOARD-SURFACE`.**
- **Coverage boundary, state it:** `plane-canary.sh`'s `unwired` leg covers the *plane* population;
  `tools/check_inert_code.py` covers *product Python*. Neither covers **rig bash detectors**, and
  neither covers the rc-discard or missing-surface legs at all — those two slivers are the only new
  work. `META-GATE-CALLSITE-ENUM` (`a92019d`, **UNLANDED**) would supply the call-site union this
  should eventually consume instead of `grep`; ship with `grep`, carry a follow-up. Note, not a dep.
- **Priority-why:** the plane's own founding evidence comes from a detector with zero callers — until
  this exists, "we have detectors" is unfalsifiable and every DISCOVER-leg green is unproven.

---

## 3. CONSTRAINTS THAT MUST APPEAR ON EVERY ONE OF T1–T5

Copy these onto each ticket; they are the design's own acceptance bars and the re-review found that
without them an implementer can still ship a check that cannot go RED.

1. **§10 EXECUTED RED-PROOF, per §5 clause, per slice.** For each §5 fail-closed clause the slice
   implements — (a) `source-unresolvable`, (b) forbidden absence-closure, (c) `vacuous-pass`/
   `min_scanned`, (e) `input-degraded` — the slice's `fleet/tests/<stem>.test.sh` carries a case that
   **drives the check into its fail-closed branch and asserts a non-zero exit AND the specific red
   id**, not merely that the path is reachable. Three anti-vacuity bars, ALL required:
   (i) **fail-on-revert, per case** — reverting that ONE clause to a pass/skip/`return 0` must turn
   that case RED; name the revert in the case; a case that still passes with its clause reverted is
   not a red-proof and **the slice is REJECTED**;
   (ii) **declared floor** — the suite asserts the count of §5 clauses it exercised against a floor
   declared in that slice's `detector-registry.tsv` row, so a suite exercising zero or a subset exits
   non-zero rather than GREEN;
   (iii) **runner-reachability, PROVEN BY EXECUTION** — the file must match `fleet/gate.sh:33`'s
   `*.test.sh` glob (**a `test_*.sh` name is NEVER matched** — `fleet/tests/test_wci_strict.sh` and
   `test_detention.sh` are live examples of proofs no runner runs) **and** be listed by
   `bash fleet/checks/rig-ci-scope.sh suites`. Paste both runner lines and the run's rc.
   Note: `gate-creation-standard.sh` S1 binds only `fleet/checks/*` and therefore discharges this for
   T2/T3/T4/T5 only — it does NOT discharge T1, whose files sit at `fleet/`.
2. **DO NOT RESURRECT THE STRUCK FORK.** `fleet/reds.tsv` + `fleet/preflight.sh` ALREADY ARE the
   unified issue board. **§5 step 2 of the design itself prescribes `state/issue-board.tsv` and is
   SUPERSEDED** — a claimant who reads the design in good faith and builds the store is wrong. A diff
   that adds `fleet/issue-board.sh` or `fleet/state/issue-board.tsv` FAILS the ticket.
3. **DO NOT ABSORB ANOTHER MECHANISM'S WORK.** 5 classes are SG-owned (T2–T5's rows); 5 are
   **pointer rows only** — `redproof-reachability` (META-GATE-REDPROOF-REACHABLE),
   `callsite-enum` (META-GATE-CALLSITE-ENUM), `built-but-unlanded` (`done_merge_gate` +
   `detect_needs_push` + `reconcile-merged.sh` — **BUILT + LIVE**, a fourth counter is the F2 defect),
   `no-ticket-mapping` (`dark-work-check.sh --register`), `stale-doc-claims` (`handoff-check.sh`).
   Two were handed back and get NO row (B5 product `.git/hooks` boundary leak; B6 adopted-tool
   under-utilization — a design-quality verdict with no deterministic predicate).
4. **UNLANDED DEPENDENCIES ARE STATED, NEVER ASSUMED.** `feat/meta-gate-callsite-enum` (`a92019d`)
   and `feat/plane-canary-wire` (`aed5fc2`) are both UNLANDED on master. Rows 1, 2, 3, 4 and 7 all
   improve when they land; none may assume they have. Design §12 item 6: the design branch is BEHIND
   master — refresh before building.
5. **Registration (§10).** Every new `fleet/checks/*.sh` must pass
   `bash fleet/checks/gate-creation-standard.sh check`; every enforceable rule gets a
   `fleet/state/RULE-REGISTRY.tsv` row; **one `fleet/plane-canary-registry.tsv` row PER SLICE**, not
   one shared row (one shared row leaves the other proofs with no runner).
6. **Sequencing.** All five start **AFTER the current landing wave**. T1 is a real `depends_on` for
   T2–T5. "After the current wave" is otherwise **plain ordering and is recorded as a note, never as
   a manufactured `depends_on`.**

---

## 4. STILL UNTICKETED AFTER T1–T5 (next session's follow-on, do not lose)

- **B2 — `KS29-DISCOVERY-LEG` preconditions NOT recorded.** Its `ds:` says "P0, slice 2" and nothing
  else. Design §6 step 3 BARS it on two external preconditions: (i) land `feat/reconcile-gate-wired`
  (`d603494`) — its detector is already WRITTEN and its absence is why the `reconciliation` plane is
  proofless RED, so rebuilding it is a duplicate build; (ii) satisfy `INERT-WIRING-ENFORCEMENT-DURABLE`,
  an operator-escalated DESIGN-FIRST ticket ("do NOT build another gate before explaining WHY the
  prior ones decayed"). **Until this is on the ticket, a P0 claimant will build the highest-risk
  fake-green slice in the design.** This is a 4-line `ds:` edit and should be the next session's
  FIRST action. Also: `KS29-DISCOVERY-LEG.owns` names `fleet/state/component-registry.tsv`, which
  needs a `.gitignore` negation — or, better, move it to `fleet/component-registry.tsv` per T1's path
  decision and dissolve the contention.
- **B4** — `SG-ISSUE-CONTROL-PLANE.owns` should add `docs/review-log/SG-ISSUE-CONTROL-PLANE.md`.
- **§6 step 5** — close the 8 RED `plane-canary.sh reconcile` rows (or record why a new plane precedes
  fixing the one already shouting). The design calls this its own premise test and non-optional. It is
  an ACTION, not a build; no ticket exists.
- **§6 step 7** — level-trigger the loop on `foreman-cadence.sh`. Probably folds into
  `ISSUE-BOARD-SURFACE`'s cadence anchor rather than becoming its own ticket.
- **§12 item 4** — `fleet/reuse-check.sh` raises `FileNotFoundError` for a not-yet-created path, so the
  reuse gate is unusable for the exact case it is most needed in. Design says this "needs its own
  ticket". None exists.
- **Design §10's independent re-review of revision 2** is a stated LAND PRECONDITION for
  `feat/sg-issue-control-plane` and has not happened.

---

## 5. THE P1 SCORECARD TICKET — SPEC READY, **NOT CREATED**

Coordinator-directed, operator-sourced. Evidence:
`fleet/state/reviews/SCORECARD-FALSE-BLOCK-AUDIT-agen-kolar.md` §5 — **42 of 46 lifetime BLOCK
enqueues (rc=127×24, rc=134×18, rc=132×4) are provably infra, not model failures.**

### `SCORECARD-BLOCK-HISTORY-RECLASSIFY`  (P1, difficulty 3, work_class rig-meta, repo charon-private)
- `branch: fix/scorecard-block-history-reclassify`
- `owns: fleet/benchmark/scorecard-block-classify.sh,
  fleet/tests/scorecard-block-classify.test.sh` (check `fleet/model-scorecard.sh` first —
  BRIEF-PREAMBLE §3 anti-accretion: extend it if the seam fits rather than adding a script)
- **`depends_on:` MUST BE LEFT EMPTY. Here is why, and do not "fix" it by inventing a dep:**
  the predicate fix is in flight on **`fix/DROID-CLIENT-PREFLIGHT-PATH` @ `adfec65`** (verified by
  reading the diff: it rewrites `is_infra_fault()` with `case "$rc" in 3|125|126|127)` plus
  `[ "$rc" -ge 128 ] && return 0`, and deliberately leaves rc=1 text-discriminated). **That branch
  has NO board ticket on any ref** — I grepped `fleet/board/*` across every branch. A
  `depends_on:` naming it would be a dangling id and an immediate `validate_board` `bad-dep` RED.
  **Record it as `real-dep:` prose + a hard `bar:` instead**, e.g.:
  `bar: DO NOT START until the is_infra_fault() widening has landed on master — verify with`
  `grep -n 'rc -ge 128' fleet/charon-run.sh` (rc=0 required). Remediating history while the
  generator still produces bad rows is pointless.
  **Separately actionable finding for the coordinator: `fix/DROID-CLIENT-PREFLIGHT-PATH` is
  UNTICKETED DARK WORK** — 5 files / 759 insertions touching `charon-run.sh`, `fleet-droid.sh`,
  `env-registry.sh`. It will be refused by `work-lease.sh guard-branch` (the branch→ticket map gate
  on `feat/branch-ticket-map-gate`) and it silently collides with `CAPTURE-WIRING-TIMEOUT-FIX`,
  which `owns: fleet/charon-run.sh`. It needs a ticket before it can land.
- **Scope — the HISTORICAL CORPUS ONLY.** Stopping NEW false rows is the predicate fix above; this
  ticket must NOT duplicate it.
- **Constraints (all mandatory on the ticket):**
  - **Not a hand-edit job.** One row (`kimi-k2.6`, rc=134 SIGABRT, `model-scorecard.tsv:36`) was
    cleared by hand because it was imminent — 33% routing block, one row from advisory-detained.
    Doing 42 that way is the accretion trap. Needs a **systematic, re-runnable** classifier keyed on
    the exit code recorded in the row's `evidence=` field.
  - **`fleet/model-scorecard.tsv` is grader-owned** (`bench-grader` unix user; the daemon runs live).
    The work produces analysis + **exact operator commands**; the operator executes. **Back up first**
    — audit §6C is the pattern:
    `sudo -u bench-grader cp -a …/fleet/model-scorecard.tsv …/model-scorecard.tsv.bak-$(date -u +%Y%m%dT%H%M%SZ)`
    (a `.bak-20260725T055548Z` already exists on disk from today's hand-clear).
  - **Do not silently delete measurement data.** Only rows where the exit code ITSELF proves infra,
    provenance preserved per row. **`rc=1` is explicitly OUT** — genuinely ambiguous (opencode generic
    error vs auth 401/403 vs `cd` into a reaped worktree), and the ledger does not record enough to
    classify it. The audit deliberately leaves `deepseek-v4-flash` / `MODEL-GRADE-PRESEED` / rc=1
    (`model-scorecard.tsv:55`) alone. A scorecard edited to taste stops being a measurement.
  - **ASK AND ANSWER EXPLICITLY: after removal, do rankings need recomputing?** Determine whether
    `fleet/capability/grades.py` and `assign.py` derive live from the rows (removal sufficient) or
    whether a materialized artifact — `fleet/scorecard.v1.json`, detention lists via
    `fleet/model-detention.sh` — must be recomputed (recompute is part of the work). The audit notes
    `grades.py` currently returns `None` for every model, so this must be re-measured, not assumed.
  - **Acceptance: fail-on-revert and NON-VACUOUS** — a classification pass that examines zero rows is
    RED, never a silent clean bill.
- **Priority-why (one line):** `model-scorecard.tsv` is what routing ranks on, and if most of its
  BLOCK history is infra noise then every ranking derived from it is suspect — but the corpus is
  historical and the bleeding stops with the predicate fix, so this is P1, not P0.

---

## 6. ROADMAP.tsv — ROWS DELIBERATELY OMITTED

**No rows were added, and the next session should also omit them unless PROJECT-MEMBERSHIP-GATE has
landed.** Two independent reasons:

1. **Ownership.** `fleet/state/ROADMAP.tsv` is `owns:`-ed by `PROJECT-MEMBERSHIP-GATE` (which also
   owns `fleet/validate_board.sh`). BRIEF-PREAMBLE §9: only the designated owner writes it.
2. **Textual conflict.** `git diff master...feat/project-membership-gate -- fleet/state/ROADMAP.tsv`
   is a pure **tail append of 22 rows at `@@ -176,3 +176,25 @@`**. Any append by another lane lands
   in the same hunk and conflicts. (A mid-file insert would dodge the textual conflict but still
   breaches reason 1.)

**Intended rows, for the owner to add post-land** — project `Fleet`, wave `Wave I — SG issue control plane`:
```
Fleet<TAB>SG-ICP-DETECTOR-REGISTRY<TAB>queued<TAB>next<TAB>sg-icp-detector-registry<TAB>detector registry + 12 seeded failure-class rows (SG-ICP anchor)<TAB>Wave I — SG issue control plane
Fleet<TAB>SG-ICP-GATE-CANNOT-RED<TAB>queued<TAB>next<TAB>sg-icp-gate-cannot-red<TAB>detect gates whose RED branch is unreachable + guards that fail open<TAB>Wave I — SG issue control plane
Fleet<TAB>SG-ICP-BUDGET-BREACH-DETECT<TAB>queued<TAB>next<TAB>sg-icp-budget-breach-detect<TAB>detect a latency budget silently switching an enforcement check off<TAB>Wave I — SG issue control plane
Fleet<TAB>SG-ICP-VACUOUS-PASS-FLOOR<TAB>queued<TAB>next<TAB>sg-icp-vacuous-pass-floor<TAB>min_scanned floor + named scanned counts on gate.sh / preflight / validate_board<TAB>Wave I — SG issue control plane
Fleet<TAB>SG-ICP-DETECTOR-INERT<TAB>queued<TAB>next<TAB>sg-icp-detector-inert<TAB>detect built detectors with zero callers / discarded rc / missing surface<TAB>Wave I — SG issue control plane
Fleet<TAB>SCORECARD-BLOCK-HISTORY-RECLASSIFY<TAB>queued<TAB>next<TAB>scorecard-block-history-reclassify<TAB>reclassify 42 of 46 lifetime scorecard BLOCKs as infra, with provenance<TAB>Wave I — SG issue control plane
```

**Pre-existing gap worth flagging to the operator:** `SG-ISSUE-CONTROL-PLANE`, `ISSUE-BOARD-SURFACE`,
`KS29-DISCOVERY-LEG` and `ISSUE-SELF-HEAL-RULES` have **no ROADMAP.tsv rows today** (grepped, zero
hits), and PROJECT-MEMBERSHIP-GATE's own +22 rows do not add them. When that gate lands and makes
"live ticket absent from ROADMAP.tsv" a RED, all four go RED immediately — plus whatever T1–T5 exist
by then. That reconciliation belongs to the ROADMAP owner, before that gate lands.

---

## 7. WHAT WAS PROVED BY EXECUTION vs BY READING

**By execution:** `bash fleet/validate_board.sh` → rc=1 / 10 issues, and its two RED causes (above);
`git diff master...feat/project-membership-gate -- fleet/state/ROADMAP.tsv` → +22 tail append, 0
deletions; `git diff master...fix/DROID-CLIENT-PREFLIGHT-PATH` → 5 files / 759 insertions rewriting
`is_infra_fault()`; `git grep` over every branch's `fleet/board/*` → no ticket for that branch;
`git check-ignore fleet/state/SG-TICKETING-STATUS-agen-kolar.md` → ignored by `.gitignore:10`;
`python3 -c 'from grades import WORK_CLASSES'` → the valid `work_class` set;
`ls fleet/board/` → the three SG slice tickets exist and `ISSUE-BOARD-SURFACE` is already re-scoped.

**By reading:** the 403-line design doc at `b9d314b` (all 14 sections); the four board tickets quoted
above; `SCORECARD-FALSE-BLOCK-AUDIT-agen-kolar.md` §§1, 5, 6; `fleet/validate_board.sh`'s required-field
checks; `.gitignore`'s negation allowlist and its anchor-file note at `:37-42`.

**NOT verified by execution:** that `feat/reconcile-gate-wired` (`d603494`),
`feat/meta-gate-callsite-enum` (`a92019d`) and `feat/plane-canary-wire` (`aed5fc2`) are still
unlanded — taken from the design doc's `[V]` claims dated 2026-07-24. **Re-check before building.**
