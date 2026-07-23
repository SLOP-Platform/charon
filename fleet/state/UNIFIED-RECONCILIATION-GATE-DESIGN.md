# UNIFIED-RECONCILIATION-GATE — design (2026-07-23, manager-authored for operator review)

> Deliverable for `UNIFIED-RECONCILIATION-GATE-DESIGN` (RANK-0 LEAD, P:0, operator-confirmed
> 2026-07-23 — stass-allie handoff action #1). **DESIGN ONLY** — spawns one-lens build tickets on
> operator approval; nothing here is built yet. Durable root fix for the class the operator has
> repeatedly escalated: **built/planned-but-not-wired, norm-exists-but-unenforced,
> merged-but-not-retired**. Desired==actual reconciliation. RED on drift. Required-check + timer.
> Tags: `[[gates-must-actually-run]]` `[[no-rig-as-product-adopt-dont-handroll]]`
> `[[decomposed-by-design-not-reactive]]` `[[detection-ticketed-never-built]]`
> `[[eval-system-under-repair]]` `[[document-model-self-report-lies]]`.

## 0. The shape of the problem (why a gate, not a checklist)

Three failure shapes share one root — **desired state and observed state drift apart in silence**:

| Class | What "desired" claims | What "actual" shows | Real incident (this repo) |
|---|---|---|---|
| **merged-but-not-retired** | ticket done; board cleared | PR merged, branch gone, `board/<id>.md` still `tier:strong` + open | `reconcile-merged` AMBIGUOUS exit 1 (the class that wrote §1.1 of this doc) |
| **built-but-not-wired** | detector/capability exists in tree | nothing invokes it from a real firing layer | `check_catalog_case_quant.py` shipped wired-into-zero-gates (GATE-GAP-LEDGER `built-but-inert`) |
| **norm-but-unenforced** | ADOPT-decision / norm in EVAL-REGISTRY / rule-registry | nothing proves it fires at decision-time | EVAL-REGISTRY #61 adopted 2026-07-21; never invoked; folded into review-gate axis (F5) |

The cure is **one substrate that asks the same question for every class**: *for each declared
piece of desired state, what is the actual set today, and do they agree?* Same substrate, three
inputs, one verdict, one wiring point. That's the reconciliation gate.

**Folding scope** (per stass-allie F5 directive, action #3): the **review-gate** (BLAST-TIER-ENFORCEMENT-DESIGN
Consumer A) and the **gate-blindness-ledger** are not a parallel build — they are *an axis* of
this same engine (`declared-review-required vs review-actually-happened`) and the reconciliation
gate's own self-diagnosis when it ships blind to a defect class.

**Folding scope, taxonomy fix** (F2): the old `tier = path-pattern` map was gameable — an unknown
`src/charon/new.py` matched nothing → tier 0 → no review. **Fail closed**: any path the classifier
does not recognize is treated as the highest tier it could plausibly be (`tier = max(recognized
tier, hot-path)` for unknown paths in `src/charon/`). This is the same posture Kubernetes
admission controllers take: deny on unrecognized policy; do not deny on absence.

## 1. v1 SCOPE — three cheap, high-value reconcilers

Each reconciler has the same five fields: **desired-source**, **actual-source**, **drift-algorithm**,
**RED condition**, **drift-primitive** (the KS29 leg — the algorithm primitive from the registry
inventory, so future reconcilers are data rows, not scripts — KS20 anti-accretion).

### 1.1 `board↔PR↔done` — the merged-but-not-retired / false-done class

- **desired-source:** every ticket's `tier:`/`branch:`/`owns:` in `fleet/board/*.md` + `fleet/board/archive/*.md`,
  in particular the `done:` marker convention. The board is the desired "this ticket is closed"
  state.
- **actual-source:** GitHub PRs whose `mergeStateStatus` ∈ {MERGED, CLEAN-merge-complete} and whose
  head branch matches a ticket's `branch:`; cross-referenced with `done.sh` proof records
  (`merged:#pr`, `--merged-sha`).
- **drift-algorithm:** set-diff bidirectional (KS29 primitive: `set-diff/bidirectional`) over
  `(merged-PR-set, open-ticket-set)` joined on `branch ↔ ticket-branch`. The fan-in from PR-file
  to ticket is governed by the existing `ticket_for_pr()` indexing with the **CREATION-PR
  GUARD** already in `reconcile-merged.sh:194-222` (a merged PR that adds the ticket's OWN
  `fleet/board/<id>.md` but delivers none of its `owns:` is a creation, not a completion —
  created != done).
- **deterministic disambiguation (root fix for the AMBIGUOUS wedge):** when a merged PR's file
  set is `owns:`-owned by N>1 tickets, the AMBIGUOUS class MUST resolve by **ordered proof**,
  not by silent bail:
  1. **branch↔ticket match (primary):** if any of the candidate tickets' `branch:` equals the
     PR's head branch, that's the ticket (unique, deterministic). Today's loop already prefers
     this and it works for the common case.
  2. **PR-title / commit-message ticket-id match (secondary):** if the branch-match fails,
     extract the PR title + merge-commit subject (via `gh pr view --json title,body` and
     `git log -1 --format=%s`) and match the ticket id substring (e.g. `BLAST-TIER-ENFORCEMENT`
     or the kebab-case ticket-id like `KS24` or `WORKLOOP-...`). This is the documented
     escape hatch for shared-owned files and is the *only* path that may resolve to a ticket
     when ownership overlaps.
  3. **merged-sha proof via `done.sh --merged-sha`:** if neither 1 nor 2 yields a unique
     ticket, the PR's `merged_sha` is recorded in a per-ticket **REVIEW** ledger
     (`fleet/state/reviewed/<id>`) by the operator when they adjudicate manually; the next
     reconcile pass picks the ticket whose ledger row matches the sha. Until the operator
     adjudicates, the PR stays `STATUS=NEEDS-MANUAL-ADJUDICATION` (NOT `done` — never
     auto-close on a hash guess). The AMBIGUOUS class becomes a **deterministic RED with
     an instruction**, not a silent bail.
- **RED condition:**
  - **R-A:** any open board ticket whose `branch:` matches a merged-but-not-`done` PR (fail
    in 20-of-recent-rig-tickets, the literal class on the call-stack when this LEAD was
    boarded). The action: call `done.sh --merged-sha` for the ticket (auto-close with proof).
  - **R-B:** any merged PR whose branch matches no ticket's `branch:` AND whose files do
    not touch any `fleet/board/*.md` (operator-PR-without-ticket — the inverse drift;
    somebody merged without a ticket). The action: RED with a "create ticket or revert" prompt.
  - **R-C:** any open ticket whose `branch:` has no recent commit AND no open PR (stale
    branch — the "is this even alive?" drift). The action: warn, do not auto-close (the
    "is alive" question is judgment, not drift).
- **drift-primitive:** `set-diff/bidirectional` (KS29 leg). The disambiguation itself is a
  *ordered fan-in resolver* — three signal sources, deterministic precedence, fall-through to
  manual adjudication. It is NOT a new primitive; it composes `set-diff` (the desired↔actual
  join) with the existing `branch-index`/`owns-index` from `reconcile-merged.sh:130-180`.
- **separation of concerns:** this reconciler does NOT decide what `done` means; that is owned
  by `done.sh` + the `merged:` proof field. It does NOT enforce review; that is the review-gate
  axis (§2.1). It does NOT retire stale tickets; that is `retire-done.sh` and is a separate
  fan-in.

### 1.2 `owns-tracked` — the durable-design-vanishes-untracked class

- **desired-source:** every ticket's `owns:` set (parsed from `fleet/board/*.md` +
  `fleet/board/archive/*.md`, kebab-trimmed). For tickets with no `owns:` but a stated
  `note: ... durable design ...` (the pattern `BLAST-TIER-ENFORCEMENT-DESIGN.md` etc. follows),
  the file path is *implicitly* part of the deliverable.
