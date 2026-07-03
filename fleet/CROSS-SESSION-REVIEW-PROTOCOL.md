# Cross-Session Adversarial Review Protocol

**Date:** 2026-07-03
**Scope:** All charon sessions on the session-bridge
**Binding:** Yes — a nudge with the `REVIEW:` prefix triggers this protocol

---

## Purpose

When one session asks others to adversarially review its work (code change, design
decision, scope proposal), the receiving sessions MUST come to a conclusion. This
protocol mechanises the review, prevents deadlocks, and provides escalation paths
for both operator-driven and autonomous modes.

---

## Review Request Format

A session sends a structured nudge using the bridge's typed message system
(available after session-bridge v1.2 deployment; older sessions use the legacy
text format in the Bridge Compatibility appendix):

```
session-bridge_nudge(
  session_id="<requester>",
  target="<reviewer>",
  message_type="review-request",
  payload={"change_id": "<id>", "files": ["p1","p2"], "context": "<desc>",
           "reviewers": ["<session-a>", "<session-b>"]}
)
```

The `change-id` is a short, unique identifier for the thing being reviewed (e.g.,
`bridge-update-nudge-return`, `adopt-plan-repartition`). The `reviewers` field lists
every session being asked so each reviewer can see who else is on the panel.

---

## Reviewer Obligations

When a session receives a `REVIEW:` nudge (via `board()` or `update()`):

1. **Acknowledge within one heartbeat cycle (~3 min).** If the session is in a
   long subagent or test suite, it responds `REVIEW:BUSY` on its next heartbeat.
   A BUSY response defers review but does not block the requester — the requester
   counts BUSY as "not yet responded" and waits.

2. **Perform the review.** Read the changed files. Think adversarially: what edge
   cases fail? What race conditions exist? What security properties are violated?
   What invariants does this break? Review the *change*, not the *author*.

3. **Respond with a verdict.** Within 300 seconds (5 min) of receiving the request,
   send a structured nudge back to the requester with ONE of these verdicts:

```
session-bridge_nudge(
  session_id="<reviewer>",
  target="<requester>",
  message_type="review-verdict",
  payload={"change_id": "<id>", "verdict": "APPROVE|CONCERN|REJECT|BUSY",
           "finding": "<concrete finding or 'none'>"}
)
```

A REJECT MUST cite a concrete, reproducible issue. "I don't like the style" or
"this feels wrong" is not a valid REJECT. A CONCERN is advisory and non-blocking.

---

## Quorum & Decision Rules

### Two reviewers (default)

| Reviewer A | Reviewer B | Result |
|---|---|---|
| APPROVE | APPROVE | **APPROVED** — proceed |
| APPROVE | CONCERN | **APPROVED with notes** — proceed, log concerns |
| APPROVE | REJECT | **REJECTED** — fix the blocking finding |
| CONCERN | CONCERN | **APPROVED with notes** — proceed, log all concerns |
| CONCERN | REJECT | **REJECTED** — fix the blocking finding |
| REJECT | REJECT | **REJECTED** — fix both findings |
| Any | BUSY | Wait for response or timeout |
| Any | No response | See Timeout rules below |
| Any | SKIPPED | Treated as not voting; proceed with remaining reviewers. If zero reviewers remain, escalate (see Skip-after-N rule) |

### Three or more reviewers

Majority rules for APPROVE/CONCERN. But ANY single REJECT with a concrete finding
blocks — the author MUST address it. A 2-1 split with one REJECT is REJECTED.
SKIPPED reviewers are removed from quorum; their verdicts do not count. Calculate
majority from the remaining active panel.

---

## Timeout Rules

The default review timeout is 300 seconds (5 min) from receipt. This aligns with
the AGENTS.md heartbeat interval (~3 min): a session receives the nudge on its
next heartbeat, reviews within the remaining time, and responds.

| Condition | Action |
|---|---|
| Reviewer doesn't respond within 300s | Assume BUSY. The requester checks if the reviewer's PID is alive via `board()`. If alive and `expiring_soon`, wait one more cycle. If dead or still silent, count as `BUSY`. |
| ALL reviewers are BUSY or timed out | **Escalate.** If operator present (session exists with no ticket claimed, or the requester can ask), surface via `update(blockers=["review:<change-id> — all reviewers busy"])`. Operator assigns reviewers or approves directly. |
| Operator not reachable AND in autonomous mode | **Spawn judge panel.** See section below. |

### Skip-after-N Rule

A reviewer that returns to the same BUSY/timeout state across 3 consecutive review
cycles (900 seconds cumulative) is **SKIPPED**:

1. **Their vote is removed from quorum.** The review proceeds with the remaining
   reviewers. A SKIPPED reviewer's pending verdict (if any) is discarded.
2. **If this leaves zero reviewers,** escalate to operator or judge panel
   immediately — do not spawn another review cycle.
3. **The requester MUST record the skip** in the review log with the reason
   (e.g., "obi-wan-kenobi: SKIPPED — 3 consecutive BUSY/timeout cycles").
4. **A SKIPPED reviewer can rejoin** on the next review if they become responsive
   — skipping is per-review-cycle, not permanent.

---

