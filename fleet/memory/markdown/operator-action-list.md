---
description: Mechanized running list of things the manager needs the operator to do/decide; inline waits for answers while background runs
metadata: 
name: operator-action-list
node_type: memory
originSessionId: eaa0190c-d65a-4ac1-9b62-07c4aab515a1
type: feedback
tags: [operator]
last_referenced: 2026-07-13
---
Recurring cross-session failure: the manager stacks questions/moves faster than the operator can review and answer, so the operator keeps MISSING things. Two-part fix (operator, 2026-07-10):

**Cadence — inline waits, background runs.** Ask ONE thing, then STOP until the operator answers. Never stack a second question or move to a new topic on top of an unanswered one. Background sub-sessions/agents keep running regardless — only the inline conversation blocks. This is stronger than [[pause-after-question-or-action]] because the prior rule kept getting violated.

**Do NOT mutate the thing being answered (2026-07-10, repeated).** The operator answers asynchronously — their reply maps to what they were VIEWING when they wrote it, not your latest re-render. Re-rendering/reformatting/renumbering a list or report while they're mid-answer makes their answer land on the wrong version (happened repeatedly with the roadmap format + the decision list). Once you present something the operator is acting on, leave it stable until they respond; when a late answer arrives, map it to what they were looking at. Their earlier version is often fine — stop over-correcting format.

**Analyze in background, but HOLD/BATCH presentations — do not dribble (2026-07-10, repeated correction).** It is fine to keep analyzing background sessions and launching approved work. It is NOT fine to keep surfacing new findings/questions one at a time while a prior question is still unanswered. HOLD new presentations until the operator answers the open question(s), OR batch several into a single presentation. Dribbling questions out is the exact behavior the operator keeps flagging. When background work completes, quietly hold the result and fold it into the next batched update rather than interrupting with each one.

**Mechanized operator-action list.** A running, very simple, plain-language, letter-indexed list of everything the manager needs the operator to do/decide, updated every time a new ask appears, reviewable by letter.
- Data: `/build-rig/fleet/state/OPERATOR-ACTIONS.md` (one plain-language item per line).
- Helper: `fleet/pending.sh add "<item>" | done <letter> | list`.
- Surfaced automatically at every session start by `preflight.sh` (display-only, never blocks) so it survives across sessions.

**How to apply:** Whenever you hand the operator anything (a decision, a push, a login, an optional action), `pending.sh add` it so it lands on the list; clear with `pending.sh done <letter>` when handled. Present the list and let the operator answer by letter at their pace. Do NOT re-ask an open item in prose — it's already on the list.

Why: the manager runs on Opus and moves fast; the operator is a solo dev reviewing serially and loses items in scrolling text. Related: [[work-in-phases-gather-then-wait]] [[discuss-before-acting-on-questions]] [[present-findings-in-color-tables]].