- **actual-source:** `git ls-files` + `git status --porcelain` + `git check-ignore` for the
  union of (a) every `owns:` path, (b) every `fleet/state/*` durable design doc (the
  operator-confirmed set: ANTI-CLOBBER-FIX-REPORT, BENCH-PROVISIONAL-SCORING-DESIGN,
  BLAST-TIER-ENFORCEMENT-DESIGN, BRANCH-PROTECTION-NOTE, EVAL-PIPELINE-DESIGN, EVAL-REGISTRY,
  EVAL-TAXONOMY, GRADER-PROVISION-NOTE, HANDOFF-REVIEW-quinlan-vos, KSF-LINTER-TOOLS-REVIEW,
  MODEL-TESTING-ADVERSARIAL-REVIEW, ON-DEMAND-TOOL-LEDGER, PATH-C-DOGFOOD-EVAL,
  PREFLIGHT-DESIGN-V2, PRIORITY-LADDER, REACHABILITY-AUDIT, REDS-CORPUS, REGISTRY-CANDIDATES,
  REVIEWS-stass-allie, ROADMAP, RULE-REGISTRY, RULE-SYNC-REGISTER, S8-GRACEFUL-DEGRADE-DESIGN,
  SESSION-CTX-HOOK, SSOT-REGISTRY).
