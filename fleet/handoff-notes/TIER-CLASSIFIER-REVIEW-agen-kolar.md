# VERDICT: DO-NOT-LAND

Branch `feat/tier-classifier` @ `0a759a8` (parent `f83d877`), worktree
`/home/stack/charon-private-wt/TIER-BALANCE`, 2 commits ahead of `origin/master`
(merge-base `e0a08b2`).

**Why not LAND:** the deliverable is real and the board re-tier pass is mostly defensible,
but the *gate* half is non-enforcing in three independent ways that I reproduced by
execution: (1) it cannot go RED in the shipped configuration, (2) it silently
disappears — still GREEN — if the classifier file is missing/renamed, and (3) its
tests are executed by no gate, no CI job and no land path. On top of that the
highest-priority rule in the table (`SEC_RE` -> frontier, checked first, no difficulty
guard) fires on ordinary substrings (`auth` inside `authoring`, `token` inside
`token-budget`, `/key` inside `/keyboard`) and routes trivial d1 docs work to the most
expensive model chain. All four are small, surgical fixes — this is a "fix and re-review",
not a redesign.

Claims verification summary (details below):

| Builder claim | Status |
|---|---|
| classifier at `fleet/capability/tier_classify.py` | TRUE |
| drift-check added to `validate_board` as "2f" | TRUE (label is unique, `validate_board.sh:230`) |
| LiteLLM tier-tag "proven" | PARTLY — proof runs only inside a test nothing executes; zero production callers |
| 36 re-tiers, frontier 3->14, strong 89->74, economy 12->16 | TRUE vs merge-base (commit msg says "34", actual 36) |
| "Fail-on-revert test ... trips the gate RED" (commit msg `0a759a8`) | FALSE — the gate cannot go RED as shipped |
| "TWO CONSUMERS" (docstring `tier_classify.py:14-21`) | FALSE — one consumer; the routing half is inert |

---

## Findings

### F1 — BLOCKING — the drift check can never go RED as landed
`fleet/capability/tier_classify.py:98-110` (`_red_set`), `:230-241` (`drift` rc logic),
`fleet/validate_board.sh:238-252`.

`drift` returns 2 (the hard-fail signal `validate_board` maps to RED) **only** for ticket
ids listed in `fleet/state/tier-drift-red.txt`. That file does not exist in the worktree
and is not added by the branch (`git ls-files | grep tier-drift` -> empty), and nothing in
the branch creates or seeds it. Every mismatch therefore prints `WARN` and returns 0.

Reproduced (scratch copy of `fleet/`, branch untouched):

```
$ sed -i 's/^tier: .*/tier: economy/' fleet/board/FIX-PROVIDER-KEY-EXFIL.md   # security ticket
$ python3 fleet/capability/tier_classify.py drift
WARN tier-drift: FIX-PROVIDER-KEY-EXFIL declared=economy derived=frontier :: security-critical path
rc=0
$ bash fleet/validate_board.sh
  WARN tier-drift: FIX-PROVIDER-KEY-EXFIL declared=economy derived=frontier :: ...
  GREEN board structurally valid
validate_board rc=0
```

Failure scenario: an author (or a droid doing board hygiene) sets
`FIX-PROVIDER-KEY-EXFIL` — key-exfiltration work — to `tier: economy`. Preflight is GREEN,
`claim.sh` hands it to an economy droid, and the cheapest chain
(`deepseek-v4-flash-free,...`) runs security-critical code. The gate that exists to stop
exactly this prints one WARN line among 100+ existing WARN lines and launches the wave.

The mechanism *does* work when the file exists (verified: adding the id to
`tier-drift-red.txt` gives `RED ... rc=2`), so the fix is to ship the file with at least
the security/money-path ids in it — otherwise this is a WARN-only advisory being described
in the commit message as a gate.

