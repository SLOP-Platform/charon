# DESIGN — SG ISSUE CONTROL PLANE (DISCOVER → SURFACE LOUDLY → SELF-HEAL)

**Status:** DESIGN + ADOPT-EVAL only (operator: "FIRST investigate this type of framework"). No product/rig code.
**Date:** 2026-07-24. **Owner:** SG-ISSUE-CONTROL-PLANE (design). Supersedes the narrower `DESIGN-SG-UNIFIED-FRAMEWORK.md` (removed — this widens it from plane-canaries to *every failure class*).
**Revision 2 (2026-07-24, post-review).** Revision 1 of this path was a 639-line document that silently REPLACED this one; it was reviewed **DO-NOT-LAND** (`fleet/state/reviews/SG-ISSUE-CONTROL-PLANE-REVIEW-agen-kolar.md`, F1–F13). Operator remedy: **FOLD, don't fork.** This revision is the original provenance-backed document as the BASE, with only the branch's genuinely-new-and-correct content folded in. Where the two conflicted, this document won unless the branch carried evidence — every such adjudication is recorded in §11. A verbatim backup of the pre-fold base is `fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.BACKUP-agen-kolar.md`; the discarded 639-line revision is recoverable at `8838670`.
Claim tags: **[V]** = verified (file:line I read, or a doc I fetched) · **[I]** = inferred.

**Citation discipline (new, from F11).** `fleet/preflight.sh` line numbers are NOT stable: the scan dispatch is `:878` at `8838670` and `:896` on master — both verified this session. **[V]** Every reference below therefore names the **symbol** (`cmd_scan`, `cmd_detect`, `board_gate`, `done_merge_gate`, `run_check`); line numbers are given only for files whose content is settled, and any builder must re-derive them. The review's F11 "wrong line number" finding is re-classified as **version skew, not a wrong reference** — but the fix is the same and is adopted: cite symbols.

---

## 0. PREMISE CORRECTION — the problem is UN-ACTIONED findings, not MISSING detection

The discarded revision's founding claim was that the fleet lacks a discover+surface leg. **That is false, and running our own tool proves it** ([[reviews-use-our-own-tools]], [[confirm-dont-trust-documentation]]).

`bash fleet/plane-canary.sh reconcile` — run this session in the worktree — returns **8 of 10 planes RED, fail-closed**: **[V]**

```
RED data/serving (unwired) · RED failover (unwired) · RED egress-key (proofless)
RED review (proofless) · RED lifecycle (proofless) · GREEN landing
RED balance (unwired) · RED config-ssot (proofless) · GREEN map-freshness
RED reconciliation (proofless — reconcile-gate-wired.sh + .test.sh absent on disk)
```

Those are precisely the `inert/not-wired` and `quarantined-good` classes the discarded revision called its novel slices. The incumbent discover+surface leg **works and is already shouting**; nobody closes its findings.

**Consequence for this design — binding:** a fourth detection layer over a third one that is RED and ignored does not cure normalization-of-deviance; it adds a surface to ignore. **Any slice this design authorises must be justified against "un-actioned", not "missing."** The measured gap is small and different: ~6 advisory detectors in `cmd_detect` have no `check_cmd` and no auto-register call, so their findings can never become blocking reds. That is rows plus small functions in an existing file — §3.

---

## 1. VERDICT

**Architecture class:** a **closed-loop, event-driven auto-remediation control plane** — the *"IFTTT for Ops"* / Kubernetes-operator shape: **sensors detect → a rule/policy engine decides → gated actions remediate**, running **level-triggered on a cadence** over a **software-catalog + relations-graph** substrate. The four best-in-class exemplars each own one facet:

- **StackStorm** = the canonical closed-loop shape. **[V]** Its own tagline is *"IFTTT for Ops … event-driven automation for auto-remediation"*; architecture = **Sensors** (watch/emit) → **Triggers** (event repr, incl. generic *timers*) → **Rules** (map trigger→action) → **Actions/Workflows** (remediate), + **ChatOps** notification (github.com/stackstorm/st2; medium "Fighting Alert Fatigue"). This is *exactly* discover→surface→self-heal.
- **ArgoCD self-heal + prune** = the **GATED** self-heal + drift model. **[V]** `selfHeal: true` "continuously monitors the cluster for drift and automatically corrects it … reverts to match Git"; `prune: true` removes resources no longer in Git; self-heal is **opt-in per-app**, and the reconcile runs on an **interval** (`timeout.reconciliation` default 120s + jitter) — level-triggered, not event-only (argo-cd.readthedocs.io auto_sync; oneuptime argocd-self-heal-policy).
- **Kubernetes operator / controller** = the detect→reconcile→self-heal loop, **level-triggered**: "always asks *is the world in the state I want?* regardless of how many events fired"; idempotent reconcile; drift corrected on the next tick even with no event (deepwiki kubebuilder 5.2; oneuptime operator-reconciliation-loop). **[V]**
- **Backstage Tech-Insights/Soundcheck + Dagster asset-checks** = the *facts→checks→scorecard* catalog that makes health *scored and un-stale-able*. **[V]** Tech-Insights: *Facts* (per-entity data) → *Checks* (rules) → *Scorecards* (roadie.io). Soundcheck: changing a check's rule **auto-deletes stale results**; collection runs on a **cadence** (backstage.spotify.com). Dagster: an asset is **stale** if code/upstream changed since last materialization; freshness policies + Declarative Automation drive re-runs with **controllable blast radius** (docs.dagster.io; dagster.io 1-1).

**RECOMMENDED SHAPE — adopt the PATTERN, build on OUR substrate; do NOT adopt any tool; do NOT fork a second board.**

> **Treat our EXISTING detectors as StackStorm-style *sensors*; make every sensor's verdict land in the board we ALREADY have (`fleet/reds.tsv`, driven by `fleet/preflight.sh`) with a mandatory `check_cmd`; and — for failure-classes on a safe allowlist — fire a *gated action* that mints a remediation ticket and hands it to the SG executor via `lease-enqueue.sh` → `review-pool.sh`. The reconcile runs level-triggered on `foreman-cadence.sh`. ~85% of this is WIRING assets we already own; the only genuinely-new slice is the verdict→action RULE layer, plus the KS29 discovery primitive.**

**How the 3 legs map (each = an owned-or-adopted mechanism):**

