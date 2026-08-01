# PR triage: #211, #263 — 2026-07-31 (read-only review)

Repo: Nnyan/charon-private. All commands run against `origin/*` refs after `git fetch origin`.
No merges/pushes/closes/commits performed.

## #211 feat/reconcile-gate-wired (8 days old)

**Verdict: CLOSE-SUPERSEDED**

1. **Diffstat** (`git diff origin/master...origin/feat/reconcile-gate-wired --stat`): only
   3 files, +482/-0 (docs/review-log, fleet/checks/reconcile-gate-wired.sh,
   fleet/tests/reconcile-gate-wired.test.sh). **NOT** the enormous graphify-out/ diff the
   prior session flagged — that divergence was already resolved: `git log` shows
   `0cd6d17 board-hygiene: RECONCILE-GATE-WIRED -> fresh branch name after divergence`,
   which spun the content off onto `fix/reconcile-gate-wired-v2` instead of this branch.
   So #211's *current* diff is small/clean, but it is stale content, not stale-because-huge.
2. **Superseded**: confirmed by content, not just ticket state. `git show
   origin/master:fleet/checks/reconcile-gate-wired.sh` **exists on master**. `git log
   origin/master --oneline --grep reconcile-gate` shows the full lineage:
   `940bce8 feat(reconcile-gate-wired): built-but-inert meta-gate (detector, no wire)` →
   `6d4d6db fix(reconcile-gate-wired): salvage + WIRE the built-but-inert meta-gate` →
   `0cd6d17 board/rename after divergence` → `38dd148 Merge PR #284
   board/reconcile-gate-rename` → `0be7d6f Merge origin/master into fix/reconcile-gate-wired-v2`
   → `7b2908b Merge pull request #285 from Nnyan/fix/reconcile-gate-wired-v2`. Master already
   has both the detector AND the wiring; #211 only ever had the unwired detector half.
3. **Scope vs ticket**: `fleet/board/RECONCILE-GATE-WIRED.md` owns:
   `fleet/checks/reconcile-gate-wired.sh, fleet/tests/reconcile-gate-wired.test.sh` — matches
   #211's file list exactly. `fleet/state/done/RECONCILE-GATE-WIRED` marker exists, consistent
   with #285 having landed the accepted version.
4. **Drift**: `git rev-list --count origin/feat/reconcile-gate-wired..origin/master` = **453**
   commits behind master (`git rev-list --count origin/master..origin/feat/reconcile-gate-wired`
   = 1, i.e. one commit not on master — the superseded/duplicate one). Heavily stale.
5. **CI** (`gh pr checks 211`): rig-ci **fail** (fails at "Board validation" step — board entry
   presumably conflicts with the now-`done` ticket state); bandit/gitleaks/semgrep pass.
   `gh pr view` reports `mergeable: CONFLICTING`.

**Disposition: close #211 as superseded by #285 (merged 2026-07-31, commit 7b2908b). No
salvageable content — master already has both halves (detector + wire) #211 was missing.**

---

## #263 feat/router-ledger-decay (7 days old)

**Verdict: NEEDS-WORK** (not superseded, not merge-ready as-is)

**MONEY-PATH: effectively NO today, but YES-INTENDED once wired — adversarial review IS
required before it is ever wired into live routing.**

1. **Diffstat**: 3 files, +367/-0 (docs/review-log, `src/charon/routing_policy/ledger_decay.py`
   — 108 lines, `tests/test_ledger_decay.py` — 210 lines). Not enormous, no accidental build
   output.
2. **Superseded?** No. `src/charon/routing_policy/` does not exist on master at all
   (`git show origin/master:src/charon/routing_policy/ledger_decay.py` → missing). No related
   master commits (`git log origin/master --grep "ledger.decay" -i` → empty).
3. **Scope vs ticket — VIOLATION FOUND**: `fleet/board/ROUTER-LEDGER-DECAY.md` explicitly
   gates this as a "build-when-needed" ticket: *"the router does not yet consume time-decayed
   model signals; wire it only when the actuals/model-signal ledger is the live ranking
   input."* Its `accept:` block requires **FAIL-ON-REVERT: ... the decay is actually applied
   in the router ranking path (not just defined)** and **GREEN-IS-NOT-PROOF: demonstrate a
   routing decision that flips ... BECAUSE a stale model signal decayed — not merely that the
   math function returns a smaller number.**
   Checked with `git grep -l ledger_decay` across the branch: **only the test file imports
   `charon.routing_policy.ledger_decay`** — no ranking/router file consumes it. The PR built
   the pure-math decay function and its own unit test only, exactly repeating the pattern the
   ticket's own `note:` says to avoid (the retired `fleet/memory/bitemporal.py` was "NEVER
   wired to the router — only its own test imported it"). **The PR does not meet its own
   ticket's accept criteria and is currently inert/self-tested-only.**
4. **Drift**: `git rev-list --count origin/feat/router-ledger-decay..origin/master` = **372**
   commits behind master (1 commit ahead — the new module). Stale branch, will need rebase
   regardless of the scope issue above.
5. **CI** (`gh pr checks 263`): rig-ci **fail** (fails at "Rig test suites (ALLOWLIST only)"
   step — consistent with the module being untethered from anything the allowlisted suites
   exercise); bandit/gitleaks/semgrep pass. `gh pr view` reports `mergeable: MERGEABLE`.

**Disposition: do not merge as-is.** Two independent reasons to hold: (a) it fails its own
ticket's accept/FAIL-ON-REVERT criteria — pure math with no wiring is exactly what the ticket
says NOT to ship; (b) it is money-path-adjacent — `ledger_decay.py` is designed to reweight the
model-signal ledger that feeds routing rank, per memory `Pool is single-source already`
(cheapest-per-model router is LIVE) — so **the moment anyone wires this in, it changes routing
decisions and requires adversarial review before merge**, per standing directive
(`e2e-dogfood-norm-for-money-code`, `security-is-a-ratchet-gate`). Recommend: either (1) close
as premature/park until the model-signal ledger is confirmed to be a live ranking input, or
(2) send back to build the wiring + the flip-a-routing-decision proof the ticket demands, and
route THAT revision through adversarial review before merge.
