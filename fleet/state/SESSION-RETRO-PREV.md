# SESSION RETRO — the PREVIOUS session (2026-08-02)

**Source:** `fleet/state/PRIORITY-TODO.md` §F1–F11, §J, §L and the "FRICTION FROM 2026-08-02"
block — a self-authored confession list. Extracted and sharpened here, not re-derived.

**Method note [[confirm-dont-trust-documentation]]:** every claim below was re-checked against the
live system on 2026-08-02 before it was written down. Where a claim could NOT be confirmed it is
marked `UNVERIFIED` rather than stated. That is F9 applied to this document itself.

---

## THE FAILURES

| what went wrong | evidence | the fix (COMMAND or RULE) | fix landed? |
|---|---|---|---|
| **Launched droids with `run_in_background`.** They were children of the manager's own session — invisible to the operator and dead the instant the session ended. The operator had to say it **three times**. `fleet/spawn-tab.sh` and `fleet/TOOL-INVENTORY.md` existed the whole time. | §F1 | `bash fleet/spawn-tab.sh <name> '<#hex>' bash fleet/fleet-droid.sh <economy\|strong\|frontier> --wait 2 --retries 0` — and for reviewers `bash fleet/reviewer-tab.sh --tier <strong\|frontier> --wait 5 --retries 0`. `reviewer-tab.sh` is a launcher-of-a-launcher: never wrap it in `spawn-tab.sh`, and its CLI is `--tier strong`, not a bare `strong`. **RULE: no droid is ever launched from the session's own process tree.** | **YES** — `fleet/spawn-tab.sh` exists and is executable. |
| **Wrote 688 lines of handoff and verified none of it until asked.** Two load-bearing claims in that very file were wrong on first draft: "a ppid of 1 means detached" (false — real detached tabs show a `bash`/`timeout` parent from the WT spawn chain) and "monit already adopted" (disproved by one `command -v`). | §F9 | **RULE: before handing off, execute every command you wrote down and stamp each claim `VERIFIED <date>` or delete it.** An unverified procedure in a handoff is not guidance, it is a trap with your name on it. The §F9 VERIFIED block (10 commands, each actually run) is the shape to copy. | **PARTIAL** — the rule is written into PRIORITY-TODO §F9 and a VERIFIED block exists; there is **no mechanized gate** that refuses an unstamped handoff. `fleet/handoff-check.sh` exists but does not enforce per-claim stamping. |
| **Reviewer pools launched with `--retries 0` spun to `cycle 461/0` and drained the entire GraphQL quota to 0/5000.** `--wait` is silently dropped by `review-pool.sh` (`main_loop "$CMD"`), so the pool never stood down; each cycle issues a `gh` GraphQL call ("syncing review queue"). Killing the pools took GraphQL from **0/5000 → 3784/5000 immediately**. That is why `land-push` could not verify CI all session and why every board push needed the logged `--force`. | §F10, §F5 | Never `--retries 0` for a reviewer. Keep the pool at 1–2. Check `gh api rate_limit --jq '.resources.graphql'` **before** scaling. If `cycle N/0` climbs fast the wait is being dropped — `pgrep -f 'bash .*review-pool\.sh' \| xargs -r kill`, do not wait it out. **RULE: REST is free, GraphQL is the binding constraint** — `gh api repos/.../pulls` not `gh pr list`. | **NO** — the real fix is PR #392 (PR-QUEUE-REST-ETAG, REST+ETag ⇒ zero-quota steady state); still in flight. Until it lands this is a hand-applied discipline only. |
| **The harness task list was used ZERO times despite ~20 reminders**, so promised work was silently dropped. Compounding it: last session tracked 24 items in that list, 15 still open at close, and **none of them would have survived** the session. | MANAGER-OPERATING-RULES §0; §F11 | **RULE: the harness task list is a working set, not a record.** Anything that matters becomes a BOARD TICKET or a line in `fleet/state/PRIORITY-TODO.md` before the turn ends. §F11 shows the conversion done by hand at close (SPILL-UP-CEILING-SSOT · LAND-PUSH-WORKTREE-STATE · SUBSTRATE-OWNS-WORD-BOUNDARY · LAUNCHER-LEAKGUARD-NONFATAL · BRIDGE-RESTORES-DISABLED-MODELS · MODELS-JSON-STRUCTURAL-LIMITS). | **NO** — durable-conversion happened once, manually, at close. Nothing forces it and nothing forces the list to be *used*. |
| **Measurement patterns that lie — fell for all four.** | §F3 | `pgrep -c -f 'review-pool.sh'` matches the string inside droid PROMPTS and counts parent+child as 2 — **tab count ≠ process count**. · `git merge-base --is-ancestor B M` is WRONG here: we **squash-merge**, so a merged branch is NEVER an ancestor — **use PR state, not ancestry**. · `curl -s … \| head -c 60 && echo OK` prints OK for a dead endpoint because **`head` exits 0 on empty input** — check the BODY, not the exit code. · `grep -c PARKED <file>` — confirm the hit is in the FIELD you mean, not in prose. **RULE: every measurement must be able to return the answer you don't want.** | **NO** — documented in §F3, zero mechanization. |
| **Operator action #15 went unread for THREE sessions.** GATE 4 UNDELIVERED: `fleet/handoff-notes/LETTA-REVIEW.md` and `MEMORY-LAYER-REVIEW.md` were commissioned, completed, and never read or reported; `grep -c Letta EVAL-REGISTRY` = 0, ~10 verdicts owed. | `fleet/pending.sh list` (#15, "Survived 2 sessions unread" — now three). VERIFIED 2026-08-02: `fleet/preflight.sh:1095` runs `show_operator_actions` **dead last**, after ~20 gates plus the full foreman advisory dump. The action list is structurally the most-buried output of the session's longest command. (The specific "200s cap" figure is **UNVERIFIED** — no `head -c`/timeout cap on that path was found; the burial is by ORDERING.) | **RULE: run `bash fleet/pending.sh list` on its own, FIRST, before reading any preflight output** — never rely on scrolling to the end of a scan. And triage the list before adding to it. | **NO** — `show_operator_actions` is still the last call on `preflight.sh:1095`. The surfacing order is unchanged. |

