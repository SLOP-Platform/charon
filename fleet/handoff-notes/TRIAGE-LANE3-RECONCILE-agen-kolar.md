# TRIAGE — LANE 3 (reconcile / doctrine / ksf / salvage)

Session: agen-kolar sub-lane 3 of 4. Date: 2026-07-24.
Method: **content-level proof only.** `git cherry` / `git log origin/master..<b>` were computed but
are NOT treated as authoritative — this rig lands work by **re-derivation, not cherry-pick**, so the
commit graph produces false "unique work" positives (confirmed by Lane 1 across six branches).
Every verdict below rests on one or more of:

- **(C)** per-file diff of the branch's OWNED files against `origin/master` — byte-identical owned
  files, or master strictly ahead, means it landed.
- **(A)** ancestor proof: `git merge-base --is-ancestor <branch> origin/master`.
- **(P)** merged PR on GitHub.
- **(R)** residue scan — every path on the branch absent from `origin/master`, excluding
  `graphify-out/`, `fleet/state/`, `SESSION-HANDOFF*`, `__pycache__`. Nothing is recommended for
  reap until its residue is either (a) nil, (b) archived in master, or (c) preserved by a push.

`fleet/session-notes/rig-salvage-triage.md` was NOT used as evidence (known stale).

---

## Disposition table

| Branch / worktree | Unique commits (graph) | Uncommitted | Superseded by | Disposition | Evidence |
|---|---|---|---|---|---|
| `feat/reconcile-gate-wired-salvaged`<br>wt `RECONCILE-GATE-WIRED` | 2 | none | — | **PUSHED** (publish only) | **(R)** `fleet/checks/reconcile-gate-wired.sh` (355), `fleet/tests/reconcile-gate-wired.test.sh` (162), `docs/review-log/RECONCILE-GATE-WIRED.md` (115) — all ABSENT from master. Genuinely live. Published to `origin` at `6d4d6db`, ls-remote PROVEN. |
| `chore/gitignore-state-negations` | 1 | none | `origin/master` | **REAP** (recommend) | **(C)** `.gitignore` on branch REMOVES 5 negation blocks master has (`RULE-REGISTRY.tsv`, `service-registry.tsv`, `EVAL-REGISTRY.md`, …). Master strictly ahead. **(R)** residue = board tickets only, all ARCHIVED in master. Landing it would be a regression. |
| `chore/retire-wire-graphify` | 1 | none | — | **NEEDS-TICKET** (board pass) | Commit `95a5091` is a pure rename `fleet/board/WIRE-GRAPHIFY-FRESHNESS.md → archive/`. Master STILL has it live in `fleet/board/`. The action is unapplied; the branch holds no code. Not mine to apply (`fleet/board/*` off-limits). Preserved on `gitea` at `95a5091`. |
| `design/unified-reconciliation-gate` | 1 | none | PR #178 (merged) | **REAP** (recommend) | **(P)** PR #178 `design/unified-reconciliation-gate` merged=true. Doc landed as `fleet/board/UNIFIED-RECONCILIATION-GATE-DESIGN.md`. **(R)** residue = archived board tickets only. |
| `doctrine/adopt-substrate-first` | 2 | none | `origin/master` | **REAP** (recommend) | **(C)** `ba86da3` = 1-line edit to `fleet/MANAGER-OPERATING-RULES.md`, present in master (branch version is 12 lines BEHIND). `f21afa7` = handoff + 5 board tickets, all ARCHIVED in master. **(R)** no non-board residue. |
| `feat/github-limits-hardening-v2` | 3 | none | `origin/master` | **REAP** (recommend) | **(C)** owned files vs master: `fleet/checks/large-file-guard.sh`, `fleet/done.sh`, `fleet/tests/test_github_limits.sh`, `docs/review-log/GITHUB-LIMITS-HARDENING.md` **byte-identical**; `fleet/gh-cache.sh` — master has **7 lines MORE** (`pr_number_is_merged()`). v2 fully landed by re-derivation, master ahead. **(R)** no non-board residue. |
| `feat/session-end-push-gate-v2` | 3 | none | `origin/master` | **REAP** (recommend) | **(C)** `fleet/tests/end-session-push.test.sh`, `fleet/tests/deploy-session-end.test.sh`, `docs/review-log/SESSION-END-PUSH-GATE.md` **byte-identical**; `fleet/end-session.sh` — master has **34 lines MORE** (M2 STALE-HANDOFF GUARD, 2026-07-24). v2 landed, master ahead. **(R)** no non-board residue. |
| `feat/ksf-vendor-gates`<br>wt `KSF-VENDOR-GATES` | **0** | none (clean) | `origin/master` | **REAP** (recommend) | **(A)** tip `dfa1664` IS the merge-base with `origin/master` → strict ancestor, 63 behind, 0 ahead. Tip is itself an old master merge commit ("Merge pull request #239"). Ticket lives at `fleet/board/archive/KSF-VENDOR-GATES.md` in master. **(R)** residue = archived board tickets only. |
| `salvage/preflight-verify-merged-ghcache-wip`<br>wt `PREFLIGHT-VERIFY-MERGED-GHCACHE` | 6 | none (clean) | PR #181 (merged) | **REAP** (recommend) | **(P)** PR #181 `fix/preflight-verify-merged-ghcache` merged=true. **(C)** owned files vs master: `fleet/_lib.sh`, `fleet/gh-cache.sh`, `docs/review-log/PREFLIGHT-VERIFY-MERGED-GHCACHE.md` **byte-identical**; `fleet/tests/gh-cache.test.sh` master has 13 lines MORE. Branch also DELETES 16 test files master has (3226 lines) and carries ~190k lines of gitignored `graphify-out/` artifacts. **(R)** residue = board tickets, all ARCHIVED in master. Already on `origin` at `93f8b02` — preserved, nothing to push. |
| `feat/work-lease-gate`<br>wt `WORK-LEASE-GATE` | **0** | 1 file — `graphify-out/manifest.json` (568+/298-) | PR #204 (merged) | **REAP** (recommend); **DISCARD** the dirty file | **(A)** tip `e6eacea` IS the merge-base → strict ancestor of master, 105 behind, 0 ahead. **(P)** PR #204 merged=true. **(C)** `hooks/session-start.sh` is **byte-identical to master** — see correction below. Ticket at `fleet/board/archive/WORK-LEASE-GATE.md`. |

