# SG-ISSUE-CONTROL-PLANE — independent adversarial DESIGN review (agen-kolar)

Target: PR #257, branch `feat/sg-issue-control-plane` @ `8838670`
Worktree: `/home/stack/charon-private-wt/SG-ISSUE-CONTROL-PLANE`
Diff: `fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md` (+639), `docs/review-log/SG-ISSUE-CONTROL-PLANE.md` (+27)
Review date: 2026-07-24. Read-only; no git write-ops performed.

---

# VERDICT: **DO-NOT-LAND**

Not because the *idea* is wrong — the DISCOVER → SURFACE → SELF-HEAL shape is right and the
operator's pain is real. It is DO-NOT-LAND because:

1. **A materially better design already exists at the exact same path** and this commit
   silently replaces it with a weaker one (F1).
2. **Two of the three build-slices it authorises are duplicate builds** of machinery that is
   already written in this repo (F2, F3).
3. **The design's founding premise is falsified by running the rig's own tooling** — the
   incumbent discover+surface mechanism for these exact classes is already live and already
   LOUD RED on 8/10 planes; nobody has actioned it (F4).
4. **Its enforcement spec reproduces three of the four failure classes this rig found today**
   (F5, F6, F7).

The next build (`ISSUE-BOARD-SURFACE`) inherits all four. Send it back for one revision pass;
the fixes are concrete and cheap (see REQUIRED CHANGES).

---

## F1 — BLOCKER. This commit replaces a better, provenance-backed design at the same path.

`/home/stack/charon-private/fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md` **already exists on
the main checkout** — 109 lines, untracked (gitignored by `.gitignore:10 fleet/state/*`), dated
2026-07-24, the original adopt-first investigation. The branch force-adds a **different**
639-line document at that path.

Verified: `git ls-files --error-unmatch` → not tracked on master; `git check-ignore -v` → hit;
`diff` of the two → DIFFERENT.

The incumbent 109-line doc is **better on every axis this review is asked to judge**:

| axis | incumbent (109L, untracked) | branch (639L, PR #257) |
|---|---|---|
| provenance | every claim tagged `[V]` (file:line read) / `[I]` (inferred); §Provenance lists 15 files read + every web doc fetched | **zero** verification markers; no provenance section |
| reuse citations | `plane-canary.sh:168-227`, `graphify-freshness.sh:38-44,230-243`, `lease-enqueue.sh:1-24`, `foreman-cadence.sh:19-21`, `session-start.sh:99,104-112`, `RECONCILE-GATE-WIRED.md:35`, `check_inert_code.py` | none of these; `RECONCILE-GATE-WIRED` mentioned **0 times** |
| board strategy | *"generalize `plane-canary-registry.tsv` → `detector-registry.tsv`"* — **extend the incumbent** (§2 line 56) | forks a **new** `fleet/state/issue-board.tsv` |
| fork hazard | §5 step 0: *"**Fold, don't fork.** … Two reconcilers must not drift."* risk = **HIGH if forked** | does the forked thing |
| known-unbuilt flag | KS29 discovery leg flagged **⚠ unbuilt**, `REGISTRY-CANDIDATES.md:58-59`, *"fake-green until KS29 discovery ships"* | flag dropped |
| self-heal rails | `review-pool.sh` fail-closed BOUNCE + `loop-guard.sh` anti-fork-bomb + `lease-enqueue.sh` exactly-once marker + explicit `--commit-dirty` hazard exclusion | rails replaced by a product-repo Python class (see F9); `--commit-dirty` hazard **not mentioned** |

**The branch document does precisely what the document it overwrites warns is the HIGH risk.**
That inversion is the strongest single reason not to make it the record.

Operational hazard on top: because the path is gitignored with **no `.gitignore` negation**,
landing this leaves the main checkout with a tracked file whose working copy differs → an
immediately dirty master that `detect_repo_drift` (preflight.sh:207) will flag, and a conflict
on the next checkout.

## F2 — BLOCKER (reuse). The SURFACE slice duplicates `fleet/reds.tsv` + `preflight.sh`.

Design §0 asserts the fleet **does not have** *"a unified ISSUE BOARD that aggregates every
detector's output into ONE visible surface … checked at SessionStart."* **False.**

`fleet/reds.tsv` + `fleet/preflight.sh` is that board, and it is stronger than the proposed
replacement:

- `preflight.sh:1-8` header — *"REDS REGISTRY driver … Every known red lives in reds.tsv and is
  RE-VERIFIED deterministically here. THE KEY RULE: a red closes ONLY on a passing check_cmd or
  an explicit RECORDED override — never by assertion."* That is level-triggered re-proof plus a
  close policy.
- `cmd_scan` (`preflight.sh:52-76`) re-runs every open red's `check_cmd` each session and prints
  the table — the SessionStart surface.
- The **auto-register-a-detector-finding-as-a-self-closing-blocking-red** pattern is already
  implemented **five times**: `board_gate` (:246-286), `executor_gate` (:288-...),
  `handoff_gate` (:~395), `detect_needs_push` (:409-465), `done_merge_gate` (:466-540).
- `cmd_detect` (:145-146) is explicitly documented as *"ACTIVE detectors for drift/risk **NOT yet
  in reds.tsv**"* — i.e. the union target is reds.tsv by design; the advisory detectors are the
  known, named backlog.

Design §2.6 (`done-but-unmerged`) is **verbatim `done_merge_gate`**, already built, already
auto-registering `done-unmerged-<id>`, already self-closing on `verify-merged.sh` — and there is
a live row for it in `fleet/reds.tsv` right now. §2.2 (`failing/RED`) is `board_gate`.

The real gap is small and different from what the design says: **~6 advisory detectors lack a
`check_cmd` and an auto-register call.** That is a handful of rows and five ~10-line functions
in an existing file — not a new board, a new upsert primitive, and a new surface script.

The branch cites `reds.tsv` **once**, in passing (§2.2), and never argues why extending it is
insufficient. Adopt-first requires that argument.

Net effect if landed: **two panes of glass** — `reds.tsv` (blocking, enforced close policy) and
`issue-board.tsv` (advisory, weaker close policy) — directly contradicting §3.3's own
*"the board is ONE tsv … the single pane of glass."*

## F3 — BLOCKER (reuse). The DISCOVER/inert slice duplicates an already-written detector.

`fleet/board/RECONCILE-GATE-WIRED.md` (P0, open) specifies design §2.1 **word for word**:

> desired-source = every gate/check/rule declared in `fleet/checks/*.sh` + `*.py`,
> `tools/check_*.py` + `*.sh`, `RULE-REGISTRY.tsv` rows with status ∈ {ACTIVE,ENFORCED}, and
> `EVAL-REGISTRY.md` rows with verdict=ADOPT + non-empty `enforced_in`. actual-source = the set
> actually executed by a real firing layer: rig side = `fleet/preflight.sh:841` scan dispatch,
> `fleet/land.sh`, `fleet/validate_board.sh`, `fleet/hooks/pre-*.sh`; product side =
> `.github/workflows/*.yml` run: steps + native branch-protection required-checks.

Compare design §2.1 — same two lists, same order, same sources; only the (also wrong) line
number differs (878 vs 841).

**The detector is already written**: commit `d603494` *"feat(reconcile-gate-wired): built-but-inert
meta-gate (detector, no wire)"*, branch `feat/reconcile-gate-wired` (present on `origin` and
`gitea`). The ticket's own note calls landing it *"the SINGLE HIGHEST-LEVERAGE action in the
whole built-but-not-wired class."* The files are absent from master (`fleet/checks/reconcile-gate-wired.sh`,
`fleet/tests/reconcile-gate-wired.test.sh` — both `ls`-verified missing), which is why
`plane-canary reconcile` reports the `reconciliation` plane proofless (see F4).

