# SG-ISSUE-CONTROL-PLANE — independent adversarial RE-REVIEW of revision 2 (agen-kolar)

Target: PR #257 (draft), branch `feat/sg-issue-control-plane` @ `67e4f48`
Worktree: `/home/stack/charon-private-wt/SG-ISSUE-CONTROL-PLANE`
Prior review answered: `fleet/state/reviews/SG-ISSUE-CONTROL-PLANE-REVIEW-agen-kolar.md` (F1–F13, DO-NOT-LAND)
Review date: 2026-07-24. **Read-only** — no commits, edits, pushes, PR-state changes; backup and
main-checkout design left untouched; `fleet/board/*` and `fleet/preflight.sh` not modified.

---

# VERDICT: **LAND-WITH-NITS**

The rework is real, not cosmetic. Revision 2 is materially stronger than **both** prior versions.
Every load-bearing enforcement mechanism it names, I invoked or read and found to exist and be
callable. The strike list is genuinely duplicate machinery, not discarded value. Nothing of
substance was lost from the 109-line base. All ten REQUIRED CHANGES are addressed or honestly
deferred with reasons. The review-log no longer self-attests clean.

Six nits below (N1–N6). **None is a build-blocking defect.** Two are worth fixing before a builder
claims a slice — N2 (a self-contradiction that can reproduce the very fork this revision undoes)
and N4 (the residual path by which an implementer could still ship a check that cannot go RED).
Both are one-to-three-line edits. Do not hold the land for the rest.

---

## Per-claim adjudication

| # | author claim | verdict | evidence |
|---|---|---|---|
| 1 | 109-line base preserved as BASE; only genuinely-new branch content folded; forked duplicate-build content struck | **VERIFIED, one qualification (N1)** | Section-by-section diff base↔rev2 below. All struck items independently confirmed duplicate/absent. Qualification: the base *itself* proposed a second board — see N1. |
| 2 | fold-don't-fork survives **verbatim** at §6 step 0 incl. "Two reconcilers must not drift" + risk HIGH if forked | **VERIFIED verbatim** | Base §5 step 0 vs rev2 §6 step 0 — character-identical, incl. the `UNIFIED-RECONCILIATION-GATE-DESIGN.md:9-14` cite and the `**HIGH if forked**` risk cell. |
| 3 | §0 records the falsified founding premise (incumbent leg works; 8/10 RED, "un-actioned not missing") | **VERIFIED BY EXECUTION** | I ran `bash fleet/plane-canary.sh reconcile` myself: 8 RED / 2 GREEN, same ten planes, same classes, same order as §0's block. Reproduced exactly. |
| 4 | §5 fail-closed floor (a)–(f); §9 pins red-proofs to BOTH runners; §10 mandates registry rows + `gate-creation-standard.sh check` | **VERIFIED as specified; two residual gaps (N3, N4)** | Every named mechanism exists and is invocable — see "mechanism existence" table. |
| 5 | design is now genuinely TRACKED via a `.gitignore` negation | **VERIFIED, durable** | `git check-ignore -v` → rc=1 (no match); `git ls-files --error-unmatch` → tracked; `git status --porcelain` → clean. |
| 6 | `owns` defers to the three landed slice tickets; false "file-disjoint" claim struck | **VERIFIED verbatim** | §8's table matches `fleet/board/{ISSUE-BOARD-SURFACE,KS29-DISCOVERY-LEG,ISSUE-SELF-HEAL-RULES}.md` `owns:`/`depends_on:` exactly, including empty/empty/`ISSUE-BOARD-SURFACE`. |

### Line-number skew correction — **CONFIRMED**

The author's correction to F11 is right, and I confirmed it independently at both refs:

- `git show 8838670:fleet/preflight.sh` → the `scan|""` dispatch chain is at **:878**.
- `git show origin/master:fleet/preflight.sh` → the same line is at **:896**.