| leg | pattern from | OWNED mechanism today | what is actually new |
|---|---|---|---|
| **1. DISCOVER** | StackStorm *sensors* / K8s *observe* / Tech-Insights *facts* | 6 detectors already exist (table §2) + graphify relations | a **detector registry** (KS29) so a new failure-class = 1 row, and the **discovery leg** that finds *un-registered* components. **⚠ BARRED pending §6 step 3 preconditions.** |
| **2. SURFACE** | Tech-Insights *scorecard* / Soundcheck *historical status* / ChatOps | `reds.tsv` + `preflight.sh` (`cmd_scan` re-proof table; `board_gate`/`executor_gate`/`handoff_gate`/`detect_needs_push`/`done_merge_gate` auto-register+self-close, implemented **5×**) + `session-start.sh` loud STALE banners + `foreman-cadence.sh` | **NOT a new board.** Give the ~6 advisory `cmd_detect` detectors a `check_cmd` + an auto-register call, and add ONE aggregate SessionStart line. See §3. |
| **3. SELF-HEAL** | StackStorm *rules→actions* / ArgoCD *gated selfHeal+prune* | `lease-enqueue.sh` (exactly-once enqueue) + `claim.sh` (selector) + `review-pool.sh` (reviewer≠builder, fail-closed) + `loop-guard.sh` (anti-fork-bomb quarantine) | the **rule layer**: verdict→safe? →mint remediation ticket→enqueue; gated by a per-class **safe/unsafe allowlist**. **The only genuinely-new slice.** |

**Adopt-vs-extend call:** EXTEND owned substrate; PATTERN-only. **[V]** StackStorm is a Python+RabbitMQ+MongoDB service with 160 integration packs; ArgoCD is a k8s controller; Backstage/Soundcheck a React+Postgres platform; Dagster a daemon — all *service-shaped* for org-scale fleets, catastrophic integration cost for a solo bash/python fleet. `plane-canary.sh:14-24` **[V]** already records the tool-eval verdict rejecting Checkly/Grafana-SM/Sensu/blackbox_exporter for this exact semantics. We already own the sensors, the board and the actuator; we lack only the *rule engine* — precisely StackStorm's cheap-to-replicate glue, not its heavy runtime.

**THE SINGLE MOST IMPORTANT ADOPT DECISION:** adopt **StackStorm's sensor→rule→action SHAPE with ArgoCD's per-app opt-in self-heal gating** — i.e. **remediation is opt-in per failure-class, never global-blind**, and every auto-launched fix is **routed through `review-pool.sh` (reviewer≠builder, fail-closed BOUNCE) + the work-lease commit gate, NEVER direct-to-master.** This is what turns "detectors we already have" into a safe closed loop without importing a platform.

**BIGGEST ADOPT-VS-HANDROLL RISK:** the self-heal leg must not become the very failure it fixes. Three named hazards: (a) **[V]** `--commit-dirty` sweeps concurrent WIP to master bypassing review ([[commit-dirty-sweeps-subagent-wip]]) — so auto-launched fixes MUST go through review-pool, never a launcher auto-commit; (b) **[V]** KS29's **discovery leg is DESIGNED-not-BUILT / FIX-REQUIRED** (`REGISTRY-CANDIDATES.md:58-59`) — so the "un-registered new component" detector is **fake-green until KS29 discovery ships**; (c) **NEW** — a second board with a weaker close policy is itself a normalization engine (§3, F2). All three are gating, not cosmetic.

---

## 2. LEG 1 — DISCOVER: every recurring failure CLASS, as StackStorm-style sensors

A **detector = a sensor**: a script that emits a per-issue verdict `{class, entity, severity, evidence, check_cmd, safe_to_auto_fix}`. We already own one per major class — the control plane *registers and unions* them (KS29 detector-registry row), it does not rebuild them:

| failure CLASS (operator's list) | OWNED detector (the sensor) | evidence | build status |
|---|---|---|---|
| built-but-not-wired / **inert** code | `tools/check_inert_code.py` — AST call-graph reachability from real entrypoints; 0-caller public symbol not in `inert-code-disposition.json` ⇒ RED "caught on the same push"; **green-without-hiding** (disposition = wire/delete/keep-why) | **[V]** header read | BUILT (product side) |
| declared-gate-not-wired / **unwired canary** | `plane-canary.sh reconcile` — proofless (dogfood last rc≠0) / unwired (firing layer doesn't invoke) / uncovered, all fail-closed | **[V]** `plane-canary.sh:168-227`; run this session → 8/10 RED | BUILT + LIVE + **un-actioned** |
| gate-declared-vs-actually-wired (**reconciler**) | `fleet/checks/reconcile-gate-wired.sh` — desired = `fleet/checks/*.sh|*.py`, `tools/check_*.py|*.sh`, `RULE-REGISTRY.tsv` status ∈ {ACTIVE,ENFORCED}, `EVAL-REGISTRY.md` verdict=ADOPT + non-empty `enforced_in`; actual = the firing layers | **[V]** `RECONCILE-GATE-WIRED.md` note + `owns:` | **WRITTEN, UNLANDED** — commit `d603494` on `feat/reconcile-gate-wired`; both files verified ABSENT on disk. **Do not rebuild it (F3).** |
| **stale/drift: test-fixture-vs-code, config-vs-reality, deployed-vs-source** (the board-correctness incident) | `graphify-freshness.sh` (map vs HEAD, self-desync-proof filter) + KS24/KS29 drift legs (content-hash / set-diff / subset-conformance / graph-reachability / staleness-TTL) as designed in `UNIFIED-RECONCILIATION-GATE-DESIGN.md` | **[V]** `graphify-freshness.sh:38-44,230-243`; `UNIFIED-RECONCILIATION-GATE-DESIGN.md:50-58` | BUILT; `graphify_freshness_gate` already auto-registers `graphify-freshness-stale` **with a `check_cmd`** **[V]** |
| **done-but-unmerged / merged-but-not-retired** | `reconcile-merged.sh` — maps merged PR→ticket by verified-merge / `owns`-overlap (not bare branch-name), auto-`done` with `--merged-sha` proof; surfaced by `done_merge_gate`, which already auto-registers `done-unmerged-<id>` and self-closes on `verify-merged.sh` | **[V]** header read + `done_merge_gate` read | **BUILT — a live row exists in `fleet/reds.tsv` now. Duplicating it is F2.** |
| **stale claims** (dead lease) | `reconcile-stale-claims.sh` | **[V]** file present | BUILT |
| **quarantined-but-good tickets** (loop-guard spin) | `loop-guard.sh` — N zero-commit re-claims ⇒ durable `state/loop-guard/<id>` quarantine + stderr escalation; `clear` re-admits | **[V]** header read (record/quarantine/clear) | BUILT |
| **junk launcher auto-commits** (`--commit-dirty`) | *GAP — no detector; memory-hazard only* | **[V]** [[commit-dirty-sweeps-subagent-wip]] | **GAP** |
| **un-registered new component** | KS29 **discovery** leg over graphify: enumerate load-bearing code-nodes (canary/gate/test/pool/catalog/grader) with firing-layer edges but no registry row ⇒ RED | **[V]** `ROADMAP.tsv:KS29`; **⚠ unbuilt** `REGISTRY-CANDIDATES.md:58-59` | **⚠ UNBUILT — fake-green until KS29 discovery ships.** Flag retained; the discarded revision dropped it. |
| **failing/RED tests+gates** | `preflight.sh` `board_gate` (auto-registers `board-validator-red`, self-closes on GREEN) + CI allowlist + `plane-canary run` | **[V]** `board_gate` read | **BUILT — duplicating it is F2.** |

**Per-class contract (folded from the discarded revision, corrected).** The 5-field shape it introduced — **name / desired-source / actual-source / drift-algorithm / RED condition** — is genuinely useful and is ADOPTED as the registry row contract, with **two mandatory additions this design imposes**: a **`check_cmd`** and a **`min_scanned`** floor (§5). Its class *list* is not adopted wholesale: `failing/RED` (its §2.2) is `board_gate` and `done-but-unmerged` (its §2.6) is `done_merge_gate` — both already built, so they are **registry rows pointing at the existing gate**, never new code.

**Awareness / relations backbone = graphify.** `graph.json` is networkx node-link with **9786 typed `links`** (`relation`=defines/calls/imports, `source`/`target`/`confidence`/`source_file`) over 7471 nodes; fleet bash fully extracted (130 canary nodes confirmed live). **[V]** (read the graph directly). Entity-level `dependsOn` (Backstage shape) = transitive reachability between two entities' anchor node-sets — the primitive `reconcile-gate-wired.sh` already uses (`RECONCILE-GATE-WIRED.md:35` **[V]**). This is how detectors become *aware of each other*: a fix to component A can be scoped to A's graph-neighborhood.

**Registry (KS29) unifies them:** one `fleet/detector-registry.tsv` (generalize `fleet/plane-canary-registry.tsv` **[V]** — which lives at `fleet/`, **not** `fleet/state/`) with columns `class, sensor_script, graph_anchor, cadence, severity, check_cmd, min_scanned, safe_to_auto_fix, remediation_recipe, owner_ticket`. Adding a new failure-class = one row (KS20 anti-accretion), and the KS29 **discovery gate** makes an *un-catalogued* load-bearing detector itself RED — mechanizing the 12-gap hand-survey (`plane-canary-gap-survey.md:25-43` **[V]**).

**Sources that do NOT exist — fail-closed, not silently skipped.** `RECONCILER-REGISTRY.tsv` was cited as a desired-source by the discarded revision; `find` over the tree confirms **it does not exist**. **[V]** Per §5(a) an absent desired-source is RED, never an empty set. `GATE-GAP-LEDGER` is `fleet/state/GATE-GAP-LEDGER.tsv` (`.tsv`, not `.md`) **[V]**.

---

## 3. LEG 2 — SURFACE LOUDLY: EXTEND `reds.tsv`; do not fork a second board

Revision 1 said "generalize the incumbent registry" — but its own §3 then proposed a thin `fleet/issue-board.sh` writing `state/issue-board.tsv`, and the discarded revision forked the same second board at a different path. **Both revisions proposed a second board; the ruling to extend `reds.tsv` instead is the REVIEW's (F2), which supplied the decisive evidence — see §11 row 1.**

**`fleet/reds.tsv` + `fleet/preflight.sh` ALREADY IS the unified issue board, and it is stronger than the proposed replacement:** **[V]**

- `preflight.sh:1-8` header — *"REDS REGISTRY driver … Every known red lives in reds.tsv and is RE-VERIFIED deterministically here. THE KEY RULE: a red closes ONLY on a passing check_cmd or an explicit RECORDED override — never by assertion."*
- `cmd_scan` re-runs **every** open red's `check_cmd` each session via `run_check` and prints the table — that IS the SessionStart surface. It is *stricter* than the fork proposed: a NOW-GREEN row prints `ready to close`; **closure is an explicit `close` subcommand, never automatic**.
- The schema is already `id · opened · sev · area · description · check_cmd · status · closed_by` — the `check_cmd` column the fork lacked **already exists**, and `cmd_add` even rejects embedded tabs in it.
- The **auto-register-a-detector-finding-as-a-self-closing-blocking-red** pattern is implemented **five times**: `board_gate`, `executor_gate`, `handoff_gate`, `detect_needs_push`, `done_merge_gate` — each `cmd_add`s with a `check_cmd`, re-opens a closed row on regression, and self-closes only via `cmd_close --override "auto: … GREEN"`.
- `cmd_detect` is explicitly labelled *"ACTIVE DETECTORS (unregistered risk not yet in reds.tsv)"* — i.e. **the union target is reds.tsv by design**, and the advisory detectors are the known, named backlog.

**Therefore the SURFACE work is:**

1. **Promote the ~6 advisory detectors.** `cmd_detect` currently calls `detect_untracked_drift, detect_secret_scan, detect_repo_drift, detect_claim_loop, detect_wci_contention, detect_inflight_landscape, detect_stranded_work, detect_cg_drift, detect_gateway_token_drift, detect_config_drift` **[V]**. Each that is deterministically re-provable gets a `check_cmd` + a ~10-line auto-register/self-close pair modelled on `board_gate`. Re-measure the exact set at build time; do not hardcode this list.
2. **Add ONE aggregate line, not a second table.** The one genuinely-good surfacing idea in the discarded revision is the *loud aggregate header* — adopted, reduced to a single line rendered by the existing `cmd_scan` block and echoed by `session-start.sh` (which already prints loud STALE banners and calls `graphify-freshness.sh`, `session-start.sh:99,104-112` **[V]**): `ISSUE-BOARD: N open reds across M areas — oldest X days — Y advisory findings unpromoted`.
3. **Age escalation on the existing `opened` column.** `reds.tsv` already stores `opened`; the Soundcheck *historical status* analog is a derived age, not a new column. A red that sits normalized for N days escalates its printed severity. **[I]**
4. **Level-triggered refresh** — wired into `foreman-cadence.sh` (which already fans a report to `session-start / post-land / handoff / cadence` triggers, `foreman-cadence.sh:1-20` **[V]**) so the surface refreshes on a timer, not only on an edge (the K8s/ArgoCD interval guarantee).

**If a second board is ever genuinely required**, that case must be argued adversarially against `preflight.sh:1-8`'s close policy, in writing, before any build. It is not argued here because the evidence runs the other way.

**Anti-normalization guarantee (structural):** a red carries `opened`; the surfacer escalates by age and the SessionStart line always prints the count. Combined with plane-canary's *proofless=RED* (a detector whose own dogfood rots goes red loudly `plane-canary.sh:189-193` **[V]**), a red can neither hide (surfaced every tick) nor rot silently (the detector-of-detectors is itself a catalogued sensor). **[I]**

**Note on tracking:** `fleet/reds.tsv` is itself gitignored (`.gitignore:84` **[V]**). That is CORRECT — it is per-checkout runtime state. Only the *design of record* needs to be tracked (§7).

---

## 4. LEG 3 — SELF-HEAL: gated auto-launch to the SG executor

**Pattern:** StackStorm *rule→action* + ArgoCD *opt-in selfHeal + prune*. **The doctrine is GATED, never blind** — `foreman-cadence.sh` already encodes it: *"Every subcommand runs report-only (NEVER --fix). Acting stays a manager decision."* **[V]** `foreman-cadence.sh:19-21`. We keep that default and add a **per-class opt-in** (ArgoCD's `selfHeal: true` is per-app; ours is per failure-class via the registry's `safe_to_auto_fix` column).

**The rule→action layer (new, thin):** for each open issue whose class is `safe_to_auto_fix=yes` (allowlist), the rule:
1. **mints a remediation ticket** from the row's `remediation_recipe` (e.g. inert symbol → "wire or dispose per disposition"; unwired canary → "wire into firing layer"; done-but-unmerged → `reconcile-merged.sh` is itself the auto-fix, already safe);
2. **enqueues via `lease-enqueue.sh`** — THE single exactly-once chokepoint: idempotent flock+`state/enqueued/<id>` marker (no double-launch), composed with Faktory (durable store) + work-lease (commit-boundary gate). **[V]** `lease-enqueue.sh:1-24`;
3. **routes execution through `review-pool.sh`** — reviewer≠builder enforced, **fail-closed: any inability to genuinely review ⇒ BOUNCE, never APPROVE**, verdict to review-log. **[V]** `review-pool.sh` header. So an auto-launched fix reaches master ONLY through adversarial review, never a launcher auto-commit.

**Safety rails (why this is not blind):**
- **allowlist gate** — a class defaults `safe_to_auto_fix=no`; only cheap/mechanical/reversible classes (inert-dispose, unwired-wire, reconcile-merged, stale-claim-release) are opted in. High-blast classes stay report-only → manager. **[I]** (mirrors ArgoCD per-app opt-in **[V]**).
- **loop-guard** — an auto-launched fix that spins (claim→no-commit→release) is quarantined after N by `loop-guard.sh` **[V]**, so a bad recipe can't fork-bomb the SG tab.
- **no direct-to-master** — review-pool + work-lease gate; the `--commit-dirty` sweep hazard is structurally excluded. **[V]** [[commit-dirty-sweeps-subagent-wip]].
- **exactly-once** — `lease-enqueue.sh` dedup marker prevents the same issue minting N duplicate remediation jobs. **[V]**

**Folded from the discarded revision (rig-native, ADOPTED):**
- **Anti-flap gate** — `auto_launch_gate ∈ {ALWAYS | after_N_ticks=N | NEVER}`. A finding must persist N consecutive ticks before auto-launch. Genuinely new and correct; adopted as a registry column.
- **Double-launch gate** — if the row's `heal_launched_at` is set and the launched ticket is still open, skip. If that ticket is DONE and the finding persists, mark `heal-failed` and **escalate — never auto-retry**.
- **`heal_blocked_reason`** — when review-pool has no available reviewer the heal cannot launch; the reason is *rendered*, never silently skipped.
- **Built-in heal commands** — some recipes are one idempotent invocation (`fleet/checks/graphify-freshness.sh update`, `fleet/config-sync.sh` — both verified present **[V]**); these run inline, no droid. A non-zero exit escalates to `heal-failed` + P0 surface.

**REJECTED from the discarded revision (F9):** its §4.4 *"reuse `ReviewerCircuitBreaker` from `src/charon/failover.py:73-142`"*. That file is **absent from `charon-private`**; it lives in the PUBLIC product repo, which must ship standalone. **[V]** A rig bash script cannot use it without importing across the rig/product boundary or copying product code into the rig — both violate [[product-vs-build-rig-boundary]] — and it is unactionable as written (no import path, no invocation shape, no cross-process persistence). **The rig-native equivalent is `loop-guard.sh`'s durable `state/loop-guard/<id>` quarantine plus `lease-enqueue.sh`'s flock + `state/enqueued/<id>` exactly-once marker, both already owned and both already named in this design.** No circuit-breaker is built.

---

## 5. FAIL-CLOSED SEMANTICS — the enforcement floor (BINDING on all slices)

The words "fail-closed"/"fail-open" appeared **zero times** in the discarded revision (F5). They are the floor here. Contrast the incumbents, which state it in their own headers: `gate-parity.sh:13` *"Fail-CLOSED: an unrunnable predicate (missing binary, timeout, parse error) => RED — never silently pass through"*; `plane-canary.sh` prints `fail-closed` on every RED line. **[V]**

**(a) Unresolvable predicate ⇒ RED.** A registry/desired-source that is absent, unreadable, or unparseable ⇒ **RED (`source-unresolvable`)**, never an empty set and never a skip. This binds explicitly for `RECONCILER-REGISTRY.tsv`, which does not exist **[V]**. A discovery-leg non-zero exit ⇒ **RED**, never an all-clear. An unresolvable predicate must never widen the pass set.

**(b) Mandatory `check_cmd` — closure requires POSITIVE PROOF, never absence of evidence.** Every issue row carries a `check_cmd`. A finding closes **only** when its `check_cmd` exits 0, or on an explicit RECORDED override — exactly `preflight.sh:1-8`'s doctrine, and exactly what `run_check` / `cmd_scan` / `cmd_close` already implement **[V]**. **Closing on the discovery leg "not re-emitting" a finding is FORBIDDEN**: if the discovery leg crashes, times out, or emits zero tuples, an absence-closure model auto-closes every open issue and renders the board all-green. That is a textbook fail-OPEN and a regression against machinery we already have. This is the single most important line in this document.

**(c) Zero items scanned ⇒ RED.** Every leg declares a `min_scanned` floor. A scan whose scanned population is 0 — empty registry, zero candidate files, empty runner set — is **RED (`vacuous-pass`)**, never a silent GREEN. This mirrors `gate-creation-standard.sh` **S2 NON-VACUOUS** (*"a gate that passes on zero items proves nothing"*) **[V]** and is the whole reason `META-GATE-FINDINGS-ZERO` exists. A GREEN verdict must always name the number of items it scanned.

**(d) Every red-proof reachable by a REAL runner.** See §9 — a proof no runner executes is decoration, not evidence.

**(e) Degraded input is RED for the class it degrades, not a warn.** A stale graphify graph makes the reachability walk incomplete ⇒ the `inert` class goes **RED (`input-degraded`)**, not "warn". The discarded revision's §9.1 chose warn — that fails open on the highest-value class exactly when its input is untrustworthy. Overruled.

**(f) Registration is mandatory.** See §10 — an unregistered check is invisible to the meta-gates, which is the disease this plane claims to cure.

---

## 6. RECOMMENDED BUILD SEQUENCE (compose-heavy)

| # | step | composes (owned) vs new | risk |
|---|---|---|---|
| 0 | **Fold, don't fork.** This plane SUPERSEDES-SCOPE the desired-vs-actual class `UNIFIED-RECONCILIATION-GATE` owns (`UNIFIED-RECONCILIATION-GATE-DESIGN.md:9-14` **[V]**). Land the DISCOVER+SURFACE legs as *that gate's aggregation axis*; the SELF-HEAL leg is the new consumer. Two reconcilers must not drift. | compose | **HIGH if forked** |
| 0b | **Anchor commit first.** Land the `.gitignore` negation(s) + any registry rows the slices need, in ONE commit, before fanning out. `.gitignore:37-42` records that four separate PRs each appended their own negation and had to re-resolve the same conflict three times. **[V]** [[anchor-lines-serialize-parallel-work]] | compose | low (HIGH if skipped) |
| 1 | **Detector-registry** (generalize `fleet/plane-canary-registry.tsv` → `fleet/detector-registry.tsv`, +`class,graph_anchor,cadence,severity,check_cmd,min_scanned,safe_to_auto_fix,remediation_recipe`). Register the existing sensors §2. | compose | low |
| 2 | **⚠ BARRED until B1 lands — SURFACE = extend `reds.tsv`** — give the ~6 advisory `cmd_detect` detectors a `check_cmd` + auto-register/self-close pair (reuse `board_gate` / `done_merge_gate` machinery); add the ONE aggregate SessionStart line + age escalation. **NOT a new board (F2).** **THE BAR:** the landed `ISSUE-BOARD-SURFACE` ticket (P0) still carries `owns: fleet/issue-board.sh, fleet/state/issue-board.tsv, fleet/tests/issue-board.test.sh` **[V]**. Under §8's *"where this design and a landed ticket disagree, the TICKET is authoritative"* rule, a builder who claims that P0 today would **correctly** build the very forked board this revision exists to strike. **Do not claim this slice until the ticket is re-scoped (B1, §8) — i.e. until `fleet/state/issue-board.tsv` is gone from its `owns:`.** | **blocked** | **HIGH** (rebuilds the struck fork) |
| 3 | **⚠ BARRED — KS29 discovery leg.** Two preconditions, both external to this design: **(i)** land `feat/reconcile-gate-wired` (`d603494`) — its detector is already written and its absence is why the `reconciliation` plane is proofless RED; building it again is a duplicate build (F3). **(ii)** satisfy `INERT-WIRING-ENFORCEMENT-DURABLE`, an **operator-escalated DESIGN-FIRST** ticket: *"do NOT build another gate before explaining WHY the prior ones decayed, or it repeats the failure."* **[V]** This plane is another gate for that class; the decay root-cause is not in scope here and is not asserted. **Do not start slice 2 until both clear.** | **blocked** | **HIGHEST** (else fake-green, `REGISTRY-CANDIDATES.md:58-59`) |
| 4 | **Rule→action layer** — for `safe_to_auto_fix=yes` rows: recipe→ticket→`lease-enqueue.sh`→`review-pool.sh`, with the §4 anti-flap / double-launch / `heal_blocked_reason` gates. Default OFF per class. **(the one genuinely-new slice)** | compose (lease-enqueue + review-pool + claim + loop-guard) | med — allowlist must start tiny |
| 5 | **Close the 8 RED plane-canary rows, or record why a new plane precedes fixing the one already shouting.** Non-optional: §0 makes this the design's own premise test. | action, not build | — |
| 6 | **Catalogue the remaining gap classes as rows** (junk-launcher-commit detector, SG off-Claude e2e, claim/lease exactly-once) each with a dogfood. | compose | low |
| 7 | **Level-trigger the whole loop on cadence** (`foreman-cadence.sh cadence`), K8s/ArgoCD interval guarantee. | compose | low |

**Composes:** check_inert_code.py, plane-canary.sh, graphify(+freshness), reconcile-merged.sh, reconcile-stale-claims.sh, loop-guard.sh, lease-enqueue.sh, review-pool.sh, claim.sh, foreman-cadence.sh, session-start.sh, preflight.sh + reds.tsv, UNIFIED-RECONCILIATION-GATE. **Builds new:** the verdict→action rule layer (step 4) and — once unbarred — the KS29 discovery primitive (step 3). The "new board" of the discarded revision is **struck**.

**Biggest risk restated:** do NOT adopt StackStorm/ArgoCD/Backstage/Dagster as tools (service-shaped, rejected-class per `plane-canary.sh:14-24`); **do NOT fork a second reconciler or a second board**; do NOT let self-heal bypass review (`--commit-dirty` hazard). The self-heal allowlist starts with *one* trivially-safe class and widens only after the surface has proven stable.

---

## 7. WHERE THIS DOCUMENT LIVES, AND WHY IT MUST BE TRACKED

**Root cause of the fork:** `.gitignore:10` is `fleet/state/*` with a per-file `!` negation allowlist. This design's path had **no negation**, so the 109-line document was invisible to git — `git status` never showed it, and the 639-line replacement was **force-added** over it without a diff anyone could see. *A design of record that git cannot see is how this fork happened.*

**Decision: keep the path, add the negation.** `fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md` plus a new `.gitignore` line `!fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md`.

Alternatives considered and rejected:
- `fleet/DESIGN-*.md` (tracked by default, no negation needed) — **rejected**: `fleet/board/SG-ISSUE-CONTROL-PLANE.md`'s `owns:` names `fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md` **[V]**, and this session must not edit `fleet/board/*`. Moving the file would immediately red the owns-tracked reconciler.
- `fleet/board/SG-ISSUE-CONTROL-PLANE-DESIGN.md` — **rejected**: `validate_board.sh` globs `board/*.md` and parses **every** one as a ticket **[V]**; the existing `*-DESIGN.md` files there are tickets (with `repo:`/`tier:`/`owns:` front-matter), not design bodies. A design doc there becomes a phantom ticket.

The negation is the convention already used for **12** durable `fleet/state/` artifacts (`ROADMAP.tsv`, `RULE-REGISTRY.tsv`, `BENCH-PROVISIONAL-SCORING-DESIGN.md`, `EVAL-REGISTRY.md`, …) **[V]**. It makes this file `git add`-able rather than force-added, visible in `git status`, and diffable in review — which is exactly the failure it closes. Land it in the §6 step-0b anchor commit.

---

## 8. OWNS RECONCILIATION + BLAST RADIUS (F8, F10)

The three build-slice tickets **already landed on master** (`99c709c`). This design does not spawn them; it must MATCH them. **Where this design and a landed ticket disagree, the TICKET is authoritative** — the ticket is the machine-checked `owns` contract:

| slice | authoritative `owns` (from the landed ticket) **[V]** |
|---|---|
| `ISSUE-BOARD-SURFACE` | `fleet/issue-board.sh`, `fleet/state/issue-board.tsv`, `fleet/tests/issue-board.test.sh` — `depends_on:` **empty** |
| `KS29-DISCOVERY-LEG` | `fleet/checks/registry-discovery.sh`, `fleet/state/component-registry.tsv`, `fleet/tests/registry-discovery.test.sh` — `depends_on:` **empty** |
| `ISSUE-SELF-HEAL-RULES` | `fleet/issue-heal.sh`, `fleet/state/self-heal-allowlist.tsv`, `fleet/tests/issue-heal.test.sh` — `depends_on: ISSUE-BOARD-SURFACE` |

The discarded revision invented a different path for **every file in slices 2 and 3, and five of six in slice 1**, and asserted a `depends_on` the tickets do not carry. All invented paths are **struck**. Because this session must not edit `fleet/board/*`, the following are handed back as required board edits, for whoever owns the board:

- **B1.** `ISSUE-BOARD-SURFACE` re-scope: §3 changes its deliverable from a new board to *extending `reds.tsv`*. Its `owns` should lose `fleet/state/issue-board.tsv` and gain `fleet/preflight.sh` (see B3), or the ticket must be re-briefed.
- **B2.** `KS29-DISCOVERY-LEG` must record the two §6-step-3 preconditions (land `d603494`; clear `INERT-WIRING-ENFORCEMENT-DURABLE`'s design-first bar) as blockers.
- **B3.** **`fleet/preflight.sh` is in NOBODY's `owns`** and two slices need to modify it. Assign it to **exactly one** — `ISSUE-BOARD-SURFACE` — and have slice 3 call in, never edit. Two slices editing `preflight.sh` is a silent collision at land.
- **B4.** `SG-ISSUE-CONTROL-PLANE.owns` should add `docs/review-log/SG-ISSUE-CONTROL-PLANE.md` (rig convention; `RECONCILE-REVIEW-GATE` / `REPO-FIELD-REQUIRED` / `REVIEW-DISPENSATION-CANARY` all list theirs).

**"File-disjoint — no collision" was FALSE and is struck.** Every registry the slices declare lives under `fleet/state/`, so each needs its own `.gitignore` negation — `.gitignore` is the single most contended file in the repo, and it appeared in none of the discarded revision's `owns` lists. Per §6 step 0b, **all negations land in ONE anchor commit before any slice starts**. Note also the convention the discarded revision broke: `reds.tsv` and `plane-canary-registry.tsv` live at `fleet/`, *not* `fleet/state/`, precisely to avoid this.

---

## 9. RED-PROOFS AND THEIR RUNNERS (F6) — a proof no runner executes is decoration

The rig has exactly **two** real runners **[V]**:
- `fleet/gate.sh:33` — `tests=("$TESTS_DIR"/*.test.sh)`, a glob over `fleet/tests/`;
- `fleet/checks/rig-ci-scope.sh:49` `CI_SUITES` — a **hand-maintained literal allowlist**, whose own comment states *"anything added to fleet/tests/ later is excluded BY DEFAULT and only runs in CI once someone deliberately adds it here after proving it is hermetic, offline and fast. NEVER replace this with a `for t in fleet/tests/*.test.sh` sweep."*

**Binding requirement.** Every red-proof this plane ships must satisfy BOTH:
1. its filename matches `fleet/tests/*.test.sh` (so `fleet/gate.sh` picks it up); **and**
2. it is added to `CI_SUITES` by name, after proving it hermetic/offline/fast — read the runner set by **invoking `rig-ci-scope.sh suites`**, never by re-parsing the array, and never by editing that file (owned by `HANDOFF-GATE-NONBYPASSABLE`).

If the runner lookup is unresolvable ⇒ **RED (`runner-set-unresolvable`)**, not a fallback to glob-only. If the resolved runner set is empty ⇒ **RED (`vacuous-pass`)** per §5(c).

This is exactly the S1 sub-assertion `fleet/board/META-GATE-REDPROOF-REACHABLE.md` already specifies **[V]**; this design does not rebuild it, it **inherits** it. (That ticket exists on master but not at `8838670` — this branch is behind master.)

Concretely: each slice's red-proof is named per its ticket's `owns` (§8) — `fleet/tests/issue-board.test.sh`, `fleet/tests/registry-discovery.test.sh`, `fleet/tests/issue-heal.test.sh` — and **each gets its own `CI_SUITES` entry and its own `plane-canary-registry.tsv` row.** One shared row for three checks (the discarded revision's proposal) leaves two proofs with no runner.

---

## 10. REGISTRATION — this plane must be visible to the meta-gates (F7)

A plane whose stated purpose is *"find checks that no meta-gate can see"* must not itself be invisible. `gate-creation-standard` appeared **zero** times in the discarded revision. Binding:

- Every new `fleet/checks/*.sh` must pass `bash fleet/checks/gate-creation-standard.sh check` — S1 RED-PROOFED (companion test exists **and is runner-reachable**, §9), S2 NON-VACUOUS, S3 UN-GAMED, S5 FAIL-LOUD (`set -uo pipefail`), S10 TRACEABILITY. **[V]** header read.
- Every enforceable rule this plane introduces gets a row in `fleet/state/RULE-REGISTRY.tsv` (consumed by `fleet/checks/rule-coverage.sh`, wired into `preflight.sh` as `coverage_gate` **[V]**).
- One `fleet/plane-canary-registry.tsv` row **per slice** (schema `plane · canary_script · dogfood_test · wired_in · owner_ticket` **[V]**), not one total.
- Every green-gate miss this plane discovers is appended to `fleet/state/GATE-GAP-LEDGER.tsv` via `gate-creation-standard.sh append`.

**Acceptance must be a literal command, not prose** (F12). "Fully wired" means: `bash fleet/plane-canary.sh reconcile` reports GREEN for this plane's row(s), **and** `bash fleet/checks/gate-creation-standard.sh check` passes for every new check, **and** each red-proof appears in `bash fleet/checks/rig-ci-scope.sh suites`. Acceptance must additionally require **non-duplication with `reds.tsv`** — the failure mode most likely to be declared satisfied while wrong.

- **EVERY §5 FAIL-CLOSED CLAUSE MUST CARRY AN EXECUTED RED-PROOF — per slice, for all three slices.** `gate-creation-standard`'s S1 RED-PROOFED binds only non-grandfathered `fleet/checks/*` **[V]**, which covers **one** of the three slices (`fleet/checks/registry-discovery.sh`); `fleet/issue-board.sh` and `fleet/issue-heal.sh` sit at `fleet/` and are **outside S1's scope**. S1 therefore does NOT discharge this — it is an independent, additional bar on all three. For each slice, its `fleet/tests/<stem>.test.sh` must carry one case per §5 clause that slice implements — (a) `source-unresolvable`, (b) forbidden absence-closure, (c) `vacuous-pass` / `min_scanned`, (e) `input-degraded` — where each case **drives the check into its fail-closed branch and asserts a non-zero exit AND the specific red id**, not merely that the code path is reachable. **Three anti-vacuity bars, all required:** (i) **fail-on-revert, per case** — reverting that one clause to a pass/skip/`return 0` must turn that case RED; name the revert in the case; a case that still passes with its clause reverted is not a red-proof and the slice is REJECTED; (ii) **declared floor** — the suite asserts the count of §5 clauses it exercised against a floor equal to the number that slice implements (declared in its `detector-registry.tsv` row), so a suite that silently exercises zero or a subset exits non-zero rather than GREEN — zero clauses proven must never read green (S2); (iii) **runner-reachability, proven by execution** — the file must match `fleet/gate.sh`'s `*.test.sh` glob (a `test_*.sh` name is REFUSED) **and** be listed by `bash fleet/checks/rig-ci-scope.sh suites`; paste both runner lines and the run's rc. A fail-closed clause with no executed red-proof is decoration, exactly as §9 says of a proof with no runner — and it is the precise residual path by which an implementer could still ship a check that cannot go RED.

---

## 11. CONFLICTS ADJUDICATED — where the base won, and where the branch had evidence

Per the operator's fold rule: the base wins unless the branch carried evidence it was wrong. Stated explicitly:

| topic | ruling | why |
|---|---|---|
| new `issue-board.tsv` vs extend `reds.tsv` | **REVIEW WINS (F2)** | **Both** revisions proposed a second board — the base's own §3 proposed a thin `fleet/issue-board.sh` writing `state/issue-board.tsv`, the branch forked the same idea at a different path. Neither argued against `preflight.sh:1-8`'s close policy. The ruling to extend `reds.tsv` came from the review (F2), which supplied the positive evidence the incumbent is stronger — not from the base. |
| fold vs fork | **BASE WINS, verbatim** (§6 step 0) | The branch did the forked thing the base names as the HIGH risk. |
| `[V]` provenance · ⚠-KS29-unbuilt flag · review-pool + loop-guard + lease-enqueue rails · `--commit-dirty` hazard | **BASE WINS** | Dropped by the branch with no justification; all restored. |
| circuit breaker | **BASE WINS** | Branch's `ReviewerCircuitBreaker` is in the PUBLIC product repo, verified absent from the rig (F9). `loop-guard.sh` is the rig-native equivalent. |
| `preflight.sh` line `878` vs `895/896` | **BRANCH NOT WRONG — both true, different checkouts.** Verified `:878` @ `8838670` and `:896` @ master. Adopted fix: **cite symbols, not line numbers** (header note). |
| 5-field per-class contract (desired / actual / algorithm / RED-condition) | **BRANCH FOLDED IN** | Genuinely new, genuinely useful structure — adopted as the registry row contract, with `check_cmd` + `min_scanned` added (§5). |
| anti-flap `after_N_ticks`, double-launch gate, `heal-failed` escalation, `heal_blocked_reason`, built-in heal commands | **BRANCH FOLDED IN** | New, correct, rig-implementable. |
| loud aggregate SessionStart header | **BRANCH FOLDED IN, REDUCED** | Good idea; rendered as ONE line on the existing surface, not a second table. |
| `failing/RED` + `done-but-unmerged` as new classes | **BRANCH STRUCK** | Verbatim `board_gate` / `done_merge_gate`; already built, already auto-registering, already self-closing (F2). |
| slice file paths · `depends_on` · "file-disjoint" | **BRANCH STRUCK** | Contradicts the three landed tickets on every slice; `.gitignore` collision unacknowledged (F8, F10). |
| `RECONCILER-REGISTRY.tsv` as a desired-source | **BRANCH STRUCK** | Does not exist; §5(a) makes an absent source RED. |
| warn-on-stale-graph | **BRANCH STRUCK** | Fails open on the highest-value class; §5(e) makes it RED. |

---

## 12. OPEN SEAMS — flagged, fail-closed, not faked-closed

1. **graphify completeness.** The reachability walk is only as complete as graphify's extractors. Pre-condition: `graphify-freshness.sh check`. **A stale/incomplete graph makes the `inert` class RED (`input-degraded`), not a warn** — §5(e).
2. **review-pool availability.** If no reviewer is available the heal cannot launch; the issue stays open with `heal_blocked_reason` **rendered** in the surface. Not silently skipped.
3. **`git -C` push bypass.** A direct push bypasses `land.sh`, so the plane's preflight leg does not run. Inherited from `UNIFIED-RECONCILIATION-GATE-DESIGN.md §3.3`; mitigation is the same (timer-based reconcile catches it at the next tick). Level-triggering is what makes this survivable.
4. **`fleet/reuse-check.sh` cannot be run at design stage** — it requires the candidate file to exist on disk and raises `FileNotFoundError` for a not-yet-created path **[V]** (reviewer-verified). Reuse for this design was established by direct search instead. **This is a real rig gap and needs its own ticket**: the reuse gate is unusable for the case it is most needed in.
5. **`UNIFIED-PLANE-CANARY-FRAMEWORK` status is ambiguous** — described as "blocked by this, launched immediately after", but the board carries it as a superseded redirect stub. Confirm which before launching anything.
6. **This branch is behind master.** `META-GATE-REDPROOF-REACHABLE.md`, `META-GATE-FINDINGS-ZERO.md` and `META-GATE-CALLSITE-ENUM.md` exist on master and not at `8838670` **[V]**. Refresh before building.

---

## 13. REVIEW DISPOSITION — the 10 REQUIRED CHANGES

| # | required change | status |
|---|---|---|
| 1 | Restore/merge the 109-line incumbent; `[V]` provenance, fold-don't-fork ruling, ⚠-KS29 flag, review-pool/loop-guard/lease-enqueue rails must survive; add the `.gitignore` negation | **DONE** — this document; §6 step 0 is verbatim; negation added (§7) |
| 2 | Re-scope slice 1 from "new board" to "extend `reds.tsv`" | **DONE in design** (§3, §6 step 2). Ticket edit handed back as **B1** (§8) — board is out of scope this session. **Slice 2 is BARRED until B1 lands** (§6 step 2): while `ISSUE-BOARD-SURFACE.owns` still names `fleet/state/issue-board.tsv`, §8's ticket-authoritative rule makes rebuilding the struck fork the *correct* action for a builder who claims it |
| 3 | Land `feat/reconcile-gate-wired` (`d603494`) before slice 2; address `INERT-WIRING-ENFORCEMENT-DURABLE`'s design-first bar | **DONE as a BAR** (§6 step 3) — both are external actions this design cannot perform; slice 2 is barred until they clear |
| 4 | Close the 8 RED plane-canary rows, or state why a new plane precedes fixing the one already shouting | **DONE** — §0 records the falsified premise and re-frames the design around "un-actioned"; §6 step 5 sequences the closure. **Closing them is not this design's work** |
| 5 | Fail-closed section: unresolvable source ⇒ RED · discovery non-zero exit ⇒ RED · zero-scanned ⇒ RED · stale graphify ⇒ RED · mandatory `check_cmd` | **DONE** — §5(a)–(f) |
| 6 | Pin the runner for all three red-proofs (`*.test.sh` + explicit `CI_SUITES`) | **DONE** — §9 |
| 7 | Registry rows in `owns`: `RULE-REGISTRY.tsv`, one `plane-canary-registry.tsv` row per slice, `.gitignore` negations as an anchor commit | **DONE in design** (§10, §6 step 0b). The `owns` field edits are board edits → **B1–B4** (§8) |
| 8 | Reconcile §6.1 with the three landed tickets (paths + `depends_on`); assign `preflight.sh` to exactly one slice | **DONE in design** — §8 makes the tickets authoritative and strikes the invented paths. Ticket-side edit → **B3** |
| 9 | Replace product-repo `ReviewerCircuitBreaker` with `loop-guard.sh` + `lease-enqueue.sh` | **DONE** — §4 |
| 10 | Independent review of the review-log (reviewer ≠ author model) | **PARTIAL / DEFERRED** — the self-attested `CONFIRMED-CLEAN` is withdrawn; `docs/review-log/SG-ISSUE-CONTROL-PLANE.md` now records the independent adversarial review (agen-kolar) and its DO-NOT-LAND verdict. A fresh independent review **of this revision** is still required and is a **land precondition** |

**Deferred, with reasons:** the #2/#7/#8 ticket-field edits (this session is barred from `fleet/board/*`; another sub owns it — handed back as B1–B4). #3 and #4 are actions on other branches/tickets, not design content, so they are recorded as sequenced bars rather than performed. #10's re-review of this revision cannot be self-performed.

---

### Provenance

Files read (**[V]**), revision 1: `check_inert_code.py`, `plane-canary.sh`, `plane-canary-registry.tsv`, `graphify-freshness.sh`, `reconcile-merged.sh`, `loop-guard.sh`, `lease-enqueue.sh`, `review-pool.sh`, `foreman-cadence.sh`, `session-start.sh`(grep), `UNIFIED-RECONCILIATION-GATE-DESIGN.md`, `REGISTRY-CANDIDATES.md`, `RECONCILE-GATE-WIRED.md`, `ROADMAP.tsv`(KS22/24/26/29), `plane-canary-gap-survey.md`, live `graph.json` (7471 nodes / 9786 links). Docs fetched (WebSearch): StackStorm sensors/triggers/rules/actions+ChatOps (github.com/stackstorm/st2; medium), ArgoCD selfHeal/prune/reconcile-interval (argo-cd.readthedocs.io; oneuptime), K8s level-triggered reconcile (deepwiki; oneuptime), Backstage Tech-Insights facts/checks/scorecards (roadie.io) + Soundcheck staleness (backstage.spotify.com), Dagster freshness/Declarative-Automation (docs.dagster.io; dagster.io 1-1).

Added for revision 2 (**[V]**, read or executed this session): `fleet/preflight.sh` (header `:1-8`, `run_check`, `cmd_scan`, `cmd_add`, `cmd_detect`, `board_gate`, `executor_gate`, `graphify_freshness_gate`, scan dispatch `:878`@`8838670` / `:896`@master), `fleet/reds.tsv` schema, `.gitignore:1-90` (negation allowlist; `fleet/state/*` at `:10`, `fleet/reds.tsv` at `:84`, anchor-file note at `:37-42`), `fleet/checks/rig-ci-scope.sh:40-75` (`CI_SUITES`), `fleet/gate.sh:33` (runner glob), `fleet/checks/gate-creation-standard.sh:1-40` (S1/S2/S3/S5/S10), `fleet/validate_board.sh:40-70` (board `*.md` parsed as tickets), `fleet/plane-canary-registry.tsv` (5-col schema), `fleet/board/{SG-ISSUE-CONTROL-PLANE,ISSUE-BOARD-SURFACE,KS29-DISCOVERY-LEG,ISSUE-SELF-HEAL-RULES,RECONCILE-GATE-WIRED,INERT-WIRING-ENFORCEMENT-DURABLE,META-GATE-REDPROOF-REACHABLE,META-GATE-FINDINGS-ZERO}.md`, `fleet/state/reviews/SG-ISSUE-CONTROL-PLANE-REVIEW-agen-kolar.md`, and the discarded 639-line revision in full. **Executed:** `bash fleet/plane-canary.sh reconcile` → 8/10 RED (§0); existence checks confirming `fleet/checks/reconcile-gate-wired.sh`, `fleet/tests/reconcile-gate-wired.test.sh`, `fleet/state/RECONCILER-REGISTRY.tsv`, `fleet/checks/reconcile-timer.sh` and `src/charon/failover.py` are all ABSENT from the rig. Inferred items tagged **[I]**.
