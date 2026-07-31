# RESEARCH — unattended spawn of watchable worker terminals (2026-07-27)

**Verdict: ADOPT `wt.exe -w charon-fleet new-tab` + a one-line wrapper script. Nothing to build, nothing to install.**
**One-time operator action: rename the current window to `charon-fleet` (Ctrl+Shift+P → "Rename window").
No relaunch, no lost session. `-w 1` works today with zero setup as the fallback — see §3.1b/§3.1c.**
The operator's existing Windows Terminal already exposes a complete, documented, scriptable spawn API
that a non-interactive WSL process can drive. It reuses an open window, adds TABS (not windows), names
and colours each tab, and the spawned worker is **not** a descendant of the manager — so it survives the
manager dying. All of that is **verified on this box today**, not inferred.

Legend: **[V]** = I ran it and observed the result · **[VD]** = verified against vendor docs/spec ·
**[I]** = inferred, not proven. Every **[V]** below was cleaned up afterwards (see §12).

---

## 0. The finding that decides everything

**Spawning and watching are two separable concerns, and only one of them is hard.**

Prior research (`RESEARCH-AGENT-COMMS-2026-07-26.md`) established that a worker launched as
`opencode --port <N>` is *simultaneously* an interactive TUI and an HTTP control-plane server, and that
`fleet/session-ctl.sh` can then list/steer/stop/reply/watch it. The only missing verb was **create**.

The missing verb is not an opencode problem. It is a *terminal* problem, and Windows Terminal solved it
years ago. `wt.exe` is a **client** of an already-running Windows Terminal process: invoking it does not
start a terminal, it sends a command to the existing one. That is why it works from a non-interactive
process, why it can target an existing window, and why the thing it spawns is not our child.

```
manager (Claude Code, WSL, non-interactive)
   │  wt.exe -w charon-fleet new-tab --title … --tabColor … wsl.exe -d Ubuntu-24.04 -- bash -lc <script>
   ▼
Windows Terminal (already running, separate Windows process)
   │  creates a TAB in the named window — the SAME window the operator is working in (§3.1b)
   ▼
WSL interop /init  ──►  bash  ──►  opencode --port N --model charon/<m>
                                     ├─ interactive TUI  → operator watches & types
                                     └─ HTTP API on :N   → manager steers via session-ctl.sh
```

The manager appears **nowhere** in that chain below Windows Terminal. Verified ancestry, §3.4.

---

## 1. Environment — verified, not trusted

| Fact | Evidence **[V]** |
|---|---|
| WSL2, Ubuntu-24.04, kernel 6.6.87.2-microsoft-standard-WSL2 | `uname -a`, `/etc/os-release` |
| Distro name for `wsl.exe -d` is exactly `Ubuntu-24.04` | `wsl.exe -l -v` → `* Ubuntu-24.04  Running  2` |
| WSL interop **enabled** | `/proc/sys/fs/binfmt_misc/WSLInterop` → `enabled` |
| `wt.exe` on `PATH` inside WSL | `which wt.exe` → `…/WindowsApps/wt.exe` |
| `tmux` present; **no tmux server running** | `which tmux`; `tmux ls` → no socket |
| `wezterm`, `zellij`, `ttyd`, `gotty`, `screen` — **absent** | `which` → not found |
| opencode **1.18.6**, has `serve` / `attach` / `web` / `acp` | `opencode --version`, `--help` |
| One live operator worker (pid 3913454, `opencode --model charon/deepseek-v4-pro`), **no port bound** | `ps`, `ss -tlnp` |
| Exactly one Windows Terminal *process* hosting *all* windows | PowerShell `Get-Process WindowsTerminal` → single PID 9284 |

> **Doc-vs-reality discrepancy worth recording.** Microsoft's own page says *"Execution aliases don't work
> in WSL distributions… spawn it from CMD directly by running `cmd.exe /c wt.exe`"* **[VD]**. On this box
> that is **wrong** — bare `wt.exe` from a non-interactive WSL bash resolves and works **[V]**. Use bare
> `wt.exe`; the `cmd.exe /c` wrapper is an unnecessary extra quoting layer. (Consistent with the standing
> `confirm-dont-trust-documentation` directive — and with `no-hardcoded-cross-boundary-paths`: use the
> PATH name, never a `/mnt/c/Users/<person>/…` absolute.)

---

## 2. THE REUSABLE FIX — why inline commands fail and a wrapper script does not

This is the single most transferable finding, because it burned two attempts.

**Failure observed [V]:** an inline payload produced Windows error `2147942402 (0x80070002)`
(`ERROR_FILE_NOT_FOUND`) and a tab whose title was the literal string `" sleep 45"` — i.e. the argument
arrived with quotes *embedded* rather than as a bare token, and nothing executed. The tab opened blank.

**Three quoting layers collide:**

1. **`wt.exe` itself** treats `;` as a **command separator** — `wt … ; new-tab …` chains actions **[VD]**.
   Any `;` in your payload (`cd X; opencode …`) is eaten by `wt` and reinterpreted as *"open another tab"*.
   Escaping it from bash requires `\;`, and it must survive bash → wt intact.
2. **`wsl.exe -d Ubuntu-24.04 --`** boundary re-tokenises everything after `--`.
3. **`bash -lc "<one long string>"`** needs its own nested quoting for anything containing spaces,
   quotes or `$`.

**The fix: collapse three layers into one. Write the payload to a script; pass only its path.**

```bash
# fleet/launch-worker.sh  — arguments only, no quoting, no `;`
#!/usr/bin/env bash
set -euo pipefail
TICKET="${1:?ticket}"; MODEL="${2:?model}"; PORT="${3:?port}"
cd /home/stack/charon-private || exit 1
exec /home/stack/.local/bin/opencode --port "$PORT" --model "charon/$MODEL"
```

```bash
wt.exe -w charon-fleet new-tab \
  --title "$TICKET · $MODEL" --tabColor "#8E44AD" --suppressApplicationTitle \
  wsl.exe -d Ubuntu-24.04 -- bash -lc /home/stack/charon-private/fleet/launch-worker.sh
```

The command line now contains **no `;`, no nested quotes, no `$`**. Every variable part is either a
`wt` flag value (which `wt` parses correctly) or an argv element handed to the script.

**Is a wrapper script "hand-rolling"? No.** It is ~6 lines of argument plumbing that exists solely to
avoid an escaping minefield across a Windows↔Linux boundary we do not control. It adds no policy, no
state, no protocol, and no product surface. The *mechanism* — tab creation, targeting, naming, colouring
— is 100% adopted from Windows Terminal. This is the `adopt-substrate-build-only-novel-slice` shape.

**Use `&&` not `;`** if you ever must inline: `bash -lc "cd /x && exec opencode …"` survives, `;` does not.

---

## 3. Candidate #1 — Windows Terminal `wt.exe` (RECOMMENDED)

**What it is:** the CLI front-end to the already-running Windows Terminal. MIT licence, Microsoft,
ships with Windows, **already installed and already in use by this operator**.

### 3.1 Window/tab targeting — all three new requirements VERIFIED

`-w, --window <window-id>` accepts an integer id, a **name**, or reserved values **[VD]**:

| Value | Semantics | Verified |
|---|---|---|
| `-w <name>` | Target window named `<name>`. **"If no window exists with the given window-id, then a new window will be created with that id/name."** | **[V]** — first call created the window, calls 2 and 3 added **tabs** to it |
| `-w 0` / `-w last` | Most **recently used** window | **[V]** — landed in whichever window I had focused last |
| `-w -1` / `-w new` | Always a new window | **[VD]** |
| `-w 1` | The first-created window (integer id) | **[VD]** |

**The decisive experiment [V].** Snapshot of top-level windows via Win32 `EnumWindows` before/after,
plus one proof-file written per tab:

```
windows BEFORE : 2 CASCADIA_HOSTING_WINDOW_CLASS
  → wt.exe -w charonfleet new-tab --title WORKER-A --tabColor #C0392B --suppressApplicationTitle …
  → wt.exe -w charonfleet new-tab --title WORKER-B --tabColor #27AE60 --suppressApplicationTitle …
  → wt.exe -w charonfleet new-tab --title WORKER-C --tabColor #2980B9 …
tab proofs     : tab-A.proof  tab-B.proof  tab-C.proof      ← 3 tabs really ran
windows AFTER  : 3 CASCADIA…  (exactly ONE new window)      ← 3 tabs, 1 window ✅
```

