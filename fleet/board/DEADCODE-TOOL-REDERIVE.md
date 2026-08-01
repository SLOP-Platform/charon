repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 1
branch: eval/deadcode-tool-rederive
depends_on:
owns: fleet/state/DEADCODE-TOOL-REDERIVE.md
serial_justified: |
  ONE comparative evaluation across one tool family. Splitting per-tool would lose the whole point
  — the deliverable is the COVERAGE MATRIX showing which tool catches which class, which only
  exists when they are measured against the same corpus in the same run.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. This is an EVAL lane: measure and report.
  Do NOT wire anything into CI as part of this ticket.
source: |
  Operator, 2026-07-31: "I thought we adopted Vulture ... We should be taking advantage of
  Vulture, Deadcode, Pylint?" then: "was it tested (and others) TOO narrowly? against full
  features/capabilities? can it help in OTHER cases?"
note: |
  ## WHY THIS IS A RE-DERIVE, NOT A REPEAT
  `fleet/state/VULTURE-EVAL.md` (2026-07-22) is REAL, tested work — it ran vulture 2.16 against
  the product tree AND a purpose-built fixture. Its finding is reproducible and STANDS:
    - vulture is a REFERENCE-COUNTING detector; our hand-roll is REACHABILITY-FROM-ENTRYPOINT.
    - A mutually-referencing island (A->B, B->A, neither reachable from an entrypoint) is MISSED
      by vulture (0 findings, rc 0) and FLAGGED by the hand-roll.
  **Do not re-litigate that. vulture cannot REPLACE the reachability gate. Settled.**

  ## WHAT WAS TOO NARROW (this is the actual ticket)
  The eval asked ONE question — "can vulture REPLACE check_inert_code.py in the product tree?" —
  and answered it. It never asked the question that matters for adoption:
  **what does vulture (or deadcode, or pylint) catch that we currently catch NOTHING of?**
  Under the corrected lens (MANAGER-OPERATING-RULES §11): "'What of ours does this delete?' is
  BLIND TO GAPS. A tool filling something we LACK scores zero." The REJECT rests on exactly that
  blind spot, plus a dependency-cost objection ("for a new pip dep") — also invalid, since size
  and dep count are not rejection criteria when WE do not maintain the tool.

  NEVER TESTED — each is in scope here:
    1. **The RIG's own Python.** The eval scanned the product tree only. `fleet/capability/` is
       3,295 LOC (measured 2026-07-31); plus `fleet/checks/*.py`. Zero dead-code tooling has ever
       run on it.
    2. **Keystone** (`/home/stack/code/keystone`) — never scanned by anything.
    3. **Capability classes vulture ships that were never exercised:** unreachable code after
       return/raise, unused classes / methods / properties, unused attributes, and
       `--make-whitelist` ratcheting (the designed way to use it — the "156 noisy findings"
       complaint measured DEFAULT confidence with no whitelist, a configuration nobody would run).
    4. **`deadcode` and `pylint`: NEVER EVALUATED AT ALL.** No EVAL-REGISTRY row exists for either.
       pylint's dead-code checks overlap ruff; the question is what it adds beyond ruff, not
       whether it duplicates it.

  ## THE MEASUREMENT THAT DECIDES IT (do this, not a doc review)
  Build a COVERAGE MATRIX from a REAL run over a REAL corpus — product tree, rig Python, Keystone:

  | class | check_inert_code.py | ruff | vulture | deadcode | pylint |
  |---|---|---|---|---|---|
  | unreachable-from-entrypoint public symbol | ? | ? | ? | ? | ? |
  | mutually-referencing dead island | ? | ? | ? | ? | ? |
  | unreachable code after return/raise | ? | ? | ? | ? | ? |
  | unused class / method / property | ? | ? | ? | ? | ? |
  | unused attribute | ? | ? | ? | ? | ? |
  | unused import / local | ? | ? | ? | ? | ? |

  Fill every cell by EXECUTION, never by reading docs. The deliverable is the matrix plus the
  answer to ONE question: **is there any row where every tool we currently run says nothing and
  a candidate says something?** If yes, that row is a GAP and the candidate is an ADOPT for that
  row — regardless of it being unable to replace anything.

  ## GROUNDING — REAL CASES TO TEST AGAINST (from 2026-07-31)
  Run the candidates against these and record which, if any, would have surfaced them:
    - **Faktory**: server up 7 days on 4-LOM, `fleet/lease-enqueue.sh` self-describes as "the ONLY
      sanctioned path that starts work", ZERO workers, and `claim.sh` never calls it. (Note: this
      is BASH, so a Python tool cannot catch it — say so plainly if that is the finding. Determining
      that our dead-code coverage is Python-only while half the rig is bash IS a valid, valuable
      result.)
    - **REVIEWER-TAB-POOL B1**: a guard comparing disjoint namespaces — structurally unable to fire.
    - The 20 live `gate-integrity.sh` findings (G1 INERT / G3 UNPROVEN / G4 DOCUMENTED-GAP).

  ## HARD RULES
  - Verdicts land in `fleet/state/EVAL-REGISTRY.md` as rows, long-form in
    `fleet/state/DEADCODE-TOOL-REDERIVE.md`. A verdict not in the registry gets paid for twice.
  - **Size / dep-count / "ruff already does some of it" are NOT rejection criteria.**
  - An honest "no gap found, keep what we have" IS a valid and welcome result. Do not manufacture
    a reason to adopt. But it must be backed by the executed matrix, not by citing the 2026-07-22
    verdict.
  - Do NOT wire anything into CI here. Recommend; a separate ticket wires.

D&S — Deps & Sequence:
  - Depends on: nothing. Pure measurement, no shared surfaces, collision-free.
  - Feeds: KS31 (component-tool-adapters) and KS13 (lens-security) if a gap is found.
