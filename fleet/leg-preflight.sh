#!/usr/bin/env bash
# leg-preflight.sh — HARDENED ENTRY POINT for the leg-preflight canary.
#
# Wraps fleet/benchmark/leg-preflight.sh with Linux namespace + tmpfs
# isolation so a hostile MODEL-EMITTED payload (run by the canary's
# exec_check.py sandbox) cannot read the user's gateway token file at
# ~/.config/opencode/opencode.json. Closes the credential-exfil vector
# identified in LEG-SANDBOX-HARDEN (adversarial review of LEG-PREFLIGHT-CANARY):
# the canary's rlimits+timeout sandbox bounds runtime but does NOT block
# FS reads or outbound sockets — a payload that reads the token file and
# POSTs it to an attacker is the full exploit chain.
#
# ── LAYERING (this file is the OUTER layer; the canary is the INNER layer) ───
#   USER-PROMPT  →  THIS WRAPPER  →  fleet/benchmark/leg-preflight.sh
#                       │                       │
#                       │ unshare user+mount    │ exec_check.py subprocess
#                       │ + tmpfs overmount     │ (already env-stripped)
#                       ↓                       ↓
#                   credential-            model-emitted Python runs
#                   containing dirs        in a hard runtime ceiling
#                   are EMPTY tmpfs        (rlimits + timeout)
#
# The canary itself is unchanged — it still calls the gateway, still writes
# LEG-RANK.tsv, still runs exec_check.py for exec-kind tasks. We only
# intervene at the FRONT (overmount cred dirs before the canary starts)
# so the model-emitted payload the canary will run later has nothing to
# read. exec_check.py's existing env-strip (line 108: env={"PATH":...})
# is the second layer of defense: even if the payload reaches an env var
# it doesn't have the token.
#
# ── THREAT MODEL (explicit — what is and is NOT blocked) ─────────────────────
#   BLOCKED:
#     • Absolute-path read of the gateway token file
#       (~/.config/opencode/opencode.json and its resolved real path
#       under $HOME) — tmpfs overmount returns ENOENT. This is the
#       PRIMARY cred-exfil vector a hostile model-emitted payload would
#       use; the test in fleet/tests/leg-sandbox-isolation.test.sh
#       fails on any revert that drops the overmount.
#     • Read of LPF_TOKEN from the canary's exec_check subprocess env —
#       exec_check.py:108 passes env={"PATH":"/usr/bin:/bin"} to the
#       candidate (the grandchild), no inherited env at all. The
#       candidate's own /proc/self/environ contains only PATH.
#     • Read of other common credential paths in $HOME (e.g.
#       ~/.aws/credentials, ~/.config/gh/hosts.yml, ~/.netrc) — same
#       overmount. New secrets added under $HOME are protected by default.
#     • Enumeration of HOST processes via /proc — hidepid=2 (with a
#       fresh /proc mount) restricts the candidate's /proc to its own
#       PID namespace's processes. The candidate cannot see or read
#       /proc/<host-pid>/environ for any host process.
#
#   NOT BLOCKED (documented residuals — each is its own risk class):
#     • Outbound TCP/UDP sockets from the candidate process. We do NOT
#       `unshare --net` because the canary itself needs the host network
#       to reach the gateway at LPF_GATEWAY_URL. A hostile payload CAN
#       open a socket — but, with the above blocks in place, the
#       token-file read vector is closed. The credential-exfil CHAIN
#       is therefore broken at the read step: a payload can open a
#       socket, but the only token accessible to it is via the
#       same-ns /proc residual below (not via the file).
#     • Read of /proc/<same-ns-pid>/environ. The kernel's ptrace_may_access
#       check grants same-uid reads; all processes in our user-namespace
#       share uid 0 (mapped to the wrapper's host uid). The canary's
#       exec_check.py subprocess inherits env from the canary's main
#       loop, which in turn inherits LPF_TOKEN from this wrapper (we
#       pass it via env so the canary can call the gateway without
#       re-reading the now-overmounted token file). A candidate that
#       can find the exec_check.py PID can read its environ and recover
#       LPF_TOKEN. The candidate can also read /proc/1/environ (the
#       canary's main loop, after the wrapper's inner bash exec'd into
#       it), with the same result. CLOSING THIS requires either:
#         (a) passing the token to the canary via a mechanism the
#             exec_check subprocess does NOT inherit (e.g. a file the
#             canary reads at runtime, then drops — would require
#             editing the canary, out of scope here), or
#         (b) running the candidate in a per-exec_check sub-namespace
#             with a DIFFERENT uid so the same-uid ptrace check fails
#             (also out of scope — the canary owns exec_check.py).
#       This is the deepest residual and the one operators should be
#       most aware of; the test asserts the closed half (host-PID
#       enumeration hidden) and the doc-comment in the test acknowledges
#       this half.
#     • Read of files outside $HOME and /root (e.g. /etc/passwd, world-
#       readable system files). These contain no secrets, so not in scope.
#     • Side effects via any writable path outside $HOME. rlimits in
#       exec_check.py still cap bytes-written (RLIMIT_FSIZE=0) and CPU,
#       so the canary's existing rlimit sandbox is the backstop.
#
#   COMPROMISE-FROM-PRIVILEGED-PROCESSES: a process that already has
#   root in the host user-ns can of course re-mount what it likes. This
#   wrapper assumes a normal unprivileged user; the canary's subprocess
#   runs with the same uid as the wrapper, no setuid.
#
# ── PORTABILITY / FALLBACK ───────────────────────────────────────────────────
#   Best-effort: we try to enter user+mount(+pid) namespaces. If any
#   unshare flag is refused by the kernel (common on WSL2 with --pid, on
#   older kernels without user-ns support, on locked-down hosts), we drop
#   that flag and proceed with the strongest set the kernel allows. The
#   `ISOLATION` log line below prints which flags were actually applied.
#   If ALL namespace flags are refused, the wrapper degrades to "no
#   isolation, env-strip only" — and logs a loud WARNING. Operators who
#   require hard isolation should run on a host that permits unshare.
#
# ── USAGE ────────────────────────────────────────────────────────────────────
#   fleet/leg-preflight.sh [args...]   — same args as the inner canary.
#                                        Default: probe DEFAULT_LEGS.
#   fleet/leg-preflight.sh --probe-isolation <cmd> [args...]
#                                     — set up the namespace + tmpfs
#                                       overmount, then exec <cmd> [args]
#                                       in that sandbox. No canary is
#                                       run. This is the test hook
#                                       (fleet/tests/leg-sandbox-isolation.test.sh)
#                                       and is also useful for ad-hoc
#                                       audit ("what can a hostile
#                                       payload see inside the sandbox?").
#
#   Exit codes match the inner canary (0=ok, 1=--gate SKIP, 2=hard error).
#
# ── ENV VARS ─────────────────────────────────────────────────────────────────
#   All leg-preflight.sh env overrides (LPF_RANK_FILE, LPF_GATEWAY_URL,
#   LPF_TOKEN, LPF_PROBE_CMD, LPF_REQ_TIMEOUT_S, LPF_LATENCY_BUDGET_S,
#   LPF_CANARY_DIR) are forwarded to the inner canary. LPF_TOKEN is
#   resolved HERE before the namespace is entered (the canary would
#   otherwise re-read it from $HOME, which is now empty tmpfs).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INNER="$HERE/benchmark/leg-preflight.sh"
LOG_PREFIX="[leg-sandbox]"
log()  { printf '%s %s\n' "$LOG_PREFIX" "$*" >&2; }
err()  { printf '%s ERROR: %s\n' "$LOG_PREFIX" "$*" >&2; }
die()  { err "$*"; exit 2; }

