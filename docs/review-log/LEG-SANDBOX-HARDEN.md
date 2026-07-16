# LEG-SANDBOX-HARDEN — review-log fragment

## Threat model in one sentence
A hostile model-emitted payload (run by the canary's exec_check.py sandbox)
must NOT be able to read the user's gateway token at
`~/.config/opencode/opencode.json` from the candidate's exec context.
The wrapper closes the most likely cred-exfil vector (FS-read of the
token file by absolute path) and the host-PID enumeration vector
(via hidepid /proc remount). One residual survives: a candidate that
can find the canary's parent PID can read its /proc/<ppid>/environ
and recover LPF_TOKEN, because the wrapper must pass the token via env
so the canary can call the gateway (the file is overmounted and
unreadable). Closing that residual requires editing exec_check.py
(out of scope).

## What was built
- `fleet/leg-preflight.sh` (NEW) — hardened entry point that wraps
  `fleet/benchmark/leg-preflight.sh` with Linux user+mount(+pid)
  namespaces, tmpfs overmount of `$HOME` (and `/root`), and a
  `hidepid=2 /proc` remount. Resolves the gateway token from
  `~/.config/opencode/opencode.json` BEFORE entering the namespace
  and passes it via `LPF_TOKEN` (which the canary already honors —
  see leg-preflight.sh:316). Exposes a `--probe-isolation <cmd>`
  hook for the test and ad-hoc audit. Falls back gracefully (with
  loud WARNING) when the kernel refuses any of the unshare flags.
- `fleet/tests/leg-sandbox-isolation.test.sh` (NEW) — fail-on-revert
  test that:
    (a) asserts the wrapper blocks absolute-path read of the token
        file via the tmpfs overmount (CORE — revert goes RED)
    (b) negative control: same payload outside the sandbox DOES read
        the file (proves (a) is not vacuous)
    (c) asserts the candidate's /proc/self/environ has no token
        (env-strip — verified via injected FAKE_TOKEN env marker)
    (d) asserts host PIDs are hidden from the candidate via
        hidepid=2 + new /proc remount (revert goes RED); the same-ns
        /proc/<ppid>/environ residual is documented but not asserted
    (e) asserts a bare TCP socket syscall SUCCEEDS (documented
        residual — we don't unshare --net because the canary needs
        the host network for the gateway)
    (f) asserts the ISOLATION log line is emitted on every run
    (g) asserts the wrapper still delegates to the inner canary
        end-to-end (canary ranks a stubbed leg HEALTHY through the
        wrapper — proves the sandbox doesn't break the canary)

## Design decisions and why

### Why a wrapper, not editing the canary
The canary (`fleet/benchmark/leg-preflight.sh`) and its sandbox
(`fleet/benchmark/preflight-tasks/canary/exec_check.py`) are owned
by LEG-PREFLIGHT-CANARY (already merged). The ticket's `owns:`
explicitly names `fleet/leg-preflight.sh` as a new wrapper at the
root, and the SESSION-HANDOFF-cere-junda.md:487-488 handoff already
flagged the path as a "to-be-created" file (not a typo). The wrapper
sits in front of the canary and overmounts credential dirs before
the canary starts; the canary itself is unchanged.

### Why user+mount+pid, not just mount
- `mount` alone: in a user-ns we can `mount -t tmpfs tmpfs <dir>`,
  but the mount is visible to the host (not private). With
  `--propagation=private` from `mount` alone the namespace grants
  us the right to do the overmount, but a non-isolated mount is
  not private to the canary's process tree.
- `user+mount`: gives us a private mount namespace. Other processes
  on the host don't see our overmounts, and the canary's subprocess
  tree inherits them. `--map-root-user` is the unprivileged-user
  equivalent of `--user` (maps ns root to the host uid).
- `pid`: gives us a private PID namespace. Optional but enables the
  `mount -t proc -o hidepid=2 proc /proc` remount that hides host
  PIDs from the candidate. Tries `--pid` first; falls back to
  user+mount-only if the kernel refuses (e.g. some WSL2 configs).

### Why tmpfs over $HOME specifically
The canary's token-resolution code (leg-preflight.sh:320) reads
`~/.config/opencode/opencode.json`. If we didn't overmount HOME,
a candidate could use `os.path.expanduser('~')` to discover the
real path (it has HOME stripped from env, but the path is
predictable: `/home/<user>/.config/opencode/opencode.json`).
Overmounting `$HOME` returns ENOENT for any guessed absolute path
under it, and also hides any other creds files the user might have
(`~/.aws/credentials`, `~/.netrc`, etc.).

### Why not unshare --net
The canary's `probe_leg` makes outbound HTTPS calls to
`$LPF_GATEWAY_URL` (default `http://10.0.1.60:8080/...`) to rank
legs. If we `unshare --net` at the wrapper level, the canary can't
reach the gateway and every leg ranks UNREACHABLE — the canary
becomes useless. A proper per-exec_check network namespace (only
the candidate is network-isolated, not the canary) would require
editing exec_check.py to add a `preexec_fn` that does `unshare --net`
before the candidate runs. Out of scope here.

The credential-exfil chain is broken at the READ step (a) +(c) + (d),
so the open-socket residual is harmless in the cred-exfil context
even though it succeeds in isolation. The test asserts the documented
behavior so a future "fix" that adds `--net` unshare (and breaks the
canary) is caught.

### Why the /proc/<ppid>/environ residual is documented, not closed
Closing it requires one of:
  (a) passing the token to the canary via a mechanism the
      exec_check.py subprocess does NOT inherit (e.g. the canary
      reads a file at runtime, drops it from env). Requires
      editing the canary — out of scope.
  (b) running the candidate in a sub-namespace with a DIFFERENT
      uid so the kernel's ptrace_may_access (same-uid) check
      denies /proc/<ppid>/environ reads. Requires exec_check.py
      to fork the candidate under a different uid — out of scope.

The ticket's "OR DOCUMENTED explicit threat-model disclaimer" path
applies here. The wrapper's threat-model section explicitly
discloses this residual, names the two ways to close it, and
notes both are owned by LEG-PREFLIGHT-CANARY (already merged and
not in this ticket's `owns:`).

## Test design notes
- Fully hermetic. Uses a `mktemp -d` fake HOME with a marker
  `FAKE_TOKEN_XYZZY` file; the wrapper overmounts it; the candidate
  tries to read it by the absolute path passed via argv (not via
  env, because the env-strip strips HOME — the test passes the
  path via argv to ensure the assertion actually exercises the
  overmount, not the env-strip).
- Negative controls in (b) and (d): the same payload without the
  wrapper DOES read the file and DOES see thousands of host PIDs.
  This proves the assertions in (a) and (d) are not vacuous — a
  test that passes only because the payload is broken would also
  fail the negative control, surfacing the inconsistency.
- FAKE_TOKEN env marker (set in the test's outer env, inherited
  by the wrapper, stripped by the env-strip in ENV_STRIP_WRAPPER)
  is the lever for (c): if the env-strip is reverted to inherit
  the parent's env, FAKE_TOKEN is in the candidate's /proc/self/environ
  and (c) goes RED.
- The end-to-end (g) checks both the wrapper's delegation
  (inner canary's [leg-preflight] log line emitted) AND a
  HEALTHY ranking (proves the sandbox doesn't break exec_check
  or the canary's python). Uses a stub that handles both the
  bal-parens (exec-checked) and lcm-bound (exact-match) tasks.

## Out of scope / not addressed
- Editing exec_check.py to env-strip its own process before
  spawning the candidate (closes the /proc/<ppid>/environ residual).
- Editing the canary to read the token from a file at runtime
  (so the wrapper doesn't need to pass LPF_TOKEN in env).
- Per-exec_check network namespace (so sockets are blocked at
  the candidate level, not the wrapper level).
- seccomp profile to block /proc/<pid>/environ reads where pid
  != self (would close the /proc/<ppid>/environ residual without
  exec_check.py edits, but requires the seccomp library which
  isn't stdlib and the ticket says no `pip install -e`).

## Verification
- `bash fleet/tests/leg-sandbox-isolation.test.sh` — 13/13 pass
- `bash fleet/tests/leg-preflight.test.sh` — 28/28 still pass
  (wrapper doesn't regress the existing F6/F14 tests)
- Manual end-to-end: `bash fleet/leg-preflight.sh goodmodel-ds`
  with a hermetic stub ranks the leg HEALTHY through the wrapper

## Sandbox-state observability
Every wrapper invocation logs:
  `[leg-sandbox] ISOLATION: user_ns=on mount_ns=on pid_ns=1 net_ns=off (...)`
so operators see the actual sandbox state on every run. A revert
that drops the line, or that disables any namespace flag, is
caught by test (f).