Also unaddressed: `fleet/board/INERT-WIRING-ENFORCEMENT-DURABLE.md` is an **operator-escalated,
design-first** ticket whose `work_class_note` reads:

> *"built-but-not-wired … keeps recurring DESPITE multiple audits … and fixes that 'don't work
> over time.' This ticket is DESIGN-FIRST — **do NOT build another gate before explaining WHY the
> prior ones decayed, or it repeats the failure.**"*

SG-ISSUE-CONTROL-PLANE is another gate for that class, authored without the decay root-cause,
and cites that ticket **0 times**. Building slice #2 as written violates a standing
operator escalation.

Also unreferenced: `fleet/board/META-GATE-REDPROOF-REACHABLE.md`, which already owns the
"a red-proof no runner executes is decoration" problem and names the mechanism (read
`fleet/gate.sh`'s `*.test.sh` glob + `rig-ci-scope.sh suites` output). See F6.

## F4 — BLOCKER (premise). The incumbent mechanism is already RED and un-actioned.

Ran `bash fleet/plane-canary.sh reconcile` on master:

```
RED  data/serving   unwired canary  — preflight does not invoke flow-canary
RED  failover       unwired canary  — ci + preflight do not invoke failover-canary
RED  egress-key     proofless       — canary_script + dogfood_test absent on disk
RED  review         proofless       — canary_script + dogfood_test absent on disk
RED  lifecycle      proofless       — dogfood_test absent on disk
GREEN landing
RED  balance        unwired canary
RED  config-ssot    proofless       — dogfood_test absent on disk
GREEN map-freshness
RED  reconciliation proofless       — reconcile-gate-wired.sh + .test.sh absent on disk
████ PLANE-CANARY reconcile: RED ████
```

**8 of 10 planes RED, fail-closed, right now.** These are exactly the design's `inert/not-wired`
(§2.1) and `quarantined-good` (§2.4) classes. The rig therefore *does* have a working
discover-and-surface leg for the two classes the design calls its novel slices; what it does not
have is anyone closing the 8 findings it already produces.

Design §0 claims the opposite — *"plane-canary.sh + plane-canary-registry.tsv (10 declared
planes, **wired+passing+proven**)"*. That is a factual error, and it is the error the whole
"we need a control plane" argument rests on.

Building a fourth detection layer over a third one that is RED and ignored does not fix
normalization-of-deviance; it adds a surface. The design tags itself
`[[reviews-use-our-own-tools]]`; the tool was not run.

## F5 — BLOCKER (enforceability). No fail-closed rule, no vacuous-pass rule, close-on-absence.

Grepped the design for `fail-clos` / `fail-open`: **zero hits.** Contrast the incumbents, which
state it in their headers: `gate-parity.sh:13` *"Fail-CLOSED: an unrunnable predicate (missing
binary, timeout, parse error) => RED — never silently pass through"*; `plane-canary.sh` prints
`fail-closed` on every RED line.

Three concrete holes:

- **(a) Closes on absence of evidence.** §3.1: *"Evidence GREEN on a cadence tick → auto-closed."*
  The schema (§3.1) has **no `check_cmd` column**. An issue is therefore closed by the discovery
  leg *not re-emitting it*, not by a re-proof. If `discover-issues.sh` crashes, times out, or
  emits zero tuples, **every open issue silently auto-closes and the board renders all-green.**
  That is a textbook fail-OPEN, and it is a *regression* against `reds.tsv`'s enforced doctrine
  (`preflight.sh:5`): *"a red closes ONLY on a passing check_cmd or an explicit RECORDED override
  — never by assertion."*
- **(b) No zero-items-scanned = RED.** Nothing anywhere requires a minimum scanned population, a
  non-empty registry, or a sentinel row. An empty `issue-class-registry.tsv` yields a clean
  board and a GREEN preflight block.
