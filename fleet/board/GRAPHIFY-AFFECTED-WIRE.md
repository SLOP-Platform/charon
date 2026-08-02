repo: charon-private
tier: economy
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/graphify-affected-wire
depends_on:
owns: fleet/checks/blast-radius.sh, fleet/reuse-check.sh, fleet/tests/blast-radius.test.sh, fleet/TOOL-INVENTORY.md
serial_justified: |
  A query wrapper and its call site are ONE unit, because the entire defect being fixed is that
  a capability exists with no caller. Shipping `blast-radius.sh` without wiring it reproduces
  the bug in a new file — one more thing that can be run and never is. The TOOL-INVENTORY row is
  part of the same unit for the same reason: the inventory is how the next session FINDS the
  command, and a tool absent from it is discoverable only by accident.
substrate: N/A
substrate-novel: |
  NO NEW TOOL IS ADOPTED. graphify is already installed (`~/.local/bin/graphify`, via
  `uv tool install graphifyy`), already documented in `fleet/TOOL-INVENTORY.md` section 1,
  already producing `graphify-out/graph.json`, and its freshness is already MECHANISED —
  `fleet/checks/graphify-freshness.sh` runs on EVERY preflight (wired at fleet/preflight.sh:859).
  We pay to build and continuously refresh a code graph and then never ask it anything.
  Alternatives were considered and rejected on the same ground each time: they would ADD a
  substrate to answer a question our existing substrate already answers. A new graph/DB layer
  (KuzuDB, DuckDB) is REJECTED in `fleet/state/EVAL-REGISTRY.md` (lines 71-72) for precisely
  this shape — storage is the easy part and swapping it changes nothing about the query. An
  LLM-driven knowledge graph (Cognee, line 68) is REJECTED as the wrong shape for what is a data
  lookup, not a reasoning problem. And the aligned COMPOSE-WHAT-WE-RUN row (line 67) already
  records the standing verdict for this exact area: compose the tools we already run, add only a
  thin shim, adopt nothing new. That row also independently measured the symptom this ticket
  fixes — that `registry-discovery.sh` is graphify's ONLY consumer.
  THE NOVEL SLICE is small and specific: a wrapper that turns a changed-file list into a
  blast-radius answer using the graph we already maintain, and a CALL SITE that makes it fire
  without anyone remembering to run it. Roughly a hundred lines of bash over an existing binary
  and an existing artifact. Nothing is hand-rolled that a tool provides.
source: |
  fleet/state/PRIORITY-TODO.md section A, row A5: "graphify affected (blast-radius) — graph built
  by 114 `update` sites, query has 0 invocations". Re-verified live 2026-08-01 in the rig
  checkout: `grep -rn "graphify path\|graphify explain" --include=*.sh --include=*.py .` returns
  **0**, while `graphify update` appears 21 times in rig scripts and docs. The graph is built,
  refreshed, gated on for staleness — and never queried.
