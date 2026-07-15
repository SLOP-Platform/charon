# REDS-CORPUS — reds-replay ground truth for the REVIEWER-DOGFOOD eval

Ticket: `fleet/board/REVIEWER-DOGFOOD-REDS.md`. Harness: `fleet/benchmark/reviewer-dogfood.sh`.
Memory: `[[real-work-is-the-trust-test]]` `[[benchmark-not-a-valid-ranker]]`
`[[document-model-self-report-lies]]`.

## Why this file exists

The REVIEWER job (today: Claude Code) cannot be graded by `charon.cli gate` — that grades
a WORKER's *output*, not a reviewer's *judgment*. The only valid grade for a reviewer is
**recall on real, previously-caught bugs**: feed it the exact diff that once slipped past
us (or was caught by adversarial review) and check whether it names the real defect.
This file is the ground truth those replays are graded against. Every case below is a
**real commit in this project's own history** — not synthetic, not invented. The harness
computes each case's diff **live from git** (`git diff <good_ref> <bad_ref> -- <paths>`)
rather than a hand-copied blob pasted into this file, so a case can never silently drift
from the real commit it claims to represent.

## OOB (out-of-band) design note — read before extending this corpus

The ticket's accept text draws a direct analogy to the MODEL-PREFLIGHT battery's held-out
answer keys (`chmod 0700`, owned by a separate `bench-grader` unix user, unreachable by a
WORKER model that has real filesystem/worktree access). That mechanism exists because a
preflight WORKER is handed a checked-out worktree it can `cat`/`grep` around in — the
answer key has to be filesystem-hidden from it.

**A reviewer candidate here never gets filesystem access at all.** `reviewer-dogfood.sh`
sends it only the diff TEXT in a chat prompt over the gateway (`charon/<model>`, via
`charon-run.sh`, reused unmodified) — there is no worktree, no checkout, nothing to `cat`.
That is a *strictly stronger* isolation boundary than 0700 perms would add, so this file
is intentionally git-tracked and human-readable (matching every other corpus/registry file
in this repo, e.g. `fleet/reds.tsv`) rather than filesystem-restricted. The ground truth
below never enters any prompt sent to a candidate model — only the harness (grading code,
never shipped to the model) reads it. If a future case ever needs to hand a candidate real
repo/worktree access (e.g. to test whether a reviewer can be tricked into reading its own
answer key), *that* case would need the 0700 treatment for real; none of the cases below
do.

## Grading method

Out-of-band, deterministic, keyword/file-anchored (no second LLM judge in the loop, no
model self-report trusted): a case counts as **CAUGHT** only if the candidate's own review
text names the affected file/area *and* uses language matching the defect's concept-keyword
set below. This is intentionally conservative (a vague "looks fine to me, but double-check
edge cases" does not count as a catch) and intentionally cheap/ungameable (no shared
grading model whose own weights a router could special-case).

## Seed cases (grown every time the reviewer catches — or misses — a new real bug)

```tsv
# id	repo	good_ref	bad_ref	paths	defect_class	keywords
CASE1	product	b8e62d0	b8e62d0^	src/charon/balance.py	concurrency-race	race|concurrent|_save_parked|thread|lock|tmp
CASE2	product	4b5df92	4b5df92^	src/charon/proxy.py	silent-misclassification	list|array|classify|billing|misclassif|coerce
CASE3	rig	c394250	c394250^	fleet/benchmark/preflight.sh	shared-stdin-fd	stdin|fd 0|file descriptor|here-string|<<<|truncat
CASE4	product	91134d7^	91134d7	.github/workflows/ci.yml .github/workflows/heavy.yml .github/workflows/release.yml .github/workflows/windows-exe.yml tools/check_workflows.py	supply-chain-sha-pin	pin|sha|commit hash|mutable|tag|supply chain
```

