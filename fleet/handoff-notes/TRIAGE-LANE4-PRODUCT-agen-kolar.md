# TRIAGE LANE 4 — PRODUCT repo (`/home/stack/code/charon`) worktree cleanup

Agent: `agen-kolar` · 2026-07-24 · scope: PRODUCT repo worktrees only.
**Nothing was deleted.** Section 4 holds reap commands for the operator to run.

Correction to the brief: there are **27** `charon-fleet-dogfood-*` worktrees, not 25.

---

## 1. Salvage — items 1 & 2 (both PUBLISHED)

| # | Worktree | Branch | Verdict | Action taken | SHA |
|---|---|---|---|---|---|
| 1 | `/home/stack/code/charon-fleet-INERT-INSTANCE-DETECT` | `feat/inert-instance-detect` | **HIGH VALUE — keep** | committed + pushed | `699be71` |
| 2 | `/home/stack/code/charon-fleet-router-ledger-decay` | `feat/router-ledger-decay` | keep (small, public-hygiene) | committed + pushed | `82f677a` |

Both published with `land-push.sh … --gate true`; **published only, not merged**. Both
worktrees are now clean; `push-verify: PROVEN` on both.

### 1a. Item 1 — `feat/inert-instance-detect` HOLDS A WORKING INERT DETECTOR

This is the headline finding. The 4 dirty files were a complete, green, tested detector,
not scratch:

| File | Change |
|---|---|
| `tools/check_inert_code.py` | +153/-11 — new `find_instance_inert_classes()` second AST pass |
| `tools/inert-code-disposition.json` | +47 — 6 gateway modules + 4 recorded false positives |
| `tests/test_inert_instance_detect.py` | +201 — FAIL-ON-REVERT suite |
| `docs/review-log/INERT-INSTANCE-DETECT.md` | +71 — review log |

**Verified by me, not taken on trust:**
- `python3 -m pytest tests/test_inert_instance_detect.py -q` → **10 passed in 1.54s**
- `python3 tools/check_inert_code.py` → **`check_inert_code: OK`, exit 0** on the real tree
- `python3 tools/check_public_clean.py` → clean; grep for `/home/stack`, `10.0.1.*`,
  `charon-private`, `4-LOM`, key patterns over the staged diff → **zero hits**
- `land-push.sh --gate true` → **gate GREEN**

**What it detects.** KSF's `inert_code` detector treats *construction* as reachability, so a
class that is instantiated and stored but whose instance methods are never invoked passes the
gate silently. The new pass compares each constructed class's public method names against all
instance-variable method calls in the production tree. Deliberately conservative — a method-name
collision suppresses the flag (false negatives tolerated over false positives).

**Direct relevance to `WIRE-GRAPHIFY-FRESHNESS`.** The detector, running live, flags exactly the
"built but no caller" set: `RequestInspector`, `SessionAffinity`, `Observability`,
`SpeculativeExecutor`, `ConsensusRouter`, `VirtualKeyManager` — all six constructed in
`gateway.py:_MODULE_SPECS`, stored on `GatewayProxyServer`, zero invocation sites. They are
now dispositioned `wire` with per-module wiring cost/benefit. **This is a mechanized detector
for the exact bug class that ticket exists to fix — it should be landed, not left on a branch.**

Caveats recorded honestly in the commit and disposition file: the heuristic produces 4 known
false positives (`GradesImport`, `Classification`, `OpencodeRenderer`, `CapSet`) — protocol
dispatch and attribute-vs-call cases it cannot resolve statically. Each carries a
`keep-detector-instance-inert-false-positive` disposition rather than being hidden.

Committed **PARTIAL**: scope-split (a), the detector, is complete and green. Scope-split (b),
actually wiring the 6 modules, is downstream — i.e. `WIRE-GRAPHIFY-FRESHNESS`.

### 1b. Item 2 — `feat/router-ledger-decay`

Confirmed already published earlier today: `origin/feat/router-ledger-decay` was at `d7caabb`,
matching local HEAD. The single dirty file was a **public-repo hygiene edit** to
`docs/review-log/ROUTER-LEDGER-DECAY.md`, replacing a named rig-internal path
(`fleet/memory/bitemporal.py`) with a neutral description. Worth keeping — it removes a
rig path from the public repo. Committed as `82f677a`, docs-only, no behaviour change.
Note the original commit message on `d7caabb` still names that path; unfixable without a
rewrite of already-published history, and it is a relative path, not a secret. Flagging, not acting.

### 1c. Process note — lease bypass

A pre-commit hook (`work-lease.sh`) refused both commits: no lease held for those tickets by
those worktrees. Acquiring a lease writes rig state, which this lane is scoped out of, so both
commits were made with the hook's own documented `WORK_LEASE_BYPASS=1` escape and that fact is
recorded **in the commit messages themselves**. Justification: these are preservation commits
of pre-existing uncommitted work in abandoned worktrees, not new work opened on a ticket.