### F2 — BLOCKING — fail-OPEN: rc 2 is overloaded, a missing classifier is silently GREEN
`fleet/validate_board.sh:239-249`.

```python
if _td.returncode not in (0, 2):
    red.append("tier-drift-check-failed: ...")
```

`python3 <missing-file>` exits **2**. Verified:

```
$ python3 /nonexistent/tier_classify.py drift ; echo $?
python3: can't open file '...': [Errno 2] No such file or directory
2
```

So rc 2 means both "a RED-set ticket drifted" and "the script isn't there". Reproduced
end to end:

```
$ mv fleet/capability/tier_classify.py fleet/capability/tier_classify.py.bak
$ bash fleet/validate_board.sh | grep -E 'tier-drift-check-failed|GREEN'
  GREEN board structurally valid
validate_board rc=0
```

Failure scenario: any refactor that moves/renames `fleet/capability/tier_classify.py`
(or an `argparse` change — argparse also exits 2 — e.g. renaming the `drift` subcommand)
deletes the entire check from preflight with no RED, no WARN, and no stderr surfaced. This
is the `fail-quiet` class the rig's own GATE-CREATION-STANDARD S5 names. Fix: use a
distinct sentinel rc for "RED drift found" (e.g. 3), or assert the script path exists
before running it.

### F3 — MAJOR — `SEC_RE` false positives route trivial work to the most expensive tier
`fleet/capability/tier_classify.py:33` and `:70-71`.

```python
SEC_RE = re.compile(r'egress|exfil|secret|(^|[_/])key|token|auth|providers\.py|key-canary')
...
if sec:
    return "frontier", "security-critical path (ratchet: never trade capability)"
```

This is the FIRST rule and has no difficulty or work_class guard, so it overrides
everything. It is unanchored substring matching. Verified against the real CLI:

```
$ python3 fleet/capability/tier_classify.py classify --work-class docs --difficulty 1 --owns docs/token-budget.md
frontier	security-critical path (ratchet: never trade capability)
$ ... --owns docs/authoring-guide.md      -> frontier   ("auth" inside "authoring")
$ ... --owns docs/keyboard-shortcuts.md   -> frontier   ("/key" inside "/keyboard")
$ ... --owns docs/oauth-notes.md          -> frontier   ("auth" inside "oauth")
$ ... --owns fleet/state/AUTHORS.md       -> economy    (case-sensitive: uppercase misses)
```

Failure scenario: a d1 docs ticket owning `docs/token-budget.md` derives `frontier`,
becomes claimable ONLY by a frontier droid (see F4), and runs on `deepseek-v4-pro` — the
most expensive chain in `fleet/tier-models.tsv:56`. The last line also shows the rule is
arbitrarily case-sensitive: `authoring-guide.md` is frontier, `AUTHORS.md` is economy.

This is not hypothetical on the current board: **BOUNCE-1** (`fleet/board/BOUNCE-1.md`,
`work_class: tests`, owns `fleet/checks/egress-key-canary.sh`,
`fleet/tests/egress-key-canary.test.sh`) was moved strong -> frontier by this rule. It is
a rig canary shell script; frontier is a two-band jump.

Fix: anchor on path segments (`(^|/)(keys?|tokens?|auth)([./_-]|$)`) and/or require
`hot`/`money` co-signal, and add `re.IGNORECASE` deliberately rather than by accident.

### F4 — MAJOR — blast radius: `frontier` is a claim CEILING, not a hint
`fleet/claim.sh:312-313`, `fleet/claim.sh:29-38`, `fleet/fleet-droid.sh:222-227`,
`fleet/tier-models.tsv:56-58`.

`claim.sh` skips any ticket whose tier rank exceeds the droid's rank
(`if (trank > drank) next`). Ranks confirmed live:

```
$ charon tier ranks
economy 1 | strong 2 | frontier 3   (plus legacy aliases)
```