Both are true at their own checkout; F11's "wrong line number" was version skew. (My prior review's
`:895` was the `case` line one above the dispatch — off by one, substance unchanged.) The adopted
remedy — cite symbols, not line numbers — is the correct class-fix. Note the design does not fully
live up to it yet: see N6.

---

## Struck items — verified genuinely duplicate, not lost value

| struck | verdict | how verified |
|---|---|---|
| forked `fleet/state/issue-board.tsv` | **genuinely duplicate** | `fleet/preflight.sh:1-8` header read: *"a red closes ONLY on a passing check_cmd or an explicit RECORDED override — never by assertion."* `fleet/reds.tsv` live rows carry the `check_cmd` column the fork lacked. `cmd_detect` is literally labelled *"ACTIVE DETECTORS (unregistered risk not yet in reds.tsv)"* — the union target is reds.tsv by design. |
| `failing/RED` + `done-but-unmerged` classes | **genuinely duplicate** | `board_gate`, `done_merge_gate` present in `preflight.sh` and both in the `scan` dispatch chain; a live `done-unmerged-*` row exists in `fleet/reds.tsv` right now. |
| product-repo `ReviewerCircuitBreaker` | **correctly struck** | `src/charon/failover.py` absent from `charon-private` (ls-verified). `loop-guard.sh`, `lease-enqueue.sh` present and are the rig-native equivalents. |
| invented slice paths / `depends_on` | **correctly struck** | The three landed tickets' `owns:` read directly; rev2 §8 reproduces them verbatim. |
| `RECONCILER-REGISTRY.tsv` as a desired-source | **correctly struck** | `ls fleet/state/RECONCILER-REGISTRY.tsv` → absent. |
| warn-on-stale-graph | **correctly struck** | Fails open on the highest-value class; §5(e) inverts it to RED. Consistent with `gate-parity.sh:12-13`'s own fail-closed doctrine. |

**Nothing struck was new value.** The one item worth checking hardest — the `RECONCILE-GATE-WIRED`
detector at `d603494` — is *not* struck; §6 step 3 correctly bars rebuilding it and requires landing
it instead. Its commit message and script header confirm it implements exactly the desired-vs-actual
set-diff the design would otherwise re-derive.

## Did folding lose anything from the 109-line base?

Compared section by section against `DESIGN-SG-ISSUE-CONTROL-PLANE.BACKUP-agen-kolar.md` (read-only):

| base element | survived? |
|---|---|
| `[V]`/`[I]` claim-tag discipline | **YES — strengthened.** 31 `[V]` tags in the base, **59** in rev2. |
| `§Provenance` files-read section | **YES — extended** with a rev-2 block naming what was executed. |
| ⚠ KS29-discovery-unbuilt flag (`REGISTRY-CANDIDATES.md:58-59`, "fake-green until KS29 ships") | **YES**, in three places: §1 hazard (b), §2 table row, §6 step 3. |
| review-pool / loop-guard / lease-enqueue rails | **YES**, §4 verbatim + folded additions. |
| `--commit-dirty` hazard | **YES**, §1 hazard (a) and §4 rail 3. |
| fold-don't-fork ruling | **YES, verbatim** (§6 step 0). |
| §1 verdict, four exemplars, adopt-vs-extend call | **YES**, verbatim except correct updates ("we already own the sensors, **the board** and the actuator"). |
| §2 nine failure-class rows | **YES**, all nine + a tenth (reconciler). |
| graphify relations-backbone paragraph, KS29 registry paragraph | **YES**. |
| base §3 aggregator (`fleet/issue-board.sh` → `state/issue-board.tsv` + scorecard banner) | **DELIBERATELY OVERRULED** — with evidence (F2). See N1. |
| anti-normalization guarantee | **YES**, re-based on `reds.tsv`'s existing `opened` column. |

**Conclusion: no value lost.** The only base content dropped is the base's own second-board proposal,
and it was dropped with positive evidence rather than silently.

