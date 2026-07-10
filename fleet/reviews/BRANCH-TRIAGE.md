# Local-branch triage — product repo `/home/stack/code/charon`

Read-only investigation. `origin/master` @ `2b443aa` (post-#5 merge). `git fetch origin` run first.
Method: content diffs + patch-id/`git grep` on master, NOT commit messages (all three feature-sets reached master via **squash merges**, so `git cherry` reports false `+` uniques — ignored in favor of file-content checks).

---

## BRANCH 1 — `feat/tool-repair` (local-only, HEAD `e06b193`)

**Classification: SUPERSEDED**

- Two commits ahead of master: `e06b193` (RFL-1 quota) + `d7aa3f2` (tool-repair). Adds `src/charon/quota.py`, `src/charon/tool_repair.py`, `tests/test_quota.py`, `tests/test_tool_repair.py` (1226 insertions).
- All four files **exist on `origin/master` and are byte-identical** — `git diff origin/master feat/tool-repair -- <the 4 files>` is EMPTY.
- They landed on master via different (cherry-picked) commit hashes: `b3656e3` (tool-repair) and `bc296eb` (RFL-1).
- Deciding fact: **content diff of all four modules vs master is empty → already merged.**

**Recommended action: DELETE (`git branch -D feat/tool-repair`).** No PR needed — the modules are on master verbatim. (Note: if the roadmap wants them *wired into the proxy*, that is a NEW follow-on ticket against master; this branch adds nothing toward it.)

---

## BRANCH 2 — `feat/global-fallback-provider` (ahead of `origin/feat/global-fallback-provider` by 2; 65 behind master)

**Classification: MOSTLY SUPERSEDED, but harbors 2 genuinely-UNMERGED features. Branch tip is UNMERGEABLE as-is.**

- **The 2 unpushed commits** = `b6353aa` (trivial "merge: integrate latest master") + `ec20f02` (WCI-MVP reconcile). `ec20f02`'s `reconcile.py` is **identical to master** — in fact master's `reconcile.py` history shows the *same hash* `ec20f02`. So both unpushed commits are already on master. **Nothing to push.**
- **Global-fallback capability IS on master**: `tests/test_fallback_provider.py` is byte-identical branch-vs-master; `config.py` has `fallback_providers` (4 refs), `gateway.py` has fallback wiring (19 refs). Landed via Batch-1 squash `c9fedf5`. The branch's own `f4b7011` "add global fallback provider chain" is superseded.
- **No open PR** for this branch (only open PR in repo is dependabot #83). Its remote `origin/feat/global-fallback-provider` @ `bb75206` is also stale.
- **The branch is 65 commits BEHIND master.** Two-dot diff `origin/master..branch` is almost entirely *deletions* (−4777 lines): master has quota.py, tool_repair.py, semantic_proof.py, response_normalizer.py, types.py, etc. that the branch lacks. **Merging this tip would REVERT large swaths of master.**
- **BUT 5 files are branch-only and their features are NOT on master anywhere** (`git grep` on master finds nothing):
  - `tools/check_public_clean.py` + `tools/.public-clean-exceptions.json` + `tests/test_public_clean.py` — **PUBLIC-CLEAN-LINT** tooling (guards the public repo against personal/internal info — directly serves the standing "public repos: no personal info" rule). **Genuinely unmerged.**
  - `tests/test_connect_omp.py` + `connect.py` deltas — **CONNECT-OMP-WSL** (reject Windows-interop binaries on WSL, force native bun/npm). No `interop`/`wslpath`/Windows-reject logic on master. **Genuinely unmerged.** (Also duplicated in a separate local-only branch `feat/connect-omp-wsl` @ `5660fe6`, itself unmerged.)
  - (SETUP-KEY-UX `_mask_key`/`_probe_key` DID reach master — on `cli.py` — so that slice is superseded.)
- Deciding fact: **fallback/pricing/DTC/WCI content is on master, but `check_public_clean` and `connect_omp` exist on no master path → 2 real unmerged features trapped on an unmergeable stale branch.**

**Recommended action: DO NOT push (no PR to update; commits already on master). DO NOT delete blindly — salvage first.** Extract the two unmerged capabilities onto fresh branches cut from current `origin/master`:
1. PUBLIC-CLEAN-LINT (`tools/check_public_clean.py` + exceptions json + test) — high value, aligns with the public-repo hygiene rule; open as its own ticket/PR.
2. CONNECT-OMP-WSL — confirm intent (it lives in two unmerged branches; may have been deliberately parked) before re-cutting.
Then delete both `feat/global-fallback-provider` and its stale remote. Everything else on the branch is superseded.

---

## BRANCH 3 — `feat/wci-semantic-slice` (1 ahead of master, 65 behind; WCI-FOLLOWON)

**Classification: SUPERSEDED (feature fully on master)**

- Single commit `0fb864c` (WCI-FOLLOWON: `merge_after` concurrency + §5.1 semantic-independence proof engine), touching `engine/semantic_proof.py`, `engine/board.py`, `intake.py`, `tests/test_semantic_proof.py`.
- All four files **EXIST on master**; `semantic_proof.py`, `test_semantic_proof.py`, `board.py` are identical. `merge_after` is on master (`board.py` 6 refs, `intake.py` 9 refs). The feature landed via master commit `87e997d` (same WCI-FOLLOWON name).
- **The ONLY residual difference** is a 1-line drift in `intake.py`: branch has `DEFAULT_TIER = "sonnet"`, master has `DEFAULT_TIER = "med"`. This is incidental, NOT the WCI feature, and *conflicts* with master's deliberate default.
- Board-validation red: `validate_board.sh` flags `WCI-FOLLOWON` for a broken dep on a missing `WCI` ticket. **The WCI-FOLLOWON code already shipped to master** — the red is a stale *ticket/board-graph* problem, not missing code. Fixing it means removing/repointing the `WCI-FOLLOWON → WCI` dependency edge in the board data, **not** merging this branch.
- Deciding fact: **the entire WCI-FOLLOWON module is on master (via `87e997d`); the branch's only unique content is a 1-line `DEFAULT_TIER` value that diverges from master's chosen `"med"`.**

**Recommended action: DELETE (`git branch -D feat/wci-semantic-slice`).** The feature is on master. Do not merge the branch — it would drag master back 65 commits. If `DEFAULT_TIER="sonnet"` is actually wanted, make it a standalone 1-line change against master (separate decision). The board red is resolved by fixing the WCI ticket dependency in the fleet board, independent of this branch.

---

### Summary table

| Branch | Class | Action |
|---|---|---|
| `feat/tool-repair` | SUPERSEDED | Delete — quota.py/tool_repair.py identical on master (cherry-picked) |
| `feat/global-fallback-provider` | MOSTLY SUPERSEDED + 2 unmerged | Salvage PUBLIC-CLEAN-LINT + CONNECT-OMP-WSL onto fresh branches off master, then delete; don't push |
| `feat/wci-semantic-slice` | SUPERSEDED | Delete — WCI-FOLLOWON on master via `87e997d`; only a conflicting 1-line tier default remains |
