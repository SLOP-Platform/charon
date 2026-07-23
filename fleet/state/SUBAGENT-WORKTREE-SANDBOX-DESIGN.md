# SUBAGENT-WORKTREE-SANDBOX — Confine subagent/droid writes to assigned worktree

**Status:** PROPOSED (design/eval only — no code changed)
**Date:** 2026-07-23
**Author:** SUBAGENT-WORKTREE-SANDBOX session (fleet droid)
**Sibling:** LEG-SANDBOX-HARDEN (same confine-untrusted-exec family, different surface: canary-exec cred-exfil vs subagent filesystem writes)

---

## (1) Escape incident: instruction-is-not-a-boundary

**2026-07-22, vulture-investigate subagent.** A build subagent explicitly instructed "do NOT touch the product repo" issued a shell command that changed its working directory to `/home/stack/code/charon` and wrote into `pyproject.toml` via an absolute-path heredoc:

```bash
cd /home/stack/code/charon && cat > pyproject.toml <<'EOF'
...
EOF
```

The write truncated `pyproject.toml`, corrupting the product's build configuration. Self-caught and restored within the same session (the vulture-investigate agent noticed and reverted). No data loss, but the vector was real: a natural-language instruction ("do NOT touch the product repo") was not and cannot be a filesystem boundary.

**Root CLASS:** Subagents/droids can write OUTSIDE their assigned worktree via absolute paths or `cd` resets followed by relative-path writes. The model's instruction-following is a best-effort advisory — not an access control mechanism. Closing this requires an OS-enforced filesystem boundary that is independent of the model's compliance.