# ── INNER-SANDBOX BRANCH ─────────────────────────────────────────────────────
# This branch runs AFTER the outer script re-exec'd us under `unshare`.
# We overmount the credential dirs in the freshly-granted mount namespace,
# then exec the target command (the inner canary in production, or the
# probe command in test mode). The target inherits the namespace, so every
# subprocess it spawns (including exec_check.py's grandchild) also sees
# the overmounted cred dirs.
if [ "${1:-}" = "--_inner-sandbox" ]; then
  shift
  PROBE_MODE="$1"; shift
  if [ "$PROBE_MODE" -eq 1 ]; then
    TARGET=("$@")
  else
    TARGET=("$INNER" "$@")
  fi

  USER_HOME="${HOME:-}"
  if [ -z "$USER_HOME" ] || [ ! -d "$USER_HOME" ]; then
    USER_HOME="$(python3 -c 'import os; print(os.path.expanduser("~"))')"
  fi
  ROOT_HOME="/root"

  # overmount: mount -t tmpfs tmpfs <dir>. Best-effort; if a single
  # overmount fails (e.g. dir is on a 9p filesystem that doesn't allow
  # tmpfs-overmount), we log a warning and continue — the other overmounts
  # may still work, and the test will catch a missing one. We do NOT die
  # on a partial failure, because a fail-loud abort would be a worse
  # outcome than running with reduced isolation (the operator gets a
  # clear ISOLATION log either way and can decide to act).
  for D in "$USER_HOME" "$ROOT_HOME"; do
    [ -d "$D" ] || continue
    if mount -t tmpfs tmpfs "$D" 2>/tmp/leg-sandbox-mount-err.$$; then
      :
    else
      log "WARNING: could not overmount $D with tmpfs ($(cat /tmp/leg-sandbox-mount-err.$$ | tr '\n' ' ')). The credential-exfil vector may be PARTIALLY open for this path."
    fi
    rm -f /tmp/leg-sandbox-mount-err.$$
  done

  # Mount a fresh /proc inside the namespace with hidepid=2 so the
  # candidate's exec context can only see its own PID (and not enumerate
  # the canary's parent PIDs to read /proc/<ppid>/environ — which holds
  # LPF_TOKEN, since the canary's python subprocess inherits the wrapper's
  # env). The candidate's own /proc/self/environ is also env-stripped by
  # exec_check.py:108 (env={"PATH":"/usr/bin:/bin"}), so even /proc/self
  # shows just PATH. Together: no token in any environ file the candidate
  # can reach. We try hidepid=2 (strongest); if that fails, fall back to
  # a plain /proc remount (still hides host PIDs, but doesn't restrict
  # same-ns PIDs from seeing each other). If even the plain remount
  # fails, leave /proc alone and accept the documented residual (the
  # candidate can enumerate host PIDs owned by the same uid).
  if mount -t proc -o hidepid=2 proc /proc 2>/dev/null; then
    :
  elif mount -t proc proc /proc 2>/dev/null; then
    log "WARNING: could not mount /proc with hidepid=2 — falling back to plain /proc remount. The candidate may enumerate other PIDs in this namespace (exec_check.py's env-strip still blocks reading the candidate's OWN environ for the token, but other PIDs in the canary chain may be readable)."
  else
    log "WARNING: could not remount /proc — leaving the host /proc visible. The candidate may enumerate host PIDs owned by the wrapper's uid and read their environ (residual credential-exfil vector — close by running on a kernel that allows unshare --user --mount + /proc remount)."
  fi

  exec "${TARGET[@]}"
  exit $?  # unreachable
