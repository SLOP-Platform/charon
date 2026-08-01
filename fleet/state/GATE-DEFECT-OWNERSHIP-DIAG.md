# GATE-DEFECT-OWNERSHIP-DIAG — false "code owned by NO live board ticket"

Diagnosed 2026-08-01. Branch under test: `fix/shared-namespace-contention` (rig repo
`/home/stack/charon-private`). **Diagnosis only — nothing fixed, nothing forced.**

## Verdict

NOT the stale-base class. `RIG-CI-BASE-DEFAULT-BRANCH` is already fixed and working:
`land-push.sh:176` resolves `origin/master` first, and `base_board_owns()` resolves the board at
the **base-ref TIP** (`substrate_first_gate.py:390`), so the ticket landed at `f8266ef` IS in the
base tree the gate reads. It reads the right ref. It then throws the ticket away.

## Root cause

`fleet/checks/substrate_first_gate.py:401-403`

```python
        try:
            fm = parse_frontmatter(content)
        except TicketError:
            continue  # an unparseable base ticket grants no ownership (it is not a live owner)
```

`parse_frontmatter()` is a **strict PyYAML** parse of everything above the first `_HALT` line
(`substrate_first_gate.py:75,111-126`). `fleet/board/SHARED-NAMESPACE-CONTENTION.md` has a
`note: |` block scalar opening at line 24; line **92** (`D&S — Deps & Sequence:`) is written at
**column 0**, which TERMINATES the block scalar. YAML then reads lines 93-96 as a new top-level
mapping and dies on the backtick at line 96 (`` `stop-worker.sh` ``).

So the ticket raises `TicketError`, `base_board_owns` **silently `continue`s**, its four `owns:`
paths never enter `owns_entries`, `_path_owned()` returns False for all four, and the gate prints
a message that asserts something FALSE: *"no base-ref ticket `owns:` covers these files."* The
true statement is "a base-ref ticket owns these files but I could not parse it." The module's own
docstring says *"A ticket the gate cannot parse is a RED, never a silent skip"* — line 402 is that
exact silent skip, and because the branch does not TOUCH the board file, `cmd_check` (which does
RED on `TicketError`, line 502) never runs on it. The parse error has no voice anywhere.

Class name: **fail-open on the OWNER, fail-closed on the OWNED** — a gate that drops evidence
silently and then reports the absence of evidence as proof of absence.

## Reproduction (deterministic)

```
$ cd /home/stack/charon-private
$ RIG_CI_ROOT=$PWD RIG_CI_BASE=origin/master \
  RIG_CI_HEAD=origin/fix/shared-namespace-contention \
  python3 fleet/checks/substrate_first_gate.py pr-has-ticket
  RED  substrate: this change touches CODE owned by NO live board ticket
  (fleet/claim-jedi-name.sh, fleet/spawn-worker.sh, fleet/tests/claim-jedi-name.test.sh,
   fleet/tests/scratch-namespace.test.sh) — no base-ref ticket `owns:` covers these files ...
RC=1
```

Emitting line: **`fleet/checks/substrate_first_gate.py:875`** (returns 1 at :880).
Call chain: `land-push.sh:200` -> `rig-ci-scope.sh:236 cmd_board` -> `:322` -> `substrate-first-gate.sh pr-has-ticket`.

### Proof it is the YAML parse, not the ref

```
$ python3 -c "...; g.parse_frontmatter(g._git(root,'show',base+':fleet/board/SHARED-NAMESPACE-CONTENTION.md'))"
PARSE FAIL: TicketError frontmatter does not parse as YAML at line 96:
  found character '`' that cannot start any token.
```

Re-indent lines 92+ by two spaces (keeping them inside `note: |`) in memory, re-resolve:

```
resolved: True entries: 174        (was 170)
 owned? fleet/claim-jedi-name.sh True
 owned? fleet/spawn-worker.sh True
 owned? fleet/tests/claim-jedi-name.test.sh True
 owned? fleet/tests/scratch-namespace.test.sh True