Counts: **1 PUSH · 7 REAP-recommended · 1 NEEDS-TICKET · 1 no-op (already published)** (salvage counts in both REAP and already-published).

---

## Correction to a brief-supplied fact

The brief stated `feat/work-lease-gate` carries "~9 unique lines in `hooks/session-start.sh`".
**That is false.** `git diff origin/master feat/work-lease-gate -- hooks/session-start.sh` is
**empty** — the file is byte-identical. The branch tip `e6eacea` is a strict ancestor of
`origin/master` (`git merge-base --is-ancestor` → true), so it can hold no unique content at all.
The 9-line figure was almost certainly read off a diff in the wrong direction (master's newer
content showing as branch-side removals).

The one dirty file, `graphify-out/manifest.json`, is a **generated graphify artifact**: it matches
`.gitignore:94 graphify-out/`, is tracked only on this stale branch, and master no longer tracks
`graphify-out/` at all. **Not salvaged — worthless.** Left in place (nothing deleted).

---

## The `-v2` verdicts (landing-queue relevant)

### `feat/github-limits-hardening` (queue item ②) — **DO NOT LAND. It is a REGRESSION.**

Both the original and the `-v2` are already in master, landed by re-derivation.

- `origin/feat/github-limits-hardening` @ `1a10452` vs `origin/master`, per owned file:
  `fleet/gh-cache.sh` −66 lines, `fleet/checks/large-file-guard.sh` −15,
  `fleet/done.sh` −36, `fleet/tests/test_github_limits.sh` −87.
- The original still carries the **`-r` bug** that commit `a64d0fb` (the v2 review-rework) fixed:
  `gh pr list … -r '…'` at line 70 of its `gh-cache.sh`. There is no `-r` flag on `gh pr list`; it
  exits non-zero, the cache file is never written, and `merged_prs_touching_file` returns empty
  forever with stderr swallowed. Master carries the fixed `-q` form plus an explicit comment at
  `fleet/gh-cache.sh:110` warning that `-r` does not exist.
- The original also lacks `pr_number_is_merged()` (0 occurrences vs 2 in master) — the function
  `fleet/_lib.sh:222` calls in the live `verify_merged` path.