So the 15 tickets promoted into `frontier` are now **unclaimable by strong or economy
droids** and can only be drained by `fleet-droid.sh frontier`, which resolves to
`deepseek-v4-pro,kimi-k2.6,glm-5.2,minimax-m3-free`. That is both a cost increase and a
throughput serialization on a single droid class. This is a real consequence of the change,
not a defect per se — but it means every questionable frontier promotion (F3, F5) is
expensive twice over.

Amplified pre-existing risk: if `charon` is not on PATH for a droid, `claim.sh:37` falls
back to `RANK=([opus]=3 [sonnet]=2 [haiku]=1)`, every canonical tier ranks 0, and the
second ("other") pass lets an **economy** droid claim a **frontier** ticket. Pre-existing,
but the branch takes the exposure from 3 tickets to 14.

### F5 — MAJOR — breadth (`nsurf`) is used as a difficulty proxy and inflates cost
`fleet/capability/tier_classify.py:53` and `:73-74`.

```python
if money and (d >= 4 or (livefwd and d >= 3) or nsurf >= 3):
    return "frontier", ...
```

`nsurf` is just the count of non-`.md` owned paths. A ticket that touches 3 small files at
**difficulty 2** goes to frontier. On the real board:

```
FT-CATALOG-SEED  economy -> frontier  wc=greenfield-feature d=2
  :: money+ (livefwd=0 d2 nsurf3)
  owns: src/charon/provider_presets/hosted.py, src/charon/routing_policy/free_tier_catalog.py,
        tests/test_free_tier_catalog.py
```

A d2 catalog-seeding ticket (a file, its policy module, its test — the *normal* shape of
any small feature) is now a frontier-only, `deepseek-v4-pro` job. Failure scenario: every
well-decomposed money-path ticket that follows the repo's own "module + test + preset"
convention hits `nsurf>=3` and is priced at the top tier regardless of how easy it is.
Suggest requiring `nsurf>=3 AND d>=3`, or counting distinct top-level packages rather than
files.

### F6 — MAJOR — the "routing half" is built-but-unwired (INERT)
`fleet/capability/tier_classify.py:14-21` (docstring: "TWO CONSUMERS"), `:147-179`,
`:227-229`.

Repo-wide grep for `build_router_model_list|validate_router|router-validate|classify_tier`
outside the module returns **only** `fleet/validate_board.sh` (the drift check) and
`fleet/capability/tests/test_tier_classify.py`. The actual routing path —
`fleet/fleet-droid.sh:107-110` (`tier_chain`) and `fleet/charon-run.sh` — parses
`fleet/tier-models.tsv` directly with awk and never touches `litellm.Router` or this
module. The claim "the gateway routing path — classify_tier() emits the tier tag" describes
a consumer that does not exist. `validate_router()` is a self-contained demo whose only
caller is a test that nothing runs (F7).

Failure scenario: a reader (or a future ticket) trusts the docstring, assumes tier tags are
already resolving through litellm on the gateway, and skips building the real wiring.
Either wire it or downgrade the docstring to "designed, not yet wired".

Nit in the same block: the docstring says `--router-validate`; the actual CLI subcommand is
`router-validate` (`tier_classify.py:202`).

### F7 — MAJOR — the new tests are executed by NO gate, NO CI job, and NO land path
`fleet/capability/tests/test_tier_classify.py` (98 lines, 15 tests).

- `fleet/gate.sh:19,33` — `TESTS_DIR="${FLEET_TESTS_DIR:-$FLEET/tests}"`, `tests=("$TESTS_DIR"/*.test.sh)`. Bash suites only; this pytest file is not discovered.
- `.github/workflows/rig-ci.yml` — runs `fleet/checks/rig-ci-scope.sh tests`, an explicit allowlist `CI_SUITES` of `fleet/tests/*.test.sh` (`rig-ci-scope.sh:49-70,302-313`). No `pytest` step exists anywhere in the workflow (`grep -n pytest fleet/checks/rig-ci-scope.sh` -> no hits).
- `fleet/land.sh:288-301` — for this repo the elif chain matches `fleet/validate_board.sh` first, so the `python3 -m pytest -q` branch is never reached.

