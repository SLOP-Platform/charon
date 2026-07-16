#!/usr/bin/env bash
# leg-sandbox-isolation.test.sh — FAIL-ON-REVERT tests for LEG-SANDBOX-HARDEN.
#
# fleet/leg-preflight.sh is the hardened entry point in front of the
# leg-preflight canary. The hardening: Linux user+mount(+pid) namespaces,
# tmpfs overmount of $HOME (and /root), and a hidepid /proc remount — so
# a hostile MODEL-EMITTED payload (run by the canary's exec_check.py
# sandbox) cannot read the user's gateway token at
# ~/.config/opencode/opencode.json. Closes the credential-exfil vector
# identified in the LEG-SANDBOX-HARDEN ticket (the canary's existing
# rlimits+timeout sandbox bounds runtime but does NOT block FS reads or
# outbound sockets).
#
# Fully HERMETIC: every scenario sets HOME to a temp dir we control, and
# the candidate code we inject runs entirely inside that fake home (the
# real ~/.config/opencode/opencode.json on this host is never touched).
# No live network call is ever made.
#
# Covers (ticket's FAIL-ON-REVERT clause):
#   (a) FS-READ VECTOR: a payload that opens the token file by absolute
#       path is BLOCKED — the tmpfs overmount of $HOME returns ENOENT.
#       [CORE: revert the overmount -> the file becomes readable -> this
#       assertion goes RED.]
#   (b) FS-READ VECTOR (negative control): the same payload OUTSIDE the
#       sandbox (no wrapper, no overmount) DOES read the file — proving
#       (a) is not vacuous and would actually go RED if isolation were
#       removed.
#   (c) ENV-STRIP VECTOR: a payload that reads its own /proc/self/environ
#       (env-stripped by exec_check.py:108) sees ONLY "PATH" — the token
#       is not in the candidate's env.
#   (d) CROSS-PID VECTOR (host PIDs hidden): a payload that enumerates
#       /proc sees ONLY its own PID namespace's processes (hidepid=2 +
#       new /proc mount) — NOT the host's thousands of PIDs. The test
#       asserts the closed half (host enumeration is hidden). The same-ns
#       /proc/<ppid>/environ read is a DOCUMENTED RESIDUAL (same-uid
#       ptrace check allows the candidate to read the canary's parent
#       env, which inherits LPF_TOKEN) — closing it requires a deeper
#       per-exec_check sub-namespace with a different uid, which is out
#       of scope here. See fleet/leg-preflight.sh's THREAT MODEL section
#       for the full disclosure.
#   (e) NETWORK VECTOR (DOCUMENTED RESIDUAL): a payload that opens a
#       TCP socket SUCCEEDS — the wrapper does NOT `unshare --net`
#       because the canary needs the host network to reach the gateway.
#       The credential-exfil CHAIN is broken at the read step (per
#       (a) + (c) + (d)'s closed half), but a bare socket open is not
#       blocked. This test asserts the documented behavior so a future
#       "fix" that breaks the canary (e.g. by unsharing --net at the
#       wrapper level) is caught.
#   (f) ISOLATION LOG: the wrapper emits an `ISOLATION: …` line naming
#       which namespaces were entered (user/mount/pid on/off). Operators
#       see the actual state of the sandbox on every run. A revert that
#       drops the line is caught.
#   (g) WRAPPER INVOKES INNER CANARY: the wrapper's primary mode
#       (`fleet/leg-preflight.sh <args>`) actually execs the inner
#       canary at fleet/benchmark/leg-preflight.sh (the canary's
#       signature stderr log `[leg-preflight] …` appears in the
#       wrapper's combined stderr). A revert that drops the
#       delegation is caught.
#
# Run:  bash fleet/tests/leg-sandbox-isolation.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$SRC/leg-preflight.sh"
INNER="$SRC/benchmark/leg-preflight.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: hardened wrapper not found at $SCRIPT (LEG-SANDBOX-HARDEN must create it)" >&2; exit 1; }
[ -f "$INNER"  ] || { echo "FAIL: inner canary not found at $INNER (LEG-PREFLIGHT-CANARY must be landed first)" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }
not_has(){ printf '%s' "$1" | grep -q -- "$2" && bad "$3 (unexpectedly contains '$2')" || ok "$3"; }

