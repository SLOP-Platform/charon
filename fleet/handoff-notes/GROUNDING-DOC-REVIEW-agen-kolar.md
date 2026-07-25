# ADVERSARIAL REVIEW — `fleet/MANAGER-GROUNDING.md`

Reviewer: sub-session (read-only). Date: 2026-07-24.
**Ref measured: `origin/master` = `ec34714` (fetched during review).**
Local `/home/stack/charon-private` master = `ab74cbc`, **13 behind / 12 ahead** of `origin/master`.
That divergence is the root cause of the two worst findings.

## VERDICT: **SHIP-WITH-FIXES**

Not DO-NOT-SHIP: the highest-consequence operational facts are verified correct — `land.sh`
PR lifecycle, `guard-branch` location, token derivation, the 302 behaviour, gateway host,
the direction of the denied-git-ops rule, and the droid launch command all check out by
execution. But there are **10 factually wrong or materially misleading claims**, three of
which are exactly the failure class the brief hunts: confident, checkable, and wrong.

---

## FINDINGS — ranked by blast radius

### F1 — CRITICAL. The `gate.sh` unbounded fork loop **was fixed and is on master**.
**Wrong text (§12 table row, and §14 bullet 2):**
> `gate.sh:44-50` unbounded fork loop — 78 suites at once on 16 cores → `fork: Resource temporarily unavailable`, non-deterministic results
> *(§14)* "One sub claimed to bound it (landed PR #265); another later found the unbounded loop at `:44-50`. **Both cannot be right.**"

**Correct text:** `origin/master:fleet/gate.sh` implements **bounded** concurrency:
```
56: JOBS="${CHARON_GATE_JOBS:-$(nproc 2>/dev/null || echo 4)}"
57: case "$JOBS" in ''|*[!0-9]*|0) JOBS=4 ;; esac
59: for test_file in "${tests[@]}"; do
63:   while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n || true; done
```
Lines `42-52` are the comment block *documenting* the fix ("BOUNDED CONCURRENCY (RIG-REDS
2026-07-24). This loop used to launch ALL of the fleet's test files at once…").

**Both subs WERE right — about different refs.** `:44-50` is unbounded on the *stale local
checkout* (`ab74cbc`); it is bounded on `origin/master`. §14 presents this as an unresolvable
contradiction; it resolves in 30 seconds with `git fetch`.

