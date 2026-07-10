# DeepSeek build session — implement SR-7 → SR-5b → SR-8 (STRICT ORDER, one at a time)

You are a Charon build session (DeepSeek V4 Pro). Repo: `/home/stack/code/charon`. Implement three
tickets **in this EXACT order: SR-7, then SR-5b, then SR-8** — one at a time, never in parallel.

**Why strictly sequential:** all three tickets own `src/charon/proxy_server.py`. Only ONE may edit
that file at a time. Finish and commit each before starting the next.

## 1. Ground yourself first (read these)
- `/home/stack/code/charon/AGENTS.md` — standing orders (mandatory)
- `/home/stack/charon-private/fleet/WORKFLOW.md` — claim / build / gate / commit process

## 2. The tickets — read the board + prompt for EACH before building it
1. **SR-7** — spend-cap hardening: record an ESTIMATED cost even when computed cost is 0, so a
   zero-priced/served response still advances the universal monthly cap (can't be bypassed).
   - board: `/home/stack/charon-private/fleet/board/SR-7.md`
   - prompt: `/home/stack/charon-private/prompts/sr-7.md`
   - branch: `feat/sr-7-spend-cap-hardening`
   - owns: `src/charon/spend_limits.py`, `src/charon/proxy_server.py`
2. **SR-5b** — the money-path multiply: compute `cost_usd` from stored per-token pricing when the
   provider reports none, and feed that SAME computed cost to the spend limiter's pre-flight estimate
   and `spend_limiter.record`.
   - board: `/home/stack/charon-private/fleet/board/SR-5b.md`
   - prompt: `/home/stack/charon-private/prompts/sr-5b.md`
   - branch: `feat/sr-5b-cost-usd-wire`
   - owns: `src/charon/proxy.py`, `src/charon/proxy_server.py`
3. **SR-8** — wire the 6 constructed-but-dead modules (DECISION CLEARED, operator-approved — no
   recommendation step; the prompt embeds all 6 approved decisions).
   - board: `/home/stack/charon-private/fleet/board/SR-8.md`
   - prompt: `/home/stack/charon-private/prompts/sr-8.md`
   - branch: `feat/sr-8-dead-module-decision`
   - owns: `src/charon/proxy_server.py`, `src/charon/consensus.py`,
     `src/charon/speculative_execution.py`, `src/charon/request_inspector.py`,
     `src/charon/session_affinity.py`, `src/charon/virtual_keys.py`, `src/charon/observability.py`

## 3. ⚠ CRITICAL — SR-7 and SR-5b touch the SAME spend-limiter call sites
- **Do SR-5b IMMEDIATELY after SR-7** (do not interleave anything else).
- SR-7 REMOVES the `cost>0` record guard (so zero-cost served calls still advance the cap). When you
  do SR-5b, **DO NOT reinstate that `cost>0` guard.** SR-5b feeds its computed `cost_usd` into the
  same pre-flight-estimate and `record` call sites SR-7 just hardened — build on top of SR-7's edit,
  do not revert it.
- SR-5b must read SR-5's canonical per-token price unit exactly (already merged in SR-5); the
  multiply is `tokens_in*cost_input + tokens_out*cost_output`. Distinguish "unknown/unpriced"
  (leave 0 + flag) from "priced at 0".

## 4. Branching — sequential stacked chain rooted at latest `master`
SR-1/2/3/5/10/11 are already MERGED to `master`. Start from the latest `master`:
```
git -C /home/stack/code/charon fetch origin
```
Because the three tickets share `proxy_server.py` and **nothing is pushed/merged between them**
(a Claude reviewer + the operator gate merges), each ticket must build on the previous one's
committed `proxy_server.py`. Stack the branches so the shared-file edits stay coherent:
- **SR-7:** branch `feat/sr-7-spend-cap-hardening` off latest `origin/master`.
- **SR-5b:** branch `feat/sr-5b-cost-usd-wire` off the **SR-7 branch** (so it sees SR-7's call-site
  edits — this is what makes the "don't reinstate the guard" rule work).
- **SR-8:** branch `feat/sr-8-dead-module-decision` off the **SR-5b branch**.

Use a separate git worktree per branch (see WORKFLOW.md). The chain's base is latest `master`.

## 5. Rules — non-negotiable
- Touch **ONLY** the files in the ticket's `owns:` line. Need a file outside `owns:`? **STOP and
  flag it** — do not create/edit it.
- Before committing EACH ticket, the FULL gate + tests must be green:
  ```
  python3 -m charon.cli gate && PYTHONPATH=src python3 -m pytest -q
  ```
  (Use `python3 -m charon.cli gate` — NOT bare `mypy src/charon`; the CLI gate runs
  ruff/mypy/boundary/version/gate-registry, and pytest is the separate test pass. `mypy src/charon`
  alone misses tests and reddens CI.)
- Commit each ticket with a conventional message (e.g. `feat(SR-7): …`, `feat(SR-5b): …`,
  `feat(SR-8): …`).
- **Do NOT push and do NOT open a PR.** Stop after committing — a Claude reviewer + the operator gate
  the merges.

When all three are committed, report the three branch names + each ticket's final `pytest` counts,
then stop.