---

## 2. Spike retirement — `spike/litellm-router-adapter` (item 3)

**Verdict: extraction is materially complete for the MEASUREMENTS. Recommend reaping the
worktree — but do NOT delete the branch. See the blocker below.**

Worktree dirt: `?? .litellm-venv/` only — a **245 MB** throwaway venv, gitignored, never
committed. Pure scratch, zero salvage value (its measurements are already in the note).

### 2a. BLOCKER — the branch is not published anywhere

```
git ls-remote origin refs/heads/spike/litellm-router-adapter   →   (empty)
```

`f2cee9d` exists **only in this local repo**. The commit adds 4 files / 394 lines:
`spike_litellm/{.gitignore, SPIKE-FINDINGS.md, litellm_router_adapter.py (90 LOC),
run_spike.py (181 LOC)}`. The measurements note preserves the *findings prose*; it does **not**
preserve the *code*. Reaping the worktree is safe (the branch ref survives). **Deleting the
branch would destroy the only copy of the adapter and the spike harness** — and the spike's own
author wrote that `litellm_router_adapter.py` "is the only file worth keeping as a reference for
ADOPT-SUBSTRATE-01", which mildly contradicts the note's claim that it is "strictly worse than
the shipped `litellm_plane/litellm_router.py`". Keep the ref.

### 2b. Present in the branch, MISSING from `LITELLM-SPIKE-MEASUREMENTS.md`

Compared `git show f2cee9d:spike_litellm/SPIKE-FINDINGS.md` line-by-line against the note.
All five numbered measurement blocks (dep footprint, deletable-LOC inventory, what-Charon-keeps,
fit result, capability gaps) are faithfully carried over, several with *added* context. Missing:

| Missing item | Where in branch | Materiality |
|---|---|---|
| **`ADOPT-SUBSTRATE-01` acceptance criteria** — "existing forwarder suite passes against BOTH backends" and "the litellm backend is never imported unless the flag is set (preserves stdlib-only default core)" | findings, final section | **Substantive.** The note's §6 declares this ticket "effectively executed" by `litellm_plane` but drops the criteria that would prove it. `pyproject.toml:30` does define an optional extra (`router = ["litellm>=1.93"]`), so the extra-only half looks satisfied — but the never-imported-unless-flagged half is unverified. Worth a follow-up check. |
| The adapter + harness **source code** (271 LOC) | `spike_litellm/*.py` | **Substantive** — see 2a. Not reproducible from prose. |
| Strategic conclusion: *"freeze the substrate, stop investing in it; the adopt path exists when needed"* | findings VERDICT | Moderate — this is the durable posture the spike argued for; the note records the PASS but not the recommendation. |
| Anchor `forwarder.py:814` / `DTC-CONCERN-#4` for the quality-scorer loop | findings §1 | Minor — the note describes the loop without the code anchor. |
| Repro command `PYTHONPATH=src .litellm-venv/bin/python3 spike_litellm/run_spike.py` and the local mock-OpenAI harness design | findings | Minor — moot once the venv is gone. |

Nothing measured is lost. What is at risk is **code and one acceptance contract**, both fixed by
keeping the branch ref.

---

## 3. Dogfood scratch — 27 worktrees (item 4)

All 27 checked individually. **All 27: 0 commits ahead of `origin/master`.** All sit on base
`b7aa4c8`, now **85 commits behind** master. All dirt is uncommitted eval output plus an
untracked `DOGFOOD-TICKET-BRIEF.md` (rig artifact) in every one.

