# Charon — Manager Handoff

You are the next **Charon Manager**. This is a complete, self-contained handoff.
Read it fully before acting. The immediate sequence is: **(1) fix the one open
issue, (2) finish outstanding work (web UI), (3) migrate to GitLab.**

---

## 1. What Charon is

A thin, vendor-neutral **cross-vendor coding-agent orchestrator**. It drives
existing coding agents (OpenCode, etc.) over **ACP** (Agent Client Protocol;
stdio + NDJSON JSON-RPC) as swappable execution backends, and owns only the gap:
a git+JSON **Work Ledger** (sole progress truth), **cross-vendor handoff**, a
control-plane **fence + autonomy ladder (L0–L3)**, **cost/budget accounting**, and
an **observing gateway proxy**. Routing/execution/review are integrated, not
rebuilt. Read `docs/adr/0001`–`0004` and `docs/REVIEW-LOG.md` first — the ADRs are
the decisions, the REVIEW-LOG is the *reasoning* (every significant fork was
adversarially reviewed and reconciled there).

**Operator's product goal:** assign a *role* (e.g. "coder") an ordered *pool* of
models; run the cheapest/free one until it's rate-limited, then **fail over** to
the next with **no work loss**; minimize cost (free → flat-rate → paid tail);
standalone + VPS-deployable; SLOP-embeddable later.

**Invariants you must never break:** INV-1 (one Ledger = truth) · zero
third-party deps in the privileged loop (the `[service]`/`[dev]` extras are
separate) · `SUPPLY-CHAIN.md` gate before anything enters the loop · **no data
egress from the privileged loop** (providers sit behind the proxy) · container-
gated L2+ (INV-B4) · INV-P0 (add a backend/provider = config, not code).

## 2. Operating methodology (follow it — the operator expects this)

- **Every significant decision gets adversarial review before code.** Low-impact:
  one focused read-only `Explore`/general-purpose subagent. Architecture-defining:
  a **DTC** (a `Workflow` of N competing proposals → adversarial judges → a
  synthesis that reconciles *against physics, not by vote*). Reconcile every
  finding in `docs/REVIEW-LOG.md` (accept/reject/re-scope + why).
- **Proven-red tests are the proof, not the claim.** Keep the gate green:
  `pytest -q` (currently **94 passing**), `ruff check src tests`, `mypy src/charon`,
  `python3 tools/check_boundary.py src`. Commit per increment with a descriptive
  message ending `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Honesty over hype.** Disclose what's unproven; never fake a result. The
  operator values "done quickly *but sanely*" — lean process for the build, but
  don't skip the review on real forks.
- **Re-scope freely before code** (cheapest place to change direction); record it.

## 3. Repo state

- Repo `/home/stack/code/charon`, package `charon`, src-layout, Python ≥3.11.
- Branches: `master` (Tier 1) · `tier2` = **PR #1** (tiers 2–4, on GitHub) ·
  **`mvp-routing`** = current work (ADR-0004 + the routing/proxy/failover engine,
  ~12 commits, pushed to GitHub `Nnyan/charon`).
- **You cannot `git push`** (harness-gated). The operator runs `! git -C
  /home/stack/code/charon push` in their session. `gh` is authed as `Nnyan` (will
  change for GitLab — see §8).
- 94 tests green; ruff/mypy/boundary clean. Key modules: `coordinator.py`,
  `ledger.py`, `fence.py`, `router.py`, `pools.py`, `failover.py`, `proxy.py`,
  `proxy_server.py`, `adapters/acp.py`, `adapters/mock.py`, `api.py`, `cli.py`.

## 4. Infrastructure (live grounding)

- **Dev box = this WSL2 env** (`/home/stack/code/charon`). You BUILD + mock-test
  here. No docker; shell network egress is gated; `git push` gated.
- **Runtime box = `charon-vm`** (Hyper-V, Ubuntu 22.04, 4 GB RAM, 8 cores,
  internet egress OK). This is where live grounding happens (it's the isolation
  boundary, Mode-B-style).
  - Reach it **directly**: `ssh -i ~/.ssh/charon_vm charon@10.0.3.91` (the earlier
    Windows port-proxy was a dead end; direct works since it was moved to a proper
    switch). User `charon`, your pubkey is in its `authorized_keys`.
  - Installed: `uv` (Python 3.12 venv at `~/charon/.venv`), **OpenCode 1.17.10**
    (`~/.opencode/bin/opencode`). Provider keys in `~/.profile` (login shell):
    `OPENROUTER_API_KEY`, `OPENCODE_API_KEY`. `sudo` is interactive (no password).
  - **Sync code to the VM** (no .git there — it's a working copy):
    ```
    tar czf - --exclude=.git --exclude=.venv --exclude='*.pyc' --exclude=__pycache__ \
      --exclude=.mypy_cache --exclude=.pytest_cache --exclude=.ruff_cache --exclude=dist \
      -C /home/stack/code/charon . | ssh -i ~/.ssh/charon_vm charon@10.0.3.91 'tar xzf - -C ~/charon'
    ```
    The venv is an editable install, so synced `src/` changes take effect immediately.
  - **Run on the VM** via a login shell (for keys + PATH):
    `ssh -i ~/.ssh/charon_vm charon@10.0.3.91 'bash -lc "export PATH=\$HOME/.opencode/bin:\$HOME/charon/.venv/bin:\$PATH; ..."'`
  - **Gotcha:** nested heredocs inside `bash -lc "..."` break; write Python diag
    scripts to a local file and `cat | ssh ... 'cat > /tmp/x.py'` then run them.
  - OpenCode-Go config that works lives at `~/.config/opencode/opencode.json` on
    the VM (provider `opencode-go` → `https://opencode.ai/zen/go/v1`). Charon
    overrides this per-run via `OPENCODE_CONFIG_CONTENT` (see §7).

