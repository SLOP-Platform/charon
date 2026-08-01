repo: charon-private
tier: strong
priority: 1
difficulty: 2
work_class: rig-meta
branch: feat/reviewer-pool-headless-tabs
owns: fleet/reviewer-tab.sh, fleet/spawn-tab.sh, fleet/REVIEWER-POOL-PROCESS.md
serial_justified: One reviewer-tab entrypoint, the generic tab spawner it needs, and the process doc that makes the decision durable; splitting them lands a launcher with no documented contract.
substrate: |
  Windows Terminal (`wt.exe`) + the rig's OWN fleet/spawn-worker.sh — adopt, do not re-derive.
  spawn-tab.sh reuses spawn-worker.sh's VERIFIED invocation verbatim (`-w 1` targets the
  operator's window because `-w 0` follows GUI focus and $WT_SESSION is a PANE guid;
  --suppressApplicationTitle stops the child retitling the tab; the quoted ';' stops wt eating it
  as a shell separator; the chained focus-tab stops the spawn eating operator keystrokes). None of
  that research is repeated — only the opencode-specific parts (port, TUI readiness, prompt
  injection) are dropped, because a reviewer pool has no TUI, no port and no prompt.
  Considered and rejected: tmux/screen (the operator's client is Windows Terminal — a tmux pane is
  not a visible tab); systemd units (headless, defeats the whole point of a WATCHABLE tab);
  `nohup`/`setsid` detached processes (TRIED THIS SESSION AND REJECTED BY THE OPERATOR — they run
  but are invisible, which is exactly the failure being fixed).
substrate-novel: |
  The novel slice is the rig-specific PREFLIGHT contract, not the spawning: derive the model chain
  from tier-models.tsv rather than a hardcoded literal, and refuse to start unless gh is present
  AND authenticated, the gateway token derives, and /v1/models parses. No external tool knows
  those are this rig's silent-failure modes.
depends_on:
note: |
  Closes a measured failure and records an operator decision.

  MEASURED 2026-08-01 — a reviewer tab spun 312 cycles logging
  `WARN gh pr list failed … / no claimable review items`, and wrote 16 FALSE `BOUNCE` verdicts
  (`diff fetch failure`) while marking all 16 done. Root cause: a WT tab runs `bash <script>` — a
  NON-login shell — which sources neither ~/.profile nor ~/.bashrc, so `~/.local/bin` is absent and
  BOTH `gh` and `opencode` vanish. Identical fault class to fleet-droid.sh:21-32 and
  charon-run.sh, which both already fix it; the reviewer path had never been given the guard.

  SECOND fault, same lane: review-pool.sh:36 defaults CHARON_REVIEW_MODELS to
  `deepseek-v3,deepseek-r1` and NEITHER id exists among the gateway's ~2580 models, so every review
  failed over the whole chain and wrote a fail-closed BOUNCE that reads like a code verdict.
  reviewer-tab.sh derives the chain from tier-models.tsv instead. review-pool.sh itself is owned by
  REVIEWER-TAB-POOL (PR #346, open), so this wrapper is the collision-free fix and can be collapsed
  into review-pool.sh once #346 lands.

  OPERATOR DECISION (2026-08-01), recorded in REVIEWER-POOL-PROCESS.md §2: reviewer pools stay
  HEADLESS and do NOT use spawn-worker.sh / session-bridge registration. A reviewer has no TUI, no
  port and no conversation to hold; its entire state is on disk and greppable. The honest
  counter-argument is recorded alongside it — a heartbeat would have reported "alive and working"
  during BOTH of the failures above, because the pool genuinely was alive and genuinely was writing
  verdicts. The fix is fail-loud preflight, not liveness reporting.
accept: |
  - A reviewer tab REFUSES to start (exit 4, loud reason) when gh/git/python3/timeout/curl is
    missing, when `gh auth status` fails, when the gateway token cannot be derived, or when
    /v1/models does not return a parseable list — instead of looping "no claimable review items".
  - The model chain is read from fleet/tier-models.tsv, never a hardcoded literal.
  - spawn-tab.sh opens a NAMED, COLOURED tab in the operator's window, returns focus, carries
    CHARON_TAB_ENV through into the tab, and holds the tab open after exit so a crash is readable.
  - The tab's non-login shell gets ~/.local/bin APPENDED (never prepended).
  - REVIEWER-POOL-PROCESS.md documents the launch command, the headless decision + its
    counter-argument, the guards, how to VERIFY a reviewer is working, and the open
    review-pool.sh defects.

## Dependencies & Sequence

- **depends_on: (none).** New files plus a doc; touches nothing another ticket owns.
- **Sequence: now.** It is what makes review throughput trustworthy, and every later PR-landing
  wave depends on verdicts being real.
- **Blocks / unblocks:** unblocks parallel review tabs, which is the throughput lever on the
  20-PR backlog.
- **owns-collision:** none. Deliberately does NOT touch `fleet/review-pool.sh` (owned by
  REVIEWER-TAB-POOL / PR #346) or `fleet/spawn-worker.sh` — both left untouched by design.
- **Follow-up (separate ticket, NOT this one):** review-pool.sh writes a `done` marker on
  INFRASTRUCTURE failure, permanently retiring a PR from review. That is the defect that made the
  16 false verdicts durable, and it must be fixed behind PR #346.