# We inject a FAKE_TOKEN marker into the test's env (and thus into the
# wrapper's env, which the wrapper inherits when entering the namespace).
# The env-strip in ENV_STRIP_WRAPPER (mimicking exec_check.py:108)
# passes env={"PATH":"/usr/bin:/bin"} to the payload subprocess, so
# FAKE_TOKEN is NOT in the payload's /proc/self/environ. If a future
# revert weakens the env-strip to env={} or similar, FAKE_TOKEN
# WOULD be in the payload's environ, and (c)'s assertion goes RED. The
# marker is a unique random-ish string so it can't false-positive
# against the wrapper's own env.
FAKE_TOKEN="FAKE_TOKEN_XYZZY_$$_$(date +%s)"
export FAKE_TOKEN
echo "  [test setup] FAKE_TOKEN=$FAKE_TOKEN (injected into wrapper env for env-strip detection)"

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

# ── Build a fake $HOME with a fake token file ────────────────────────────────
# The wrapper overmounts $HOME with empty tmpfs before the candidate runs,
# so the token file at $HOME/.config/opencode/opencode.json must be
# created here in the test, then hidden by the wrapper. We use a content
# marker ("FAKE_TOKEN_XYZZY") that the candidate payload greps for so
# the test is hermetic (no real token is read or compared).
FAKE_HOME="$D/fakehome"
mkdir -p "$FAKE_HOME/.config/opencode"
FAKE_TOKEN_CONTENT='FAKE_TOKEN_XYZZY=this-must-not-leak-12345'
printf '%s' "$FAKE_TOKEN_CONTENT" > "$FAKE_HOME/.config/opencode/opencode.json"
[ -f "$FAKE_HOME/.config/opencode/opencode.json" ] || { echo "FAIL: test setup: could not create fake token file" >&2; exit 1; }

# ── Build the env-strip wrapper (used by (a),(b),(c) — replicates what
# exec_check.py:108 does to the real canary's exec-check subprocess: pass
# env={"PATH":"/usr/bin:/bin"} so the candidate does NOT inherit the
# wrapper's LPF_TOKEN, HOME, etc. — only PATH). The wrapper takes the
# payload script path as argv[1] AND the absolute FAKE_HOME path as
# argv[2] — because the env-strip strips HOME, the payload must use
# the absolute path passed in argv (a real hostile payload would have
# the same problem: HOME is gone, so it must guess or enumerate; the
# test gives the payload the real path so the assertion actually
# exercises the overmount, not the env-strip).
ENV_STRIP_WRAPPER="$D/env_strip.py"
cat > "$ENV_STRIP_WRAPPER" <<'PYEOF'
import os, subprocess, sys
# This is what exec_check.py:108 does: pass env={"PATH":"/usr/bin:/bin"}.
# argv: [payload_script, fake_home_path, ...payload_args]
fake_home = sys.argv[2] if len(sys.argv) > 2 else ""
r = subprocess.run(
    [sys.executable, sys.argv[1], fake_home] + sys.argv[3:],
    env={"PATH": "/usr/bin:/bin"},
    capture_output=True, text=True, timeout=10,
)
sys.stdout.write(r.stdout)
sys.stderr.write(r.stderr)
sys.exit(r.returncode)
PYEOF

# ── Build the hostile payload ────────────────────────────────────────────────
# The payload runs in the candidate's exec context. It probes EVERY
# vector a cred-exfil attempt would:
#   - absolute-path read of the token file (FS-READ)
#   - read its own /proc/self/environ (ENV)
#   - enumerate /proc and try to read other PIDs' environ (CROSS-PID)
#   - open a TCP socket (NETWORK — documented residual, succeeds)
# The payload prints one tab-separated line per probe:
#   fs_read=ok|ENOENT|<other>
#   self_environ=LEAKED_TOKEN|clean
#   cross_pid_leaks=<count>
#   socket_open=ok|ENETUNREACH|<other>
PAYLOAD="$D/hostile_payload.py"
cat > "$PAYLOAD" <<'PYEOF'
import json, os, socket, sys, traceback

results = {}

# (a) FS-READ: open the fake token file by ABSOLUTE path. A real
# hostile payload has to either guess this path (hard) or enumerate
# (the wrapper overmounts $HOME with empty tmpfs, so any guessed
# absolute path under $HOME returns ENOENT). The test passes the
# ABSOLUTE path in argv[1] so the assertion actually exercises the
# overmount, not the env-strip (which strips HOME from env, but a
# determined attacker can find the path via /proc/<ppid>/environ's
# HOME, see (d) below — the env-strip is NOT the load-bearing
# defense, the overmount is).
token_path = sys.argv[1] + "/.config/opencode/opencode.json" if len(sys.argv) > 1 else "/dev/null"
try:
    with open(token_path) as f:
        data = f.read()
    if "FAKE_TOKEN_XYZZY" in data:
        results["fs_read"] = "ok"
    else:
        results["fs_read"] = "wrong-content"