## 5. What's built and PROVEN LIVE

- Charon drives **real OpenCode + OpenCode-Go** end to end: `charon doctor` ACP
  handshake ✓; a real run creates files, commits, verifies executable acceptance,
  advances `lkg` ✓.
- The **observing proxy** sits in front of the gateway, **captures real token
  usage OpenCode hides over ACP** into the Ledger, and holds the provider key so
  **the agent env has no real key** (re-validated live).
- **Cost-first failover, proven live** (via `api.run_task`): pool
  `[openrouter-free → opencode-go]`, the free model is probed → **429 → SKIPPED**
  → OpenCode-Go selected → work done → verified → **complete, 12,996 tokens**, with
  the `failover` note recorded. ~8s.

## 6. THE ONE OPEN ISSUE — ✅ RESOLVED 2026-06-25 (see REVIEW-LOG 2026-06-25)

**Resolution:** the hypothesized main-thread deadlock was **disproved** (a live
all-thread stack trace shows the main thread's `select` loop and the proxy worker
threads composing cleanly to completion). The actual blockers were two real bugs:
(1) the proxy forwarded the pre-flight probe's `Python-urllib` UA, which
opencode.ai's Cloudflare edge now 403-bans; (2) the pseudo-success guard compared
the upstream's native model id against the prefixed pool id, false-flagging every
honest 200. Both fixed; the §7 CLI demo now completes **reliably (7/7 main-thread
runs)**. The CLI was **not** re-architected (no worker-thread/proxy-process move —
those were premised on the non-existent deadlock). Original trail kept below for
provenance.



**Symptom:** the failover run works via `api.run_task` **in a worker thread**
(reliable, ~8s) but **hangs in the main thread** — and therefore the **`charon`
CLI** (and `python -m charon.cli`) hangs (exit 124, no output) on the live
ACP+proxy `--role` run. The mock-backed CLI paths are fine.

**Already ruled out / fixed (do NOT repeat):**
- The CLI code is current on the VM (it has `--role`); editable install reflects syncs.
- The failover *selection* logic is correct and fast (probes free→429→skip→Go in 0.4s).
- A real **stderr pipe-buffer deadlock** was found and fixed (`adapters/acp.py`
  now uses `stderr=subprocess.DEVNULL`) — necessary, but did **not** resolve this hang.
