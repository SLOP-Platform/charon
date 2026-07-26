# SESSION — SW-IDENTITY-FOLD follow-up: aistudio preview alias + drop the no-op regex

**Model:** a NON-ANTHROPIC model through the Charon gateway (`opencode --model charon/<model>`).
Never Claude/Anthropic. Graded sample, work_class `bugfix`.
**Repo:** charon (PUBLIC) · **Ticket:** SW-IDENTITY-FOLD (follow-up review findings)
**Branch:** `fix/sw-identity-fold` — CONTINUE the existing branch, do not cut a new one.
**Worktree:** `/home/stack/charon-wt/SW-IDENTITY-FOLD` — already exists at commit `46eab38`.
The previous session (qui-gon-jinn) finished and released it. One checkout, one agent.

## FIRST ACTS
0. **Register on the session-bridge** — `session-bridge_register(session_id="<an UNUSED Jedi name;
   kit-fisto, qui-gon-jinn and mace-windu are taken>", name="SW-IDENTITY-FOLD followup",
   repo="charon", ticket="SW-IDENTITY-FOLD", status="in-progress", model="<your model>")`.
   **Then `session-bridge_update` every ~5 minutes as a HEARTBEAT** — the lease is 600s and a session
   that stops heartbeating is purged and becomes invisible to the manager.
1. `cd /home/stack/charon-wt/SW-IDENTITY-FOLD` (already on `fix/sw-identity-fold` at 46eab38)
2. `git log --oneline -1` — confirm you are on 46eab38 before changing anything.

## CONTEXT — the prior work was GOOD; these are two review findings, not a rework
The anchor commit is accepted: fp4 + quant families folded, corpus test with 38 entries, red-proof
executed (exit 1 -> 0). Do NOT redo it. Two findings from manager review:

### FINDING 1 (the important one) — a funded frontier leg is still stranded
`google-aistudio` is configured with a LIVE key and advertises these ids:
```
models/gemini-3-pro-preview     models/gemini-3-flash-preview
models/gemini-3.1-flash-image   models/gemini-3-pro-image-preview
```
The routable pool ids are `gemini-3-pro` / `gemini-3-flash`. Because `-preview` is (correctly) NOT
folded, those aistudio ids never join those pools — so a funded, already-keyed **Gemini-3 frontier
leg is unreachable**. That is the INV-SW2 "never falsely exhausted" stranding this ticket exists to
eliminate (ADR-0011, Accepted).

**The operator's decision (binding): add an explicit ALIAS, do NOT blanket-fold `-preview`.**
Blanket-folding would merge GA and preview identities and silently route a GA request to a preview
model — worse than the stranding. Keep the `-preview` non-fold disposition exactly as it is.

Implement a narrow, explicit alias so the aistudio preview ids resolve into the corresponding base
pool. Requirements:
- EXPLICIT and enumerable — a small named mapping a human can read and audit, not a new regex family.
- Do NOT add a second normalizer. Extend the one identity path (`_normalize_model_id` and its
  callers); `routing_policy/catalog_refresh.py` imports it deliberately (anti-accretion).
- Alias only what you can justify. `gemini-3-pro-preview -> gemini-3-pro` is defensible (it is the
  only way to reach Gemini-3 Pro on that endpoint). `gemini-3-pro-image-preview` is an IMAGE model —
  do NOT alias it into a text pool. State your reasoning per alias.
- If you conclude an alias is the wrong mechanism and something else is genuinely better, STOP and
  report your reasoning instead of building it. Do not silently substitute a different design.

### FINDING 2 (small) — dead regex in the identity hot path
`src/charon/proxy.py:277`:
```python
_MARKETING_SUFFIX = re.compile(r"(?!x)x")  # no-op: see rationale above
```
A regex that can never match, whose `.sub()` still executes on every normalization inside the fold
loop. Remove the pattern and the `.sub()` call; KEEP the rationale as a plain comment so the
disposition (why `-turbo`/`-instruct`/`-preview`/`-latest`/`-hf` are NOT folded) stays recorded.
Deleting the comment loses the decision; keeping the regex keeps dead code. Do both correctly.

## REQUIRED PROOF (green is not proof)
- Extend `tests/test_model_identity_fold.py`: each new alias in the corpus with its expected result,
  AND a negative case proving `gemini-3-pro-image-preview` does NOT land in the text pool.
- **RED-PROOF BY EXECUTION** for the alias: remove the alias -> the test goes RED naming the stranded
  aistudio id. **Report BOTH exit codes.**
- Prove Finding 2 changed no behaviour: the full corpus test passes identically before and after
  removing the no-op. Report both runs.
- NON-VACUOUS: the corpus must still fail on an empty table.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- State what you proved by RUNNING vs by READING, and which git ref you measured on.

## GATE (both, from the worktree)
- `PYTHONPATH=src python3 -m charon.cli gate`
- `PYTHONPATH=src python3 -m pytest -q`

## BOUNDARY
Product is PUBLIC: no `/home/stack` paths, no internal IPs or hostnames, no fleet/rig/SLOP
references, no secrets in `src/` or committed config. Provider NAMES are fine; internal host
addresses are not.

## OWNS — do not touch anything else
`src/charon/proxy.py`, `tests/test_model_identity_fold.py`. If the fix appears to need another file,
STOP and report — every other routing file is owned by another live ticket.

## REPORT BACK (short — no diffs)
Aliases added + the justification for each · confirmation the `-preview` non-fold disposition is
UNCHANGED · both exit codes from the alias red-proof · before/after corpus runs for Finding 2 · gate
pass/fail · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "SW-IDENTITY-FOLD: alias aistudio gemini preview ids into their base pools; drop no-op marketing regex"
```

Do NOT push.

## Dependencies & sequence

- **Depends on:** the existing `46eab38` on this same branch — continue it, do not rebase or rewrite.
- **Concurrency safety:** owns `proxy.py` + its test, same as the parent ticket. No other live ticket
  owns them. SW-STATIC-LEGS-RETIRE and SW-P2-* own different files and may run concurrently.
- **Blocks:** SW-STATIC-LEGS-RETIRE keys on this identity function — land this before it starts, for
  the same reason the anchor came first.
- **Wave:** wave 0 (anchor completion), P0.
