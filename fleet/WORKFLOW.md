# Charon Fleet — Ticket Workflow (top-to-bottom, authoritative)

How a Charon ticket is worked, documented, landed, and closed — the exact process this
fleet runs. Two roles, never blurred:

- **OPERATOR** opens droid tabs and runs pushes. Never gates/merges logic.
- **MANAGER** (a watching Claude session) gates + merges + unblocks. **Never** launches
  droids (`fleet-droid.sh`/`claude --bg`) and never pushes (blocked).

Ticket pool: `board/<ID>.md` (metadata) + `../prompts/<id>.md` (work spec).
State (runtime, git-ignored): `state/{claims,submitted,done}/<ID>`.

---

## 0. Ticket states (the machine)
```
ready ──claim.sh──► claimed ──submit.sh──► PR-OPEN ──done.sh(merge-proof)──► done
  ▲                    │                      │
  └──release.sh────────┘                      └──reject.sh (PR closed unmerged) ──► ready
```
- `claim.sh` is atomic (flock) and only claims a ticket whose **deps are all done**
  (multi-dep, comma-separated, case-insensitive).
- `done.sh` **refuses** unless a MERGED PR exists for the branch (`--no-verify` to override).
- `reject.sh` is the inverse of `submit` (clears claim+submitted → ready). Use it, never a
  manual `rm`.
- Every id is canonicalized to the exact `board/` basename — case can't fork state.

---

## 1. DROID workflow (what each ticket session does, in order)
A droid is launched by the OPERATOR as one tab: `bash fleet-droid.sh <opus|sonnet|haiku>`.
It claims ONE ticket and runs `claude -p` with `JOIN-PROMPT.md` + the ticket. Then:

1. **Worktree off the LATEST `origin/master`** (never the main checkout, never stale local
   `master`). Retry cleanup removes the local worktree/branch AND the lingering remote
   branch:
   ```
   git -C /home/stack/code/charon fetch origin --quiet
   git -C /home/stack/code/charon worktree remove --force /home/stack/code/charon-fleet-<id> 2>/dev/null || true
   git -C /home/stack/code/charon branch -D <branch> 2>/dev/null || true
   git -C /home/stack/code/charon push origin --delete <branch> 2>/dev/null || true
   git -C /home/stack/code/charon worktree add /home/stack/code/charon-fleet-<id> -b <branch> origin/master
   cd /home/stack/code/charon-fleet-<id>
   ```
2. **Read first:** the ticket + its prompt, plus `docs/DECISIONS.md`, the relevant `docs/adr/*`,
   and prior `docs/review-log/*` fragments. Never silently re-decide a Settled `OP`-owned row.