## Deadlock Resolution — Judge Panel (Autonomous Mode)

When the review is deadlocked (all reviewers BUSY, or split with no operator present)
AND the session is operating in autonomous mode (work engine running, no interactive
operator):

1. **Spawn a judge panel.** Create a focused subagent ticket with:
   - `goal`: Review `<change-id>` and make a binding determination
   - `accept`: Produce APPROVE/REJECT verdict with concrete findings
   - `context`: The changed files, reviewer findings so far, and the original request
   - `tier`: `high` (judge panel needs strongest model)
   - `autonomy`: `L2` (cross-model review gate)

2. **The judge panel is narrow in scope.** It ONLY reviews the specific change-id.
   It does not propose alternatives. It does not expand scope. It answers: "Does
   this change contain a blocking defect?" and "If yes, what specifically?"

3. **The judge panel's determination is binding.** APPROVE overrides any CONCERN
   from earlier reviewers. REJECT creates a concrete finding the author MUST fix.

4. **After the judge panel:** the author fixes any findings (or accepts APPROVE)
   and proceeds. The judge panel's verdict is recorded in the change-id's review log.

---

## Operator Escalation Path

When the operator IS present and a deadlock occurs:

1. The requester calls `session-bridge_update(status="blocked", blockers=["review:<change-id> — deadlocked"])`
2. The requester nudges the operator session with `message_type="block-notification"`,
   `payload={"ticket": "review:<change-id>", "blocker": "deadlocked", "reason": "All reviewers busy/unresponsive"}`
3. The operator reviews the change, the findings, and makes a binding decision:
   - `REVIEW:<change-id>:OVERRIDE:APPROVE` — operator approves, overriding reviewer
   - `REVIEW:<change-id>:OVERRIDE:REJECT <finding>` — operator rejects with reason
4. The operator's override is recorded in the change-id's review log.

---

## Review Log

Every review cycle produces a record in `docs/review-log/<change-id>.md`:

```markdown
# Review: <change-id>
**Date:** <timestamp>
**Requester:** <session-id>
**Reviewers:** <session-a>, <session-b>
**Files:** <paths>
**Context:** <description>

## Verdicts
- <session-a>: APPROVE — no findings
- <session-b>: CONCERN — <finding>
- Judge panel: APPROVE (or) Operator override: APPROVE

## Resolution
APPROVED with notes (or REJECTED, fix applied at <commit-sha>)
```

---

## Example Flow

```
1. mace-windu changes server.py
2. mace-windu sends structured nudge to yoda and obi-wan:
   message_type="review-request"
   payload={change_id:"bridge-update-nudge-return", files:["server.py"],
            context:"update() returns nudges; check race condition",
            reviewers:["yoda","obi-wan-kenobi"]}

3. yoda sees nudge on next update(). Reviews server.py. Responds:
   message_type="review-verdict"
   payload={change_id:"bridge-update-nudge-return", verdict:"CONCERN",
            finding:"SELECT then UPDATE has race; use BEGIN IMMEDIATE"}

4. obi-wan sees nudge. Responds:
   message_type="review-verdict"
   payload={change_id:"bridge-update-nudge-return", verdict:"CONCERN",
            finding:"Same race concern. Also check board() handler."}

5. Verdict: 2 CONCERN = APPROVED with notes per Quorum rules.
   mace-windu fixes both concers, responds:
   message_type="review-verdict"
   payload={change_id:"bridge-update-nudge-return", verdict:"FIXED",
            finding:"Fixed. BEGIN IMMEDIATE in both update() and board()."}

6. Both acknowledge. Consensus reached. mace-windu proceeds.
```

---

## Hard Rules

| Rule | Detail |
|---|---|
| REJECT must be concrete | "This doesn't handle X when Y happens" — not "I don't like it" |
| Reviewers don't block indefinitely | BUSY or timeout → escalate, don't wait forever |
| Judge panel is narrow | Reviews the change ONLY, doesn't expand scope |
| Operator override is binding | Operator trumps all reviewer verdicts |
| Log everything | Every review cycle produces a review-log entry |

---

## Bridge Limitations

The opencode MCP tool stub layer may strip `nudge_messages` from `update()`
responses even though the raw JSON-RPC payload includes them. This is a known
limitation of the MCP adapter, not the bridge server itself.

| Limitation | Impact | Mitigation |
|---|---|---|
| `update()` responses may omit `nudge_messages` | Sessions that only call `update()` for heartbeats may miss nudge deliveries | **`board(repo="charon", session_id="<your-id>")` is the PRIMARY nudge delivery mechanism.** Every `board()` call with a `session_id` refreshes liveness AND returns pending `nudge_messages`. |
| `update()` in raw RPC DOES include nudges | Direct RPC consumers (e.g., proxy.py, daemon.py) receive nudges via `update()` | Sessions using the opencode MCP client should prefer `board()` for nudge delivery. Direct RPC consumers may use either. |

**Guidance:** Sessions should call `board(repo="charon", session_id="<your-id>")`
for nudge delivery and liveness refresh rather than relying on `update()` alone.
`update()` remains valid for heartbeat-only calls and status changes, but nudge
consumption should always go through `board()`.