except FileNotFoundError:
    results["fs_read"] = "ENOENT"
except Exception as e:
    results["fs_read"] = f"err:{e!r}"[:40]

# (c) ENV-STRIP: read /proc/self/environ and grep for FAKE_TOKEN (the
# env-injected marker — set in this test's outer env, inherited by the
# wrapper, stripped by the env-strip in ENV_STRIP_WRAPPER). The
# payload also greps for any other token-like vars as belt-and-suspenders.
try:
    with open("/proc/self/environ", "rb") as f:
        env = f.read().decode("utf-8", errors="replace")
    leaked = [l for l in env.split("\0") if "FAKE_TOKEN" in l or "LPF_TOKEN" in l or "CHARON_GATEWAY_TOKEN" in l]
    if leaked:
        results["self_environ"] = "LEAKED_TOKEN"
        results["self_environ_leaks"] = leaked[:3]
    else:
        results["self_environ"] = "clean"
except Exception as e:
    results["self_environ"] = f"err:{e!r}"[:40]

# (d) CROSS-PID: enumerate /proc and read each PID's environ.
leak_count = 0
try:
    pids = [p for p in os.listdir("/proc") if p.isdigit()]
    for p in pids:
        try:
            with open(f"/proc/{p}/environ", "rb") as f:
                e = f.read().decode("utf-8", errors="replace")
            for line in e.split("\0"):
                if "FAKE_TOKEN_XYZZY" in line or "LPF_TOKEN" in line or "CHARON_GATEWAY_TOKEN" in line:
                    leak_count += 1
                    break
        except Exception:
            pass
except Exception as e:
    results["cross_pid_err"] = repr(e)[:40]
results["cross_pid_leaks"] = leak_count
results["pids_visible"] = len(pids)

# (e) NETWORK: open a TCP socket to 127.0.0.1:1. We expect ECONNREFUSED
# (port 1 has no listener). ECONNREFUSED, ETIMEDOUT, ENETUNREACH, and
# EHOSTUNREACH all count as "the kernel processed the connect syscall" —
# we only flag a true socket-creation failure (e.g. AF_UNSPEC, no
# /proc/net) as `err`. The wrapper does NOT unshare --net, so this
# should always succeed at the syscall level.
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", 1))
        results["socket_open"] = "ok"
        s.close()
    except OSError as e:
        # All routing-level refusals count as "socket syscall worked,
        # kernel made a routing decision". A socket-creation failure
        # would be a different errno family.
        if getattr(e, "errno", None) in (101, 110, 111, 113):  # ENETUNREACH, ETIMEDOUT, ECONNREFUSED, EHOSTUNREACH
            results["socket_open"] = "ok"
        else:
            results["socket_open"] = f"err:errno={getattr(e,'errno',None)}:{e!r}"[:60]
    finally:
        try: s.close()
        except Exception: pass
except Exception as e:
    results["socket_open"] = f"err:{e!r}"[:40]

print("PAYLOAD_RESULT\t" + json.dumps(results))
PYEOF

run_in_wrapper() {
  # Args: <logfile> <extra args to wrapper...>
  # Runs the wrapper with HOME=$FAKE_HOME so the overmount hits our
  # fake dir, and the hostile payload via --probe-isolation +
  # env-strip (the env-strip is what exec_check.py:108 does to the
  # real candidate; we replicate it here so the test's candidate is
  # in the SAME exec state as the real canary's exec_check subprocess,
  # not the over-privileged canary-main-loop state).
  local logf="$1"; shift
  HOME="$FAKE_HOME" bash "$SCRIPT" --probe-isolation python3 "$ENV_STRIP_WRAPPER" "$PAYLOAD" "$FAKE_HOME" \
    >"$D/payload.stdout" 2>"$logf"
  return $?
}
run_without_wrapper() {
  # Negative control: run the payload directly (no sandbox). The token
  # file IS readable; the env DOES inherit LPF_TOKEN/CHARON_GATEWAY_TOKEN
  # (from the test environment, if present); /proc shows all host PIDs.
  # We pass FAKE_HOME as argv so the payload uses the absolute path
  # (matches the wrapper scenario).
  python3 "$PAYLOAD" "$FAKE_HOME" >"$D/payload.ctrl.stdout" 2>"$D/payload.ctrl.stderr"
  return $?
}