**Requirement 1 (no window-per-worker): SATISFIED.** **Requirement 2 (reuse an open window): SATISFIED.**

### 3.1b "Will tabs appear in the window I run the MANAGER from?" — settled empirically

This is the question that decides usability, so I tested every form against the operator's **real**
window (handle `525294`, the one running the manager). A spawn "landed in the operator's window" iff
that window's title changed to my tab's title; it "made a new window" iff a new
`CASCADIA_HOSTING_WINDOW_CLASS` handle appeared.

| Form | Result | Verdict |
|---|---|---|
| *(no `-w`)* | New window | ✗ |
| `-w <name>` (e.g. `charonfleet`) | Creates a window **named** that, then adds tabs to it | ✓ but **not** the operator's window unless that window already carries the name |
| `-w 0` | Most-**recently-used** window — landed in whichever window was last focused, **not** the manager's | ✗ **fragile** |
| `-w $WT_SESSION` | **New window** `1445054` | ✗ **hard negative** |
| **`-w 1`** | **Landed in the operator's window `525294`** — title became `WID-1`, then `AGAIN` on a repeat | **✓ VERIFIED, zero setup** |
| `-w 2` | New window `3410180` (no window with id 2 existed) | ✗ |

**1. `-w 0` follows focus and is positionally fragile — confirmed [V].** It resolves to Windows
Terminal's own most-recently-used window, which tracks *GUI focus*. A WSL subprocess invoking `wt.exe`
is **not** treated as "using" the window its parent lives in. So from a non-interactive manager, `-w 0`
lands wherever the operator last clicked — including a window that has nothing to do with the fleet.
**This kills `-w 0` as the zero-setup option.** Do not use it.

**2. `WT_SESSION` does NOT resolve to a window id — hard negative [V].** `WT_SESSION`
(`0440b827-…`) and `WT_PROFILE_ID` *are* both visible from inside WSL, and are inherited all the way
down to the manager process. But `WT_SESSION` identifies a **terminal session (pane/connection)**, not a
window. `-w` accepts only an integer id or a name **[VD]**, so the GUID was treated as a *name*, no
window had it, and Windows Terminal **created a brand-new window** — exactly the outcome the operator
does not want. **There is nothing readable from inside WSL that yields the manager's window id.** Not
"probably" — I ran it and watched a new window appear.

**3. `-w 1` DOES hit the operator's window, with zero setup — verified twice [V].** `-w 1` means *the
first-created window* **[VD]**, and the operator's long-running manager window is the first-created one.
Two independent spawns (`WID-1`, then `AGAIN` with a colour) both retitled handle `525294` and left no
new window. **This is the only zero-setup form that works.** Its limitation is honest and structural: it
is *positional*. If the operator ever closes that window and opens others, or the Terminal process
restarts in a different order, `-w 1` points somewhere else — and if no window has id 1, it silently
creates one.

**4. Named windows are deterministic, and adopting one does NOT require relaunching [V]/[VD].**
`-w <name>` attaches to an existing window of that name and **creates one with that name if none
exists** **[VD]**, verified both halves **[V]** (first call created `charonfleet`; calls 2 and 3 added
tabs). The name is resolved by Windows Terminal's monarch process, so it **survives the manager
restarting** — nothing needs remembering, the name *is* the handle. Verified across separate,
independent `wt.exe` invocations from different shells **[V]**.

The catch is that a window only answers to a name once it *has* one, and **there is no `wt.exe` verb to
rename an existing window** — I checked the full CLI surface (`new-tab`, `split-pane`, `focus-tab`,
`move-focus`, `move-pane`, `swap-pane`; nothing else) **[VD]**. Rename is a GUI/action-level operation:

- **`openWindowRenamer`** (id `Terminal.OpenWindowRenamer`) — pops up an in-place rename box **[VD]**
- **`renameWindow`** — `{"command":{"action":"renameWindow","name":"charon-fleet"}}`; **not bound by
  default**, but all actions are automatically added to the Command Palette **[VD]**
- **`identifyWindow` / `identifyWindows`** — overlay showing each window's **name and index**; this is
  how the operator can *read off* the integer id to confirm `-w 1` is really their window **[VD]**

**Crucially, renaming happens in place — the operator does NOT have to close their terminal or lose the
running manager session.** Ctrl+Shift+P → "Rename window" → `charon-fleet` → Enter. One time, ~5 seconds.

### 3.1c Recommendation on targeting

**Use `-w charon-fleet` (named), after a one-time in-place rename. Fall back to `-w 1`.**

| | `-w 1` | `-w charon-fleet` |
|---|---|---|
| Setup | **none** | one-time rename, no relaunch, ~5s |
| Lands in the operator's window | ✅ **[V]** | ✅ once named **[V]** for the mechanism |
| Survives focus changes | ✅ | ✅ |
| Survives manager restart | ✅ | ✅ |
| Survives the operator reordering/closing windows | ❌ **positional** | ✅ **deterministic** |
| Failure mode | silently targets the wrong window, or creates one | creates a correctly-named window to adopt |

The operator's instinct was right, and it now has evidence behind it: **the named window is correct**,
because it is the only form whose failure mode is benign. When `-w 1` is wrong it puts a worker tab in a
stranger's window; when `-w charon-fleet` is "wrong" (the name is missing) it creates the fleet window,
which is self-healing and immediately adoptable. `-w 1` is a legitimate zero-setup starting point and it
is **verified working today** — but it should be treated as the fallback, not the design.

### 3.2 Tab name and colour — requirement 3, with a mandatory gotcha

| Flag | Result |
|---|---|
| `--title "<text>"` | Sets the tab title **[V]** |
| `--tabColor "#RRGGBB"` | Per-tab colour; accepts `#RGB` or `#RRGGBB` **[VD]**, accepted without error and applied per tab **[V]** |
| `--suppressApplicationTitle` | **REQUIRED** — without it the app's title escape wins **[V]** |

**Proof of the gotcha [V].** My worker script deliberately emitted `\033]0;APP-SET-TITLE-x\007`.
Cycling focus and reading each window title back:

```
focus-tab 0 → "WORKER-A"            (spawned WITH --suppressApplicationTitle)  ✅ name stuck
focus-tab 1 → "WORKER-B"            (spawned WITH --suppressApplicationTitle)  ✅ name stuck
focus-tab 2 → "APP-SET-TITLE-C"     (spawned WITHOUT it)                       ❌ app hijacked it
```

Microsoft's docs agree: *"If you change the title of a tab… and want that title to persist, you must
enable `suppressApplicationTitle`"* **[VD]**. **opencode does set its own title** (it emits `]0;OpenCode`
— observed in raw TUI capture **[V]**), so **without this flag every tab will be called "OpenCode"** and
the operator loses exactly the at-a-glance distinction they asked for. Always pass it.

Caveat **[VD]**: `--tabColor` binds to the tab's *first pane*; with split panes you must repeat
`--tabColor` on each `split-pane`. Irrelevant if one worker = one tab (recommended).

### 3.3 The full verified end-to-end spawn

```bash
wt.exe -w charonfleet new-tab \
  --title "T-SPAWN-01 · minimax-m3-free" --tabColor "#8E44AD" --suppressApplicationTitle \
  wsl.exe -d Ubuntu-24.04 -- bash -lc /…/scratchpad/realworker.sh
```
where `realworker.sh` = `cd /home/stack/charon-private && exec opencode --port 47801 --model charon/<m>`.

Observed **[V]**:

```
spawn exit                = 0
tab                       = "T-SPAWN-01 · minimax-m3-free", coloured, in the shared window
curl :47801/api/health    = {"healthy":true}                    ← manager control plane LIVE
readlink /proc/<pid>/cwd  = /home/stack/charon-private          ← correct cwd
argv                      = opencode --port 47801 --model charon/minimax-m3-free
fleet/session-ctl.sh http://127.0.0.1:47801 list  → returned the session list  ← already addressable
```

**The existing `fleet/session-ctl.sh` drove the spawned worker with zero changes.** Spawn was the only
missing verb and it is now closed.

### 3.4 Does it survive the manager dying? — YES, verified

The load-bearing claim, proven by walking the real ancestry of a spawned process **[V]**:

