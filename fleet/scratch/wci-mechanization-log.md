# WCI mechanization — build log (2026-07-08)

Mechanized the "WCI ticket-decompose method" into the fleet rig so it self-enforces
(advisory / RECOMMEND semantic — flag, don't hard-block). Did NOT touch fleet/board/ or
validate_board.sh (owned by another live session). Not committed/pushed (manager lands).

## Artifacts

- **Doctrine doc:** `/home/stack/charon-private/fleet/WCI-METHOD.md`
  The repeatable 5-step method (dedup → find contention axis → god-file decompose →
  re-slice into collision-free waves → sequence), a "run this BEFORE opening tabs" note,
  and a reference to the detector.

- **Detector (new, executable):** `/home/stack/charon-private/fleet/wci-contention.sh`
  Scans every `board/*.md` + `board/*.md.parked`, parses the `owns:` field, counts owning
  tickets per file, prints any file owned by ≥ N tickets (N default 4, override via `$1`)
  as a `DECOMPOSE CANDIDATE` with the owning-ticket list. Robust to missing/empty owns;
  always exits 0 (advisory). Run: `fleet/wci-contention.sh [N]`.

## preflight.sh wiring (exact lines added)

Added a new detector function before `cmd_detect()` in `fleet/preflight.sh`:

```bash
# WCI high-contention-file advisory: a file owned by >= N tickets is a DECOMPOSE
# CANDIDATE (collision metric -> refactor trigger). Informational; never fails preflight.
# Delegates to wci-contention.sh (fleet/WCI-METHOD.md). Top line surfaced here; run the
# script directly for the full owner lists.
detect_wci_contention(){
  local script="$HERE/wci-contention.sh"
  [ -x "$script" ] || { echo "wci-contention: detector not found/executable at $script"; return 0; }
  local out top
  out="$(bash "$script" 2>/dev/null)"
  if printf '%s\n' "$out" | grep -q 'DECOMPOSE CANDIDATE'; then
    local n
    n="$(printf '%s\n' "$out" | grep -c 'DECOMPOSE CANDIDATE')"
    echo "DETECTED (unregistered): wci-contention — $n DECOMPOSE CANDIDATE file(s) (owned by >= 4 tickets)"
    printf '%s\n' "$out" | grep 'DECOMPOSE CANDIDATE:' | head -5 | sed 's/^ */    /'
    [ "$n" -gt 5 ] && echo "    +$((n-5)) more — run: fleet/wci-contention.sh"
    echo "    -> run the WCI pass BEFORE opening tabs on a backlog (fleet/WCI-METHOD.md)"
  else
    echo "clean: wci-contention (no file owned by >= 4 tickets)"
  fi
}
```

And added one call line inside `cmd_detect()`, after `detect_repo_drift`:

```bash
  detect_wci_contention
```

It prints as a `DETECTED (unregistered):` advisory line matching the existing style — purely
informational, does NOT fail preflight (`cmd_detect` still returns 0).

## Detector current output (threshold N=4)

19 DECOMPOSE CANDIDATE files right now. Top of the list:

```
  DECOMPOSE CANDIDATE: src/charon/proxy_server.py — owned by 25 tickets
  DECOMPOSE CANDIDATE: src/charon/cli.py — owned by 16 tickets
  DECOMPOSE CANDIDATE: src/charon/config.py — owned by 12 tickets
  DECOMPOSE CANDIDATE: src/charon/gateway.py — owned by 11 tickets
  DECOMPOSE CANDIDATE: src/charon/proxy.py — owned by 7 tickets
  DECOMPOSE CANDIDATE: src/charon/api.py — owned by 6 tickets
  DECOMPOSE CANDIDATE: tools/check_boundary.py — owned by 5 tickets
  DECOMPOSE CANDIDATE: tests/test_gateway.py — owned by 5 tickets
  DECOMPOSE CANDIDATE: src/charon/providers.py — owned by 5 tickets
  DECOMPOSE CANDIDATE: README.md — owned by 5 tickets
  DECOMPOSE CANDIDATE: tests/test_agent_launch_routing.py — owned by 4 tickets
  DECOMPOSE CANDIDATE: src/charon/ports/agent_launch.py — owned by 4 tickets
  DECOMPOSE CANDIDATE: src/charon/connect.py — owned by 4 tickets
  DECOMPOSE CANDIDATE: src/charon/adapters/acp.py — owned by 4 tickets
  DECOMPOSE CANDIDATE: pyproject.toml — owned by 4 tickets
  DECOMPOSE CANDIDATE: capability/grades.py — owned by 4 tickets
  DECOMPOSE CANDIDATE: benchmark/lib/tier_chart.py — owned by 4 tickets
  DECOMPOSE CANDIDATE: .github/workflows/release.yml — owned by 4 tickets
```

**Top decompose candidate: `src/charon/proxy_server.py` (owned by 25 tickets)** — exactly the
god-file that motivated this method. `cli.py` (16), `config.py` (12), and `gateway.py` (11) are
the next structural offenders.

`preflight.sh -n` syntax check: PASS. `preflight.sh detect` shows the advisory line and does not
fail preflight.
