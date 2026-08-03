# RESCUE-TRIAGE-RIG — disposal table for the 9 rig branches (2026-08-01 sweep)

Source: RESCUE-PUSH-TOOL live sweep 2026-08-01. Pushing 47 local-only branches made
them safe from disk loss but did not make them reviewed or visible. Nine rig branches
sat on origin with **no PR of any kind** against them. This ticket is the read-then-dispose
pass over exactly those nine. Method per branch: (a) is the change already on master by
another route — proven with commit shas, byte-identical files, patch-id; (b) does it still
contribute anything master lacks. A verdict without evidence is a guess; every row carries
its proof.

Master base: `origin/master` @ `67c7eaa` (2026-08-01). PRs opened via `gh`, branches
closed via `gh api -X DELETE .../git/refs/heads/<branch>`.

| branch | commits ahead | verdict | evidence |
|---|---|---|---|
| `chore/retire-wire-graphify` | 1 | **CLOSED-DEAD** | Master already retired it: `fleet/board/archive/WIRE-GRAPHIFY-FRESHNESS.md` exists on master, byte-identical to the branch's file (diff: no output), committed by `6a8bcaa` "board-hygiene: commit the retire-done move for 30 completed tickets". The board file no longer exists on master at all. The branch's only change is already on master. |
| `feat/bench-oob-grading` | 2 | **CLOSED-DEAD** | All 5 branch files already on master in **evolved** form: `grader-daemon.py` (master 992 lines vs branch 720, landed via `3cd07f2` "bench(#26)" + `f9960ed` "GRADER-SECFIX-RECONCILE — graft verified F1/F2/F5 hardening onto master's canonical grader (#148)" + `3238f7c` STAGE-DEMUX), `fleet/benchmark/graders/reds_replay.py`, `fleet/benchmark/selftest/test_grader_daemon.py`, `REVIEW-PACKET.md`, `fleet/benchmark/RUN-BENCHMARK.md`. Master's versions carry post-branch security hardening (F1/F2/F5). Nothing the branch offers is absent from master. |
| `feat/coverage-meta-gate` | 1 | **CLOSED-DEAD** | `fleet/checks/rule-coverage.sh` is **byte-identical** on master (landed `0c6982e` "COVERAGE-META-GATE — rule-coverage meta-gate (§11 teeth), re-derived onto master (#140)"). `fleet/tests/rule-coverage.test.sh` present on master. `fleet/state/RULE-REGISTRY.tsv` on master is a **superset** of the branch's (adds s0-adopt-first rows). The branch's content landed and was extended. |
| `feat/pr-queue-rest-etag` | 1 | **PR-OPENED #392** | The **only** live branch of the nine. `fleet/pr-queue.sh` + `fleet/tests/pr-queue.test.sh` are ABSENT from master. The governing board ticket `fleet/board/PR-QUEUE-REST-ETAG.md` is LIVE on master (not archived) and `fleet/state/PRIORITY-TODO.md` records it BUILT (40/40 tests, zero-quota steady state) with the `review-pool.sh` cutover approved-but-not-done. PR body states what it delivers, what's on master (the ticket + still-GraphQL `queue_gen()` in `review-pool.sh`), and what's left (the cutover, owned by REVIEWER-TAB-POOL/PR #346). |
| `feat/substrate-first-gate` | 1 | **CLOSED-DEAD** | The v1 shape (hand-rolled sed/case/awk parser). Master already carries the gate: `fleet/checks/substrate-first-gate.sh` on master is **identical** to the **v2** branch's version, and `fleet/checks/substrate_first_gate.py` (the v2 real-YAML parser, 984 lines on master) is an evolved superset of v2's 793-line version. Landed `8cb2ba7` "net-diff re-derive the substrate-first gate onto current master" + follow-on `03ba2b1` (#142), `06b1764` (base-ref owns), `c636ad8` (#365 GATE-OWNERSHIP-FAILOPEN). v1 was the LOSER of the two-shape race: its hand-rolled 285-line parser had nine adversarial evasions and was replaced by the real YAML parser in v2. |
| `feat/substrate-first-gate-v2` | 3 | **CLOSED-DEAD** | The v2 shape was the WINNER of the two-shape race (its parser model is what lives on master), but its content is already fully on master: master's `fleet/checks/substrate-first-gate.sh` is byte-identical to v2's, and master's `substrate_first_gate.py` is a **superset** of v2's (adds base-ref owns resolution, fnmatch import, live-board-ticket scoping, FAILOPEN fix). The gate live on master supersedes BOTH shapes. |
| `fix/broker-bare-tier-legs` | 1 | **HELD-WITH-REASON** | The hold is NOT spent — the blocker `GRADE-MODEL-PROVIDER-PAIR` is still LIVE on master (`fleet/board/GRADE-MODEL-PROVIDER-PAIR.md` present, not in archive; its branch `feat/grade-model-provider-pair` is not merged; master's `model-scorecard.sh` still has no provider capture field). PER TICKET: blocker has not landed -> leave the branch alone with the reason recorded. ADDITIONAL (strengthens HELD): master's `fleet/tier-models.tsv` has since moved in the OPPOSITE direction (`137d3e3` "tier chains route to DIRECT providers") — ids are now provider-qualified (`deepseek-v4-pro-ds`, `minimax-m2.5-go`, `gpt-oss-120b-groq`), while this branch strips ids BARE so the broker picks the provider. The branch's premise is now contradicted by master; not a PR candidate, not yet safe to dispose. |
| `fix/budget-source-reconcile` | 1 | **CLOSED-DEAD** | Master commit `d200497` carries the **identical message** "fix(budget): reconcile real-outcome source with grades.py SSOT". Master's `fleet/capability/grades.py` exposes `REAL_OUTCOME_SOURCES = frozenset({"live"})` (line 348) exactly as the branch adds it; `fleet/benchmark/budget-derive.py` on master is byte-identical to the branch's and imports `grades.REAL_OUTCOME_SOURCES`; `fleet/tests/budget-derive.test.sh` present on master. The change landed verbatim by another route. |
| `salvage/session-notes-20260719` | 1 | **CLOSED-DEAD** | 3 of the 7 files are byte-identical on master already: `fleet/session-notes/2026-07-18-meter-doc-reconcile-followup.md`, `fleet/session-notes/2026-07-19-public-clean-sweep-inventory.txt`, `fleet/session-notes/2026-07-19-public-clean-sweep.md`. The other 4 (`20260719T*Z-submit-auto.md`) are auto-submit check-in notes — a class master deliberately sweeps as dead (`5ab9c47` "chore(state): sweep 92 dead submit-auto check-in notes"). Nothing salvageable is absent from master. |

## Disposition summary
- **PR-OPENED: 1** (`feat/pr-queue-rest-etag` → PR #392).
- **CLOSED-DEAD: 7** (all content verified on master, either byte-identical or as an
  evolved superset; branches deleted on origin).
- **HELD-WITH-REASON: 1** (`fix/broker-bare-tier-legs` — GRADE-MODEL-PROVIDER-PAIR still
  live, and master has since moved tier routing in the opposite direction).
- The two-shape pair (`substrate-first-gate` / `-v2`) resolved in favour of NEITHER branch:
  the gate live on master supersedes both. v1 lost the parser race (9 evasions vs real YAML
  parser); v2 won the shape but its content landed on master before this triage ran.

## Outcome vs failure mode
Opening 9 PRs would have been the failing result — it would have converted the rescue into
nine review-queue slots for content master already holds. Exactly one PR was opened, with a
body a reviewer can judge without re-deriving this triage. Seven branches were closed with
evidence of landing; one remains held with the reason on record.