Column notes: `good_ref`/`bad_ref` are given in **git-diff order** — `git diff <good_ref>
<bad_ref>` always renders as "the change that takes the clean state to the buggy state",
i.e. the actual defect-introducing diff a reviewer must catch, regardless of which ref is
chronologically earlier (CASE4's bug-introducing commit runs *forward*; CASE1-3's bug is
recovered by diffing a fix commit *against its own parent*, since the fix removed the bug
rather than a separate commit having introduced it in isolation). `repo` selects which
local clone the harness runs `git diff` against: `product` = `/home/stack/code/charon`
(default `REVIEWER_PRODUCT_REPO`), `rig` = this repo (`charon-private`) itself — this
script's own worktree already has full history, so no extra clone is needed for CASE3.

### CASE1 — auto-park concurrency race (real, PR #124 pre-fix)

- **Real fix**: `b8e62d044980b0c28a8e4c4f2e77897e116e5b29` "fix(balance): serialize +
  uniquely-name parked-set persist (concurrency BLOCKER)".
- **Ground truth**: `src/charon/balance.py:464` `_save_parked()` released `self._lock`
  *before* writing and reused a single static `"<name>.tmp"` path, so two concurrent
  `park()`/`unpark()` callers race on the same tmp file — the loser's `os.replace` can
  raise `FileNotFoundError` (repro'd 526/1200 calls under 4 threads in the real fix
  commit's own test). `record_exhaustion()` → `park()` is reached from the **money path**
  (`forwarder.py`'s non-200 branch) with no enclosing `try/except`, so the unhandled
  exception tears down the client connection with **no HTTP response** — a silent hang.
- A reviewer that catches this must name the race/lock-ordering problem in
  `_save_parked`/`balance.py`, not just generically flag "looks risky."

### CASE2 — list-body billing-signal blindness (real, #116→#119 regression chain)

- **Real fix**: `4b5df92c089e994697557f8e67f5b8ff2ea68782` "fix(proxy): preserve
  billing-pattern detection for list-shaped error bodies".
- **Ground truth**: `src/charon/proxy.py` `classify()` (~line 396) — PR #116 made a
  non-dict error body crash-safe by coercing ANY non-dict payload (including a genuine
  JSON **list**, e.g. Google AI Studio's array-shaped error responses) straight to `None`.
  That silently threw away billing/exhaustion pattern matching for list bodies: a real 401
  whose list body says "insufficient balance" gets misclassified as a bare auth error
  (no failover triggered) instead of exhaustion. A crash-safety fix regressed a real
  billing-signal path — exactly the kind of "fixed one bug, silently reintroduced another"
  diff a reviewer must catch.

### CASE3 — preflight fd-sharing stdin-drain (real, rig PR #39 follow-up)

- **Real fix**: `c394250d162ac8b1fd3109b7a5f9e4c5c9cc48fc` "fix(preflight): PFR_DEBUG
  instrumentation + two confirmed INVALID-card root causes" (root cause (a)).
- **Ground truth**: `fleet/benchmark/preflight.sh`'s task loop did
  `while IFS=$'\t' read -r ...; do ... done <<< "$rows"` — the here-string binds the
  loop's `read` to **fd 0**, the SAME file description every command run inside the loop
  body inherits. Any inner command that touches stdin (e.g. `charon-run.sh` → `opencode
  run`) drains that shared here-string, so the next iteration's `read` hits EOF and the
  whole battery **silently stops after task #1** — no error, no non-zero exit, just a
  truncated run. The fix moves the read to a private fd (`read ... <&3` / `done 3<<<
  "$rows"`).
- This is deliberately buried inside a larger, real, multi-purpose commit (it also adds
  `PFR_DEBUG` tracing and two unrelated permission fixes) — realistic "find the actual
  defect in a diff that does several things at once," not a single-hunk toy.

### CASE4 — SHA-pin supply-chain regression (real, PR #118 follow-up, self-fixed same session)

- **Bug-introducing commit**: `91134d76feac12a7ea8dad7b3f7377599d2147ca` "fix(gate): wire
  the last orphaned gate (workflow-policy) + prove it stays wired".
- **Real fix**: `e31173e9ac893a431f4d7f2cd85bc037470ea798` "fix(security): restore
  SHA-pins + flip workflow-policy to require them".
- **Ground truth**: wiring `tools/check_workflows.py`'s previously-orphaned gate into CI
  surfaced that all four workflow files pinned first-party GitHub Actions
  (`actions/checkout`, `actions/setup-python`, `actions/upload-artifact`) by full 40-char
  commit SHA — `91134d7` "fixed" the newly-red gate by **unpinning** them down to mutable
  version tags (`@v4`/`@v5`) and flipping the policy to *require* the weaker bare-tag form.
  That makes the gate green while moving supply-chain security backwards (OpenSSF
  Scorecard "Pinned-Dependencies": a tag is attacker-repointable, a commit SHA is not). A
  reviewer must recognize "gate went green" is not the same as "the change is safe" —
  the single hardest class of defect for a reviewer to catch, because the diff's own stated
  goal ("fix the gate") is a plausible-sounding cover story for the regression.

## Clean/known-good diff (false-positive / precision probe)

Fed to every candidate exactly like a red case, but contains **no defect at all** — a
correct reviewer says so. A candidate that invents a "bug" here (any language matching
`bug|vulnerability|race condition|security issue|incorrect|broken|flaw|blocker|reject`)
is a **false positive** and directly hurts its precision score, per the ticket's PART 2
requirement. This diff is embedded literally (not a real git ref) so it never depends on
product/rig repo state:

```diff
DIFF:CLEAN0-START
diff --git a/src/charon/util_format.py b/src/charon/util_format.py
index 1111111..2222222 100644
--- a/src/charon/util_format.py
+++ b/src/charon/util_format.py
@@ -8,6 +8,7 @@ from __future__ import annotations


 def human_bytes(n: float) -> str:
+    """Return ``n`` formatted as a human-readable byte size (e.g. '4.2 KB')."""
     for unit in ("B", "KB", "MB", "GB"):
         if abs(n) < 1024.0:
             return f"{n:3.1f} {unit}"
DIFF:CLEAN0-END
```

## Verdict thresholds (PART 3 — read by `reviewer-dogfood.sh`, never auto-applied)

- **Recall**: a candidate must CATCH every seeded red case (`REVIEWER_RECALL_THRESHOLD`
  default `1.0`) to be reviewer-tier-eligible. The corpus is small and every case is a
  real, previously-shipped miss — at this size, anything less than 100% recall means the
  candidate would have let at least one of these exact regressions through, which is
  disqualifying for the reviewer role specifically (worker tiers can tolerate partial
  scores; the reviewer is the last backstop).
- **Precision**: zero tolerance on the single clean case for now (`REVIEWER_ALLOW_FP`
  default `0`) — grow the clean set before loosening this.
- **A pass here is a RECOMMENDATION only.** `reviewer-dogfood.sh` never merges, never
  edits `fleet/tier-models.tsv`, and never writes `fleet/model-scorecard.tsv` directly (that
  file is bench-grader-owned); it prints a verdict and generates a runnable
  scorecard-append script for a human to run, same convention as
  `fleet/benchmark/dogfood-to-scorecard.sh`. **Favor a multi-model voting PANEL over any
  single passing reviewer**, and keep Claude as the escalation path for high-blast-radius
  / money-path review regardless of how many models pass this replay — this corpus proves
  a candidate can clear a fixed, known set of cases, not that it is safe unsupervised on
  a case it has never seen.

## Growing this corpus

Every time the (eventual) non-Claude reviewer catches a **new** real bug — or misses one
that a human/Claude review then catches — add a row here: id, repo, `good_ref`/`bad_ref`
in git-diff order, `paths`, a `defect_class`, and a concept-keyword set for OOB grading.
Never delete a case; a case that stops being caught by everyone is a regression signal,
not dead weight.
