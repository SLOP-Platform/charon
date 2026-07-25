# DROID-SESSION-FAILURE — root cause (read-only diagnosis)

Reviewer: agen-kolar · 2026-07-24 · **nothing modified**

## 1. The exact error (verbatim, from the real session log)

`/home/stack/charon-private/fleet/state/agent-logs/strong-3436392-LENS-REGISTRY-AND-REPORT.txt`
(identical text in `strong-3436392-DROID-BRIDGE-REGISTER.txt` and `strong-3436392-FORGE-PRIMARY-GITEA.txt`):

```
[charon-run] STARTED on charon/minimax-m3-free (failover chain: charon/minimax-m3-free,deepseek-v4-flash,glm-5.2,gpt-5.4-mini; ...)
===== [charon-run] attempt: charon/minimax-m3-free @ LENS-REGISTRY-AND-REPORT =====
timeout: failed to run command ‘opencode’: No such file or directory
[charon-run] model 'minimax-m3-free' exited nonzero (rc=127, not a limit, not an infra fault) -> failing over
  ... same 3 more times (deepseek-v4-flash, glm-5.2, gpt-5.4-mini) ...
[charon-run] ALL MODELS EXHAUSTED: minimax-m3-free deepseek-v4-flash glm-5.2 gpt-5.4-mini
CHARON_RUN_RESULT=EXHAUSTED
```

Corroborated in `/home/stack/charon-private/fleet/provider-exhaustion-ledger.tsv` (12 rows at
`2026-07-25T05:14–05:15Z`, all `rc=127`, then `ALL-EXHAUSTED / POOL TOO THIN`).

Each log is 1.3 KB and each of the three sessions lasted **under one second** — the whole 4-model
chain burned before a single byte of HTTP was sent.

## 2. Root cause

`rc=127` = **command not found**. The work client `opencode` was not on `$PATH` in the launcher's
process environment.

- The binary is present and healthy: `/home/stack/.local/bin/opencode` →
  `/home/stack/.local/lib/node_modules/opencode-ai/bin/opencode.exe`, ELF 64-bit x86-64,
  `opencode --version` → `1.18.2`. Not dangling, not corrupt, not a Windows binary.
- `$HOME/.local/bin` is added to `PATH` **only** by `/home/stack/.bashrc:118` and
  `/home/stack/.profile:25-26` — i.e. only for an **interactive or login** shell.
- `fleet/fleet-droid.sh` and `fleet/charon-run.sh` never set, export, or validate `PATH`, and never
  preflight the client's existence. `charon-run.sh:114` calls bare `opencode` via
  `timeout … opencode run --model charon/$M`.

**Reproduced byte-for-byte:**

```
$ env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/home/stack \
    /usr/bin/timeout 5 opencode --version
/usr/bin/timeout: failed to run command ‘opencode’: No such file or directory   # rc=127
```