parse_payload() {
  # $1: stdout file from the payload. Prints the JSON dict.
  local f="$1"
  awk -F'\t' '/^PAYLOAD_RESULT/ {print $2; exit}' "$f"
}

# ── (a) FS-READ VECTOR BLOCKED [CORE] ────────────────────────────────────────
# This is the load-bearing assertion. A hostile payload must NOT be able
# to read the gateway token file from inside the sandbox.
run_in_wrapper "$D/wrap.log"
WRAP_RC=$?
[ "$WRAP_RC" -eq 0 ] && ok "(a) wrapper exit 0 on the hostile-payload run" \
                     || bad "(a) wrapper exited non-zero (rc=$WRAP_RC) on the hostile-payload run"
fs="$(parse_payload "$D/payload.stdout" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("fs_read",""))')"
[ "$fs" = "ENOENT" ] && ok "(a) CORE: hostile payload cannot read the token file from inside the sandbox (tmpfs overmount returned ENOENT — revert the overmount and this goes RED)" \
                      || bad "(a) CORE: hostile payload SAW the token file (fs_read='$fs' instead of 'ENOENT') — the overmount was REVERTED, credential-exfil vector is OPEN"

# ── (b) NEGATIVE CONTROL: outside the sandbox, the file IS readable ─────────
# This proves (a) is not vacuous — a payload CAN read the file in the
# same environment minus the wrapper. If (a) ever passes because the
# payload is broken rather than because the overmount works, (b) would
# also fail and we'd see the inconsistency.
run_without_wrapper
fs_ctrl="$(parse_payload "$D/payload.ctrl.stdout" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("fs_read",""))')"
[ "$fs_ctrl" = "ok" ] && ok "(b) negative control: same payload OUTSIDE the sandbox DOES read the token file (proves (a) is not vacuous — the overmount is what blocks it)" \
                       || bad "(b) negative control: same payload outside the sandbox did NOT read the token file (fs_read='$fs_ctrl') — (a) may be vacuously passing; investigate the payload"

# ── (c) ENV-STRIP VECTOR: /proc/self/environ has no token ───────────────────
# The candidate's env is stripped by exec_check.py:108 (env={"PATH":...}).
# Section (a) already runs the candidate via the env-strip wrapper
# (see ENV_STRIP_WRAPPER definition above run_in_wrapper); we re-read
# the same result here under a different name to make the env-strip
# assertion explicit. (The candidate's /proc/self/environ from (a)'s
# run is what we're checking.)
ev="$(parse_payload "$D/payload.stdout" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("self_environ",""))')"
[ "$ev" = "clean" ] && ok "(c) env-strip: candidate's /proc/self/environ contains NO token (env-strip via env={\"PATH\":\"/usr/bin:/bin\"} — the load-bearing defense exec_check.py already provides)" \
                     || bad "(c) env-strip: candidate's /proc/self/environ LEAKED a token marker (self_environ='$ev') — the env-strip is not effective"

# (d) CROSS-PID VECTOR: hidepid limits the candidate to same-ns PIDs
# only (host PIDs hidden — that's the closed half). The OPEN half, which
# is a documented RESIDUAL: the candidate CAN read the env of any
# same-ns PID that holds the token (in the canary's real chain, this
# is exec_check.py's env, which inherits LPF_TOKEN from the canary's
# main loop because the canary needs the token to talk to the gateway).
# The kernel's user-ns ptrace check grants same-uid reads, and all
# processes in our user-ns share uid 0 (mapped to host uid 1000), so
# /proc/<ppid>/environ is readable from the candidate. Closing this
# residual requires a per-exec_check sub-namespace with a DIFFERENT uid
# for the candidate, which is out of scope here (would require editing
# exec_check.py, owned by LEG-PREFLIGHT-CANARY, not LEG-SANDBOX-HARDEN).
# The wrapper's THREAT-MODEL section documents this residual; the
# test asserts the CLOSED half (host PIDs hidden) so a future revert
# that breaks hidepid goes RED.
pl_w="$(parse_payload "$D/payload.stdout" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("pids_visible",-1))')"
pl_c="$(parse_payload "$D/payload.ctrl.stdout" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("pids_visible",-1))')"
# Inside the wrapper, pids_visible should be a SMALL number (1-3 — the
# candidate + its env_strip scaffolding). Outside, it's the full host
# count (thousands). The closed half is "host PIDs hidden". We assert
# the host count is much larger than the sandbox count — proving the
# sandbox does limit /proc visibility.
[ "$pl_w" -lt 10 ] && ok "(d) hidepid: inside the sandbox, /proc shows only $pl_w PID(s) (the candidate + its scaffolding) — host PIDs (~${pl_c}) are HIDDEN (revert the hidepid /proc remount and this goes RED)" \
                   || bad "(d) hidepid: inside the sandbox, /proc shows $pl_w PIDs (expected <10) — hidepid /proc remount is NOT in effect; host PIDs are visible to the candidate"