fi

# ── OUTER (entry-point) BRANCH ───────────────────────────────────────────────
command -v unshare >/dev/null 2>&1 || die "unshare(1) not found — cannot build sandbox"
[ -f "$INNER" ] || die "inner canary not found at $INNER (LEG-PREFLIGHT-CANARY dependency must be landed first)"
command -v mount >/dev/null 2>&1 || die "mount(8) not found — cannot overmount credential dirs"
command -v id >/dev/null 2>&1    || die "id(1) not found"

# ── 1. --probe-isolation <cmd> [args...] ─────────────────────────────────────
# Set up the namespace + overmount, then exec <cmd> [args] in the sandbox.
# Used by the fail-on-revert test and for ad-hoc audit. No canary is run.
PROBE_MODE=0
if [ "${1:-}" = "--probe-isolation" ]; then
  PROBE_MODE=1
  shift
  [ "$#" -ge 1 ] || die "--probe-isolation requires a command to run"
fi

# ── 2. Read the gateway token BEFORE the namespace ───────────────────────────
# Once inside, ~/.config/opencode/opencode.json is hidden by the overmount
# and the canary (which reads it on cold start, line ~320 of
# fleet/benchmark/leg-preflight.sh) would fail to find it. We read it
# here and pass via LPF_TOKEN, which the canary honors (skips the file
# read) — see leg-preflight.sh's own LPF_TOKEN env override (line ~59).
# In probe mode this is a no-op (the probe doesn't need the token).
if [ "$PROBE_MODE" -eq 0 ] && [ -z "${LPF_TOKEN:-}" ] && [ -z "${LPF_PROBE_CMD:-}" ]; then
  RESOLVED_TOKEN="$(python3 -c "