So this run's `fleet-droid.sh` was started from a shell that sourced neither `.bashrc` nor
`.profile` (a non-interactive, non-login shell — e.g. `setsid`/`nohup`/`sh -c`/a detached wrapper,
or a tool-invoked shell). Earlier droids **today** (09:xx and 13:55, large healthy logs in the same
`agent-logs/` dir) ran fine from a normal tab, which is why this looks new: it is an environment
property of *how this tab was launched*, not a code change (last touch to either script predates
today's successes).

## 3. Candidates ruled OUT by evidence

| Candidate | Verdict | Evidence |
|---|---|---|
| Gateway / auth (401, missing bearer token) | **NOT the cause** | Zero HTTP attempted. `opencode` never executed, so no request reached `http://10.0.1.60:8080`. A token problem cannot produce `rc=127` from `timeout`. |
| Pool exhaustion | **Symptom, not cause** | The `ALL-EXHAUSTED / POOL TOO THIN` ledger rows are `charon-run.sh:204-207` firing *after* four `rc=127` legs. Providers were never contacted. |
| Client failure (`opencode` missing/broken) | **CONFIRMED — this is it** | Binary healthy, but absent from the launcher's `PATH`. |
| Ticket-side (new tickets, bad field, missing dep, bad `owns`) | **NOT the cause** | All three passed the parallelizability gate, the detention filter, and `repo_resolve`; the launcher created the worktree and wrote the brief (`state/agent-briefs/strong-3436392-*.md`, 6.8–15 KB) before the client was invoked. Failure is downstream of every ticket-dependent step, and identical across three unrelated tickets. |
| `INERT-INSTANCE-DETECT` refusal | **Not a fault** | Correct `state/needs-push/` guard behaviour. Excluded from this report per brief. |

## 4. Blast radius

**ALL droid work, not just these three.** Any `fleet-droid.sh` tab launched from a non-login,
non-interactive shell fails every ticket it claims, instantly, at any tier — the client is
tier-independent. The three tickets are innocent; a `--only` retry from the same shell would fail
identically. Conversely, a tab launched from a normal interactive terminal works today.

**No data loss.** Branches were deleted by `leak-guard.sh:270` only because they had zero unique
commits (`git branch -d` then `-D`, the safe recreate-from-base path); `was 128605a` is the base
commit. Worktrees were cleanly reaped. The three tickets are quarantined by `loop-guard.sh`, which
is correct behaviour given two consecutive hard failures.

## 5. Secondary damage — scorecard ledger poisoning (separate, real)

`charon-run.sh:187-191` treats `rc=127` as *"genuine model-attributable result"* and calls
`cap "$M" "FAIL" "BLOCK" "fail" …`, enqueueing a **scorecard BLOCK** into the bench-grader spool.

`is_infra_fault()` (`charon-run.sh:48-65`) covers rc=3, 5xx, resets, deadlines, db-locks — but
**not rc=127**. A missing local binary is the purest possible infra fault and it is being charged to
the model.

This run therefore enqueued up to **12 false BLOCK verdicts** (4 models × 3 tickets) against
`minimax-m3-free`, `deepseek-v4-flash`, `glm-5.2`, `gpt-5.4-mini`. The ledger rows in
`provider-exhaustion-ledger.tsv` also read `error-failover … genuine model-attributable result`.
`/var/lib/bench-grader/spool/req/` is grader-owned and not readable from this account, so the exact
count is unconfirmed — the operator should check it before trusting any grade for those four models
dated `2026-07-25T05:14–05:15Z`.

## 6. Minimal fix

Three lines, no redesign. Preferred order:

1. **Make the client resolvable regardless of shell type.** In `fleet/charon-run.sh`, after
   `SCRIPT_DIR=…` (line 10), add:
   `export PATH="$HOME/.local/bin:$PATH"` — or honour an explicit
   `OPENCODE_BIN="${OPENCODE_BIN:-opencode}"` and invoke `"$OPENCODE_BIN"` at line 114.

2. **Fail fast and loud instead of burning the chain.** Before the `for M in …` loop (line 95):
   `command -v opencode >/dev/null || { echo "[charon-run] FATAL: work client 'opencode' not on PATH" | tee -a "$OUT" >&2; exit 4; }`
   One clear message beats four silent `rc=127` legs and a bogus `POOL TOO THIN`.

3. **Stop charging infra faults to models.** Add `[ "$rc" -eq 127 ] && return 0` to
   `is_infra_fault()` (`charon-run.sh:60`, next to the existing rc=3 line) so a missing client
   never enqueues a scorecard BLOCK.

Immediate unblock with zero code change: relaunch the tab from an interactive terminal, or prefix
the command —
`PATH="$HOME/.local/bin:$PATH" bash /home/stack/charon-private/fleet/fleet-droid.sh strong --wait 3 --retries 10`
— then clear the three loop-guard quarantines under `fleet/state/loop-guard/`.

## 7. What the operator must supply

**Nothing.** No credential, token, API key, or env var is missing. This is not the gateway-401 class
other subs hit today — the gateway was never contacted. The only operator actions are (a) launch
from a shell that has `~/.local/bin` on `PATH` (or land fix #1), (b) clear the three loop-guard
quarantine markers, and (c) audit the bench-grader spool for the false BLOCKs in §5.