- **(c) The one dependency failure that is handled is handled fail-OPEN.** §9.1: a stale graphify
  graph makes the reachability walk *"warn 'graph stale — inert detection is incomplete' rather
  than silently missing inert components."* A warn is not a RED. The inert class — the highest-value
  class in the design — degrades to advisory exactly when its input is untrustworthy.

## F6 — MAJOR (enforceability). Two of the three red-proofs have no runner.

§8 lists three fail-on-revert tests and what each proves — good — but never says **who executes
them**. The rig has exactly two real runners: `fleet/gate.sh` (globs `fleet/tests/*.test.sh`) and
`fleet/checks/rig-ci-scope.sh:CI_SUITES` (a literal 16-name allowlist, `rig-ci-scope.sh:49`;
verified — `CI_SUITES` is a hand-maintained array, and the file's own comment at :45-48 explains
anything added to `fleet/tests/` later is **not** picked up).

§8 proposes **one** `plane-canary-registry.tsv` row (`sg-issue-control`, for
`issue-board-surface.test.sh`). `discover-issues.test.sh` and `self-heal-engine.test.sh` get no
row, no `CI_SUITES` entry, no runner. They are the design's own "red-proof no runner executed"
class, shipped by name.

`META-GATE-REDPROOF-REACHABLE` already specifies the fix (an S1 sub-assertion that reads both
runners' definitions). The design does not reference it.

## F7 — MAJOR (meta-gate invisibility). Three new checks, zero registry rows required.

§6.1's `owns` lists contain no `RULE-REGISTRY.tsv` row, no `GATE-GAP-LEDGER.tsv` row, and no
requirement to pass `fleet/checks/gate-creation-standard.sh` (the rig's gate-creation meta-gate,
whose traceability is machine-checked). `gate-creation-standard` appears 0 times in the design.

So the plane whose §2.1 purpose is *"find checks that no meta-gate can see"* would itself ship
invisible to the rig's meta-gates. Its own §2.7 (`un-registered component`) would flag its three
new scripts on the first tick — which is either an amusing dogfood or, more likely, three P2 rows
the operator learns to ignore.

Also: `RECONCILER-REGISTRY.tsv` is cited as a desired-source in §2.1 and §2.7. **It does not
exist** (`find` verified). A builder implementing §2.1 literally will read a missing file — and
the design gives no fail-closed rule for that case (see F5).

## F8 — MAJOR (blast radius). "File-disjoint — no collision" is false; all three slices hit the anchor file.

`.gitignore:10` is `fleet/state/*` with a **per-file `!` negation allowlist** (lines 12-45). All
three proposed registries live under `fleet/state/`:

- `fleet/state/issue-board.tsv` (slice 1)
- `fleet/state/issue-class-registry.tsv` (slice 2)
- `fleet/state/heal-templates.tsv` (slice 3)

Each needs its own `!fleet/state/<name>` line. **`.gitignore` is never mentioned in the design**,
and appears in none of §6.1's `owns` lists — so §6.1's headline claim *"file-disjoint — no
collision"* is wrong: all three slices must edit the single most contended file in the repo.
`.gitignore:37-42` says so in as many words:

> *"`.gitignore` is an anchor file, and four separate PRs (#97 #96 #93 #47) each appended their
> own negation here. Serialising them meant re-resolving the same conflict three times…"*

This is `[[anchor-lines-serialize-parallel-work]]` — land the three negations up front or the
slices serialise on merge conflicts.

Note the convention the design breaks: `reds.tsv` and `plane-canary-registry.tsv` live at
`fleet/`, **not** `fleet/state/`, precisely to avoid this. The `ISSUE-BOARD-SURFACE` ticket got
this half-right (`fleet/issue-board.sh` at `fleet/`, but the tsv at `fleet/state/`).

## F9 — MAJOR (boundary + implementability). §4.4 reaches into the PUBLIC product repo.

§4.4: *"Reuse `ReviewerCircuitBreaker` from `src/charon/failover.py:73-142`."* Verified: that file
does **not** exist in `charon-private`; it is in `/home/stack/code/charon` — the PUBLIC product
repo that must ship standalone.

Two problems: (a) a rig bash script (`fleet/checks/self-heal-engine.sh`) cannot use a product
Python class without either importing across the rig/product boundary or copying product code
into the rig — both are `[[product-vs-build-rig-boundary]]` violations, and neither is specified;
(b) it is unactionable as written — no import path, no invocation shape, no persistence story for
breaker state across bash processes.

The incumbent design solves this with rig-native mechanisms it verified: `loop-guard.sh`
(durable `state/loop-guard/<id>` quarantine after N zero-commit re-claims — the anti-fork-bomb
rail) and `lease-enqueue.sh`'s flock + `state/enqueued/<id>` exactly-once marker. Neither appears
in the branch design.

## F10 — MAJOR (implementability). The design contradicts the tickets it governs, on every slice.

The three build-slice tickets **already landed on master** (commit `99c709c`), so the design is
not "spawning" them — it must match them. It does not:

| slice | design §6.1 `owns` | ticket `owns` (on master) |
|---|---|---|
| ISSUE-BOARD-SURFACE | `fleet/checks/issue-board-surface.sh`, `fleet/state/issue-board.tsv`, MODIFY `fleet/preflight.sh` | `fleet/issue-board.sh`, `fleet/state/issue-board.tsv`, `fleet/tests/issue-board.test.sh` |
| KS29-DISCOVERY-LEG | `fleet/checks/discover-issues.sh`, `fleet/state/issue-class-registry.tsv`, `fleet/tests/discover-issues.test.sh` | `fleet/checks/registry-discovery.sh`, `fleet/state/component-registry.tsv`, `fleet/tests/registry-discovery.test.sh` |
| ISSUE-SELF-HEAL-RULES | `fleet/checks/self-heal-engine.sh`, `fleet/state/heal-templates.tsv`, `fleet/tests/self-heal-engine.test.sh`, MODIFY `fleet/preflight.sh` | `fleet/issue-heal.sh`, `fleet/state/self-heal-allowlist.tsv`, `fleet/tests/issue-heal.test.sh` |

**Every path in slices 2 and 3 differs. Five of six in slice 1.** Plus: design §6/§6.1 says KS29
*"Depends on #1 (ISSUE-BOARD-SURFACE)"*; the ticket's `depends_on:` is **empty**. And `preflight.sh`
(MODIFY, in two slices) is in nobody's `owns`.

A competent builder following this doc creates files their ticket does not own → `owns`-tracked
RED at land, or a silent collision between slices 1 and 3 both editing `preflight.sh`. **This
alone answers question 3: no, two builders would not produce the same thing.**

## F11 — MINOR (accuracy). Load-bearing references are wrong.

Every one verified:

| design says | actual |
|---|---|
| `preflight.sh:878` is the scan dispatch (§2.1, §3.1 sample row, §6.2) | :878 is inside `startup_budget_selftest`; the dispatch chain is at **:895** |
| `fleet/state/plane-canary-registry.tsv` (§2.1) | `fleet/plane-canary-registry.tsv` |
| `reds.tsv` under `fleet/state/` (implied §2.2) | `fleet/reds.tsv` |
| `GATE-GAP-LEDGER.md` (§2.1) | `fleet/state/GATE-GAP-LEDGER.tsv` |
| `RECONCILER-REGISTRY.tsv` (§2.1, §2.7) | **does not exist** |
| `fleet/checks/reconcile-gate-wired.sh` exists (implied by §3.3 "plane-canary reconcile leg") | absent on master; unlanded on `feat/reconcile-gate-wired` |

`[[confirm-dont-trust-documentation]]`: the design's concrete anchors were not confirmed against
the tree. The doc it replaces tagged every such claim `[V]` with the line it read.

## F12 — MINOR (acceptance testability). Good bones, one unnamed command.

The ticket's `accept:` is better than most — the e2e dogfood clause (*"seed a real issue of each
class → it appears on the issue-board → surfaces at SessionStart → (for a safe class)
auto-launches a reviewed fix"*) is objectively checkable, and the fail-on-revert clause is a real
falsifier. `reviewer != builder` is checkable.

Two soft spots:
- *"the plane is FULLY + COMPLETELY wired (no built-but-inert leg)"* names no command. It should
  be a literal: `bash fleet/plane-canary.sh reconcile` exits 0 for the `sg-issue-control` row,
  **and** `bash fleet/checks/gate-creation-standard.sh` passes for all three new checks.
- Nothing in `accept:` requires **non-duplication** with `reds.tsv`, which is the failure mode
  most likely to be declared satisfied while wrong.

## F13 — MINOR (scope + review independence).

Scope is essentially clean: the diff is the design doc plus `docs/review-log/SG-ISSUE-CONTROL-PLANE.md`.
The review-log is a rig convention (other tickets — `RECONCILE-REVIEW-GATE`, `REPO-FIELD-REQUIRED`,
`REVIEW-DISPENSATION-CANARY` — list it in `owns`), so the file is legitimate; the ticket's `owns:`
should list it. No stray code, no product-repo changes.

But the review-log is a **self-review**: *"Author model: deepseek-v4-pro / Reviewer: operator"*,
verdict `CONFIRMED-CLEAN`, with seven bullets that restate the design's own §11 checklist. It
asserts *"Open seams flagged (§9) … None are faked-closed"* while §9.1 fails open (F5c), and
*"fail-on-revert (§8) … one dogfood per slice"* without noticing two have no runner (F6).
This is builder==reviewer — the exact independence rule the design itself mandates in §4.1
(`reviewer_must_not_be = builder`). A design that ships a self-attested CONFIRMED-CLEAN should
not be the record for a plane whose purpose is catching false-greens.

---

## REQUIRED CHANGES (to reach LAND)

1. **Restore or merge the 109-line incumbent** at `fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md`.
   Its `[V]`-tagged reuse inventory, its *"Fold, don't fork / two reconcilers must not drift"*
   ruling, its ⚠-unbuilt-KS29 flag, and its `review-pool`/`loop-guard`/`lease-enqueue` safety
   rails must survive into whatever lands. Add the `.gitignore` negation so the file is
   `git add`-able rather than force-added.
2. **Re-scope slice 1 from "new board" to "extend `reds.tsv`."** Give the ~6 advisory detectors in
   `cmd_detect` a `check_cmd` + auto-register call, reusing the `board_gate` / `done_merge_gate`
   machinery. If a second board is genuinely required, argue it adversarially against
   `preflight.sh:1-8`'s close policy — that argument is currently absent.
3. **Land `feat/reconcile-gate-wired` (`d603494`) before authoring slice 2**, and address
   `INERT-WIRING-ENFORCEMENT-DURABLE`'s standing bar (*explain why the prior gates decayed*)
   before adding another gate to that class.
4. **Close the 8 RED plane-canary rows, or state in the design why a new plane precedes fixing
   the one that is already shouting.**
5. **Add a fail-closed section**: unreadable/absent registry ⇒ RED; discovery-leg non-zero exit ⇒
   RED (never all-clear); **zero items scanned ⇒ RED**; stale graphify ⇒ RED for the inert class,
   not warn. Add a mandatory `check_cmd` column so issues close on re-proof, never on absence.
6. **Pin the runner for all three red-proofs** — `*.test.sh` naming (for `fleet/gate.sh`'s glob)
   plus explicit `CI_SUITES` entries, per `META-GATE-REDPROOF-REACHABLE`.
7. **Add registry rows to `owns`**: `RULE-REGISTRY.tsv`, `plane-canary-registry.tsv` (one row per
   slice, not one total), and `.gitignore` negations — landed as an anchor commit up front.
8. **Reconcile §6.1 with the three landed tickets** (paths + `depends_on`), and assign
   `preflight.sh` to exactly one slice.
9. **Replace §4.4's product-repo `ReviewerCircuitBreaker`** with the rig-native `loop-guard.sh` +
   `lease-enqueue.sh` exactly-once marker.
10. **Get an independent review on the review-log** (reviewer ≠ author model).

---

## What I verified by execution/search vs. by reading

**Executed (facts, not inference):**
- `bash fleet/plane-canary.sh reconcile` → 8/10 planes RED (F4). Full output captured above.
- `git ls-files --error-unmatch` + `git check-ignore -v` + `diff` on
  `fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md` → untracked, ignored, and **different** from the
  branch version (F1).
- `git diff --stat origin/master...HEAD` → 2 files, +666 (F13). `git status --porcelain` → clean.
- `git log --oneline -1 d603494` + `git branch -a` → the reconcile-gate-wired detector commit and
  its branches exist on `origin` and `gitea` (F3).
- `ls` → `fleet/checks/reconcile-gate-wired.sh`, `fleet/tests/reconcile-gate-wired.test.sh`,
  `src/charon/failover.py` all absent from the rig (F3, F9).
- `sed -n '73,80p' /home/stack/code/charon/src/charon/failover.py` → `ReviewerCircuitBreaker` is in
  the product repo (F9).
- `find` → no `RECONCILER-REGISTRY.tsv`; `GATE-GAP-LEDGER` is `.tsv` (F11).
- `grep -c` over the design for `reds.tsv` (1), `reconcile-gate-wired` (0), `INERT-WIRING` (0),
  `META-GATE` (0), `gate-creation-standard` (0), `rig-ci-scope` (0), `CI_SUITES` (0),
  `fail-clos`/`fail-open` (0) (F2, F3, F5, F6, F7).
- `fleet/reuse-check.sh` — attempted on the three proposed paths; it requires the candidate file
  to exist on disk and raised `FileNotFoundError`, so it **cannot** be run against a
  design-stage path. Reuse was established by direct search instead. (Worth a rig ticket: the
  tool is unusable for the design-review case it is most needed for.)

**Read (source of the structural findings):**
- `fleet/preflight.sh` (header, `cmd_scan`/`add`/`close`/`run_check`, `cmd_detect`, `board_gate`,
  `executor_gate`, `detect_needs_push`, `done_merge_gate`, dispatch) — F2, F5, F11.
- `fleet/reds.tsv`, `fleet/plane-canary-registry.tsv`, `fleet/plane-canary.sh` header — F2, F4.
- `.gitignore:1-45` — F8.
- `fleet/board/{RECONCILE-GATE-WIRED,INERT-WIRING-ENFORCEMENT-DURABLE,META-GATE-REDPROOF-REACHABLE,
  UNIFIED-PLANE-CANARY-FRAMEWORK,ISSUE-BOARD-SURFACE,KS29-DISCOVERY-LEG,ISSUE-SELF-HEAL-RULES}.md`
  — F3, F6, F10.
- `fleet/checks/{gate-parity,rig-ci-scope,graphify-freshness}.sh` headers, `fleet/foreman-cadence.sh`
  — F5, F6.
- Both versions of the design doc in full, and the review-log fragment — F1, F13.

**Not verified (out of scope / would need a build):**
- Whether graphify's graph is complete enough for the reachability walk. §9.1's own seam; I
  confirmed `graphify` is installed and `foreman-cadence.sh:162 cmd_graphify_cadence` is wired,
  but did not assess extractor coverage.
- Whether `UNIFIED-PLANE-CANARY-FRAMEWORK` is truly retired: its ticket is now a redirect stub
  (`owns: fleet/state/UNIFIED-PLANE-CANARY-REDIRECT.md`, priority 5) pointing at this design. Note
  for the caller — the brief describes it as *"blocked by this, launched immediately after"*, but
  the board says superseded-and-stubbed. Worth confirming which is intended before launching.