- `OPENCODE_CONFIG` (file path) is ignored by OpenCode; `OPENCODE_CONFIG_CONTENT`
  (inline) works. OpenCode-ACP hangs on an **unrecognized provider name** — use the
  real provider (`opencode-go`/`openrouter`); these are already handled by `_split_model`.
- Direct evidence: `diag2.py` (run_task in a daemon thread) → completes 8s, 12996
  tokens. `diag3.py` (run_task in the main thread) → hangs. Same code/env.

**Leading hypothesis:** an interaction in the **main thread** between the blocking
ACP read-loop (`AcpBackend._readline` → `select.select` on the agent's stdout) and
the **in-process `ThreadingHTTPServer` proxy** (and/or signal/SIGCHLD handling that
only happens in the main thread). The proxy worker thread must service OpenCode's
HTTP call while the main thread blocks in `select`; in a worker thread this
composes fine, in the main thread it doesn't.

**Recommended approach:**
1. Reproduce with **logging** on the VM: write a diag that calls `run_task` in the
   main thread with prints (to a file) before/after `select_live_entry`, before/
   after `coordinator.run`, and inside `AcpBackend._rpc`/`_readline` and
   `proxy_server._ProxyHandler._handle`. Find the exact line the main thread blocks
   on and whether the proxy handler ever runs.
2. If it's the proxy-thread-not-servicing-during-main-thread-select interaction,
   the clean fixes are (pick after root-causing): run the proxy as its own
   **process** (not an in-process thread); OR run the coordinator/dispatch in a
   **worker thread** from the CLI (`_cmd_run`) — defensible since run_task is
   self-contained and the worker path is proven; OR make `_readline` poll with a
   short select timeout in a loop so it yields. Add a regression test if feasible.
3. Re-run the **CLI** `charon run --role coder ...` on the VM until it reliably
   completes (recipe + pool config in §7). That closes the live failover demo.

## 7. Live failover demo recipe (for verifying the fix)

On the VM, in a fresh dir with `.charon/models.json` + `.charon/pools.json`:
```json
// models.json — native opencode "provider/model" ids; key_env per upstream
{
 "openrouter/qwen/qwen3-coder:free": {"agent":"opencode","cost_tier":"free","cost_rank":5,"code_safe":false,"free":true,"upstream_base":"https://openrouter.ai/api/v1","key_env":"OPENROUTER_API_KEY"},
 "opencode-go/kimi-k2.7-code":      {"agent":"opencode","cost_tier":"flat","cost_rank":20,"code_safe":true, "free":false,"upstream_base":"https://opencode.ai/zen/go/v1","key_env":"OPENCODE_API_KEY"}
}
// pools.json
{"coder": ["openrouter/qwen/qwen3-coder:free", "opencode-go/kimi-k2.7-code"]}
```
```
charon run --goal "Create hello.txt with hi" --accept "test -f hello.txt" \
  --role coder --acp-cmd "opencode acp" --autonomy L1
```
Expect: `status complete`, `failover: role 'coder' → opencode-go/kimi-k2.7-code (flat); skipped ['openrouter/qwen/qwen3-coder:free']`, tokens > 0.
(`pkill -9 -f opencode` between runs to avoid orphans from killed hangs.)

## 8. Outstanding work (after the open issue)

- **Web UI (ADR-0004 D7/R3). ✅ BUILT 2026-06-25** (see REVIEW-LOG 2026-06-25).
  A **minimal, read-only web Ledger dashboard** served by `service/app.py`:
  token-gated, single-operator, **container is the boundary**; serves a config
  view + project/run list + a Ledger run view (progress/cost/handoffs/
  checkpoints). Self-contained HTML (zero egress); auto-docs disabled. Run it with
  `python -m charon.service` (refuses a non-loopback bind without
  `CHARON_SERVICE_TOKEN`). The exposed web process **does not run the privileged
  loop** — `POST /v1/runs` still `501`s; the enqueue→worker run path stays
  deferred to Tier 2b *with* its Tier-3 SLOP consumer. Live-verified on the VM
  against real failover ledgers. Tests are behind the `[service]` extra
  (`importorskip`), so the core gate stays stdlib-only.
- **Deferred items** (each has recorded directives): live HTTP service web/worker
  split (Tier 2b, lands with the Tier-3 SLOP adapter, which lives in the SLOP
  repo) · parallelism PERF-4 (unsafe-as-drafted; fixes in `PLAN-tier4.md §6`) ·
  the real cross-model consensus reviewer (the L2 gate is built; the reviewer is
  gated behind the gateway) · the network gateway (gated on `SUPPLY-CHAIN.md`;
  adopt the orq.ai patterns natively per `docs/research/orq-comparison.md`).
- **Supported backends/providers** are in ADR-0004 D2/D3 (OpenCode/Goose/Cline +
  Codex/Claude Code; reject Cursor/Crush; tiered provider pool with `code_safe`).

## 9. Hosting — PIVOTED 2026-06-25: GitLab ABANDONED → public GitHub `SLOP-Platform` org

**Decision (operator, 2026-06-25):** do **NOT** go to GitLab. The GitLab move added
real friction (SSH/token-scope setup, a different CI dialect, a heavier UI; the
first pipeline even failed `yaml invalid` and was never fixed). We established the
"GitHub cost" was only **Actions minutes** (private repos are free; public repos
get unlimited free Actions). Operator chose: **Charon becomes a PUBLIC repo in the
GitHub org `SLOP-Platform`**, CI on a **shared self-hosted runner** (zero GitHub
minutes). This is the authoritative plan; the GitLab work below is to be UNWOUND.

### 9a. What the NEXT session must do (operator-coordinated)

Operator's migration spec (paste, 2026-06-25) — follow exactly:

> Goal: get Charon live on GitHub in org **SLOP-Platform**, running CI on the
> shared **4-LOM** self-hosted runner. **COLLISION GUARD:** a separate *mediastack*
> session owns ALL 4-LOM / runner / org-runner setup (ticket #1318). You do **NOT**
> register or configure runners or touch org runner settings — you ONLY create the
> repo + workflows that **use** the `[self-hosted, 4-lom]` org runner pool.
>
> - Repo `SLOP-Platform/charon` already EXISTS but is **PRIVATE** → make it public
>   (Settings → visibility) since Charon is the public product. Keep any
>   private/dev-apparatus files OUT if public.
> - Push the local `/home/stack/code/charon` tree; set remote to
>   `git@github.com:SLOP-Platform/charon.git`. **Prompt the operator before pushing
>   to origin/main.** (`git push` is harness-gated — hand the operator the `!`.)
> - CI: add `.github/workflows/*.yml` with `runs-on: [self-hosted, 4-lom]`
>   (org-level runners the mediastack session is standing up). If those runners
>   aren't online yet, pipelines just QUEUE until they are — coordinate timing with
>   the operator; do NOT register your own. Self-hosted = ZERO GitHub minutes.
>   Gates: fast lint+typecheck+unit-test on every push/PR; heavy/slow suites on
>   `schedule:`/`workflow_dispatch:` only.
> - **4-LOM facts (read-only):** `10.0.1.60`, Ubuntu 24.04, ssh alias `mediastack`,
>   user `stack`, Docker+buildx + Python 3.12 + libicu present.
> - **Gotchas (proven on mediastack — bake in):** (1) Ubuntu runner, so
>   `actions/setup-python` `python-version: "3.12"` works. (2) If using actionlint,
>   add `4-lom` to `.github/actionlint.yaml` (`self-hosted-runner.labels: [4-lom]`)
>   or it errors "unknown label". (3) Install CLI tools into `$RUNNER_TEMP/bin` +
>   `echo "$RUNNER_TEMP/bin" >> $GITHUB_PATH`, never root-owned `/usr/local/bin`.
>   (4) Do NOT set `PYTEST_ADDOPTS=--basetemp=$RUNNER_TEMP/...` if there are
>   hermeticity/tmp-allowlist checks. (5) Verify ONE gate goes green on the runner
>   before pointing everything at it. Reference mediastack's
>   `.github/workflows/*.yml` for working self-hosted patterns.

### 9b. Unwind the abandoned GitLab port (in this repo, `mvp-routing`)

The GitLab detour left artifacts to revert/redirect to the SLOP-Platform target:
- **Delete `.gitlab-ci.yml`** (replaced by `.github/workflows/` using the 4-LOM
  runner). The existing `.github/workflows/ci.yml` is GitHub-hosted-runner-based —
  rework it to `runs-on: [self-hosted, 4-lom]` per 9a (or split fast/slow gates).
- **Redirect URLs `gitlab.com/slop-platform/charon` →
  `github.com/SLOP-Platform/charon`** in: `pyproject.toml` (Homepage/Repository),
  `README.md` (install/clone + the web-dashboard section), `docker-compose.yml`
  (image → GHCR `ghcr.io/slop-platform/charon` or keep a local tag),
  `docs/adr/0001`+`0002`, `docs/PLAN-tier1`+`tier2`, `docs/SUPPLY-CHAIN.md §5`
  (registry/provenance — GHCR + GitHub-OIDC `attest-build-provenance` is back on
  the table since we're on GitHub again). Git history references to "GitHub"/"PR
  #1" are fine as-is.
- The container registry decision (GHCR vs none) rides with the publish job; for a
  public repo, GHCR + GitHub-native SLSA provenance is the original (cleanest) path
  — the GitLab provenance "open item" evaporates.

### 9c. Current repo/remote state at handoff
- Branch **`mvp-routing`**, 3 commits ahead of `e99d3cc`, **pushed to GitHub
  `Nnyan/charon`** (origin) AND `gitlab` (the abandoned remote — can be removed:
  `git remote remove gitlab`). 114 tests green; tree clean.
- The product (failover engine + web UI) is **done and host-independent** — none of
  the above touches application code, only CI/URLs.

## 10. Landmines / hard-won facts (live-verified — trust these)

- **ACP has no "set model"** → a pool entry = an agent pre-pinned to a model
  (Option B). Model comes from the agent's config default.
- **OpenCode hides usage over ACP** → the observing proxy is mandatory for
  cost/exhaustion. (`charon doctor` confirms `reports_usage: false`.)
- **OpenRouter free tier is not a workhorse** — every free model 429s (shared
  global daily cap) or 404s (removed). Flat-rate (OpenCode Go ~1.4s, usage
  reported) is the real backbone; free buys *diversity*, not headroom.
- Proxy must **stream SSE** (OpenCode streams; buffering breaks it) and inject
  `stream_options.include_usage` to see tokens; must **forward client headers**
  (some gateways 403 an unknown User-Agent); must distinguish **429 (retry/failover)
  from 404 (drop-from-pool)**.
- Failover pre-flight must require a **positive 200**, not "absence of a flag" — a
  slow/timed-out probe must skip, or the agent gets a dead model and hangs.
- The fence's scrubbed env (`HOME=worktree`, no creds) **breaks** a real agent;
  the live ACP path passes a **trusted env** (real HOME/PATH, **no provider keys** —
  proxy injects them) because the VM/container is the boundary. Keep the worktree
  escape-scan.
- `git push` and registry/network git ops are **harness-gated for you** — hand the
  operator the `! ...` command.

## 11. Suggested first moves

1. Reconnect: `ssh -i ~/.ssh/charon_vm charon@10.0.3.91 'echo up; free -h'`, sync
   code, run `pytest -q` on the VM (proves deploy).
2. Root-cause the §6 hang with VM-side logging; fix; verify the §7 CLI demo
   completes reliably; commit; have the operator push.
3. Design → (light review) → build the **read-only web Ledger UI** (§8); keep it
   thin and honest.
4. Do the **GitLab migration** (§9).

Keep the gate green, commit per increment, reconcile decisions in REVIEW-LOG, and
ask the operator to push. Good luck.