The suite passes when run by hand (`15 passed in 2.46s`, executed), but nothing will ever
run it again. Failure scenario: someone neuters `SEC_RE` or reverts a rule; the
"fail-on-revert" test that was written to catch that never executes, `validate_board` stays
GREEN (F1/F2), and the regression lands unnoticed.

This also violates the rig's own standard: `fleet/GATE-CREATION-STANDARD.md:27` S1 requires
"Fleet checks: a companion test in `fleet/tests/` carrying a `red-proof`/`fail-on-revert`
marker." The companion test is in `fleet/capability/tests/`, which no runner scans.

### F8 — MODERATE — the new gate is placed where the gate meta-standard cannot see it
`fleet/checks/gate-creation-standard.sh:155` scans `"$CHECKS_DIR"/*.sh "$CHECKS_DIR"/*.py`
(i.e. `fleet/checks/`). The tier-drift check was added as an inline block inside
`fleet/validate_board.sh`, so it is structurally exempt from the S1 red-proof and S5
fail-loud scans that would have flagged F1, F2 and F7. Whether or not this was intentional,
the effect is that the rig's newest gate is the one gate the gate-standard cannot audit.

### F9 — MODERATE — vacuous pass: empty / tier-less board is GREEN, not RED
`fleet/capability/tier_classify.py:113-128` (`board_drift`), `:119-121`
(`if not declared: continue`).

Reproduced:

```
$ python3 fleet/capability/tier_classify.py drift --board <empty dir>            -> rc=0, no output
$ python3 fleet/capability/tier_classify.py drift --board <2 tickets, no tier:>  -> rc=0, no output
```

Zero discovery is indistinguishable from zero drift. Failure scenario: a board-path bug, a
bad `--board`, or a checkout where `fleet/board` is empty produces a confident silent pass.
A gate should assert it examined >0 items. (`validate_board` never passes `--board`, so in
practice the classifier always resolves its own `../board`; the risk is the tier-less path
and any future caller.)

### F10 — MODERATE — root cause is detected, not prevented; drift will re-accumulate
No ticket-creation or board-edit path calls `classify_tier`. Grep across `fleet/*.sh`
(`decompose.sh`, `handoff.sh`, `submit.sh`, `auto_append.py`) returns no reference. `tier:`
remains hand-typed free text at creation; the only feedback is a post-hoc WARN that nobody
is required to act on (F1). The ticket intent was "stop tier drift"; what landed detects
drift after the fact, advisory-only.

Secondarily, the derived tier is now driven mostly by `work_class`, which is itself
author-chosen (it *is* allowlist-validated at `validate_board.sh:174-181`, so this is
weaker than the original problem — but the judgment call has moved one field over, not
disappeared). Visible on the board: `SG-ISSUE-CONTROL-PLANE` (a design doc,
`work_class: rig-meta`, d5) -> frontier, while `MODEL-PREFLIGHT` (also a `.md` state doc,
`work_class: ci-infra`, d4) -> strong. Same artifact shape, different tier, decided by a
free-choice label.

### F11 — MODERATE — two capability DOWNGRADES on review-class work
```
FINAL-E2E-REVIEW   frontier -> strong   wc=ci-infra d=3  :: middle band d3 ci-infra
MODEL-PREFLIGHT    frontier -> strong   wc=ci-infra d=4  :: middle band d4 ci-infra
```
Both own a single `fleet/state/*.md` and were hand-set to frontier by an author. The rule
demotes them purely because `work_class: ci-infra` is not in the design-review branch.
`FINAL-E2E-REVIEW` is the end-to-end product review; running it on a cheaper model is the
direction that produces a worse review while looking green. Worth an explicit operator
decision rather than a silent rule outcome.