3. **Ownership = single source of truth.** Create/edit ONLY the files in the ticket's
   `owns:` line. The work-spec never widens that — `owns:` wins. If the work genuinely needs
   a file outside `owns:`, **STOP** (`release.sh <id>`) and report — do not create it (that
   double-claims another ticket's file).
4. **Build.** Privileged core stays **stdlib-only**; no `pip install -e`; no secrets in the
   repo. Keep the gate GREEN on **every commit**:
   ```
   PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src/charon ; \
   python3 tools/check_boundary.py src ; python3 tools/check_version.py
   ```
   New behaviour ships with its test in the same commit. Conventional Commits only.
5. **Document the work** as a per-ticket fragment: write your review/decision note to
   **`docs/review-log/<id>.md`** (your own file). **NEVER** append to the shared
   `docs/REVIEW-LOG.md` — it's a generated rollup (`tools/render_review_log.py`); a shared
   append collides with other droids.
6. **Scope self-check before the PR:**
   ```
   git -C <worktree> diff --name-only master...HEAD
   ```
   Every path must be in `owns:` (your `docs/review-log/<id>.md` fragment is the only extra).
   Anything else → do NOT open the PR; `release.sh` and report.
7. **Open a DRAFT PR, base master, then STOP:**
   ```
   gh pr create --repo SLOP-Platform/charon --base master --draft --fill
   bash submit.sh <id>
   ```
   The droid **never** marks ready, never merges. It stands down.

---

## 2. MANAGER workflow (gating + landing, in order)
1. **Before naming any tab:** `bash validate_board.sh` must be GREEN (no missing prompt, no
   live double-claim, no bad dep, no dup branch, no orphan marker). RED = fix first.
2. **Watch ground truth:** `bash status.sh` (live tabs + board + PRs/CI) and `bash board.sh`.
   "Working" = a tab process alive AND holding a claim — not a self-report.
3. **Gate each submitted PR** — ALL must hold:
   - `gh pr checks <n> --repo SLOP-Platform/charon` → `gate` PASS (green).
   - `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN`.
   - **diff ⊆ `owns`:** `gh pr view <n> --json files` — every path in the ticket's `owns:`
     (+ its `docs/review-log/<id>.md` fragment). A stray file = reject, don't merge.
   - Conventional commit subject; no secrets; no `pip install -e`.
   - Used a **fragment**, not the shared `REVIEW-LOG.md`.
   - Consistent with `docs/DECISIONS.md` — flag (don't merge) anything contradicting a
     Settled row; re-confirm `OP`-owned rows with the operator.
4. **Land it (merge-proof order):**
   ```
   gh pr ready <n> --repo SLOP-Platform/charon
   gh pr merge <n> --repo SLOP-Platform/charon --merge --delete-branch
   git -C /home/stack/code/charon fetch origin --quiet && git -C /home/stack/code/charon merge --ff-only origin/master
   # VERIFY state==MERGED and master advanced BEFORE the next line:
   bash done.sh <id>      # refuses unless a MERGED PR exists; unblocks dependents
   ```
   Never run `done.sh` before confirming the merge landed.
4b. **Red or contested → auto-review THEN escalate (don't dump a raw red PR on the operator).**
   When a PR is CI-red, out-of-scope, or touches a Settled / `OP`-owned decision, the manager
   MAY spawn ONE **read-only adversarial reviewer** (an analysis subagent that merges nothing,
   pushes nothing, mutates nothing — spawning read-only review is allowed; spawning state-
   mutating WORKERS is not, that's the SLOP-incident guardrail). Prompt it to REFUTE the PR
   (find why it's wrong), not bless it. Then present the operator BOTH the reviewer's verdict
   AND the raw facts (the actual CI failure, the diff, the decision it touches) — never the
   verdict alone, so the operator can judge cold and the review augments rather than replaces
   the human check. The operator then: **accepts**, **rejects** (below), or **escalates to a
   DTC** (full debate-to-consensus, reserved for irreversible / first-of-kind calls).
5. **Reject path** (CI red / out-of-scope / wrong): do NOT merge. Diagnose. If it's a ticket
   bug, stage a fix ticket. To re-run:
   ```
   gh pr close <n> --repo SLOP-Platform/charon --comment "<why>"
   bash reject.sh <id>     # back to ready; operator re-opens a tab
   ```
6. **Recovery:**
   - Stale-base / behind master → `gh pr update-branch <n>` (re-runs CI against current master).
   - Stuck claim (crashed tab) → `bash release.sh <id>`.
   - Shared-doc (REVIEW-LOG rollup) conflict → resolve in a worktree, re-render
     `tools/render_review_log.py`, operator pushes.

---

## 3. Files touched when a ticket CLOSES
- The ticket's **owned source + test files** (in the merge commit).
- **`docs/review-log/<id>.md`** — the per-ticket fragment (the rollup `docs/REVIEW-LOG.md`
  is regenerated, never hand-edited).
- **State markers** — handled by `done.sh` (writes `state/done/<id>`, clears claim+submitted).
- If the ticket settled a decision: a new row in **`docs/DECISIONS.md`** (append above the
  marker line) and/or the relevant **`docs/adr/*`** — via the ticket's owns, not silently.

---

## 4. Adding work to the board
1. `board/<id>.md`: `tier` · `branch` · `depends_on` (comma-sep ok) · `owns` (disjoint within
   a wave; include the ticket's OWN test files) · `prompt:` pointer.
2. `../prompts/<id>.md`: the work spec. End with the CONSTRAINTS block restating "own ONLY
   the files in your board `owns:`".
3. `bash validate_board.sh` → GREEN before launching. Same-wave tickets must own disjoint
   files; cross-wave collisions are sequenced via `depends_on`.

---

## 5. Hard rules (never violate)
- Droids open DRAFT PRs and **never merge**; the manager merges (propose-default).
- Manager **never** launches FLEET BUILD-DROIDS (the product workers) — operator's job, the
  SLOP-incident guardrail. But it **SHOULD delegate its OWN substantive work** (investigation,
  audits, analysis, contained implementation, drafting) to **sub-sessions** to keep the primary
  session lean for operator communication — reviewing/owning the result in primary. Keep work
  in the primary session only when it must be: gating decisions, merges, pushes, operator
  dialogue, quick inline state checks, and tightly-sequenced mutations. (Read-only reviewers are
  always fine; a delegated implementation sub-session may mutate, but the manager owns the
  result.) Manager **never** pushes by hand; pushes go through the gated `land-push.sh` and only
  when the **AUTONOMOUS** lever is ON (else the operator pushes).
- Privileged core = **stdlib-only**; no `pip install -e`; **no secrets** committed.
- One file is owned by exactly one in-flight ticket. Need another's file → STOP.
- Gate green every commit; conventional commits; per-ticket review-log fragment.
- A review/DTC that overturns an `OP`-owned decision must be **re-confirmed**, not
  auto-reconciled.