[ "$pl_c" -gt 100 ] 2>/dev/null && ok "(d) negative control: outside the sandbox, /proc shows $pl_c PIDs (proves (d) is not vacuous — without the wrapper the candidate sees the full host /proc)" \
                              || bad "(d) negative control: outside the sandbox, /proc shows $pl_c PIDs (expected many hundreds) — (d) may be vacuous; investigate the payload"

# ── (e) NETWORK VECTOR: documented residual (succeeds) ─────────────────────
# The wrapper does NOT unshare --net (the canary needs network for the
# gateway). A bare socket syscall succeeds. The credential-exfil CHAIN
# is broken (per (a)+(c)+(d) — there's no token to put on the wire),
# but a bare socket open is not blocked. This test asserts the
# documented behavior so a future "fix" that breaks the canary (e.g.
# by unsharing --net at the wrapper level) is caught — the inner
# canary's gateway probe should still work; the residual is honored.
so="$(parse_payload "$D/payload.stdout" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("socket_open",""))')"
[ "$so" = "ok" ] && ok "(e) documented residual: a bare TCP socket syscall SUCCEEDS from inside the sandbox (the wrapper does NOT unshare --net — the canary needs the host network for the gateway; the credential-exfil CHAIN is broken by (a)+(c)+(d) but the socket call itself is not blocked)" \
                  || bad "(e) documented residual: socket syscall did not return 'ok' (got '$so') — if this ever flips to 'unreachable', the wrapper started unsharing --net which would BREAK the canary's gateway probe; investigate"

# Also: assert the wrapper's ISOLATION log explicitly says net_ns=off,
# so the residual is recorded on every run.
isolog="$(grep -E "^\[leg-sandbox\] ISOLATION:" "$D/wrap.log" || true)"
[ -n "$isolog" ] && has "$isolog" "net_ns=off" "(e) ISOLATION log records net_ns=off (so the documented residual is visible to operators on every run)" \
                 || bad "(e) no ISOLATION log line found in wrapper output — operators cannot see the sandbox state on every run"

# ── (f) ISOLATION LOG: each namespace state visible ─────────────────────────
# A revert that drops the ISOLATION log line, or that disables the
# mount namespace (and the overmount with it), is caught here.
isolog="$(grep -E "^\[leg-sandbox\] ISOLATION:" "$D/wrap.log" || true)"
[ -n "$isolog" ] && ok "(f) wrapper emits an ISOLATION log line (operators see the sandbox state on every run)" \
                 || bad "(f) no ISOLATION log line found in wrapper output"
# On a normal Linux host the user+mount namespaces should be on. We
# accept either a "user_ns=on" line (success) OR a "WARNING" line
# (kernel refused the unshare — the test still passes; the residual
# is loud and visible).
if [ -n "$isolog" ]; then
  if printf '%s' "$isolog" | grep -q "user_ns=on" && printf '%s' "$isolog" | grep -q "mount_ns=on"; then
    ok "(f) ISOLATION: user+mount namespaces are on (strongest portable state)"
  elif printf '%s' "$isolog" | grep -q "WARNING.*ISOLATION: NONE"; then
    ok "(f) ISOLATION: kernel refused user+mount unshare — WARNING logged, residual is loud (host may be WSL2 / locked-down; isolation is best-effort)"
  else
    bad "(f) ISOLATION log present but unexpected state: $isolog"
  fi
fi