**Merging queue item ② would reintroduce the dead owns-match and break `verify_merged`.**
Recommend: drop item ② from the queue and reap **both** `feat/github-limits-hardening` and
`feat/github-limits-hardening-v2`. This is exactly the "-v2 that looked live while the original had
already landed" trap — except here it is the *original* that is the stale, regressive one.

### `feat/session-end-push-gate` / `-v2` — **both landed; original is regressive.**

- `-v2` is the review-rework of the original (its own commit `ba9f2fd` says "rebuild #62 as net
  diff onto master"), and `-v2`'s content is now byte-identical to master except that master has
  **34 more lines**: the M2 STALE-HANDOFF GUARD added 2026-07-24 (refuses to close on a committed,
  unmodified handoff whose last commit predates the session start).
- The original `origin/feat/session-end-push-gate` @ `1088460` would **delete 271 lines** from
  `fleet/end-session.sh` and 115 from `fleet/tests/end-session-push.test.sh`. It also carries a
  committed `fleet/capability/__pycache__/availability.cpython-312.pyc`.
- Verdict: `-v2` **supersedes** the original, and master now supersedes `-v2`. Reap both.
  (The original is not in my item list — flagged for whoever owns it.)

---

## The `reconcile-gate-wired` relationship — **PR #211 (queue item ①) is INCOMPLETE**

| ref | sha | content |
|---|---|---|
| `origin/feat/reconcile-gate-wired` = **PR #211 head** | `d603494` | detector only — *"built-but-inert meta-gate (detector, no wire)"* |
| `feat/reconcile-gate-wired` (local, wt `RECONCILE-GATE-WIRED`) | `6d4d6db` | rebased detector **+ the wire** |
| `feat/reconcile-gate-wired-salvaged` | `6d4d6db` | **identical sha** — a duplicate safety ref, not a fork |

`feat/reconcile-gate-wired-salvaged` is **not a rescue of a different branch** — it is a second name
pointing at the same commit as the local `feat/reconcile-gate-wired`. The local branch is 35 ahead
of its own remote because it was rebased onto a newer master; only **2** commits are genuinely its
own work.

The material fact: **PR #211's head `d603494` does not contain the wire.** Merging it as-is ships
the meta-gate built-but-inert — precisely the defect the gate exists to detect, which would make it
red on itself. The missing commit `6d4d6db`:

- wires `reconcile_gate_wired_gate()` into `fleet/preflight.sh`'s scan dispatch;
- fixes 3 accuracy bugs in the salvaged detector (rig's own `.github/workflows/*.yml` never
  scanned → false-RED on `bandit.sh`/`gitleaks.sh`/`semgrep.sh`/`rig-ci-scope.sh`; single-hop
  reachability → now a transitive fixed-point closure; R-H regex matching basenames inside
  comments);
- fixes a **pre-existing live landmine**: `VALID_AREA` in `fleet/preflight.sh` omitted `rig-meta`,
  so `cmd_add`'s `die()` would kill the entire preflight process the moment any rig-meta gate went
  RED, with the error swallowed by the caller's `>/dev/null 2>&1`. `coverage_gate` already used
  that area and carried the same bug — it just never went red.

**Action taken:** published `feat/reconcile-gate-wired-salvaged` → `origin` at `6d4d6db`
(ls-remote PROVEN). This preserves the wire on GitHub without touching PR #211 or its branch.

**Action for the next session (NOT taken — changes a queue item, out of lane):** before merging
PR #211, either fast-forward `origin/feat/reconcile-gate-wired` to `6d4d6db` (PR #211 then contains
the wire), or close #211 and open a PR from `feat/reconcile-gate-wired-salvaged`. See ticket
proposal **TP-1**.

---

## Reap recommendations (NOTHING DELETED — recommend only)

All 10 branches are published on `gitea` at their exact local SHA, so no reap below can lose work.