note: |
  ## THE FINDING — WE MAINTAIN AN ANSWER NOBODY ASKS

  `graphify update` is invoked from 114 sites across the tracked repos (PRIORITY-TODO A5; 21 of
  them in the rig checkout alone, re-counted 2026-08-01). There is a dedicated freshness gate,
  `fleet/checks/graphify-freshness.sh`, wired into `fleet/preflight.sh:859` so that a stale map
  is a preflight RED. We have institutionalised KEEPING THE GRAPH FRESH.

  The blast-radius query — `graphify path "A" "B"` (shortest path between two nodes) and
  `graphify explain "X"` (a node and its neighbours), which `fleet/TOOL-INVENTORY.md:26`
  explicitly names as the way to answer "how does A reach B / blast-radius questions" — has
  **zero** invocations in any script in the rig. Not few. Zero.

  This is independently corroborated by the aligned COMPOSE-WHAT-WE-RUN row in
  `fleet/state/EVAL-REGISTRY.md` (line 67), which measured that `registry-discovery.sh` is
  graphify's only consumer.

  So the standing blast-radius lens is applied by HAND, from memory, differently by every
  session, over a graph that is already sitting there current. That is the defect. It is the
  same shape as the shellcheck one in the sibling ticket: an adopted capability running at a
  fraction of its coverage because of a default nobody chose.

  ## WHY THE CALL SITE IS `fleet/reuse-check.sh` AND NOT `fleet/preflight.sh`

  State this plainly because it is a deliberate deviation worth defending.

  `fleet/preflight.sh` is the obvious-looking home and it is the WRONG one here. EIGHT live
  tickets already declare it in `owns:` (`PREFLIGHT-GATE-REGISTRY`, `PREFLIGHT-GATE-RUN-HELPER`,
  `MARKER-PROOF-MECHANIZE`, `RECONCILE-WIRING`, `REPO-MAP-CONVERGE`, `SYNC-SCHEDULE`,
  `GATE-INTEGRITY-C`, `WCI-DEC-FLEET-PREFLIGHT-SH`), and `PREFLIGHT-GATE-REGISTRY` exists
  specifically to END that contention by turning "add a gate" into "add a row to a table"
  instead of "edit a shared file". Claiming preflight.sh here would mean eight merge-order edges,
  which would leave this ticket unclaimable for as long as that queue takes to drain — the exact
  opposite of what it is for.

  `fleet/reuse-check.sh` is the better fit ON THE MERITS, not merely as an escape hatch. It is
  the rig's designated "before you write a new file/module" checkpoint. `TOOL-INVENTORY.md:14`
  ALREADY pairs the two ideas in its own trigger table: "About to propose/create new work →
  `graphify explain "X"` + grep board/*.md for owns: (reuse-check)". The inventory says these
  belong together; nothing joins them. Reuse-check answers "does this already exist?"; the
  blast-radius query answers "what does touching it affect?" Those are two halves of one
  question and they are asked at the same instant. reuse-check.sh has ZERO live owners
  (verified 2026-08-01), so this wiring is collision-free and claimable today.

  After `PREFLIGHT-GATE-REGISTRY` lands, adding a preflight row for the same check is a one-line
  follow-up. That is a strictly better sequence than blocking on it now.

  ## SCOPE

  1. `fleet/checks/blast-radius.sh` — a wrapper over the ALREADY-BUILT graph. Given a changed
     file or symbol (and defaulting to the current diff's changed files), report what depends on
     it: the neighbourhood from `graphify explain`, and reachability via `graphify path` where a
     target is named. Read-only. Never mutates the graph and never calls `graphify update` —
     freshness is `graphify-freshness.sh`'s job and duplicating it would fork the contract.
  2. FAIL SOFT, LOUD. A missing graph, a missing binary, or a node the graph does not know must
     print WHY and exit in a way that does not wedge `reuse-check.sh`. A blast-radius advisory
     that hard-fails a session's first command gets deleted within a day. Silence is equally
     bad: "no answer" and "no impact" must be distinguishable in the output.
  3. Wire it into `fleet/reuse-check.sh` so it runs as part of the reuse check. Preserve
     reuse-check.sh's existing contract EXACTLY — same argv order (`[repo-root] <candidate>
     [threshold]`), same exit semantics from `ksf reuse-check`. The blast-radius output is
     ADDITIVE. Provide an env opt-out for the hermetic case.
  4. Add the TOOL-INVENTORY row: the exact command, and a trigger-table entry so the next
     session reaches it by the mechanism-selection ladder rather than by recall.
  5. Do NOT touch `fleet/preflight.sh`, `fleet/checks/graphify-freshness.sh`, or
     `fleet/checks/registry-discovery.sh`.

  ## BURN DOWN OR BASELINE — NEITHER APPLIES, AND HERE IS WHY

  Stated explicitly because every other ticket in this batch has a burn-down and a reviewer will
  look for one. This enablement surfaces no findings to fix. Turning on a QUERY produces
  information at the moment of use; it does not produce a backlog. There is no baseline, and
  there must not be one — a baseline here could only mean an allowlist of "files we agree not to
  compute blast radius for", which would be a mechanism for making the tool quiet rather than
  useful. PRIORITY-TODO section D4's warning (a baseline generated before known defects are
  fixed freezes the bugs in permanently) is the reason to name this now: the temptation, when
  the first real blast-radius report is inconveniently large, will be to suppress it. Do not add
  a suppression surface to this tool.

  ## DONE CONTRACT — RED THEN GREEN, EXTERNALLY RED-PROOFED

  Hermetic: build a throwaway fixture graph JSON with known nodes and edges and point the check
  at it (graphify's own `--graph <path>` flag supports this). No network, no dependency on the
  live 5.5MB product graph, no LLM.

  a. `fleet/checks/blast-radius.sh` exists, is executable, and answers a blast-radius query
     against a fixture graph with a KNOWN dependency structure — a node with two dependents
     reports exactly those two, by name.
  b. THE CALL-SITE ASSERTION, and it is the one that matters: running `fleet/reuse-check.sh`
     must ACTUALLY INVOKE the blast-radius query. Assert the observable effect (the report in
     the output), not the presence of a line of source. The whole defect being fixed is a
     capability with zero callers; a test that only proves the file exists would leave the bug
     exactly where it was, in a new location.
  c. FAIL-ON-REVERT, three independent reverts, three REDs:
     - remove the wiring from `reuse-check.sh` → the call-site assertion goes RED;
     - break the query in `blast-radius.sh` → the correctness assertion goes RED;
     - remove the TOOL-INVENTORY row → the discoverability assertion goes RED.
  d. NEGATIVE CASE: a node with no dependents reports "no dependents" and is DISTINGUISHABLE in
     the output from "graph missing" and from "node not found". Three distinct outcomes, three
     distinct messages. A tool that says nothing when it knows nothing is how a wired check
     silently becomes inert again.
  e. reuse-check.sh's PRE-EXISTING behaviour is unchanged: same argv contract, and the
     `ksf reuse-check` exit code still governs. Assert this — a wrapper that swallows its
     wrappee's exit code is a gate-weakening change.
  f. The opt-out env var suppresses the blast-radius section and nothing else.
  g. `bash fleet/gate.sh` is GREEN (the new test is auto-discovered from `fleet/tests/*.test.sh`
     — see gate.sh:31-36; no gate.sh edit is needed or permitted here).
  h. Report BOTH counts — green intact, RED on each of the three reverts.

## Dependencies & Sequence

- **depends_on: (none). IMMEDIATELY ELIGIBLE — claimable the moment it lands on the board.**
  Deliberate. The economy tier has been starving with zero eligible work; this ticket and
  `SHELLCHECK-OPTIONAL-CHECKS-ON` are the two in this batch with no inbound edges, so two idle
  lanes can start at once.
- **owns-collision: NONE, verified against the live board 2026-08-01 by grepping `^owns:` across
  all live `fleet/board/*.md`.**
  - `fleet/checks/blast-radius.sh` — does not exist yet; zero owners.
  - `fleet/reuse-check.sh` — exists; **zero** live owners.
  - `fleet/tests/blast-radius.test.sh` — new path; zero owners.
  - `fleet/TOOL-INVENTORY.md` — **zero** live `owns:` declarations. Two live tickets
    (`KILL-PATH-WORK-GUARD`, `OWN-TOOLS-CAPABILITY-AUDIT`) mention it in PROSE only, which is not
    ownership. Keep the edit to a single additive row to stay conflict-free if either later
    claims it.
- **Explicitly NOT owning `fleet/preflight.sh`** — eight live co-owners; full reasoning in the
  note. This is the single deliberate deviation from the original scoping and it is what keeps
  the ticket claimable today.
- **No shared path with `SHELLCHECK-OPTIONAL-CHECKS-ON`.** That ticket owns `fleet/gate.sh`;
  this one owns none of it (the new test is auto-discovered, requiring no gate.sh edit). The two
  run FULLY CONCURRENTLY — which is the point, since they are the two unblocked units.
- **No shared path with the product chain.** `RUFF-PREVIEW-ON` → `RUFF-ARG-C90-ON` →
  `MYPY-STRICTNESS-3-FLAGS` are all `repo: charon` on `pyproject.toml`. Zero overlap.
- **Sequence: NOW.** It is the last uncovered row of PRIORITY-TODO section A and the only one
  whose payoff compounds — every later session gets a mechanised blast-radius answer instead of
  a hand-applied lens.
- **Blocks / unblocks:** blocks nothing. Unblocks a one-line preflight registration once
  `PREFLIGHT-GATE-REGISTRY` lands, at which point the same check gains a second call site with
  no contention.
- **Related, do NOT fold in:** `PREFLIGHT-GATE-REGISTRY` (the preflight wiring follow-up),
  `graphify-freshness.sh` (freshness is already solved and must not be duplicated here), and the
  COMPOSE-WHAT-WE-RUN ownership-index shim from EVAL-REGISTRY line 67 (the owns:-to-graph join
  is a larger, separate piece of work; this ticket does the graph-side query only).