---

## THE SECOND-ORDER PATTERN

Every row above is the same shape: **a mechanism existed and was not reached for.**
`spawn-tab.sh` existed. `TOOL-INVENTORY.md` existed. `pending.sh list` existed. `gh api rate_limit`
existed. The failure was never a missing tool — it was recall substituted for mechanism, then a
document written to compensate for the recall. §F11 and §F9 are the same defect at two altitudes:
state that only lives in one session's head, handed off as prose nobody executed.

---

## WHAT I WILL DO DIFFERENTLY THIS SESSION

Five commitments, each mechanically checkable — not intentions.

1. **Zero droids launched with `run_in_background`.** Every launch goes through
   `fleet/spawn-tab.sh` (or `fleet/reviewer-tab.sh` for reviewers, un-wrapped).
   *Check:* every launch command in my transcript begins `bash fleet/spawn-tab.sh` or
   `bash fleet/reviewer-tab.sh`.

2. **Zero reviewer launches with `--retries 0`, and `gh api rate_limit --jq '.resources.graphql'`
   is read BEFORE any pool is started or scaled.**
   *Check:* GraphQL remaining never reaches 0 this session; no `--retries 0` appears in any
   reviewer launch line.

3. **Every claim I write into a handoff, ticket, or report carries either the command that proved
   it or the token `UNVERIFIED`.** No claim inherited from a prior document is repeated without
   re-running its check.
   *Check:* `grep -c UNVERIFIED` on anything I author is > 0 or every claim has a command beside it.

4. **`bash fleet/pending.sh list` is run STANDALONE as my first command, and every item I can prove
   closed is retired with `bash fleet/pending.sh done <label>` before I add a single new one.**
   *Check:* the open-item count goes DOWN this session, not up.

5. **Nothing I promise lives only in the harness task list.** Every commitment becomes a board
   ticket or a line in `fleet/state/PRIORITY-TODO.md` in the same turn it is made — and I use the
   harness task list *as well*, as the working set it is.
   *Check:* at close, the harness list and the durable record agree; no open harness item lacks a
   board/PRIORITY-TODO counterpart.