| # | Worktree (`charon-fleet-dogfood-` prefix stripped) | Ahead | Tracked diff | Untracked |
|---|---|---|---|---|
| 1 | PROVIDER-URL-HELPER-deepseek-v4-flash | 0 | 4 files +49/-6 | BRIEF |
| 2 | PROVIDER-URL-HELPER-deepseek-v4-pro | 0 | 4 files +43/-6 | BRIEF |
| 3 | PROVIDER-URL-HELPER-free-mistral-code | 0 | 3 files +10/-4 | BRIEF |
| 4 | PROVIDER-URL-HELPER-gemma-4-31b-cb | 0 | none | BRIEF |
| 5 | PROVIDER-URL-HELPER-glm-5.2 | 0 | 4 files +81/-6 | BRIEF |
| 6 | PROVIDER-URL-HELPER-kimi-k2.6 | 0 | 4 files +38/-5 | BRIEF |
| 7 | PROVIDER-URL-HELPER-minimax-m2.7 | 0 | none | BRIEF |
| 8 | PROVIDER-URL-HELPER-minimax-m3-together | 0 | 4 files +93/-6 | BRIEF |
| 9 | RFL-3-deepseek-v4-flash | 0 | forwarder +23 | BRIEF, test_image_routing.py (180L) |
| 10 | RFL-3-deepseek-v4-pro | 0 | forwarder +28 | BRIEF, test_image_routing.py (177L) |
| 11 | RFL-3-free-mistral-code | 0 | forwarder +18/-8 | BRIEF, test_image_routing.py (45L) |
| 12 | RFL-3-gemma-4-31b-cb | 0 | none | BRIEF |
| 13 | RFL-3-glm-5.2 | 0 | forwarder +26 | BRIEF, test_image_routing.py (180L) |
| 14 | RFL-3-kimi-k2.6 | 0 | forwarder +21 | BRIEF, test_image_routing.py (171L) |
| 15 | RFL-3-minimax-m2.7 | 0 | none | BRIEF |
| 16 | **RFL-3-minimax-m3-together** | 0 | forwarder +35 | BRIEF, test_image_routing.py (**244L**) |
| 17 | SECRET-HOTROTATE-deepseek-v4-flash | 0 | 2 files +35/-3 | BRIEF |
| 18 | SECRET-HOTROTATE-deepseek-v4-pro-134749 | 0 | 2 files +46/-6 | BRIEF |
| 19 | SECRET-HOTROTATE-deepseek-v4-pro-232021 | 0 | 2 files +42/-6 | BRIEF |
| 20 | SECRET-HOTROTATE-deepseek-v4-pro-232300 | 0 | 2 files +30/-6 | BRIEF |
| 21 | SECRET-HOTROTATE-deepseek-v4-pro-232603 | 0 | 2 files +37/-6 | BRIEF |
| 22 | SECRET-HOTROTATE-free-mistral-code | 0 | 2 files +13/-2 | BRIEF |
| 23 | SECRET-HOTROTATE-gemma-4-31b-cb | 0 | 2 files +26/-6 | BRIEF |
| 24 | **SECRET-HOTROTATE-glm-5.2** | 0 | 2 files **+52/-6** | BRIEF |
| 25 | SECRET-HOTROTATE-kimi-k2.6 | 0 | 2 files +31/-6 | BRIEF |
| 26 | SECRET-HOTROTATE-minimax-m2.7 | 0 | none | BRIEF |
| 27 | SECRET-HOTROTATE-minimax-m3-together | 0 | 2 files +40/-3 | BRIEF |

### Bulk verdict: REAP ALL 27 — **but capture two diffs first (2 exceptions)**

The dirt is *not* junk output; each is a model's attempt at a real ticket, with source and
tests. But they are an **eval corpus**: 8–11 independent attempts at the *same three tickets*,
on a base 85 commits stale. No individual attempt is authored work anyone is waiting on.
Per-ticket landing status decides the call:

- **PROVIDER-URL-HELPER (8 worktrees) — SUPERSEDED, reap freely.** The ticket landed on master
  as `5dd929d` "refactor(providers): dedup provider URL/path construction into a shared helper
  (#159)", with the exact prescribed API present now at `src/charon/providers.py`
  (`models_url:149`, `chat_url:154`, `join_endpoint:137`, `validate_base_url:118`). Zero loss.

- **EXCEPTION 1 — RFL-3 (8 worktrees) — UNLANDED, and it cross-links to the inert work.**
  `tests/test_image_routing.py` does not exist on master and `forwarder.py` has no vision
  routing. More importantly: **6 of the 8 attempts wire `RequestInspector.inspect()` into
  `forward_with_failover`** — i.e. they are a candidate implementation for wiring one of the
  six modules `feat/inert-instance-detect` just flagged as instance-inert. The attachment points
  they use still exist on current master (`proxy_server.py:577 self.request_inspector`,
  `proxy_server.py:529 self.model_meta`), so the shape still applies. Best variant:
  **#16 RFL-3-minimax-m3-together** (+35 in `forwarder.py`, a 244-line loopback-gateway e2e test,
  and a hard-fail 502 rather than a silent text-only fallback). Capture before reaping and
  attach to `WIRE-GRAPHIFY-FRESHNESS` as prior art.

- **EXCEPTION 2 — SECRET-HOTROTATE (11 worktrees) — UNLANDED.** `apply_to_env(force_refresh=…)`
  is absent from `src/charon/secrets.py` on master; the feature (live key rotation without a
  process restart, preserving the `setdefault` default and the `_SENSITIVE_ENV` guards) was never
  landed. 10 of 11 produced impl + tests. Best variant: **#24 SECRET-HOTROTATE-glm-5.2**
  (+52/-6 across `secrets.py` and `tests/test_secrets.py`). Capture before reaping and confirm
  the ticket is still open in the tracker.

