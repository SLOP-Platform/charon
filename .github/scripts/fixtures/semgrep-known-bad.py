# semgrep-known-bad.py — FIXTURE. NOT product code, never imported, never packaged. Deliberately
# violates charon-policy.yml RULE 1 (charon-no-hardcoded-lan-host) so the canary can prove the
# gate actually fires.
#
# It triggers RULE 1 ONLY (no developer-home absolute path here) so that neutering RULE 1 drops
# the finding count to zero — that drop is what proves RULE 1 is load-bearing, not vacuous.
#
# This directory is excluded from the wrappers' tree/diff scans (a PR that ADDS a fixture must not
# red on its own fixture); the canary scans it by EXPLICIT path instead.


def gateway_base_url():
    # VIOLATION (RULE 1): a hardcoded private-LAN address on the routing plane. Hosts must be read
    # from env/config so a fresh install on any other machine still works.
    return "http://192.168.42.7:8080/v1"  # public-clean: allow — the fixture must contain the literal it proves is detected
