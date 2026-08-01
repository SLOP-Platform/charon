# PR Triage: #189 and #193 (read-only review, 2026-07-31)

Prior triage (2026-07-31, local-worktree-only) recommended ABANDON for both, citing
"review fragment for a design doc never written" (189) and "design absent" (193).
Verified against **origin** branch content (not local worktrees). Both branch SHAs
confirmed to match the live PR heads (`gh pr view --json headRefOid`).

## Method
- `git diff origin/master...origin/<branch> --stat` (three-dot only, per repo convention)
- `git cat-file -e` checks for the named deliverable path on master / branch / all history
- `git log origin/master --oneline --grep=<keyword>` for supersession
- `git rev-list --count` both directions for drift
- `gh pr checks <n>`

## PR #189 — feat/price-tracked-inventory-autoswap
**What's on the branch:** exactly one file,
`docs/review-log/PRICE-TRACKED-INVENTORY-AUTOSWAP.md` (48 lines, +48/-0). It is a
review-log fragment, not the ticket's actual deliverable. The board ticket
(`fleet/board/PRICE-TRACKED-INVENTORY-AUTOSWAP.md`, still open on master, unarchived)
requires `owns: fleet/state/PRICE-TRACKED-INVENTORY-AUTOSWAP-DESIGN.md` — that file
does **not exist** on the branch, on master, or anywhere in `git log --all`. Confirmed:
the prior triage's "design doc never written" claim is correct.

**Drift:** 476 commits behind origin/master, 1 ahead (the fragment commit only).

**Supersession — the real finding.** The fragment proposes composing 4 existing pieces.
Checked each on origin/master:
1. Fresh pricing (`PROVIDER-CATALOG-REFRESH`) — **DONE**, independently. `ROADMAP.tsv`:
   `PROVIDER-CATALOG-REFRESH done - provider-catalog-refresh ... (wired)`.
2. Drift alert (R17 `pricing_limits_checker`) — **DONE**, independently. Landed via
   ROUTER R17 commits (`752cfef`, marked done in `1cc5521`), well before this PR opened.
3. Inventory-as-data (KS29 registry table) — **DONE**, independently, via merged PR #205
   `feat(inventory-table)` (commit `bcc2a15`) — same operator 2026-07-23 provider list
   (synthetic/trae/HF/nous/grok/mistral/zai/cerebras/deepinfra/deepseek/together/groq/
   morph) that this fragment cites. `fleet/state/price-tracked-inventory.tsv` +
   `fleet/inventory-table.sh` already live on master.
4. Auto-swap / single-leg RED — **NOT done**, but tracked as its own separate, still-open
   board ticket `SINGLE-LEG-AUTOSWAP` (P1, `depends_on: INVENTORY-TABLE`, owns
   `fleet/single-leg-guard.sh`) — confirmed never dispatched (no branch/PR exists per
   `fleet/handoff-notes/NEVER-DISPATCHED-AUDIT.md`). This gap is NOT part of PR #189 and
   closing #189 does not touch it.

So 3 of the 4 pieces this PR's fragment was "designing" already shipped through
independent tickets, and the 4th has its own independent open ticket. PR #189 itself
delivers zero code and its named deliverable was never produced.

**CI:** all green (bandit/gitleaks/semgrep/rig-ci) — meaningless signal, the diff is a
markdown-only add.

**Verdict: CLOSE-SUPERSEDED**

**Disposition on prior triage: PARTIAL OVERTURN.** The "close it" action is confirmed,
but the *reason* was incomplete — this isn't just an orphaned fragment for work that
never happened, it's superseded: the described system was already built, piece by piece,
through other already-merged tickets, independent of this PR. Nothing is lost by closing:
the remaining real gap (single-leg auto-swap) already has its own live board ticket
tracking it.

## PR #193 — fix/inert-wiring-enforcement-durable
**What's on the branch:** exactly one file,
`docs/review-log/INERT-WIRING-ENFORCEMENT-DURABLE.md` (35 lines, +35/-0). Same pattern:
review-log fragment, not the deliverable. Board ticket
(`fleet/board/INERT-WIRING-ENFORCEMENT-DURABLE.md`, still open/unarchived on master)
requires `owns: fleet/state/INERT-WIRING-ENFORCEMENT-DESIGN.md` — confirmed **absent**
everywhere (branch, master, `git log --all`). Prior triage's "design absent" claim is
correct.

**Drift:** 476 commits behind origin/master, 1 ahead (fragment commit only).

**Supersession — partial only, core ask still undone.** The fragment spawned a 9-item
backlog. Checked each on origin/master:
- #1 GRAPHIFY-FRESHNESS-MERGE — **landed** independently (PR #232,
  `fix(WIRE-GRAPHIFY-FRESHNESS): fire graphify cadence from the real timer entrypoint`).
- #6 CATALOG-GATE-WIRE — **landed** independently (`970d642`, `957ac40`), now archived.
- The other 7 items (NO-ANTHROPIC-SG-WIRE, BASE-INTEGRITY-WIRE, DARK-WORK-WIRE,
  RULE-SYNC-WIRE, WIRING-MANIFEST-GATE-BUILD, WIRING-MANIFEST-SEED,
  PRODUCT-WIRING-META-EXTEND) — **zero hits** anywhere on master; never built.
- The actual core ask of the ticket — a WIRING-MANIFEST + dual meta-gate durable
  anti-decay mechanism — was **never built anywhere** under any name. No board file,
  no commit, no PR matches. The board ticket itself is still open, unarchived, still
  asking for this.

**CI:** all green — meaningless (markdown-only diff).

**Verdict: CLOSE-ABANDON**

**Disposition on prior triage: CONFIRM**, with one amendment worth recording: 2 of the
9 spawned backlog items (graphify-freshness wiring, catalog-gate wiring) already shipped
via their own independent tickets, so closing #193 loses nothing there either. What
would genuinely be lost by closing: nothing — the PR never contained the design doc, so
the WIRING-MANIFEST root-cause design work still has to be done from scratch regardless
of whether this stale PR stays open or closes. The live, unarchived board ticket
`INERT-WIRING-ENFORCEMENT-DURABLE` is the correct place to re-drive that work, not this
PR (whose branch/worktree is 476 commits stale and contains no salvageable code).

## Summary table
| PR | Verdict | Prior triage | Agreement |
|----|---------|-------------|-----------|
| #189 price-tracked-inventory-autoswap | CLOSE-SUPERSEDED | ABANDON | partial overturn (right action, incomplete reason — 3/4 pieces already shipped elsewhere) |
| #193 inert-wiring-enforcement-durable | CLOSE-ABANDON | ABANDON | confirm (core ask still fully undone; 2/9 backlog items independently shipped, nothing lost) |
