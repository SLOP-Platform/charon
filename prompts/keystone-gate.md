# BRIEF — build ONE KEYSTONE (KSF) gate

You are building exactly ONE gate for the Keystone Framework. **Your ticket = the KS id in your current git
branch name** (e.g. branch `feat/ks29-...` → ticket **KS29**). Portable stdlib-first; correctness over speed.

## Where you are
- You are in a git worktree of the keystone repo (`/home/stack/code/keystone`), on YOUR `feat/ks<NN>-...` branch.
  Commit here. No remote push, no merge.
- The `ksf` CLI + gate framework already exist (KS1/KS2/KS4 built). Reuse BUILT primitives only: stdlib
  `ast`/`git`, the graph adapter (`ksf/modules/graph_adapter`), `reuse_check`, `state_store`.

## Find YOUR spec (read these at /home/stack/charon-private — absolute paths, same filesystem)
- `fleet/state/KEYSTONE-AUDIT.md` §3 — the owned-file map. Yours is one of:
  KS29→`ksf/registry.py` (+ a registry gate) · KS31→`ksf/adapters/*` · KS8→`ksf/gates/coverage_ssot.py` (COMPLETE the partial: add numeric % + mechanized/guidance/GAP 3-class classification) ·
  KS22→`ksf/gates/firing_layer.py` · KS23→`ksf/gates/verification_delta.py` · KS18→`ksf/gates/anti_god_file.py` · KS10→`ksf/gates/no_duplicate_impl.py` · KS21→`ksf/gates/code_tension.py`.
- `fleet/state/ROADMAP.tsv` — grep your KS id for the full one-line scope.

## Build rules
- Implement the gate in YOUR owned file (+ private helpers as needed). Do NOT touch other gates' files.
- MUST ship a RED-PROOF test that goes RED when your gate's core logic is neutered (place it per the repo's
  redproof convention, e.g. `.ksf/gates/test_redproof_<name>.py`). A gate with no red-proof = rejected.
- **COLLISION RULE (critical):** do NOT edit `manifest.toml` or `.ksf/gates.json`. The MANAGER registers your
  gate at merge — parallel edits to those shared files collide. Build + test your gate STANDALONE (call its
  function/CLI directly in your test); registration happens later.

## LAST STEP
- Run your gate's own test pipe-free: `python3 -m pytest <your redproof test> -q; echo "EXIT=$?"` → 0, and show it goes RED when neutered.
- Commit on your `feat/ks<NN>-...` branch; report SHA. Do NOT push. Do NOT merge. (separate line.)
- Write `/home/stack/charon-private/fleet/state/overnight/<KSID>-BUILD-REPORT.md`: what you built (file:line), the red-proof test + its neutered-RED proof (real output), test EXIT, SHA, and confirm you did NOT edit manifest.toml/gates.json.
- Print `PACKET: <report path>` + ≤8-line honest summary. Real outputs only — never a fabricated SUCCESS line.
