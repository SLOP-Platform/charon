# Adversarial review — rig PR #104 (MEMORY-INDEX-COMPACTION)

Repo: Nnyan/charon-private · Branch: feat/memory-index-compaction · Base: master · State: OPEN

## VERDICT: NEEDS-WORK

**Not crash-partial in the "empty deliverable" sense.** The crash-signal title belongs to the
SECOND commit only. Commit history:

- `f3776cee` feat(fleet/hooks): add memory-compact.sh — **the real, complete deliverable**
  (docs/review-log/MEMORY-INDEX-COMPACTION.md +89, fleet/hooks/memory-compact.sh +211,
  fleet/tests/memory-compact-hook.test.sh +232 = 532 insertions)
- `a349b0d5` chore(...): launcher auto-commit — **contains ONLY** fleet/board/REVIEWER-DOGFOOD-REDS.md +41

So the droid committed its work BEFORE crashing; the launcher auto-commit then swept in one
unrelated stray board file. The mechanism itself is substantive and the 23-assertion test suite
runs green locally. But it fails review on correctness-against-real-data, a vacuous test pair,
and an unmet accept bullet.

---

## Accept-bullet judgement

### Bullet 1 — NEW fleet/hooks/memory-compact.sh: threshold, one-line invariant, flags stale/dupes, reports size, never deletes a topic file, idempotent
**PARTIAL — mechanism present but semantically wrong against the real index.**

Present and working:
- Threshold gate: `fleet/hooks/memory-compact.sh:78-81` — `MEMORY_THRESHOLD_BYTES` default 17408, no-op under.
- Never deletes a topic file: script only ever writes `$INDEX_PATH` (`:191-199`); no `rm` of any `*.md`.
  Verified by test (e) `fleet/tests/memory-compact-hook.test.sh:186-197` (50 referenced + 1 decoy all survive).
- Atomic write: tmpfile + `mv -f`, `fleet/hooks/memory-compact.sh:191-199`.
- Idempotent: second run falls under threshold → no-op. Test (c) `:161-172`.
- Duplicate flagging without auto-removal: `:158-162` + test (d) `:174-190`.
- Size report: `:167-169`.

**BLOCKER 1 — the "detail leak" definition matches 100% of well-formed real entries.**
The script classifies ANY text after the closing `)` as leaked detail and strips it
(`fleet/hooks/memory-compact.sh:121-127`, RE_PURE vs RE_LEAK at `:114-115`).
But the live index's canonical, *by-design* line form IS `- [Title](file.md) — one-line summary`.

Read-only dry-run against the real memory dir
(`/home/stack/.claude/projects/-home-stack-code-charon/memory`):

```
memory-compact: index 20045B -> 8172B (120 lines)
memory-compact: pointer lines preserved: 0; truncated to pointer: 118; section headers/blank: 1
memory-compact: STALE / detail-leak flags ...
  - real-work-is-the-trust-test.md: detail leaked into index (truncated to pointer)
  - evaluate-tools-by-code-not-stars.md: detail leaked into index (truncated to pointer)
  ...
```

`pointer lines preserved: 0` / `truncated to pointer: 118` is the smoking gun: the hook
considers **every single entry** in the live index to be a leak and would strip the summary
from all 118. The summary is the index's entire informational value — it is what tells the
manager which topic file to open. Post-compaction the manager sees 118 bare titles and must
read 118 files to recover what one 20KB index used to convey.

The ticket's own `note:` calls the index "a one-line-per-entry POINTER list" that bloats when
"the description leaks into the index line" — i.e. the invariant is ONE LINE per entry, not
ZERO detail per entry. The script conflates the two. The ticket `scope:` warns "a bad compaction
could drop a pointer"; this is worse in kind — it preserves all pointers and drops all 118 summaries.

Corollary: the stale-flag report is pure noise — all 118 entries get flagged "stale", so the
"flags stale pointers for review" accept sub-clause is met only vacuously.

The droid's own review log (`docs/review-log/MEMORY-INDEX-COMPACTION.md:79-86`) pastes this exact
`preserved: 0 / truncated: 117` dry-run output and reads it as SUCCESS. It is the defect.

### Bullet 2 — WIRED into SessionStart (and/or PostToolUse), per dynamic-tools-never-on-demand — not a manual step
**NOT-MET.** Nothing in the diff wires anything. The droid self-granted a scope reduction:
`docs/review-log/MEMORY-INDEX-COMPACTION.md:68-74` — "Why not also wire it into SessionStart/PostToolUse …
is out of scope for this ticket", and `:88` — "The manager reviews this run, then wires the settings.json
hook entry."

