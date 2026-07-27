repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 0
branch: review/substrate-first-gate-v2
depends_on:
owns: fleet/handoff-notes/ADVREVIEW-SUBSTRATE-FIRST-GATE-V2.md
prompt: /home/stack/charon-private/prompts/REVIEW-SUBSTRATE-FIRST-GATE-V2.md
serial_justified: |
  ONE review producing ONE verdict file. Owns no code — the point is to decide whether 31 files of
  gate machinery should land, and which of two rival branches is canonical.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample. Read-only review.
source: |
  Landing sweep 2026-07-26 marked `feat/substrate-first-gate-v2` ABANDON. That verdict was WRONG —
  produced by a bad two-dot diff command in the sweep brief (manager error). The branch carries
  31 files / 1142 insertions of real unlanded work. Escalated to a review rather than a batch land.
note: |
  ## WHY THIS IS A REVIEW AND NOT A LANDING
  The other 18 sweep branches landed on triage evidence. This one is held back for three reasons:
  1. **31 files, ~30 under fleet/, plus .gitignore and .github** — the widest blast radius in the set.
  2. **It installs a GATE that fires at DECISION time** and claims to "close nine adversarial
     evasions". An unreviewed gate is how this fleet ended up with gates that do not gate
     (land-push allowing UNVERIFIED-BY-CI; done.sh closing on unrelated PRs; a detector that clears
     six dead modules). A gate landing unreviewed is the specific failure this fleet keeps repeating.
  3. **Its own commit says it "repairs the pre-existing B5 failure surfaced by the substrate gate"** —
     a change fixing something it caused. That is exactly where a reviewer earns their keep.

  ## THE RIVAL-BRANCH QUESTION (must be answered, not assumed)
  `feat/substrate-first-gate` (v1) STILL EXISTS alongside `-v2`. This is one of the duplicate pairs
  RIG-BRANCH-16-DEEPDIVE flagged, and the mechanism is known: `fleet/land.sh:151-161`'s
  EXISTING-BRANCH GUARD makes people cut a `-v2` rather than continue the original. So:
  which is canonical, what does v2 contain that v1 does not, and does landing v2 orphan real work
  sitting only in v1? Answer with diffs, not with the branch names.
accept: |
  DONE-CONTRACT:
  - A MERGE / BLOCK verdict with reasons, in the report file.
  - v1-vs-v2 settled with evidence: what v2 adds, what (if anything) exists ONLY in v1, and whether
    v1 can be safely retired after v2 lands.
  - The gate is EXERCISED, not just read: make it FIRE and make it FAIL. A gate that has never been
    seen to go RED is not verified.
  - The "nine adversarial evasions" claim is CHECKED — pick at least three and try to evade the gate.
    Report which evasions actually hold and which do not. Do not accept the count on its word.
  - The B5 "repair" is assessed: is it a genuine fix, or does it mask a regression the gate itself
    introduced? Name which.
  - Blast-radius statement: what breaks for a session that trips this gate, and can it be bypassed.
  - NON-VACUOUS: a review that never ran the gate is incomplete, not partial credit.
  - READ-ONLY: no edits, no commits to the branch under review, no landing.
## Dependencies & sequence
- **Depends on: NOTHING. Read-only; owns one report file. Cannot collide.**
- **Blocks:** landing `feat/substrate-first-gate-v2` and retiring `feat/substrate-first-gate`.
- **Wave:** review lane, P0.