## Mechanism existence — is the enforcement REAL or just wording?

Every mechanism §5/§9/§10 leans on, checked against the tree:

| design clause | mechanism | exists? |
|---|---|---|
| §9 runner 1 — `gate.sh` glob | `fleet/gate.sh:33` `tests=("$TESTS_DIR"/*.test.sh)` | **YES, exact line** |
| §9 runner 2 — `CI_SUITES` | `fleet/checks/rig-ci-scope.sh:49` `CI_SUITES=(` + the verbatim "NEVER replace this with a sweep" comment at `:45-48` | **YES, exact line** |
| §9 "read via `rig-ci-scope.sh suites`, never re-parse the array" | `cmd_suites(){ printf '%s\n' "${CI_SUITES[@]}"; }` at `:300`, dispatched at `:320`; also run by `.github/workflows/rig-ci.yml:93` | **YES — invocable, and itself CI-executed** |
| §10 `gate-creation-standard.sh check` | `:108` `case "$MODE" in check\|scan)` — `check` is a HARD verdict mode; S1/S2/S3/S5/S10 as quoted | **YES, quotes accurate** |
| §10 `RULE-REGISTRY.tsv` → `rule-coverage.sh` → `coverage_gate` | `preflight.sh:318-326`, and `coverage_gate` is in the `scan` dispatch chain | **YES** |
| §10 one `plane-canary-registry.tsv` row per slice, 5-col schema | header row `plane / canary_script / dogfood_test / wired_in / owner_ticket` | **YES, exact** |
| §5(b) closure only on positive re-proof | `run_check` / `cmd_scan` / `cmd_close --override` in `preflight.sh`; header doctrine at `:1-8` | **YES — already-built machinery, not aspiration** |
| §5(c) non-vacuous floor | `gate-creation-standard.sh` S2 *"a gate that passes on zero items proves nothing"* | **YES, quoted correctly** |
| §5(e)/§12.1 graphify precondition | `fleet/checks/graphify-freshness.sh` present; `session-start.sh:104-112` invokes it | **YES** |
| §4 built-in heal commands | `fleet/config-sync.sh`, `graphify-freshness.sh update` both present | **YES** |

This is the strongest part of the revision: §5(b) and §9 are not new promises, they are *bindings to
machinery that already enforces them*. An implementer cannot satisfy §5(b) vacuously — `cmd_close`
physically requires a passing `check_cmd` or a recorded override.

---

## Findings

### N1 — MINOR (provenance accuracy). §11 row 1 mis-attributes the board ruling to the base.

§3 opens: *"Revision 1 said 'generalize the incumbent registry.' The discarded revision forked
`fleet/state/issue-board.tsv` instead."* §11 row 1 records the outcome as **BASE WINS**.

The base's §2 sentence being quoted is about the **registry** (`plane-canary-registry.tsv` →
`detector-registry.tsv`). The base's **§3** proposes, in as many words, *"a thin `fleet/issue-board.sh`
… writes one row per open issue to `state/issue-board.tsv` … and prints a GREEN/RED scorecard banner"*
— i.e. **the base forked a second board too**, just at a different path, and called it *"the missing
piece; operator's #1 pain."*

The *outcome* (extend `reds.tsv`) is right and is well-evidenced. But the attribution is wrong: this
ruling came from the **review (F2)**, not from the base. In a document whose distinguishing discipline
is `[V]` provenance, this is the one claim that fails its own standard.

**Fix (1 line):** §11 row 1 → **"REVIEW WINS (F2) — both revisions proposed a second board; neither
argued against `preflight.sh:1-8`'s close policy."** Adjust §3's opening sentence accordingly.

### N2 — MAJOR-nit (can reproduce the fork). §8's authority rule and §3's ruling contradict each other on one file.