**Blast radius:** a new manager inherits (a) a false live hazard ("the gate can fork-starve
this box"), (b) distrust of every gate count, (c) a standing invitation to re-fix a landed
fix. It also directly contradicts the doc's own §13.2 rule.

---

### F2 — CRITICAL (method). The doc never states which ref its line cites were measured against.
The doc's own §13.2 ("'X does not exist' is only true if you checked the right ref") and
§13.12 ("state which ref you measured") are violated by the doc itself. Every `file:line`
in §5/§6/§7/§12 was measured on a checkout 13 commits behind `origin/master`, and the
doc presents them as current-on-master. This produced F1, F8 and F9.

**Fix:** add a provenance line at the top — "line cites measured against `origin/master`
@ `<sha>` on `<date>`" — and add a `git fetch && git rev-list --left-right --count
master...origin/master` step to §2.

---

### F3 — HIGH (data-loss risk). Two of the three "pushed, unlanded" branches are **NOT pushed**.
**Wrong text (§16 footer):**
> **Not yet on master (pushed, unlanded):** `fleet/board-lock.sh` (`fix/board-write-lock`), `LAND_RIG_TESTS` (`fix/land-gate-rig-suite`), the droid PATH/token/push-mode fixes (`fix/DROID-CLIENT-PREFLIGHT-PATH`).

**Measured:**
| branch | local | `origin` | `gitea` |
|---|---|---|---|
| `fix/DROID-CLIENT-PREFLIGHT-PATH` | `8f0a4e5` | `8f0a4e5` ✅ pushed | — |
| `fix/land-gate-rig-suite` | `506caa1` | **NOT PUSHED** | not present |
| `fix/board-write-lock` | `6ef1fb1` | **NOT PUSHED** | not present |

`fleet/board-lock.sh` exists only on the local `fix/board-write-lock` blob; it is absent
from `origin/master`. §5 repeats the same error ("A fix exists unlanded on
`fix/land-gate-rig-suite`" — implying it is retrievable).

**Correct text:** "`fix/DROID-CLIENT-PREFLIGHT-PATH` @ `8f0a4e5` is pushed to `origin`.
`fix/land-gate-rig-suite` @ `506caa1` and `fix/board-write-lock` @ `6ef1fb1` exist **only in
the local rig checkout** — push them before any branch-reaper, `git clean`, or worktree prune
runs."

**Blast radius:** a manager who believes these are remote-safe can permanently lose two
completed fixes. This is the single most dangerous finding operationally.

---

### F4 — HIGH (wrong path, silent empty result). SLOP ticket DB path is wrong.
**Wrong text (§3 SLOP):**
> Its tickets live in `/home/stack/code/mediastack/tracking.db` (SQLite).

**Measured:** `/home/stack/code/mediastack/tracking.db` is **0 bytes** (mtime Jun 15).
The populated DB is `/home/stack/code/mediastack/tracking/tracking.db`. (`query.py` is not
at the mediastack root either.)

**Blast radius:** a manager queries the named file, gets a valid-but-empty SQLite handle,
and concludes SLOP has no tickets — the doc's own §13.6 defect ("Empty ≠ error") reproduced
by the doc.

---

### F5 — HIGH (wastes a session). "Sub-sessions are NOT bound" is unverified and probably false for Task sub-agents.
**Wrong/ambiguous text (§5):**
> **Sub-sessions are NOT bound by all of these** — delegate a rebase to a sub.

The deny rules live in `/home/stack/code/charon/.claude/settings.local.json` and are
**session-scoped**, so an in-session Task sub-agent inherits them. What is genuinely
unbound is a **droid tab the operator opens in a rig worktree**
(`/home/stack/charon-private-wt/<NAME>`), which is outside that project's settings scope.
`MANAGER-OPERATING-RULES.md:87` states the ops "are all deny-listed — do NOT reach for
them; they will be denied" with no sub-agent exemption → **direct contradiction**.

**Correct text:** "A Task sub-agent in this session inherits the same deny-list. Only an
operator-opened droid tab running in a rig worktree escapes it — and even then, prefer
`land.sh` / `land-push.sh`."
*I did not execute a denied command to prove this (it would hang on a permission prompt);
flagged as UNVERIFIED-AND-CONTRADICTED, which is itself a reason not to state it flatly.*

---

### F6 — MEDIUM-HIGH. The DENIED list is real but **project-scoped**, and is incomplete.
**§5 list is directionally correct** — `git push*`, `git -C * push*`, `git merge*`,
`git -C * merge*`, `git rebase*`, `git reset --hard*`, `git remote add*`, `git config user.*`,
`git config --global*`, `git push --force*`/`-f*`, `git commit --no-verify*` are all
genuinely denied.

Two problems:
1. **Scope not stated.** Those rules are in `/home/stack/code/charon/.claude/settings.local.json`.
   `/home/stack/charon-private` has **no `.claude/` directory**, and
   `/home/stack/.claude/settings.json` has an **empty deny list**. The guardrail therefore
   depends on the session's project scope — the doc presents it as unconditional. A manager
   who assumes "git push will be blocked" is relying on a scope the doc never names.
2. **Omissions, some safety-relevant:** `git commit --amend*`, `git clean -f*` / `-fd*`,
   `git checkout main*` / `git switch main*`, `git remote set-url*`, `sudo *`, `su *`,
   `systemctl *`, `apt*`, `docker *`, `rm -rf …/charon/.git*`. Omitting `sudo` matters
   because §4 tells the manager the operator must run `sudo -u bench-grader …` without
   saying the manager *cannot* run sudo at all.

---

### F7 — MEDIUM. "33 never-run test files" is wrong by >2×.
**Wrong text (§12):** "**33 never-run test files** — Named `test_*.sh` … 7 guard money/security/data-loss"
**Measured on `origin/master`:** **15** `test_*.sh` files repo-wide — 12 in `fleet/tests/`,
3 in `fleet/benchmark/selftest/`. Only the 12 under `fleet/tests/` sit in gate.sh's scan
directory. (83 `*.test.sh` files exist and DO run.)
The underlying claim is sound — `gate.sh:33` globs `"$TESTS_DIR"/*.test.sh`, so `test_*.sh`
is never matched — but the count and therefore the "7 of them guard money/security" subset
must be re-derived.

---

### F8 — MEDIUM. `preflight.sh` line count is stale.
**Wrong text (§12):** "906 lines, 8 inline gates, 6 owners"
**Measured:** `origin/master:fleet/preflight.sh` = **968 lines**. The **8 gates is correct** —
`board_gate:269`, `executor_gate:304`, `coverage_gate:340`, `handoff_gate:382`,
`done_merge_gate:484`, `hold_reason_gate:543`, `graphify_freshness_gate:851`,
`startup_budget_gate:921`. Same stale-ref cause as F1.

---

### F9 — LOW-MEDIUM. `LAND_RIG_TESTS` line cite is off by one.
**Wrong text (§5):** "flip `LAND_RIG_TESTS` at `land.sh:320`"
**Correct:** on `fix/land-gate-rig-suite` it is **`fleet/land.sh:321`**
(`if [ "${LAND_RIG_TESTS:-0}" = "1" ] && [ -f "$REPO/fleet/gate.sh" ]; then`).
On master, `land.sh:320` is `else`. The doc does correctly say the fix is unlanded; only the
line is wrong — but `handoff-check.sh` demands behavioural claims cite a *real* `file:line`,
so the doc fails its own gate here.

---

### F10 — LOW. "~38 P0s" → actual **35** `priority: 0` tickets of 117 board files. Directionally fine.

### F11 — LOW. "~21 branches built and pushed but unmerged" is not reproducible as stated.
189 remote branches are unmerged into `origin/master`. Per the doc's own §13.1, branch counts
are not evidence of liveness. The claim needs the "prove by CONTENT" caveat attached, or a
named method.

---

## VERIFIED CORRECT — do not re-audit these
Confirmed by execution against `origin/master` / live hosts:
- **`land.sh:395` create · `:399` ready · `:404` merge** — exact, on both refs. §5's
  "an old handoff claimed otherwise; that is false" is itself correct.
- **`land.sh:341-342`** — exact: `git add "${LAND_STAGE[@]}" && git commit -q -m "${MSG:-…}"`.
  Pathspec-less commit ⇒ takes the whole index. The §5 warning is accurate.
- **`work-lease.sh:408` (`guard-branch)` dispatch) + `fleet-droid.sh:619` wiring** — exact on
  `origin/master`. **PR #267 is genuinely MERGED** (`2026-07-25T05:52:54Z`, head
  `feat/branch-ticket-map-gate`). The doc is RIGHT and
  **`BRIEF-PREAMBLE.md:42-45` is now STALE** — it still says `guard-branch` is *not* on master
  and cites `fleet-droid.sh:375`. **Contradiction resolved in the grounding doc's favour;
  fix the preamble, not the doc.**
- **`env-registry.sh:54-56`** STALE-token comment — exact. **`availability.py:197`** prefers
  the stale var — exact (`GATEWAY_TOKEN_ENVS = ("CHARON_GATEWAY_TOKEN", …)` at `:50`, first
  non-empty wins). The "set-if-unset is a no-op" warning is correct.
- **Gateway `http://10.0.1.60:8080/charon/status` → HTTP 302** unauthenticated — verified live.
  **Gitea `http://10.0.1.52:3000` → 200** — verified live.
- **Remotes** — rig `origin=https://github.com/Nnyan/charon-private.git`,
  `gitea=http://10.0.1.52:3000/stack/charon-private.git`; product
  `origin=git@github.com:SLOP-Platform/charon.git`. All exact.
- **`--push` / `--push-only` at `fleet-droid.sh:558-559`** on `fix/DROID-CLIENT-PREFLIGHT-PATH`
  @ `8f0a4e5`; **zero hits on master**. Exact, including the SHA.
- **§7 launch command runs as written.** `fleet-droid.sh <tier> --wait <min> --retries <n>`
  parses at `:443-444`; tier allowlist accepts `frontier|strong|economy`. The probe
  `CLAIM_ONLY=<id> bash fleet/claim.sh --dry-run <tier> probe own-only` matches
  `claim.sh [--dry-run] <tier> <droid> [both|own-only]` with `CLAIM_ONLY` honoured at
  `claim.sh:23,27`; `POOL-PAUSED` halt at `claim.sh:18`.
- **`autonomous.sh status`** is a valid subcommand. Note: **`fleet/state/AUTONOMOUS` EXISTS
  right now ⇒ the lever is ON**, so a new manager may push without asking.
- All 26 §16 tool paths, all 5 named directories, `/home/stack/code/charon/tools/hooks/pre-commit`,
  and `~/.local/bin/graphify` exist.

---

## §14 HONESTY ASSESSMENT — honest in tone, but **understates**

§14 is unusually candid and its listed gaps are real. It nonetheless omits five things
confidently asserted elsewhere that belong in it:

1. **Ref-staleness of every line cite** (F2). §14 never says "I measured against a checkout
   that may be behind origin". This is the doc's largest systematic risk and is invisible.
2. **The `gate.sh` bullet is framed as unresolvable** ("Both cannot be right") when it is
   resolvable in one command (F1). Presenting a solvable question as a mystery discourages
   the next manager from solving it.
3. **Push-state of the "unlanded" branches** (F3). §16 asserts "pushed" flatly; §14 does not
   qualify it.
4. **SLOP.** §14 says "I know it is `/home/stack/code/mediastack` with `tracking.db`" — the
   one SLOP fact it claims certainty about is the wrong path (F4).
5. **The deny-list scope + the sub-agent exemption** (F5/F6) are asserted in §5 with no
   hedge and appear nowhere in §14, despite being untested.

---

## MISSING — a fresh manager would be stuck or unsafe without these

| Missing | Why it matters |
|---|---|
| **`git fetch` + divergence check as §2 step 1** | The rig checkout is 13 behind / 12 ahead of `origin/master` *right now*. This is the root cause of F1/F8/F9 and will re-victimise the next manager on day one. **Highest-value single addition.** |
| **`gh auth status`** | §2 checks `gh api rate_limit` but never that `gh` is authenticated at all. `land.sh` is entirely `gh`-driven (`:395/399/404`); an auth failure surfaces as a confusing partial land. |
| **Which repo cwd a manager session starts in** | Determines whether the deny-list applies at all (F6). Undefined behaviour on a guardrail is worse than no guardrail. |
| **`land.sh` exit-code map** | Only `rc=8` is documented. `rc=4` (gate red) and `rc=6` (owner/repo unresolved) both exist in the script and both look like generic failure. |
| **How to push a local-only branch safely** | Given F3, the doc should name `land-push.sh <branch> <repo>` as the rescue path for the two unpushed branches, explicitly. |

---

## RECOMMENDED MINIMUM EDIT SET BEFORE SHIPPING
1. Rewrite the §12 `gate.sh` row and the §14 bullet — the loop **is bounded on `origin/master`**
   (`gate.sh:56-63`); re-scope the row to "verify on your own fetched ref". *(F1)*
2. Correct §16 + §5: only `fix/DROID-CLIENT-PREFLIGHT-PATH` is pushed; the other two are
   local-only and at risk. *(F3)*
3. Fix the SLOP path to `/home/stack/code/mediastack/tracking/tracking.db`. *(F4)*
4. Replace the §5 sub-session exemption sentence; state the deny-list's project scope and
   add the omitted denied ops (`sudo`, `git clean -f`, `git commit --amend`, `git checkout main`). *(F5/F6)*
5. Add a ref-provenance line at the top and `git fetch` + divergence check as §2 step 1. *(F2)*
6. Correct counts: 15 `test_*.sh`, 968-line `preflight.sh` (8 gates is right),
   `land.sh:321` for `LAND_RIG_TESTS`, 35 P0s. *(F7/F8/F9/F10)*
7. Note in §6 that `BRIEF-PREAMBLE.md:42-45` is stale on `guard-branch` — the grounding doc
   is the correct one; the preamble needs the fix.