### F12 — MODERATE — `board_drift` scans done/parked tickets that every other check skips
`fleet/capability/tier_classify.py:115` globs all `board/*.md` with no `is_done`/`is_parked`
filter, unlike `validate_board.sh:203-207` (`inactive()`), which exempts them from the
work_class / difficulty / owns / WCI checks precisely because their fields are provisional.
Today this produces no output (the board is drift-free), so it is latent: the first done
ticket with a provisional `owns` will emit a permanent WARN nobody can clear without
editing shipped work.

### F13 — NIT — self-report inaccuracies
- `f83d877` message: "34 re-tiers". Actual: **36** board files changed, all tier-only (verified: 36 `-tier:` / 36 `+tier:` lines, no other field touched).
- `0a759a8` message: "Fail-on-revert test proves reverting the rule ... trips the gate RED." `test_fail_on_revert` (`test_tier_classify.py:70-81`) only asserts `classify_tier()`'s return value changes; it never invokes `drift`, `validate_board`, or any rc. And the gate cannot go RED at all (F1).
- `tier_classify.py:11` cites `assign.py:12` as the tier filter. `fleet/capability/assign.py:12` is the D&S gate line; the cost-tier filter is described at `assign.py:14-16`.
- `test_tier_classify.py:86` imports `litellm` transitively via `tc.validate_router`. `litellm` is not declared in `fleet/checks/requirements.txt` or any rig requirements file. It happens to be installed on this box; on a clean checkout the test errors rather than skips.
- `test_tier_classify.py:93-97` `test_live_board_is_balanced` carries an unjustified `pytest.skip("board not present")`. `fleet/board` is git-tracked so it will not fire, but it is a skip with no linked justification (criterion (c)).

### Context — pre-existing RED, NOT caused by this branch (flagged, not dismissed)
`bash fleet/checks/gate-creation-standard.sh` exits **1** with 4 findings:
`unproofed-gate: reachability-gate`, `no-red-proof-test: large-file-guard.sh`,
`no-red-proof-test: rig-ci-scope.sh`, `class-untraced: no-decision-time-gate`. None of these
name any file this branch touches (branch touches only `fleet/board/*.md`,
`fleet/capability/tier_classify.py`, `fleet/capability/tests/test_tier_classify.py`,
`fleet/validate_board.sh`), so they pre-date it. Worth a ticket: the rig's own S1 meta-gate
is currently red, which is part of why F7/F8 slipped through.