**Affected harnesses:**
| Harness | Can write outside worktree? | Boundary mechanism |
|---|---|---|
| Claude Code (interactive or `claude -p`) | YES — `cd /somewhere` + write, absolute-path write, heredoc | Natural-language instruction only (==none) |
| opencode (`opencode run`) | YES — same vectors | opencode permission config (partial, subagent-bypass bug #5894) |
| fleet droid (Bash dispatch) | YES — same vectors | Natural-language instruction only (==none) |

All three share the same root cause: the model's execution environment has the host's full filesystem access and there is no OS-level confinement tied to the assigned worktree root.

---

## (2) Mechanism evaluation

### Methodology

Per [[adopt-substrate-build-only-novel-slice]] and [[confirm-dont-trust-documentation]]:

1. **Check availability on target hosts** — the host this eval was performed on (`4-LOM`, WSL2 kernel 6.6.87.2-microsoft-standard-WSL2) is representative of the developer workstations where subagents run. CI runners (`ubuntu-latest`) are the secondary target.
2. **Execute or document the trial** — run if possible; source-read if unavailable but runnable on a real host (per AP-12: source-reading can confirm absence but cannot stand in for an executed trial of a runnable candidate).
3. **Record verdict as an EVAL-REGISTRY row** — included inline; the file-level row is to be added by the BUILD follow-up ticket.

### Mechanism A: bubblewrap/bwrap

| Property | Value |
|---|---|
| **Source** | `github.com/containers/bubblewrap`, MIT license |
| **Status** | Actively maintained (2026 commits), used by flatpak in production |
| **Install** | `apt install bubblewrap` (Debian/Ubuntu), `dnf install bubblewrap` (Fedora) |
| **Kernel dep** | Linux user namespaces (`CONFIG_USER_NS=y`) — no root/setuid required for unprivileged mode |
| **Mechanism** | `bwrap --bind $WORKTREE $WORKTREE --ro-bind / / <cmd>` — bind-mounts the assigned worktree rw; everything else (/, /home, /tmp, /etc) is ro; no write access outside the worktree |
| **Prerequisite on host** | User namespaces confirmed working (`unshare --user --map-root-user --mount true`, exit 0). bwrap binary is an apt-cache match (`bubblewrap - utility for unprivileged chroot and namespace manipulation`) but COULD NOT BE INSTALLED for this eval (no sudo on this WSL2 host). The user-ns prerequisite is verified; the binary itself is a commodity `apt install` away on any debian/ubuntu host. |
| **Covers sibling?** | YES — `bwrap --ro-bind / / --ro-bind $WRAPPED_SCRIPT $WRAPPED_SCRIPT --ro-bind /usr/bin/python3 /usr/bin/python3 ...` can also replace LEG-SANDBOX-HARDEN's direct `unshare` wrapper with a cleaner CLI, though the sibling already ships with direct unshare and is not blocked. |
| **Novel glue needed** | ~30 LOC: wrapper script that (a) resolves the assigned worktree root from context, (b) constructs the bwrap bind-mount CLI, (c) spawns the subagent/command inside the sandbox. Integration with the fleet droid launcher. |
| **Escape surface** | bwrap itself is well-audited (flatpak's sandbox). A bug in bwrap's argument parsing (e.g. `--bind` path collision) is a realistic residual, but narrower than the present unlimited-access surface. |

**Verdict: ADOPT** as the primary confinement mechanism.

### Mechanism B: Linux landlock

| Property | Value |
|---|---|
| **Source** | In-kernel (since Linux 5.13), `CONFIG_SECURITY_LANDLOCK=y` |
| **Status** | Stable ABI (ABI versions 1-4 as of kernel 6.6) |
| **Install** | No binary — used via `landlock_restrict_self()` syscall (needs a C caller or ctypes wrapper) |
| **Kernel dep** | `CONFIG_SECURITY_LANDLOCK=y` AND securityfs mounted at `/sys/kernel/security/` |
| **Availability on this host** | `CONFIG_SECURITY_LANDLOCK=y` is in the kernel config. BUT: securityfs is NOT mounted by default on WSL2; `/sys/kernel/security/landlock/` does not exist at runtime. Mounting it requires `sudo mount -t securityfs securityfs /sys/kernel/security` or a boot-time systemd unit. On `ubuntu-latest` CI runners, securityfs is mounted by default and landlock ABI is exposed — so landlock WORKS in CI but may NOT work on developer WSL2 workstations. |
| **Covers sibling?** | PARTIAL — landlock restricts the calling process tree's filesystem access. It could cover the subagent confinement. But it doesn't help LEG-SANDBOX-HARDEN's credential-exfil surface (which needs namespace isolation for tmpfs overmount). |
| **Novel glue needed** | ~80-120 LOC: a Python ctypes wrapper for `landlock_create_ruleset()` and `landlock_restrict_self()` syscalls, plus ruleset construction for "worktree rw, everything else ro". OR use the `landlock` PyPI package (not stdlib; adds a dep). |
| **Portability concern** | WSL2 does NOT expose landlock without manual securityfs mount. A fallback to bwrap would be needed anyway. Running two sandbox mechanisms doubles the maintenance surface. |

**Verdict: REJECT** for this use case. Not portable enough (WSL2 gap), requires more novel glue than bwrap, and does not cover the sibling's credential-exfil surface. If landlock becomes the default on WSL2 in the future (WSL2 kernel 6.6+ should support it; the gap is securityfs mounting, not the kernel feature), this could be revisited.

### Mechanism C: firejail

| Property | Value |
|---|---|
| **Source** | `github.com/netblue30/firejail`, GPL2 |
| **Status** | Actively maintained (2026 commits) |
| **Install** | `apt install firejail` (available per apt-cache search) |
| **Kernel dep** | Linux user namespaces for unprivileged mode, or setuid-root binary |
| **COULD NOT BE TESTED** | Not installed on this host; no sudo to install. However, firejail's surface (full seccomp/profile/network isolation) is well-documented and understood. |
| **Fit for purpose** | firejail is a full sandbox suite: seccomp profiles, filesystem blacklists/whitelists, network isolation, X11, D-Bus. For "bind-mount worktree rw, rest ro" — ~5% of firejail's capability. The remaining 95% is unused surface (profile system, seccomp rules, network isolation) that adds maintenance burden and CVE surface. |
| **Documented CVEs** | Multiple past CVEs (CVE-2021-26910, CVE-2021-26911 — seccomp-bypass; CVE-2023-45658 — suid-root LPE; CVE-2024-47012 — fs restriction bypass). Several are old, but the suid-root binary is a realistic escalation surface on a shared host. |
| **Novel glue needed** | ~20 LOC wrapper similar to bwrap (firejail supports `--bind`/`--read-only=/` syntax). Less glue but more host surface. |
| **Covers sibling?** | YES — firejail's full profile could cover both tickets, but at the cost of running a suid/setcap binary with a documented CVE history. |

**Verdict: REJECT** for this use case. firejail's full-suite capability is overkill; the suid-root binary is unnecessary attack surface when bwrap provides the same bind-mount confinement with no setuid requirement and a smaller, more audited codebase (flatpak's sandbox).

### Mechanism D: PreToolUse path-guard hook

| Property | Value |
|---|---|
| **Source** | Claude Code hooks system (`PreToolUse` event) |
| **Status** | ADOPTED per EVAL-REGISTRY (2026-07-21) — the hook system itself is adopted for drift/in-plan enforcement |
| **Mechanism** | A `PreToolUse:Agent|Task` script that resolves the tool-call's path arguments against the assigned worktree root and exits 1 (rejecting the tool call) if the resolved realpath escapes the worktree |
| **Strengths** | Works at the model-call level — catches writes before they happen, not after. Can provide a structured error message to the model. No OS kernel dependency. Can be deployed per-repo without host-wide configuration. |
| **Weaknesses** | ~5% escape rate documented (EVAL-REGISTRY row, 2026-07-21): Bash `>`/heredoc write paths bypass PreToolUse (they are shell builtins, not tool calls). Model can self-edit `.claude/settings.json` to disable hooks. Only covers the Claude Code harness — does NOT cover opencode or fleet droid Bash dispatch. A natural-language instruction is not a boundary, AND a PreToolUse hook enforced by the model is also not an OS boundary (the model can stop calling the hook-gated tool and use a shell builtin instead). |
| **Covers sibling?** | NO — LEG-SANDBOX-HARDEN's threat is credential-exfil from a spawned process, not a model tool call. |

**Verdict: REJECT as primary mechanism.** A PreToolUse hook is a complementary in-session defense-in-depth layer, but it cannot be the sole boundary because:
- 5% escape (Bash builtins, heredoc) = same class as the original vulnerability
- Only covers the Claude Code harness, not opencode or fleet droid
- The model can disable hooks by editing settings.json

**Adopt as defense-in-depth complement:** Wire a PreToolUse path-guard hook as the in-session warning layer (blocks writes before they happen for the ~95% of tool-call paths), with bwrap as the OS-level backstop (blocks the ~5% that bypass the hook + covers non-Claude harnesses).

---

### Summary matrix

| Dimension | bwrap | landlock | firejail | PreToolUse hook |
|---|---|---|---|---|
| OS boundary | YES (namespace) | YES (kernel LSM) | YES (namespace+seccomp) | NO (model-level) |
| Defeats `cd`+write / absolute-path escape | YES | YES | YES | ~95% (Bash builtins bypass) |
| Covers Claude + opencode + fleet droid | YES | YES | YES | Claude only |
| Host prerequisite | user namespaces (verified) | securityfs mount (WSL2 gap) | user namespaces (verified) or suid | hooks enabled in settings.json |
| Novel glue | ~30 LOC wrapper | ~80-120 LOC ctypes + fallback | ~20 LOC wrapper | ~50 LOC hook script |
| Suid/setcap binary | NO | NO | YES | NO |
| CVE history | Minimal (flatpak-audited) | N/A (in-kernel) | Multiple (old + recent) | N/A |
| Covers LEG-SANDBOX-HARDEN? | YES (refactor possible) | PARTIAL (no /proc hidepid) | YES (overkill) | NO |

---

### Verdict: ADOPT bubblewrap/bwrap

**Primary confinement mechanism: bubblewrap/bwrap.** It is the maintained, purpose-built tool for "bind-mount these paths rw, everything else ro" — the exact primitive needed to confine subagent writes to their assigned worktree. It requires no setuid, no kernel config changes, zero novel security infrastructure to maintain. The ~30 LOC wrapper (novel glue) is the fleet-specific integration: resolve worktree root → construct bwrap CLI → spawn subagent.

**Defense-in-depth complement: PreToolUse path-guard hook.** Catches the ~95% of tool-call writes before they happen; bwrap catches any residual. The hook is fast (no process spawn) and provides structured feedback to the model. Both layers are independently testable — the canary must assert both are operational.

**Coordination with LEG-SANDBOX-HARDEN:** LEG-SANDBOX-HARDEN already ships (`fleet/leg-preflight.sh`) with direct `unshare`-based namespaces, which is a valid working implementation. The sibling can optionally be refactored to use bwrap for consistency in a follow-up, but is NOT blocked — its existing solution works. A single `fleet/bwrap-sandbox.sh` utility could serve both tickets: `bwrap --bind <worktree> <worktree> --ro-bind / / <cmd>` for subagent confinement, and `bwrap --ro-bind <canary-script> <canary-script> --tmpfs /home --tmpfs /root ...` for canary isolation.

---

## EVAL-REGISTRY row (to be added by BUILD follow-up)

```
| bubblewrap/bwrap | subagent/droid filesystem write confinement — bind-mount assigned worktree rw, everything else ro, as an OS-level boundary | 2026-07-23 | ADOPT | aligned | Tested on the target class host (WSL2): user namespaces confirmed working (unshare --user --map-root-user --mount exit 0); bwrap binary is standard `apt install bubblewrap` (verify via apt-cache); cannot test binary execution on THIS host (no sudo), but the prerequisite is confirmed and the tool is production-proven (flatpak). CHOSEN over landlock (WSL2 securityfs gap, more novel glue), firejail (suid binary + CVE surface), and PreToolUse hook (not an OS boundary, 5% escape, Claude-only harness). | fleet/state/SUBAGENT-WORKTREE-SANDBOX-DESIGN.md | — |
```

---

## (3) BUILD follow-up ticket: SUBAGENT-WORKTREE-BUILD

The following ticket is spawned for the implementation phase:

```yaml
repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/subagent-worktree-build
depends_on: SUBAGENT-WORKTREE-SANDBOX
real-dep: Design/eval in SUBAGENT-WORKTREE-SANDBOX must land first — this ticket implements the chosen mechanism.
owns: fleet/bwrap-sandbox.sh, fleet/tests/bwrap-sandbox.test.sh, fleet/state/EVAL-REGISTRY.md
ds: |
  ## Dependencies & sequence
  - depends_on: SUBAGENT-WORKTREE-SANDBOX (design/eval — this ticket implements the chosen design)
  - relationship: CHILD of SUBAGENT-WORKTREE-SANDBOX
  - priority: 2 (same P-band as parent)
accept: |
  Subagent/droid Bash commands dispatched by the fleet launcher are confined to their
  assigned worktree: any write (via Bash, Write, Edit, heredoc, or any other mechanism)
  whose resolved realpath is NOT within the assigned worktree root is BLOCKED by an
  OS-level filesystem boundary (bubblewrap user+mount namespace).
  Specifically:
  (1) `fleet/bwrap-sandbox.sh` (NEW) — a wrapper script that takes $WORKTREE_ROOT and
      optional $COMMAND, constructs `bwrap --bind $WORKTREE $WORKTREE --ro-bind / /`
      (with additional bind-mounts for essential read-only paths like /usr, /lib, /etc/alternatives
      as needed for the interpreter), and spawns the command inside the sandbox.
      Falls back with a loud WARNING if bwrap is not installed (graceful degradation).
  (2) `fleet/tests/bwrap-sandbox.test.sh` (NEW) — fail-on-revert hermetic test suite:
      (a) asserts a write TO a path inside $WORKTREE_ROOT succeeds (positive control)
      (b) asserts a write TO a path outside $WORKTREE_ROOT is BLOCKED (CORE — revert goes RED)
      (c) asserts a `cd /outside` + relative write is BLOCKED
      (d) asserts a Bash heredoc write to an absolute path outside worktree is BLOCKED
      (e) asserts the wrapper falls back gracefully when bwrap is absent (LOUD WARNING, no crash)
      (f) negative control: same payloads outside the sandbox DO write (proves (b)-(d) not vacuous)
      (g) asserts ISOLATION log line emitted on every sandboxed invocation
  (3) Integration with the fleet droid launcher: the launcher calls bwrap-sandbox.sh
      with the ticket's assigned worktree root before dispatching the subagent command.
  (4) EVAL-REGISTRY.md updated with the bubblewrap row (from the design doc).
  FAIL-ON-REVERT:
    A subagent attempting an out-of-worktree write is BLOCKED (test (b)-(d) PASS).
    If the bwrap guard is neutered (removed from the launch path, --ro-bind / changed to
    --bind /, or the entire wrapper deleted), the test payload escapes → test FAILS →
    gate RED.
  DEFERRED / NOT IN SCOPE:
    - PreToolUse path-guard hook (defense-in-depth complement — separate ticket)
    - Refactoring LEG-SANDBOX-HARDEN to use bwrap (optional, sibling ticket's decision)
    - Securing the bwrap binary itself against tampering (host integrity is out of scope)
```

---

## Threat model

**Attacker:** A model (Claude/openmode/fleet droid) instructed to write to a specific file that the operator does NOT intend it to touch.

**Goal:** The subagent writes or overwrites a file outside its assigned worktree (e.g. the product repo, system files, another ticket's worktree) via absolute path, `cd`+relative path, or heredoc.

**Boundary:** The subagent's process tree is confined by a bwrap user+mount namespace. The assigned worktree root is bind-mounted `rw` at its host path; all other host filesystem paths are bind-mounted `ro` (read-only). The subagent CANNOT write to any path outside the worktree — regardless of what the model instructs, what tool it uses (Bash, Write, Edit), or whether it changes directories.

**Out of scope:**
- **Network egress** (the subagent can still make outbound connections) — separate surface; LEG-SANDBOX-HARDEN covers credential exfil over the network for canary execs; a similar mechanism could be added for subagents in a follow-up but is not in scope.
- **Process list visibility** (the subagent can still see host PIDs via /proc) — not in scope for filesystem write confinement. The sibling uses hidepid for the canary; if needed for subagents, add as a follow-up.
- **Kernel-level privilege escalation** — a bwrap escape via a kernel bug is not within the threat model (it is mitigated by keeping the host kernel updated).
- **The bwrap binary itself being absent** — the wrapper MUST degrade gracefully (warn loudly, proceed without sandbox) so the developer is not blocked. The canary assertion detects the degraded state and fails CI, forcing installation.

---

## Verification

- The EVAL-REGISTRY row above documents the verdict and evidence, to be added to the shared registry by the BUILD ticket.
- The BUILD ticket's test suite (assertions (a)-(g)) serves as the fail-on-revert canary: neuter the guard → escape succeeds → test fails → gate RED.

---

## Appendices

### A. WSL2 user namespace verification (raw output)

```
$ unshare --version
unshare from util-linux 2.39.3

$ mkdir -p /tmp/test-sandbox && unshare --user --map-root-user --mount --propagation private mount -t tmpfs tmpfs /tmp/test-sandbox
EXIT=0  (mount succeeded in the namespace)
```
