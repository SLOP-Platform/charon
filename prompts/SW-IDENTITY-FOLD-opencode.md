# SESSION — SW-IDENTITY-FOLD: canonical model-identity folding (Switchboard anchor)

**Model:** a NON-ANTHROPIC model served through the Charon gateway (`opencode --model charon/<model>`).
Never Claude/Anthropic. This run is a GRADED sample — it will be scored into the model scorecard
under work_class `bugfix`.
**Repo:** charon (PUBLIC) · **Ticket:** SW-IDENTITY-FOLD · **Branch:** `fix/sw-identity-fold`
**Worktree:** `/home/stack/charon-wt/SW-IDENTITY-FOLD` — an ISOLATED worktree.
**Do NOT work in `/home/stack/code/charon`.** The manager session holds that checkout.
One checkout, one agent.

## FIRST ACTS
1. `git -C /home/stack/code/charon fetch origin`
2. `git -C /home/stack/code/charon worktree add -b fix/sw-identity-fold /home/stack/charon-wt/SW-IDENTITY-FOLD origin/master`
3. `cd /home/stack/charon-wt/SW-IDENTITY-FOLD`
4. Read the ticket: `/home/stack/charon-private/fleet/board/SW-IDENTITY-FOLD.md` — it is binding.
5. Read `docs/adr/0011-the-switchboard-demand-routed-no-pools.md` (Accepted) for INV-SW1/2/3.

## THE TASK (facts pre-verified — do NOT re-derive)
`src/charon/proxy.py:265-266` — `_QUANT_SUFFIX` omits `fp4`. Together's
`MiniMaxAI/MiniMax-M2.5-FP4` therefore normalizes to `minimax-m2.5-fp4`, forming an ORPHAN pool
instead of folding into `minimax-m2.5`, stranding a funded, unparked provider. Under ADR-0011 that
is an **INV-SW2 (never falsely exhausted) violation — release-blocking**.

`_normalize_model_id` (`src/charon/proxy.py:269`) is the SINGLE cross-provider identity function in
the tree: `src/charon/routing_policy/catalog_refresh.py:61-68` imports it rather than defining its
own. Fixing it fixes pool folding everywhere. Do not add a second normalizer (anti-accretion).

## REQUIRED CHANGE — the CLASS, not the instance
The one-token `fp4` patch must ship INSIDE the class fix, never as a standalone patch. Audit and
DISPOSITION every variant-spelling family that can split one model into two pool ids, using the live
catalog as the corpus:
- quantization: `fp4` (known miss) plus any other family the live catalog advertises (nvfp4, mxfp4,
  awq, gptq, w8a8, stacked `q8_0` forms)
- serving/marketing suffixes: `-turbo`, `-fast`, `-instruct`, `-latest`, `-preview`, `-hf`
- mode selectors (COLON tail, not hyphen): `:thinking`, `:reasoning`, `:free`, `:nitro`, `:online`
- CASE: the compare already lower-cases — PROVE it, do not assume
- vendor path prefixes: `openai/gpt-4o` vs bare `gpt-4o` — the final-path-segment rule covers this;
  pin it with a test so a refactor cannot silently drop it
For each family: FOLD it, or record in-code WHY it is genuinely a different model. A `:thinking`
variant may legitimately be distinct — say so explicitly rather than leaving it to the regex's silence.

## REQUIRED PROOF (green is not proof)
- `tests/test_model_identity_fold.py`: a CORPUS test — a table of real advertised ids with their
  expected folded id, INCLUDING the deliberate non-folds and the reason for each.
- **RED-PROOF BY EXECUTION:** revert the suffix table to its current value, run the test, observe RED,
  and confirm the fp4 case is named in the failure. **Report BOTH exit codes** (green run and
  deliberately-broken run). A green you did not first make fail is not evidence.
- NON-VACUOUS: a corpus of zero ids is RED, never a silent pass.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`, and `set -o pipefail` on any verification path.
- State explicitly what you proved by RUNNING vs by READING, and which git ref you measured on.

## GATE (both, from the worktree, must be green)
- `PYTHONPATH=src python3 -m charon.cli gate`
- `PYTHONPATH=src python3 -m pytest -q`

## BOUNDARY
Product ships standalone and is PUBLIC: no `/home/stack` paths, no internal IPs or hostnames, no
fleet/rig/SLOP references, no secrets in `src/` or committed config.

## OWNS — do not touch anything else
`src/charon/proxy.py`, `tests/test_model_identity_fold.py`. If the fix appears to require another
file, STOP and report — every other routing file is owned by another live ticket.

## REPORT BACK (short — no diffs)
Files changed · test names · both exit codes from the red-proof · gate pass/fail · before/after
pool identity for the MiniMax fp4 case · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "SW-IDENTITY-FOLD: fold quantization/variant model-id spellings into one pool identity"
```

Do NOT push.