That leaves the fix as a manual step the manager must remember — which is *precisely* the
`dynamic-tools-never-on-demand` violation the ticket exists to kill (`note:` line 18-19:
"the fix must be a MECHANISM, not a reminder"). Shipping an unwired script converts a deferred
manual compaction into a deferred manual *wiring*. Net mechanization: zero.

Mitigating: the ticket's `serial_justified:` does say wiring is a settings.json ENTRY (config, not a
shared script) to dodge the `fleet/hooks/session-start.sh` owns-collision with SYNC-SCHEDULE. So the
config half is legitimately out-of-repo. But the accept bullet still demands WIRED, and the PR offers
no evidence the entry exists anywhere. At minimum this needs the operator to apply + confirm the
settings.json entry before the ticket can close — it cannot close on the script alone.

### Bullet 3 — fail-on-revert test: bloated fixture → under threshold with every pointer preserved; compact index → no-op
**MET (for the stated shape) — with two vacuous assertions.**

Real fail-on-revert coverage exists and is not a rubber stamp. Ran the branch suite: **23 passed, 0 failed.**
- (b) bloated 100 leaky entries → under threshold, all 100 pointers preserved, no `DIRECTIVE:` residue,
  all 100 topic files on disk, entry-50 sentinel intact: `fleet/tests/memory-compact-hook.test.sh:106-159`.
- (a) compact index → no-op: `:88-104`.
Delete the hook body and (a)/(b)/(c) genuinely fail. This is a real test, not a vacuous one.

**BLOCKER 2 — test (f) assertions f1/f2 can never fail.**
`fleet/tests/memory-compact-hook.test.sh:199-213`:
```bash
HOME="/dev/null/should-not-be-touched" MEMORY_DIR="$DF" bash "$HOOK" >/dev/null 2>&1
[ ! -e "/dev/null/should-not-be-touched" ] && ok "f1 ..." || bad "f1 ..."
```
`/dev/null` is a character device, not a directory, so nothing can ever be created beneath it —
verified: `mkdir -p /dev/null/should-not-be-touched` → `mkdir: cannot create directory '/dev/null': Not a directory`.
The `[ ! -e ... ]` guard therefore passes unconditionally, **regardless of what the script does**.
f1/f2 would still pass if the script ignored `MEMORY_DIR` entirely and hardcoded a path.

