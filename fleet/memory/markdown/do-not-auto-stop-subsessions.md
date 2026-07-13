---
description: "When operator says stop/pause/wait, hold MY next move but never kill running sub-sessions unless they specifically ask"
metadata: 
name: do-not-auto-stop-subsessions
node_type: memory
originSessionId: 02f0da30-0dc8-45ce-acbc-4cded96858db
type: feedback
tags: [session, subsession]
last_referenced: 2026-07-13
---
FEEDBACK (2026-07-09): When the operator says "stop", "pause", "wait", or anything like that, do NOT TaskStop/kill running background sub-sessions. Only stop a sub-session when the operator SPECIFICALLY asks to stop that sub-session/task.

**Why:** "wait/pause/stop" means *hold your own next move / I have more input* — it is about MY cadence, not the background work. Sub-sessions are either read-only or reversible (backup + verify + rollback), so letting them finish costs nothing and killing them wastes work and momentum. (I killed the routing sub-session on a "wait" and it was the wrong call.)

**How to apply:** on stop/pause/wait → stop launching NEW moves, present, and WAIT for the operator; let all in-flight sub-sessions continue running. Reach for TaskStop ONLY on an explicit "stop the <X> sub-session / kill that task." Relates [[pause-after-question-or-action]], [[discuss-before-acting-on-questions]].