- **drift-algorithm:** set-membership with git-tracked-state (`git ls-files` for "tracked",
  `git status --porcelain` for "untracked-but-on-disk", `git check-ignore` for "gitignored").
  The desired state is the *union* of owned paths + durable design catalog; the actual is the
  per-file git status. Each file lands in exactly one bucket.
- **RED condition:**
  - **R-D:** a ticket `owns:` path is `untracked` (file on disk, not in `git ls-files`, not
    gitignored) — almost always a missed `git add` from a ticket that wrote a file but never
    staged it. Action: `git add <path>`. This is the silent-fail class.
  - **R-E:** a ticket `owns:` path is `gitignored` AND the `.gitignore` does not have a
    matching `!` exemption — the durable design vanished. This is the literal class on the
    call-stack when this LEAD was filed (the `fleet/state/*` blanket gitignore ate the
    doc; the operator-confirmed workaround was `git add -f` per the stass-allie handoff).
    Action: **RED with two surgical options surfaced**: (i) add an `!` exemption to
    `.gitignore` (owner of `.gitignore` = whoever is currently editing it; this gate
    does NOT auto-edit it), (ii) move the doc to a tracked-by-default location (the
    durable fix). The gate surfaces the choice; it does not pretend to choose.
  - **R-F:** a durable design catalog entry's file is not in any ticket's `owns:` AND not
    in `.gitignore` (orphan design doc — design-of-record with no accountable owner).
    Action: RED with a "who owns this?" prompt to the operator.
- **drift-primitive:** `subset/schema-conformance` (KS29 leg) — every element of a
  *known set* (owned paths ∪ durable-design catalog) MUST appear in another known set
  (git-tracked, or gitignored-with-exemption). The "two surgical options" for R-E are a
  POLICY choice the gate makes legible; the algorithm itself is the membership check.

### 1.3 `gate-declared-vs-actually-wired` — the wired-but-never-run class

- **desired-source:** every gate/check/rule declared in:
  - `fleet/checks/*.sh` + `fleet/checks/*.py` (the rig check suite)
  - `tools/check_*.py` + `tools/check_*.sh` (the product check suite, cross-repo)
  - entries in `fleet/state/RULE-REGISTRY.tsv` whose `status` ∈ {ACTIVE, ENFORCED}
  - entries in `fleet/state/EVAL-REGISTRY.md` whose `verdict` = ADOPT and
    `enforced_in` is non-empty (the `tools/...` or `fleet/checks/...` path)
- **actual-source:** the set of paths actually executed by a real firing layer:
  - **Rig firing layer:** `fleet/preflight.sh` scan dispatch (`preflight.sh:779`-ish —
    the existing chain), `fleet/land.sh` pre-conditions, `fleet/board/validate_board.sh`,
    `fleet/fleet-ci/rig-ci.yml` (when wired), `fleet/hooks/pre-*.sh`. The gate parses
    these scripts for the literal invocation of each registered check; the set of
    invocations is the "actually fires" set.
  - **Product firing layer:** `.github/workflows/*.yml` (each `run:` step that invokes a
    check), `tools/check_*.py` chain in `make` / CI, native GitHub branch-protection
    required-checks (the *strongest* signal — a check in branch protection always fires
    for protected branches on public).
  - The product-firing-layer ground truth is **only** machine-checkable on the product
    repo (`/home/stack/code/charon`); the rig fires `fleet/board/validate_board.sh` which
    already covers a subset.