```
4106212  opencode --port 47801 --model charon/minimax-m3-free
4106211  /init          ← WSL interop
4106210  /init
      2  /init
      1  /sbin/init
```

The manager's pid (and the Claude Code process-tree root, 1794003) appear **nowhere**. `wt.exe` returns
`0` immediately after handing the request to Windows Terminal; the worker is parented to WSL's interop
`init`, in its own session and process group. **Killing the manager cannot kill a worker.** No `setsid`,
no `nohup`, no `disown` needed — orphan-safety is structural.

### 3.5 Failure modes

| Mode | Detail | Mitigation |
|---|---|---|
| Quoting/`;` | §2. Silent: tab opens blank, `0x80070002` | Wrapper script; never inline `;` |
| Title hijack | opencode renames every tab "OpenCode" | `--suppressApplicationTitle` (mandatory) |
| `-w 0` follows GUI focus | Worker tab lands in whatever window was last clicked — **not** the manager's **[V]** | Never use `-w 0`; use `-w <name>` (§3.1b) |
| `-w $WT_SESSION` | Creates a NEW window — the GUID is a pane id, not a window id **[V]** | Never use it |
| `-w 1` is positional | Points at the *first-created* window; wrong after window churn | Prefer the named window |
| Bare `wt.exe --help`/`--version` | **Does not print to stdout** — opens a Help *dialog* and retitles a window. I did this twice by accident **[V]** | Never probe `wt.exe` for help from a script; read the docs |
| Window closed by operator | Next `-w <name>` silently creates a fresh window **[VD]** | Benign — self-healing |
| Tab closes when process exits | Verified: a 4s tab vanished on exit **[V]** | Wrap with a `read` if post-mortem inspection is wanted |
| Port collision | Second worker on a taken port | Allocate ports from a registry file, or `--port 0` + read back |
| Windows Terminal not running | First `-w <name>` starts it | None needed |

**Licence:** MIT (microsoft/terminal). **Setup cost: ZERO.** Nothing to install, no config change, no
`settings.json` edit. `--tabColor`/`--suppressApplicationTitle` are per-invocation flags.

---

## 4. Candidate #2 — tmux (best HEADLESS/detached complement, already installed)

**Spawn [V]:** `tmux -L <socket> new-session -d -s <name> -x 200 -y 50 '<cmd>'` → exit 0, and
`tmux capture-pane -p -t <name>` rendered the **full opencode TUI** correctly. tmux is a *proper* pty: it
answers the terminal capability queries (DA1, XTGETTCAP, DECRQM) that opencode's TUI blocks on. A naive
`pty.fork()` harness does **not** answer them and the TUI stalls mid-init — a real trap for anyone
scripting TUI capture **[V]**.

- **Unattended:** yes, perfectly. Pure Linux, no interop.
- **Watchable:** only after `tmux attach`. The operator must run one command to see a worker, and then
  lives inside tmux's own tab/pane model.
- **Naming/colour:** `new-window -n <name>`; per-window colour via `window-status-style` /
  `set -w window-status-current-format`; pane titles via `select-pane -T`. Real but **config-file work**,
  not a per-spawn flag — materially clunkier than `--title`/`--tabColor`.
- **Survives manager death:** yes — the tmux *server* is already detached from every client.
- **`send-keys` races:** prior research rejected `send-keys` for **control**, and that stands. But this
  task is **spawn**, and `new-session`/`new-window` take the command as **argv** — no keystroke
  simulation, no bracketed-paste, **none of the documented races apply**. Honest assessment: the
  send-keys objection does **not** transfer to spawning.
- **What the operator loses vs a native tab:** the Windows Terminal tab bar, per-tab colour at a glance,
  native mouse/scrollback/copy-paste (tmux intercepts these), and their font/theme behave differently
  inside tmux. For an operator who *actively watches tabs*, that is a real regression.

**Verdict: not #1 for watchability, but the right answer for workers that should keep running with
nobody looking** — and a zero-install fallback if Windows Terminal is ever not the front end.

## 5. Candidate #3 — `opencode serve` + `opencode attach` (the "spawn headless, attach to watch" ideal)

This is the shape the brief hoped for, and it **half** works.

**Verified [V]:**
- `setsid opencode serve --port 47701` → detached, `PPID 277` (init), `{"healthy":true}`.
- Created a session over HTTP, prompted it, it **ran to completion and produced output** — a fully
  working headless worker with no terminal at all.
- `opencode attach http://127.0.0.1:47701 --dir …` renders a **complete interactive TUI** (prompt box,
  agent tabs, model, `~/charon-private:master`, MCP indicator).
- **Killing the attached TUI did NOT kill the server or the work** — server stayed healthy. Attach and
  detach are free. That is *strictly better* than today's model, where closing a tab kills the worker.