This matters beyond the 2 assertions: `docs/review-log/MEMORY-INDEX-COMPACTION.md:36-39` cites this
exact test as the *proof* of no-hardcoded-cross-boundary-path compliance ("proven by the test running
the script with `HOME=/dev/null/should-not-be-touched`"). That is a **false proof claim** — the
no-hardcoded-path accept bullet rests on an assertion that cannot fail. Fix: point HOME at a writable
`mktemp -d` and assert the derived default subtree was never created.

### Bullet 4 — takes memory dir as parameter/env; no hardcoded cross-boundary path
**PARTIAL.** Arg > env > default resolution is real: `fleet/hooks/memory-compact.sh:63-70`. Both the
positional arg and `MEMORY_DIR` work (exercised throughout the suite).

But `:69` still bakes the operator's exact project path into the fallback:
```bash
MEMORY_DIR="${HOME:-/root}/.claude/projects/-home-stack-code-charon/memory"
```
`-home-stack-code-charon` is a dev-box-specific project slug crossing a process boundary. The script
defends it as "a CONFIG default, not a hardcoded path" (`:65-67`) — defensible, since every other
context can override, and it is HOME-relative rather than `/home/stack`-absolute. But per
`[no-hardcoded-cross-boundary-paths]` and `[public-repo-no-personal-info]` this slug is dev-meta in a
public-adjacent repo. Prefer requiring `MEMORY_DIR` explicitly (fail with usage if unset), which also
makes the wiring in bullet 2 explicit. And as established above, the test that supposedly guards this
is vacuous.

---

## Owns / contamination

Ticket `owns:` (verbatim, line 8): `fleet/hooks/memory-compact.sh`

| File | In owns? | Note |
|---|---|---|
| `fleet/hooks/memory-compact.sh` | YES | the deliverable |
| `fleet/tests/memory-compact-hook.test.sh` | implied | test for owned script — conventionally fine |
| `docs/review-log/MEMORY-INDEX-COMPACTION.md` | implied | per-ticket review log — conventionally fine |
| `fleet/board/REVIEWER-DOGFOOD-REDS.md` | **NO** | **crash contamination — unrelated ticket** |

`fleet/board/REVIEWER-DOGFOOD-REDS.md` is a wholly unrelated eval-infra board ticket
(reviewer-dogfood reds-replay corpus / `owns: fleet/benchmark/reviewer-dogfood.sh,
fleet/state/REDS-CORPUS.md`). It has nothing to do with memory-index compaction. It entered via the
launcher auto-commit `a349b0d5` — i.e. it is stray session work the crash swept in. This is the exact
failure mode the LAUNCHER-CRASH-PARTIAL-DETECT insight predicts, just inverted: the crash didn't
truncate the deliverable, it *appended* unrelated debris.

The ticket content itself looks like real, wanted work — it should be **split out to its own commit/PR**,
not merged under this ticket's number where it is invisible to the board.

## CI / gate execution

`gh pr checks 104` → **"no checks reported on the 'feat/memory-index-compaction' branch"**.

Not itself damning: the rig repo has **no `.github/workflows/` at all**, so no rig PR reports checks —
the gate here is local `fleet/gate.sh`. Confirmed the new test IS auto-discovered:
`fleet/gate.sh:31-36` globs `tests=("$TESTS_DIR"/*.test.sh)`, so `memory-compact-hook.test.sh` is picked
up with no registration needed.

But per `[gates-must-actually-run]`: **nothing in this PR proves the gate ever executed on this branch.**
Green-by-absence is not green. I ran the suite manually off `FETCH_HEAD` (23/23 pass), which covers the
test but not the full gate. Require a gate run before merge.

## Collisions

Files touched by #104:
- `docs/review-log/MEMORY-INDEX-COMPACTION.md` (new)
- `fleet/board/REVIEWER-DOGFOOD-REDS.md` (new)
- `fleet/hooks/memory-compact.sh` (new)
- `fleet/tests/memory-compact-hook.test.sh` (new)

vs #108 (feat/startup-context-diet): `fleet/MANAGER-OPERATING-RULES.md`, `fleet/START-SESSION.md`,
`fleet/handoff.sh`, `fleet/preflight.sh` → **no overlap**.
vs #106: `fleet/handoff.sh` → **no overlap**.

All four files are NEW, so no merge contention with any open rig branch. Clean on this axis.

Forward-looking note: bullet 2's wiring is settings.json config (out-of-repo), so it will not collide
with SYNC-SCHEDULE's `fleet/hooks/session-start.sh` — the ticket's `serial_justified:` reasoning holds.

---

## Required before merge

1. **Fix the leak definition** (BLOCKER). Distinguish a one-line summary (KEEP — it is the index's
   value) from genuine multi-line/oversized detail leakage (TRUNCATE). E.g. cap the summary at N chars
   or only truncate entries whose detail exceeds a per-line budget. Re-run the live dry-run and expect
   `preserved` ≫ 0. Current behavior would strip all 118 summaries and gut the manager's recall.
2. **De-vacuum test (f)** (BLOCKER). Use a writable `mktemp -d` HOME and assert the HOME-derived
   subtree was not created. Then correct the false proof claim at review-log `:36-39`.
3. **Bullet 2 (WIRED)**: either land the settings.json entry and show it, or the operator applies +
   confirms it as an explicit pending action. The ticket cannot close on an unwired script — that
   re-creates the manual step it exists to remove.
4. **Split out `fleet/board/REVIEWER-DOGFOOD-REDS.md`** into its own commit/PR; drop the launcher
   auto-commit `a349b0d5` from this branch.
5. **Run `fleet/gate.sh` on the branch** and record it — no gate execution is currently evidenced.
6. Consider requiring `MEMORY_DIR` explicitly rather than defaulting to the `-home-stack-code-charon`
   dev slug (`fleet/hooks/memory-compact.sh:69`).

## Bottom line

The droid did NOT ship an empty PR — `f3776cee` is a genuine 532-line mechanism with a genuine
fail-on-revert test, and it survived the crash intact. But it is not merge-ready: the hook's
central heuristic misfires on 100% of real index entries and would destroy the very data it is
meant to curate, its no-hardcoded-path guarantee rests on an assertion that cannot fail, the
mechanization (wiring) bullet is unmet, and the crash left unrelated debris in the branch.

**NEEDS-WORK** — the branch is a solid base; it should be fixed forward on this branch, not redone.