- **drift-algorithm:** static-grep + cross-reference. For each declared check path P in
  the desired-source, search the firing-layer source for the basename of P being invoked
  (allow substring/alias matches for known wrappers like `gitleaks.sh` → `gitleaks`).
  Build the (declared, fired) set pair; compute set-difference.
- **RED condition:**
  - **R-G:** a check is in the desired-source but NOT in any actual-source — the
    `built-but-inert` class (the literal GATE-GAP-LEDGER row from 2026-07-14 on
    `tools/check_catalog_case_quant.py`). Action: RED with a "wire this into `<firing
    layer>` at `<location>`" instruction. The reconciler does not auto-wire (auto-wiring
    is a product change, not a drift check); it makes the gap visible.
  - **R-H:** a check is in the actual-source but NOT in the desired-source — the
    "running but not registered" mirror. Catches ad-hoc shell snippets that became load-
    bearing without being declared. Action: RED with a "declare this" prompt.
  - **R-I:** a check is declared + fired, but the firing-layer reference is in a
    *gated-only-on-master* path while the change being reconciled is on a feature
    branch. The deploy-context-blind class (GATE-GAP-LEDGER 2026-07-15). Action:
    RED with the *context-of-validity* annotation surfaced.
- **drift-primitive:** `graph-reachability` (KS29 leg) — declared nodes must be
  *reachable* from the firing-layer root (preflight / land.sh / CI). Reachability is
  a graph walk; "wired but never reached" is the red. This generalizes to
  staleness-probe-TTL when the firing layer is timer-driven (the cadence check; see §3).

## 2. Folded-in axes (review-gate + fail-closed taxonomy)

### 2.1 Review-gate axis (folds BLAST-TIER-ENFORCEMENT Consumer A)

- **desired-source:** every change in the reconcile window whose `blast_tier ≥ hot-path`
  (the BLAST-TIER substrate — one home in `src/charon/blast_tier.py`, consumed by both
  the rig and the product). The substrate already exists as a designed-but-unbuilt
  module (BLAST-TIER-ENFORCEMENT-DESIGN §0). For v1, we treat the `tier` field of the
  ticket + a path-pattern fallback as a sufficient proxy IF the substrate is not yet
  built; once the substrate lands, the path-pattern fallback is removed.
- **actual-source:** `docs/review-log/<id>.md` (a per-ticket review-log fragment, the
  operator-merged form) + `fleet/state/reviewed/<id>` (machine-readable marker:
  `reviewed_sha=<sha>  author_model=<m>  reviewer=<operator|model-id>  verdict=<CONFIRMED-CLEAN|FIXES|BLOCK>
  findings=<n>`).
- **drift-algorithm:** content-hash match (KS29 leg `content-hash/checksum`) — the review's
  recorded `reviewed_sha` MUST equal the merge commit's `sha`. The marker MUST be
  present, the SHA MUST match, the reviewer MUST NOT be the author model (or the
  reviewer MUST be the operator). This is the same "fail closed on unknown" posture
  the taxonomy fix adopts.
- **RED condition:**
  - **R-J:** a `≥hot-path` change has no review-log fragment AND no `reviewed/<id>` marker
    at its merge SHA. Action: BLOCK (this is the consumer-A BLOCK condition).
  - **R-K:** a review-log fragment exists but the `reviewed_sha` does NOT match the
    merged commit (the review was for a different SHA — drift). Action: BLOCK + "re-review
    at current HEAD."
  - **R-L:** a review-log fragment exists with `verdict=FIXES` but no follow-up review
    after the fixes were committed (review→fix→review loop not closed — also a
    fingerprint-able doom loop; reuse `ReviewerCircuitBreaker` from
    `src/charon/failover.py:73-142` per BLAST-TIER §1).
- **drift-primitive:** `content-hash/checksum` (KS29 leg). The review-gate is a hash
  match; the doom-loop detector is a TTL probe (KS29 leg `staleness-probe-TTL`).

### 2.2 Fail-closed taxonomy (F2 fix)

The BLAST-TIER substrate must adopt the same fail-closed posture this gate demands of
itself: any path or file the classifier does not recognize is treated as
`tier = max(unknown, hot-path)`. Concretely: an unknown `src/charon/<x>.py` matches
nothing in the regex map → defaults to `hot-path` (or higher if any unknown path falls
in a `src/charon/{forwarder,proxy_server,api,router,capability,balance,meter,billing,
egress,keys,secret,acl}*.py`-prefix directory). An unknown file under `docs/` or
`fleet/` is tier 0 (`doc`/`tooling`). An unknown `work_class` is treated as
`hot-path` (the highest non-explicit tier). This kills the gameable-by-PR-splitting
class at the source; the gate-blindness-ledger (GATE-GAP-LEDGER's role here) flags
any class the substrate cannot yet classify so the operator can extend the map.

### 2.3 PARKING the grading consumer (BLAST-TIER Consumer B)

The grade-substrate is empty today: `grades.py` returns 0 real-outcome grades for all 6
models (REVIEWS-stass-allie F1). Per `[[eval-system-under-repair]]`, we PARK the
multi-axis grade + blast-tier routing + assign.py eligibility filter behind the
EVAL-PROMOTION-GATE / EVAL-PIPELINE repair. The reconciliation-gate does NOT depend
on grades.py for v1; the review-gate axis (§2.1) operates on review-log + marker
exclusively. When the grade substrate is repaired, the **single trust-of-green
back-link** (a PASS that review overturned) is a future v2 axis — not a v1 dependency,
and explicitly NOT a circular dep. This is the v1 / v2 split: gate it can be
self-sufficient; the grading consumer needs the substrate.

## 3. Enforcement — required-check + timer + the wiring

### 3.1 Rig side (the fleet itself)

Three enforcement points, no fourth:

1. **`fleet/preflight.sh scan` dispatch (the existing chain):** add `bash fleet/checks/
   reconcile-board-pr-done.sh` + `bash fleet/checks/reconcile-owns-tracked.sh` +
   `bash fleet/checks/reconcile-gate-wired.sh` + `bash fleet/checks/reconcile-review-
   gate.sh` to the `preflight.sh:779`-ish scan chain, immediately after
   `reconcile-merged.sh` and BEFORE the existing `board_gate`. The order matters:
   `reconcile-merged` writes done-markers (idempotent), the new reconcilers read those
   markers + their own evidence, then the existing gates see the post-reconciliation
   board. fail-on-revert tests for each new check live in `fleet/tests/`. (The
   pre-existing test class `fleet/tests/reconcile-merged.test.sh` is the model.)
2. **`fleet/land.sh` required-path pre-condition:** add a final pre-merge block (alongside
   the existing AUTONOMOUS lever + marker check) that re-runs all four reconciliation
   checks against the head SHA's tree + the live state. If ANY is RED, refuse to
   mark-done or to advance to merge. (The exact verb depends on whether the land.sh
   variant is autonomous or operator-merged; both paths must call this.)
3. **A timer (cadence check) — `fleet/checks/reconcile-timer.sh`:** runs the same four
   checks on a fixed cadence (e.g. cron / systemd timer / `foreman.sh` heartbeat tick)
   independent of preflight, so drift that develops between runs (e.g. a doc added
   untracked overnight, a merged PR whose branch-rename loses the index) is caught
   at the next tick, not at the next `land.sh`. The cadence itself is a registry row
   (KS29 — `interval_seconds` is data, not code).

### 3.2 Public product side

Native GitHub branch protection with a required-check named `reconcile-gate`
(or its decomposed successors) on the default branch. The check is implemented as a
GitHub Actions step (e.g. `tools/check_reconcile_gate.py` in
`.github/workflows/reconcile.yml`); the required-check name is the human-visible
invocation. This is free on public repos and is the strongest available signal
("a green cannot land without the check running"). For the private rig, native
branch protection is 403/paywalled (verified — stass-allie F3); the rig uses
marker+land.sh+CI as the substitute (F3 noted this).

### 3.3 The flagged open seam — `land.sh` `git -C` bypass

**OPEN SEAM, not faked-closed.** The `land.sh` chain refuses to mark-done, but a
direct `git -C <other-worktree> merge` (or any push to master that bypasses
land.sh) lands a change without the check running. On the **public product repo**
this is closed by GitHub native required-check (§3.2). On the **private rig** the
closure depends on the **Gitea-primary migration** (the planned `charon-ci` runner
+ server-side pre-receive hook). Until that migration lands, the only available
mitigations are:

- a **post-receive hook on the rig's bare repo** that re-runs the four checks and
  emits a RED notification (does NOT block — the hook is a detector, not a
  gate). Actionable for the operator, not auto-rolling-back.
- a **timer-based reconcile** that catches any direct-merge drift at the next tick
  and surfaces it as RED-in-the-board.

**Explicit non-fix:** do NOT pretend `land.sh` is a closed gate on the rig until
the Gitea migration lands. Per `[[detection-ticketed-never-built]]` — flag the
seam in the README + in `GATE-GAP-LEDGER` as `status=open; closure=depends-on-
gitea-primary` so a future reviewer cannot ship a false-green claiming
reconciliation is enforced. This seam is the explicit, operator-confirmed
limitation of v1.

## 4. Build posture — adopt-first, open-seams, anti-accretion

### 4.1 The reconciliation LOGIC — implement-as-pattern (VALIDATED)

The stass-allie WLS-7 review (2026-07-23) **validated** the implement-as-pattern
posture: "no external tool reconciles Charon's own state; K8s/Terraform
desired-vs-observed is the pattern." This is the *sanctioned* hand-roll — the
algorithm is from the public literature, not a from-scratch invention. Cite
this validation in each per-reconciler ticket's accept text. The drift-algorithm
primitives (`set-diff/bidirectional`, `content-hash/checksum`, `subset/schema-
conformance`, `graph-reachability`, `staleness-probe-TTL`) are from the KS24 /
KS29 inventory — they are the documented vocabulary this gate composes from.

### 4.2 The glue / harness — OPEN SEAM pending WORKLOOP-INTEGRITY-STACK-SPIKE

The harness that runs reconciliation on a timer and feeds the results to
downstream consumers (e.g. ao, Windmill, a Slack-bot) is **deliberately not
chosen** in this design. The WORKLOOP-INTEGRITY-STACK-SPIKE is still finalizing
its adopt-first verdict (adnanh/webhook, ao, Windmill, pydantic/cerberus are the
candidates). The reconciliation gate must be **independent** of that verdict —
its checks are pure-Python / pure-bash; the firing layer (cron / systemd / a
harness) is a single shim. Proceed NOW; plug the harness later.

### 4.3 KS29 leg discipline — anti-accretion

Every reconciler in v1 is **one row in a registry**, not a new script. The
registry schema (proposed, will land with the first build ticket):

```
id                  path-pattern         desired-source-grammar       actual-source-grammar    primitive         severity
BOARD_PR_DONE       fleet/board/...      board:<id>:<tier>:<branch>   gh:pr:<branch>:merged    set-diff          P0
OWNS_TRACKED        <path-glob>          owns:<ticket-id>:<path>      git:status:<path>        subset-membership P0
GATE_WIRED          <check-path>         registry:<checks>            fired-in:<layer>         graph-reach       P0
REVIEW_GATE         <change>             blast_tier:>=hot-path        reviewed/<id>:marker     content-hash      P0
```

Adding a reconciler = appending a row + (if a new primitive is needed) registering
the primitive first. This is the **same shape** the rule-coverage meta-gate
(PR #119 / `tools/check_gate_registry_execution.py`) uses for gates. Future
reconcilers are data, not scripts. (KS20 anti-accretion: this gate MUST run on
itself, dogfooding the very pattern it implements — see §6.)

## 5. v2 — explicitly deferred, named so they don't get smuggled in

These are real, they are known, they are NOT v1. v1 deliberately defers them.
Listing them here prevents a v1 build ticket from scope-creeping.

| v2 reconciler | why deferred |
|---|---|
| **ADR / roadmap / config-manifest / registry drift** | the class exists (KS24 lists it; the rule-coverage / rule-sync registers already partial-cover it); the full desired-vs-actual wiring depends on the EVAL-PROMOTION-GATE substrate being repaired, and on `REVIEWER-DOGFOOD-REDS` having grown enough that a per-ADR review log is meaningful. v1 catches the structural drift (owns-tracked, gate-wired); the *content* drift waits. |
| **R44 e2e observable-effects** ("prove a feature is EXERCISED, not merely reachable") | an entire eval / harness layer; orthogonal to the structural drift. Belongs in its own LEAD once the EVAL-PIPELINE is repaired. |
| **Grading consumer (BLAST-TIER B)** | empty substrate today (F1); explicitly parked. The reconciliation-gate does NOT grade work — it grades the gates that gate the work. The grade-the-work consumer is downstream and unblocked when the eval-substrate is repaired. |
| **Harness-specific timers (ao / Windmill / pydantic)** | depends on the WORKLOOP spike verdict; deliberately not in v1. |
| **Cross-repo blast_tier.py single-home enforcement** | the 2-repo boundary issue (F6); wants a separate ticket that designs a publish/consume model before the substrate migrates. |

## 6. Build backlog (decomposed — one lens per ticket, spawns on approval)

Each is a separate ticket. Sequence is the BUILDER'S choice; v1 = all of §1 + §2.1
+ §2.2. §2.3 / §3.3 / §5 are tracked as separate concerns (parked / open-seam /
deferred respectively).

| # | ticket id | lens | one-liner |
|---|---|---|---|
| 1 | `RECONCILE-SUBSTRATE` | substrate | One registry (`fleet/state/RECONCILER-REGISTRY.tsv`) + schema (per §4.3) + `fleet/checks/reconcile_lib.sh` with the four primitive algorithms as functions (set-diff, content-hash, subset, graph-reach, staleness-TTL). The substrate everything else reads. Dogfoods KS20. **Substrate blocker — everything else depends on it.** |
| 2 | `RECONCILE-BOARD-PR-DONE` | §1.1 | The merged-but-not-retired / false-done reconciler. Re-uses the `reconcile-merged.sh:130-180` indexing + the AMBIGUOUS disambiguation ladder (branch↔ticket, title-match, merged-sha proof). Test fixtures: a merged PR with no ticket (`R-B`); a ticket whose `branch:` matches a merged PR (`R-A`); a stale branch (`R-C`). |
| 3 | `RECONCILE-OWNS-TRACKED` | §1.2 | The durable-design-vanishes class. Walks the `owns:` set + the durable-design catalog, checks git-tracked status. Test fixtures: untracked file (`R-D`); gitignored-without-exemption (`R-E`); orphan design doc (`R-F`). **The R-E case must reference THIS doc as its own example — a self-eating dogfood.** |
| 4 | `RECONCILE-GATE-WIRED` | §1.3 | The wired-but-never-run class. Cross-references `fleet/checks/*` + `tools/check_*` + `RULE-REGISTRY.tsv` + `EVAL-REGISTRY.md` against `preflight.sh:779`-ish + `land.sh` + `.github/workflows/*.yml`. The product-side ground truth is cross-repo (`/home/stack/code/charon`); the rig-side is in-tree. Test fixtures: a `tools/check_*.py` not invoked anywhere (`R-G`); a shell snippet load-bearing but unregistered (`R-H`). |
| 5 | `RECONCILE-REVIEW-GATE` | §2.1 | The folded review-gate axis. Reads the BLAST-TIER substrate (or its path-pattern fallback pre-substrate); verifies `docs/review-log/<id>.md` + `fleet/state/reviewed/<id>` for `≥hot-path` changes; content-hash match on `reviewed_sha`; reuse `ReviewerCircuitBreaker` for the doom-loop case. **Depends on the BLAST-TIER substrate ticket (BLAST-TIER-MODULE per BLAST-TIER-ENFORCEMENT §5); sequence: build that substrate first OR land the path-pattern fallback here.** |
| 6 | `RECONCILE-FAIL-CLOSED-TAXONOMY` | §2.2 | One-line doctrine (in the BLAST-TIER substrate) — unknown path/work_class defaults to hot-path, not doc. Has to land in the BLAST-TIER module's regex map; this ticket is the contract that the module MUST adopt the rule. **Sequences with #5.** |
| 7 | `RECONCILE-WIRING` | §3 | The enforcement wiring — `preflight.sh:779`-ish chain insertion (3 lines each, in the existing dispatch), `land.sh` required-path pre-condition, and `fleet/checks/reconcile-timer.sh`. Plus the GATE-GAP-LEDGER row declaring the `land.sh` `git -C` seam `open` (status=open, closure=gitea-primary). **Blocks operator adoption of v1.** |
| 8 | `RECONCILE-DOGFOOD` | §4.3 / KS20 | The reconciliation-gate running on **itself** — every new file the v1 build adds (`RECONCILER-REGISTRY.tsv`, the new `fleet/checks/reconcile_*.sh`, the new `fleet/tests/reconcile_*.test.sh`) MUST be `owns:`-tracked (no `fleet/state/*` vanish untracked) and the `RECONCILER-REGISTRY.tsv` itself MUST be wired into the firing layer. Catches the "gate that doesn't run on itself" failure mode. |

The **8 tickets are independent in design, ordered in build** by the substrate
(#1) and the BLAST-TIER dependency (#5 / #6). The operator can choose to
parallelize (e.g. #2 + #3 + #4 in parallel after #1) or serialize (single
droid, one ticket at a time). Each ticket carries its own EVAL-REGISTRY
consult + adversarial review (dogfooding the very review-gate axis it
implements).

## 7. Completion self-check (this doc)

This design is COMPLETE if and only if all six items below are true. The author
has verified each as of 2026-07-23.

- [x] **The 3 v1 reconcilers (§1.1–§1.3)**, each with desired-source, actual-source,
  drift-algorithm, RED condition, AND drift-primitive.
- [x] **Folded review-gate axis (§2.1) + fail-closed taxonomy fix (§2.2)** with the
  substrate-line items (BLAST-TIER module dependency, ReviewerCircuitBreaker reuse).
- [x] **Parked / deferred list (§2.3 grading consumer; §5 ADR/roadmap drift, e2e,
  harness, cross-repo)** — each named, each with a one-line reason.
- [x] **Enforcement wiring (§3)** with rig-side (preflight + land.sh + timer) AND
  public-product-side (native required-check) AND the flagged `land.sh` `git -C`
  open seam (§3.3) — explicit non-fix recorded in GATE-GAP-LEDGER.
- [x] **KS29 leg discipline (§4.3)** — drift-primitive named per reconciler; the
  registry schema is laid out; the future-reconciler-as-data-row posture is
  asserted.
- [x] **Decomposed one-lens-per-reconciler BUILD BACKLOG (§6)** — 8 tickets, each
  with one lens, each with one-liner, sequence dependencies stated.

## 8. Reviewer notes (this doc only)

- **Why this doc itself is in `fleet/state/` (gitignored) and was force-added:**
  this is exactly the `owns-tracked` class (§1.2 R-E). The design is its own first
  test fixture. The `RECONCILE-OWNS-TRACKED` build ticket (#3) MUST cite this doc
  as the canonical R-E example; the future RED that this doc's gitignore produces
  is the desired signal, not a bug.
- **Why no `owns:` exemption was added to `.gitignore`:** `.gitignore` is not in
  the ticket's `owns:`; modifying it would be off-scope (double-claim with whatever
  ticket currently owns `.gitignore`). The `git add -f` precedent is operator-
  confirmed (stass-allie handoff 2026-07-23) and is the right intermediate
  posture; the durable fix is the R-E policy choice in §1.2.
- **Why v1 is three reconcilers, not five+:** scope-creep would reproduce the
  "BLAST-TIER-ENFORCEMENT built tickets 4-6 inert on F1" failure (F7). Three
  reconcilers, each independently RED-when-broken, fold-able later as data
  rows. The KS29 registry schema is the door; the v2 list is the queue.
- **Why this folds rather than supersedes R44/R45/KS24/board-trust/owns-untracked
  in name:** the OPERATOR's directive (handoff action #1) was to make the
  durable root fix; that is the **substrate**, not a rename. The original ticket
  ids remain valid (the *class* they pointed at is real); the *fix* is this
  gate. Subsequent tracking can continue to cite the original ids as the
  historical names of the failure classes.
