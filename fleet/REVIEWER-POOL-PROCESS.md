# REVIEWER-POOL-PROCESS

## 1. What a reviewer tab is

A reviewer tab is a **watchable headless process** — a Windows Terminal tab running `bash review-pool.sh` in a loop. It is NOT a TUI session (no port, no interactive prompt), and it does NOT register with session-bridge. Its entire state is on disk: `fleet/state/review-queue.tsv`, `fleet/state/review-claims/`, `fleet/state/review-done/`, and `docs/review-log/*.md`.

## 2. How to launch one

```bash
# One tab per machine, strong tier (adversarial code review)
bash fleet/reviewer-tab.sh

# Override tier, color, or retry policy
bash fleet/reviewer-tab.sh --tier strong --color "#f59e0b" --wait 5 --retries 10
```

The `reviewer-tab.sh` wrapper runs the preflight contract (see §3), derives the model chain from `fleet/tier-models.tsv`, and calls `spawn-tab.sh` to open the physical WT tab.

## 3. The headless decision (operator, 2026-08-01)

**Decision: reviewer pools stay HEADLESS. Do NOT use `spawn-worker.sh` or session-bridge registration.**

Rationale: a reviewer has no TUI, no port, and no live conversation to hold — its entire state is on disk and greppable. Registering it with session-bridge would add liveness overhead with zero observable benefit: the session-bridge heartbeat reports "alive and working", but the 2026-08-01 outage showed the pool can be *alive and working and writing false verdicts*. The heartbeat would have reported the same status during both failures because the pool genuinely was alive and genuinely was writing BOUNCE verdicts.

**Counter-argument (recorded, not adopted):** A session-bridge heartbeat would have surfaced the tab was running (vs a crashed tab, which is silent) and the pool was cycling (vs an empty queue, which is also "no claimable review items"). The honest answer is both failures were detectable *earlier* with liveness, but the failure mode was not "tab dead" — it was "tab alive but producing garbage verdicts". Liveness would have reported green when it was green; the problem was green was wrong.

**Remediation:** fail-loud preflight, not liveness reporting.

## 4. The preflight contract

`reviewer-tab.sh` refuses to start (exit 4) when any of these is true:

| Check | Why |
|---|---|
| `git`, `gh`, `python3`, `timeout`, `curl` missing | `review-pool.sh` needs all of them |
| `gh auth status` fails | `gh pr list/diff` is the lane for every PR operation |
| Gateway token cannot be derived from opencode.json | The whole review chain needs the gateway |
| `/v1/models` returns empty or unparseable JSON | review-pool.sh hard-loops "no claimable review items" when models are absent |

The model chain is read from `fleet/tier-models.tsv` (via `tier_chain()`) — never a hardcoded literal. `review-pool.sh` defaults `CHARON_REVIEW_MODELS=deepseek-v3,deepseek-r1`, neither of which exists in the gateway's ~2580 models; `reviewer-tab.sh` overrides this with `CHARON_REVIEW_MODELS` set to the tier's chain.

## 5. Fault classes fixed

### Fault 1: non-login shell loses ~/.local/bin
`wt.exe bash <script>` runs a NON-login shell. `~/.profile` and `~/.bashrc` are not sourced, so `~/.local/bin` is absent. Both `gh` and `opencode` live in `~/.local/bin` and silently vanish → `review-pool.sh` loops "no claimable review items" (because `gh pr list` exited 127) and writes BOUNCE verdicts on every cycle.

Identical fault class to:
- `fleet-droid.sh:21-32` (fixed 2026-07-24)
- `charon-run.sh:28-31` (fixed 2026-07-24)
- `spawn-worker.sh:178-180` (opencode resolver)

Fix: `spawn-tab.sh` appends `~/.local/bin` to PATH inside the tab script before running the command.

### Fault 2: hardcoded wrong model ids
`review-pool.sh:36` defaults `CHARON_REVIEW_MODELS=deepseek-v3,deepseek-r1`. Neither id exists among the gateway's ~2580 models, so every review failed over the whole chain and wrote fail-closed BOUNCE that reads like a code verdict.

Fix: `reviewer-tab.sh` derives the chain from `fleet/tier-models.tsv` via `tier_chain()` and exports `CHARON_REVIEW_MODELS`.

## 6. How to verify a reviewer tab is working

```bash
# Check the queue is populated
bash fleet/review-pool.sh status

# Watch the claim dir for activity
ls -lt fleet/state/review-claims/ | head

# Watch the review log dir for new verdicts
ls -lt docs/review-log/*.md | head

# Grep for BOUNCE verdicts (should be near zero after preflight is in)
grep -r "^## Verdict$" docs/review-log/ | grep -v BOUNCE | wc -l

# Check the tab is alive (it's just a bash process)
ps aux | grep review-pool | grep -v grep
```

## 7. Open defects (separate tickets)

### review-pool.sh writes `done` marker on INFRASTRUCTURE failure
`review-pool.sh` calls `_write_verdict "$key" "BOUNCE" ...` on infrastructure failures (diff fetch, CG failure, verdict parse). A BOUNCE written to the review-log file is indistinguishable from a genuine BOUNCE verdict, and the `DONE_DIR` marker is written unconditionally. The 16 false BOUNCE verdicts from 2026-08-01 were made durable by this — once written, no mechanism un-retires them.

**Fix (ticket: REVIEWER-TAB-POOL / PR #346):** On INFRASTRUCTURE failure, write a `DONE_DIR/<key>.infra` marker with the failure reason, but do NOT write a review-log verdict. The item stays in the claim dir so a restarted tab can retry it with fresh credentials/gateway.

### review-pool.sh:36 hardcoded model defaults
`CHARON_REVIEW_MODELS="${CHARON_REVIEW_MODELS:-deepseek-v3,deepseek-r1}"` — wrong ids, will be overridden once this wrapper lands. After PR #346 lands, collapse `reviewer-tab.sh`'s export into `review-pool.sh` itself and retire the wrapper.
