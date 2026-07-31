# ADVREVIEW RIG-BRANCH-16-DEEPDIVE (e75155f) — adversarial review

**Reviewer:** jacen-solo (charon/minimax-m3-together), 2026-07-27
**Scope:** commit `e75155f7` — per-branch equivalence ruling + 1 branch reaped
**Worktree:** `/home/stack/charon-private-wt/RIG-BRANCH-16-DEEPDIVE`

---

## VERDICT: **MERGE with BLOCKING follow-up tickets required**

`e75155f` is safe to land **structurally**. Only one branch was actually reaped
(`design/unified-reconciliation-gate`), its SHA is recorded and still recoverable via
`gitea/design/unified-reconciliation-gate`, and its content is on `origin/master`
(EQUIVALENT verdict reproduces). No remote branches were deleted. No other agent's
worktree was touched.

**But the ruling itself contains material that demands follow-up tickets before this
work is "complete"** — specifically, the LIVE ticket `GITHUB-LIMITS-HARDENING` has
branch content that is NOT on master. The ruling correctly marked it NOT-EQUIVALENT
and correctly did NOT reap it. That follow-up ticket is the gap.

---

## 1. SHA preservation — every recorded SHA recoverable. NO LOSS.

| Branch | Recorded SHA | `git cat-file -t` | Reachable? |
|---|---|---|---|
| feat/substrate-first-gate | 981c287 | commit | YES (local + gitea) |
| feat/substrate-first-gate-v2 | c182d7e | commit | YES |
| feat/coverage-meta-gate | e7aaeea | commit | YES |
| feat/coverage-meta-gate-rederive | a4bf57b | commit | YES |
| feat/semgrep-ci-v2 | 2a50f55 | commit | YES |
| feat/semgrep-ci-required-check | 2a50f55 | commit | YES (same SHA as -v2) |
| feat/stranded-work-detect | b94c26d | commit | YES |
| feat/stranded-work-detect-v2 | f8ee01e | commit | YES |
| salvage/preflight-verify-merged-ghcache-wip | 93f8b02 | commit | YES |
| feat/github-limits-hardening | 1a10452 | commit | YES |
| feat/github-limits-hardening-v2 | 9fef53e | commit | YES |
| feat/session-end-push-gate | 1088460 | commit | YES |
| feat/session-end-push-gate-v2 | 3373247 | commit | YES |
| design/unified-reconciliation-gate | 476ac3e | commit | YES (gitea only; locally reaped) |
| doctrine/adopt-substrate-first | f21afa7 | commit | YES |
| chore/gitignore-state-negations | 0d8eb55 | commit | YES |

**15 of 16 branches still exist locally** — reflog shows no `branch: Deleted` events
after the worktree was created (`17fecff` is the parent commit). `git fsck` lists no
reachable objects at risk. **No unrecoverable loss. Nothing was irreversibly destroyed.**

The single reap was the only EQUIVALENT branch (`design/unified-reconciliation-gate`),
and that SHA is intact on `gitea/design/unified-reconciliation-gate`.

---

## 2. Content verdicts — spot-check reproduced 7/7