Neither exception blocks the reap — both are cheap to capture as patch files (§4 step 0), after
which all 27 worktrees are disposable.

---

## 4. Reap commands for the OPERATOR

Nothing below has been run. Review before executing. Run from `/home/stack/code/charon`.

### Step 0 — capture the two exception diffs FIRST (do not skip)

```bash
mkdir -p /home/stack/charon-private/fleet/state/salvage
git -C /home/stack/code/charon-fleet-dogfood-RFL-3-minimax-m3-together-20260715T001840Z diff \
  > /home/stack/charon-private/fleet/state/salvage/RFL-3-vision-routing-minimax-m3.diff
cp /home/stack/code/charon-fleet-dogfood-RFL-3-minimax-m3-together-20260715T001840Z/tests/test_image_routing.py \
  /home/stack/charon-private/fleet/state/salvage/RFL-3-test_image_routing.py
git -C /home/stack/code/charon-fleet-dogfood-SECRET-HOTROTATE-glm-5.2-20260714T232603Z diff \
  > /home/stack/charon-private/fleet/state/salvage/SECRET-HOTROTATE-glm-5.2.diff
ls -la /home/stack/charon-private/fleet/state/salvage/
```

### Step 1 — reap the 27 dogfood worktrees (and their local eval branches)

```bash
cd /home/stack/code/charon
for w in /home/stack/code/charon-fleet-dogfood-*; do
  b=$(git -C "$w" rev-parse --abbrev-ref HEAD)
  git worktree remove --force "$w" && git branch -D "$b"
done
git worktree prune
git worktree list | wc -l   # expect 46 - 27 = 19
```

Dry-run first if preferred: replace the body with `echo "$w -> $b"`.

### Step 2 — reap the LiteLLM spike WORKTREE ONLY — **keep the branch**

```bash
rm -rf /home/stack/code/charon-fleet-LITELLM-SPIKE/.litellm-venv   # 245 MB, gitignored
git -C /home/stack/code/charon worktree remove --force /home/stack/code/charon-fleet-LITELLM-SPIKE
# DO NOT run: git branch -D spike/litellm-router-adapter
# f2cee9d is NOT on origin — that branch is the only copy of the adapter (271 LOC).
```

Optional, to make the branch durable rather than merely local:

```bash
git -C /home/stack/code/charon tag archive/litellm-spike f2cee9d
# or publish it:
# bash /home/stack/charon-private/fleet/land-push.sh spike/litellm-router-adapter <worktree> --gate true
```

### Step 3 — items 1 & 2 worktrees: reap only after the branches are merged

Both are pushed and clean, so the worktrees are now redundant — but they hold branches with
unmerged work. Reap the directories once `feat/inert-instance-detect` and
`feat/router-ledger-decay` land; **never `git branch -D` these.**

```bash
git -C /home/stack/code/charon worktree remove /home/stack/code/charon-fleet-INERT-INSTANCE-DETECT
git -C /home/stack/code/charon worktree remove /home/stack/code/charon-fleet-router-ledger-decay
```

**Reap total: 28 worktrees now** (27 dogfood + LITELLM-SPIKE), **+2 later** (items 1 & 2, post-merge).

### Untouched (out of scope / protected)

`charon-wt-GATE-REENTRANCY`, `charon-wt-GW-CUTOVER`, `charon-wt-CONTRIB-HOOKS`,
`charon-fleet-DIFF-COVER-FIX`, `.claude/worktrees/*`, plus the other-lane worktrees
(`BENCH-OOB-GRADING`, `DEGRADE-ALERT`, `EVAL-CONTROL-GATE-FIX`, `LITELLM-CI-DEPS`,
`LITELLM-COST-FIELD-FIX`, `UNIFIED-PLANE-CANARY-FRAMEWORK`, `charon-wt-meter-kwh`,
`charon-wt/order-a`). `charon gate` was never run on `feat/diff-cover-mutmut-adopt`.

---

## 5. Follow-ups worth ticketing

1. **Land `feat/inert-instance-detect`** — it is the mechanized detector for the exact bug class
   `WIRE-GRAPHIFY-FRESHNESS` was opened to fix. Currently published but unmerged.
2. **Attach the RFL-3 vision-routing diff to `WIRE-GRAPHIFY-FRESHNESS`** as a candidate wiring
   for `RequestInspector` — one of the six modules the detector flags.
3. **Verify the dropped `ADOPT-SUBSTRATE-01` criterion**: is `litellm` still never imported
   unless the backend flag is set, now that `litellm_plane/` has shipped?
4. **Confirm `SECRET-HOTROTATE` is still open** in the tracker — the feature never landed and
   11 eval attempts at it are about to be reaped.
