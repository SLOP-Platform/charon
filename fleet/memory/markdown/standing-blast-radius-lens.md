---
description: Manager sessions (Charon AND SLOP) ALWAYS apply a blast-radius + outside-the-box lens and auto-spawn a read-only review on defined triggers — never wait to be asked
metadata: 
name: standing-blast-radius-lens
node_type: memory
originSessionId: ebcf9a1e-605b-4f25-ae5c-e6f7580be989
type: feedback
tags: [blast-radius, standing-rule]
last_referenced: 2026-07-13
---
Every MANAGER session (Charon and SLOP) applies a **standing blast-radius + think-outside-the-box
lens by default** — the operator should NOT have to remember to ask for it. Don't just evaluate
the change in front of you; ask what ELSE it touches and what you're not seeing.

**AUTO-TRIGGER** — apply the lens and **auto-spawn a read-only blast-radius review** (a sub-session,
per [[manager-delegates-to-subsessions]]) BEFORE committing / merging / settling, when a change:
- touches shared infra, the gate/CI, security, or the push / deny-list / settings paths;
- adds or changes a dependency — **especially one that could leak the local build-rig / SLOP /
  self-hosted runner into the standalone product** (Charon must run with none of the home infra);
- "fixes" something by **TIGHTENING a rule** — could it silently break a workflow that relied on
  the old/looser behavior? (2026-06-27 lesson: closing the `git -C` deny gap broke droid pushes);
- settles a decision or introduces a new pattern;
- is non-trivial or hard to reverse.

The review asks: **What else depends on this? What's the second-order / downstream effect? What
relied on the thing we just changed? What are we NOT seeing?** Surface findings BEFORE proceeding.

**Why:** the operator fears missing things when they don't think to ask for this viewpoint — and
this session, asking for "blast radius" caught a manager-CAUSED critical bug. Make it the default,
not an on-request lens. Pairs with the auto-adversarial-review doctrine and [[manager-never-spawns-droids]]
(this is a read-only review sub-session, allowed; not a build-droid).
