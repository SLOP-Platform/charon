# SESSION — ADVERSARIAL REVIEW: feat/substrate-first-gate-v2 (P0, 31 files)

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `design-review`.
**You are the REVIEWER. READ-ONLY.** Do not edit, commit, land, or delete anything.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="REVIEW SUBSTRATE-FIRST-GATE-V2",
   repo="charon", ticket="REVIEW-SUBSTRATE-FIRST-GATE-V2", status="in-progress", model="<your model>")`.
   If the lease expires, do NOT renew — **re-register**.
1. Read the ticket (BINDING): `fleet/board/REVIEW-SUBSTRATE-FIRST-GATE-V2.md`
2. Work read-only against `/home/stack/charon-private` with `git -C`. Create no worktree.

## ⚠ USE THE RIGHT DIFF — the sweep that judged this branch used the WRONG one
`git diff origin/master..<branch>` (two-dot) renders master's later additions as if the BRANCH
deleted them. That is how this branch was wrongly marked ABANDON. Use:
- what the branch changes: `git diff --stat master...feat/substrate-first-gate-v2` (**THREE** dots)
- already on master?: `P=$(git diff --name-only master...<b>); git diff --stat master <b> -- $P`
  (empty ⇒ already landed; commit-count NEVER proves this — squash-merged branches look unlanded forever)

## WHAT YOU ARE JUDGING
Three commits, 31 files (~30 under `fleet/`, plus `.gitignore` and `.github`):
```
981c287 feat(rig): substrate-first gate — fire build-vs-adopt at DECISION time, not session start
5e9de6c feat(substrate-gate): v2 — replace the hand-rolled parser, close nine adversarial evasions
c182d7e fix(land-push-ci-gate): repair the pre-existing B5 failure surfaced by the substrate gate
```

## ATTACK THESE — in priority order
1. **MAKE THE GATE FIRE, AND MAKE IT FAIL.** A gate nobody has watched go RED is unverified. Run it
   against a case it should PASS and a case it should BLOCK. Paste both outcomes and exit codes.
   This fleet has repeatedly shipped gates that do not gate: `land-push` allowed a push
   UNVERIFIED-BY-CI, `done.sh` closed a ticket citing an unrelated PR, and `check_inert_code.py`
   cleared six provably-dead modules. Assume the same failure until you have seen RED.
2. **"Closes nine adversarial evasions" — CHECK IT.** Pick at least THREE and actively try to evade
   the gate. Report which evasions genuinely hold and which do not. Do not accept the count on trust;
   an uncheckable claim in a commit message is not evidence.
3. **The B5 "repair".** `c182d7e` fixes a failure "surfaced by" this gate. Is that a genuine
   pre-existing bug the gate exposed, or is the gate itself causing it and the commit masking it?
   Name which, with evidence. A gate that requires disabling a check to pass is not a gate.
4. **v1 vs v2 — SETTLE IT.** `feat/substrate-first-gate` (v1) still exists. What does v2 add? Does
   anything exist ONLY in v1? Can v1 be retired safely once v2 lands? This pair is a known instance
   of the `land.sh:151-161` EXISTING-BRANCH-GUARD sprawl mechanism — answer with diffs, not names.
5. **BLAST RADIUS.** It fires at DECISION time, so it can block ordinary work. What exactly breaks
   for a session that trips it? Is there a bypass, and if so is the bypass loud or silent? A silent
   bypass makes the gate decorative.
6. **`.github` change** — what does it alter in CI, and could it weaken an existing check?

## RULES
- Default to REFUTING. Every finding: `file:line` + concrete failure scenario + severity
  (BLOCKING / SHOULD-FIX / NIT).
- READ-ONLY: no edits, no commits, no landing, no branch deletion.
- A zero-hit grep is NOT evidence — read the code.
- FAIL-LOUD in your own verification: no `| tail`, `| head`, `|| true`; `set -o pipefail`.
- Say what you proved by RUNNING vs by READING. If it is sound, say so plainly — do NOT invent
  findings. But a review that never executed the gate is INCOMPLETE, not clean.

## ANSWER EXPLICITLY
**"Is feat/substrate-first-gate-v2 safe to land, and is feat/substrate-first-gate safe to retire?"**
MERGE/BLOCK plus RETIRE-V1/KEEP-V1. Those two lines are what the operator acts on.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-SUBSTRATE-FIRST-GATE-V2.md`.
Then emit the SESSION REPORT v1 block (spec: `fleet/SESSION-REPORT-FORMAT.md`; validate with
`bash fleet/check-session-report.sh <file>`).

## Dependencies & sequence
- **Depends on: NOTHING.** Read-only; owns one report file. Cannot collide with any live work.
- **Blocks:** landing v2 and retiring v1.
- **Wave:** review lane, P0.