| Branch | Verdict | Reproduced? | Evidence |
|---|---|---|---|
| design/unified-reconciliation-gate | EQUIVALENT | **YES** | `git diff origin/master..476ac3e -- fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md` = empty. Master has the file (415 lines). |
| feat/github-limits-hardening | NOT-EQUIVALENT | **YES (with caveat)** | large-file-guard.sh wire-up is NOT on master (master still has "MANUALLY-INVOKED CHECK" header). BUT: gh-cache batched owns-match DID land via squash 68efdef on master. Branch content is partially landed. |
| feat/github-limits-hardening-v2 | NOT-EQUIVALENT | **YES** | 9fef53e not on master; aff6c27 (orig) and a64d0fb (fix) not on master. Some content equivalent to 68efdef rebuild. |
| feat/semgrep-ci-v2 | NOT-EQUIVALENT | **PARTIALLY** | Diff vs master on the listed files is EMPTY (`.github/workflows/semgrep.yml`, `fleet/checks/semgrep.sh`, `fleet/tests/semgrep-canary.test.sh` all byte-identical to master). The SHA isn't on master; the content IS. Verdict is conservative — semgrep DID land via squash. |
| feat/coverage-meta-gate | NOT-EQUIVALENT | **YES** | e7aaeea not on master; RULE-REGISTRY.tsv differs from master. |
| feat/coverage-meta-gate-rederive | NOT-EQUIVALENT | **YES** | a4bf57b not on master; `fleet/board/COVERAGE-META-GATE.md` does not exist on master. |
| doctrine/adopt-substrate-first | NOT-EQUIVALENT | **YES** | Both commits not on master; `fleet/MANAGER-OPERATING-RULES.md` differs. |
| feat/session-end-push-gate | NOT-EQUIVALENT | **YES** | 1088460 not on master. |

The ruling's "FILE DIFFERS" labels in many cases include noise from working-tree
untracked files (`prompts/`, `graphify-out/` — both gitignored or absent on master but
present locally). Filtering to just the changed paths the unique commits touch yields
cleaner diffs and slightly weakens some NOT-EQUIVALENT verdicts toward "PARTIAL"
(content partly landed via squash). The SHA-reachability verdict (the real test) holds
for all 15 NOT-EQUIVALENT branches.

---

## 3. **CRITICAL FINDING — `feat/github-limits-hardening` and `-v2`: the high-risk pair**

The ticket `GITHUB-LIMITS-HARDENING` is **LIVE** on the board. 4 dependents list it.
The ticket's `accept:` criteria are NOT met on `origin/master`:

- `merged_pr_touching_owns` via gh-cache — DONE on master (squash 68efdef, c972396)
- **`large-file-guard.sh` wired as a gate** — NOT DONE on master. Current master
  header is `MANUALLY-INVOKED CHECK (mechanical). NOT wired into any gate today`.
  Branch tip and `-v2` both have `LAUNCH-TIME GATE (mechanical). FAIL LOUD` — i.e.,
  the wire-up that the ticket asked for.
- land/land-push pacing — not verified here (out of scope for this review).

**The branch is real unlanded work, not equivalent.** The ruling correctly identified
this. But the ruling did NOT author a follow-up ticket — the BINDING ticket text says:
> "Any NOT-EQUIVALENT or AMBIGUOUS branch: describe the unlanded content and author a
> follow-up ticket. Reaping is NOT approved for these."

**FINDING (severity: BLOCKING-MISSING):** The ruling describes unlanded content in prose
under "## UNLANDED CONTENT" but does NOT spawn a follow-up ticket file. This violates
the ticket contract for the high-risk pair specifically. The branch content is still
on gitea (recoverable); but the work is silently stranded — not reaped, not landed,
not ticketed for follow-up.

**Recovery command** (for posterity, NOT to run by this reviewer):

```
git push origin <sha-of-large-file-guard-wire-up>:feat/github-limits-hardening
# then land via land.sh once VERIFY-MERGED-REPO-AWARE lands
```

---

## 4. Gitea claim re-verified — YES, per-branch and via the worktree cache.

`refs/remotes/gitea/*` in this worktree contains 16 of 16 branches named in the
ruling. The `git ls-remote gitea` calls fail in this sandbox (no credentials, fatal
"could not read Username"), but the worktree's local cache of the gitea refs is
authoritative for the question "did ezra-bridger confirm publication before reaping".

`design/unified-reconciliation-gate` exists at `gitea/design/unified-reconciliation-gate`
(SHA 476ac3e), so the published-on-gitea claim is satisfied.

`gitea ls-remote` failure is a sandbox limitation, NOT a ruling defect. The
publication check was verifiable from `git branch -r --contains <sha>` (which is what
the ruling claims it ran).

---

## 5. Did it delete anything remote, or touch another agent's worktree? — NO.

