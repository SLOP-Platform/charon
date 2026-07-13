---
description: Mechanize continuous contention-axis lane-planning + always-on concurrency + auto-close of satisfied tickets; never wait to be asked to optimize
metadata: 
name: continuous-work-optimization
node_type: memory
originSessionId: eaa0190c-d65a-4ac1-9b62-07c4aab515a1
type: feedback
tags: [optimization]
last_referenced: 2026-07-13
---
The operator should NOT have to ask the manager to optimize work into contention-axis lanes, nor discover after the fact that work could have run concurrently all along. Three standing mechanization requirements (2026-07-10):

1. **Continuous contention-axis optimization.** As tickets are added/removed, the rig re-computes the collision-free max-concurrency wave plan automatically (group by the file/resource each ticket OWNS — the contention axis) and keeps it current. This is NOT a manual, on-request pass. Extend `wci-contention.sh` into a full lane-planner.
2. **Always-on concurrency.** The maximal collision-free parallel set should ALWAYS be surfaced/running; the manager proactively fires disjoint lanes rather than working serial ticket-by-ticket. Don't make the operator notice the missed parallelism.
3. **Auto-close satisfied tickets.** A ticket whose work is already done (commits in master), redundant (duplicate of another), or not-relevant (superseded) must AUTO-CLOSE with a recorded reason — never linger as active/parked. (Origin: audit items #13-15 sat as "no work needed" instead of being closed.)

**How to apply:** proactively maximize concurrency every session (launch file-disjoint lanes in parallel by default); scope + build the lane-planner and auto-close into the rig, design-first (present before build). Related: [[charon-work-composition-intelligence]] [[wci-ticket-decompose-method]] [[optimize-execution-wallclock-tokens]] [[wci-rig-enforced-product-deferred]] [[charon-own-work-engine]].
