# bandit-known-bad.py — FIXTURE. NOT product code. Deliberately contains an insecure pattern
# (subprocess with shell=True) so the canary can prove the bandit gate actually fires.
#
# The shell=True call trips bandit test B602 (subprocess_popen_with_shell_equals_true), a HIGH
# severity finding — so it is caught at ANY severity threshold. Neutering B602 (config skips:) drops
# the finding count to zero; that drop is what proves B602 detection is load-bearing, not vacuous.
import subprocess


def run_untrusted(cmd):
    # VIOLATION (B602, HIGH): a shell command built from an argument, run with shell=True — the
    # classic shell-injection sink bandit exists to catch.
    return subprocess.call(cmd, shell=True)