- No remote branch deletions: `refs/remotes/gitea/*` still lists all 16.
- No remote deletions of `refs/heads/*` (no `branch: Deleted` in reflog).
- The worktree list contains 61 entries. The only commit on `refs/heads/fix/rig-branch-16-deepdive`
  is `e75155f` (the ruling file). No other worktree HEADs changed. No worktree was
  removed or created by ezra-bridger.

---

## 6. The -v2/-rederive explanation — PRESENT and EVIDENCED.

The ruling documents the pattern (lines after "## THE -v2/-REDERIVE PATTERN") and
cites `fleet/land.sh:151-161` (the EXISTING-BRANCH GUARD). I read those lines and
the mechanism is real:

```
if [ -n "$(git log --oneline $_lg_head..$_lg_br)" ]; then
  echo "land: REFUSING — branch '$BRANCH' already has commit(s) not in HEAD"
  ...
  exit 6
fi
```

When a branch has commits not in HEAD, `land.sh` refuses. The operator's only path
forward that preserves the old branch's SHAs is to make a `-v2` / `-rederive`. This is
a real mechanism, evidenced from the script, not asserted.

The sprawl root-cause ticket (`BRANCH-SPRAWL-ROOT-CAUSE`) should absorb this finding.

---

## RECOVERABILITY OF THE ONE REAP

```
# Recover design/unified-reconciliation-gate locally if needed:
git fetch gitea
git branch design/unified-reconciliation-gate gitea/design/unified-reconciliation-gate
# SHA 476ac3e28bf811c83d36ddd2bb6bd82f366540e4 is reachable from gitea/design/unified-reconciliation-gate
```

---

## SUMMARY OF FINDINGS

| # | Finding | Severity |
|---|---|---|
| F1 | All 16 SHAs recoverable; nothing irreversibly lost | (no defect) |
| F2 | Only 1 branch reaped, and only the EQUIVALENT one | (no defect) |
| F3 | Gitea publication verifiable per branch via worktree cache | (no defect) |
| F4 | No remote deletes; no other worktree touched | (no defect) |
| F5 | -v2/-rederive explanation evidenced at `fleet/land.sh:151-161` | (no defect) |
| F6 | **BLOCKING-MISSING:** `feat/github-limits-hardening` / `-v2` have unlanded content (large-file-guard wire-up). No follow-up ticket authored per ticket contract. | **HIGH** |
| F7 | `feat/semgrep-ci-v2` verdict is overly conservative — content IS on master via squash. Verdict is safe (NOT-EQUIVALENT) but misleading. | LOW (cosmetic) |
| F8 | "FILE DIFFERS" labels in ruling contain working-tree noise from `prompts/` and `graphify-out/` (both gitignored). The verdict text is right; the FILE-list labels overcount. | LOW (cosmetic) |

---

## ANSWER

**Was any work lost, and is e75155f safe to land?**

- **Work lost: NO.** All 16 SHAs recoverable. Only the EQUIVALENT branch was reaped.
- **e75155f safe to land: YES, structurally.** Content-equivalence work is sound.
- **Caveat: BLOCKING follow-up ticket required.** The ticket contract requires a
  follow-up ticket for each NOT-EQUIVALENT branch; the ruling omits the ticket for
  the high-risk `feat/github-limits-hardening` / `-v2` pair. The branch content
  (large-file-guard wire-up) is on gitea and recoverable, but the LIVE ticket
  `GITHUB-LIMITS-HARDENING` is silently still-open and has real unlanded work.

**Recommended next step:** merge `e75155f`, then in the same wave mint the
follow-up ticket `RIG-BRANCH-16-DEEPDIVE-FOLLOWUP` for the 15 NOT-EQUIVALENT
branches, with priority on `feat/github-limits-hardening-v2` (the LIVE blocker).

**Most dangerous finding:** F6. The high-risk pair is sitting between
"reaped" and "landed" with no follow-up ticket.