**The gap [V]:** `opencode attach -s <sessionID>` **did not open the target session**. It opened a **new
empty session** — right-hand panel read `New session - …`, `0 tokens`, `$0.00 spent`, and the default
model `gpt-5.4`, not my session's `minimax-m3-free`, with none of its content. Reproduced twice (once in
a Windows Terminal tab, once under tmux). The flag exists in `--help` for 1.18.6 and there is an upstream
issue requesting exactly this (anomalyco/opencode#5445), so it is plausibly new/partial. **Not
production-ready for "operator, go watch worker #3".**

**Consequence:** the elegant `serve` + `attach -s` topology is **blocked on one upstream flag**. Until it
works, the `--port`-on-an-interactive-TUI shape (§3) is the one that delivers both properties today.
Worth re-testing on each opencode upgrade — if `-s` starts working, the architecture gets strictly better
(work becomes independent of any window, and the operator can attach/detach at will).

## 6. Candidate #4 — browser (`opencode web`, ttyd/gotty/wetty)

- **`opencode web`** ships in the binary (`start opencode server and open web interface`) **[VD]**, with
  `--cors` and `OPENCODE_SERVER_PASSWORD` basic auth **[VD]**. Vendor docs state a client "can be a
  terminal tab, your phone, a desktop, a browser — each … pointed at the same server, fully synced," and
  that TUI and browser can view the same session simultaneously **[VD]** — **not verified by me**.
- Spawning a worker becomes "open a URL", trivially scriptable and inherently orphan-safe.
- **Costs:** no tab bar / colour affordance the operator asked for; browser tabs instead of terminal
  tabs; a second UI paradigm alongside their terminal workflow.
- **ttyd / gotty / wetty:** all absent here, all require install + a per-worker daemon, and all merely
  re-expose a pty in a browser — strictly more moving parts than `wt.exe` for less integration. **Reject
  as #1**; `opencode web` is the only browser option worth a look, and only as a *supplement*.

## 7. Candidate #5 — WezTerm / Zellij / others

- **WezTerm** (MIT) is genuinely the closest cross-platform rival: `wezterm cli spawn --new-window`,
  `--window-id <N>`, `--cwd`, `wezterm cli list --format json` (enumerate windows/tabs → real programmatic
  targeting), `wezterm cli set-tab-title`, `wezterm cli send-text` **[VD]**. Its targeting story is
  arguably *better designed* than `wt`'s (`list` gives you ids to target deterministically). **But:**
  it is **not installed**, requires installing WezTerm on Windows **and** configuring a WSL domain, the
  operator would have to **abandon Windows Terminal**, and per-tab **colour** has no direct CLI flag —
  it needs a Lua `format-tab-title` config. **Adopting it would cost a terminal migration to gain
  nothing `wt.exe` doesn't already do on this box.** Correct answer only if the operator ever leaves
  Windows Terminal or needs the same script on macOS/Linux.
- **Zellij** (MIT): `zellij action new-tab --name <name>` — clean naming, good spawn CLI, but same class
  as tmux (multiplexer inside WSL, attach to watch), and **not installed**. No advantage over tmux here.
- **Alacritty / ConEmu:** no session-level spawn-into-existing-window CLI. ✗
- **systemd-user / supervisors:** solve *supervision*, not *watchability*. `wt.exe` already gives
  orphan-safety structurally (§3.4), so this buys nothing for the stated problem. Revisit only if
  auto-restart policy is wanted. ✗

## 8. Prior art in the agent ecosystem

Nothing to adopt. The frameworks surveyed in `RESEARCH-AGENT-COMMS-2026-07-26.md` §3.8 (AutoGen/AG2,
CrewAI, LangGraph, OpenAI Agents SDK, Letta, Ray) **all own the agent loop in-process**; none spawns a
*watchable terminal* per worker, because none of them assumes a human is watching. The one adjacent piece
of prior art, `obra/claude-session-driver`, drives *existing* sessions by keystroke and explicitly refuses
to scrape TUIs for state — it does not solve spawn either. **The "spawn N watchable worker terminals"
pattern is not something the ecosystem has productised; it is a terminal-emulator feature, and Windows
Terminal already has it.** Correctly, this is an *adopt* — just from Microsoft rather than from an agent
framework.

---

## 9. Ranked recommendation

**HARD REQUIREMENT** (operator, explicit): *tabs must land in the terminal window they are already
working in* — a spawner that can only create new windows is materially worse and is marked ✗ below.

| # | Option | Unattended | **Tab in operator's EXISTING window** | Operator watches | Name | Colour | Survives mgr death | Install |
|---|---|---|---|---|---|---|---|---|
| **1** | **`wt.exe -w charon-fleet new-tab` + wrapper** | **✅ [V]** | **✅ MET** — `-w 1` verified into their window **[V]**; `-w <name>` after one-time rename | **✅ native tab [V]** | **✅ [V]** | **✅ [V]** | **✅ [V]** | **none** |
| 2 | tmux | ✅ [V] | ✗ **NOT MET** — tmux windows are inside a tmux client, not WT tabs | ⚠ must attach; loses native tab UX | ✅ | ⚠ config, not flag | ✅ | none |
| 3 | `opencode serve` (+ web UI) | ✅ [V] | ✗ **NOT MET** — no terminal at all | ⚠ browser, or blocked on `attach -s` [V] | n/a | ✗ | ✅ [V] | none |
| 4 | WezTerm `cli spawn --window-id` | ✅ [VD] | ⚠ **only in WezTerm** — cannot put a tab in a Windows Terminal window; requires abandoning WT | ✅ | ✅ [VD] | ⚠ Lua only | ✅ [I] | **terminal migration** |
| 5 | Zellij | ✅ [VD] | ✗ NOT MET | ⚠ attach | ✅ [VD] | ⚠ | ✅ [I] | new package |
| ✗ | ttyd/gotty/wetty, Alacritty, ConEmu, systemd-user | — | ✗ NOT MET | — | — | — | — | more parts, less integration |

**Only `wt.exe` meets the hard requirement.** Every alternative either spawns into its *own* UI (tmux,
Zellij, WezTerm, browser) or has no UI at all (`serve`). This is not a close call and it is not a matter
of preference: nothing except Windows Terminal's own CLI can insert a tab into a running Windows
Terminal window. Rankings 2–5 remain useful only for the *headless* case (§9, below the table).

**Two options serve two different cases, and both should exist:**
- **`wt.exe` — the default**, for every worker the operator wants to watch. Full marks on all axes, zero install.
- **`opencode serve` (detached, no terminal) — for genuinely headless work** (canaries, long grinds,
  batch jobs) that nobody should have to look at. Already proven end-to-end **[V]**; drive it entirely
  through `session-ctl.sh`.

tmux is the **fallback**, not the plan: it is the answer if Windows Terminal is ever not the front end.

---

## 10. Model selection — a launcher rule, not a spawn detail

Spawning works; **model choice is now the failure surface.** The `T-SPAWN-01` tab came up correctly and
then the *model* returned `all providers exhausted [retrying in 33s]`.

- **NEVER default to a FREE-tier leg for a working session.** Free tiers pass a one-shot probe and
  collapse under a real session's request volume.
- **Sustained-capable now:** `deepseek-v4-pro`, `deepseek-v4-flash` (deepseek direct),
  `minimax-m3-together` (together) — clean served/failed ratios.
- **Avoid for sustained work:** `minimax-m3-free` (nvidia free leg), `gemini-3.1-pro` (aistudio free tier).
- **NEVER the opencode default `gpt-5.4`** — pool `[nanogpt, openrouter]`, both 429/402. A defaulted
  model is how an entire fleet lands on a dead pool simultaneously.
- **The launcher must take `--model` as a REQUIRED parameter with NO fallback default.** `launch-worker.sh`
  above uses `${2:?model}` precisely for this: it fails loudly rather than defaulting.
- **A one-shot 200 probe does NOT prove a model can carry a session.** Any pre-spawn health check built on
  single-request success will greenlight free tiers that die 30 seconds later. If a preflight is added it
  must measure *sustained* behaviour (served/failed ratio over a window, per `model-scorecard.tsv` live
  lane), never a single ping.

Corroborates the standing `benchmark-not-a-valid-ranker` and `latency-is-a-failure-class` directives.

---

## 11. Smallest spike to prove it (~1–2 hours, well under a day)

Spawn is already proven; the spike is to **productise it into the launcher**, not to re-prove it.

1. **`fleet/launch-worker.sh`** (~10 lines) — `$1` ticket, `$2` model (**required, no default**),
   `$3` port. `cd /home/stack/charon-private && exec opencode --port "$3" --model "charon/$2"`.
   Run `fleet/reuse-check.sh` against the path first.
2. **`fleet/spawn-worker.sh`** (~20 lines) — allocate a free port, pick a colour by work class
   (e.g. red=fix, green=feat, blue=review), then:
   ```bash
   wt.exe -w "${CHARON_WT_WINDOW:-charon-fleet}" new-tab \
     --title "$TICKET · $MODEL" --tabColor "$COLOR" --suppressApplicationTitle \
     wsl.exe -d Ubuntu-24.04 -- bash -lc "/home/stack/charon-private/fleet/launch-worker.sh $TICKET $MODEL $PORT"
   ```
   `CHARON_WT_WINDOW` lets the operator set `1` (zero-setup fallback) or any window name without a code
   change — and keeps the Windows-specific value out of the script, per `no-hardcoded-cross-boundary-paths`.
   Append `name → (ticket, model, port, pid)` to a registry file — this is the `name → port` registry the
   prior research already identified as launcher-owned (**not** a thing an agent calls).
3. **Push the opening prompt over HTTP, not the CLI.** `--prompt` is **unverified as an auto-submit**:
   the flag is accepted and appears in `argv`, but I saw **no session created and no messages** from it
   **[V]**. Use the already-verified path instead — `session-ctl.sh <url> launch <agent> <model> <text>`
   (`POST /api/session` → `POST …/prompt`). Belt-and-braces, and it keeps the opening instruction in the
   transport rather than in a fragile CLI flag.
4. **Acceptance (all five):**
   - three `spawn-worker.sh` calls → **three tabs, one window**, three distinct names and colours;
   - each tab's `/api/health` answers on its port, and `session-ctl.sh … list` addresses it;
   - the manager pushes the opening prompt and it appears **in the tab** the operator is watching;
   - the operator types into a tab and it works (interactive, not a viewer);
   - **kill the manager session → all three tabs keep running** (structurally guaranteed by §3.4, but
     assert it once).
5. **Then:** point `fleet-droid.sh` at `spawn-worker.sh` so the operator stops opening tabs by hand.

**Explicitly NOT in the spike:** `attach -s` (upstream-blocked, §5), WezTerm migration, browser UI,
tmux (fallback only).

---

## 12. Honest statement of what is LOST vs today's manual tab

**Essentially nothing — this is close to a pure win, which is rare enough to be worth stating plainly.**

1. **The operator's chosen profile/font/theme.** `new-tab` with an explicit `commandline` uses the
   *default* profile, not whichever one they normally pick. Fixable with `-p "<profile>"`, but it must be
   passed deliberately. **[I]** — untested.
2. **`--tabColor` colours the tab, not the terminal background.** A failed vs finished worker is
   distinguishable by tab colour only if the launcher *changes* it — and `wt` has no
   "recolour an existing tab" verb. Colour is assigned at spawn, so it can encode **work class**, not
   **live status**. Live status must come from `session-ctl.sh` / the `/api/event` SSE stream. This is a
   genuine limit on requirement 3 and should be stated to the operator.
3. **`--prompt` auto-start is unproven** (§11.3) — mitigated by pushing the prompt over HTTP.
4. **Windows-only.** The `wt.exe` path does not port to a Linux or macOS box. tmux is the portable
   fallback; WezTerm is the portable *equivalent* if portability ever becomes a requirement.
5. **A one-time window rename** (Ctrl+Shift+P → "Rename window" → `charon-fleet`). This is the *entire*
   setup cost of the recommendation. It is done in place, needs no relaunch, and does not disturb the
   running manager session. If the operator later closes that window, the next spawn recreates it by
   name automatically. Choosing `-w 1` instead removes even this, at the cost of positional fragility.
5. **Not lost, gained:** every spawned worker now binds `--port`, so `session-ctl.sh`'s five control verbs
   work against it — which the current hand-launched workers **do not have** (verified: the live worker
   pid 3913454 binds no port). Spawning via the launcher is what finally makes the control plane universal.

---

## 13. Reproduce / clean-up statement

**ONE-TIME operator setup (5 seconds, no relaunch, session preserved):**
in the manager's Windows Terminal window press **Ctrl+Shift+P** → type **"Rename window"** → enter
**`charon-fleet`**. (Ctrl+Shift+P → "Identify window" shows the current name and index if you want to
confirm.) Skip this and use `CHARON_WT_WINDOW=1` instead — verified working, but positional.

```bash
# spawn three named, coloured worker tabs INTO THE OPERATOR'S EXISTING WINDOW
W="${CHARON_WT_WINDOW:-charon-fleet}"      # or: W=1  (zero-setup fallback, verified [V])
for i in 1 2 3; do
  wt.exe -w "$W" new-tab \
    --title "T-$i · deepseek-v4-flash" --tabColor "#27AE60" --suppressApplicationTitle \
    wsl.exe -d Ubuntu-24.04 -- bash -lc "/home/stack/charon-private/fleet/launch-worker.sh T-$i deepseek-v4-flash 478$i"
done
# then drive them (spawn was the only missing verb; control already works)
fleet/session-ctl.sh http://127.0.0.1:4781 list
fleet/session-ctl.sh http://127.0.0.1:4781 steer <session-id> "switch to ticket X"
```

Enumerating Windows Terminal windows (a single process hosts them all, so `MainWindowTitle` is useless —
you need `EnumWindows` filtered to `CASCADIA_HOSTING_WINDOW_CLASS`): see the PowerShell snippet pattern
in §3.1; it is the only reliable way to *verify* tab-vs-window behaviour from a script.

**Clean-up performed and verified [V].** Killed only processes I created (2 opencode servers on 47701/47801,
4 probe scripts, my private `tmux -L charonprobe` server); deleted the test session I created; closed my
two probe windows and the two Help dialogs I accidentally opened; removed the temporary PowerShell file
from the Windows profile. Final window enumeration shows **only the operator's own window remaining**.
**The operator's live worker (pid 3913454) and all 5 session-bridge processes were confirmed intact
before and after.** No session I did not create was touched, interrupted, or sent input.

---

## 14. Open questions / not verified

- `opencode attach -s <sessionID>` loading an existing session — **fails today** (§5). Re-test each upgrade.
- `opencode --prompt` auto-submitting in TUI mode — no evidence it fired **[V]**; use HTTP instead.
- `--tabColor` rendering was accepted without error and applied per tab, but I could not read the colour
  back programmatically — visual confirmation is the operator's (they have since confirmed colours applied).
- `-p "<profile>"` to preserve the operator's font/theme — untested **[I]**.
- `opencode web` browser client and multi-client session sharing — **[VD]** only, not run.
- Cross-host spawn (4-LOM). `wt.exe` is local-Windows-only; a remote worker would need
  `ssh host opencode serve` + local attach, i.e. the §5 topology, which is blocked on `attach -s`.

## Sources

- [Windows Terminal command line arguments](https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments) — `-w`, `new-tab`, `--title`, `--tabColor`, `--suppressApplicationTitle`, `;` separator
- [OpenCode — Server](https://opencode.ai/docs/server/) · [OpenCode — Web](https://opencode.ai/docs/web/)
- [anomalyco/opencode#5445 — `--session` flag for `opencode attach`](https://github.com/anomalyco/opencode/issues/5445)
- [wezterm cli spawn](https://wezterm.org/cli/cli/spawn.html) · [wezterm cli](https://wezterm.org/cli/cli/index.html)
- Prior in-repo research: `fleet/handoff-notes/RESEARCH-AGENT-COMMS-2026-07-26.md`,
  `fleet/handoff-notes/SPIKE-SESSION-CTL-2026-07-26.md`, `fleet/session-ctl.sh`

---

# ADDENDUM — pushing the opening prompt into a spawned TUI (2026-07-27, follow-up)

**ANSWER: the recipe EXISTS and is verified. No human keystroke is required.**
`POST /tui/append-prompt` + `POST /tui/submit-prompt`, **against the worker's own port**, after a
readiness gate. Not "one pasted line per tab" — zero pasted lines.

This also **corrects a conclusion in `RESEARCH-AGENT-COMMS-2026-07-26.md`**, which said *"Do not build on
`/tui/*`; use `/api/session/{id}/prompt`."* That was measured on a **headless `opencode serve`, where no
TUI exists** — so of course the events went nowhere. With a real TUI attached (`opencode --port N`), the
`/tui/*` endpoints are exactly the right mechanism, and `/api/session/{id}/prompt` is the wrong one.

## A. Why `session-ctl.sh launch` produced a dead session

`launch` does `POST /api/session` → `POST /api/session/{id}/prompt`. Both succeed, and both are
irrelevant to the TUI. **The TUI owns its own session and will not adopt an externally-created one** —
the same law behind the `attach -s` failure in §5. `POST /api/session` writes into the **global store**;
no TUI is driving that row, so nothing executes and the title never gets generated. `admittedSeq:1` means
*"durably written"*, **not** *"a TUI is running it"*. Confirmed **[V]**: manager-created session
`ses_05e58f394ffe…` still had **0 messages** after a full round-trip, while the TUI ran the same prompt in
a session of its own.

**Corollary: do not use `session-ctl.sh launch` against a TUI worker.** It silently creates orphan rows.

## B. The four questions, answered

**1. Does the TUI create its session lazily? — YES, and there is no pre-turn id. [V]**
A freshly spawned TUI has **no** session. One appears in the store at the *instant of first submit*
(observed: injection at 03:37:14 → `New session - 2026-07-27T03:37:14.577Z`). So there is **no session id
addressable over HTTP before the first turn** — which is precisely why any id-based approach cannot start
a TUI worker. `--prompt` does not create one either (§14).

**2. Which global session belongs to THIS port's TUI? — NOT DISCOVERABLE, and NOT NEEDED. [V]**
I searched all **162 paths** in the live OpenAPI spec: there is **no per-server "current session"
endpoint**. `/api/session` and `/api/session/active` are global-store reads. `GET /api/event` on the
worker's port yields **only `server.connected`** — no `sessionID` for the TUI's own turns, with or
without `?directory=` (96 bytes of stream across two attempts) **[V]**. `POST /tui/select-session`
returns `true` but does **not** redirect the turn into the given session **[V]** — same law as (A).

**The reframe that dissolves the problem: address workers by PORT, not by session id.** `/tui/*` is
port-scoped, and `port → worker` is a 1:1 mapping the launcher already owns and already records. The
manager never needs the session id to start work or to send follow-ups.

**3. Does injection work once a turn has started? — YES, admitted mid-turn. [V]**
Fired a long counting turn, then injected `STOP counting. Reply only: MIDTURN-STEER-OK` at +6s; the
directive was admitted and appears in the conversation. **Caveat, stated honestly:** the counting turn
finished at 8.0s, so I could **not** distinguish *interrupts the current turn* from *queues behind it*.
For guaranteed mid-turn interruption the verified mechanism is still the prior spike's
`POST /api/session/{id}/prompt {"delivery":"steer"}` — which needs a session id, so it applies to
**headless** workers, not TUI workers. For TUI workers, treat `/tui/*` as *at-least-queued*.

**4. Is there a flag that runs an initial prompt? — NO. [V]** `--prompt` is accepted, appears in `argv`,
and is **inert**: no session, no messages, TUI sits on the splash. The `/tui/*` pair is the mechanism.

## C. THE TRAP — `/tui/*` returns `true` unconditionally

**`true` is not an acknowledgement. It means "event published", not "a TUI received it".** This is what
makes the failure look like success, and it is the single thing most likely to cost another round.

Proof **[V]**: `POST /tui/execute-command` returned `true` for `session_interrupt`, `interrupt`, `abort`,
`session_abort`, `app_exit` **and `messages_abort`** — six strings, at least some pure nonsense, all
`true`. There is no validation and no delivery guarantee anywhere on `/tui/*`.

**The real failure was a race, not a bug.** Identical injections:

| Attempt | Timing | `true`? | Turn ran? |
|---|---|---|---|
| Worker `t2`, ~10s after spawn | early | `true` | **NO** — 0 messages, TUI on splash |
| Worker `t2`, same commands minutes later | warm | `true` | **YES** |
| Worker `t4`, **after readiness gate** | gated | `true` | **YES, first try** |

`GET /api/health` returns `{"healthy":true}` **before the TUI client has attached** — the HTTP server
comes up first, the TUI connects after. Injecting in that window is silently discarded. **This is almost
certainly what bit the four production tabs.**

## D. The readiness gate (the missing piece) — VERIFIED

A TUI client attaches to its own server over loopback. So *"is a TUI attached?"* is answerable:

```bash
ss -tn state established "( sport = :$PORT or dport = :$PORT )" | tail -n +2 | wc -l
```

| Process | established conns |
|---|---|
| `opencode --port N` (TUI worker) | **18–36** |
| `opencode serve --port N` (headless, no client) | **0** |

Gate on `health == healthy` **AND** `established > 0`. Measured ready **5s** after spawn, and the
first-try injection then succeeded immediately **[V]**.

## E. THE RECIPE — spawn a tab already working on its ticket, no keystroke

```bash
# 1. spawn the watchable tab (unchanged, already in production)
wt.exe -w "${CHARON_WT_WINDOW:-1}" new-tab \
  --title "$TICKET · $MODEL" --tabColor "$COLOR" --suppressApplicationTitle \
  wsl.exe -d Ubuntu-24.04 -- bash /home/stack/charon-private/fleet/launch-worker.sh "$TICKET" "$MODEL" "$PORT"

# 2. READINESS GATE — health alone is NOT enough
for i in $(seq 1 60); do
  h=$(curl -s --max-time 2 "http://127.0.0.1:$PORT/api/health" 2>/dev/null)
  n=$(ss -tn state established "( sport = :$PORT or dport = :$PORT )" 2>/dev/null | tail -n +2 | wc -l)
  [ "$h" = '{"healthy":true}' ] && [ "$n" -gt 0 ] && break
  sleep 1
done
sleep 2                    # small settle after the client attaches

# 3. inject the opening prompt INTO THE TUI (port-addressed; no session id anywhere)
curl -s -X POST "http://127.0.0.1:$PORT/tui/append-prompt" \
     -H 'content-type: application/json' \
     -d "$(python3 -c 'import json,sys;print(json.dumps({"text":sys.argv[1]}))' "$PROMPT")"
curl -s -X POST "http://127.0.0.1:$PORT/tui/submit-prompt" \
     -H 'content-type: application/json' -d '{}'

# 4. VERIFY — never trust the `true`
sleep 8
curl -s "http://127.0.0.1:$PORT/api/session?directory=$DIR" \
  | python3 -c 'import sys,json,time;d=json.load(sys.stdin)["data"];now=time.time()*1000;print("started" if any(now-s["time"]["created"]<60000 for s in d) else "NOT STARTED — retry")'
```

Verified end to end **[V]**: gate reported ready at 5s, one `append`+`submit`, and the tab rendered
`Reply with exactly: FIRSTTRY-OK` → `FIRSTTRY-OK` → `Build · deepseek-v4-flash · 1.8s`, with **no
keystroke**. Repeated successfully on a second worker (`TUIPROMPTWORKS`, 2.3s).

Step 4 matters because the gate is a heuristic: on a miss, re-run step 3 (it is safely repeatable — a
dropped injection leaves no state). Prefer verify-then-retry over a longer blind sleep.

## F. Changes to make

1. **`session-ctl.sh`: `launch` must not be used on TUI workers.** Either make it port-addressed
   (`append-prompt` + `submit-prompt` + verify) or rename it `launch-headless` and add
   `start <port> <prompt>` for TUI workers. As written it silently manufactures orphan sessions.
2. **`spawn-worker.sh`: add the readiness gate and the post-injection verify.** Without both, spawn is a
   race that fails silently and looks like success.
3. **Two worker classes, two control paths — do not mix them:**

   | | **TUI worker** (`opencode --port N`) | **Headless worker** (`opencode serve`) |
   |---|---|---|
   | Operator can watch | **yes** | no |
   | Addressed by | **port** | session id |
   | Start work | `/tui/append-prompt` + `/tui/submit-prompt` | `POST /api/session` → `POST …/prompt` |
   | Follow-up | same pair (at-least-queued) | `{"delivery":"steer"}` — verified mid-turn |
   | Hard stop | not verified via `/tui/*` | `POST …/interrupt` — verified |

4. **Open, worth one cheap test later:** whether any `/tui/execute-command` string performs a real
   interrupt. Because the endpoint returns `true` for everything, discovering the valid command names
   requires reading opencode's TUI command registry in source — not probing. Until then, a TUI worker has
   **no verified hard-stop**, which is the one genuine capability gap versus headless workers.

## G. Clean-up

Killed all four test workers (ports 47901/47902/47903/47904) and my private `tmux -L cp2` server;
no residual processes on 479xx. The operator's worker (pid 4102750, `--port 47099`) was confirmed intact
afterwards. Test sessions created during this addendum remain as inert rows in the global store.

---

# ADDENDUM 2 — STOPPING a TUI worker, and the FOCUS-STEAL fix (2026-07-27, third round)

Scope: how a manager reliably STOPS a spawned opencode TUI worker; plus the newly-raised
requirement that a spawn must not steal the operator's keyboard focus.
Method: every claim below was produced on workers **I spawned myself** on ports 47901/47902/
47904/47905/47906/47907/47908/47911. The operator's live workers (47201-47205, 47099) were never
signalled. `[V]` = verified by execution, `[I]` = inferred, stated as such.

## H. The `/tui/execute-command` question is CLOSED — and the answer is NO

The previous round could not enumerate valid command names because every string returns `true`.
They are now enumerated **from the binary**, not probed:

```bash
strings -n 6 /home/stack/.local/lib/node_modules/opencode-ai/bin/opencode.exe \
  | grep -oE 'app_exit:"app.exit".{0,4500}' | tr ',' '\n'
```

This dumps opencode's whole keybind→command map. The canonical ids are **dot-separated**, not
underscore: `app.exit`, `session.interrupt`, `session.new`, `prompt.submit`, `session.compact`,
`session.export`, `model.list`, … (~150 entries). Every string the previous round tried
(`app_exit`, `session_interrupt`, `messages_abort`) was the **keybind name**, not the command id —
which is why they all silently no-op'd.

**But the correct ids do not work either. [V]** On worker 47901:

| Sent to `/tui/execute-command` | Response | Actual effect |
|---|---|---|
| `app.exit` (canonical id) | `true` | **none** — pid alive, port still listening, 3 attempts |
| `app.exit` after `/tui/clear-prompt` | `true` | **none** (rules out the "input must be empty" keybind guard) |
| `app_exit`, `app.quit`, `quit`, `exit` | `true` | none |
| `session.interrupt` mid-turn | `true` | **none** — the turn ran on for a further ~110s to completion |
| `session.new` | `true` | none observable |
| `prompt.submit` (with text staged) | `true` | **none** — no turn started; `/tui/submit-prompt` is what works |

**Conclusion [V]: `/tui/execute-command` is inert on opencode 1.18.6. There is NO HTTP stop —
neither a quit nor a turn-interrupt — for a TUI worker.** `/tui/append-prompt` + `/tui/submit-prompt`
remain the only `/tui/*` endpoints with demonstrated effect. Stop must be done at the OS level.
This closes the open question from Addendum §F.4; do not spend another round probing it.

## I. THE STOP LADDER — verified, and it is the simple answer

Port→PID→signal. Nothing fancier is needed or better.

```bash
stop_worker() {                       # $1 = worker port
  local P="$1" PID
  PID=$(ss -lptnH "sport = :$P" | grep -oP 'pid=\K[0-9]+' | head -1)
  [ -n "$PID" ] || { echo "no listener on $P — already stopped"; return 0; }

  kill -INT  "$PID"                                   # 1. graceful — the TUI's own ctrl+c path
  for i in $(seq 1 5); do sleep 1; kill -0 "$PID" 2>/dev/null || break; done
  kill -0 "$PID" 2>/dev/null && kill -TERM "$PID"     # 2. still graceful, also exits 0
  for i in $(seq 1 5); do sleep 1; kill -0 "$PID" 2>/dev/null || break; done
  kill -0 "$PID" 2>/dev/null && kill -KILL "$PID"     # 3. last resort — leaves a dead tab

  sleep 1                                             # 4. VERIFY — both conditions, never one
  local code; code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
                     "http://127.0.0.1:$P/api/health")
  if ! kill -0 "$PID" 2>/dev/null && [ "$code" = "000" ]; then
    echo "STOPPED port=$P pid=$PID (pid gone, connection refused)"
  else
    echo "STOP FAILED port=$P pid=$PID alive=$(kill -0 "$PID" 2>/dev/null && echo y || echo n) http=$code"
    return 1
  fi
}
```

Measured behaviour, one worker per signal, each spawned by me:

| Signal | Died in | Exit code | Port after | Own `proxy.py` child | WT tab |
|---|---|---|---|---|---|
| `kill -INT`  (47905) | **<1s** [V] | **0** [V] | refused (`000`) [V] | reaped [V] | **closes** [V] |
| `kill -TERM` (47901, 47902 mid-turn, 47906, 47907, 47908) | **<1s** [V] | **0** [V] | refused (`000`) [V] | reaped [V] | **closes** [V] |
| `kill -KILL` (47904) | <1s [V] | 9 (as WSL reports it) [V] | refused [V] | reaped, but see §K | **stays** at `[process exited with code 9] … press Enter to restart` [V] |

Exit codes were captured by running the identical wrapper under a pty
(`setsid script -qc "bash run.sh; echo EXITCODE=\$? >> f" /dev/null`) and signalling it — so the
`0` is opencode's real exit status, not a guess. **SIGTERM is sufficient; SIGKILL was never needed
in any test.** SIGKILL should be the timeout fallback only, and its use is self-announcing because
it is the only case that leaves tab litter.

Tab behaviour is now VERIFIED, not inferred: after the test run, window 1 contained **zero**
KILLTEST tabs (all SIGTERM/SIGINT, exit 0 → auto-closed) while the two tabs whose payload was
SIGTERM'd `sleep` (exit 143) **remained** at the dead-shell prompt. The rule is
`closeOnExit`, whose WT default is `graceful` = *close iff exit code 0*; the operator's
`settings.json` (…`Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json`, 3251 bytes)
contains **no `closeOnExit` key**, so the default is in force. **`closeOnExit` is a PROFILE setting
with no `wt new-tab` CLI equivalent [I, from schema + absence of any accepted flag], so per-spawn
control is not available — but it is also not needed: exit 0 already closes the tab.** The correct
fix for dead-tab litter is therefore "use the ladder, don't lead with `kill -9`", not a settings change.

### Is a hard kill safe? YES — established, not assumed [V]

* State lives in **`~/.local/share/opencode/opencode.db` — SQLite in WAL mode** (`opencode.db-wal`
  18 MB, `-shm` present). WAL is crash-atomic by construction; an untrapped kill is exactly the case
  it is designed for.
* After a mid-turn SIGTERM **and** a SIGKILL, a freshly started `opencode serve` read the store
  cleanly: `GET /api/session` returned all **50** sessions including the killed worker's row, with
  valid JSON and no error. No repair, no corruption. [V]
* The **other four live workers on 47201-47204 kept serving throughout** — all still `LISTEN`,
  all still healthy. Killing one worker does not disturb siblings sharing the db. [V]
* What IS lost: the **in-flight turn**. The killed session's row shows `tokens {0,0,0}` and
  `cost 0` — the partial assistant output was never committed. A completed turn on the same worker
  had recorded `output: 8914, cost: 0.0038`. So: **a kill loses the current turn and nothing else.**
  Cheap to redo; not a data-integrity risk.

### Do NOT use `pkill -f`
`pkill -f -- "--port 47901"` matches on the port string, which looks precise, but the pattern also
matches any wrapper/`script`/shell whose argv contains it, and a mistyped port silently matches
nothing (exit 1) — indistinguishable from "already dead". `ss`→PID→`kill` gives you the pid to
verify against. Prefer it. [I, reasoned; not required in testing because the ladder always worked]

### Process groups / `setsid` — not needed
Each worker already **is** its own process-group and session leader: `PGID == SID == PID`
(e.g. pid 183807 → pgid 183807, sid 183807), because `wsl.exe -d … -- bash wrapper` gets a fresh
session per interop invocation. So `kill -- -$PID` is available for free as a group sweep with no
pidfile and no wrapper change. It was **not necessary** — SIGTERM to the leader already reaped the
`proxy.py` child in every test. Keep it in reserve, see §K.

## J. Consuming the bridge's liveness signal instead of growing a second one

Per the coordinator's correction, this section does **not** propose a new liveness mechanism.
What was verified:

* `/api/event` (SSE) on an **actively-working TUI worker** emits **only `server.connected`** — 45 s
  of capture across a live turn produced 1 event. It is not a progress channel. [V]
* `GET /api/session/{id}/message` returns `{"data":[]}` **even for a session with 54 481 output
  tokens**, on every port tried. Message/part counts are not obtainable. [V]
* A session's `tokens` and `time.updated` **freeze for the whole duration of a turn** and jump only
  at turn end (observed: frozen at `out 647 / dt 53958` for 40 s while a turn ran, then jumped to
  `out 8914 / dt 181111`). So the session record is a *completion* signal, never a *progress* one. [V]
* **`GET /api/session` is GLOBAL, not per-port.** Every worker serves the same shared
  `opencode.db`, so a session list fetched from port X includes sessions created on ports Y and Z.
  Any "is *my* worker busy" logic built on it is wrong by construction. [V]
* Therefore the port-based API offers **no reliable working/idle/stuck discriminator**. Stated
  plainly, as requested: a verified *we cannot tell from the port*.

**The gap is registration, not detection. [V]** `board(repo=charon)` during this session returned
exactly **2** sessions — both manager sessions — while **five** opencode workers were live on
47201-47205. None of the spawned TUI workers appear on the board, so the bridge's existing
`stall_seconds` / `stalled` / `lease_expires_at` / auto-nudge machinery — which
`fleet/board/DROID-LIFECYCLE-REAP.md` documents working correctly on a 12.6-hour-dead manager —
simply has nothing to act on for them.

The mechanism to reuse is already wired and already correct:

* Every worker runs `session-bridge/proxy.py` as a child (`~/.config/opencode/opencode.json` →
  `mcp.session-bridge`), so the control path exists on every spawn. [V]
* `proxy.py` registers `atexit` plus **`SIGTERM` and `SIGINT` handlers** (`proxy.py:185-192`) whose
  `_cleanup` calls `unregister`. So the §I ladder's graceful rungs are exactly the ones that let a
  worker **release its board row and its ticket on the way out**; `kill -9` skips cleanup and leaves
  the row to expire via the bridge's own lease TTL. Another reason not to lead with SIGKILL. [V]
* Registration is **model-elective** and models don't do it — a worker instructed by injected prompt
  to call `register` produced a session titled "KILLTEST-BRIDGE registration for charon" yet never
  appeared on the board. [V]

**Recommendation (single liveness notion, per DROID-LIFECYCLE-REAP):** have **`spawn-worker.sh`
register the worker on the operator's behalf at spawn time** — the harness registering, not the
model — carrying `session_id`, `pid`, port and ticket. Everything downstream (stall detection,
nudges, expiry, and any future reaper deciding *whether* to run the §I ladder) then consumes the
bridge signal that already exists. Do **not** build a port-poller. No second liveness notion.

## K. Two incidental hazards found while killing things

1. **opencode spawns a Windows `scoop install opencode@1.18.5` child.** Seen on worker 47904:
   `/bin/sh /mnt/c/Users/…/scoop/shims/scoop install opencode@1.18.5` as a direct child of the
   worker — an auto-update that would *downgrade* the running 1.18.6. It runs in **its own process
   group**, so it survives `kill -9 $PID` *and* `kill -- -$PGID`; after the kill it reparented and
   kept running a PowerShell install. I killed it manually. **A stop routine should sweep for
   `[s]coop.*opencode` strays after stopping a worker**, and the auto-updater is worth disabling
   outright. [V]
2. **`~/.local/share/opencode/opencode.db` is 6.9 GB.** Shared by every worker. Not implicated in
   any failure here, but it is on the critical path of every spawn and every session read. [V]

## L. FOCUS STEAL — measured, and fixed

### The measurement rig (reusable)
Windows Terminal sets its **window title to the active tab's title**, so the foreground *tab* is
readable programmatically via `GetForegroundWindow` + `GetWindowText`. A 40 ms-resolution PowerShell
sampler makes focus steal an objective measurement instead of an opinion. This is how A/B/C were
separated; keep the technique.

### Results

| Variant | Form | Steal measured | Operator verdict |
|---|---|---|---|
| **A** | `wt -w 1 new-tab …` (today's `spawn-worker.sh`) | new tab foreground for **≥1.5 s** [V] | steals — unusable |
| **B** | spawn into a *separate* window `-w charonw`, then `SetForegroundWindow(orig)` from PowerShell | **750 ms–1.25 s** [V] | steals |
| **C** | `wt -w 1 new-tab … ';' focus-tab -t <IDX>` — one invocation | **one 40 ms sample per spawn** [V] | **"did not steal the focus"** |

**Why C works and A/B do not — the mechanism, not the syntax.** `wt.exe` executes a chained action
list **inside a single invocation, in the target window, before the window settles**. `new-tab`
selects the new tab and `focus-tab -t IDX` re-selects the operator's tab as part of the same
command, so the new tab is never the input target for a perceptible interval. B fails for a
different reason: it targets a **different window**, so the cost is a *window activation* — a
Win32-level focus change that an out-of-process `SetForegroundWindow` can only undo *after* the
fact, hence the ~1 s hole. A fails because nothing restores focus at all.
Note the corollary: **C's guarantee only holds when the operator is in the SAME window being
targeted (`-w 1`).** If they are typing in a *different* WT window, `-w 1` raises window 1 and C
degrades to the B failure mode. The operator does keep more than one WT window open — this is the
known limit of C. [V/I]

### Back-to-back fan-out — tested, 4 spawns in immediate succession [V]
40 ms sampling across ~625 samples: **exactly 5 samples showed a FANTEST tab focused** (one per
spawn, one spawn showing two), at t=1905/1995/2089/2135/2182 ms — i.e. ~40-90 ms each, and focus
was back on the operator's tab between every spawn and at the end. **The refocus does not lose the
race under a 4-tab fan-out.** It is **not** literally zero: a keystroke landing inside that ~40-90 ms
window would go to the new tab. Honest ceiling, ~1 keystroke per spawn in the worst case.
*Not tested:* the operator actively typing at the instant of spawn, and the operator switching tabs
mid-sequence — neither is simulable from here. Both should be exercised once in real use.

### How C learns the index — the fragile part, stated explicitly
`focus-tab -t` takes an **absolute, 0-based index within the `-w` window**. It is not relative and
there is no "previous"/MRU form that reliably means *the tab the operator was on*. In testing,
index `0` happened to be the operator's tab, which is why C looked perfect.
The manager can **enumerate** the map — `wt -w 1 focus-tab -t $k` then read the foreground title,
for k=0,1,2,… (indices past the last tab are no-ops, which is how you find the count) — but that
**flips through the operator's tabs visibly** and is not acceptable on the spawn path. So:
make it configuration, default 0, e.g. `CHARON_WT_HOME_TAB` set once by the operator.
Tabs are always **appended at the end**, so a low home index stays stable as workers are added.

### Exact line for `fleet/spawn-worker.sh`
Replace the final `"$WT" …` invocation with:

```bash
"$WT" -w "$WINDOW" new-tab --title "$NAME" --tabColor "$COLOR" --suppressApplicationTitle \
      wsl.exe -d Ubuntu-24.04 -- bash "$RUN" \
      ';' focus-tab -t "${CHARON_WT_HOME_TAB:-0}"
```

The `';'` must be a **quoted, standalone argv element** — unquoted, bash eats it; unseparated,
`wt` folds it into the payload. Everything already won is preserved: tab lands in the operator's
existing window, named, coloured, `--suppressApplicationTitle`, running `opencode --port N --model
charon/M` via the wrapper, and injectable after the Addendum-§D readiness gate.

## M. tmux-in-one-WT-tab — the option that removes the focus mechanism entirely [V]

Re-evaluated on the corrected topology (ONE WT tab → one tmux session → workers as tmux *windows*),
and it tests better than its earlier ranking implied. tmux **3.4** is installed. `libtmux` is **not**
installed (`import libtmux` → ImportError); plain `tmux` CLI was sufficient for everything below, so
adopting libtmux would be adding a dependency for no verified gain.

```bash
tmux new-session -d -s workers -n manager 'bash -i'
tmux new-window -d -n "W-47911" \
     "cd /home/stack/charon-private && exec /home/stack/.local/bin/opencode --port 47911 --model charon/deepseek-v4-flash"
tmux setw -t W-47911 window-status-style 'fg=colour196,bold'   # per-window colour
tmux attach -t workers                                          # operator watches; Ctrl-b <n> to switch
```

Verified [V]:
* **`new-window -d` = zero focus change.** `display-message -p '#{window_index}:#{window_name}'`
  read `0:manager` before the spawn, immediately after it, and after the worker came up. There is
  no flicker to measure because nothing at the Windows level is created. This *eliminates* the
  mechanism rather than narrowing the window to 40 ms.
* opencode's TUI runs correctly inside tmux — readiness gate passed at **4 s** with **18**
  established loopback connections (a real TUI client attached).
* `/tui/append-prompt` + `/tui/submit-prompt` worked unchanged; `capture-pane -p -t W-47911` showed
  the prompt rendered and `TMUXWORKS` answered. **`capture-pane` is also a free progress probe that
  the WT topology does not have.**
* Stop: `kill -INT $PID` (or `tmux kill-window -t W-47911`) → pid gone, `health=000`, and the tmux
  window **vanished from `list-windows`** — no dead-tab litter, ever.
* Per-window colour works via `window-status-style`.

Honestly LOST vs WT tabs: at-a-glance overview (one status line instead of a row of coloured tabs),
native mouse/click-to-switch and Windows-native copy/paste (tmux needs mouse mode and its own
copy-mode), independent per-tab scrollback, and the operator must learn `Ctrl-b` navigation. All
workers also die with the single WT tab unless the operator re-attaches — though `tmux` surviving a
detach is strictly *better* than today, where closing the tab is fatal.

## N. Ranked recommendation

1. **Stopping — `kill -INT` → `kill -TERM` → `kill -KILL`, discovered by port, verified by
   `pid gone AND http 000`** (§I). Graceful at rungs 1-2, exits 0, closes the tab, lets `proxy.py`
   unregister from the bridge, loses only the in-flight turn, cannot corrupt the WAL store.
   Port→PID + `kill` **is** the whole answer; nothing more elegant is warranted. There is no HTTP
   stop and no plugin hook to wait for.
2. **Focus — variant C** (§L): one `wt` invocation, `new-tab … ';' focus-tab -t ${CHARON_WT_HOME_TAB:-0}`.
   Operator-confirmed; ~40-90 ms residual per spawn; holds under a 4-way fan-out; degrades only when
   the operator is typing in a *different* WT window.
3. **tmux-in-one-WT-tab** (§M) is the structurally cleaner answer to both problems at once — zero
   focus steal by construction, litter-free kill, plus `capture-pane` as a progress probe. It costs
   the operator's tab ergonomics. Worth a deliberate trial if C's residual steal or its
   multi-window limitation bites in practice.
4. **Liveness — register at spawn, consume the bridge** (§J). Do not build a port-poller.

## O. Clean-up statement

All test workers stopped and verified: nothing listening on 479xx. `tmux -L charontest` server
killed. The `scoop install opencode@1.18.5` stray was killed. PowerShell probes removed from
`C:\Users\<user>\`. The operator's workers (47201-47205, 47099) were never signalled and were
confirmed still listening afterwards.
**Two tabs remain for the operator to close manually — `FOCUSTEST-A` and `FOCUSTEST-C`** (window 1,
indices 2 and 3). Their payload was a `sleep` I SIGTERM'd, so they exited 143 and `closeOnExit:
graceful` correctly kept them — the same rule §I documents. Press Ctrl+D or Enter in each.
Test sessions remain as inert rows in the shared store.