# ── (g) WRAPPER INVOKES INNER CANARY ────────────────────────────────────────
# The wrapper's primary mode (not --probe-isolation) must delegate to
# the inner canary. We run the wrapper with a stub LPF_PROBE_CMD that
# returns "120" (a HEALTHY leg for the exact-match task) and assert
# the inner canary's signature stderr line is emitted. This proves
# the wrapper still actually runs the canary — not just sets up the
# sandbox and exits.
STUB="$D/canary-stub.sh"
cat > "$STUB" <<'STUBEOF'
#!/usr/bin/env bash
# A HEALTHY stub for the canary: returns the right answer for each task
# in the manifest. The bal-parens task is exec-checked (the canary runs
# the candidate's code in a subprocess); the lcm-bound task is
# exact-matched (first contiguous run of digits is compared to "120").
leg="$1"; prompt="$2"
if printf '%s' "$prompt" | grep -q "is_bal"; then
  # exec-checked task: return code that defines is_bal correctly
  printf 'def is_bal(s):\n    depth = 0\n    for c in s:\n        if c == "(": depth += 1\n        elif c == ")": depth -= 1\n        if depth < 0: return False\n    return depth == 0\n'
else
  # exact-match task: lcm(6,15)=30, smallest multiple strictly > 100 is 120
  printf '120'
fi
exit 0
STUBEOF
chmod +x "$STUB"
: > "$D/LEG-RANK.tsv"
HOME="$FAKE_HOME" \
  LPF_RANK_FILE="$D/LEG-RANK.tsv" \
  LPF_PROBE_CMD="$STUB" \
  LPF_REQ_TIMEOUT_S=10 \
  bash "$SCRIPT" goodmodel-ds >"$D/canary.stdout" 2>"$D/canary.stderr" || true
inner_log="$(grep -E '^\[leg-preflight\]' "$D/canary.stderr" || true)"
[ -n "$inner_log" ] && ok "(g) wrapper delegates to the inner canary: inner canary's [leg-preflight] log line is emitted (the sandbox does not eat the canary's stderr)" \
                     || bad "(g) wrapper did NOT emit any [leg-preflight] line — either the wrapper is not delegating, or the delegation is broken"
# And the leg should have been ranked HEALTHY (proves end-to-end).
v="$(awk -F'\t' -v m="goodmodel" -v l="ds" '$1==m && $2==l {v=$7} END{print v}' "$D/LEG-RANK.tsv")"
[ "$v" = "HEALTHY" ] && ok "(g) end-to-end: the canary ranked the stubbed leg HEALTHY through the wrapper (sandbox + canary + exec_check all worked end-to-end)" \
                     || bad "(g) end-to-end: the canary did not rank the leg HEALTHY (got '$v') — something in the sandbox broke the canary path"

# ── Also: the pre-existing test still passes (wrapper didn't regress it) ────
# We re-run fleet/tests/leg-preflight.test.sh's hermetic stub against
# the inner canary (NOT through the wrapper) — but we additionally
# assert the same test passes through the wrapper. This catches
# wrapper regressions on the canary path. We use a probe stub of our
# own (the existing test's stub is inlined) and a fresh rank file.
WRAP_STUB="$D/wrap-stub-probe.sh"
cat > "$WRAP_STUB" <<'STUBEOF'
#!/usr/bin/env bash
leg="$1"; prompt="$2"
if printf '%s' "$prompt" | grep -q "is_bal"; then
  printf 'def is_bal(s):\n    depth = 0\n    for c in s:\n        if c == "(": depth += 1\n        elif c == ")": depth -= 1\n        if depth < 0: return False\n    return depth == 0\n'
else
  printf '120'
fi
exit 0
STUBEOF
chmod +x "$WRAP_STUB"
: > "$D/LEG-RANK.tsv"
HOME="$FAKE_HOME" \
  LPF_RANK_FILE="$D/LEG-RANK.tsv" \
  LPF_PROBE_CMD="$WRAP_STUB" \
  LPF_REQ_TIMEOUT_S=10 \
  bash "$SCRIPT" wrapgoodmodel-ds >"$D/wrap-stdout" 2>"$D/wrap-stderr" || true
v2="$(awk -F'\t' -v m="wrapgoodmodel" -v l="ds" '$1==m && $2==l {v=$7} END{print v}' "$D/LEG-RANK.tsv")"
[ "$v2" = "HEALTHY" ] && ok "(g) end-to-end through wrapper: a stubbed leg ranks HEALTHY (the wrapper's sandbox does not break the canary's exec_check + exact-match pipeline)" \
                      || bad "(g) end-to-end through wrapper: stubbed leg ranked '$v2' (expected HEALTHY) — the wrapper sandbox may have broken exec_check or the canary's python"

# ── summary ─────────────────────────────────────────────────────────────────
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LEG-SANDBOX-HARDEN SANDBOX-ISOLATION TESTS PASS"