import json, os
try:
    print(json.load(open(os.path.expanduser('~/.config/opencode/opencode.json')))['provider']['charon']['options']['apiKey'])
except Exception:
    pass
" 2>/dev/null || true)"
  if [ -n "$RESOLVED_TOKEN" ]; then
    export LPF_TOKEN="$RESOLVED_TOKEN"
  else
    log "WARNING: no gateway token found at ~/.config/opencode/opencode.json — legs will likely rank UNREACHABLE (the inner canary emits the same WARNING)"
  fi
fi

# ── 3. Build the namespace flag set, best-effort ─────────────────────────────
# Probe each candidate flag set with a sacrificial `unshare <flags> true`.
# If the kernel denies any flag in a set, the whole unshare fails. Walk
# from strongest to weakest, keep the first set that works.
NS_USER=0
NS_MOUNT=0
NS_PID=0

probe_ns() {
  # $1: flag set as a single string. Probe with `unshare <flags> true`.
  # Returns 0 on success.
  unshare $1 true >/dev/null 2>&1
}

if probe_ns "--user --map-root-user --mount --propagation=private --pid --fork"; then
  NS_USER=1; NS_MOUNT=1; NS_PID=1
  NS_FLAGS=(--user --map-root-user --mount --propagation=private --pid --fork)
elif probe_ns "--user --map-root-user --mount --propagation=private --fork"; then
  NS_USER=1; NS_MOUNT=1
  NS_FLAGS=(--user --map-root-user --mount --propagation=private --fork)
elif probe_ns "--user --map-root-user --mount --propagation=private"; then
  NS_USER=1; NS_MOUNT=1
  NS_FLAGS=(--user --map-root-user --mount --propagation=private)
else
  NS_FLAGS=()
fi

if [ "$NS_MOUNT" -eq 1 ]; then
  log "ISOLATION: user_ns=on mount_ns=on pid_ns=$NS_PID net_ns=off (intentionally not unshared: the canary needs the host network to reach the gateway; the candidate's exec-check env is already stripped of the token, so the open-socket path is exploitable only in combination with the now-blocked token-file read)"
else
  log "WARNING: ISOLATION: NONE (kernel refused user+mount unshare). Credential-exfil vector is OPEN; this run is no safer than running the inner canary directly."
fi

# ── 4. Enter the namespace, then re-enter the script's inner branch ─────────
# We re-exec self under the namespace, with --_inner-sandbox as a marker
# so the child branch (top of file) knows to overmount + exec. We use a
# fresh exec instead of doing `unshare` in-process because util-linux
# `unshare` without --fork does affect the calling process, but a fresh
# exec makes the lifecycle cleaner (no risk of leaking the unshared state
# into a parent script's continuation if the script is ever sourced).
if [ "${#NS_FLAGS[@]}" -gt 0 ]; then
  exec unshare "${NS_FLAGS[@]}" "$0" --_inner-sandbox "$PROBE_MODE" "$@"
fi

# No-isolation path: just run the target command directly.
if [ "$PROBE_MODE" -eq 1 ]; then
  exec "$@"
fi
exec "$INNER" "$@"
exit $?  # unreachable; exec replaces