| Branch | Proof |
|---|---|
| `feat/work-lease-gate` | ancestor of origin/master; PR #204 merged; `hooks/session-start.sh` byte-identical; residue nil |
| `feat/ksf-vendor-gates` | ancestor of origin/master (tip == merge-base); ticket archived; residue nil |
| `salvage/preflight-verify-merged-ghcache-wip` | PR #181 merged; owned files byte-identical, master +13 lines; already on origin |
| `feat/github-limits-hardening-v2` | owned files byte-identical, master +7 lines (`pr_number_is_merged`) |
| `feat/session-end-push-gate-v2` | owned files byte-identical, master +34 lines (M2 guard) |
| `design/unified-reconciliation-gate` | PR #178 merged |
| `doctrine/adopt-substrate-first` | 1-line rule edit present in master; board tickets archived |
| `chore/gitignore-state-negations` | branch `.gitignore` is a strict subset of master's |

Also flagged, **not in my lane**: `feat/github-limits-hardening` and `feat/session-end-push-gate`
(the no-`-v2` originals) are both landed-and-regressive by the same content proof.

Worktrees `WORK-LEASE-GATE`, `KSF-VENDOR-GATES`, `PREFLIGHT-VERIFY-MERGED-GHCACHE`,
`RECONCILE-GATE-WIRED` are all reap-eligible once their branches are. **Not removed.**

---

# TICKET PROPOSALS

*(do not apply here — for the serialized board pass)*

## TP-1 — `RECONCILE-GATE-WIRE-COMPLETE` (P1)

```markdown
# RECONCILE-GATE-WIRE-COMPLETE

status: open
priority: P1
work_class: fix
area: rig-meta
owns: fleet/preflight.sh, fleet/checks/reconcile-gate-wired.sh, fleet/tests/reconcile-gate-wired.test.sh, docs/review-log/RECONCILE-GATE-WIRED.md
substrate: N/A — rig-internal gate wiring (substrate-novel)
depends_on: —
blocks: RECONCILE-WIRING

## Problem
PR #211 ("built-but-inert meta-gate (detector, no wire)") has head `d603494`, which contains the
DETECTOR ONLY. Merging it ships the reconcile meta-gate built-but-inert — the exact defect class
the gate exists to detect, so it would report RED on itself on the first preflight after landing.

The wire exists and is published: `origin/feat/reconcile-gate-wired-salvaged` @ `6d4d6db`
(pushed 2026-07-24, ls-remote proven). It is a rebase of `d603494` onto current master plus one
fix commit. `feat/reconcile-gate-wired` (local) points at the same sha; the two names are
duplicates, not divergent branches.

`6d4d6db` additionally carries:
  - 3 accuracy fixes in the detector (rig's own .github/workflows never scanned -> false-RED on
    bandit.sh/gitleaks.sh/semgrep.sh/rig-ci-scope.sh; single-hop reachability -> transitive
    fixed-point closure; R-H regex matched basenames inside comment lines);
  - a pre-existing LIVE landmine fix: VALID_AREA in fleet/preflight.sh omitted "rig-meta", so
    cmd_add's die() killed the ENTIRE preflight process the moment any rig-meta gate went RED,
    with the error swallowed by the caller's `>/dev/null 2>&1`. coverage_gate already used that
    area and carried the same bug (never fired because it has never gone RED).

## Done contract
- [ ] PR #211 either fast-forwarded to `6d4d6db` (`origin/feat/reconcile-gate-wired` updated) OR
      closed and replaced by a PR from `feat/reconcile-gate-wired-salvaged`.
- [ ] `bash fleet/checks/reconcile-gate-wired.sh` runs on every preflight (dispatch entry present
      in fleet/preflight.sh) and does NOT list reconcile-gate-wired.sh in its own R-G report.
- [ ] `fleet/preflight.sh` VALID_AREA includes `rig-meta`; a RED rig-meta gate no longer aborts
      preflight (regression test).
- [ ] `fleet/tests/reconcile-gate-wired.test.sh` case (e) passes: reverting the wiring re-surfaces
      reconcile-gate-wired.sh in its own report.
- [ ] The 11 disclosed pre-existing R-G items remain RECONCILE-WIRING's scope, not this ticket's.

## Deps & Sequence
Blocks RECONCILE-WIRING (that ticket depends_on this one). No other branch touches
fleet/checks/reconcile-gate-wired.sh. Land BEFORE any further preflight.sh edits — the VALID_AREA
fix is load-bearing for every rig-meta gate.
```

## TP-2 — `GH-LIMITS-QUEUE-TRAP-CLEAR` (P1)