### Context — branch is behind master (no conflict, but the counts are vs merge-base)
`origin/master` has 7 board tickets added since merge-base `e0a08b2`
(`4LOM-CANARY-SERVICE`, `BOARD-REDS-TRIAGE`, `CENTRAL-WORK-ROUTING-HUB`,
`DROID-BRIDGE-REGISTER`, `LENS-REGISTRY-AND-REPORT`, `REGISTRY-META-CATALOG`,
`WATCHDOG-RESTART-CMDS-VERIFY`) and one `.md.parked` deletion. No overlap with the 36 files
this branch edits, so no modify/delete conflict. I simulated the post-merge board (branch's
104 tickets + master's 7) and ran `drift`: **rc=0, no drift** — merging will not introduce
new WARN noise.

---

## What I verified BY EXECUTION

| # | Command | Result |
|---|---|---|
| 1 | `bash fleet/validate_board.sh` (in worktree) | **rc=0 GREEN**; zero `tier-drift` lines — board is genuinely drift-free vs the classifier |
| 2 | `python3 -m pytest fleet/capability/tests/test_tier_classify.py -q` | **15 passed in 2.46s** (rc 0) — including the live `litellm.Router` model-group resolution |
| 3 | `python3 fleet/capability/tier_classify.py drift` | rc=0, no output |
| 4 | drift vs **empty** board dir | rc=0, silent (F9) |
| 5 | drift vs board with tickets but no `tier:` | rc=0, silent (F9) |
| 6 | mis-tier `FIX-PROVIDER-KEY-EXFIL` -> economy, run drift | `WARN`, **rc=0** (F1) |
| 7 | same + `validate_board.sh` | **GREEN, rc=0** (F1) |
| 8 | same + seeded `fleet/state/tier-drift-red.txt` | `RED`, **rc=2** — mechanism works, file just isn't shipped |
| 9 | `mv tier_classify.py .bak` then `validate_board.sh` | **GREEN, rc=0**, no `tier-drift-check-failed` (F2) |
| 10 | `python3 /nonexistent/x.py drift; echo $?` | **2** — proves the rc collision (F2) |
| 11 | `classify --owns docs/token-budget.md` / `authoring-guide.md` / `keyboard-shortcuts.md` / `oauth-notes.md` (all d1 docs) | all **frontier** (F3) |
| 12 | `classify --owns fleet/state/AUTHORS.md` d1 | economy — case-sensitivity inconsistency (F3) |
| 13 | `charon tier ranks` | `economy 1 / strong 2 / frontier 3` — confirms the claim ceiling (F4) |
| 14 | per-ticket `classify <ID>` for all 36 re-tiers | reasons reproduce the applied tiers exactly |
| 15 | tier counts at merge-base vs HEAD | 3/89/12 -> 14/74/16 — builder's numbers confirmed |
| 16 | `git diff` field census on the 36 board files | 36 `-tier:` / 36 `+tier:`, nothing else changed (commit msg says 34) |
| 17 | post-merge board simulation (104 + master's 7) -> `drift` | rc=0, no drift |
| 18 | `bash fleet/checks/gate-creation-standard.sh` | **rc=1**, 4 findings — all pre-existing |

All mutation tests (4-12) ran against a scratch copy of `fleet/` under the session
scratchpad. **The branch and worktree were not modified**; `git status --porcelain` in
`/home/stack/charon-private-wt/TIER-BALANCE` was clean before and after.

## What I verified BY READING ONLY

- `fleet/claim.sh:305-323` tier-rank claim filter semantics (rank values themselves were executed).
- `fleet/land.sh:288-301` gate-selection elif chain (not run — it pushes).
- `.github/workflows/rig-ci.yml` step list and `fleet/checks/rig-ci-scope.sh:49-70,302-313` allowlist (not run — CI).
- `fleet/capability/assign.py:1-40` docstring describing the cost-tier filter (its runtime behaviour was not exercised).
- `fleet/GATE-CREATION-STANDARD.md:27` S1 wording.

## Smallest set of changes that would flip this to LAND

1. Ship `fleet/state/tier-drift-red.txt` seeded with at least the security + money-path ids (F1). Note `fleet/state/` is gitignored — if it must be tracked, pick a tracked path or add a `!` exception.
2. Give "RED drift found" its own rc (e.g. 3) and treat rc 2 as a hard failure; or `os.path.exists()`-assert the classifier before running it (F2).
3. Anchor `SEC_RE` on path segments and decide case-sensitivity deliberately (F3); re-run the balance pass and re-check `BOUNCE-1`.
4. Move the red-proof to `fleet/tests/tier-drift.test.sh` (bash, hermetic, red-proof marker) so `gate.sh`/`rig-ci` actually run it, and add it to `CI_SUITES` (F7, F8).
5. Correct the docstring's "TWO CONSUMERS" to reflect one live consumer, or wire the routing half (F6).

Optional but recommended before the next balance pass: F5 (`nsurf>=3` alone -> frontier) and
F11 (review-class downgrades) both deserve an explicit operator call, since F4 makes every
frontier promotion a claim ceiling on the most expensive chain.

---
Reviewer: agen-kolar (independent adversarial). Read-only: no commit, push, merge, or file
modification on `feat/tier-classifier`.