```

One 2-space indent flips the gate from RED to GREEN. Root cause confirmed.

### Two owns-readers that disagree

The LINE-BASED reader sees the field perfectly:

```
$ . fleet/_lib.sh; ticket_owns SHARED-NAMESPACE-CONTENTION
fleet/claim-jedi-name.sh, fleet/tests/claim-jedi-name.test.sh, fleet/spawn-worker.sh, fleet/tests/scratch-namespace.test.sh
```

`_lib.sh:301 ticket_owns` (via `_vm_meta`), `validate_board.sh field()`, `rig-ci-scope.sh:268
_field`, `claim.sh:144`, `ladder-health.sh:81`, `reconcile-board-pr-done.sh:49` are all
`sed`/`awk` line matchers — they never see a YAML break. `substrate_first_gate.py` is the ONLY
strict-YAML consumer. That is why 23 malformed tickets have sat on master with every board gate
GREEN.

## Blast radius — this is NOT one ticket

Full sweep of `origin/master`'s board through the gate's own parser:

```
live parseable: 89   parked: 8   UNPARSEABLE (silently unowned): 47
```

47 breaks down as **23 live `fleet/board/*.md` tickets** with broken YAML +
23 `fleet/board/briefs/*.md` (empty frontmatter) + `fleet/board/retired/FRAGILITY-TICKETS.md`.

Live tickets whose `owns:` is INVISIBLE to the ownership gate right now:

```
ASSIGN-DISPATCH-PICK-FIX  BENCH-OOB-GRADING  BRIDGE-MIGRATE-DROID-CLIENT  BRIEF-ABSOLUTE-PATHS
CI-SUITES-CANARY  FORCE-PUSH-SAFETY-GATE  FT-LIMITS-GROQ-RECONCILE  KSF-LOAD-BEARING
LAUNCHER-CRASH-PARTIAL-DETECT  LITELLM-CAPABILITY-ADOPTION  MARKER-PROOF-MECHANIZE
NO-LOCAL-MASTER-COMMITS  PREFLIGHT-GATE-REGISTRY  PRICE-REFRESHER  PROJECT-MEMBERSHIP-GATE
RECONCILE-WIRING  RELEASE-PRESERVES-WORK  REPO-MAP-CONVERGE  RUNTIME-INERT-DETECTION
SESSION-END-GATE-REPAIR  SHARED-NAMESPACE-CONTENTION  SPEND-METRIC-TRUSTWORTHY  SSOT-DRIFT-GATE
```

~21% of the live board. Every branch whose only ticket is one of these 23 will hit the same
false RED. This is a standing push-blocker across a fifth of the board, and exactly the pressure
that manufactures `--force` habits.

### Gates sharing the read path

| Consumer | Shares the defect? | Why |
|---|---|---|
| `substrate_first_gate.py pr-has-ticket` (`:854`) | **YES — the defect** | silent skip at `:402` |
| `rig-ci-scope.sh cmd_board` (`:322`) | **YES (inherits)** | sole caller of pr-has-ticket |
| `land-push.sh` gate (`:200`) | **YES (inherits)** | runs rig-ci-scope board |
| `.github` rig CI `board` job | **YES (inherits)** | same cmd_board |
| `substrate_first_gate.py check` (`:502`) | NO | REDs loudly on TicketError — but only for tickets IN the diff |
| `validate_board.sh`, `_lib.sh ticket_owns`, `claim.sh`, `ladder-health.sh`, `wci-contention.sh`, `land.sh` dirty-scope, `reconcile-*` | NO | line-based `sed`/`awk`; blind to YAML validity (which is the second half of the problem — nothing catches malformed frontmatter at authoring time) |

### Secondary defect found in the same function

`base_board_owns` filters only `"/archive/" in path` (`:398`). `git ls-tree -r` also returns
`fleet/board/retired/` and `fleet/board/briefs/`, so a RETIRED ticket with parseable frontmatter
would still grant LIVE ownership. Not the cause here (`retired/FRAGILITY-TICKETS.md` happens to
be unparseable) but it is a live fail-open.

## Proposed minimal fix (3 parts — not applied)

1. **Stop lying** — `substrate_first_gate.py:401-403`: collect unparseable base tickets instead of
   dropping them, return them from `base_board_owns`, and have `cmd_pr_has_ticket` name them in the
   RED. A gate that cannot read the board must say so, not claim the board is empty.
2. **Unblock** — repair the 23 tickets' frontmatter: the recurring shape is a column-0 line
   (`D&S — Deps & Sequence:`, a bare URL, a backtick) escaping an open `note: |`/`source: |` block.
   For `SHARED-NAMESPACE-CONTENTION.md` that is a 2-space indent of lines 92-96.
3. **Close the class** — add a strict-YAML frontmatter parse to `validate_board.sh` +
   `rig-ci-scope.sh syntax` (reusing `parse_frontmatter`, no second parser) so malformed
   frontmatter REDs at authoring time. Today the line-based readers make it invisible until a
   different gate silently mis-answers an ownership question.

Sequence: 1 before 2 (so the repair is verifiable by the gate's own diagnostic), 3 last (it will
RED until 2 completes). Fix 1 alone still leaves the push blocked — but blocked with the TRUE
reason printed, which is strictly better than a false one.

## Owns / contention note

Files 1 and 3 touch `fleet/checks/substrate_first_gate.py`, `fleet/validate_board.sh`,
`fleet/checks/rig-ci-scope.sh` — `validate_board.sh` is flagged in `rig-ci-scope.sh:11` as
contended by REPO-MAP-CONVERGE / REPO-FIELD-REQUIRED and others. Mint the fix ticket with an
owns-collision check before dispatching.