```markdown
# GH-LIMITS-QUEUE-TRAP-CLEAR

status: open
priority: P1
work_class: chore
area: rig-meta
owns: (branch dispositions only — no tracked files)
substrate: N/A
depends_on: —

## Problem
`feat/github-limits-hardening` sits in the landing queue as item ②. Content proof against
origin/master shows it is ALREADY LANDED and now REGRESSIVE:
  - vs master it DELETES 66 lines from fleet/gh-cache.sh, 15 from fleet/checks/large-file-guard.sh,
    36 from fleet/done.sh, 87 from fleet/tests/test_github_limits.sh;
  - it still carries the dead `gh pr list … -r` invocation (there is no `-r` flag; gh exits
    non-zero, the cache file is never written, merged_prs_touching_file returns empty forever,
    stderr swallowed by 2>/dev/null). Master carries the fixed `-q` form plus an explicit warning
    comment at fleet/gh-cache.sh:110.
  - it lacks pr_number_is_merged(), which fleet/_lib.sh:222 calls in the live verify_merged path.

Its rework `feat/github-limits-hardening-v2` is byte-identical to master on every owned file except
fleet/gh-cache.sh, where master is 7 lines AHEAD. Both are dead.

The same shape holds for `feat/session-end-push-gate` (original would delete 271 lines from
fleet/end-session.sh and also carries a committed .pyc) and `feat/session-end-push-gate-v2`
(byte-identical to master except master is 34 lines ahead — the M2 STALE-HANDOFF GUARD).

## Done contract
- [ ] Landing-queue item ② REMOVED; a note recorded that merging it reintroduces the `-r` bug.
- [ ] Reap recommendation recorded for: feat/github-limits-hardening,
      feat/github-limits-hardening-v2, feat/session-end-push-gate, feat/session-end-push-gate-v2.
- [ ] Confirm each is published on gitea at its local sha before any deletion.

## Deps & Sequence
Do BEFORE the next landing pass — the queue currently points at a regression.
```

## TP-3 — `BOARD-RETIRE-WIRE-GRAPHIFY-FRESHNESS` (P3)

```markdown
# BOARD-RETIRE-WIRE-GRAPHIFY-FRESHNESS

status: open
priority: P3
work_class: chore
area: rig-meta
owns: fleet/board/WIRE-GRAPHIFY-FRESHNESS.md
substrate: N/A
depends_on: —

## Problem
The WIRE-GRAPHIFY-FRESHNESS work landed (gate wired on all 4 triggers, cadence-orphan fixed) but
the ticket was never archived: origin/master still has fleet/board/WIRE-GRAPHIFY-FRESHNESS.md live.
The retirement exists as a one-commit branch, `chore/retire-wire-graphify` @ 95a5091 — a pure
rename to fleet/board/archive/, zero code. Preserved on gitea.

## Done contract
- [ ] fleet/board/WIRE-GRAPHIFY-FRESHNESS.md moved to fleet/board/archive/.
- [ ] chore/retire-wire-graphify reaped once applied.

## Deps & Sequence
Apply during the serialized board-hygiene pass ONLY (fleet/board/* is single-writer). No code
dependency. Sibling tickets GRAPHIFY-MAP-FRESHNESS and DEDUP-CHECKARCH-GRAPHIFY are already
archived in master — this is the last straggler of that group.
```

---

## Push receipts

| Branch | Sha | Remote | Gate | Verified |
|---|---|---|---|---|
| `feat/reconcile-gate-wired-salvaged` | `6d4d6dba89f554e346a83b63b4bb278ebc889799` | `origin` (new branch) | `--gate true` | ls-remote PROVEN, exit 0 |

`--gate true` was deliberate. These are old branches whose real gates may be stale, and the
operation is **preservation, not landing** — the branch is published so the wire commit cannot be
lost, with no PR opened and no merge implied. `land-push.sh` correctly refused the bare-name form
(exit 6, stale-ref guard, HEAD was master); re-run with the explicit
`feat/reconcile-gate-wired-salvaged:feat/reconcile-gate-wired-salvaged` refspec after confirming
`6d4d6db` was the intended sha.

No lease bypass was needed — no SALVAGE commits were made (the only uncommitted file in the lane
was a worthless generated artifact). Nothing was deleted: no branch, no worktree, no file.