§8 states the binding conflict rule: *"Where this design and a landed ticket disagree, the TICKET is
authoritative."* The landed `ISSUE-BOARD-SURFACE` ticket (P0) `owns: fleet/issue-board.sh,
**fleet/state/issue-board.tsv**, fleet/tests/issue-board.test.sh` — verified verbatim.

So a builder who claims that P0 ticket and applies the design's own conflict rule **builds the forked
board this revision exists to strike**, and is *correct* to do so under the document as written. §8
hands the fix back as **B1**, but B1 carries no bar. Contrast §6 step 3, which explicitly **BARS**
slice 2 until two preconditions clear. There is no equivalent "do not claim `ISSUE-BOARD-SURFACE`
until B1 lands."

This is not a defect of reasoning — the session is legitimately barred from `fleet/board/*` — it is a
missing guard rail on the exact failure mode the revision was written to close.

**Fix (1–2 lines):** in §6 step 2, add: *"**BARRED until B1 lands.** `ISSUE-BOARD-SURFACE.owns` still
names `fleet/state/issue-board.tsv`; under §8's ticket-authoritative rule a builder claiming it today
builds the struck fork. Do not claim this slice until the ticket is re-scoped."* Mirror one line into
§13 row 2 and into the review-log's precondition list.

### N3 — MINOR (over-strong `[V]` claim). §9's "exactly two real runners" is not accurate.

§9: *"The rig has exactly **two** real runners **[V]**."* There are more firing layers that execute
`fleet/tests/*.test.sh`:

- `.github/workflows/bandit.yml:74` → `bash fleet/tests/bandit-canary.test.sh`
- `.github/workflows/semgrep.yml:69` → `bash fleet/tests/semgrep-canary.test.sh`
- `.github/workflows/gitleaks.yml:77` → `bash fleet/tests/gitleaks-canary.test.sh`

each invoked **by name, outside `CI_SUITES`**. And `plane-canary.sh` runs each registry row's
`dogfood_test` — a third runner shape the design's own §10 depends on.

**Impact on enforcement: none.** The binding requirement (glob **and** a named `CI_SUITES` entry) is
strictly conservative — satisfying both guarantees execution regardless of how many other runners
exist. Only the count claim is wrong, and it carries a `[V]`.

**Fix:** soften to *"the two runners this plane's proofs must satisfy"*, or *"at least two; these are
the two that bind here."*

### N4 — MINOR-to-MAJOR (the residual "cannot go RED" path). The fail-closed floor has no red-proof obligation of its own.

This is the sharpest thing I could find against the brief's central question, so state it precisely.

§5(a)–(f) specify fail-closed **semantics**. §9 pins each slice's `*.test.sh` to both runners. §10
inherits `gate-creation-standard`'s S1 RED-PROOFED. But:

1. S1's companion-test clause binds *"every NON-grandfathered `fleet/checks/*`"* (header read). Per the
   landed tickets, **only one of three slices** lives there (`fleet/checks/registry-discovery.sh`).
   `fleet/issue-board.sh` and `fleet/issue-heal.sh` are at `fleet/`, **outside S1's scope**.
2. Nothing anywhere requires a slice's test to *assert that each §5 clause actually goes RED*. §10's
   acceptance requires `plane-canary reconcile` GREEN — which requires the dogfood test to **pass**,
   not to red-proof `min_scanned`, `source-unresolvable`, or `input-degraded`.

So an implementer following this document faithfully can write a `min_scanned` branch that is never
exercised, ship a green dogfood, pass every acceptance command in §10, and have a floor that cannot
fire. That is precisely the class this rig found today. The design *names* the disease correctly and
then leaves one door open.

**Fix (1 line in §10 acceptance):** *"Each slice's `*.test.sh` must carry a fail-on-revert case per
§5(a), (b), (c) and (e) — a check whose fail-closed branch has no red-proof is decoration, exactly as
§9 says of a proof with no runner."*

### N5 — NIT (sequencing accuracy). Landing `d603494` will not make the `reconciliation` plane GREEN.

§6 step 3(i) and §6 step 5 read as though landing `feat/reconcile-gate-wired` clears that RED row.
It clears only the *proofless* half. The registry row is:

```
reconciliation  fleet/checks/reconcile-gate-wired.sh  fleet/tests/reconcile-gate-wired.test.sh  preflight,timer  UNIFIED-RECONCILIATION-GATE
```

`wired_in=preflight,timer`, and `d603494`'s own commit trailer reads `depends_on: RECONCILE-WIRING
(wires this into preflight.sh:841 + land.sh)`. `fleet/checks/reconcile-timer.sh` is absent (the design's
own provenance says so). Landing the detector flips the row **proofless → unwired**, still RED.

Also: §2's reconciler row states the desired-source predicates as `RULE-REGISTRY.tsv` status ∈
{ACTIVE,ENFORCED} and `EVAL-REGISTRY.md` verdict=ADOPT + non-empty `enforced_in`. That is the
**ticket's** spec (honestly `[V]`-attributed to `RECONCILE-GATE-WIRED.md`). The **built** script at
`d603494` uses `classification=mechanized` and an `evidence-link` pointing at a check path. A builder
should reuse the script, not re-derive from the ticket text.

**Fix:** one clause in §6 step 3/5 noting the wire is a separate step (`RECONCILE-WIRING`), and one
clause in §2 noting the built script's predicates differ from the ticket's prose.

### N6 — NIT (citation skew the doc's own header warns about).

- `foreman-cadence.sh:19-21` is cited twice (§1 leg table via `:1-20`, §4 explicitly) for text that is
  at **`:12-13`**.
- `gate-parity.sh:13` — the quoted sentence spans **`:12-13`**.
- §3 lists 10 `cmd_detect` detectors; the live function calls **11** (`detect_service_watchdog` is
  missing from the list).

All three are the exact skew class the design's own citation-discipline header (§ after line 8)
identifies, and §3 already instructs *"Re-measure the exact set at build time; do not hardcode this
list."* **Self-mitigated; noting for completeness only.** Applying the doc's own remedy (cite symbols)
to these three would close it.

---

## `.gitignore` negation — correct and durable

- Added at `:88-93` (comment + `!fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md`), after `fleet/state/*`
  at `:10`. Git's last-matching-pattern-wins rule makes this effective, and it is effective:
  `git check-ignore -v` returns rc=1 (no match) and the file is tracked.
- The parent pattern is `fleet/state/*` (glob), **not** `fleet/state/` (directory) — so the directory
  itself is never excluded and the negation is reachable. This is the failure mode that silently
  defeats negations; it does not apply here.
- Follows the established convention — 12+ sibling negations for durable `fleet/state/` artifacts.
- **Re-ignore risk: low.** Only a *new, broader* ignore pattern placed **after** `:93` could re-ignore
  it, and the file's own explanatory comment block makes that an obvious mistake to catch in review.
- Pre-existing, **not introduced here**: `!fleet/state/REACHABILITY-AUDIT.md` is duplicated at `:40`
  and `:87`. Harmless, but it is the kind of cruft this rig treats as a class defect. Worth a separate
  one-line cleanup, not this PR's problem.

## Scope

`67e4f48` touches exactly what it claims: `.gitignore` (+6), `docs/review-log/SG-ISSUE-CONTROL-PLANE.md`,
`fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md`. Branch total vs `origin/master`: **3 files, +361**. No
code, no `fleet/board/*`, no `fleet/preflight.sh`, no product-repo changes. Working tree clean.

The review-log is honest: it **withdraws** the revision-1 `CONFIRMED-CLEAN`, names the withdrawal
reason (builder == reviewer), and closes with *"PENDING INDEPENDENT REVIEW OF REVISION 2"* rather than
a fresh self-attestation. That is the correct posture and it is why this re-review can clear it.

## Implementability

Implementable as written for slices 1 and 3. Slice 2 is explicitly **barred**, correctly. The crucial
parts are not hand-waved: the surface work is named down to the function level (`board_gate` /
`done_merge_gate` as the template, `cmd_detect`'s advisory list as the population), the runner
requirement is a literal command (`rig-ci-scope.sh suites`), acceptance is three literal commands, and
the registry-row contract is a named column list. The two things a builder still has to decide for
themselves — the exact `min_scanned` values and the initial `safe_to_auto_fix` allowlist membership —
are correctly left open with a stated default (`no`) and a stated policy (start with one class).

---

## What I verified by EXECUTION vs by READING

**Executed:**
- `bash fleet/plane-canary.sh reconcile` → 8 RED / 2 GREEN, reproducing §0's block exactly (claim 3).
- `git check-ignore -v` (rc=1), `git ls-files --error-unmatch` (tracked), `git status --porcelain`
  (clean) on the design path in the worktree (claim 5).
- `git diff --stat origin/master...HEAD` (3 files, +361) and `git show --stat 67e4f48` (scope).
- `git show 8838670:fleet/preflight.sh` vs `git show origin/master:fleet/preflight.sh` → dispatch at
  `:878` and `:896` respectively (skew correction).
- `git show --stat d603494` + `git show d603494:fleet/checks/reconcile-gate-wired.sh` (N5, F3 follow-up).
- `ls` → `RECONCILER-REGISTRY.tsv`, `src/charon/failover.py`, `fleet/checks/reconcile-gate-wired.sh`,
  `fleet/tests/reconcile-gate-wired.test.sh` absent; `GATE-GAP-LEDGER` is `.tsv`; `review-pool.sh`,
  `loop-guard.sh`, `lease-enqueue.sh`, `config-sync.sh`, `graphify-freshness.sh` present.
- `grep -c '\[V\]'` → 31 (base) vs 59 (rev2).

**Read:**
- Both design versions in full, plus the preserved 109-line backup (read-only, unmodified).
- `fleet/preflight.sh` (header `:1-8`, `cmd_detect`, `coverage_gate` block, scan dispatch), `fleet/reds.tsv`.
- `fleet/gate.sh:30-36`, `fleet/checks/rig-ci-scope.sh` (`:30-31` usage, `:40-55`, `:300`, `:320`).
- `fleet/checks/gate-creation-standard.sh:1-45` + `:108` dispatch; `fleet/checks/gate-parity.sh:11-14`.
- `fleet/plane-canary.sh:14-24,189-193`; `fleet/plane-canary-registry.tsv` (schema + `reconciliation` row).
- `fleet/foreman-cadence.sh:12-13,19-21`; `fleet/hooks/session-start.sh:99,104-112`.
- `fleet/board/{SG-ISSUE-CONTROL-PLANE,ISSUE-BOARD-SURFACE,KS29-DISCOVERY-LEG,ISSUE-SELF-HEAL-RULES}.md`
  front-matter; `.gitignore` in full; `.github/workflows/*.yml` run-steps; the review-log diff.

**Not verified (out of scope):**
- Whether graphify's extractor coverage is sufficient for the reachability walk (§12.1's own declared seam).
- Whether `INERT-WIRING-ENFORCEMENT-DURABLE`'s design-first bar can be cleared — that is slice-2 work.
- `UNIFIED-PLANE-CANARY-FRAMEWORK`'s true status (§12.5 flags it as ambiguous; still unresolved).

---

## Bottom line

The previous DO-NOT-LAND was answered on the merits, not papered over. The document now does what a
design of record should: it is tracked, provenance-tagged, adjudicated line by line against the
version it replaces, honest about what it deferred and why, and it binds its enforcement to machinery
that already exists rather than to promises. **LAND-WITH-NITS.** Apply N2 and N4 before a builder
claims a slice; N1, N3, N5, N6 can ride in any later touch.
